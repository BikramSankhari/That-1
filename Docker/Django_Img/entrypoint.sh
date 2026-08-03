#!/bin/sh
cd That_1/

# rm .env
python manage.py makemigrations
python manage.py migrate

python -m Auth.server