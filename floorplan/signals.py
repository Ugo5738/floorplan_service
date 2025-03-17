# from django.db.models.signals import post_save
# from django.dispatch import receiver

# from floorplan.models import FloorPlan
# from floorplan.utils.backup import backup_floorplan


# @receiver(post_save, sender=FloorPlan)
# def backup_floorplan_handler(sender, instance, created, **kwargs):
#     # Optionally, you can check for 'created' or even filter updates if needed.
#     try:
#         backup_floorplan(instance)
#     except Exception as e:
#         # Log error; you may want to implement retry logic or asynchronous backup here.
#         print("Error backing up property:", e)
