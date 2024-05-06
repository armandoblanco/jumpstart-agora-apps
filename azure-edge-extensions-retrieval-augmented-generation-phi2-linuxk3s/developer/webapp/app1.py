from flask import Flask, request, jsonify
import openai

app = Flask(__name__)

# Configure your OpenAI key here
openai.api_key = "38d82ccac49149e49367fc5329f1c84d"

@app.route('/analyze_query', methods=['POST'])
def analyze_query():
    user_query = request.json.get('query')
    if not user_query:
        return jsonify({"error": "No query provided"}), 400

    prompt = f"Determine the intent of the following user query: \n\nQuery: \"{user_query}\"\nCategories: \n1. Real-time data queries (Production line telemetry, Advaris, ODEN, QAD, Quality cost) - Query for InfluxDB.\n2. Troubleshooting and manuals - Query for LLM in the Edge/VectorDB.\n\nInstructions: If the query relates to real-time operational data or system-specific data tracking, classify it as \"InfluxDB\". If it pertains to troubleshooting, problem-solving, or manual inquiries, classify it as \"LLM in the Edge/VectorDB\". Provide a brief reasoning for your classification."

    response = openai.Completion.create(
        engine="gpt-35-turbo",
        prompt=prompt,
        max_tokens=100
    )

    intent = response.choices[0].text.strip()

    return jsonify({"intent": intent})

if __name__ == '__main__':
    app.run(debug=True)
