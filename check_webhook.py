import requests
from telebot.credentials import BOT_TOKEN  # Replace with your actual bot token

def check_webhook():
    response = requests.get(f'https://api.telegram.org/bot{BOT_TOKEN}/getWebhookInfo')
    if response.status_code == 200:
        print("Webhook Info:", response.json())
    else:
        print(f"Failed to retrieve webhook info: {response.status_code} - {response.text}")

if __name__ == "__main__":
    check_webhook()