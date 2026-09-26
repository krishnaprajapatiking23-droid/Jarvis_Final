"""
Notification Manager
"""

from datetime import datetime


class NotificationManager:

    def notify(

        self,

        title,

        message

    ):

        print()

        print("=" * 60)

        print("NOTIFICATION")

        print("=" * 60)

        print("Time :", datetime.now())

        print("Title :", title)

        print("Message :", message)

        print("=" * 60)

        print()

        return True


notifications = NotificationManager()