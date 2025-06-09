# floorplan/management/commands/export_floorplan_data.py

import csv
import os
import traceback

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Prefetch
from django.utils import timezone  # Import timezone for formatting

from floorplan.models import (
    AllFloorsCsvData,  # Using this for CSV 2 is much more efficient
)
from floorplan.models import (
    AllFloorsData,
    FloorPlan,
    FloorPlanAnalysisResult,
    TotalAreasCsvData,
)


class Command(BaseCommand):
    help = "Exports floorplan data into three separate CSV files, including analysis creation time."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output-dir",
            type=str,
            default=".",  # Default to current directory
            help="Directory where the CSV files will be saved.",
        )

    def handle(self, *args, **options):
        output_dir = options["output_dir"]
        os.makedirs(output_dir, exist_ok=True)  # Ensure directory exists

        csv1_path = os.path.join(output_dir, "floorplan_summary_export.csv")
        csv2_path = os.path.join(output_dir, "floorplan_room_details_export.csv")
        csv3_path = os.path.join(output_dir, "floorplan_total_area_export.csv")

        self.stdout.write(f"Starting export to directory: {output_dir}")

        try:
            self._export_csv1(csv1_path)
            self._export_csv2(csv2_path)
            self._export_csv3(csv3_path)
            self.stdout.write(self.style.SUCCESS("Successfully exported all data."))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"An error occurred during export: {e}"))
            traceback.print_exc()  # Print traceback for debugging
            raise CommandError(f"Export failed. See traceback above for details.")

    def _get_safe_value(self, obj, attribute_path, default=""):
        """Safely retrieves nested attributes, returning default if any part is None."""
        value = obj
        try:
            for attr in attribute_path.split("."):
                if value is None:
                    return default
                value = getattr(value, attr)
            return value if value is not None else default
        except AttributeError:
            return default

    def _format_datetime(self, dt_obj, default=""):
        """Formats a datetime object to ISO 8601 string, handling None."""
        if dt_obj and hasattr(dt_obj, "isoformat"):
            # Optional: Convert to local timezone if desired, otherwise uses stored timezone (likely UTC)
            # return timezone.localtime(dt_obj).isoformat()
            return dt_obj.isoformat()
        return default

    # === CSV 1 Export Logic ===
    def _export_csv1(self, filepath):
        self.stdout.write(f"Exporting CSV 1: Summary Data to {filepath}...")
        headers = [
            "property_id",
            "user_id",
            "floorplan_id",
            "original_url",
            "json_file_url",
            "csv_url",
            "total_area_csv_url",
            "image_labelme_side_by_side_url",
            "created_at",  # Changed header name
        ]

        queryset = AllFloorsData.objects.select_related(
            "floor_plan__analysis_result"
        ).all()

        with open(filepath, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(headers)

            count = 0
            for afd in queryset.iterator():
                fp = self._get_safe_value(afd, "floor_plan")
                analysis = self._get_safe_value(fp, "analysis_result")
                analysis_time = self._get_safe_value(analysis, "created_at")

                writer.writerow(
                    [
                        self._get_safe_value(analysis, "property_id"),
                        self._get_safe_value(analysis, "user_id"),
                        self._get_safe_value(fp, "floorplan_id"),
                        self._get_safe_value(fp, "original_url"),
                        self._get_safe_value(afd, "json_file_url"),
                        self._get_safe_value(afd, "csv_url"),
                        self._get_safe_value(afd, "total_area_csv_url"),
                        self._get_safe_value(afd, "image_labelme_side_by_side_url"),
                        self._format_datetime(
                            analysis_time
                        ),  # Data source remains the same
                    ]
                )
                count += 1
                if count % 1000 == 0:
                    self.stdout.write(f"  ..processed {count} rows for CSV 1")

        self.stdout.write(self.style.SUCCESS(f"Finished CSV 1: Exported {count} rows."))

    # === CSV 2 Export Logic ===
    def _export_csv2(self, filepath):
        self.stdout.write(f"Exporting CSV 2: Room Detail Data to {filepath}...")
        headers = [
            "property_id",
            "user_id",
            "floorplan_id",
            "floor_name",
            "room_name",
            "is_segment",
            "dimensions_imperial",
            "dimensions_metric",
            "room_id",
            "no_of_door",
            "no_of_window",
            "no_of_room_points",
            "min_x_pixels",
            "min_y_pixels",
            "max_x_pixels",
            "max_y_pixels",
            "max_area_metric",
            "max_area_imperial",
            "max_area_pixels",
            "actual_area_pixels",
            "pixel_ratio",
            "scale_metric",
            "scale_imperial",
            "calculated_sq_area_metric",
            "calculated_area_imperial",
            "created_at",  # Changed header name
        ]

        queryset = AllFloorsCsvData.objects.select_related(
            "all_floors_data__floor_plan__analysis_result"
        ).all()

        with open(filepath, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(headers)

            count = 0
            for row in queryset.iterator():
                afd = self._get_safe_value(row, "all_floors_data")
                fp = self._get_safe_value(afd, "floor_plan")
                analysis = self._get_safe_value(fp, "analysis_result")
                analysis_time = self._get_safe_value(analysis, "created_at")

                writer.writerow(
                    [
                        self._get_safe_value(analysis, "property_id"),
                        self._get_safe_value(analysis, "user_id"),
                        self._get_safe_value(fp, "floorplan_id"),
                        self._get_safe_value(row, "floor_name"),
                        self._get_safe_value(row, "room_name"),
                        self._get_safe_value(row, "is_segment"),
                        self._get_safe_value(row, "dimensions_imperial"),
                        self._get_safe_value(row, "dimensions_metric"),
                        self._get_safe_value(row, "room_id"),
                        self._get_safe_value(row, "no_of_door"),
                        self._get_safe_value(row, "no_of_window"),
                        self._get_safe_value(row, "no_of_room_points"),
                        self._get_safe_value(row, "min_x_pixels"),
                        self._get_safe_value(row, "min_y_pixels"),
                        self._get_safe_value(row, "max_x_pixels"),
                        self._get_safe_value(row, "max_y_pixels"),
                        self._get_safe_value(row, "max_area_metric"),
                        self._get_safe_value(row, "max_area_imperial"),
                        self._get_safe_value(row, "max_area_pixels"),
                        self._get_safe_value(row, "actual_area_pixels"),
                        self._get_safe_value(row, "pixel_ratio"),
                        self._get_safe_value(row, "scale_metric"),
                        self._get_safe_value(row, "scale_imperial"),
                        self._get_safe_value(row, "calculated_sq_area_metric"),
                        self._get_safe_value(row, "calculated_area_imperial"),
                        self._format_datetime(
                            analysis_time
                        ),  # Data source remains the same
                    ]
                )
                count += 1
                if count % 5000 == 0:
                    self.stdout.write(f"  ..processed {count} rows for CSV 2")

        self.stdout.write(self.style.SUCCESS(f"Finished CSV 2: Exported {count} rows."))

    # === CSV 3 Export Logic ===
    def _export_csv3(self, filepath):
        self.stdout.write(f"Exporting CSV 3: Total Area Data to {filepath}...")
        headers = [
            "property_id",
            "user_id",
            "floorplan_id",
            "area_name",
            "square_meters",
            "square_feet",
            "total_floors",
            "total_named_rooms",
            "total_segments",
            "total_points",
            "total_objects",
            "total_door_objects",
            "total_window_objects",
            "total_stair_objects",
            "list_of_objects",
            "total_actual_pixels",
            "metric_scale",
            "imperial_scale",
            "input_image_tokens",
            "input_text_tokens",
            "output_text_tokens",
            "created_at",  # Changed header name
        ]

        queryset = TotalAreasCsvData.objects.select_related(
            "all_floors_data__floor_plan__analysis_result"
        ).all()

        with open(filepath, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(headers)

            count = 0
            for tad in queryset.iterator():
                afd = self._get_safe_value(tad, "all_floors_data")
                fp = self._get_safe_value(afd, "floor_plan")
                analysis = self._get_safe_value(fp, "analysis_result")
                analysis_time = self._get_safe_value(analysis, "created_at")

                writer.writerow(
                    [
                        self._get_safe_value(analysis, "property_id"),
                        self._get_safe_value(analysis, "user_id"),
                        self._get_safe_value(fp, "floorplan_id"),
                        self._get_safe_value(tad, "area_name"),
                        self._get_safe_value(tad, "square_meters"),
                        self._get_safe_value(tad, "square_feet"),
                        self._get_safe_value(tad, "total_floors"),
                        self._get_safe_value(tad, "total_named_rooms"),
                        self._get_safe_value(tad, "total_segments"),
                        self._get_safe_value(tad, "total_points"),
                        self._get_safe_value(tad, "total_objects"),
                        self._get_safe_value(tad, "total_door_objects"),
                        self._get_safe_value(tad, "total_window_objects"),
                        self._get_safe_value(tad, "total_stair_objects"),
                        self._get_safe_value(tad, "list_of_objects"),
                        self._get_safe_value(tad, "total_actual_pixels"),
                        self._get_safe_value(tad, "metric_scale"),
                        self._get_safe_value(tad, "imperial_scale"),
                        self._get_safe_value(tad, "input_image_tokens"),
                        self._get_safe_value(tad, "input_text_tokens"),
                        self._get_safe_value(tad, "output_text_tokens"),
                        self._format_datetime(
                            analysis_time
                        ),  # Data source remains the same
                    ]
                )
                count += 1
                if count % 1000 == 0:
                    self.stdout.write(f"  ..processed {count} rows for CSV 3")

        self.stdout.write(self.style.SUCCESS(f"Finished CSV 3: Exported {count} rows."))
