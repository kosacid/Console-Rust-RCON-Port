import discord
import asyncio
import os
import json
import websockets
from typing import Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get values from .env
TOKEN = os.getenv('DISCORD_TOKEN')
SERVER_IP = os.getenv('SERVER_IP')
RCON_PORT = int(os.getenv('RCON_PORT'))
RCON_PASSWORD = os.getenv('RCON_PASSWORD')
SERVER_OWNER_CHANNEL_ID = int(os.getenv('SERVER_OWNER_CHANNEL_ID'))

class RawRCONClient:
    """Simple RCON WebSocket client for sending raw commands"""
    
    def __init__(self, server_ip: str, rcon_port: int, rcon_password: str):
        self.uri = f"ws://{server_ip}:{rcon_port}/{rcon_password}"
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.command_counter = 1
        self.is_connected = False
    
    async def connect(self) -> bool:
        """Establish connection to server"""
        try:
            print(f"Connecting to {self.uri}")
            self.websocket = await websockets.connect(self.uri)
            self.is_connected = True
            print("Connected successfully")
            
            # Send initial command to start receiving messages
            init_data = {
                "Message": "",
                "Identifier": 1,
                "Type": "Command",
                "Stacktrace": None
            }
            await self.websocket.send(json.dumps(init_data))
            
            return True
        except Exception as e:
            print(f"Connection failed: {e}")
            self.is_connected = False
            return False
    
    async def send_raw_command(self, command: str) -> str:
        """Send raw command to WebSocket RCON server and return response"""
        try:
            if not self.is_connected or not self.websocket:
                if not await self.connect():
                    return "❌ Failed to connect to server"
            
            current_id = self.command_counter
            
            command_data = {
                "Message": command,
                "Identifier": current_id,
                "Type": "Command",
                "Stacktrace": None
            }
            
            await self.websocket.send(json.dumps(command_data))
            print(f"Sent command (ID {current_id}): {command}")
            
            # Wait for response
            response = await self.websocket.recv()
            response_data = json.loads(response)
            
            message = response_data.get("Message", "")
            if isinstance(message, str):
                message = message.replace("\u0000", "").strip()
            
            self.command_counter += 1
            return message
            
        except Exception as e:
            print(f"Error sending command: {e}")
            self.is_connected = False
            return f"❌ Error: {str(e)}"
    
    async def close(self) -> None:
        """Close the connection"""
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
            self.is_connected = False

# Discord bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)

# Global RCON client
rcon_client = None

@bot.event
async def on_ready():
    print(f'Bot ready: {bot.user}')
    
    global rcon_client
    rcon_client = RawRCONClient(SERVER_IP, RCON_PORT, RCON_PASSWORD)
    
    # Try to connect
    if await rcon_client.connect():
        print("RCON client connected successfully")
    else:
        print("Failed to connect RCON client")

@bot.event
async def on_message(message):
    # Ignore messages from the bot itself
    if message.author == bot.user:
        return
    
    # Only respond in SERVER_OWNER channel
    if message.channel.id != SERVER_OWNER_CHANNEL_ID:
        return
    
    # Send the raw message content as a command to the server
    raw_command = message.content.strip()
    
    if not raw_command:
        return
    
    # Send typing indicator
    async with message.channel.typing():
        # Send command to server
        response = await rcon_client.send_raw_command(raw_command)
        
        # Format response for Discord
        if response:
            # Truncate if too long for Discord
            if len(response) > 1900:
                response = response[:1900] + "\n... (truncated)"
            
            # Send response back to Discord
            await message.reply(f"```\n{response}\n```", mention_author=False)
        else:
            await message.reply("✅ Command sent (no response received)", mention_author=False)

# Run the bot
bot.run(TOKEN)
