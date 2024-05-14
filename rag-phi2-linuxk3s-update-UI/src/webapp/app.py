from flask import Flask, render_template, request, redirect, url_for, session, jsonify, render_template_string
import openai
from openai import AzureOpenAI
from dotenv import load_dotenv
import os
from influxdb_client import InfluxDBClient
from influxdb_client.client.query_api import QueryOptions
import plotly.express as px
from io import BytesIO
import base64
import pandas as pd
from flask_session import Session
import redis

import pytz
import requests
import time

# Check response for up to 500/1=500 times (500sec)
CHECK_NUM = 500 
CHECK_INTERVAL_SEC = 1 
retrieval_prompt = '''Use the Content to answer the Search Query.

Search Query: 

SEARCH_QUERY_HERE

Search Content and Answer: 

'''

app = Flask(__name__)
app.secret_key = 'una_clave_secreta_muy_dificil_de_adivinar' 

load_dotenv()  # Load environment variables from .env file

# Configure session to use Redis
app.config['SESSION_TYPE'] = 'redis'
app.config['SESSION_PERMANENT'] = False  # You can set this to True if you want
app.config['SESSION_USE_SIGNER'] = True  # If you want to sign the cookie
app.config['SESSION_REDIS'] = redis.from_url("redis://10.0.0.4:6379")

Session(app)

MODEL_NAME = os.getenv("CHATGPT_MODEL")

#Classify question
client = AzureOpenAI(
  azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT"), 
  api_key=os.getenv("AZURE_OPENAI_API_KEY"),  
  api_version="2024-03-01-preview"
)

#Generate InfliuxDB query
client2 = AzureOpenAI(
  azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT"), 
  api_key=os.getenv("AZURE_OPENAI_API_KEY"),  
  api_version="2024-03-01-preview"
)

#Generate recommendations
clientRecommendations = AzureOpenAI(
  azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT"), 
  api_key=os.getenv("AZURE_OPENAI_API_KEY"),  
  api_version="2024-03-01-preview"
)

INFLUXDB_URL=os.getenv("INFLUXDB_URL")
INFLUXDB_BUCKET=os.getenv("INFLUXDB_BUCKET")
INFLUXDB_TOKEN=os.getenv("INFLUXDB_TOKEN")
INFLUXDB_ORG=os.getenv("INFLUXDB_ORG")

clientInfluxDb = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)

conversation =""

conversation=[
    {
        "role": "system",
        "content": "Assistant is an expert technical support chatbot specialized in the manufacturing sector, particularly skilled in maintenance, support, and operation of automotive assembly lines. It should answer all questions with this expertise in mind. If the assistant is unsure of an answer, it can say 'I don't know'."
    },
    {
        "role": "user",
        "content": "I am having problems with my Kuka robotic arm for car hybrid assembly line, how can I reset the system?"
    }
]

def execute_query_and_return_data(url, token, org, bucket, query):
    client = InfluxDBClient(url=url, token=token, org=org)
    query_api = client.query_api(query_options=QueryOptions(profilers=["query", "operator"]))
    #result = query_api.query(query=query)
    result = query_api.query(query=query)
    print("Query executed successfully")
 
    try:
        
        points = [point for table in result for point in table.records]
        if len(points) == 1:
            single_point = points[0]
            print("Aggregation result:", single_point.get_value())
            return single_point.get_value()
        else:
            # Múltiples puntos, manejo como serie de tiempo
            #for point in points:
            #    print(f'Time: {point.get_time()}, Value: {point.get_value()}')
            data = []
            for table in result:
                try:
                    for record in table.records:
                        data.append({
                            '_time': record.get_time(),
                            '_field': record.get_field(),
                            '_value': record.get_value()
                        })
                except Exception as e:
                    print(f"Error processing record: {e}")
                    continue  # Skip to the next record
    except Exception as e:
        print(f"Failed to execute query: {e}")
        data = result
    finally:
        client.close()

    return data

    #data = []
    #for table in result:
    #    for record in table.records:
    #        data.append({
    #            '_time': record.get_time(),
    #            '_field': record.get_field(),
    #            '_value': record.get_value()
    #        })
    #client.close()
    #return data

def clean_string(original_string):
    return original_string.replace("Output: ", "", 1)


