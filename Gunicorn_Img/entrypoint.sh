#!/bin/sh
cd That_1/

export $(grep -v '^#' .env | xargs)

gunicorn --bind 0.0.0.0:8000 That_1.wsgi