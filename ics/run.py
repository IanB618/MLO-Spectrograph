from src.web import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host=app.config["ICS_HOST"], port=app.config["ICS_PORT"])
