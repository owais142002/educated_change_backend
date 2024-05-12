from flask import Blueprint, request
from openai import OpenAI
from langchain.text_splitter import RecursiveCharacterTextSplitter
import os, tiktoken
from tenacity import retry
from tenacity import stop_after_delay
from tenacity import RetryError
from tenacity import stop_after_attempt
from tenacity import wait_exponential
import uuid
from pymongo import MongoClient
from dotenv import load_dotenv
load_dotenv()

pinecone_key = os.getenv('pinecone_key')
pinecone_env = os.getenv('pinecone_env')
pinecone_index = os.getenv('pinecone_index')
openai_req_timeout=int(os.getenv('openai_req_timeout'))
default_openai_key = os.getenv('default_openai_key')
CONNECTION_STRING_MONGODB = os.getenv("mongodb_connection_string")
MONGODB_COLLECTION = os.getenv("mongodb_collection_name")
MONGODB_DATABASE = os.getenv("mongodb_database_name")
tokenizer = tiktoken.get_encoding('cl100k_base')
 
# create the length function used by the RecursiveCharacterTextSplitter
def tiktoken_len(text):
    tokens = tokenizer.encode(
        text,
        disallowed_special=()
    )
    return len(tokens)

# create recursive text splitter
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=400,
    chunk_overlap=20,  # number of tokens overlap between chunks
    length_function=tiktoken_len,
    separators=['\n\n', '\n', ' ', '']
)
def removeDuplicatesRef(data):
    forDuplication = []
    returnList = []
    for instance in data:
        if instance['metadata']['content'] in forDuplication:
            continue
        returnList.append(instance)
        forDuplication.append(instance['metadata']['content'])

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
           
def get_metadata_links(index, namespace):
    client = MongoClient(CONNECTION_STRING_MONGODB)
    db = client.educated_change_data
    collection = db.data    
    pipeline = [
        {"$match": {"index": index, "namespace": namespace}},
        {"$project": {"metadata.link": 1, "_id": 0}}
    ]
    result = collection.aggregate(pipeline)
    metadata_links = list(set([doc["metadata"]["link"] for doc in result]))
    return metadata_links

create_embedding_image_bp = Blueprint('create_embedding_image', __name__)

@create_embedding_image_bp.route("/projects/embeddings/analyze-image", methods=["POST"])
def analyzeImage():
    try:
        data = request.json
    except:
        return {"error":"No JSON object recieved!"},400
    
    attributes=['namespace','index','metadata','image_url']
    for attr in attributes:
        if attr not in data:
            return {"error": f"{attr} attribute is missing!"},400        
        elif type(data[attr])==str and data[attr].strip()=='':
            return {"error": f"{attr} attribute is empty!"},400    
    try:
        if 'link' not in data['metadata']:
            return {"error": f"metadata link attribute is missing!"},400
        elif type(data['metadata']['link'])!=str:
            return {"error": f"metadata link attribute must be string!"},400        
        elif data['metadata']['link'].strip()=='' or data['metadata']['link']==None:
            return {"error": f"metadata link attribute is empty or null!"},400
        
    except (AttributeError, TypeError):
        return {"error": f"metadata link attribute must be string!"},400  
    
    metadata_links = get_metadata_links(data['index'], data['namespace'])
    if data['metadata']['link'] in metadata_links:
        return ({"error":"This image is already been embeded."}), 400
        
    client = OpenAI(api_key=default_openai_key)

    response = client.chat.completions.create(
    model="gpt-4-vision-preview",
    messages=[
        {
        "role": "user",
        "content": [
            {"type": "text", "text": "Give a breif description of the image?"},
            {
            "type": "image_url",
            "image_url": {
                "url": f"{data['image_url']}",
            },
            },
        ],
        }
    ],
    max_tokens=300,
    )    
    text = (response.choices[0].message.content)
    splittedContent=text_splitter.split_text(text)
    splittedContent = [' '.join(i.split()) for i in splittedContent if i.strip() != '']       
    try:
        splittedContent.remove('.')
    except:
        pass    
    returnJsonData=[]
    for chunk in splittedContent:
        tempJson={}
        try:            
            embeddingResp = create_embedding(client,chunk)
            if embeddingResp[1] == 'failed':
                return ({'error': f'{embeddingResp[0]}'}), 400
            else:
                response = embeddingResp[0]
        except RetryError:
            return ({'error': f'The server is currently overloaded with other requests'}), 400        
         
        tempJson['embedding']=response.data[0].embedding
        tempJson['content']=chunk
        tempJson['_id']=str(uuid.uuid4())
        tempJson['metadata']=data['metadata'].copy()
        tempJson['namespace']=data['namespace']
        tempJson['index']=data['index']
        returnJsonData.append(tempJson)

    client_mongo = MongoClient(CONNECTION_STRING_MONGODB)
    db = client_mongo[MONGODB_DATABASE]
    collection = db[MONGODB_COLLECTION]

    collection.insert_many(returnJsonData, ordered=False)    
    finalResponse={
        "text":text,
        "index":data['index'],
        "namespace":data["namespace"],
        "total_chunks":len(returnJsonData)
    }

    return finalResponse,200   
