from django.db.models import Count

from floorplan.models import FloorPlan

print("--- Finding FloorPlan duplicates based on floorplan_id ---")

duplicates = (
    FloorPlan.objects.values("floorplan_id")
    .annotate(count=Count("id"))
    .filter(count__gt=1)
)

if not duplicates:
    print("No duplicate floorplan_id values found in FloorPlan table.")
else:
    print(f"Found {duplicates.count()} floorplan_id values with duplicates.")
    for item in duplicates:
        fp_id = item["floorplan_id"]
        count = item["count"]
        print(
            f"\nFound {count} records for floorplan_id '{fp_id}'. Preparing to delete extras..."
        )

        # Get all records for this floorplan_id, order by creation time of the *analysis result*
        # or the floorplan's own ID as a fallback. Keep the ONE associated with the
        # EARLIEST analysis result (or adjust ordering as needed).
        results_to_check = FloorPlan.objects.filter(floorplan_id=fp_id).order_by(
            "analysis_result__created_at", "id"
        )  # Or '-analysis_result__created_at' to keep newest

        # Keep the first one, get IDs of the rest to delete
        ids_to_delete = list(results_to_check.values_list("id", flat=True)[1:])

        if ids_to_delete:
            record_to_keep = results_to_check.first()
            print(
                f"  Keeping FloorPlan ID: {record_to_keep.id} (AnalysisResult ID: {record_to_keep.analysis_result_id}, Created: {record_to_keep.analysis_result.created_at})"
            )
            print(f"  Planning to Delete FloorPlan IDs: {ids_to_delete}")
            # *** UNCOMMENT THE NEXT LINE TO ACTUALLY DELETE ***
            FloorPlan.objects.filter(id__in=ids_to_delete).delete()
            print(
                f"  ---> Deletion SKIPPED (uncomment the delete line to proceed)"
            )  # Safety message
        else:
            print(
                f"  No extra records found to delete for floorplan_id '{fp_id}', count was {count}. Check manually."
            )

print("\n--- FloorPlan duplicate cleanup check finished ---")
print(
    "Review the output. If correct, BACKUP YOUR DB, then re-run the loop but UNCOMMENT the delete line."
)
