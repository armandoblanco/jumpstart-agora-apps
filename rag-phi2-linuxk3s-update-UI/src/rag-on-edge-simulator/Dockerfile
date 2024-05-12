# Use a base Python image
FROM python:3.12-slim

# Copy application files to the container
COPY . /app

# Set the working directory
WORKDIR /app

# Install dependencies
RUN pip install paho-mqtt
RUN pip install influxdb-client


#ENV MQTT_BROKER="10.211.55.5"
#ENV MQTT_PORT=1883
#ENV FRECUENCY=10

# Command to run the application
CMD ["python", "app.py"]