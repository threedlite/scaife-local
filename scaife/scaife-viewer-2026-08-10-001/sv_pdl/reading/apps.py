from django.apps import AppConfig


class ReadingConfig(AppConfig):
    # Must be the full dotted path. Django 2.2 never loaded this class
    # (no default_app_config, so it was never auto-discovered); from 3.2
    # apps.py is discovered automatically and the bare name failed with
    # ImproperlyConfigured: Cannot import 'reading'. The default label is
    # the last component either way, so it stays "reading" and no migration
    # state changes.
    name = "sv_pdl.reading"
