import requests
import getpass

print("--- Discord Slash Command Registration ---")

APP_ID = input("Enter your Discord App ID: ").strip()
BOT_TOKEN = getpass.getpass("Enter your Discord Bot Token (input will be hidden): ").strip()

if not APP_ID or not BOT_TOKEN:
    print("❌ Error: Both App ID and Bot Token are required.")
    exit(1)

url = f"https://discord.com/api/v10/applications/{APP_ID}/commands"

json_payload = [
    {
        "name": "snapshot",
        "type": 1,
        "description": "Generates a live image of the current pixel canvas!"
    },
    {
        "name": "ping",
        "type": 1,
        "description": "Checks if the Discord canvas bot is online."
    },
    {
        "name": "draw",
        "type": 1,
        "description": "Draws one pixel on the canvas.",
        "options": [
            {
                "name": "x",
                "description": "X coordinate (0-999)",
                "type": 4,
                "required": True,
                "min_value": 0,
                "max_value": 999,
            },
            {
                "name": "y",
                "description": "Y coordinate (0-999)",
                "type": 4,
                "required": True,
                "min_value": 0,
                "max_value": 999,
            },
            {
                "name": "color",
                "description": "Hex color (#RRGGBB)",
                "type": 3,
                "required": True,
            },
        ],
    },
    {
        "name": "clean",
        "type": 1,
        "description": "Admin only: clears the entire canvas.",
    },
]

headers = {
    "Authorization": f"Bot {BOT_TOKEN}",
    "Content-Type": "application/json"
}

print("\nRegistering slash commands (snapshot, ping, draw, clean)...")
response = requests.put(url, headers=headers, json=json_payload)

if response.status_code in (200, 201):
    print("✅ Command registered successfully!")
    registered = response.json()
    print(f"Registered {len(registered)} commands")
    for cmd in registered:
        print(f"- /{cmd.get('name')} (id={cmd.get('id')})")
else:
    print(f"❌ Failed to register command. HTTP Status: {response.status_code}")
    print("Error Details:", response.json())
