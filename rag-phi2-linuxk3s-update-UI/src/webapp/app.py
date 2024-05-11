from flask import Flask, render_template, request, redirect, url_for, session
import openai
from openai import AzureOpenAI
from dotenv import load_dotenv
import os
from influxdb_client import InfluxDBClient

app = Flask(__name__)
app.secret_key = 'una_clave_secreta_muy_dificil_de_adivinar'  


load_dotenv()  # Load environment variables from .env file

MODEL_NAME = os.getenv("CHATGPT_MODEL")

client = AzureOpenAI(
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


def get_influx_data(field):
    #return [list(range(10)), [x**2 for x in range(10)]]
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
    #return [list(range(10)), [x**2 for x in range(10)]]

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

def chat_with_openai_for_data(question):
    print("chat_with_openai_for_data")
    instructions = """
    The user submits a query regarding the manufacturing process. Based on the query, generate an InfluxDB query for data from the 'manufacturing' bucket, considering the following data fields:
    - Plant, Country, Assembly Line, Car ID, Model, Color, Engine Type, Assembly Status, Shift
    - Drive1 Voltage, Drive2 Voltage, Current, Voltage, Temperature, Humidity
    - Cooler ON, Fan001 On, Heater ON, VacuumAlert
    - Pump1 Temperature Flow, Pump2 Temperature Flow, Pump3 Temperature Flow, Pumps Total Flow
    - Pressure Filter Inlet, Pressure Filter Outlet
    - RobotPosition J0 to J5
    - Tank Level, Drive1 Current, Drive1 Frequency, Drive1 Speed
    - Drive2 Current, Drive2 Frequency, Drive2 Speed
    - Vacuum Pressure, Oil Temperature, Oil Temperature Target
    - Waste, Waste Reason, Lost Time, Lost Time Reason, Lost Time Time Count
    - Scheduled Batteries, Completed Batteries, Scheduled Batteries Per Hour
    - Impact Test, Vibration Test, Cell Test, Down Time, Thruput, Overall Efficiency, Availability, Performance, Quality
    - Planned Production Time, Actual Runtime, Unplanned Downtime, Planned Downtime
    - Planned Quantity, Actual Quantity, Rejected Quantity
    - OEE Goal by Plant, OEE Mexico, OEE Battery A, OEE Battery B, OEE Battery C

    User Query: "{question}"

    Instructions:
    1. Determine if the query seeks the latest data point or data over a specific time period. If unspecified, default to data from the last hour.
    2. Construct an InfluxDB query specific to the 'manufacturing' bucket that addresses the user's request.
    3. If the query relates to real-time production line telemetry, Advaris, ODEN, QAD, or Quality cost, construct the query. Otherwise, indicate "No data available."
    4. Provide the complete InfluxDB query or a response indicating data availability based on the query content.

    Example Outputs:
    - If the query is: "What is the latest Drive1 Voltage at the Monterrey plant?"
    Output: "from(bucket: 'manufacturing') |> range(start: -1m) |> filter(fn: (r) => r._measurement == 'Drive1_Voltage' and r.plant == 'Monterrey')"
    - If the query asks for: "Assembly statuses over the past two days?"
    Output: "from(bucket: 'manufacturing') |> range(start: -48h) |> filter(fn: (r) => r._measurement == 'assembly_status')"
    - If the query is unrelated: "What is the staff's favorite lunch?"
    Output: "No data available."

    """
    response = client.completions.create(
        model="gpt-35-turbo",
        prompt=instructions,
        temperature=0,
        max_tokens=60,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0,
        stop=["\n"]
    )

    print( response.choices[0].text.strip())

    return response.choices[0].text.strip()

    #conversation.append({"role": "user", "content": question})

    #response = client.chat.completions.create(
    #        model=MODEL_NAME,
    #        messages=conversation
    #    )
    
    #conversation.append({"role": "system", "content": response.choices[0].message.content})
    #print(response.choices[0].message.content)

    return "" #response.choices[0].message.content

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
        if 'history' not in session:
            session['history'] = []
        
        if category == "data":
            response = chat_with_openai_for_data(user_input)  
        elif category == "documentation":
            response = chat_with_local_llm(user_input)  
        else:
            response = "No appropriate category was found to answer this question."
        
        session['history'].append(f"Q: {user_input} - A: {response}")
        session['last_response'] = category
    else:
        session['last_response'] = ""
    
    return render_template('index.html', history=session.get('history', []), last_response=session.get('last_response', 'Type of Question:'), js_script=js_script)


@app.route('/reset', methods=['POST'])
def reset():
    session.pop('history', None)  # Clear chat history
    return redirect(url_for('home'))

if __name__ == '__main__':
    app.run(debug=True)
