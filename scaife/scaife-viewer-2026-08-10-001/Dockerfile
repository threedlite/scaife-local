FROM node:12.13-alpine AS static-build
RUN apk --no-cache add \
    g++ make python
WORKDIR /opt/scaife-viewer/src/
COPY package.json package-lock.json ./
RUN npm ci
COPY webpack.config.js babel.config.js .eslintrc.json ./
COPY ./static static
COPY ./test test

ARG FORCE_SCRIPT_NAME
# Style checks are opt-in: a lint error should not stop you from getting a
# working image. Run them deliberately with `bash scripts/lint.sh`, or bake
# them back into the build with --build-arg RUN_LINT=1.
ARG RUN_LINT=0
RUN if [ "$RUN_LINT" = "1" ]; then npm run lint; \
    else echo "skipping npm run lint (build with --build-arg RUN_LINT=1 to enable)"; fi
# Unit tests stay mandatory - they catch broken behaviour, not formatting.
RUN npm run unit
RUN npm run build

# LOCAL CHANGE: 3.8 -> 3.9, matching upstream's own deployment image
# (deploy/webapp/webapp-base.dockerfile). The `python:3.8-alpine` tag is
# frozen at Alpine 3.20.3 because it stopped being rebuilt when Python 3.8
# went EOL, so it no longer receives OS security updates. `python:3.9-alpine`
# currently ships Alpine 3.22.2. Django 2.2.28 supports Python 3.9.
# LOCAL CHANGE (2026-08-14): was python:3.9-alpine. 3.9 reached EOL in
# 2025-10 and Django 5.2 requires 3.10+. 3.12 rather than 3.13 because it
# is supported by both Django 4.2 and 5.2, so the interpreter move and
# the framework move stay independently revertible.
FROM python:3.12-alpine AS python-build
WORKDIR /opt/scaife-viewer/src/
RUN pip --no-cache-dir --disable-pip-version-check install virtualenv
ENV PATH="/opt/scaife-viewer/bin:${PATH}" VIRTUAL_ENV="/opt/scaife-viewer"
COPY requirements.txt /opt/scaife-viewer/src/
# LOCAL CHANGE: scaife-viewer-core and scaife-viewer-atlas are vendored into
# packages/ rather than fetched from GitHub archive URLs, so their source has
# to be present before pip runs. Copied separately from the `COPY . .` in the
# webapp stage to keep this layer cached against application-code changes.
COPY packages /opt/scaife-viewer/src/packages
RUN set -x \
    && virtualenv /opt/scaife-viewer \
    && apk --no-cache add \
    build-base curl git libgcc libxml2-dev libxslt-dev postgresql-dev linux-headers python3-dev libffi-dev \
    && pip install -r requirements.txt

# LOCAL CHANGE (2026-08-14): MyCapytain declares a dependency on the
# `typing` PyPI backport, which is vestigial — the stdlib has provided
# `typing` since 3.5 — and actively harmful, because the backport
# shadows the stdlib module and breaks on modern interpreters. Removing
# it is a prerequisite for the Python upgrade.
RUN pip uninstall -y typing

# LOCAL CHANGE (2026-08-15): the urllib3 pin-back is gone. It existed
# because urllib3 2.x requires Python 3.10+ while this image was on 3.9,
# so pip resolved 2.x and it had to be forced back to 1.26.20. On Python
# 3.12 nothing caps it: opensearch-py declares urllib3<3,>=1.26.19 for
# python_version >= 3.10, and requests wants <3,>=1.26. pip now resolves
# 2.x directly and no override is needed.

# LOCAL CHANGE: the two remaining CVEs in the dependency set. Both packages
# are pinned at vulnerable versions upstream, so they are overridden here
# using the same post-install pattern as urllib3 above.
#
#   gunicorn 19.9.0 -> 23.0.0
#     CVE-2024-1135, HTTP request smuggling via Transfer-Encoding handling
#     (affects >=0.10.0,<22.0.0). 23.0.0 is the newest release supporting
#     Python 3.9 — gunicorn 26 requires 3.10+.
#
#   certifi 2018.11.29 -> 2026.7.22
#     CVE-2023-37920 (e-Tugra roots, CVSS 9.8) and CVE-2022-23491 (TrustCor),
#     both fixed in 2023.07.22. The pinned bundle was over seven years old.
#     scaife-viewer-core declares certifi==2018.11.29; pip warns about the
#     conflict and proceeds. `requests` is already overridden the same way.
# certifi no longer needs an override: the vendored core declares
# certifi>=2018.11.29 rather than ==, so pip resolves the current
# release on its own. gunicorn is pinned in requirements.txt.

