

sudo docker login $ACR -u $ACRUSER -p $ACRPWD
sudo docker build -t $CONTAINER .
sudo docker tag $CONTAINER $ACR/$CONTAINER
sudo docker push $ACR/$CONTAINER


sudo docker run -d -p 5001:5000 \
  -e AZURE_OPENAI_API_KEY=<KEY> \
  -e CHATGPT_MODEL=gpt-35-turbo \
  -e AZURE_OPENAI_ENDPOINT=https://hmidemo-openai.openai.azure.com \
  -e OPENAI_API_VERSION=2024-03-01-preview \
  -e INFLUXDB_URL=http://10.0.0.4:8086 \
  -e INFLUXDB_BUCKET=manufacturing \
  -e INFLUXDB_TOKEN=secret-token \
  -e INFLUXDB_ORG=InfluxData \
  -e REDIS_URL=redis://10.0.0.4:6379 \
  agoraarmbladev.azurecr.io/rag-on-edge-cerebral:1.6
