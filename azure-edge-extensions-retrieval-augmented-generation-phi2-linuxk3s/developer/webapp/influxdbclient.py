from influxdb_client import InfluxDBClient
from influxdb_client import InfluxDBClient, Point, WriteOptions
from influxdb_client.client.write_api import SYNCHRONOUS
import pandas as pd
import datetime 
import json
import warnings
from influxdb_client.client.warnings import MissingPivotFunction

warnings.simplefilter("ignore", MissingPivotFunction)

class InfluxDBAdapter:
    def __init__(self,url, token, org, bucket) -> None:
        self.bucket = bucket
        self.org = org
        self.token = token
        self.url = url
        self.client = None

    def connect(self):
        self.client = InfluxDBClient(url=self.url, token=self.token, org=self.org)
        self.write_api = self.client.write_api(write_options=SYNCHRONOUS)
        #self.query_api = self.client.query_api()


    def execute_influxquery(self, flux_query):
        print("-=====",flux_query)
        #response = self.client.query_api.query(org=self.org, query=flux_query)
        tables = self.client.query_api().query(org=self.org, query=flux_query)

        output = tables.to_json(indent=5)
        df = self.client.query_api().query_data_frame(org=self.org, query=flux_query)
        return df
