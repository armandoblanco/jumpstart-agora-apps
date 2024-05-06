import openai
import string
import ast
from datetime import timedelta
import os
import pandas as pd
import plotly.express as px
import plotly.graph_objs as go
from statsmodels.tsa.arima.model import ARIMA
import numpy as np
import random
from urllib import parse
import re
import json
from plotly.graph_objects import Figure
import time
from influxdbclient import InfluxDBAdapter

class ChatGPT_Handler: #designed for chatcompletion API
    def __init__(self, gpt_deployment=None,max_response_tokens=None,token_limit=None,temperature=None,extract_patterns=None) -> None:
        self.max_response_tokens = max_response_tokens
        self.token_limit= token_limit
        self.gpt_deployment=gpt_deployment
        self.temperature=temperature
        # self.conversation_history = []
        self.extract_patterns=extract_patterns

    def _call_llm(self,prompt, stop):
        print("prompt: ", prompt)
        response = openai.ChatCompletion.create(
        engine=self.gpt_deployment, 
        messages = prompt,
        temperature=self.temperature,
        max_tokens=self.max_response_tokens,
        stop=stop
        )
        print("response: ", response)
        llm_output = response['choices'][0]['message']['content']
        return llm_output
    def extract_output(self, text_input):
            output={}
            if len(text_input)==0:
                return output
            for pattern in self.extract_patterns: 
                if "flux_query" in pattern[1]:

                    flux_query=""
                    flux_result = re.findall(pattern[1], text_input, re.DOTALL)

                    if len(flux_result)>0:
                        flux_query=flux_result[0]
                        output[pattern[0]]= flux_query
                    else:
                        return output
                    text_before = text_input.split(flux_query)[0].strip("\n").strip("```flux").strip("\n")

                    if text_before is not None and len(text_before)>0:
                        output["text_before"]=text_before
                    text_after =text_input.split(flux_query)[1].strip("\n").strip("```")
                    if text_after is not None and len(text_after)>0:
                        output["text_after"]=text_after
                    return output

                if "python" in pattern[1]:
                    result = re.findall(pattern[1], text_input, re.DOTALL)
                    if len(result)>0:
                        output[pattern[0]]= result[0]
                else:

                    result = re.search(pattern[1], text_input,re.DOTALL)
                    if result:  
                        output[result.group(1)]= result.group(2)

            return output

