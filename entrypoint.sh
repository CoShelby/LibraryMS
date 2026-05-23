#!/bin/bash
set -e

echo "Waiting for database..."
python manage.py wait_for_db

echo "Running database migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Creating superuser if it does not exist..."
python manage.py create_admin_user

echo "Starting Gunicorn..."
exec gunicorn libraryms.wsgi:application --bind 0.0.0.0:8000 --workers 3
