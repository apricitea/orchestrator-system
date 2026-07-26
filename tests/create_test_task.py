import requests
import os
from dotenv import load_dotenv

load_dotenv("/home/ubuntu/.env")

TRELLO_API_KEY = os.getenv("TRELLO_API_KEY")
TRELLO_TOKEN = os.getenv("TRELLO_TOKEN")
TRELLO_LIST_TODO = os.getenv("TRELLO_LIST_TODO")

# Create a proper test task
url = f"https://api.trello.com/1/cards"
params = {
    "key": TRELLO_API_KEY,
    "token": TRELLO_TOKEN,
    "idList": TRELLO_LIST_TODO,
    "name": "[TEST] Create hello world function",
    "desc": """Project: apricitea/test-autonomous-agent
Priority: P0

Task: Create a simple Python function that returns 'Hello, World!'.

Requirements:
- Create a file hello.py in the root directory
- Add a function hello() that returns 'Hello, World!'
- Make sure it's a proper Python function with docstring

This is a test task for the autonomous agent.""",
}

response = requests.post(url, params=params)
if response.status_code == 200:
    card = response.json()
    print(f"✅ Test task created!")
    print(f"   Card ID: {card['id']}")
    print(f"   URL: {card['url']}")
else:
    print(f"❌ Failed: {response.text}")
