#!/bin/sh
cd That_1/

export $(grep -v '^#' .env | xargs)
# rm .env

python3 manage.py makemigrations
python3 manage.py migrate
python3 manage.py runserver 0.0.0.0:8000