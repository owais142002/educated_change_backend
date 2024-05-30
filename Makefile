build-dev:
	/opt/render/project/src/.venv/bin/python -m pip install --upgrade pip
	pip install -r requirements.txt

start-dev:
	 gunicorn -w 4 --bind 0.0.0.0:3000 main:app --timeout 1500 

