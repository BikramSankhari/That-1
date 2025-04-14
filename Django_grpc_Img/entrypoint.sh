#!/bin/sh
cd That_1/

export $(grep -v '^#' .env | xargs)
# rm .env

python manage.py grpcrunserver --dev