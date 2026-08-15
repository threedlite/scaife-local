"""Restore a few Django APIs that unmaintained dependencies still import.

Django 4.0 removed `force_text`, `smart_text`, the `ugettext*` aliases,
and `Model._meta.installed`. `HttpRequest.is_ajax()` is not shimmed:
django-user-accounts 3.3.2 ships its own `is_ajax(request)` helper and no
longer calls the removed method.

Three installed packages still need the rest, and for each one the *latest
release* is what we already have — there is no version to upgrade to:

| Package | Needs | Latest release | Where |
|---|---|---|---|
| `pinax-theme-bootstrap` 8.0.1 | `force_text` | 8.0.1 | `templatetags/pinax_theme_bootstrap_tags.py` |
| `pinax-theme-bootstrap` 8.0.1 | `Model._meta.installed` | 8.0.1 | `context_processors.py` (runs on every page) |
| `pinax-webanalytics` 5.0.0 | `ugettext_lazy` | 5.0.0 | `apps.py` |
| `raven` 6.10.0 | `force_text`, `smart_text` | 6.10.0 (deprecated by upstream in favour of `sentry-sdk`) | `raven/utils/encoding.py` |

All three are wired into the running site — the theme provides the base
template every page extends — so dropping them means dropping features,
not tidying. Shimming the handful of removed names is the smaller change, and
it is what keeps the Django upgrade a backend-only exercise.

This is deliberately a **compatibility shim, not a fix**. It is debt: each
row above is a package that should eventually be replaced or vendored. To
keep the debt visible rather than silently permanent,
`sv_pdl/tests/test_django_compat.py` asserts that the set of packages
relying on it is exactly the table above. When a package is fixed or
dropped, that test fails and the corresponding shim can go.

Imported from the top of `settings.py`, which runs before any app is
loaded — `account/forms.py` and the theme's template tags import these
names at module scope, so a later hook would be too late.
"""


def install():
    """Idempotently re-add the removed names. Safe on any Django version."""
    from django.utils import encoding

    # Removed in Django 4.0; force_str/smart_str are the same functions.
    if not hasattr(encoding, "force_text"):
        encoding.force_text = encoding.force_str
    if not hasattr(encoding, "smart_text"):
        encoding.smart_text = encoding.smart_str

    from django.utils import translation

    # Removed in Django 4.0. The u-prefixed names were Python 2 era aliases
    # for the identical functions.
    for legacy, current in (
        ("ugettext", "gettext"),
        ("ugettext_lazy", "gettext_lazy"),
        ("ugettext_noop", "gettext_noop"),
        ("ungettext", "ngettext"),
        ("ungettext_lazy", "ngettext_lazy"),
    ):
        if not hasattr(translation, legacy) and hasattr(translation, current):
            setattr(translation, legacy, getattr(translation, current))

    from django.db.models.options import Options

    # `Model._meta.installed` was removed in Django 4.0. Restored with
    # Django's own former implementation — a model's app is installed
    # exactly when it resolved to an AppConfig. pinax-theme-bootstrap's
    # `theme` context processor calls `Site._meta.installed`, and that
    # context processor runs on every page, so without this every request
    # is a 500.
    if not hasattr(Options, "installed"):
        Options.installed = property(lambda self: self.app_config is not None)
