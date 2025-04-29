# floorplan/management/commands/sync_total_areas.py

import csv
import io
import logging
import time

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone  # Use timezone for comparisons if needed

# Import necessary models
from floorplan.models import (
    AllFloorsData,
    FloorPlan,
    FloorPlanAnalysisResult,
    TotalAreasCsvData,
)

# Import necessary helpers (assuming they are defined in tasks.py or a utils file)
# If not, copy their definitions into this file or a shared utils file.
from floorplan.tasks import (
    _process_total_area_csv,  # Assuming this function is defined in tasks.py
)
from floorplan.tasks import (  # Add safe_float, safe_int, safe_string if _process_total_area_csv needs them directly; and they aren't imported within it.
    _download_csv_content,
)

logger = logging.getLogger(__name__)  # Use Django's logging

# --- User ID Mapping ---
# Map from the ID stored in *your database* back to the ID the *API expects*
DB_TO_API_USER_ID_MAP = {
    "8": "447841869529",
    "2": "2347033588400",
}


class Command(BaseCommand):
    help = "Fetches the latest total_area_csv_url from the API for floorplans and updates the corresponding TotalAreasCsvData."

    def add_arguments(self, parser):
        parser.add_argument(
            "--api-url",
            default=getattr(
                settings, "FLOORPLAN_API_BASE_URL", "http://165.232.101.36"
            ),
            help="Base URL of the floorplan API.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Limit the number of FloorPlan records to process.",
        )
        parser.add_argument(
            "--delay",
            type=float,
            default=0.1,
            help="Delay in seconds between API calls.",
        )
        parser.add_argument(
            "--force-update",
            action="store_true",
            help="Force processing of the CSV even if the URL hasn't changed.",
        )
        parser.add_argument(
            "--floorplan-pk",
            type=int,
            default=None,
            help="Process only a specific FloorPlan primary key.",
        )

    def handle(self, *args, **options):
        api_base_url = options["api_url"]
        limit = options["limit"]
        delay = options["delay"]
        force_update = options["force_update"]
        specific_pk = options["floorplan_pk"]

        if not api_base_url:
            raise CommandError(
                "API Base URL is not configured. Use --api-url or set FLOORPLAN_API_BASE_URL in settings."
            )

        api_endpoint = f"{api_base_url.rstrip('/')}/get-floorplan-data-by-user-property"

        self.stdout.write(self.style.SUCCESS(f"--- Starting Total Area CSV Sync ---"))
        self.stdout.write(f"Using API endpoint: {api_endpoint}")
        if limit:
            self.stdout.write(f"Limiting processing to {limit} records.")
        if specific_pk:
            self.stdout.write(f"Processing only FloorPlan PK: {specific_pk}")
        if force_update:
            self.stdout.write(
                self.style.WARNING(
                    "Force update enabled: CSV will be processed even if URL is unchanged."
                )
            )

        # --- Query Preparation ---
        floorplan_queryset = FloorPlan.objects.select_related(
            "analysis_result", "all_floors_data"
        )

        if specific_pk:
            floorplan_queryset = floorplan_queryset.filter(pk=specific_pk)
            if not floorplan_queryset.exists():
                raise CommandError(f"FloorPlan with PK {specific_pk} not found.")
        elif limit:
            floorplan_queryset = floorplan_queryset[:limit]

        # --- Stats Counters ---
        processed_count = 0
        updated_count = 0
        skipped_no_afd = 0
        skipped_no_analysis = 0
        api_errors = 0
        api_errors_fallback = 0
        url_missing_errors = 0
        processing_errors = 0
        fallback_attempts = 0
        fallback_success = 0

        # --- Main Loop ---
        start_time = time.time()
        # Use iterator for memory efficiency
        for floorplan in floorplan_queryset.iterator():
            processed_count += 1
            if processed_count % 50 == 0:
                elapsed = time.time() - start_time
                self.stdout.write(
                    f"  Processed {processed_count} floorplans... ({elapsed:.2f}s elapsed)"
                )

            # --- Basic Checks ---
            if not floorplan.analysis_result:
                self.stdout.write(
                    self.style.WARNING(
                        f"Skipping FloorPlan PK {floorplan.pk} (Hash: {floorplan.floorplan_id[:8]}...) - Missing Analysis Result"
                    )
                )
                skipped_no_analysis += 1
                continue

            if (
                not hasattr(floorplan, "all_floors_data")
                or floorplan.all_floors_data is None
            ):
                logger.debug(
                    f"Skipping FloorPlan PK {floorplan.pk} (Hash: {floorplan.floorplan_id[:8]}...) - No AllFloorsData linked"
                )
                skipped_no_afd += 1
                continue

            db_user_id = floorplan.analysis_result.user_id
            property_id = floorplan.analysis_result.property_id

            if not db_user_id or not property_id:
                self.stdout.write(
                    self.style.WARNING(
                        f"Skipping FloorPlan PK {floorplan.pk} - Missing user_id or property_id in AnalysisResult PK {floorplan.analysis_result.pk}"
                    )
                )
                skipped_no_analysis += 1
                continue

            # --- API Call with Fallback Logic ---
            api_data = None
            api_error_occurred = False
            current_api_error_count = api_errors  # Store current count before attempts

            # 1. Try with the DB User ID first
            self.stdout.write(
                f"Attempting API call for DB User ID: {db_user_id}, Prop ID: {property_id} (FP PK: {floorplan.pk})"
            )
            try:
                response = requests.get(
                    api_endpoint,
                    params={"user_id": db_user_id, "property_id": property_id},
                    timeout=45,
                )
                # Check for specific non-success codes that might warrant a fallback
                # A 404 is a good candidate. Maybe 5xx errors too?
                if response.status_code == 404:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  API returned 404 for DB User ID {db_user_id}. Checking for fallback..."
                        )
                    )
                    api_error_occurred = True  # Mark error to trigger fallback check
                elif not response.ok:  # Handle other non-2xx errors
                    response.raise_for_status()  # Raise HTTPError for other bad statuses
                else:
                    api_data = response.json()  # Success!
                    self.stdout.write(
                        f"  API call successful for DB User ID {db_user_id}."
                    )

            except requests.Timeout:
                logger.error(
                    f"Timeout calling API for FloorPlan PK {floorplan.pk} (DB User: {db_user_id}, Prop: {property_id})"
                )
                api_errors += 1
                api_error_occurred = True
            except requests.RequestException as e:
                status_code = getattr(e.response, "status_code", "N/A")
                response_text = getattr(e.response, "text", "N/A")[:200]
                logger.error(
                    f"API Request Error for FloorPlan PK {floorplan.pk} (DB User: {db_user_id}, Prop: {property_id}): {e} (Status: {status_code}) Response: {response_text}"
                )
                api_errors += 1
                api_error_occurred = (
                    True  # Mark error to trigger fallback if applicable
                )

            # 2. Try Fallback if needed and possible
            api_user_id = DB_TO_API_USER_ID_MAP.get(db_user_id)
            if api_error_occurred and api_user_id:
                self.stdout.write(
                    self.style.NOTICE(
                        f"  Attempting fallback API call for API User ID: {api_user_id}, Prop ID: {property_id}"
                    )
                )
                fallback_attempts += 1
                try:
                    response = requests.get(
                        api_endpoint,
                        params={"user_id": api_user_id, "property_id": property_id},
                        timeout=45,
                    )
                    response.raise_for_status()  # Raises error for non-2xx status codes
                    api_data = response.json()  # Success on fallback!
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"  Fallback API call successful for API User ID {api_user_id}."
                        )
                    )
                    fallback_success += 1
                    # Reset api_error_occurred as fallback succeeded
                    api_error_occurred = False
                    # If the *first* call failed but this one worked, don't increment the overall api_errors count
                    if api_errors > current_api_error_count:
                        api_errors = current_api_error_count  # Correct the count
                        api_errors_fallback += (
                            1  # Keep track of errors that needed fallback
                        )

                except requests.Timeout:
                    logger.error(
                        f"Timeout on fallback API call for FloorPlan PK {floorplan.pk} (API User: {api_user_id}, Prop: {property_id})"
                    )
                    api_errors_fallback += 1  # Track fallback specific errors
                    # Keep api_error_occurred = True
                except requests.RequestException as e:
                    status_code = getattr(e.response, "status_code", "N/A")
                    response_text = getattr(e.response, "text", "N/A")[:200]
                    logger.error(
                        f"Fallback API Request Error for FloorPlan PK {floorplan.pk} (API User: {api_user_id}, Prop: {property_id}): {e} (Status: {status_code}) Response: {response_text}"
                    )
                    api_errors_fallback += 1  # Track fallback specific errors
                    # Keep api_error_occurred = True

            # If api_data is still None after potential fallback, skip this floorplan
            if api_data is None:
                self.stdout.write(
                    self.style.ERROR(
                        f"  Skipping FloorPlan PK {floorplan.pk} after failed API attempts."
                    )
                )
                continue  # Move to the next floorplan

            # --- Process Successful API Response ---
            total_area_url = None
            try:
                # --- Safely Extract URL ---
                output_data = api_data.get("output_data")
                if isinstance(output_data, list) and len(output_data) > 0:
                    first_output_item = output_data[0]
                    if isinstance(first_output_item, dict):
                        # Prefer matching floorplan_id if possible
                        response_fp_id = first_output_item.get("floorplan_id")
                        if response_fp_id == floorplan.floorplan_id:
                            all_floors_dict = first_output_item.get("all_floors")
                            if isinstance(all_floors_dict, dict):
                                total_area_url = all_floors_dict.get(
                                    "total_area_csv_url"
                                )
                        else:
                            logger.warning(
                                f"API response floorplan_id ({response_fp_id}) "
                                f"does not match current FloorPlan ({floorplan.floorplan_id}) "
                                f"for User: {db_user_id}, Prop: {property_id}. Using URL from first item anyway."
                            )
                            all_floors_dict = first_output_item.get("all_floors")
                            if isinstance(all_floors_dict, dict):
                                total_area_url = all_floors_dict.get(
                                    "total_area_csv_url"
                                )

                if not total_area_url:
                    self.stdout.write(
                        self.style.WARNING(
                            f"No 'total_area_csv_url' found in API response for FloorPlan PK {floorplan.pk} (User: {db_user_id}, Prop: {property_id})"
                        )
                    )
                    url_missing_errors += 1
                    continue  # Skip to next floorplan

                self.stdout.write(f"  Found total_area_csv_url: {total_area_url}")

                # --- Update AllFloorsData URL and Process CSV ---
                all_floors_data_instance = floorplan.all_floors_data

                needs_update = (
                    all_floors_data_instance.total_area_csv_url != total_area_url
                )

                if needs_update:
                    self.stdout.write(
                        f"  Updating total_area_csv_url for AllFloorsData PK {all_floors_data_instance.pk}"
                    )
                    all_floors_data_instance.total_area_csv_url = total_area_url
                    try:
                        with transaction.atomic():
                            all_floors_data_instance.save(
                                update_fields=["total_area_csv_url", "updated_at"]
                            )
                    except Exception as save_exc:
                        logger.error(
                            f"Failed to save updated URL for AllFloorsData PK {all_floors_data_instance.pk}: {save_exc}"
                        )
                        processing_errors += 1
                        continue  # Skip CSV processing if save failed

                # Process CSV if URL updated OR if force_update is True
                if needs_update or force_update:
                    self.stdout.write(
                        f"  Processing CSV for FloorPlan PK {floorplan.pk}..."
                    )
                    try:
                        # _process_total_area_csv handles its own transaction
                        _process_total_area_csv(all_floors_data_instance)
                        updated_count += 1
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"    Successfully processed total area CSV."
                            )
                        )
                    except Exception as proc_exc:
                        logger.exception(
                            f"Error processing total area CSV for AFD PK {all_floors_data_instance.pk} (FP PK {floorplan.pk}): {proc_exc}"
                        )
                        processing_errors += 1
                else:
                    self.stdout.write(
                        f"  Skipping CSV processing for FP PK {floorplan.pk} (URL unchanged and --force-update not set)."
                    )

            except Exception as e:
                logger.exception(
                    f"Unexpected error processing API data or CSV for FloorPlan PK {floorplan.pk}: {e}"
                )
                processing_errors += 1  # Count as processing error

            # Optional delay
            if delay > 0:
                time.sleep(delay)

        # --- End of Loop ---

        # --- Final Summary ---
        end_time = time.time()
        duration = end_time - start_time
        self.stdout.write(self.style.SUCCESS("\n--- Sync Complete ---"))
        self.stdout.write(f"Duration: {duration:.2f} seconds")
        self.stdout.write(f"FloorPlans Checked: {processed_count}")
        self.stdout.write(f"CSVs Updated/Processed: {updated_count}")
        self.stdout.write(f"Skipped (No AnalysisResult/ID): {skipped_no_analysis}")
        self.stdout.write(f"Skipped (No AllFloorsData): {skipped_no_afd}")
        self.stdout.write(f"API URL Missing in Response: {url_missing_errors}")
        self.stdout.write(
            self.style.WARNING(
                f"Initial API Errors (incl. 404s): {api_errors + api_errors_fallback}"
            )
        )  # Total errors encountered before potential fallback success
        self.stdout.write(
            self.style.WARNING(f"Fallback API Attempts: {fallback_attempts}")
        )
        self.stdout.write(
            self.style.WARNING(f"Fallback API Successes: {fallback_success}")
        )
        self.stdout.write(
            self.style.WARNING(f"Fallback API Errors: {api_errors_fallback}")
        )  # Errors specifically on the fallback call
        self.stdout.write(
            self.style.ERROR(f"CSV Processing Errors: {processing_errors}")
        )
        if (
            processing_errors > 0
            or (api_errors + api_errors_fallback) > fallback_success
        ):
            self.stderr.write(
                self.style.ERROR("Errors occurred. Please check the logs.")
            )
