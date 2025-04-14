#!/bin/sh
cd That_1/

export $(grep -v '^#' .env | xargs)
# rm .env

python manage.py makemigrations
python manage.py migrate
python manage.py runserver 0.0.0.0:8000