from flask import Flask, render_template, request, redirect, url_for, session
import openai
from openai import AzureOpenAI
from dotenv import load_dotenv
import os

app = Flask(__name__)
app.secret_key = 'una_clave_secreta_muy_dificil_de_adivinar'  


load_dotenv()  # Load environment variables from .env file

MODEL_NAME = os.getenv("CHATGPT_MODEL")

client = AzureOpenAI(
  azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT"), 
  api_key=os.getenv("AZURE_OPENAI_API_KEY"),  
  api_version="2024-03-01-preview"
)

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

def chat_with_openai_for_data(question):

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
    
    return render_template('index.html', history=session.get('history', []), last_response=session.get('last_response', 'Type of Question:'))


@app.route('/reset', methods=['POST'])
def reset():
    session.pop('history', None)  # Clear chat history
    return redirect(url_for('home'))

if __name__ == '__main__':
    app.run(debug=True)
