from django.db import models

# === API-Level Models ===


class FloorPlanAnalysisResult(models.Model):
    message = models.CharField(max_length=255)
    user_id = models.CharField(max_length=255)
    property_id = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user_id} - {self.property_id}"


class FloorPlan(models.Model):
    analysis_result = models.ForeignKey(
        FloorPlanAnalysisResult, related_name="floor_plans", on_delete=models.CASCADE
    )
    floorplan_id = models.CharField(max_length=255)
    original_url = models.URLField()

    def __str__(self):
        return self.floorplan_id


class AllFloorsData(models.Model):
    floor_plan = models.OneToOneField(
        FloorPlan, related_name="all_floors_data", on_delete=models.CASCADE
    )
    json_file_url = models.URLField()
    csv_url = models.URLField()
    total_area_csv_url = models.URLField()
    image_labelme_side_by_side_url = models.URLField()
    notes = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"All Floors Data for {self.floor_plan.floorplan_id}"


class PlanFloor(models.Model):
    """
    Represents each floor-level data inside the API response's 'floors' list.
    """

    floor_plan = models.ForeignKey(
        FloorPlan, related_name="plan_floors", on_delete=models.CASCADE
    )
    floor = models.CharField(max_length=255)  # e.g., "first_floor" or "ground_floor"
    label_me_url = models.URLField()
    json_file_url = models.URLField()
    image_url = models.URLField()
    labelme_image_url = models.URLField()
    csv_url = models.URLField()
    image_side_by_side_url = models.URLField()

    def __str__(self):
        return f"{self.floor} - {self.floor_plan.floorplan_id}"


# === CSV Data Models (Your Original Models, Renamed) ===


class CsvFloor(models.Model):
    """
    Represents each row group from the CSV (identified by Floor_Name).
    Related to a specific AllFloorsData (the CSV file downloaded from csv_url).
    """

    all_floors_data = models.ForeignKey(
        AllFloorsData, related_name="csv_floors", on_delete=models.CASCADE
    )
    floor_name = models.CharField(max_length=100, null=True, blank=True)
    calculated_total_area_metric = models.FloatField(null=True, blank=True)
    calculated_total_area_imperial = models.FloatField(null=True, blank=True)

    def __str__(self):
        return self.floor_name


class CsvRoom(models.Model):
    """
    Represents each room (row) in the CSV file.
    """

    floor = models.ForeignKey(CsvFloor, on_delete=models.CASCADE, related_name="rooms")
    room_name = models.CharField(max_length=100, null=True, blank=True)
    is_segment = models.CharField(max_length=50, null=True, blank=True)
    room_id = models.FloatField(null=True, blank=True)
    no_of_doors = models.FloatField(null=True, blank=True)
    no_of_windows = models.FloatField(null=True, blank=True)
    no_of_room_points = models.FloatField(null=True, blank=True)

    def __str__(self):
        return f"{self.room_name} ({self.floor.name})"


class CsvRoomPixelData(models.Model):
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

    def __str__(self):
        return f"Pixel Data for {self.room.room_name}"


class CsvRoomDimensions(models.Model):
    """
    Stores dimension and area details for each room.
    """

    room = models.OneToOneField(
        CsvRoom, on_delete=models.CASCADE, related_name="dimensions"
    )
    # Text fields for dimensions
    dimensions_imperial = models.CharField(max_length=100, null=True, blank=True)
    dimensions_metric = models.CharField(max_length=100, null=True, blank=True)

    # Numeric fields for maximum areas
    max_area_metric = models.FloatField(null=True, blank=True)
    max_area_imperial = models.FloatField(null=True, blank=True)

    # Numeric fields for calculated areas:
    calculated_sq_area_metric = models.FloatField(
        null=True, blank=True
    )  # Calculated Sq Area Metric
    calculated_floor_total_sq_area_metric = models.FloatField(
        null=True, blank=True
    )  # Calculated Floor Total Sq Area Metric
    calculated_area_imperial = models.FloatField(
        null=True, blank=True
    )  # calculated_area_imperial
    calculated_floor_total_sq_area_imperial = models.FloatField(
        null=True, blank=True
    )  # Calculated Floor Total Sq Area Imperial

    def __str__(self):
        return f"Dimensions for {self.room.room_name}"


class CsvRoomScalingFactors(models.Model):
    """
    Stores scaling factors for metric and imperial measurements.
    """

    room = models.OneToOneField(
        CsvRoom, on_delete=models.CASCADE, related_name="scaling_factors"
    )
    scale_metric = models.FloatField(null=True, blank=True)  # Scale Metric
    scale_imperial = models.FloatField(null=True, blank=True)  # Scale Imperial

    def __str__(self):
        return f"Scaling Factors for {self.room.room_name}"
