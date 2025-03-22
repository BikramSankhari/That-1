FROM python:3.11.4-alpine

WORKDIR /usr/src/app

# Copy Necessary Files
COPY Code_Market/ Code_Market/
COPY Django_Img/ Django_Img/

# Install Dependencies
RUN pip install --upgrade pip
RUN pip install -r Code_Market/requirements.txt

# Set Environment Variables
# prevent Python from writing .pyc files
ENV PYTHONDONTWRITEBYTECODE=1
# ensure Python output is sent directly to the terminal without buffering
ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["./Django_Img/entrypoint.sh"]