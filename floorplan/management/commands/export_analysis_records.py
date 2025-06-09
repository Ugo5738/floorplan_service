# floorplan/management/commands/export_fp_analysis_records.py

import csv
import sys

from django.core.management.base import BaseCommand, CommandError

# --- Updated Import ---
# Import models from the 'floorplan' app
from floorplan.models import AllFloorsData, FloorPlan, FloorPlanAnalysisResult

# --- End Updated Import ---


class Command(BaseCommand):
    # Help text can remain similar, focusing on the action
    help = (
        "Exports floor plan analysis records (user_id, property_id, original_url, floorplan_data_url) "
        "from the 'floorplan' app models for a specific user ID to a CSV file."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "output_file",
            nargs="?",
            type=str,
            help="Optional path to the output CSV file. If not provided, output will be written to stdout.",
            default=None,
        )
        # Keep the user_id argument for flexibility
        parser.add_argument(
            "--user_id",
            type=str,
            # You might want to remove the default here if you always want to specify it
            # Or keep it if 'FloorplanTest290425' is still the most common use case
            default="FloorplanTest290425",
            help="Filter records for a specific user ID.",
        )

    def handle(self, *args, **options):
        output_file = options["output_file"]
        specific_user_id = options["user_id"]  # Get user_id from argument

        output_stream = (
            open(output_file, "w", newline="", encoding="utf-8")
            if output_file
            else sys.stdout
        )

        self.stdout.write(
            f"Exporting 'floorplan' app analysis records for user_id: {specific_user_id}..."  # Added 'floorplan' app context
        )
        if output_file:
            self.stdout.write(f"Output file: {output_file}")
        else:
            self.stdout.write(f"Outputting to stdout")

        # Prepare CSV writer - fieldnames are the same
        fieldnames = ["user_id", "property_id", "original_url", "floorplan_data_url"]
        writer = csv.DictWriter(output_stream, fieldnames=fieldnames)
        writer.writeheader()

        count = 0
        processed_count = 0

        # --- Query Modification ---
        # Query FloorPlan from floorplan.models
        # Filter based on the user_id in the related FloorPlanAnalysisResult
        floor_plans_query = (
            FloorPlan.objects.filter(analysis_result__user_id=specific_user_id)
            .select_related(
                "analysis_result",  # Gets FloorPlanAnalysisResult
                # --- Updated Related Name ---
                # Use the related_name defined in floorplan.models.AllFloorsData ('all_floors_data')
                # This refers to the reverse relationship from FloorPlan to AllFloorsData
                "all_floors_data",
                # --- End Updated Related Name ---
            )
            .order_by("created_at")
        )
        # --- End Query Modification ---

        total_plans = floor_plans_query.count()
        self.stdout.write(
            f"Found {total_plans} 'floorplan' app records for user '{specific_user_id}' to process."  # Added context
        )

        if total_plans == 0:
            self.stdout.write(
                self.style.WARNING(
                    f"No 'floorplan' app records found for user '{specific_user_id}'. Exiting."  # Added context
                )
            )
            if output_file:
                output_stream.close()
            return

        for floor_plan in floor_plans_query.iterator():
            processed_count += 1
            if processed_count % 100 == 0:
                self.stdout.write(
                    f"Processed {processed_count}/{total_plans} records..."
                )

            try:
                analysis_result = floor_plan.analysis_result
                user_id = analysis_result.user_id
                property_id = analysis_result.property_id
                original_url = floor_plan.original_url

                floorplan_data_url = ""

                try:
                    # --- Updated Attribute Access ---
                    # Access the related AllFloorsData using the correct related_name from the model definition
                    all_floors_data = floor_plan.all_floors_data
                    # --- End Updated Attribute Access ---
                    if all_floors_data.csv_url:
                        floorplan_data_url = all_floors_data.csv_url
                    elif all_floors_data.json_file_url:
                        floorplan_data_url = all_floors_data.json_file_url

                except AllFloorsData.DoesNotExist:
                    # This is expected if analysis didn't generate AllFloorsData yet
                    pass
                except AttributeError:
                    # This might happen if the select_related failed or the relation is somehow broken
                    self.stderr.write(
                        self.style.WARNING(
                            # Use the correct attribute name in the warning
                            f"Could not access all_floors_data for FloorPlan ID {floor_plan.id}"
                        )
                    )

                # Double check user_id (optional paranoia)
                if user_id != specific_user_id:
                    self.stderr.write(
                        self.style.WARNING(
                            f"Record {floor_plan.id} has unexpected user_id '{user_id}'. Skipping write (should not happen due to filter)."
                        )
                    )
                    continue

                writer.writerow(
                    {
                        "user_id": user_id,
                        "property_id": property_id,
                        "original_url": original_url,
                        "floorplan_data_url": floorplan_data_url,
                    }
                )
                count += 1

            except FloorPlanAnalysisResult.DoesNotExist:
                self.stderr.write(
                    self.style.WARNING(
                        f"Skipping FloorPlan ID {floor_plan.id} due to missing FloorPlanAnalysisResult (unexpected)."
                    )
                )
            except Exception as e:
                self.stderr.write(
                    self.style.ERROR(
                        f"Error processing FloorPlan ID {floor_plan.id}: {e}"
                    )
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully exported {count} 'floorplan' app analysis records for user '{specific_user_id}'."  # Added context
            )
        )

        if output_file:
            output_stream.close()
            self.stdout.write(self.style.SUCCESS(f"Output saved to {output_file}"))
