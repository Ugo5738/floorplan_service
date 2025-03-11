from django.db import models


class Floorplan(models.Model):
    # total_area_metric as fp display
    pass


class Floor(models.Model):
    name = models.CharField(max_length=100, unique=True)
    calculated_total_area_metric = models.FloatField(null=True, blank=True)
    calculated_total_area_imperial = models.FloatField(null=True, blank=True)

    def __str__(self):
        return self.name


class Room(models.Model):
    floor = models.ForeignKey(Floor, on_delete=models.CASCADE, related_name="rooms")
    room_name = models.CharField(max_length=100)
    is_segment = models.CharField(max_length=50, blank=True, null=True)
    room_id = models.FloatField(null=True, blank=True)
    no_of_doors = models.FloatField(null=True, blank=True)
    no_of_windows = models.FloatField(null=True, blank=True)
    no_of_room_points = models.FloatField(null=True, blank=True)

    def __str__(self):
        return f"{self.room_name} ({self.floor.name})"


class RoomPixelData(models.Model):
    room = models.OneToOneField(
        Room, on_delete=models.CASCADE, related_name="pixel_data"
    )
    min_x_pixels = models.FloatField(null=True, blank=True)
    min_y_pixels = models.FloatField(null=True, blank=True)
    max_x_pixels = models.FloatField(null=True, blank=True)
    max_y_pixels = models.FloatField(null=True, blank=True)
    max_area_pixels = models.FloatField(null=True, blank=True)
    actual_area_pixels = models.FloatField(null=True, blank=True)
    pixel_ratio = models.FloatField(null=True, blank=True)

    def __str__(self):
        return f"Pixel Data for {self.room.room_name}"


class RoomDimensions(models.Model):
    room = models.OneToOneField(
        Room, on_delete=models.CASCADE, related_name="dimensions"
    )
    dimensions_imperial = models.CharField(max_length=100, blank=True, null=True)
    dimensions_metric = models.CharField(max_length=100, blank=True, null=True)
    max_area_metric = models.FloatField(null=True, blank=True)
    max_area_imperial = models.FloatField(null=True, blank=True)
    calculated_area_metric = models.FloatField(null=True, blank=True)
    calculated_area_imperial = models.FloatField(null=True, blank=True)

    def __str__(self):
        return f"Dimensions for {self.room.room_name}"


class RoomScalingFactors(models.Model):
    room = models.OneToOneField(
        Room, on_delete=models.CASCADE, related_name="scaling_factors"
    )
    scale_metric = models.FloatField(null=True, blank=True)
    scale_imperial = models.FloatField(null=True, blank=True)

    def __str__(self):
        return f"Scaling Factors for {self.room.room_name}"
