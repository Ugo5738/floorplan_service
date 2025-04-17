# floorplan/management/commands/deduplicate_floorplans.py

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Count, F, Max

from floorplan.models import FloorPlan, FloorPlanAnalysisResult


class Command(BaseCommand):
    help = (
        "Identifies and deletes older duplicate FloorPlan records for the same "
        "FloorPlanAnalysisResult (user_id, property_id pair), keeping only the most recent one."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Identify duplicates and what would be deleted, but don't actually delete anything.",
        )
        parser.add_argument(
            "--keep-field",
            type=str,
            default="updated_at",
            choices=[
                "updated_at",
                "created_at",
                "pk",
            ],  # pk uses highest primary key as "most recent"
            help="Field to use to determine the 'most recent' FloorPlan record to keep ('updated_at', 'created_at', or 'pk').",
        )

    @transaction.atomic  # Wrap the whole process in a transaction
    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        keep_field = options["keep_field"]

        self.stdout.write(
            self.style.SUCCESS(
                f"--- Starting FloorPlan Deduplication (Keep based on most recent '{keep_field}') ---"
            )
        )
        if dry_run:
            self.stdout.write(
                self.style.WARNING("DRY RUN enabled. No records will be deleted.")
            )

        # 1. Find FloorPlanAnalysisResult IDs with more than one FloorPlan
        analysis_results_with_duplicates = (
            FloorPlanAnalysisResult.objects.annotate(
                floorplan_count=Count(
                    "floor_plans"
                )  # Use the related_name from FloorPlan.analysis_result
            )
            .filter(floorplan_count__gt=1)
            .values_list("id", flat=True)
        )

        duplicate_analysis_ids = list(analysis_results_with_duplicates)
        total_analysis_duplicates = len(duplicate_analysis_ids)

        if not total_analysis_duplicates:
            self.stdout.write(
                self.style.SUCCESS(
                    "No duplicate FloorPlans found based on Analysis Results."
                )
            )
            return

        self.stdout.write(
            f"Found {total_analysis_duplicates} Analysis Results with multiple FloorPlans."
        )

        total_deleted_count = 0
        processed_analysis_count = 0

        # 2. Iterate through each analysis result with duplicates
        for analysis_id in duplicate_analysis_ids:
            processed_analysis_count += 1
            if processed_analysis_count % 50 == 0:
                self.stdout.write(
                    f"  Processed {processed_analysis_count}/{total_analysis_duplicates} analysis results..."
                )

            # Get all floorplans for this analysis result
            floorplans_for_analysis = FloorPlan.objects.filter(
                analysis_result_id=analysis_id
            )

            # 3. Determine the most recent FloorPlan to keep
            try:
                # Use Max aggregation on the chosen field to find the "latest" value
                latest_value_data = floorplans_for_analysis.aggregate(
                    latest_value=Max(keep_field)
                )
                latest_value = latest_value_data.get("latest_value")

                if latest_value is None:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  Could not determine latest value for AnalysisResult ID {analysis_id}. Skipping."
                        )
                    )
                    continue

                # Find the specific FloorPlan(s) that match the latest value.
                # It's possible (though less likely with timestamps) multiple have the exact same latest value.
                # In that case, we arbitrarily keep the one with the highest PK among those tied.
                floorplans_to_keep_qs = floorplans_for_analysis.filter(
                    **{keep_field: latest_value}  # Filter by the latest value found
                ).order_by(
                    "-pk"
                )  # Order by PK descending

                if not floorplans_to_keep_qs.exists():
                    self.stdout.write(
                        self.style.ERROR(
                            f"  Logic error: Could not find FloorPlan to keep for AnalysisResult ID {analysis_id} with latest value {latest_value}. Skipping."
                        )
                    )
                    continue

                floorplan_to_keep = (
                    floorplans_to_keep_qs.first()
                )  # Get the one with the highest PK among those with the latest value

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f"  Error determining FloorPlan to keep for AnalysisResult ID {analysis_id}: {e}. Skipping."
                    )
                )
                continue

            # 4. Identify FloorPlans to delete (all except the one to keep)
            floorplans_to_delete = floorplans_for_analysis.exclude(
                pk=floorplan_to_keep.pk
            )
            delete_pks = list(floorplans_to_delete.values_list("pk", flat=True))
            delete_count = len(delete_pks)

            if delete_count > 0:
                self.stdout.write(
                    f"  AnalysisResult ID {analysis_id}: Keeping FloorPlan PK {floorplan_to_keep.pk} (based on '{keep_field}'), planning to delete {delete_count} older records (PKs: {delete_pks})."
                )

                if not dry_run:
                    try:
                        deleted_count_actual, deleted_details = (
                            floorplans_to_delete.delete()
                        )
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"    Successfully deleted {deleted_count_actual} records."
                            )
                        )
                        # logger.debug(f"Deletion details for AnalysisResult {analysis_id}: {deleted_details}") # Optional more detail
                        total_deleted_count += deleted_count_actual
                    except Exception as e:
                        self.stdout.write(
                            self.style.ERROR(
                                f"    Error deleting records for AnalysisResult ID {analysis_id}: {e}"
                            )
                        )
                        # Since we're in a transaction, this will cause a rollback unless caught differently
                        raise CommandError(
                            f"Failed during deletion for AnalysisResult ID {analysis_id}"
                        )  # Stop execution on error

            else:
                self.stdout.write(
                    f"  AnalysisResult ID {analysis_id}: No older records to delete."
                )

        self.stdout.write(self.style.SUCCESS("\n--- Deduplication Complete ---"))
        if dry_run:
            self.stdout.write(
                self.style.WARNING("DRY RUN completed. No records were deleted.")
            )
            # You might want to report the *potential* delete count here if needed
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Total older duplicate FloorPlan records deleted: {total_deleted_count}"
                )
            )
