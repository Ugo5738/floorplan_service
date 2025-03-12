from django.apps import AppConfig


class FloorplanConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "floorplan"

    def ready(self):
        # Import the signals module to ensure signal handlers are registered.
        import floorplan.signals  # registers the signal handlers

        print("Floorplan signals have been imported and registered.")
