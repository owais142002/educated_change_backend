import os
from dotenv import load_dotenv
from datetime import datetime
from flask import Blueprint, request
from pymongo import MongoClient

load_dotenv()
openai_req_timeout=int(os.getenv('openai_req_timeout'))
CONNECTION_STRING_MONGODB = os.getenv("mongodb_connection_string")
MONGODB_COLLECTION = os.getenv("mongodb_collection_name")
MONGODB_DATABASE = os.getenv("mongodb_database_name")


def removeDuplicatesRef(data):
    forDuplication=[]
    returnList=[]
    for instance in data:
        if instance['metadata']['content'] in forDuplication:
            continue
        returnList.append(instance)
        forDuplication.append(instance['metadata']['content'])
    return returnList


        
fetch_bp = Blueprint('fetch', __name__)
@fetch_bp.route("/projects/fetch", methods=["POST"])
def fetch_vectors():
    try:
        data = request.json
    except:
        return {"error":"No JSON object recieved!"},400
    if 'index' not in data:
        return ({'error': 'Index is missing in JSON body'}), 400
    
    index = data['index']
    client_mongo = MongoClient(CONNECTION_STRING_MONGODB)
    db = client_mongo[MONGODB_DATABASE]
    collection = db[MONGODB_COLLECTION]            
    unique_links = collection.distinct("metadata.link", {"index": index})

    result = []
    
    for link in unique_links:
        chunks = collection.find({"index": index, "metadata.link": link})
        content = ''.join(chunk['content'] for chunk in chunks)
        namespace = collection.find_one({"index": index, "metadata.link": link})['namespace']
        
        result.append({
            "index": index,
            "namespace": namespace,
            "content": content,
            "link": link
        })

    return result,200
