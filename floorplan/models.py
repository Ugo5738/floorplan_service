import hashlib

from django.db import models
from simple_history.models import HistoricalRecords

from floorplan_service.config.logging_config import configure_logger
from helpers.models import TrackingModel

logger = configure_logger(__name__)

# === API-Level Models ===


class FloorPlanAnalysisResult(TrackingModel):
    message = models.CharField(max_length=255)
    user_id = models.CharField(max_length=255)
    property_id = models.CharField(max_length=255)

    history = HistoricalRecords()

    class Meta:
        unique_together = ("user_id", "property_id")

    def __str__(self):
        return f"{self.user_id} - {self.property_id}"


class FloorPlan(TrackingModel):
    analysis_result = models.ForeignKey(
        FloorPlanAnalysisResult, related_name="floor_plans", on_delete=models.CASCADE
    )
    # Change CharField max_length to 64 for SHA256 hex digest and add unique=True
    floorplan_id = models.CharField(
        max_length=64,
        db_index=True,  # unique=True,
    )  # Ensures DB-level uniqueness and speeds up lookups
    original_url = models.URLField(
        max_length=1024
    )  # Increase max_length for potentially long URLs
    update_count = models.PositiveIntegerField(
        default=0, help_text="Number of times webhook processing updated this record."
    )
    history = HistoricalRecords()

    def __str__(self):
        # Show first 8 chars of hash for brevity in admin dropdowns etc.
        short_hash = self.floorplan_id[:8] if self.floorplan_id else "N/A"
        return f"FP Hash: {short_hash}... (Analysis: {self.analysis_result_id})"

    @staticmethod
    def generate_hash_id(property_id, user_id, url):  # <-- Accept all three parts
        """
        Generates a SHA-256 hash for the combination of property ID, user ID,
        and URL string.
        """
        if not all([property_id, user_id, url]):  # Ensure all parts are non-empty
            raise ValueError(
                "Cannot generate hash: property_id, user_id, and url must all be provided and non-empty."
            )

        try:
            # Combine the strings with a separator unlikely to appear in the inputs
            combined_string = f"{property_id}|{user_id}|{url}"
            string_bytes = combined_string.encode("utf-8")
            return hashlib.sha256(string_bytes).hexdigest()
        except Exception as e:
            logger.error(
                f"Error generating combined hash for '{property_id}|{user_id}|{url}': {e}"
            )
            raise ValueError(f"Hashing failed for combined input") from e


class AllFloorsData(TrackingModel):
    floor_plan = models.OneToOneField(
        FloorPlan, related_name="all_floors_data", on_delete=models.CASCADE
    )
    json_file_url = models.URLField(max_length=1024, null=True, blank=True)
    csv_url = models.URLField(max_length=1024, null=True, blank=True)
    total_area_csv_url = models.URLField(max_length=1024, null=True, blank=True)
    image_labelme_side_by_side_url = models.URLField(
        max_length=1024, null=True, blank=True
    )
    notes = models.TextField(null=True, blank=True)
    history = HistoricalRecords()

    def __str__(self):
        fp_id = self.floor_plan.floorplan_id if self.floor_plan else "N/A"
        return f"All Floors Data for {fp_id}"


class PlanFloor(TrackingModel):
    """
    Represents each floor-level data inside the API response's 'floors' list.
    """

    floor_plan = models.ForeignKey(
        FloorPlan, related_name="plan_floors", on_delete=models.CASCADE
    )
    floor = models.CharField(max_length=255)  # e.g., "first_floor" or "ground_floor"
    label_me_url = models.URLField(max_length=1024, null=True, blank=True)
    json_file_url = models.URLField(max_length=1024, null=True, blank=True)
    image_url = models.URLField(max_length=1024, null=True, blank=True)
    labelme_image_url = models.URLField(max_length=1024, null=True, blank=True)
    csv_url = models.URLField(max_length=1024, null=True, blank=True)
    image_side_by_side_url = models.URLField(max_length=1024, null=True, blank=True)
    history = HistoricalRecords()

    def __str__(self):
        fp_id = self.floor_plan.floorplan_id if self.floor_plan else "N/A"
        return f"{self.floor} - {fp_id}"


# === CSV Data Models ===
class CsvFloor(TrackingModel):
    """
    Represents each row group from the CSV (identified by Floor_Name).
    Related to a specific AllFloorsData (the CSV file downloaded from csv_url).
    """

    all_floors_data = models.ForeignKey(
        AllFloorsData, related_name="csv_floors", on_delete=models.CASCADE
    )
    floor_name = models.CharField(max_length=100, null=True, blank=True)
    # calculated_floor_total_sq_area_metric
    calculated_total_area_metric = models.FloatField(null=True, blank=True)
    # calculated_floor_total_sq_area_imperial
    calculated_total_area_imperial = models.FloatField(null=True, blank=True)
    history = HistoricalRecords()

    def __str__(self):
        # Handle potential None for floor_name
        return self.floor_name or f"Unnamed Floor (ID: {self.id})"


