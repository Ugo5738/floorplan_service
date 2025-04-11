from floorplan.models import FloorPlan

# 3. List the PKs with missing URLs
missing_url_pks = [168, 169, 170, 171, 172, 196]

# 4. Loop and update
updated_count = 0
not_found_count = 0
print(f"Attempting to update original_url for {len(missing_url_pks)} records...")

for pk in missing_url_pks:
    try:
        fp = FloorPlan.objects.get(pk=pk)
        # Generate the fake URL using the pattern
        fake_url = f"https://fake-placeholder.com/floorplan/{pk}"
        fp.original_url = fake_url
        fp.save(update_fields=["original_url"])  # Only update this field
        print(f"  Updated pk={pk} with URL: {fake_url}")
        updated_count += 1
    except FloorPlan.DoesNotExist:
        print(f"  Record pk={pk} not found.")
        not_found_count += 1
    except Exception as e:
        print(f"  Error updating pk={pk}: {e}")

print(f"\nFinished updating URLs.")
print(f"Successfully updated: {updated_count}")
print(f"Not found: {not_found_count}")


# --- ALSO DELETE THE TRULY REDUNDANT RECORD ---
# As identified before, one of 199 or 201 needs deletion.
# Let's delete 201.
pk_to_delete = 201
try:
    print(f"\nAttempting to delete truly redundant record pk={pk_to_delete}...")
    fp_to_delete = FloorPlan.objects.get(pk=pk_to_delete)
    deleted_info = fp_to_delete.delete()
    print(f"Successfully deleted pk={pk_to_delete}. Info: {deleted_info}")
except FloorPlan.DoesNotExist:
    print(f"Record pk={pk_to_delete} already deleted or not found.")
except Exception as e:
    print(f"Error deleting pk={pk_to_delete}: {e}")
