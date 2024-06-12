from flask import Blueprint, request,Response
import os
from dotenv import load_dotenv
import requests
from io import BytesIO

load_dotenv(dotenv_path='env')
elevenlabs_key = os.getenv('elevenlabs_key')
voice_id = os.getenv('voice_id')
chunk_size = int(os.getenv('chunk_size'))


textToSpeechRoute = Blueprint('textToSpeechRoute', __name__)
@textToSpeechRoute.route("/elevenlabs/textToSpeech", methods=["POST"])
def textToSpeech():
    data = request.json
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": elevenlabs_key
    }
    payload = {
        "text": data['text'],
        "model_id": "eleven_monolingual_v1",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.5
        }
    }
    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()

    audio_data = response.content
    return Response(audio_data, mimetype='audio/mpeg')