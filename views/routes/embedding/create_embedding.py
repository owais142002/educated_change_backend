
from flask import Blueprint, request
from openai import OpenAI
import os, tiktoken
from langchain.text_splitter import RecursiveCharacterTextSplitter
from tenacity import retry
from tenacity import stop_after_delay
from tenacity import RetryError
from tenacity import stop_after_attempt
from tenacity import wait_exponential
import requests
import io
import urllib
import docx2txt
import chardet
from zipfile import BadZipFile
from PyPDF2.errors import PdfReadError
from urllib.error import URLError
from PyPDF2 import PdfReader
from requests.exceptions import ConnectionError
from bs4 import BeautifulSoup
from bs4.element import Comment
from pymongo import MongoClient
import uuid

from dotenv import load_dotenv
load_dotenv()

max_timeout=int(os.getenv('max_timeout'))
openai_req_timeout=int(os.getenv('openai_req_timeout'))
default_openai_key = os.getenv('default_openai_key')
browserless_token = os.getenv('browserless_token')
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

    return returnList

def tag_visible(element):
    if element.parent.name in ['style', 'script', 'head', 'title', 'meta', '[document]', 'noscript', 'header', 'html',
                               'input']:
        return False
    if isinstance(element, Comment):
        return False
    return True


@retry(wait=wait_exponential(multiplier=1, min=4, max=10), stop=stop_after_attempt(3))
def browserLessReq(data,options):
    try:
        response = requests.post(
            f'https://chrome.browserless.io/scrape?token={browserless_token}&stealth&headless=false', json=options)
#             print(response.status_code)
#             print(response.headers['x-response-code'])
        try:               
            if str(response.status_code)!="200" or str(response.headers['x-response-code'])=='403':
                try:
                    response = requests.get(data['webpage'],timeout=max_timeout)
                except requests.exceptions.ReadTimeout:
                    return (f'The webpage is not responding.','failed')
                # Check if the request was successful (status code 200)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    visible_text = ' '.join([element for element in soup.find_all(text=True) if tag_visible(element)])
                    return (visible_text,'success')
                else:
                    return (f'The webpage is giving {response.status_code} error.','failed')

            elif str(response.headers['x-response-code'])!='200':
                code=response.headers['x-response-code']
                return (f'The x-response code is {code}','failed')
            else:                
                return (response.json()['data'][0]['results'][0]['text'].replace('\n', ' '), 'success')
        except KeyError:
            return ('Webpage can’t be reached or invalid webpage','failed')
    except Exception as e:
        if 'net::ERR_NAME_NOT_RESOLVED' in e:
            raise Exception
        else:
            return (e, 'failed')  

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
        
create_embedding_bp = Blueprint('create_embedding', __name__)

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

