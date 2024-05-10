#Import necessary libraries
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objs as go
from statsmodels.tsa.arima.model import ARIMA
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from influxdbclient import InfluxDBAdapter

#Query data for line FM407 from the anomalies bucket
flux_query = '''
from(bucket: "flowermound")
|> range(start: -30d)
|> filter(fn: (r) => r["_measurement"] == "sensordata")
|> filter(fn: (r) => r["line"] == "FM407")
|> keep(columns: ["_time", "_value"])
|> sort(columns: ["_time"], desc: false)
'''

influxdbadapter = InfluxDBAdapter(  url="http://10.0.0.29:8086", 
                                    token="my-super-secret-auth-token", 
                                    org="mythical", 
                                    bucket="flowermound")

influxdbadapter.connect()

df = influxdbadapter.execute_influxquery(flux_query)

#Replace NAN with 0
df['_value'] = df['_value'].replace(np.nan,0)

#Convert _time column to datetime format
df['_time'] = pd.to_datetime(df['_time'])

#Set _time column as index
df.set_index('_time', inplace=True)

print(df)

#Split data into train and test sets
train_size = int(len(df) * 0.8)
train, test = df.iloc[:train_size], df.iloc[train_size:]

#Fit ARIMA model to training data
model = ARIMA(train, order=(1,1,1))
model_fit = model.fit()

#Make predictions on test data
predictions = model_fit.forecast(steps=len(test))

#Combine predictions with actual values
results = pd.concat([test, predictions], axis=1)
results.columns = ['Actual', 'Predicted']

#Plot actual and predicted values
fig = go.Figure()
fig.add_trace(go.Scatter(x=results.index, y=results['Actual'], name='Actual'))
fig.add_trace(go.Scatter(x=results.index, y=results['Predicted'], name='Predicted'))
fig.update_layout(title='Actual vs Predicted Anomalies for Line FM407')
show(fig)