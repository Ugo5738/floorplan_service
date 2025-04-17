# floorplan/management/commands/sync_all_to_sdb.py
import time

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Prefetch
from requests.exceptions import RequestException

from floorplan.models import FloorPlan  # Import source model

# Import the SDB serialization function
from floorplan.utils.backup import serialize_floorplan_for_sdb

# Assuming you have your logger configured
from floorplan_service.config.logging_config import configure_logger

logger = configure_logger(__name__)


class Command(BaseCommand):
    help = "Synchronizes all existing FloorPlan data from this service to the SDB backup service API."

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size",
            type=int,
            default=50,
            help="Number of FloorPlans to process before logging progress.",
        )
        parser.add_argument(
            "--start-pk",
            type=int,
            default=None,
            help="Optional primary key to start processing from.",
        )
        parser.add_argument(
            "--api-url",
            type=str,
            default=None,
            help="Override the SDB API URL from settings.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Simulate the process without actually sending data.",
        )
        parser.add_argument(
            "--delay",
            type=float,
            default=0.1,
            help="Delay in seconds between API calls to avoid overwhelming the SDB service.",
        )

    def handle(self, *args, **options):
        batch_size = options["batch_size"]
        start_pk = options["start_pk"]
        api_url_override = options["api_url"]
        dry_run = options["dry_run"]
        delay = options["delay"]

        if api_url_override:
            sdb_api_url = api_url_override.rstrip("/") + "/api/backup/floorplan/"
        else:
            base_url = getattr(settings, "BACKUP_SERVICE_URL", None)
            if not base_url:
                raise CommandError("BACKUP_SERVICE_URL is not configured in settings.")
            sdb_api_url = base_url.rstrip("/") + "/api/backup/floorplan/"

        self.stdout.write(
            self.style.SUCCESS(
                f"--- Starting Initial FloorPlan Sync to SDB ({sdb_api_url}) ---"
            )
        )
        if dry_run:
            self.stdout.write(
                self.style.WARNING("DRY RUN enabled. No data will be sent.")
            )

        # Queryset optimization: Prefetch related data needed for serialization
        queryset = (
            FloorPlan.objects.all()
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
            .order_by("pk")
        )  # Order for predictable processing

        if start_pk:
            queryset = queryset.filter(pk__gte=start_pk)
            self.stdout.write(f"Starting processing from PK >= {start_pk}")

        total_count = queryset.count()
        self.stdout.write(f"Found {total_count} FloorPlan records to process.")

        processed_count = 0
        success_count = 0
        error_count = 0

        for floorplan in queryset.iterator():
            processed_count += 1
            self.stdout.write(
                f"Processing FloorPlan PK={floorplan.pk}, ID={floorplan.floorplan_id} ({processed_count}/{total_count})...",
                ending="",
            )

            try:
                payload = serialize_floorplan_for_sdb(floorplan)
                if payload is None:
                    self.stdout.write(
                        self.style.WARNING(
                            " Serialization failed (see logs). Skipping."
                        )
                    )
                    error_count += 1
                    continue

                if dry_run:
                    # Simulate success in dry run if serialization worked
                    self.stdout.write(self.style.SUCCESS(" [DRY RUN - OK]"))
                    success_count += 1
                else:
                    # Make the actual API call
                    try:
                        response = requests.post(sdb_api_url, json=payload, timeout=30)
                        response.raise_for_status()  # Check for HTTP errors

                        self.stdout.write(
                            self.style.SUCCESS(
                                f" [OK - Status: {response.status_code}]"
                            )
                        )
                        success_count += 1

                    except RequestException as e:
                        self.stdout.write(self.style.ERROR(f" [Error: {e}]"))
                        logger.error(
                            f"Failed to sync FloorPlan PK={floorplan.pk}: {e}",
                            exc_info=True,
                        )
                        # Log response details if available
                        if hasattr(e, "response") and e.response is not None:
                            logger.error(f"Response status: {e.response.status_code}")
                            logger.error(
                                f"Response text: {e.response.text[:500]}"
                            )  # Log snippet
                        error_count += 1
                    # Optional delay
                    if delay > 0:
                        time.sleep(delay)

            except Exception as e:
                # Catch unexpected errors during serialization or loop logic
                self.stdout.write(self.style.ERROR(f" [Unexpected Error: {e}]"))
                logger.exception(
                    f"Unexpected error processing FloorPlan PK={floorplan.pk}: {e}"
                )
                error_count += 1

            if processed_count % batch_size == 0:
                self.stdout.write(
                    f"\nProcessed {processed_count}/{total_count}. Success: {success_count}, Errors: {error_count}\n"
                )

        self.stdout.write(self.style.SUCCESS(f"\n--- Sync Complete ---"))
        self.stdout.write(f"Total Processed: {processed_count}")
        self.stdout.write(self.style.SUCCESS(f"Successful Syncs: {success_count}"))
        self.stdout.write(self.style.ERROR(f"Errors: {error_count}"))

        if error_count > 0:
            self.stdout.write(self.style.WARNING("Check logs for details on errors."))
