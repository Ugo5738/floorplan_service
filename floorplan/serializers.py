from rest_framework import serializers

from floorplan.models import (
    FloorPlanAnalysisResult,
    FloorPlan,
    AllFloorsData,
    PlanFloor,
    AllFloorsCsvData,
    TotalAreasCsvData,
)


class TotalAreasCsvDataSerializer(serializers.ModelSerializer):
    class Meta:
        model = TotalAreasCsvData
        exclude = ["history", "created_at", "updated_at", "all_floors_data"]


class AllFloorsCsvDataSerializer(serializers.ModelSerializer):
    class Meta:
        model = AllFloorsCsvData
        exclude = ["history", "created_at", "updated_at", "all_floors_data"]


class PlanFloorSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlanFloor
        exclude = ["history", "created_at", "updated_at", "floor_plan"]


class AllFloorsDataSerializer(serializers.ModelSerializer):
    all_floors_csv_data = AllFloorsCsvDataSerializer(many=True, read_only=True)
    total_areas_csv_data = TotalAreasCsvDataSerializer(many=True, read_only=True)
    
    class Meta:
        model = AllFloorsData
        exclude = ["history", "created_at", "updated_at", "floor_plan"]


class FloorPlanSerializer(serializers.ModelSerializer):
    all_floors_data = AllFloorsDataSerializer(read_only=True)
    plan_floors = PlanFloorSerializer(many=True, read_only=True)
    
    class Meta:
        model = FloorPlan
        exclude = ["history", "created_at", "updated_at", "analysis_result"]


class FloorPlanAnalysisResultSerializer(serializers.ModelSerializer):
    floor_plans = FloorPlanSerializer(many=True, read_only=True)
    
    class Meta:
        model = FloorPlanAnalysisResult
        exclude = ["history", "created_at", "updated_at"]


class PropertyOverviewSerializer(serializers.ModelSerializer):
    """Simplified serializer for property overview"""
    floor_plan_count = serializers.SerializerMethodField()
    
    class Meta:
        model = FloorPlanAnalysisResult
        fields = ["id", "property_id", "user_id", "message", "floor_plan_count", "created_at"]
    
    def get_floor_plan_count(self, obj):
        return obj.floor_plans.count()
