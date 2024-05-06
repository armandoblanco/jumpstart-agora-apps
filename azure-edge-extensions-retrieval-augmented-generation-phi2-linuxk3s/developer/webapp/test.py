import os
from openai import AzureOpenAI

AZURE_OPENAI_API_KEY="38d82ccac49149e49367fc5329f1c84d"
api_version="2024-02-01"
AZURE_OPENAI_ENDPOINT="https://acbuilddemo.openai.azure.com/"
    
#client = AzureOpenAI(
#    api_key=os.getenv("AZURE_OPENAI_API_KEY"),  
#    api_version="2024-02-01",
#    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
#    )

client = AzureOpenAI(
    api_key=AZURE_OPENAI_API_KEY,  
    api_version="2024-02-01",
    azure_endpoint = AZURE_OPENAI_ENDPOINT
    )
    
deployment_name='gpt-35-turbo' 
    
response = client.chat.completions.create(
    model=deployment_name,
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Does Azure OpenAI support customer managed keys?"},
        {"role": "assistant", "content": "Yes, customer managed keys are supported by Azure OpenAI."},
        {"role": "user", "content": "Do other Azure AI services support this too?"}
    ]
)

print(response.choices[0].message.content)