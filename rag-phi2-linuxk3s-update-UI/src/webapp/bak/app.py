import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objs as go
from analyze import AnalyzeGPT, ChatGPT_Handler
import openai
from pathlib import Path
from dotenv import load_dotenv
import os
import datetime
from influxdbclient import InfluxDBAdapter

# Only load the settings if they are running local and not in Azure
if os.getenv('WEBSITE_SITE_NAME') is None:
    env_path = Path('.') / 'secrets.env'
    load_dotenv(dotenv_path=env_path)

def load_setting(setting_name, session_name,default_value=''):  
    """  
    Function to load the setting information from session  
    """  
    if session_name not in st.session_state:  
        if os.environ.get(setting_name) is not None:
            st.session_state[session_name] = os.environ.get(setting_name)
        else:
            st.session_state[session_name] = default_value  

load_setting("AZURE_OPENAI_CHATGPT_DEPLOYMENT","chatgpt","gpt-35-turbo")  

load_setting("AZURE_OPENAI_GPT4_DEPLOYMENT","gpt4","gpt-35-turbo")  
load_setting("AZURE_OPENAI_ENDPOINT","endpoint","https://resourcenamehere.openai.azure.com/")  
load_setting("AZURE_OPENAI_API_KEY","apikey")  
load_setting("INFLUXDB_SERVER_URL","influxdbserverurl")
load_setting("INFLUXDB_ORG","influxdborg")
load_setting("INFLUXDB_BUCKET","influxdbbucket")
load_setting("INFLUXDB_USER","influxdbuser")
load_setting("INFLUXDB_TOKEN","influxdbtoken")

if 'show_settings' not in st.session_state:  
    st.session_state['show_settings'] = False  

def saveOpenAI():
    st.session_state.chatgpt = st.session_state.txtChatGPT
    st.session_state.gpt4 = st.session_state.txtGPT4
    st.session_state.endpoint = st.session_state.txtEndpoint
    st.session_state.apikey = st.session_state.txtAPIKey
    st.session_state.influxdbserverurl = st.session_state.txtinfluxdbserverurl
    st.session_state.influxdborg = st.session_state.txtinfluxdborg
    st.session_state.influxdbbucket = st.session_state.txtinfluxdbbucket
    st.session_state.influxdbuser = st.session_state.txtinfluxdbuser
    st.session_state.influxdbtoken = st.session_state.txtinfluxdbtoken

    # We can close out the settings now
    st.session_state['show_settings'] = False

def toggleSettings():
    st.session_state['show_settings'] = not st.session_state['show_settings']

openai.api_type = "azure"
openai.api_version = "2023-07-01-preview" #"2023-03-15-preview" 
openai.api_key = st.session_state.apikey
openai.api_base = st.session_state.endpoint
max_response_tokens = 1250
token_limit= 4096
temperature=0

st.set_page_config(page_title="Natural Language Query", page_icon=":memo:", layout="wide")

col1, col2  = st.columns((3,1)) 

