# import requests

# from config import settings
# from utils.logger import get_logger

# log = get_logger()


# def send_telegram(message: str):

#     if not settings.TELEGRAM_ENABLED:
#         return

#     try:

#         url = (
#             f"https://api.telegram.org/bot"
#             f"{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
#         )

#         payload = {
#             "chat_id": settings.TELEGRAM_CHAT_ID,
#             "text": message,
#             "parse_mode": "Markdown"
#         }

#         requests.post(url, json=payload, timeout=10)

#     except Exception as e:
#         log.error(f"Telegram error: {e}")



"""
utils/telegram.py
Telegram notification helper.
"""

import requests

from config import settings
from utils.logger import get_logger

log = get_logger()


class TelegramNotifier:

    def __init__(self):

        self.enabled = settings.TELEGRAM_ENABLED,

        self.token = settings.TELEGRAM_BOT_TOKEN

        self.chat_id = settings.TELEGRAM_CHAT_ID

    # ---------------------------------------------------
    # SEND MESSAGE
    # ---------------------------------------------------

    def send(self, message: str):

        if not self.enabled:
            return

        try:

            url = (

                f"https://api.telegram.org/bot"

                f"{self.token}/sendMessage"

            )

            payload = {

                "chat_id": self.chat_id,

                "text": message,

                "parse_mode": "Markdown"

            }

            response = requests.post(

                url,

                json=payload,

                timeout=10

            )

            if response.status_code != 200:

                log.error(

                    f"Telegram error: "

                    f"{response.text}"

                )

        except Exception as e:

            log.error(

                f"Telegram send failed: {e}"

            )


telegram = TelegramNotifier()


# ---------------------------------------------------
# HELPER FUNCTION FOR LEGACY IMPORTS
# ---------------------------------------------------

def send_telegram(message: str):
    """Legacy wrapper for backward compatibility."""
    telegram.send(message)

