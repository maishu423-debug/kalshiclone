from django.apps import AppConfig


class KalshiApiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "kalshi_api"

    def ready(self):
        # Start the background forecast refresh thread once Django is up.
        # Guard against double-start in Django's local auto-reloader, while still
        # starting under Gunicorn on Render where RUN_MAIN is not set.
        import os
        if os.environ.get("RUN_MAIN") != "true" and os.environ.get("RENDER") != "true":
            return
        from .forecast import start_background_refresh
        from .price_tracker import start_price_tracking
        from .temp_monitor import start_temp_monitor
        start_background_refresh()
        start_temp_monitor()
        start_price_tracking()