with st.sidebar:  
    system_message="""
    You are a smart AI assistant to help answer business questions based on analyzing data. 
    You can plan solving the question with one more multiple thought step. At each thought step, 
    you can write python code to analyze data to assist you. Observe what you get at each step to plan for the next step.
    You are given following utilities to help you retrieve data and commmunicate your result to end user.
    1. execute_influxquery(flux_query: str): A Python function can query data from the <<data_sources>> given a query 
    which you need to create. The query has to be syntactically correct for Open source InfluxDB and only use 
    bucket, measurements, fields and tags under <<data_sources>>. 
    The execute_influxquery function returns a Python pandas dataframe containing the results of the query.
    2. Use plotly library for data visualization. 
    3. Use observe(label: str, data: any) utility function to observe data under the label for your evaluation. 
    Use observe() function instead of print() as this is executed in streamlit environment. 
    Due to system limitation, you will only see the first 10 rows of the dataset.
    4. To communicate with user, use show() function on data, text and plotly figure. show() is a utility function 
    that can render different types of data to end user. Remember, you don't see data with show(), only user does. 
    You see data with observe()
        - If you want to show  user a plotly visualization, then use ```show(fig)`` 
        - If you want to show user data which is a text or a pandas dataframe or a list, use ```show(data)```
        - Never use print(). User don't see anything with print()
    5. Don't forget to deal with data quality problem. You should apply data imputation technique to deal with missing data or NAN data.
    6. The query output from InfluxDB always contains time in the column _time
    7. When you query a field from InfluxDB, the value of the field is always in the column _value and this should be referred in the pandas dataframe as df['_value']
    8. When the query contains count or sum, the value of the count or sum is always in the column _value and this should be referred in the pandas dataframe as df['_value']
    9. Always follow the flow of Thought: , Observation:, Action: and Answer: as in template below strictly. 

    """

    few_shot_examples="""
    <<Template>>
    Question: User Question
    Thought 1: Your thought here.
    Action: 
    ```python
    #Import neccessary libraries here
    import numpy as np
    #Query some data 
    flux_query = "SOME FLUX QUERY"
    step1_df = execute_influxquery(flux_query)
    # Replace NAN with 0. Always have this step
    step1_df['Some_Column'] = step1_df['Some_Column'].replace(np.nan,0)
    #observe query result
    observe("some_label", step1_df) #Always use observe() instead of print
    ```
    Observation: 
    step1_df is displayed here
    Thought 2: Your thought here
    Action:  
    ```python
    import plotly.express as px 
    #from step1_df, perform some data analysis action to produce step2_df
    #To see the data for yourself the only way is to use observe()
    observe("some_label", step2_df) #Always use observe() 
    #Decide to show it to user.
    fig=px.line(step2_df)
    #visualize fig object to user.  
    show(fig)
    #you can also directly display tabular or text data to end user.
    show(step2_df)
    ```
    Observation: 
    step2_df is displayed here
    Answer: Your final answer and comment for the question. Also use Python for computation, never compute result youself.
    <</Template>>

    <<Flux query examples>>
    # Count anomalies in the last 30 minutes for line FM407
        from(bucket: "flowermound")
        |> range(start: -30m)
        |> filter(fn: (r) => r["_measurement"] == "anomalies")
        |> filter(fn: (r) => r["_field"] == "anomalyscore")
        |> filter(fn: (r) => r._value < 0)
        |> filter(fn: (r) => r["line"] == v.line)
        |> count()
        |> yield(name: "count")


    """

    extract_patterns=[("Thought:",r'(Thought \d+):\s*(.*?)(?:\n|$)'), ('Action:',r"```python\n(.*?)```"),("Answer:",r'([Aa]nswer:) (.*)')]
    extractor = ChatGPT_Handler(extract_patterns=extract_patterns)
    faq_dict = {  
        "ChatGPT": [  
            "Show me anomalies in the last 30 minutes for line FM407",  
            "How often are the anomalies happening in the last 30 minutes for all lines?",  
            "Which lines have the most anomalies",  
            "Predict when might be the next anomaly for line FM407. Do not use Prophet. Show the prediction in a chart together with historical data for comparison."
        ],  
        "GPT-4": [  
            "Predict monthly revenue for next 6 months starting from June-2018. Do not use Prophet. Show the prediction in a chart together with historical data for comparison." 
        ]  
    }  

    st.button("Settings",on_click=toggleSettings)
    if st.session_state['show_settings']:  
        # with st.expander("Settings",expanded=expandit):
        with st.form("AzureOpenAI"):
            st.title("Azure OpenAI Settings")
            st.text_input("ChatGPT deployment name:", value=st.session_state.chatgpt,key="txtChatGPT")  
            st.text_input("GPT-4 deployment name (if not specified, default to ChatGPT's):", value=st.session_state.gpt4,key="txtGPT4") 
            st.text_input("Azure OpenAI Endpoint:", value=st.session_state.endpoint,key="txtEndpoint")  
            st.text_input("Azure OpenAI Key:", value=st.session_state.apikey, type="password",key="txtAPIKey")

            st.title("InfluxDB Settings")
            st.text_input("Server Url:", value=st.session_state.influxdbserverurl,key="txtinfluxdbserverurl")
            st.text_input("Org:", value=st.session_state.influxdborg,key="txtinfluxdborg")
            st.text_input("Bucket:", value=st.session_state.influxdbbucket,key="txtinfluxdbbucket")
            st.text_input("User:", value=st.session_state.influxdbuser,key="txtinfluxdbuser")  
            st.text_input("Token:", type="password",value=st.session_state.influxdbtoken,key="txtinfluxdbtoken")

            st.form_submit_button("Submit",on_click=saveOpenAI)


    chat_list=[]
    if st.session_state.chatgpt != '':
        chat_list.append("ChatGPT")
    if st.session_state.gpt4 != '':
        chat_list.append("GPT-4")
    gpt_engine = st.selectbox('GPT Model', chat_list)  
    if gpt_engine == "ChatGPT":  
        gpt_engine = st.session_state.chatgpt  
        faq = faq_dict["ChatGPT"]  
    else:  
        gpt_engine = st.session_state.gpt4
        faq = faq_dict["GPT-4"]  
    
    option = st.selectbox('FAQs',faq)  

    show_code = st.checkbox("Show code", value=False)  
    show_prompt = st.checkbox("Show prompt", value=False)
    # step_break = st.checkbox("Break at every step", value=False)  
    question = st.text_area("Ask me a question", option)

    influxdbadapter = InfluxDBAdapter(  url=st.session_state.influxdbserverurl, 
                                        token=st.session_state.influxdbtoken, 
                                        org=st.session_state.influxdborg, 
                                        bucket=st.session_state.influxdbbucket)
    influxdbadapter.connect()
  
    if st.button("Submit"):  
        print("Submit clicked")
        analyzer = AnalyzeGPT(
                                content_extractor= extractor, 
                                flux_query_tool=influxdbadapter,  
                                system_message=system_message, 
                                few_shot_examples=few_shot_examples,
                                st=st,  
                                gpt_deployment=gpt_engine,
                                max_response_tokens=max_response_tokens,
                                token_limit=token_limit,  
                                temperature=temperature
                            )  
        analyzer.run(question,show_code,show_prompt, col1)  

        # else:
        #     for key in st.session_state.keys():
        #         if ("AZURE_OPENAI" not in key )and ("settings" not in key) and ("SQL" not in key) : 
        #             del st.session_state[key]  

 
