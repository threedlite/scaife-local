from importlib import import_module

from django.apps import AppConfig as BaseAppConfig
from django.conf import settings


class WebAnalyticsConfig(BaseAppConfig):
    """Replacement app config for `pinax.webanalytics`.

    The package ships `label = "pinax-webanalytics"`, and from Django 3.2 an
    app label must be a valid Python identifier, so loading it aborts
    startup with ImproperlyConfigured. `pinax-webanalytics` 5.0.0 — the
    latest release — still has the hyphen, so there is no version to upgrade
    to; the package is unmaintained against current Django.

    The app is still needed: `templates/site_base.html` loads
    `pinax_webanalytics_tags` and calls `{% analytics %}`. Only the label is
    wrong, and nothing depends on its value — the app has no models and no
    migrations, and template tag libraries are found by module, not by
    label.

    Written out rather than subclassing the packaged AppConfig on purpose:
    that module also imports `ugettext_lazy`, removed in Django 4.0, so
    importing it would carry a second blocker forward. Defining the config
    here means `pinax/webanalytics/apps.py` is never imported.
    """

    name = "pinax.webanalytics"
    label = "pinax_webanalytics"
    verbose_name = "Pinax Web Analytics"


class AppConfig(BaseAppConfig):
    name = "sv_pdl"

    def ready(self):
        import_module("sv_pdl.receivers")

        if settings.DEBUG is False:
            # calling this will prime the cache in the master process. each fork
            # will inherit it. gunicorn --preload is required for this to work.
            precomputed = import_module("scaife_viewer.core.precomputed")
            precomputed.library_view_json()
            print("Precomputed library view JSON")
