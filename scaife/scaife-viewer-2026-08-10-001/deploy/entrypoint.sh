#!/bin/sh

SENTINEL_DIR=${ATLAS_DATA_DIR:-atlas_data}/sentinels
mkdir -p ${SENTINEL_DIR} ${CTS_LOCAL_DATA_PATH:-data/cts} ${ATLAS_DATA_DIR:-atlas_data}


die() {
    echo "entrypoint: $*" >&2
    exit 1
}

# NOTE: `makemigrations` used to run here, ahead of the migrates below.
# It was removed deliberately. Generating migrations at boot meant:
#
#   * a fresh 0002_auto_<timestamp> for localcomm/localdict on every start,
#     because their models and migrations disagreed under Django 2.2 (the
#     models declared no explicit pk, so an implicit AutoField faced a
#     BigAutoField migration). Each one carried a different timestamp, so
#     django_migrations and the files on disk permanently diverged.
#   * migrations written *into site-packages* for third-party apps —
#     django-user-accounts derives its language choices from
#     settings.LANGUAGES, so makemigrations always saw a change and wrote
#     account/migrations/0006_auto_<timestamp>.py into the dependency.
#   * `migrate` then failing with "relation ... already exists" while the
#     boot carried on regardless, because this script had no error handling.
#   * MigrationStateTests being unable to fail: any drift was absorbed into
#     a generated migration before the test could see it.
#
# Models and migrations now agree (both declare BigAutoField pks and
# explicitly named indexes), so `migrate` alone is sufficient. If a model
# changes, generate the migration deliberately and commit it:
#
#     docker exec -u scaife scaife-viewer python manage.py makemigrations <app>
#
# FIXME: (charles) I have no idea why we need to run migrate
# twice. Something is clearly wrong with what's
# going on here, but Django complains about the
# missing sites table unless we run these processes
# in this order.
python manage.py migrate || die "migrate failed"
python manage.py migrate sites || die "migrate sites failed"
python manage.py migrate --database=atlas || die "migrate --database=atlas failed"

python manage.py loaddata sites

# Re-load text repos if the content manifest has changed since last ingestion.
MANIFEST_PATH="${CONTENT_MANIFEST_PATH:-data/content-manifests/production.yaml}"
MANIFEST_HASH=$(sha256sum "${MANIFEST_PATH}" 2>/dev/null | cut -d' ' -f1 || echo "")
STORED_HASH=""
[ -f "${SENTINEL_DIR}/.manifest_hash" ] && STORED_HASH=$(cat "${SENTINEL_DIR}/.manifest_hash")

if [ ! -f "${SENTINEL_DIR}/.text_repos_loaded" ] || [ "${MANIFEST_HASH}" != "${STORED_HASH}" ]; then
    python manage.py load_text_repos
    python manage.py slim_text_repos
    echo "${MANIFEST_HASH}" > "${SENTINEL_DIR}/.manifest_hash"
    touch "${SENTINEL_DIR}/.text_repos_loaded"
    # Atlas must be rebuilt when repos change
    rm -f "${SENTINEL_DIR}/.atlas_db_prepared"
fi

if [ ! -f "${SENTINEL_DIR}/.atlas_db_prepared" ]; then
    # Upstream runs ./bin/copy_corpus_repo_metadata here, which stages
    # corpus-metadata.json for ATLAS's import_repo_metadata. That importer
    # calls api.github.com once per repo to fetch descriptions, so it is
    # skipped in this offline build: with no file staged, get_paths()
    # returns [] and the importer is a no-op. Cost is an empty repo list on
    # /about/; benefit is no network at ATLAS build time.
    python manage.py prepare_atlas_db --force && \
    touch "${SENTINEL_DIR}/.atlas_db_prepared" && \
    rm -f "${SENTINEL_DIR}/.search_indexed" # rebuild the search index when ATLAS changes
fi

# Local dictionaries (LSJ, Lewis & Short, Middle Liddell) and commentaries.
# Both read TEI/markdown from read-only bind mounts that only the local
# override provides, so skip cleanly when running under the upstream/CI
# compose files where those mounts are absent.
if [ ! -f "${SENTINEL_DIR}/.dictionaries_ingested" ] && [ -d /host-lexica ]; then
    python manage.py ingest_dictionaries && touch "${SENTINEL_DIR}/.dictionaries_ingested"
fi

if [ ! -f "${SENTINEL_DIR}/.commentaries_ingested" ] && [ -d /host-commentaries ]; then
    python manage.py ingest_commentaries && touch "${SENTINEL_DIR}/.commentaries_ingested"
fi

if [ ! -f "${SENTINEL_DIR}/.search_indexed" ]; then
    curl -X PUT "http://${SV_OPENSEARCH_HOST}:${SV_OPENSEARCH_PORT}/_template/scaife-viewer?pretty" -H 'Content-Type: application/json' -d "$(cat deploy/scaife-viewer-opensearch-template.json)"
    # Index the FULL corpus by default (SV_INDEXER_LIMIT=0 means "no
    # --limit"), matching upstream. Set SV_INDEXER_LIMIT=<N> for a fast
    # sample instead if you want the quickest possible first boot and do
    # not need working search.
    SV_INDEXER_LIMIT="${SV_INDEXER_LIMIT:-0}"
    if [ "${SV_INDEXER_LIMIT}" = "0" ]; then
        INDEXER_LIMIT_ARG=""
    else
        INDEXER_LIMIT_ARG="--limit=${SV_INDEXER_LIMIT}"
    fi
    # Worker count dominates runtime: 1 worker is roughly 10x slower.
    python manage.py indexer --max-workers="${SV_INDEXER_MAX_WORKERS:-4}" ${INDEXER_LIMIT_ARG}
    touch "${SENTINEL_DIR}/.search_indexed"
fi

exec "$@"
