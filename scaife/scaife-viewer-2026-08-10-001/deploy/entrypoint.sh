#!/bin/sh

SENTINEL_DIR=${ATLAS_DATA_DIR:-atlas_data}/sentinels
mkdir -p ${SENTINEL_DIR} ${CTS_LOCAL_DATA_PATH:-data/cts} ${ATLAS_DATA_DIR:-atlas_data}


# FIXME: (charles) I have no idea why we need to run migrate
# twice. Something is clearly wrong with what's
# going on here, but Django complains about the
# missing sites table unless we run these processes
# in this order.
python manage.py makemigrations
python manage.py migrate
python manage.py migrate sites
python manage.py migrate --database=atlas

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
    rm -f "${SENTINEL_DIR}/.es_indexed" # rebuild ES index when ATLAS changes
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

if [ ! -f "${SENTINEL_DIR}/.es_indexed" ]; then
    curl -X PUT "http://${SV_ELASTICSEARCH_HOST}:${SV_ELASTICSEARCH_PORT}/_template/scaife-viewer?pretty" -H 'Content-Type: application/json' -d "$(cat deploy/scaife-viewer-es-template.json)"
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
    touch "${SENTINEL_DIR}/.es_indexed"
fi

exec "$@"
