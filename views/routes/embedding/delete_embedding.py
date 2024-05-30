from flask import Blueprint, request
import os
from tenacity import retry
from tenacity import stop_after_delay
from tenacity import RetryError
from tenacity import stop_after_attempt
from tenacity import wait_exponential
from pymongo import MongoClient
from dotenv import load_dotenv
load_dotenv()
CONNECTION_STRING_MONGODB = os.getenv("mongodb_connection_string")
MONGODB_COLLECTION = os.getenv("mongodb_collection_name")
MONGODB_DATABASE = os.getenv("mongodb_database_name")
delete_embedding_bp = Blueprint('delete_embedding', __name__)

@delete_embedding_bp.route("/projects/embeddings/delete", methods=["POST"])
def embeddingDelete():
    try:
        data = request.json
    except:
        return ({"error":"No JSON object recieved!"}),400
    
    
    if 'index' not in data:
        return ({'error': 'Index is missing in JSON body'}), 400
    
    index = data['index']
    client_mongo = MongoClient(CONNECTION_STRING_MONGODB)
    db = client_mongo[MONGODB_DATABASE]
    collection = db[MONGODB_COLLECTION] 

    if collection.count_documents({"index": index}) == 0:
        return ({"error": f"Index '{index}' not found"}), 404    
    
    if 'namespace' in data:
        namespace = data['namespace']
        if 'filter' in data:
            filter_criteria = { "index": index, "namespace": namespace, "metadata.link": data['filter']['link'] }
        else:
            filter_criteria = { "index": index, "namespace": namespace }

    if 'filter' in data:
        link = data['filter'].get('link')
        if link:
            filter_criteria["metadata.link"] = link

    if collection.count_documents(filter_criteria) == 0:
        return ({"error": "No documents found matching the provided criteria"}), 404
           
    result = collection.delete_many(filter_criteria)
            
    return ({"message":"success"}),200
