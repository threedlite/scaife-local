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
FROM python:3.9-alpine AS python-build
WORKDIR /opt/scaife-viewer/src/
RUN pip --no-cache-dir --disable-pip-version-check install virtualenv
ENV PATH="/opt/scaife-viewer/bin:${PATH}" VIRTUAL_ENV="/opt/scaife-viewer"
COPY requirements.txt /opt/scaife-viewer/src/
RUN set -x \
    && virtualenv /opt/scaife-viewer \
    && apk --no-cache add \
    build-base curl git libgcc libxml2-dev libxslt-dev postgresql-dev linux-headers python3-dev libffi-dev \
    && pip install -r requirements.txt

# We need to uninstall and reinstall urllib3 manually
# to avoid conflicts
RUN pip uninstall -y urllib3
# LOCAL CHANGE: upstream pins 1.26.15, which is vulnerable to
#   CVE-2023-43804 (Cookie header leaked on cross-origin redirect, fixed 1.26.17)
#   CVE-2023-45803 (request body retained on 303 redirect,        fixed 1.26.18)
#   CVE-2024-37891 (Proxy-Authorization leaked on redirect,       fixed 1.26.19)
# 1.26.20 is the final release of the 1.26.x line and fixes all three. We stay
# on 1.26.x rather than 2.x because upstream pins here deliberately to avoid
# resolver conflicts, and because urllib3 2.7 requires Python 3.10+ while this
# image is Python 3.9. Revisit if the interpreter is upgraded.
RUN pip install urllib3==1.26.20

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
RUN pip install gunicorn==23.0.0 certifi==2026.7.22

# Likewise, we install PyGithub here to avoid conflicts
RUN pip install PyGithub
RUN apk add --update make automake gcc g++ subversion

# LOCAL CHANGE: kept in step with the python-build stage above.
FROM python:3.9-alpine AS webapp

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
    | grep -v 'libgcc_s-' \
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
