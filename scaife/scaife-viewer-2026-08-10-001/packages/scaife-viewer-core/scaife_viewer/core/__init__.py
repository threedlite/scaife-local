# LOCAL CHANGE (2026-08-15): was `import pkg_resources` +
# `pkg_resources.get_distribution(...).version`. pkg_resources is a
# setuptools API that setuptools 81 deprecated and later versions
# removed, and these two files were the *only* remaining users of it in
# the whole image — which is why the Dockerfile had to pin
# setuptools==81.0. importlib.metadata is the stdlib replacement
# (Python 3.8+) and releases that pin.
from importlib.metadata import version


default_app_config = "scaife_viewer.core.apps.AppConfig"
__version__ = version("scaife-viewer-core")
