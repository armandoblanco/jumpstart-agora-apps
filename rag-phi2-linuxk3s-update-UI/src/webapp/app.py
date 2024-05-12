from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import openai
from openai import AzureOpenAI
from dotenv import load_dotenv
import os
from influxdb_client import InfluxDBClient
from influxdb_client.client.query_api import QueryOptions
from tabulate import tabulate
import pytz

app = Flask(__name__)
app.secret_key = 'una_clave_secreta_muy_dificil_de_adivinar'  


load_dotenv()  # Load environment variables from .env file

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
        "content": "I am having problems with my Kuka roboric arm for car hybrid assembly line, how can I reset the system?"
    }
]

def execute_query_and_return_data(url, token, org, bucket, query):
    client = InfluxDBClient(url=url, token=token, org=org)
    query_api = client.query_api(query_options=QueryOptions(profilers=["query", "operator"]))
    result = query_api.query(query=query)
    data = []
    for table in result:
        for record in table.records:
            data.append({
                '_time': record.get_time(),
                '_field': record.get_field(),
                '_value': record.get_value()
            })
    
    client.close()
    return data

def clean_string(original_string):
    return original_string.replace("Output: ", "", 1)

def get_influx_data(field):
    
    try:
        query = """
        from(bucket: "manufacturing")
        |> range(start: -1h)
        |> filter(fn: (r) => r["_measurement"] == "assemblyline")
        |> filter(fn: (r) => r["_field"] == "Performance" )

        """
        print("get_influx_data")
        result = clientInfluxDb.query_api().query(query=query, org=INFLUXDB_ORG)
        print(result)
        data = []
        for table in result:
            for record in table.records:
                data.append((record.get_time(), record.get_value()))

        #print(data)
        return data
    except Exception as e:
        print(f"Error retrieving InfluxDB data: {str(e)}")
        return []

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

def get_chart_script():

    js_script = ""
    field = "Performance"
    result = get_influx_data(field)
    if result:
        times = [r[0].isoformat() for r in result]  # Convierte datetime a string ISO
        #times = [r[0] for r in result]  # Convierte datetime a string ISO
        values = [r[1] for r in result]

        #print(times)
        #print(values)

        js_script = f"""
             var myChart;
            document.addEventListener('DOMContentLoaded', function () {{
                var ctx = document.getElementById('influxChart').getContext('2d');
                myChart = new Chart(ctx, {{
                    type: 'line',
                    data: {{
                        labels: {times},
                        datasets: [{{
                            label: '{field}',
                            backgroundColor: 'rgba(255, 99, 132, 0.2)',
                            borderColor: 'rgba(255, 99, 132, 1)',
                            data: {values}
                        }}]
                    }},
                    options: {{
                        scales: {{
                            y: {{
                                beginAtZero: true
                            }}
                        }}
                    }}
                }});
            }});
        """
       
        js_script1 = f"""
         var myChart;
        document.addEventListener('DOMContentLoaded', function () {{
            var ctx = document.getElementById('influxChart').getContext('2d');
            myChart = new Chart(ctx, {{
                type: 'line',
                data: {{
                    labels: {times},
                    datasets: [{{
                        label: 'Valores de InfluxDB',
                        backgroundColor: 'rgba(255, 99, 132, 0.2)',
                        borderColor: 'rgba(255, 99, 132, 1)',
                        data: {values}
                    }}]
                }},
                options: {{
                    scales: {{
                        y: {{
                            beginAtZero: true
                        }},
                        x: {{
                            type: 'time',
                            time: {{
                                unit: 'minute'
                            }},
                            displayFormats: {{
                                minute: 'HH:mm'
                            }}
                        }}
                    }}
                }}
            }});
        }});
        """
        #print(js_script)
    else:
        return ""
    return js_script

