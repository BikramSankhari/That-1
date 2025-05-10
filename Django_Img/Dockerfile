FROM python:3.13-alpine

WORKDIR /usr/src/app

# Copy Necessary Files
COPY That_1/ That_1/
COPY Django_Img/ Django_Img/

# Set Environment Variables
# prevent Python from writing .pyc files
ENV PYTHONDONTWRITEBYTECODE=1
# ensure Python output is sent directly to the terminal without buffering
ENV PYTHONUNBUFFERED=1
ENV PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python

# Install Dependencies
RUN pip install --upgrade pip
RUN pip install -r That_1/requirements.txt

ENTRYPOINT ["./Django_Img/entrypoint.sh"]