@create_embedding_bp.route("/projects/embeddings/create", methods=["POST"])
def embeddingCreate():

    try:
        data = request.json
    except:
        return {"error":"No JSON object recieved!"},400
    
    attributes=['namespace','metadata', 'index', 'namespace']
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
        return ({"error":"This document is already been embeded."}), 400
    
    attributes = ['text', 'fileURL', 'webpage', 'youtubeURL']
    present_attributes = [attr for attr in attributes if attr in data]
    
    if len(present_attributes) != 1:
        return ({"error": "Exactly one of text, fileURL, webpage, youtubeURL should be present!"}), 400
    if 'youtubeURL' in data:
        if 'youtubeText' not in data:
            return ({"error":"youtubeText attr is missing!"}),400
        else:
            pass

    if 'openAIKey' in data:
        pass
    else:
        data['openAIKey'] = default_openai_key

    client =OpenAI(api_key=data['openAIKey'])  

    if 'webpage' in present_attributes:
        fileType = 'webpage'
    elif 'fileURL' in present_attributes:
        if '.pdf' in data.get('fileURL', '').lower():
            fileType = 'file'
        elif '.doc' in data.get('fileURL', '').lower():
            fileType = 'file'
        elif '.txt' in data.get('fileURL', '').lower():
            fileType = 'file'            
        else:
            return ({"error": "Invalid fileURL! file should be pdf or doc or txt."}), 400
        
    elif 'text' in present_attributes:
        fileType = 'text'  
    elif 'youtubeURL' in present_attributes:
        fileType = 'youtubeURL'
        
    if fileType=='text':
        pdfContent = data['text']
        
    elif fileType=='file':        
        r = requests.get(data['fileURL'])
        f = io.BytesIO(r.content)     
        if r.status_code ==403:
            HEADERS = {'User-Agent': 'Mozilla/5.0 (iPad; CPU OS 12_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148'}
            r = requests.get(data['fileURL'],headers=HEADERS)
            f = io.BytesIO(r.content)            
             
        if '.pdf' in data['fileURL'].lower():
            try:
                reader = PdfReader(f)
            except PdfReadError:
                return ({"error":"PDF file not valid or forbidden!"}),400

            totalPages=reader.pages.length_function()
            pdfContent=''
            for page in range(totalPages):
                pdfContent=pdfContent+reader.pages[page].extract_text()
            if pdfContent=='':
                return ({"error":"Oops, we can't read this PDF, it might be scanned or empty. Please ensure the PDF has not been scanned and text can be selected from it."}),400
            
        if '.doc' in data['fileURL'].lower():
            try:
                pdfContent = docx2txt.process(f)
            except BadZipFile:
                return ({"error":"Invalid file link. File may have expired."}),400    
            
        if 'txt' in data['fileURL'].lower():
            pdfContent=''
            for line in urllib.request.urlopen(data['fileURL']):
                try:
                    pdfContent=pdfContent+(line.decode('utf-8',errors='ignore'))
                except:
                    try:
                        pdfContent=pdfContent+(line.decode(chardet.detect(line)['encoding'])) 
                    except:
                        pdfContent=pdfContent+(line.decode('ISO-8859-1'))             

    elif fileType=='webpage':
        try:
            options = {
                "url": data['webpage'],
                "elements": [
                    {
                        "selector": "html"
                    }
                ],
                "gotoOptions": {
                    "timeout": 30000,
                    "waitUntil": "networkidle2"
                }
            }
            try:                
                browserReq = browserLessReq(data,options)
                if browserReq[1] == 'failed':                        
                    return ({'error': f'{browserReq[0]}'}), 400
                else:
                    response = browserReq[0]
            except RetryError:
                return ({'error': f'The url is not responding!'}), 400
            try:
                pdfContent = response

            except:
                return ({"error": "Webpage can’t be reached"}), 400

            if pdfContent == '':
                return ({"error": "Webpage can’t be reached or empty!"}), 400

        except (ConnectionError, URLError):
            options = {
                "url": data['webpage'],
                "elements": [
                    {
                        "selector": "html"
                    }
                ],
                "gotoOptions": {
                    "timeout": 30000,
                    "waitUntil": "networkidle2"
                }
            }

            try:
                browserReq = browserLessReq(data,options)
                if browserReq[1] == 'failed':
                    return ({'error': f'{browserReq[0]}'}), 400
                else:
                    response = browserReq[0]
            except RetryError:
                return ({'error': f'The server is currently overloaded with other requests'}), 400
            try:
                pdfContent = response                   
            except:
                return ({"error": "Webpage can’t be reached"}), 400
            
    elif fileType == 'youtubeURL':

        pdfContent = data['youtubeText']
        r = requests.get(data['youtubeURL'])
        soup = BeautifulSoup(r.text,features='lxml')
        link = soup.find_all(name="title")[0]
        video_title = str(link)
        video_title = video_title.replace("<title>","")
        video_title = video_title.replace("</title>","")
        video_title = video_title.replace(' - YouTube','').strip() 
        
    splittedContent=text_splitter.split_text(pdfContent)
    splittedContent = [' '.join(i.split()) for i in splittedContent if i.strip() != '']       
    if fileType == 'youtubeURL':
        splittedContent = [f'This is a Youtube video transcript. The title of the video is: {video_title}. Transcript Content:  '+i for i in splittedContent]     
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
        "index":data['index'],
        "namespace":data["namespace"],
        "total_chunks":len(returnJsonData)
    }

    return finalResponse,200   