def classify_question(question):
    categories = ["data", "documentation", "general"]
    
    prompt_text = f"For the below text, provide one single label each from the following categories:\n- Category: {', '.join(categories)}\n\nThe system should analyze the question and identify if it is related to data that could exist and get in a time series database in InfluxDB (e.g., statistics, metrics, performance, quality, telemetry, current variable values, etc.). If so, the system should respond with 'data'. If the question is related to manuals, troubleshooting, or how to solve a problem based on documents, it should respond with 'documentation'. For all other questions, the system should respond with 'general'. Examples: Question: What are the current metrics for our main system? Category: data Question: How can I troubleshoot the connection issue? Category: documentation\n\nQuestion: {question}\nCategory:"

    response = client.completions.create(
        model="gpt-35-turbo",
        prompt=prompt_text,
        temperature=0,
        max_tokens=60,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0,
        stop=["\n"]
    )

    return response.choices[0].text.strip()

def generate_recommendations(question, response, result):

    conversation=[
        {
            "role": "system",
            "content": """
            I am an agent specialized in technical support for automobile manufacturing, particularly skilled in the maintenance, support, and operation of automotive assembly lines. My role is to interpret user questions with expertise, analyze production data, and provide proactive recommendations to optimize assembly line operations. Give me the Interpretation and response, including data analysis and proactive recommendations separeted in different paragraphs. Instructions:
            1. Avoid technological terms and explanations that the solution was built with such as InfluxDb, bucket, etc, keep it like an automotive manufacturing plant manager.
            2. Format should be <B>Interpretation:</B><BR></BR>Generated text <BR></BR><B>Data Analysis:</B><BR></BR>Generated text <BR></BR><B>Proactive Recommendations:</B><BR></BR>Generated text<BR></BR>."""
            
        }
    ]

    conversation.append({"role": "user", "content": f"question: {question} and data received: {result} and row data {response}"})

    response = clientRecommendations.chat.completions.create(
            model=MODEL_NAME,
            messages=conversation
        )
    
    conversation.append({"role": "system", "content": response.choices[0].message.content})
    print(response.choices[0].message.content)

    return response.choices[0].message.content

def chat_with_openai_for_data(question):
    print("chat_with_openai_for_data")

    conversation=[
        {
            "role": "system",
            "content": """
            User submits a query regarding the manufacturing process. Generate an InfluxDB query for data from the 'manufacturing' bucket using the specified fields:
            - plant, country, assembly_line, car_id, model, color, engine_type, assembly_status, shift, Drive1_Voltage, Cooler_ON, Fan001_On, Heater_ON, Pump1_Temperature_Flow, Pump2_Temperature_Flow, Pump3_Temperature_Flow, Pumps_Total_Flow, Pressure_Filter_Inlet, Pressure_Filter_Outlet, RobotPosition_J0, RobotPosition_J1, RobotPosition_J2, RobotPosition_J3, RobotPosition_J4, RobotPosition_J5, Tank_Level, Drive1_Current, Drive1_Frequency, Drive1_Speed, Drive2_Current, Drive2_Frequency, Drive2_Speed, Drive2_Voltage, Current, Voltage, Temperature, Humidity, VacuumAlert, VacuumPressure, Oiltemperature, OiltemperatureTarget, Waste, WasteReason, LostTime, LostTimeReason, LostTimeTimeCount, ScheduledBatteries, CompletedBatteries, ScheduledBatteriesPerHour, ImpactTest, VibrationTest, CellTest, DownTime, Thruput, OverallEfficiency, Availability, Performance, Quality, PlannedProductionTime, ActualRuntime, UnplannedDowntime, PlannedDowntime, PlannedQuantity, ActualQuantity, RejectedQuantity, OEE_GoalbyPlant, OEE_Mexico, OEE_BatteryA, OEE_BatteryB, OEE_BatteryC

            Instructions:

            1. Determine if the query seeks the latest data point or spans a specific time period. Default to data from the last hour if unspecified.
            2. Construct an InfluxDB query specific to the 'manufacturing' bucket that includes ["_measurement"] == "assemblyline" and identifies the relevant _field for the query.
            3. If the query relates to real-time production line telemetry, Advaris, ODEN, QAD, or Quality cost, create the query. Otherwise, indicate "No data available."
            4. Provide the complete InfluxDB query or a statement on data availability.
            5. Just give me the query.
            6. Remove additional text such as comments # or " or ''' or ''' or ```
            Example Outputs:

            Query: "What is the latest Drive1 Speed at the Monterrey plant?"
            Output: from(bucket: "manufacturing") |> range(start: -1m) |> filter(fn: (r) => r["_measurement"] == "assemblyline") |> filter(fn: (r) => r["_field"] == "Drive1_Speed") |> last())
            Query: "Assembly statuses over the past two days?"
            Output: from(bucket: "manufacturing") |> range(start: -48h) |> filter(fn: (r) => r["_measurement"] == "assemblyline") |> filter(fn: (r) => r["_field"] == "assembly_status")
            Query: "What is the staff's favorite lunch?"
            Output: "No data available."
            """
        }
    ]

    conversation.append({"role": "user", "content": question})

    response = client2.chat.completions.create(
            model=MODEL_NAME,
            messages=conversation
        )
    
    conversation.append({"role": "system", "content": response.choices[0].message.content})
    print(response.choices[0].message.content)

    clean_response = clean_string(response.choices[0].message.content)

    #return response.choices[0].message.content
    return clean_response