def generate_recommendations(question, response):

    conversation=[
        {
            "role": "system",
            "content": """
            I am an agent specialized in technical support for automobile manufacturing, particularly skilled in the maintenance, support, and operation of automotive assembly lines. My role is to interpret user questions with expertise, analyze production data, and provide proactive recommendations to optimize assembly line operations. Give me the Interpretation and response, including data analysis and proactive recommendations separeted in different paragraphs. Instructions:
            1. Format should be <B>Interpretation:</B><BR/>Generated text <BR/><B>Data Analysis:</B><BR/>Generated text <BR/><B>Proactive Recommendations:</B><BR/>Generated text<BR/>."""
        }
    ]

    conversation.append({"role": "user", "content": f"question: {question} and data received: {response}"})

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

    return response.choices[0].message.content

def chat_with_local_llm(question):
    conversation.append({"role": "user", "content": question})

    response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=conversation
        )
    #print(response.choices[0].message.content)
    conversation.append({"role": "system", "content": response.choices[0].message.content})

    #print(response)
    return response.choices[0].message.content

def fetch_graph_data(data):
    raw_data = data
    times = [data['_time'].strftime("%Y-%m-%d %H:%M:%S") for data in raw_data]
    values = [data['_value'] for data in raw_data]
    return times, values

def generate_html_table(data):
    
    html = '<table border="1">'
    html += '<tr><th>Time</th><th>Field</th><th>Value</th></tr>' 

    for entry in data:
        time_str = entry['_time'].strftime('%Y-%m-%d %H:%M:%S %Z') 
        field = entry['_field']
        value = entry['_value']
        html += f'<tr><td>{time_str}</td><td>{field}</td><td>{value}</td></tr>'
    
    html += '</table>'
    return html

@app.route('/', methods=['GET', 'POST'])
def home():

    #Initial chart
    try:
        js_script = get_chart_script()
    except Exception as e:
        print(f"Error generating chart script: {str(e)}")
        js_script = ""

    #Question
    if request.method == 'POST':
        user_input = request.form['txtQuestion']
        category = classify_question(user_input)
        verbose_mode = 'chkVerbose' in request.form

        print(verbose_mode)

        if 'history' not in session:
            session['history'] = []
        
        if category == "data":
            response = chat_with_openai_for_data(user_input)  
        elif category == "documentation":
            response = chat_with_local_llm(user_input)  
        else:
            response = "No appropriate category was found to answer this question."
        
        session['history'].append(f"<span class='question'>Question: {user_input} </span><span class='answer'>Answer: {response}</span>")
        session['last_response'] = category
    else:
        session['last_response'] = ""
    
    return render_template('index.html', history=session.get('history', []), last_response=session.get('last_response', 'Type of Question:'), js_script=js_script)

@app.route('/handle_button_click', methods=['POST'])
def handle_button_click():
    button_id = request.form['button_id']
    recommendation = ""
    question = ""

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
        response = chat_with_openai_for_data(user_input)

        result = execute_query_and_return_data(INFLUXDB_URL, INFLUXDB_TOKEN, INFLUXDB_ORG, INFLUXDB_BUCKET, clean_string(response))

        recommendation = generate_recommendations(user_input, response)
        
        times, values = fetch_graph_data(result)
        
        table_html = generate_html_table(result)

        print(result)

        response = f"Query: {clean_string(response)}\n\n{ table_html }"  

    elif category == "documentation":
        response = chat_with_local_llm(user_input)  
    else:
        response = "No appropriate category was found to answer this question."
    
    svg_server = "<svg width='38' height='38'><image href='/static/images/openai.png' height='38' width='38' /></svg>"
    svg_client = "<svg width='38' height='38'><image href='/static/images/user.jpeg' height='38' width='38' /></svg>"

    answer = f"{response} <BR/> {recommendation}" 

    session['history'].append(f"<span class='question'>{svg_client} Question: {user_input} </span><span class='answer'> {svg_server} Answer: {answer}</span>")
    session['last_response'] = category
    
    #updated_history = session.get('history', []) + ["Nueva entrada debido a: " + button_id]
    updated_history = session.get('history', [])
    last_response = category
    
    session['history'] = updated_history
    session['last_response'] = last_response
    return jsonify(history=updated_history, last_response=last_response)

    

    

@app.route('/reset', methods=['POST'])
def reset():
    session.pop('history', None)  # Clear chat history
    return redirect(url_for('home'))

if __name__ == '__main__':
    app.run(debug=True)
