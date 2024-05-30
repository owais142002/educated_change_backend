from main import app


if __name__ == "__main__":
    app.run(threaded=True, debug=True)  # is threaded=True necessary? it is True by default
