import os
import firebase_admin
from firebase_admin import credentials, messaging
import threading
import traceback

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVICE_ACCOUNT_PATH = os.path.join(BASE_DIR, "firebase", "serviceAccountKey.json")


def initialize_firebase():
    try:
        if not firebase_admin._apps:
            cred = credentials.Certificate(SERVICE_ACCOUNT_PATH)
            firebase_admin.initialize_app(cred)
            print("✅ Firebase initialized successfully")
    except Exception as e:
        print("❌ Firebase init error:", e)
        traceback.print_exc()


initialize_firebase()


def send_fcm_notification(token, title, body, data=None):
    try:
        print("📲 Sending FCM...")

        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body
            ),
            token=token,
            data=data or {},
            android=messaging.AndroidConfig(
                priority="high",
            ),
        )

        response = messaging.send(message)
        print("✅ Notification sent:", response)
        return True

    except Exception as e:
        print("❌ FCM error:", e)
        traceback.print_exc()
        return False


def send_notification_async(token, title, body, data=None):
    thread = threading.Thread(
        target=send_fcm_notification,
        args=(token, title, body, data),
        daemon=True
    )
    thread.start()