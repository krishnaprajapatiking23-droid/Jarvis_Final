"""
Jarvis REST API
"""

from flask import Flask

from .config import config

from .routes import register_routes


def create_server():

    app = Flask(__name__)

    app.config["SECRET_KEY"] = config.SECRET_KEY

    register_routes(app)

    return app


server = create_server()


def run():

    print("=" * 60)

    print("JARVIS SERVER")

    print("=" * 60)

    print(f"Listening : {config.HOST}:{config.PORT}")

    print("=" * 60)

    server.run(

        host=config.HOST,

        port=config.PORT,

        debug=config.DEBUG

    )


if __name__ == "__main__":

    run()