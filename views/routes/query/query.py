from flask import Blueprint, request, Response
import os
import re
from openai import OpenAI
from langchain_mongodb import MongoDBAtlasVectorSearch
from langchain_openai import OpenAIEmbeddings
from tenacity import retry
from tenacity import stop_after_delay
from tenacity import RetryError
from tenacity import stop_after_attempt
from tenacity import wait_exponential
import json
from pymongo import MongoClient
from dotenv import load_dotenv
load_dotenv()

max_timeout=int(os.getenv('max_timeout'))
openai_req_timeout=int(os.getenv('openai_req_timeout'))
default_openai_key = os.getenv('default_openai_key')
browserless_token = os.getenv('browserless_token')
CONNECTION_STRING_MONGODB = os.getenv("mongodb_connection_string")
MONGODB_COLLECTION = os.getenv("mongodb_collection_name")
MONGODB_DATABASE = os.getenv("mongodb_database_name")

@retry(wait=wait_exponential(multiplier=1, min=4, max=10), stop=stop_after_attempt(10))
def create_embedding(client,text):
    try:
        response = client.embeddings.create(
            model="text-embedding-ada-002",
            input=text
        )
        return (response, 'success')    
    except Exception as e:
        if 'The server is currently overloaded with other requests' in e:
            raise Exception
        else:
            return (e, 'failed')

def removeDuplicatesRef(data):
    forDuplication = []
    returnList = []
    for instance in data:
        if instance['metadata']['content'] in forDuplication:
            continue
        returnList.append(instance)
        forDuplication.append(instance['metadata']['content'])
    return returnList


@retry(stop=stop_after_delay(30))
def ask_question(client,messages,data):
    response = client.chat.completions.create(messages=messages,
                                            temperature=data['temperature'], frequency_penalty=1,
                                            max_tokens=data['maxTokens'],timeout=openai_req_timeout ,model=data['model'], stream=True)
    for chunk in response:
        if type(chunk.choices[0].delta.content)==str:
            yield chunk.choices[0].delta.content
    return 


        


query_bp = Blueprint('query', __name__)
@query_bp.route("/projects/query", methods=["POST"])
def embeddingQuery():

    try:
        data = request.json
    except:
        return {"error":"No JSON object recieved!"},400
    
    attributes=['query','index','namespace','model','openAIKey','temperature','maxTokens']
    for attr in attributes:
        if attr not in data:
            return {"error": f"{attr} attribute is missing!"},400        
        elif type(data[attr])==str and data[attr].strip()=='':
            return {"error": f"{attr} attribute is empty!"},400  
        
    if 'openAIKey' in data:
        pass
    else:
        data['openAIKey'] = default_openai_key

    data['results']=3

    client_mongo = MongoClient(CONNECTION_STRING_MONGODB)
    db = client_mongo[MONGODB_DATABASE]
    collection = db[MONGODB_COLLECTION]
    embedding_model  = OpenAIEmbeddings(api_key=data['openAIKey'])
    vector_search = MongoDBAtlasVectorSearch(
        collection,
        embedding_model,
        index_name="vector_index",
        text_key="content",
        relevance_score_fn="cosine"
    )    
    pre_filter = { "$and": [{ "index": data['index'] }, { "namespace": data['namespace'] }]}
    search_results = vector_search.similarity_search(data['query'], k=3, pre_filter=pre_filter)
    contentText=''
    for item in search_results:
        contentText=contentText+'\n- '+(item.page_content).replace('\n',' ')+' '    
        
    systemChatMessage = "You are a helpful assistant which helps the user with given context. Your goal is to provide realistic answers based on the context provided. If you lack information to answer a question, respond with 'I am not given enough knowledge to answer the question,' but attempt to answer first. Never start your answer refering to the context like Based on the information provided, it appears "

    chatInstruction = "Follow these instructions:\n1. Provide an answer to the question with the context given..\n2. If the answer is not within your knowledge, respond with 'I am not given enough knowledge to answer the question.' Always try your best to answer first.\n3. Avoid explicitly referring to specific sources or contexts in your responses. Never start your answer refering to the context like Based on the information provided. The context provided is 100% correct"


    contentText = f'''Available information: {contentText[0:8193]}\n\n{chatInstruction}\n\nQuestion: "{data["query"]}?"'''
    if data['prompt'].strip()!='':
        messages = [
                    {"role": "system", "content": systemChatMessage},
                    {"role": "user", "content":data['prompt']},
                    {"role": "user", "content":contentText}
                   ]    
    else:
        messages = [
                    {"role": "system", "content": systemChatMessage},
                    {"role": "user", "content":contentText}
                    ]            
    # try:
    #     tenResp = ask_question(client,messages,data)
    #     if tenResp[1] == 'failed':
    #         return {'error': f'OpenAI error {tenResp[0]}'}, 400
    #     else:
    #         response = tenResp[0]
    # except RetryError:
    #     return {'error': f'OpenAI error: OpenAI is overloaded with requests right now, please try again'}, 400
        
    
    
    # answer = response.choices[0].message.content.replace('\n- ', '\n• ').replace('- ', '• ').replace('(IDK)','<IDK>').replace('Answer: ', '')


    # successMessage={
    #     "answer":answer
    # }
    headers = {"Transfer-Encoding": "chunked", "Content-Type": "application/json"}
    client =OpenAI(api_key=data['openAIKey'])  
    return Response(ask_question(client,messages,data), headers=headers, status=200)   