# Likewise, we install PyGithub here to avoid conflicts
RUN pip install PyGithub
RUN apk add --update make automake gcc g++ subversion

# LOCAL CHANGE: kept in step with the python-build stage above.
FROM python:3.12-alpine AS webapp

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/opt/scaife-viewer/src/
ENV PATH="/opt/scaife-viewer/bin:${PATH}" VIRTUAL_ENV="/opt/scaife-viewer"

WORKDIR /opt/scaife-viewer/src/

COPY --from=python-build /opt/scaife-viewer/ /opt/scaife-viewer/
RUN set -x \
    && runDeps="$( \
    scanelf --needed --nobanner --format '%n#p' --recursive /opt/scaife-viewer \
    | tr ',' '\n' \
    | sort -u \
    | awk 'system("[ -e /usr/local/lib/" $1 " ]") == 0 { next } { print "so:" $1 }' \
    # LOCAL CHANGE: exclude sonames that are not apk packages. libgcc_s-
    # was already excluded upstream-side; libc.so joined it when newer
    # C extensions started linking it directly, and musl always
    # provides it, so `apk add so:libc.so` fails with 'no such package'.
    | grep -vE 'libgcc_s-|^so:libc\.so$' \
    )" \
    && apk --no-cache add \
    $runDeps \
    libgcc \
    curl

COPY . .

# static files must be copied after COPY . . — otherwise the latter command overwrites
# the Docker-built files with whatever exists from the last local build.
COPY --from=static-build /opt/scaife-viewer/src/static/dist /opt/scaife-viewer/src/static/dist
COPY --from=static-build /opt/scaife-viewer/src/static/stats /opt/scaife-viewer/src/static/stats

# Pre-bake ingestion sentinels when data already exists in the build context.
# Sentinels live inside atlas_data/ so they travel with the data (volume or image layer)
# rather than being lost on every container restart. The entrypoint skips expensive
# re-ingestion steps when the corresponding sentinel is present.
RUN mkdir -p atlas_data/sentinels && \
    if [ -d data/cts ] && [ "$(ls -A data/cts 2>/dev/null)" ]; then \
    sha256sum data/content-manifests/production.yaml 2>/dev/null | cut -d' ' -f1 \
    > atlas_data/sentinels/.manifest_hash; \
    touch atlas_data/sentinels/.text_repos_loaded; \
    fi && \
    if [ -f atlas_data/atlas.sqlite ]; then \
    touch atlas_data/sentinels/.atlas_db_prepared; \
    fi

# bash is needed for some of the ingestion
# scripts
RUN apk --no-cache add bash

# LOCAL CHANGE, adopted verbatim from upstream's own 3.9-based image
# (deploy/webapp/webapp-base.dockerfile): python:3.9-alpine ships a
# setuptools new enough that `pkg_resources` is gone, and django-user-accounts
# does `import pkg_resources` at module import. 81.0 still provides it.
# The root Dockerfile does not need this on 3.8; we do because we moved to 3.9.
# setuptools is pinned because `pkg_resources` was removed after 81.0.
#
# LOCAL CHANGE (2026-08-15): the vendored core and atlas used to be two of
# the three reasons for this pin; both now use importlib.metadata instead.
# What remains is exactly one unmaintained third-party package:
#
#   pinax/webanalytics/__init__.py:1: import pkg_resources
#
# It cannot simply be skipped: site_base.html loads
# `pinax_webanalytics_tags`, and importing that templatetags module
# imports its parent package. Removing this pin therefore means either
# replacing pinax-webanalytics (5.0.0, the latest, has the same line) or
# vendoring it. Tracked in SBOM-2026-08-15.md §3.
RUN pip install setuptools==81.0
RUN python manage.py collectstatic --noinput

CMD ["gunicorn", "sv_pdl.wsgi:application"]

FROM alpine AS search-annotations
ARG ANNOTATIONS_TARBALL="https://github.com/scaife-viewer/ogl-pdl-annotations/tarball/main"
RUN apk --no-cache add curl
RUN mkdir -p /opt/scaife-viewer/src/data/search-annotations
WORKDIR /opt/scaife-viewer/src/data/search-annotations
RUN curl -L $ANNOTATIONS_TARBALL -o archive.tgz && \
    tar -xf archive.tgz --strip-components=1 && \
    rm archive.tgz

FROM webapp AS search-index
COPY --from=search-annotations /opt/scaife-viewer/src/data/search-annotations /opt/scaife-viewer/src/data/search-annotations
ENV LEMMA_CONTENT=1
ENV TOKEN_ANNOTATIONS_PATH=/opt/scaife-viewer/src/data/search-annotations/data/token-annotations
