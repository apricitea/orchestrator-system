import requests
import os
from dotenv import load_dotenv

load_dotenv("/home/ubuntu/.env")

TRELLO_API_KEY = os.getenv("TRELLO_API_KEY")
TRELLO_TOKEN = os.getenv("TRELLO_TOKEN")
TRELLO_LIST_TODO = os.getenv("TRELLO_LIST_TODO")

# Create Wikipedia Analytics task
url = f"https://api.trello.com/1/cards"
params = {
    "key": TRELLO_API_KEY,
    "token": TRELLO_TOKEN,
    "idList": TRELLO_LIST_TODO,
    "name": "[apricitea/wikipedia-analytics] Add summary hero section",
    "desc": """Priority: P0

Task: Add 1 summary hero section that highlights the most interesting and current finding as of today.

Requirements:
- Create a hero section at the top of the dashboard
- Display the most interesting Wikipedia trend/article of the day
- Show current statistics (views, rank, change percentage)
- Make it visually appealing with good design
- Update dynamically based on latest Wikipedia data

This is for the Wikipedia Analytics Dashboard project.""",
}

response = requests.post(url, params=params)
if response.status_code == 200:
    card = response.json()
    print(f"✅ Wikipedia Analytics task created!")
    print(f"   Card ID: {card['id']}")
    print(f"   URL: {card['url']}")
else:
    print(f"❌ Failed: {response.text}")
