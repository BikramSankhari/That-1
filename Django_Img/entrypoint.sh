#!/bin/sh
cd Code_Market/

export $(grep -v '^#' .env | xargs)
# rm .env

python3 manage.py makemigrations
python3 manage.py migrate
python3 manage.py runserver 0.0.0.0:8000