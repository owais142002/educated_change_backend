from socketserver import ThreadingMixIn
import os
from flask import Flask
from flask import request, jsonify

from views.routes.embedding.create_embedding import create_embedding_bp
from views.routes.embedding.delete_embedding import delete_embedding_bp
from views.routes.query.query import query_bp
from views.routes.embedding.create_embedding_image import create_embedding_image_bp
from views.routes.query.fetch import fetch_bp
from flask_cors import CORS
from dotenv import load_dotenv
load_dotenv()

class ThreadedServer(ThreadingMixIn, Flask):
    pass


app = ThreadedServer(__name__)

CORS(app, supports_credentials=True, methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'])

app.register_blueprint(create_embedding_bp)
app.register_blueprint(delete_embedding_bp)
app.register_blueprint(query_bp)
app.register_blueprint(fetch_bp)
app.register_blueprint(create_embedding_image_bp)