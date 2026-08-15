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
    "isort>=5.6.4,<6",
] + tests_require

setup(
    author="Scaife Viewer Team",
    author_email="jtauber+scaife@jtauber.com",
    description="Aligned Text and Linguistic Annotation Server (ATLAS)",
    name="scaife-viewer-atlas",
    version="0.1a15",
    url="http://github.com/scaife-viewer/backend/",
    license="MIT",
    packages=find_packages(),
    package_data={
        "atlas": []
    },
    test_suite="runtests.runtests",
    # LOCAL CHANGE (2026-08-14): Django floor raised to 3.2 and the four
    # co-dependencies raised to the newest releases that still support it.
    # Deliberately not the newest overall — django-filter 26, treebeard 7
    # and django-extensions 4 all now require Django >= 4.2 or >= 5.2 and
    # Python >= 3.10, which would force the whole framework and
    # interpreter move into one step. See DJANGO-3.2-PLAN.md §2.
    install_requires=[
        "django_appconf>=1.0.4",
        "django-extensions>=3.2.3,<4",
        "django-filter>=23.5,<24",
        # LOCAL CHANGE (2026-08-14): 3.1.1 calls rel.is_hidden(), which
        # Django 5.0 replaced with the `hidden` property. 4.0.0 covers
        # Django 4.2-5.1 and is the only release that works here.
        "django-sortedm2m>=4.0,<5",
        "django-treebeard>=4.7.1,<5",
        "Django>=5.2,<6",
        # LOCAL CHANGE (2026-08-14): was graphene-django==2.6.0.
        # 2.16.0 is the last release of the 2.x line and the only one whose
        # metadata declares Django>=2.2 rather than >=1.11. Still graphene 2,
        # so the schema is unaffected; this is the staging step before the
        # graphene 3 port, which cannot happen until Django is on 3.2.
        # See DJANGO-3.2-PLAN.md §4.1.
        # LOCAL CHANGE (2026-08-14): graphene-django 3. Required before
        # Django 4.0, which removes force_text — used throughout
        # graphene-django 2.x. Brings graphene 3 and graphql-core 3.
        "graphene-django>=3.2,<4",
        "logfmt==0.4",
        "regex>=2020.11.13",
        "tqdm>= 4.48.2,<5",
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


