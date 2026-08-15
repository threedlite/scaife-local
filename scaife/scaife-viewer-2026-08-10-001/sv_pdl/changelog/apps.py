from django.apps import AppConfig


class ChangelogConfig(AppConfig):
    # Must be the full dotted path. Django 2.2 never loaded this class
    # (no default_app_config, so it was never auto-discovered); from 3.2
    # apps.py is discovered automatically and the bare name failed with
    # ImproperlyConfigured: Cannot import 'changelog'. The default label is
    # the last component either way, so it stays "changelog" and no migration
    # state changes.
    name = "sv_pdl.changelog"
