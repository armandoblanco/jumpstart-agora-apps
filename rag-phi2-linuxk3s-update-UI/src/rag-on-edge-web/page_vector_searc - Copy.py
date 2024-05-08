import streamlit as st
import time
import logging
import requests
#from streamlit.server.server import Server

#logging.basicConfig(level=logging.INFO)

# Check response for up to 100/1=100 times (100sec)
CHECK_NUM = 100 
CHECK_INTERVAL_SEC = 1 
CONV_HISTORY_NUM = 3
retrieval_prompt = '''Use the Content to answer the Search Query.

Search Query: 

SEARCH_QUERY_HERE

Search Content and Answer: 

'''
query_response = '''
Query: 

SEARCH_QUERY_HERE

SEARCH_ANSWER_HERE

'''
faq = [
    {
        "persona": "operator",
        "question": "How is the production going?"
    },
    {
        "persona": "operator",
        "question": "Which units have defects and what are the reasons?"
    },
    {
        "persona": "operator",
        "question": "Do we have information on anomalies that might have led to these defects?"
    },
    {
        "persona": "operator",
        "question": "Which machine is causing the defects, and what could be the possible reasons?"
    },
    {
        "persona": "operator",
        "question": "How can we fix this? Are there any guidelines or manuals?"
    }
    # Add more FAQ questions and answers as needed
]


#conversation_history = []

st.set_page_config(page_title="Natural Language Query For OT Data Insights", page_icon=":memo:", layout="wide")
col1, col2  = st.columns((10,1)) 

if 'conversation_history' not in st.session_state:
	st.session_state.conversation_history = []


def check_processed_result(request_id, user_input_json):
    check_url = f'http://rag-interface-service:8701/check_processed_result/{request_id}'
    response = requests.get(check_url)
    
    if response.status_code == 200:
        result_data = response.json()
        if result_data['status'] == 'success':
            #st.write(f"test-before: {st.session_state.conversation_history}")
            query_response_str = query_response.replace('SEARCH_QUERY_HERE',user_input_json['user_query']).replace('SEARCH_ANSWER_HERE',result_data['processed_result'])
            #query_response_str = result_data['processed_result']
            st.session_state.conversation_history.append(query_response_str)
            #st.text(st.session_state.conversation_history[-1])
            #st.write(f"test-after: {st.session_state.conversation_history}")
            # keep the conversation history to a certain number
            if len(st.session_state.conversation_history)> CONV_HISTORY_NUM:
                st.session_state.conversation_history.pop(0) #removing old history

            
            col1.title("Conversation Log")
            for item in st.session_state.conversation_history:
                col1.success(item)
            
            return True
    
    return False

def publish_user_input(user_input_json):
    backend_url = 'http://rag-interface-service:8701/webpublish'
    check_num_counter = CHECK_NUM
    try:
        response = requests.post(backend_url, json=user_input_json)
        if response.status_code == 200:
            #st.success(response.json()['message'])
            request_id = response.json()['request_id']
            # Check for processed results periodically
            for _ in range(CHECK_NUM):  
                check_num_counter -= 1
                if check_num_counter == 0:
                    st.error('Timeout! Failed to get query response. Please try again later.')
                    break
                if check_processed_result(request_id, user_input_json):
                    break
                time.sleep(CHECK_INTERVAL_SEC)

        else:
            st.error('Failed to publish user input to the backend')
    except requests.RequestException as e:
        st.error(f'Request failed: {e}')

def query_retrieval():
    #st.title('Please input your question and press enter to search:')
    with st.sidebar:
        with st.spinner(text="Loading..."):
            # get the index names from the backend VDB module
            index_names = requests.get('http://rag-vdb-service:8602/list_index_names').json()['index_names']
            index_name = st.selectbox('**Please select an index name:**',index_names)
            st.write('You selected:', index_name)

        prompt = st.text_input('**Please input your question:**')
        #prompt = st.text_input("You:", key="user_input")
        #if st.button("Send", key="send_button") and prompt:
        if st.button('Send') and prompt:
            #st.session_state.conversation_history = [] #------test
            # st.title("Chat History")
            # st.session_state.conversation_history.append(prompt)
            # st.text(st.session_state.conversation_history[-1])
            
            with st.spinner(text="Document Searching..."):  
                retrieval_prepped = retrieval_prompt.replace('SEARCH_QUERY_HERE',prompt)
                #st.write(f"{retrieval_prepped}\n\n")

                user_input_json = {'user_query': prompt, 'index_name': index_name}
                publish_user_input(user_input_json)

        # st.title("Chat History")
        # for message in st.session_state.conversation_history:
        #     st.text(message)

        st.title("FAQ")
        for item in faq:
            #st.markdown(f"**persona:** {item['persona']}")
            st.write(f"**question:** {item['question']}")


if __name__ == "__main__":
    query_retrieval()

