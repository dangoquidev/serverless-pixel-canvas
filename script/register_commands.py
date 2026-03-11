import requests
import getpass

print("--- Discord Slash Command Registration ---")

APP_ID = input("Enter your Discord App ID: ").strip()
BOT_TOKEN = getpass.getpass("Enter your Discord Bot Token (input will be hidden): ").strip()

if not APP_ID or not BOT_TOKEN:
    print("❌ Error: Both App ID and Bot Token are required.")
    exit(1)

url = f"https://discord.com/api/v10/applications/{APP_ID}/commands"

json_payload = {
    "name": "snapshot",
    "type": 1, # 1 = CHAT_INPUT (Slash Command)
    "description": "Generates a live image of the current pixel canvas!"
}

headers = {
    "Authorization": f"Bot {BOT_TOKEN}",
    "Content-Type": "application/json"
}

print(f"\nRegistering '/{json_payload['name']}' command...")
response = requests.post(url, headers=headers, json=json_payload)

if response.status_code in (200, 201):
    print("✅ Command registered successfully!")
    print(f"Command ID: {response.json().get('id')}")
else:
    print(f"❌ Failed to register command. HTTP Status: {response.status_code}")
    print("Error Details:", response.json())
