from django.contrib import admin

from floorplan.models import (
    AllFloorsData,
    CsvFloor,
    CsvRoom,
    CsvRoomDimensions,
    CsvRoomPixelData,
    CsvRoomScalingFactors,
    FloorPlan,
    FloorPlanAnalysisResult,
    PlanFloor,
)


class FloorPlanInline(admin.TabularInline):
    model = FloorPlan
    extra = 0


@admin.register(FloorPlanAnalysisResult)
class FloorPlanAnalysisResultAdmin(admin.ModelAdmin):
    list_display = ("user_id", "property_id", "message", "created_at")
    list_filter = ("created_at",)
    search_fields = ("user_id", "property_id", "message")
    date_hierarchy = "created_at"
    inlines = [FloorPlanInline]


class PlanFloorInline(admin.TabularInline):
    model = PlanFloor
    extra = 0


class AllFloorsDataInline(admin.StackedInline):
    model = AllFloorsData
    extra = 0


@admin.register(FloorPlan)
class FloorPlanAdmin(admin.ModelAdmin):
    list_display = ("floorplan_id", "get_property_id", "get_user_id")
    search_fields = (
        "floorplan_id",
        "analysis_result__property_id",
        "analysis_result__user_id",
    )
    inlines = [AllFloorsDataInline, PlanFloorInline]

    def get_property_id(self, obj):
        return obj.analysis_result.property_id

    get_property_id.short_description = "Property ID"
    get_property_id.admin_order_field = "analysis_result__property_id"

    def get_user_id(self, obj):
        return obj.analysis_result.user_id

    get_user_id.short_description = "User ID"
    get_user_id.admin_order_field = "analysis_result__user_id"


@admin.register(AllFloorsData)
class AllFloorsDataAdmin(admin.ModelAdmin):
    list_display = ("get_floorplan_id", "get_property_id", "has_notes")
    search_fields = (
        "floor_plan__floorplan_id",
        "floor_plan__analysis_result__property_id",
        "floor_plan__analysis_result__user_id",
    )
    list_filter = ("floor_plan__analysis_result__created_at",)

    def get_floorplan_id(self, obj):
        return obj.floor_plan.floorplan_id

    get_floorplan_id.short_description = "Floor Plan ID"
    get_floorplan_id.admin_order_field = "floor_plan__floorplan_id"

    def get_property_id(self, obj):
        return obj.floor_plan.analysis_result.property_id

    get_property_id.short_description = "Property ID"
    get_property_id.admin_order_field = "floor_plan__analysis_result__property_id"

    def has_notes(self, obj):
        return bool(obj.notes)

    has_notes.boolean = True
    has_notes.short_description = "Has Notes"


@admin.register(PlanFloor)
class PlanFloorAdmin(admin.ModelAdmin):
    list_display = ("floor", "get_floorplan_id", "get_property_id")
    list_filter = ("floor",)
    search_fields = (
        "floor",
        "floor_plan__floorplan_id",
        "floor_plan__analysis_result__property_id",
    )

    def get_floorplan_id(self, obj):
        return obj.floor_plan.floorplan_id

    get_floorplan_id.short_description = "Floor Plan ID"
    get_floorplan_id.admin_order_field = "floor_plan__floorplan_id"

    def get_property_id(self, obj):
        return obj.floor_plan.analysis_result.property_id

    get_property_id.short_description = "Property ID"
    get_property_id.admin_order_field = "floor_plan__analysis_result__property_id"


class CsvRoomInline(admin.TabularInline):
    model = CsvRoom
    extra = 0
    fields = ("room_name", "is_segment", "room_id", "no_of_doors", "no_of_windows")


