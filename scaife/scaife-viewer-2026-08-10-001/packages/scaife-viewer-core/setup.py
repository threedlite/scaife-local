from setuptools import find_packages, setup

# LOCAL CHANGE (2026-08-14): upstream caps these below majors that predate
# Python 3.12. hypothesis <6 calls importlib_metadata.entry_points().get(),
# which 3.12 removed, so the suite cannot even be collected; pytest-django
# <4 predates Django 5. Raised to the current majors.
tests_require = [
    "pytest-cov>=4",
    "pytest-django>=4.5",
    "hypothesis>=6,<7",
]

dev_requires = [
    "black==19.10b0",
    "flake8>=3.7,<4",
    "flake8-quotes>=2.1.1,<3",
    "isort>=4.3.21,<5",
] + tests_require

setup(
    author="Scaife Viewer Team",
    author_email="jtauber+scaife@jtauber.com",
    description="Scaife Viewer Backend :: Core Functionality",
    name="scaife-viewer-core",
    version="0.1a9",
    url="https://github.com/scaife-viewer/backend/",
    license="MIT",
    packages=find_packages(),
    include_package_data=True,
    entry_points={
        "console_scripts": [
            "scaife=scaife_viewer.core.cli:cli"
        ],
    },
    test_suite="runtests.runtests",
    install_requires=[
        # LOCAL CHANGE (2026-08-15): was anytree==2.4.3 (2018), whose
        # Resolver.__translate appends "\\Z(?ms)" — a global inline regex
        # flag at the END of the pattern. Python 3.11 made that an error
        # ("global flags not at the start of the expression"), so every
        # anytree path resolution raised. That is the CTS table-of-contents
        # resolver, so /library/<version>/json/ returned 500 and the reader
        # could not open a text. 2.13.0 requires Python >= 3.9.2.
        "anytree>=2.13,<3",
        # LOCAL CHANGE (2026-08-14): was certifi==2018.11.29. The image
        # installs a patched certifi over the top of this pin (CVE-2023-37920
        # and CVE-2022-23491 both concern removed-for-cause CA roots), which
        # pip reported as a dependency conflict and then proceeded past. A
        # floor rather than an exact pin makes the metadata agree with what
        # is actually installed. See packages/README.md.
        "certifi>=2018.11.29",
        "click>=8.0.0",
        "dask[bag]==2022.1.0",
        "django_appconf>=1.0.4",
        # LOCAL CHANGE (2026-08-14): was Django>=2.2,<3.0. Raised to 3.2 in
        # step with atlas. See DJANGO-3.2-PLAN.md §4.3.
        "Django>=5.2,<6",
        # LOCAL CHANGE (2026-08-14): was elasticsearch>=7,<8. This cap is
        # what kept the client an API generation behind an Elasticsearch 8
        # server. OpenSearch forked from ES 7.10, so opensearch-py — itself
        # a fork of elasticsearch-py 7.x — matches the server again.
        # <3 because opensearch-py 3.1+ requires Python 3.10.
        "opensearch-py>=2.8,<3",
        "google-auth==1.6.2",
        "google-cloud-pubsub==0.39.1",
        "lxml>=4.3.5",
        "MyCapytain==3.0.1",
        "python-dateutil==2.7.5",
        "python-mimeparse==1.6.0",
        "rdflib==4.2.2",
        "regex>=2020.11.13",
        # LOCAL CHANGE (2026-08-14): was requests==2.22.0, for the same
        # reason as certifi above.
        "requests>=2.22.0",
        "ruamel.yaml==0.17.21",
        "wrapt==1.11.1",
    ],
    tests_require=tests_require,
    extras_require={
        "test": tests_require,
        "dev": dev_requires,
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Environment :: Web Environment",
        "Framework :: Django",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    zip_safe=False
)