def clean_string(original_string):
    clean_string = original_string.replace("```", "")
    clean_string = clean_string.replace("Output:", "")
    clean_string = clean_string.replace("Query:", "")
    return clean_string

def check_processed_result(request_id):
    check_url = f'http://rag-interface-service:8701/check_processed_result/{request_id}'
    response = requests.get(check_url)
    
    if response.status_code == 200:
        result_data = response.json()
        if result_data['status'] == 'success':
            # CC: need to replace with webapp for displaying processed_result
            #st.success(f"{result_data['processed_result']}")
            return True
    return False

def publish_user_input(user_input_json):
    backend_url = 'http://rag-interface-service:8701/webpublish'
    try:
        response = requests.post(backend_url, json=user_input_json)
        if response.status_code == 200:
            #st.success(response.json()['message'])
            request_id = response.json()['request_id']
            # Check for processed results periodically
            for _ in range(CHECK_NUM):  
                if check_processed_result(request_id):
                    break
                time.sleep(CHECK_INTERVAL_SEC)
        else:
            # CC: need to replace with webapp error message
            #st.error('Failed to publish user input to the backend')
            pass
            
    except requests.RequestException as e:
        # CC: need to replace with webapp error message
        #st.error(f'Request failed: {e}')
        pass

# CC: need to replace the below code to get Index name from webapp user input, and pass to chat_with_local_llm()
# index_names = requests.get('http://rag-vdb-service:8602/list_index_names').json()['index_names']
# index_name = st.selectbox('Please select an index name.',index_names)
# st.write('You selected:', index_name)
def chat_with_local_llm(question, index_name="test-index1"):
    #retrieval_prepped = retrieval_prompt.replace('SEARCH_QUERY_HERE',question)
    user_input_json = {'user_query': question, 'index_name': index_name}
    publish_user_input(user_input_json)

    # conversation.append({"role": "user", "content": question})

    # response = client.chat.completions.create(
    #         model=MODEL_NAME,
    #         messages=conversation
    #     )
    # #print(response.choices[0].message.content)
    # conversation.append({"role": "system", "content": response.choices[0].message.content})

    # #print(response)
    # return response.choices[0].message.content

#def fetch_graph_data(data):
#    print("fetch_graph_data")
#    raw_data = data
#    times = [data['_time'].strftime("%Y-%m-%d %H:%M:%S") for data in raw_data]
#    values = [data['_value'] for data in raw_data]
#    return times, values

def generate_html_table(data):
    
    html=""
    print("generate_html_table")
    print(data)
    if isinstance(data, float):
        return f"<B>Value is: </B> {str(data)}"
    elif isinstance(data, str):
        return f"<b>Value is: </b> {data}"
    else:
        html = '<table border="1">'
        html += '<tr><th>Time</th><th>Field</th><th>Value</th></tr>' 

        try:

            for entry in data:
                time_str = entry['_time'].strftime('%Y-%m-%d %H:%M:%S %Z') 
                field = entry['_field']
                value = entry['_value']
                html += f'<tr><td>{time_str}</td><td>{field}</td><td>{value}</td></tr>'
            html += '</table>'
        except Exception as e:
            print(f"Error generating table: {e}")

    return html

