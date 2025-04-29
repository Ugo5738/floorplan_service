# floorplan/management/commands/check_sdb_fp_consistency.py
import time
from datetime import datetime, timedelta, timezone

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import CharField, Value
from django.utils.dateparse import parse_datetime
from requests.exceptions import RequestException

# Import THIS service's models and utils
from floorplan.models import FloorPlan, FloorPlanAnalysisResult
from floorplan.utils.backup import serialize_floorplan_for_sdb

# Import logger from THIS service
from floorplan_service.config.logging_config import configure_logger

logger = configure_logger(__name__)


# --- Helper to fetch paginated data from SDB API ---
def fetch_paginated_sdb_data(
    api_url, data_key="results", id_field="primary_key", fields=None
):
    """Fetches all data from a paginated SDB check endpoint."""
    data = {}
    next_url = api_url
    page_num = 1
    logger.info(f"Fetching paginated SDB data from {api_url}...")
    retrieved_count = 0

    while next_url:
        try:
            logger.debug(
                f"Fetching SDB page {page_num} from {next_url}"
            )  # More detailed logging
            response = requests.get(next_url, timeout=30)  # Increased timeout
            response.raise_for_status()
            page_data = response.json()

            results = page_data.get(data_key, [])
            if not results:
                logger.debug("No results in page data.")
                break  # Stop if no results on a page

            for item in results:
                key = item.get(id_field)
                if key is not None:
                    # Only store requested fields if specified
                    data[key] = {f: item.get(f) for f in fields} if fields else item
                    retrieved_count += 1
                else:
                    logger.warning(
                        f"Warning: SDB Item missing ID field '{id_field}': {item}"
                    )

            next_url = page_data.get("next")
            if next_url:
                page_num += 1
            # time.sleep(0.05) # Optional delay between pages

        except RequestException as e:
            logger.error(f"SDB API request failed for {next_url or api_url}: {e}")
            if hasattr(e, "response") and e.response is not None:
                logger.error(
                    f"Response status: {e.response.status_code}, Body: {e.response.text[:200]}"
                )
            return None  # Indicate failure
        except Exception as e:
            logger.error(
                f"Error processing paginated SDB data from {next_url or api_url}: {e}"
            )
            return None  # Indicate failure

    logger.info(f"Finished fetching SDB data. Total records mapped: {len(data)}")
    return data


