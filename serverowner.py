import discord
import asyncio
import os
import json
import websockets
from typing import Optional, Dict
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
        self.pending_responses: Dict[int, asyncio.Future] = {}
        self.receive_task = None
    
    async def connect(self) -> bool:
        """Establish connection to server"""
        try:
            print(f"Connecting to {self.uri}")
            self.websocket = await websockets.connect(self.uri)
            self.is_connected = True
            print("Connected successfully")
            
            # Start receiving messages in background
            self.receive_task = asyncio.create_task(self._receive_messages())
            
            return True
        except Exception as e:
            print(f"Connection failed: {e}")
            self.is_connected = False
            return False
    
    async def _receive_messages(self):
        """Continuously receive messages from server"""
        try:
            while self.is_connected and self.websocket:
                try:
                    response = await asyncio.wait_for(self.websocket.recv(), timeout=1.0)
                    await self._process_response(response)
                except asyncio.TimeoutError:
                    continue
                except websockets.exceptions.ConnectionClosed:
                    print("WebSocket connection closed")
                    self.is_connected = False
                    break
        except Exception as e:
            print(f"Error in receive_messages: {e}")
            self.is_connected = False
    
    async def _process_response(self, response: str):
        """Process response from server"""
        try:
            response_data = json.loads(response)
            identifier = response_data.get("Identifier", -1)
            message = response_data.get("Message", "")
            
            # Clean up the message
            if isinstance(message, str):
                message = message.replace("\u0000", "").strip()
            
            print(f"Received response for ID {identifier}: {repr(message[:100])}")
            
            # Check if we're waiting for this response
            if identifier in self.pending_responses:
                future = self.pending_responses[identifier]
                if not future.done():
                    future.set_result(message)
                del self.pending_responses[identifier]
            else:
                # Log unexpected responses
                print(f"Unexpected response for ID {identifier}")
                
        except json.JSONDecodeError:
            print(f"Non-JSON response: {repr(response[:100])}")
    
    async def send_raw_command(self, command: str) -> str:
        """Send raw command to WebSocket RCON server and return response"""
        try:
            if not self.is_connected or not self.websocket:
                if not await self.connect():
                    return "❌ Failed to connect to server"
            
            current_id = self.command_counter
            
            # Create a future to wait for the response
            response_future = asyncio.Future()
            self.pending_responses[current_id] = response_future
            
            command_data = {
                "Message": command,
                "Identifier": current_id,
                "Type": "Command",
                "Stacktrace": None
            }
            
            await self.websocket.send(json.dumps(command_data))
            print(f"Sent command (ID {current_id}): {command}")
            
            # Wait for response with timeout
            try:
                response = await asyncio.wait_for(response_future, timeout=10.0)
                self.command_counter += 1
                return response if response else "✅ Command executed (empty response)"
            except asyncio.TimeoutError:
                del self.pending_responses[current_id]
                self.command_counter += 1
                return "⏰ Command timed out - no response received"
            
        except Exception as e:
            print(f"Error sending command: {e}")
            if current_id in self.pending_responses:
                del self.pending_responses[current_id]
            self.is_connected = False
            return f"❌ Error: {str(e)}"
    
    async def close(self) -> None:
        """Close the connection"""
        self.is_connected = False
        if self.receive_task:
            self.receive_task.cancel()
        if self.websocket:
            await self.websocket.close()
            self.websocket = None

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
            if response.startswith("❌") or response.startswith("⏰"):
                # Error message
                await message.reply(response, mention_author=False)
            else:
                # Normal response in code block
                await message.reply(f"```\n{response}\n```", mention_author=False)

# Run the bot
bot.run(TOKEN)