def generate_html_image(raw_data):
    print("generate_html_image")
    html =""
    try:
        data = pd.DataFrame(raw_data)
        data['_time'] = pd.to_datetime(data['_time']).dt.strftime('%Y-%m-%d %H:%M:%S %Z')
        data.rename(columns={'_field': 'Field', '_value': 'Value'}, inplace=True)
        
        # Generate the plot
        fig = px.line(data, x='_time', y='Value', title='Time Series Data', labels={'_time': 'Time', 'Value': data['Field'][0]})
        
        # Convert the figure to a PNG image byte stream
        img_bytes = fig.to_image(format="png")
        encoded = base64.b64encode(img_bytes).decode('utf-8')  # Encode the bytes to base64 and decode to a string

        # Embed the image in HTML
        html = f'''
        <br></br><b>Dynamic Graph of {data['Field'][0]}</b><br></br>
        <img src="data:image/png;base64,{encoded}">
        '''
    except Exception as e:
        print(f"Error generating image: {e}")
        html = "No image was generated."
    return html

@app.route('/', methods=['GET', 'POST'])
def home():
    return render_template('index.html')

@app.route('/handle_button_click', methods=['POST'])
def handle_button_click():
    button_id = request.form['button_id']
    recommendation = ""
    question = ""
    plot_html = ""
    response = ""
    influxquery=""

    if button_id == "btnSend":
        #question = request.form['txtQuestion']
        question = request.form.get('txtQuestion', '')
    elif button_id == "btnFAQ1":
        question = "What is the last color manufactured?"
    elif button_id == "btnFAQ2":    
        question = "Show me the Oil temperature in the past 15 minutes?"
    elif button_id == "btnFAQ3": 
        question = "What are the steps to maintain and change the oil in my kuka robotic arm?"
    elif button_id == "btnFAQ4": 
        question = "How can we fix the problem with the motor of my robotic arm? Are there any guidelines or manuals?"
    elif button_id == "btnFAQ5": 
        question = "What is the current performance of the assembly line?"
    else:
        question = "No question was found."

    user_input = question
    category = classify_question(user_input)
    verbose_mode = 'chkVerbose' in request.form

    print(verbose_mode)

    if 'history' not in session:
        session['history'] = []
        
    if category == "data":
        influxquery = chat_with_openai_for_data(user_input)
        result_data_influx = execute_query_and_return_data(INFLUXDB_URL, INFLUXDB_TOKEN, INFLUXDB_ORG, INFLUXDB_BUCKET, clean_string(influxquery))
        recommendation = generate_recommendations(user_input, influxquery, result_data_influx)
        table_html = generate_html_table(result_data_influx)
        plot_html = generate_html_image(result_data_influx)

        response = f"{ table_html }"  

    elif category == "documentation":
        response = chat_with_local_llm(user_input)  
    else:
        response = "No appropriate category was found to answer this question."
    
    svg_server = "<svg width='38' height='38'><image href='/static/images/openai.png' height='38' width='38' /></svg>"
    svg_client = "<svg width='38' height='38'><image href='/static/images/user.jpeg' height='38' width='38' /></svg>"
    
    answer = f"<BR/> {recommendation} <BR/> {plot_html} <BR/> {response}" 

    session['history'].append(f"<span class='question'><B>{svg_client} Armando Blanco - Question: {user_input} </B></span><span class='answer'> {svg_server} Cerebral - Answer {answer}</span>")
    session['last_response'] = f"{category}  -- {clean_string(influxquery)}"
    updated_history = session.get('history', [])
    last_response = f"{category}  -- {clean_string(influxquery)}"
    session['history'] = updated_history
    session['last_response'] = last_response
    return jsonify(history=updated_history, last_response=last_response)


@app.route('/reset', methods=['POST'])
def reset():
    session.pop('history', None)  # Clear chat history
    return redirect(url_for('home'))

if __name__ == '__main__':
    app.run(debug=True)