class Command(BaseCommand):
    help = "Checks Floorplan data consistency (Results & Plans) between Floorplan service and the SDB aggregate database via APIs."

    def add_arguments(self, parser):
        parser.add_argument("--staleness-threshold-hours", type=int, default=24)
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Limit source records checked PER MODEL.",
        )
        parser.add_argument("--fix-missing", action="store_true")
        parser.add_argument("--fix-mismatched", action="store_true")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--delay", type=float, default=0.1)

    def handle(self, *args, **options):
        staleness_threshold = timedelta(hours=options["staleness_threshold_hours"])
        limit = options["limit"]
        fix_missing = options["fix_missing"]
        fix_mismatched = options["fix_mismatched"]
        dry_run = options["dry_run"]
        delay = options["delay"]

        self.stdout.write(
            self.style.SUCCESS("--- Starting Floorplan -> SDB Consistency Check ---")
        )
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN mode enabled."))

        # Get SDB Base URL from this service's settings
        sdb_base_url = getattr(settings, "BACKUP_SERVICE_URL", None)
        if not sdb_base_url:
            raise CommandError(
                "BACKUP_SERVICE_URL (pointing to SDB service) is not configured in Floorplan settings."
            )
        sdb_base_url = sdb_base_url.rstrip("/")

        # --- Define Checks ---
        # SDB Fix URL is the same for both, as Floorplan payload includes AnalysisResult
        sdb_fix_url = f"{sdb_base_url}/api/sdb/floorplan/"
        can_fix = (fix_missing or fix_mismatched) and not dry_run
        if can_fix:
            self.stdout.write(self.style.WARNING("\nFixing enabled."))

        overall_summary = {}

        # --- Check FloorPlanAnalysisResult ---
        self.stdout.write(
            self.style.MIGRATE_HEADING("\n--- Checking FloorPlanAnalysisResult ---")
        )
        fpa_summary = self._check_fpa_results(
            limit,
            staleness_threshold,
            fix_missing,
            fix_mismatched,
            dry_run,
            sdb_base_url
            + "/api/sdb/check/fp-analysis-results/",  # Requires this endpoint in SDB
            sdb_fix_url,
            delay,
        )
        overall_summary["FloorPlanAnalysisResult"] = fpa_summary

        # --- Check FloorPlan ---
        # (Potentially skip if FPA results had major issues)
        # We need the mapping from FPA check if we need to trigger fixes based on FP mismatch
        self.stdout.write(self.style.MIGRATE_HEADING("\n--- Checking FloorPlan ---"))
        fp_summary = self._check_floorplans(
            limit,
            staleness_threshold,
            fix_missing,
            fix_mismatched,
            dry_run,
            sdb_base_url
            + "/api/sdb/check/floorplans/",  # Requires this endpoint in SDB
            sdb_fix_url,
            delay,
        )
        overall_summary["FloorPlan"] = fp_summary

        # --- Final Summary ---
        self.stdout.write(
            self.style.SUCCESS("\n--- Overall Floorplan Check Summary ---")
        )
        for model_key, summary in overall_summary.items():
            self.stdout.write(f"{model_key}:")
            for key, value in summary.items():
                style = (
                    self.style.SUCCESS
                    if value == 0 or key.startswith("source") or key.startswith("sdb")
                    else self.style.WARNING
                )
                self.stdout.write(
                    style(f"  {key.replace('_', ' ').capitalize()}: {value}")
                )
            if summary.get("fix_api_errors", 0) > 0:
                self.stdout.write(
                    self.style.ERROR("  Fixing API errors occurred. Check logs.")
                )

    def _check_fpa_results(
        self,
        limit,
        staleness_threshold,
        fix_missing,
        fix_mismatched,
        dry_run,
        sdb_check_url,
        sdb_fix_url,
        delay,
    ):
        """Checks FloorPlanAnalysisResult consistency."""
        summary = self._initialize_summary()
        source_model = FloorPlanAnalysisResult
        src_pk_field = "id"

        # Fetch Source FPA Results
        self.stdout.write(
            "Fetching data from source Floorplan DB (FloorPlanAnalysisResult)..."
        )
        source_data = {}
        try:
            source_qs = source_model.objects.using("default").order_by(src_pk_field)
            if limit:
                source_qs = source_qs[:limit]
            source_values = source_qs.values(
                src_pk_field, "updated_at", "user_id", "property_id"
            )
            for item in source_values.iterator():
                # Use composite key for matching as SDB might not store source PK directly for FPAResult
                key = f"{item['user_id']}|{item['property_id']}"
                source_data[key] = item
            summary["source_records_checked"] = len(source_data)
            self.stdout.write(
                f"Fetched {summary['source_records_checked']} records from source."
            )
        except Exception as e:
            self.stderr.write(
                self.style.ERROR(f"Error fetching source FPA Results: {e}")
            )
            summary["errors_fetching_source"] += 1
            return summary

        # Fetch SDB FPA Results via API
        self.stdout.write(
            f"Fetching corresponding FPA Result data from SDB API: {sdb_check_url} ..."
        )
        sdb_api_fields = [
            "unique_id",
            "updated_at",
            "id",
        ]  # SDB Check API should return unique_id and SDB PK ('id')
        sdb_data_raw = fetch_paginated_sdb_data(
            sdb_check_url, id_field="unique_id", fields=sdb_api_fields
        )
        if sdb_data_raw is None:
            summary["errors_fetching_sdb"] += 1
            return summary
        summary["sdb_records_found"] = len(sdb_data_raw)
        self.stdout.write(
            f"Fetched {summary['sdb_records_found']} records from SDB API."
        )

        # Compare FPA Results
        missing_pks_to_fix = (
            []
        )  # Store SOURCE PKs of FPA Results whose FloorPlan needs resync
        mismatched_pks_to_fix = []
        now_aware = timezone.now()

        source_pks_by_unique_key = {
            f"{d['user_id']}|{d['property_id']}": d[src_pk_field]
            for d in source_data.values()
        }

        for unique_key, source_item in source_data.items():
            sdb_item = sdb_data_raw.get(unique_key)
            source_pk = source_item[src_pk_field]

            if sdb_item is None:
                summary["missing_in_sdb"] += 1
                missing_pks_to_fix.append(source_pk)  # Mark for fix
            else:
                source_updated = source_item.get("updated_at")
                sdb_updated_str = sdb_item.get("updated_at")
                sdb_updated = (
                    parse_datetime(sdb_updated_str) if sdb_updated_str else None
                )
                if sdb_updated and not sdb_updated.tzinfo:
                    sdb_updated = timezone.make_aware(sdb_updated, timezone.utc)

                if source_updated and sdb_updated and source_updated > sdb_updated:
                    if (now_aware - sdb_updated) > staleness_threshold:
                        summary["potentially_stale_update"] += 1
                        mismatched_pks_to_fix.append(source_pk)  # Mark for fix
                        self.stdout.write(
                            f"\n  Potentially Stale FPA Result for Source PK {source_pk} (Key: {unique_key}): Source={source_updated}, SDB={sdb_updated}"
                        )

        # --- Trigger Fixes (by re-syncing the *entire* FloorPlan linked to the FPA Result) ---
        can_fix = (fix_missing or fix_mismatched) and not dry_run
        pks_to_fix = set(missing_pks_to_fix + mismatched_pks_to_fix)

        if can_fix and pks_to_fix:
            self.stdout.write(
                self.style.WARNING(
                    f"\nAttempting to trigger re-sync for {len(pks_to_fix)} FloorPlans due to FPA Result discrepancies..."
                )
            )
            for source_fpa_pk in pks_to_fix:
                # Find the *most recent* FloorPlan associated with this FPA Result in the source DB
                # This assumes the latest FP reflects the state that *should* be in SDB
                source_fp_to_fix = (
                    FloorPlan.objects.using("default")
                    .filter(analysis_result_id=source_fpa_pk)
                    .order_by("-updated_at")
                    .first()
                )
                if source_fp_to_fix:
                    if self._fix_floorplan_api(
                        source_fp_to_fix.pk,
                        serialize_floorplan_for_sdb,
                        sdb_fix_url,
                        delay,
                        dry_run,
                    ):
                        if source_fpa_pk in missing_pks_to_fix:
                            summary["fixes_attempted_missing"] += 1
                        if source_fpa_pk in mismatched_pks_to_fix:
                            summary["fixes_attempted_mismatched"] += 1
                    else:
                        summary["fix_api_errors"] += 1
                else:
                    self.stderr.write(
                        self.style.ERROR(
                            f"  Cannot fix FPA PK {source_fpa_pk}: No corresponding FloorPlan found in source DB."
                        )
                    )
                    summary["fix_api_errors"] += 1  # Count as error

        return summary

    def _check_floorplans(
        self,
        limit,
        staleness_threshold,
        fix_missing,
        fix_mismatched,
        dry_run,
        sdb_check_url,
        sdb_fix_url,
        delay,
    ):
        """Checks FloorPlan consistency."""
        summary = self._initialize_summary()
        source_model = FloorPlan
        src_pk_field = "id"
        source_unique_field = "floorplan_id"  # Use the hash for matching

        # Fetch Source FloorPlans
        self.stdout.write("Fetching data from source Floorplan DB (FloorPlan)...")
        source_data = {}
        try:
            source_qs = source_model.objects.using("default").order_by(src_pk_field)
            if limit:
                source_qs = source_qs[:limit]
            # Fetch fields needed for comparison and the source PK for fixing
            source_values = source_qs.values(
                src_pk_field, source_unique_field, "updated_at", "update_count"
            )
            for item in source_values.iterator():
                source_data[item[source_unique_field]] = (
                    item  # Key by floorplan_id hash
                )
            summary["source_records_checked"] = len(source_data)
            self.stdout.write(
                f"Fetched {summary['source_records_checked']} records from source."
            )
        except Exception as e:
            self.stderr.write(
                self.style.ERROR(f"Error fetching source FloorPlans: {e}")
            )
            summary["errors_fetching_source"] += 1
            return summary

        # Fetch SDB FloorPlans via API
        self.stdout.write(
            f"Fetching corresponding FloorPlan data from SDB API: {sdb_check_url} ..."
        )
        # Ask SDB check API for floorplan_id, updated_at, update_count
        sdb_api_fields = ["floorplan_id", "updated_at", "update_count"]
        sdb_data_raw = fetch_paginated_sdb_data(
            sdb_check_url, id_field="floorplan_id", fields=sdb_api_fields
        )
        if sdb_data_raw is None:
            summary["errors_fetching_sdb"] += 1
            return summary
        summary["sdb_records_found"] = len(sdb_data_raw)
        self.stdout.write(
            f"Fetched {summary['sdb_records_found']} records from SDB API."
        )
        # SDB data is already keyed by floorplan_id

        # Compare FloorPlans
        missing_pks_to_fix = []  # Store SOURCE PKs
        mismatched_pks_to_fix = []
        now_aware = timezone.now()

        for fp_hash, source_item in source_data.items():
            sdb_item = sdb_data_raw.get(fp_hash)
            source_pk = source_item[src_pk_field]

            if sdb_item is None:
                summary["missing_in_sdb"] += 1
                missing_pks_to_fix.append(source_pk)
            else:
                stale = False
                content_diff = False
                # Compare updated_at
                source_updated = source_item.get("updated_at")
                sdb_updated_str = sdb_item.get("updated_at")
                sdb_updated = (
                    parse_datetime(sdb_updated_str) if sdb_updated_str else None
                )
                if sdb_updated and not sdb_updated.tzinfo:
                    sdb_updated = timezone.make_aware(sdb_updated, timezone.utc)

                if source_updated and sdb_updated and source_updated > sdb_updated:
                    if (now_aware - sdb_updated) > staleness_threshold:
                        stale = True
                        self.stdout.write(
                            f"\n  Potentially Stale FloorPlan {fp_hash} (PK {source_pk}): Source={source_updated}, SDB={sdb_updated}"
                        )

                # Compare update_count
                source_uc = source_item.get("update_count")
                sdb_uc = sdb_item.get("update_count")
                if source_uc != sdb_uc:  # Simple comparison
                    content_diff = True
                    self.stdout.write(
                        f"\n  Update Count Mismatch for FloorPlan {fp_hash} (PK {source_pk}): Source={source_uc}, SDB={sdb_uc}"
                    )

                if stale or content_diff:
                    summary["potentially_stale_or_mismatched"] += 1
                    mismatched_pks_to_fix.append(source_pk)

        # --- Trigger Fixes (by re-syncing the *entire* FloorPlan) ---
        can_fix = (fix_missing or fix_mismatched) and not dry_run
        pks_to_fix = set(missing_pks_to_fix + mismatched_pks_to_fix)

        if can_fix and pks_to_fix:
            self.stdout.write(
                self.style.WARNING(
                    f"\nAttempting to trigger re-sync for {len(pks_to_fix)} FloorPlans..."
                )
            )
            for source_fp_pk in pks_to_fix:
                if self._fix_floorplan_api(
                    source_fp_pk,
                    serialize_floorplan_for_sdb,
                    sdb_fix_url,
                    delay,
                    dry_run,
                ):
                    if source_fp_pk in missing_pks_to_fix:
                        summary["fixes_attempted_missing"] += 1
                    if source_fp_pk in mismatched_pks_to_fix:
                        summary["fixes_attempted_mismatched"] += 1
                else:
                    summary["fix_api_errors"] += 1
        return summary

    def _initialize_summary(self):
        """Returns a dictionary to store check results."""
        return {
            "source_records_checked": 0,
            "sdb_records_found": 0,
            "missing_in_sdb": 0,
            "potentially_stale_update": 0,
            "content_mismatched": 0,  # Keep track if specific content differs
            "errors_fetching_source": 0,
            "errors_fetching_sdb": 0,
            "fixes_attempted_missing": 0,
            "fixes_attempted_mismatched": 0,
            "fix_api_errors": 0,
        }

    def _fix_floorplan_api(
        self, source_pk, serialize_func, sdb_fix_url, delay, dry_run
    ):
        """Fetches source FloorPlan, serializes (including nested), and POSTs to SDB."""
        # This helper reuses the logic from the Property fix, adapted for FloorPlan
        if dry_run:
            self.stdout.write(
                f"\n  [DRY RUN] Would trigger fix for FloorPlan PK {source_pk} -> {sdb_fix_url}"
            )
            return True

        if not sdb_fix_url or not serialize_func:
            self.stderr.write(
                self.style.ERROR(
                    f"  Cannot fix FloorPlan PK {source_pk}: API endpoint or serialize function not configured."
                )
            )
            return False
        try:
            # Fetch the full instance with prefetched data for serialization
            instance = (
                FloorPlan.objects.using("default")
                .select_related("analysis_result")
                .prefetch_related(
                    "all_floors_data",
                    "all_floors_data__csv_floors__rooms__pixel_data",
                    "all_floors_data__csv_floors__rooms__dimensions",
                    "all_floors_data__csv_floors__rooms__scaling_factors",
                    "all_floors_data__all_floors_csv_data",
                    "all_floors_data__total_areas_csv_data",
                    "plan_floors",
                )
                .get(pk=source_pk)
            )

            payload = serialize_func(instance)

            if payload is None:
                self.stderr.write(
                    self.style.ERROR(
                        f"  Serialization failed for FloorPlan PK {source_pk}. Cannot fix."
                    )
                )
                return False

            self.stdout.write(
                f"\n  Attempting POST fix for FloorPlan PK {source_pk} to {sdb_fix_url}..."
            )
            response = requests.post(
                sdb_fix_url, json=payload, timeout=60
            )  # Longer timeout for complex payload
            response.raise_for_status()
            self.stdout.write(
                self.style.SUCCESS(
                    f"    Fix successful (Status: {response.status_code})."
                )
            )
            if delay > 0:
                time.sleep(delay)
            return True

        except FloorPlan.DoesNotExist:
            self.stderr.write(
                self.style.ERROR(
                    f"  Cannot fix FloorPlan PK {source_pk}: Record not found in source DB anymore."
                )
            )
            return False
        except RequestException as e:
            self.stderr.write(
                self.style.ERROR(f"  API Error fixing FloorPlan PK {source_pk}: {e}")
            )
            if hasattr(e, "response") and e.response is not None:
                logger.error(f"  Fix API Response status: {e.response.status_code}")
                logger.error(f"  Fix API Response text: {e.response.text[:500]}")
            return False
        except Exception as e:
            self.stderr.write(
                self.style.ERROR(
                    f"  Unexpected error fixing FloorPlan PK {source_pk}: {e}"
                )
            )
            logger.exception(f"Unexpected error fixing FloorPlan PK {source_pk}")
            return False
