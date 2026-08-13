#!/bin/sh

SENTINEL_DIR=/sv-data/sentinels
mkdir -p ${CTS_LOCAL_DATA_PATH} ${SENTINEL_DIR} ${ATLAS_DATA_DIR:-atlas_data}

python manage.py migrate
python manage.py loaddata sites
python manage.py makemigrations

if [ ! -f ${SENTINEL_DIR}/.text_repos_loaded ]; then
    python manage.py load_text_repos
    python manage.py slim_text_repos
    touch ${SENTINEL_DIR}/.text_repos_loaded
fi

if [ ! -f ${SENTINEL_DIR}/.atlas_db_prepared ]; then
    python manage.py prepare_atlas_db --force
    touch ${SENTINEL_DIR}/.atlas_db_prepared
fi

# Local dictionaries (LSJ, Lewis & Short, Middle Liddell) and commentaries.
# Both read TEI/markdown from read-only bind mounts that only the local
# override provides, so skip cleanly when running under the upstream/CI
# compose files where those mounts are absent.
if [ ! -f ${SENTINEL_DIR}/.dictionaries_ingested ] && [ -d /host-lexica ]; then
    python manage.py ingest_dictionaries && touch ${SENTINEL_DIR}/.dictionaries_ingested
fi

if [ ! -f ${SENTINEL_DIR}/.commentaries_ingested ] && [ -d /host-commentaries ]; then
    python manage.py ingest_commentaries && touch ${SENTINEL_DIR}/.commentaries_ingested
fi

if [ ! -f ${SENTINEL_DIR}/.es_indexed ]; then
    curl -X PUT "http://${SV_ELASTICSEARCH_HOST}:${SV_ELASTICSEARCH_PORT}/_template/scaife-viewer?pretty" -H 'Content-Type: application/json' -d "$(cat deploy/scaife-viewer-es-template.json)"
    # --limit caps how many passages are indexed. The default of 1000 is a
    # small sample of the corpus (fast first boot, but most texts are then
    # unsearchable). Set SV_INDEXER_LIMIT=0 to index everything — correct
    # but slow, on the order of hours.
    SV_INDEXER_LIMIT="${SV_INDEXER_LIMIT:-1000}"
    if [ "${SV_INDEXER_LIMIT}" = "0" ]; then
        INDEXER_LIMIT_ARG=""
    else
        INDEXER_LIMIT_ARG="--limit=${SV_INDEXER_LIMIT}"
    fi
    python manage.py indexer --max-workers="${SV_INDEXER_MAX_WORKERS:-1}" ${INDEXER_LIMIT_ARG}
    touch ${SENTINEL_DIR}/.es_indexed
fi

exec "$@"
