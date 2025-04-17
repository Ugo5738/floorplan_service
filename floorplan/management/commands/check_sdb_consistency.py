# floorplan/management/commands/check_sdb_consistency.py
import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connections
from django.db.utils import OperationalError

# Import models from BOTH apps (assuming sdb models are accessible somehow,
# or we query raw SQL, or we define simplified stub models here).
# For simplicity, let's assume we query floorplan_id and updated_at from both.
from floorplan.models import FloorPlan as FloorPlanSource
from floorplan.utils.backup import serialize_floorplan_for_sdb  # For re-sync
from floorplan_service.config.logging_config import configure_logger

# We need a way to represent the SDB FloorPlan model.
# Easiest way IF sdb is installed as an app (unlikely): from sdb.models import FloorPlan as FloorPlanBackup
# Alternative: Raw SQL or define a stub model if needed.
# Let's try querying via alias directly.


logger = configure_logger(__name__)


class Command(BaseCommand):
    help = "Compares FloorPlan records between the source (default) and SDB backup databases."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Limit the number of records fetched from the source DB for comparison.",
        )
        parser.add_argument(
            "--check-updated",
            action="store_true",
            help="Compare the updated_at timestamp for matching records.",
        )
        parser.add_argument(
            "--fix-missing",
            action="store_true",
            help="Attempt to sync records found in source DB but missing in SDB.",
        )
        parser.add_argument(
            "--api-url",
            type=str,
            default=None,
            help="Override the SDB API URL from settings (needed for --fix-missing).",
        )
        parser.add_argument(
            "--delay",
            type=float,
            default=0.1,
            help="Delay in seconds between API calls if using --fix-missing.",
        )

    def handle(self, *args, **options):
        limit = options["limit"]
        check_updated = options["check_updated"]
        fix_missing = options["fix_missing"]
        api_url_override = options["api_url"]
        delay = options["delay"]

        source_db = "default"
        backup_db = "sdb_backup"

        self.stdout.write(
            self.style.SUCCESS(
                f"--- Starting Consistency Check: '{source_db}' vs '{backup_db}' ---"
            )
        )

        # Check if backup DB alias exists
        if backup_db not in settings.DATABASES:
            raise CommandError(
                f"Database alias '{backup_db}' not found in settings. "
                f"Ensure it's configured correctly (e.g., in settings/dev.py)."
            )

        # Test connections
        try:
            connections[source_db].ensure_connection()
            self.stdout.write(f"Connected to source DB '{source_db}'")
            connections[backup_db].ensure_connection()
            self.stdout.write(f"Connected to backup DB '{backup_db}'")
        except OperationalError as e:
            raise CommandError(f"Database connection error: {e}")
        except Exception as e:
            raise CommandError(f"Unexpected error checking DB connection: {e}")

        if fix_missing:
            if api_url_override:
                sdb_api_url = api_url_override.rstrip("/") + "/api/sdb/floorplan/"
            else:
                base_url = getattr(settings, "BACKUP_SERVICE_URL", None)
                if not base_url:
                    raise CommandError(
                        "BACKUP_SERVICE_URL must be configured in settings to use --fix-missing."
                    )
                sdb_api_url = base_url.rstrip("/") + "/api/sdb/floorplan/"
            self.stdout.write(
                self.style.WARNING(
                    f"Auto-fix enabled. Will POST missing records to {sdb_api_url}"
                )
            )

        # --- Fetch IDs and Timestamps ---
        self.stdout.write("Fetching data from source database...")
        source_data_qs = FloorPlanSource.objects.using(source_db).values(
            "floorplan_id", "updated_at", "pk"
        )
        if limit:
            source_data_qs = source_data_qs[:limit]
        source_data = {
            item["floorplan_id"]: {"updated_at": item["updated_at"], "pk": item["pk"]}
            for item in source_data_qs
        }
        self.stdout.write(f"Fetched {len(source_data)} records from source.")

        self.stdout.write("Fetching data from SDB backup database...")
        try:
            # Querying FloorPlan model using the backup alias
            # Important: Assumes 'sdb.models.FloorPlan' exists and mirrors the structure enough for this query
            # If not, raw SQL might be needed, or adjust the import/model definition.
            # This requires the 'sdb' app models to be available in the floorplan environment,
            # which might not be ideal. Let's query directly using the source model definition
            # but targeting the backup DB. This relies on the table name being correct
            # in the backup DB (sdb_floorplans).

            backup_data_qs = (
                FloorPlanSource.objects.using(backup_db)
                .filter(
                    floorplan_id__in=source_data.keys()  # Optimization: Only check IDs present in source
                )
                .values("floorplan_id", "updated_at")
            )

            backup_data = {
                item["floorplan_id"]: {"updated_at": item["updated_at"]}
                for item in backup_data_qs
            }
            self.stdout.write(
                f"Fetched {len(backup_data)} matching records from SDB backup."
            )

        except Exception as e:
            raise CommandError(
                f"Error querying backup DB '{backup_db}'. Does table 'sdb_floorplans' exist and match the model? Error: {e}"
            )

        # --- Compare Data ---
        missing_in_backup = []
        updated_mismatch = []

        for fp_id, source_info in source_data.items():
            if fp_id not in backup_data:
                missing_in_backup.append((fp_id, source_info["pk"]))
            elif check_updated:
                backup_info = backup_data[fp_id]
                # Compare timestamps (naive comparison, timezone might matter)
                if source_info["updated_at"] > backup_info["updated_at"]:
                    # Add a tolerance (e.g., 1 second) if needed
                    # if abs(source_info["updated_at"] - backup_info["updated_at"]).total_seconds() > 1:
                    updated_mismatch.append(
                        (
                            fp_id,
                            source_info["updated_at"],
                            backup_info["updated_at"],
                        )
                    )

        # --- Report Results ---
        self.stdout.write("\n--- Consistency Report ---")
        if not missing_in_backup and not updated_mismatch:
            self.stdout.write(
                self.style.SUCCESS("All checked records appear consistent.")
            )
        else:
            if missing_in_backup:
                self.stdout.write(
                    self.style.WARNING(
                        f"\nFound {len(missing_in_backup)} records missing in SDB Backup:"
                    )
                )
                for fp_id, source_pk in missing_in_backup[:20]:  # Show first 20
                    self.stdout.write(
                        f"  - Floorplan ID: {fp_id} (Source PK: {source_pk})"
                    )
                if len(missing_in_backup) > 20:
                    self.stdout.write(f"  ... and {len(missing_in_backup) - 20} more.")

                if fix_missing:
                    self.stdout.write(
                        self.style.WARNING("\nAttempting to fix missing records...")
                    )
                    fix_success = 0
                    fix_error = 0
                    for fp_id, source_pk in missing_in_backup:
                        try:
                            self.stdout.write(
                                f"  Syncing {fp_id} (Source PK: {source_pk})...",
                                ending="",
                            )
                            source_instance = FloorPlanSource.objects.using(
                                source_db
                            ).get(pk=source_pk)
                            payload = serialize_floorplan_for_sdb(source_instance)
                            if payload:
                                response = requests.post(
                                    sdb_api_url, json=payload, timeout=30
                                )
                                response.raise_for_status()
                                self.stdout.write(
                                    self.style.SUCCESS(
                                        f" [OK - Status: {response.status_code}]"
                                    )
                                )
                                fix_success += 1
                            else:
                                self.stdout.write(
                                    self.style.WARNING(" [Serialization Failed]")
                                )
                                fix_error += 1

                            if delay > 0:
                                time.sleep(delay)

                        except FloorPlanSource.DoesNotExist:
                            self.stdout.write(
                                self.style.ERROR(" [Source Record Vanished?]")
                            )
                            fix_error += 1
                        except RequestException as e:
                            self.stdout.write(self.style.ERROR(f" [API Error: {e}]"))
                            logger.error(f"Fix Error for {fp_id}: {e}", exc_info=True)
                            fix_error += 1
                        except Exception as e:
                            self.stdout.write(
                                self.style.ERROR(f" [Unexpected Fix Error: {e}]")
                            )
                            logger.error(
                                f"Unexpected Fix Error for {fp_id}: {e}", exc_info=True
                            )
                            fix_error += 1
                    self.stdout.write(
                        f"Fix attempts complete. Success: {fix_success}, Errors: {fix_error}"
                    )

            if updated_mismatch:
                self.stdout.write(
                    self.style.WARNING(
                        f"\nFound {len(updated_mismatch)} records with newer 'updated_at' in Source:"
                    )
                )
                for fp_id, source_ts, backup_ts in updated_mismatch[
                    :20
                ]:  # Show first 20
                    self.stdout.write(
                        f"  - Floorplan ID: {fp_id} (Source: {source_ts}, Backup: {backup_ts})"
                    )
                if len(updated_mismatch) > 20:
                    self.stdout.write(f"  ... and {len(updated_mismatch) - 20} more.")
                if not fix_missing:
                    self.stdout.write(
                        self.style.NOTICE(
                            "  (Run with --fix-missing to attempt re-sync for missing records)"
                        )
                    )

        self.stdout.write(self.style.SUCCESS("\n--- Consistency Check Complete ---"))