class CsvRoom(TrackingModel):
    """
    Represents each room (row) in the CSV file.
    """

    floor = models.ForeignKey(CsvFloor, on_delete=models.CASCADE, related_name="rooms")
    room_name = models.CharField(max_length=100, null=True, blank=True)
    is_segment = models.CharField(max_length=50, null=True, blank=True)
    room_id = models.FloatField(
        null=True, blank=True, db_index=True  # Index room_id within a floor
    )
    no_of_doors = models.FloatField(null=True, blank=True)
    no_of_windows = models.FloatField(null=True, blank=True)
    no_of_room_points = models.FloatField(null=True, blank=True)
    history = HistoricalRecords()

    class Meta:
        # Ensure room_id is unique within a specific CsvFloor
        unique_together = ("floor", "room_id")

    def __str__(self):
        try:
            floor_name = self.floor.floor_name or "Unnamed Floor"
        except CsvFloor.DoesNotExist:
            floor_name = "Detached Floor"
        room_name = self.room_name or f"Unnamed Room (ID: {self.id})"
        return f"{room_name} ({floor_name})"


class CsvRoomPixelData(TrackingModel):
    """
    Stores the pixel-specific data for each room from the CSV.
    """

    room = models.OneToOneField(
        CsvRoom, on_delete=models.CASCADE, related_name="pixel_data"
    )
    # Numeric fields from CSV for pixel positions and areas:
    min_x_pixels = models.FloatField(null=True, blank=True)  # Min X Pixels
    min_y_pixels = models.FloatField(null=True, blank=True)  # Min Y Pixels
    max_x_pixels = models.FloatField(null=True, blank=True)  # Max X Pixels
    max_y_pixels = models.FloatField(null=True, blank=True)  # Max Y Pixels
    max_area_pixels = models.FloatField(null=True, blank=True)  # Max Area Pixels
    actual_area_pixels = models.FloatField(null=True, blank=True)  # Actual Area Pixels
    pixel_ratio = models.FloatField(null=True, blank=True)  # Pixel ratio
    history = HistoricalRecords()

    def __str__(self):
        try:
            room_name = self.room.room_name or f"Unnamed Room (ID: {self.room.id})"
            return f"Pixel Data for {room_name}"
        except CsvRoom.DoesNotExist:
            return f"Pixel Data for Detached Room (ID: {self.id})"


class CsvRoomDimensions(TrackingModel):
    """
    Stores dimension and area details for each room.
    """

    room = models.OneToOneField(
        CsvRoom, on_delete=models.CASCADE, related_name="dimensions"
    )
    # Text fields for dimensions (Handles 'Unknown')
    dimensions_imperial = models.CharField(max_length=100, null=True, blank=True)
    dimensions_metric = models.CharField(max_length=100, null=True, blank=True)

    # Numeric fields for maximum areas
    max_area_metric = models.FloatField(null=True, blank=True)
    max_area_imperial = models.FloatField(null=True, blank=True)

    # Numeric fields for calculated areas:
    calculated_sq_area_metric = models.FloatField(
        null=True, blank=True
    )  # Calculated Sq Area Metric
    calculated_area_imperial = models.FloatField(
        null=True, blank=True
    )  # calculated_area_imperial
    history = HistoricalRecords()

    def __str__(self):
        try:
            room_name = self.room.room_name or f"Unnamed Room (ID: {self.room.id})"
            return f"Dimensions for {room_name}"
        except CsvRoom.DoesNotExist:
            return f"Dimensions for Detached Room (ID: {self.id})"


class CsvRoomScalingFactors(TrackingModel):
    """
    Stores scaling factors for metric and imperial measurements.
    """

    room = models.OneToOneField(
        CsvRoom, on_delete=models.CASCADE, related_name="scaling_factors"
    )
    scale_metric = models.FloatField(null=True, blank=True)  # Scale Metric
    scale_imperial = models.FloatField(null=True, blank=True)  # Scale Imperial
    history = HistoricalRecords()

    def __str__(self):
        try:
            room_name = self.room.room_name or f"Unnamed Room (ID: {self.room.id})"
            return f"Scaling Factors for {room_name}"
        except CsvRoom.DoesNotExist:
            return f"Scaling Factors for Detached Room (ID: {self.id})"


