#!/bin/sh

echo "Waiting for postgres..."

while ! nc -z $SV_POSTGRES_HOST $SV_POSTGRES_PORT; do
  sleep 0.1
done
echo "PostgreSQL started"

if [ "$USE_OPENSEARCH_SERVICE" = "1" ]
then
  echo "Waiting for opensearch..."
  while ! nc -z $SV_OPENSEARCH_HOST $SV_OPENSEARCH_PORT; do
    sleep 0.1
  done

  # wait until the nodes endpoint comes online
  until $(curl --output /dev/null --silent http://$SV_OPENSEARCH_HOST:$SV_OPENSEARCH_PORT/_nodes/_all/http); do
    sleep 1
  done
  echo "opensearch started"
fi

echo "Running migrations"
python manage.py makemigrations
python manage.py migrate


exec "$@"
