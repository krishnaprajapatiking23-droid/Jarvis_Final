"""
Jarvis Mobile Client
"""

import requests


class MobileClient:

    def __init__(self):

        self.host = "http://127.0.0.1:5000"

        self.token = None

    def login(self):

        response = requests.post(

            f"{self.host}/api/login"

        )

        data = response.json()

        self.token = data["token"]

        print("Connected Successfully")

        return True

    def verify(self):

        if self.token is None:

            return False

        response = requests.post(

            f"{self.host}/api/verify",

            json={

                "token": self.token

            }

        )

        return response.json()["valid"]

    def ping(self):

        response = requests.get(

            f"{self.host}/api/ping"

        )

        return response.json()


client = MobileClient()