class AnalyzeGPT(ChatGPT_Handler):
    
    def __init__(self,content_extractor, flux_query_tool, system_message,few_shot_examples,st,**kwargs) -> None:
        super().__init__(**kwargs)
        
        system_message = f"""
        <<data_sources>>
        bucket: flowermound
        Measurement: "anomalies",
        Notes: The anomalyscore field contains positive and negative values. Negative values are considered anomalies.
        The shap_* fields are the shap values for each feature. The shap values are the contribution of each feature to the anomalyscore.
        The fields without the prefix shap_ are the original values of each feature. To filter for a specific line, use the "line" in Tags
        "Tags": ["site","area","cell","line","asset"],
        "Fields": [
                "anomalyscore",
                "opticalLFiltered" ,
                "opticalRFiltered" ,
                "pumpPressure",
                "rotational",
                "vibrationHorizon",
                "shap_opticalLFiltered" ,
                "shap_opticalRFiltered" ,
                "shap_pumpPressure",
                "shap_rotational",
                "shap_vibrationHorizon"                      
        ],
        "DateTime": "timestamp"

        bucket: flowermound
        Measurement: "sensordata",
        Notes: This is the raw sensor data. The data is not filtered or processed in any way. To filter for a specific line, use the "line" in Tags
        "Tags": ["site","area","cell","line","asset"],
        "Fields": [
        "opticalLFiltered" ,
        "opticalRFiltered" ,
        "pumpPressure",
        "rotational"
        ],
        "DateTime": "timestamp"
        <</data_sources>>

        {system_message}
        {few_shot_examples}
        """

        self.conversation_history =  [{"role": "system", "content": system_message}]
        self.st = st
        self.content_extractor = content_extractor
        self.flux_query_tool = flux_query_tool

    def get_next_steps(self, updated_user_content, stop):
        old_user_content=""
        if len(self.conversation_history)>1:
            old_user_content= self.conversation_history.pop() #removing old history
            #old_user_content=old_user_content['content']+"\n"
            old_user_content=""
        self.conversation_history.append({"role": "user", "content": old_user_content+updated_user_content})
        n=0
        try:
            llm_output = self._call_llm(self.conversation_history, stop)
            #print("llm_output \n", llm_output)

        except Exception as e:
            print(f"Exception: {e} ")
            time.sleep(8) #sleep for 8 seconds
            while n<5:
                try:
                    llm_output = self._call_llm(self.conversation_history, stop)
                except Exception as e:
                    n +=1
                    print("error calling open AI, I am retrying 5 attempts , attempt ", n)
                    time.sleep(8) #sleep for 8 seconds
                    print(e)

            llm_output = "OPENAI_ERROR"     
             
    
        # print("llm_output: ", llm_output)
        output = self.content_extractor.extract_output(llm_output)
        if len(output)==0 and llm_output != "OPENAI_ERROR": #wrong output format
            llm_output = "WRONG_OUTPUT_FORMAT"

            

        return llm_output,output

    def run(self, question: str, show_code,show_prompt,st) -> any:
        import numpy as np
        import plotly.express as px
        import plotly.graph_objs as go
        import pandas as pd

        st.write(f"Question: {question}")
        def execute_influxquery(flux_query):
            return self.flux_query_tool.execute_influxquery(flux_query)
        observation=None
        def show(data):
            if type(data) is Figure:
                st.plotly_chart(data)
            else:
                st.write(data)
            if type(data) is not Figure:
                self.st.session_state[f'observation: this was shown to user']=data
        def observe(name, data):
            try:
                data = data[:10] # limit the print out observation to 15 rows
            except:
                pass
            self.st.session_state[f'observation:{name}']=data

        max_steps = 15
        count =1

        finish = False
        new_input= f"Question: {question}"
        while not finish:
            llm_output,next_steps = self.get_next_steps(new_input, stop=["Observation:", f"Thought {count+1}"])
            if llm_output=='OPENAI_ERROR':
                st.write("Error Calling Azure Open AI, probably due to max service limit, please try again")
                break
            elif llm_output=='WRONG_OUTPUT_FORMAT': #just have open AI try again till the right output comes
                count +=1
                continue

            new_input += f"\n{llm_output}"
            for key, value in next_steps.items():
                new_input += f"\n{value}"
                
                if "ACTION" in key.upper():
                    if show_code:
                        st.write(key)
                        st.code(value)
                    observations =[]
                    serialized_obs=[]
                    try:
                        # if "print(" in value:
                        #     raise Exception("You must not use print() statement, instead use st.write() to write to end user or observe(name, data) to view data yourself. Please regenerate the code")
                        exec(value, locals())
                        for key in self.st.session_state.keys():
                            if "observation:" in key:
                                observation=self.st.session_state[key]
                                observations.append((key.split(":")[1],observation))
                                if type(observation) is pd:
                                    # serialized_obs.append((key.split(":")[1],observation.to_json(orient='records', date_format='iso')))
                                    serialized_obs.append((key.split(":")[1],observation.to_string()))

                                elif type(observation) is not Figure:
                                    serialized_obs.append({key.split(":")[1]:str(observation)})
                                del self.st.session_state[key]
                    except Exception as e:
                        observations.append(("Error:",str(e)))
                        serialized_obs.append({"\nEncounter following error, can you try again?\n:":str(e)+"\nAction:"})
                        
                    for observation in observations:
                        st.write(observation[0])
                        st.write(observation[1])

                    obs = f"\nObservation on the first 10 rows of data: {serialized_obs}"
                    new_input += obs
                else:
                    st.write(key)
                    st.write(value)
                if "Answer" in key:
                    print("Answer is given, finish")
                    finish= True
            if show_prompt:
                self.st.write("Prompt")
                self.st.write(self.conversation_history)

            count +=1
            if count>= max_steps:
                print("Exceeding threshold, finish")
                break




    