@admin.register(CsvFloor)
class CsvFloorAdmin(admin.ModelAdmin):
    list_display = (
        "floor_name",
        "get_floorplan_id",
        "get_property_id",
        "calculated_total_area_metric",
        "calculated_total_area_imperial",
        "room_count",
    )
    search_fields = (
        "floor_name",
        "all_floors_data__floor_plan__floorplan_id",
        "all_floors_data__floor_plan__analysis_result__property_id",
    )
    inlines = [CsvRoomInline]

    def get_floorplan_id(self, obj):
        return obj.all_floors_data.floor_plan.floorplan_id

    get_floorplan_id.short_description = "Floor Plan ID"
    get_floorplan_id.admin_order_field = "all_floors_data__floor_plan__floorplan_id"

    def get_property_id(self, obj):
        return obj.all_floors_data.floor_plan.analysis_result.property_id

    get_property_id.short_description = "Property ID"
    get_property_id.admin_order_field = (
        "all_floors_data__floor_plan__analysis_result__property_id"
    )

    def room_count(self, obj):
        return obj.rooms.count()

    room_count.short_description = "Room Count"


class CsvRoomPixelDataInline(admin.StackedInline):
    model = CsvRoomPixelData
    extra = 0


class CsvRoomDimensionsInline(admin.StackedInline):
    model = CsvRoomDimensions
    extra = 0


class CsvRoomScalingFactorsInline(admin.StackedInline):
    model = CsvRoomScalingFactors
    extra = 0


@admin.register(CsvRoom)
class CsvRoomAdmin(admin.ModelAdmin):
    list_display = (
        "room_name",
        "get_floor_name",
        "get_floorplan_id",
        "is_segment",
        "no_of_doors",
        "no_of_windows",
    )
    list_filter = ("is_segment", "floor__floor_name")
    search_fields = (
        "room_name",
        "floor__floor_name",
        "floor__all_floors_data__floor_plan__floorplan_id",
    )
    inlines = [
        CsvRoomPixelDataInline,
        CsvRoomDimensionsInline,
        CsvRoomScalingFactorsInline,
    ]

    def get_floor_name(self, obj):
        return obj.floor.floor_name

    get_floor_name.short_description = "Floor"
    get_floor_name.admin_order_field = "floor__floor_name"

    def get_floorplan_id(self, obj):
        return obj.floor.all_floors_data.floor_plan.floorplan_id

    get_floorplan_id.short_description = "Floor Plan ID"
    get_floorplan_id.admin_order_field = (
        "floor__all_floors_data__floor_plan__floorplan_id"
    )


# Register the remaining models (if needed to access them independently)
@admin.register(CsvRoomPixelData)
class CsvRoomPixelDataAdmin(admin.ModelAdmin):
    list_display = (
        "get_room_name",
        "get_floor_name",
        "min_x_pixels",
        "min_y_pixels",
        "max_x_pixels",
        "max_y_pixels",
        "actual_area_pixels",
    )
    search_fields = ("room__room_name", "room__floor__floor_name")

    def get_room_name(self, obj):
        return obj.room.room_name

    get_room_name.short_description = "Room"
    get_room_name.admin_order_field = "room__room_name"

    def get_floor_name(self, obj):
        return obj.room.floor.floor_name

    get_floor_name.short_description = "Floor"
    get_floor_name.admin_order_field = "room__floor__floor_name"


@admin.register(CsvRoomDimensions)
class CsvRoomDimensionsAdmin(admin.ModelAdmin):
    list_display = (
        "get_room_name",
        "get_floor_name",
        "dimensions_metric",
        "dimensions_imperial",
        "calculated_sq_area_metric",
        "calculated_area_imperial",
    )
    search_fields = ("room__room_name", "room__floor__floor_name")

    def get_room_name(self, obj):
        return obj.room.room_name

    get_room_name.short_description = "Room"
    get_room_name.admin_order_field = "room__room_name"

    def get_floor_name(self, obj):
        return obj.room.floor.floor_name

    get_floor_name.short_description = "Floor"
    get_floor_name.admin_order_field = "room__floor__floor_name"


@admin.register(CsvRoomScalingFactors)
class CsvRoomScalingFactorsAdmin(admin.ModelAdmin):
    list_display = (
        "get_room_name",
        "get_floor_name",
        "scale_metric",
        "scale_imperial",
    )
    search_fields = ("room__room_name", "room__floor__floor_name")

    def get_room_name(self, obj):
        return obj.room.room_name

    get_room_name.short_description = "Room"
    get_room_name.admin_order_field = "room__room_name"

    def get_floor_name(self, obj):
        return obj.room.floor.floor_name

    get_floor_name.short_description = "Floor"
    get_floor_name.admin_order_field = "room__floor__floor_name"