class AllFloorsCsvData(TrackingModel):
    """Stores a raw representation of a single row from all_floors.csv."""

    # Link back to the AllFloorsData instance this row belongs to
    all_floors_data = models.ForeignKey(
        AllFloorsData, on_delete=models.CASCADE, related_name="all_floors_csv_data"
    )

    # --- Fields matching CSV columns ---
    # Object/String Columns
    floor_name = models.CharField(
        max_length=100, null=True, blank=True, db_index=True
    )  # Index useful for potential lookups
    room_name = models.CharField(max_length=100, null=True, blank=True)
    is_segment = models.CharField(max_length=50, null=True, blank=True)
    dimensions_imperial = models.CharField(max_length=100, null=True, blank=True)
    dimensions_metric = models.CharField(max_length=100, null=True, blank=True)

    # Float64/Numeric Columns
    room_id = models.FloatField(null=True, blank=True, db_index=True)  # Index useful
    no_of_door = models.FloatField(null=True, blank=True)  # Match CSV header case
    no_of_window = models.FloatField(null=True, blank=True)  # Match CSV header case
    no_of_room_points = models.FloatField(null=True, blank=True)
    min_x_pixels = models.FloatField(
        null=True, blank=True, db_column="min_x_pixels_csv"
    )  # Use db_column if name conflicts/desired
    min_y_pixels = models.FloatField(
        null=True, blank=True, db_column="min_y_pixels_csv"
    )
    max_x_pixels = models.FloatField(
        null=True, blank=True, db_column="max_x_pixels_csv"
    )
    max_y_pixels = models.FloatField(
        null=True, blank=True, db_column="max_y_pixels_csv"
    )
    max_area_metric = models.FloatField(
        null=True, blank=True, db_column="max_area_metric_csv"
    )
    max_area_imperial = models.FloatField(
        null=True, blank=True, db_column="max_area_imperial_csv"
    )
    max_area_pixels = models.FloatField(
        null=True, blank=True, db_column="max_area_pixels_csv"
    )
    actual_area_pixels = models.FloatField(
        null=True, blank=True, db_column="actual_area_pixels_csv"
    )
    pixel_ratio = models.FloatField(null=True, blank=True, db_column="pixel_ratio_csv")
    scale_metric = models.FloatField(
        null=True, blank=True, db_column="scale_metric_csv"
    )
    scale_imperial = models.FloatField(
        null=True, blank=True, db_column="scale_imperial_csv"
    )
    calculated_sq_area_metric = models.FloatField(
        null=True, blank=True, db_column="calculated_sq_area_metric_csv"
    )
    calculated_floor_total_sq_area_metric = models.FloatField(
        null=True, blank=True, db_column="calc_floor_total_metric_csv"
    )
    calculated_area_imperial = models.FloatField(
        null=True, blank=True, db_column="calculated_area_imperial_csv"
    )  # Note lowercase 'c'
    calculated_floor_total_sq_area_imperial = models.FloatField(
        null=True, blank=True, db_column="calc_floor_total_imperial_csv"
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = "All Floors CSV Data"
        verbose_name_plural = "All Floors CSV Data"

        # Add indexes for frequently filtered columns if needed (like floor_name, room_id)
        indexes = [
            models.Index(fields=["all_floors_data", "floor_name"]),
            models.Index(fields=["all_floors_data", "room_id"]),
        ]

    def __str__(self):
        afd_id = self.all_floors_data_id if self.all_floors_data_id else "N/A"
        return (
            f"Raw Row for AFD:{afd_id} - Floor:{self.floor_name} RoomID:{self.room_id}"
        )


class TotalAreasCsvData(TrackingModel):
    """Stores parsed data from the total_area.csv file."""

    # Link back to the AllFloorsData it belongs to
    all_floors_data = models.ForeignKey(
        AllFloorsData, related_name="total_areas_csv_data", on_delete=models.CASCADE
    )
    # Fields corresponding to total_area.csv columns
    area_name = models.CharField(
        max_length=500, null=True, blank=True
    )  # Increased length for descriptive names
    square_meters = models.FloatField(null=True, blank=True)
    square_feet = models.FloatField(null=True, blank=True)
    total_floors = models.IntegerField(null=True, blank=True)  # Assuming integer
    total_named_rooms = models.IntegerField(null=True, blank=True)
    total_segments = models.IntegerField(null=True, blank=True)
    total_points = models.IntegerField(null=True, blank=True)
    total_objects = models.IntegerField(null=True, blank=True)
    total_door_objects = models.IntegerField(null=True, blank=True)
    total_window_objects = models.IntegerField(null=True, blank=True)
    total_stair_objects = models.IntegerField(null=True, blank=True)
    list_of_objects = models.TextField(
        null=True, blank=True
    )  # Store the list representation as text
    total_actual_pixels = models.FloatField(null=True, blank=True)
    metric_scale = models.FloatField(null=True, blank=True)
    imperial_scale = models.FloatField(null=True, blank=True)
    input_image_tokens = models.IntegerField(null=True, blank=True)
    input_text_tokens = models.IntegerField(null=True, blank=True)
    output_text_tokens = models.IntegerField(null=True, blank=True)

    history = HistoricalRecords()

    class Meta:
        # If you only expect one row per Area Name per AllFloorsData, enforce it
        unique_together = ("all_floors_data", "area_name")
        verbose_name_plural = "Total Area Data"  # Nicer name in admin

    def __str__(self):
        fp_id = (
            self.all_floors_data.floor_plan.floorplan_id
            if self.all_floors_data and self.all_floors_data.floor_plan
            else "N/A"
        )
        return f"{self.area_name} for {fp_id}"


# csv has been renamed to all_floors.csv
# save metabase sql for the report writing so that
