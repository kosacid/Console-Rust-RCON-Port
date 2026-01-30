import discord
import asyncio
import os
import re
import json
import websockets
from typing import Optional
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get values from .env
TOKEN = os.getenv('DISCORD_TOKEN')
SERVER_IP = os.getenv('SERVER_IP')
RCON_PORT = int(os.getenv('RCON_PORT'))
RCON_PASSWORD = os.getenv('RCON_PASSWORD')
ADMIN_CHANNEL_ID = int(os.getenv('ADMIN_CHAT'))

class RCONListener:
    """RCON WebSocket client that listens to ALL server messages"""
    
    def __init__(self, server_ip: str, rcon_port: int, rcon_password: str):
        self.uri = f"ws://{server_ip}:{rcon_port}/{rcon_password}"
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.command_counter = 1
        self.is_connected = False
        self.pending_responses = {}
        self.listening = False
    
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
    
    async def listen_forever(self):
        """Continuously listen for ALL server messages (run this once!)"""
        if not self.websocket:
            print("Not connected")
            return
        
        if self.listening:
            print("Already listening!")
            return
        
        self.listening = True
        print("\nListening for ALL server messages...")
        
        try:
            while self.listening:
                try:
                    # Wait for message from server with timeout
                    raw_response = await asyncio.wait_for(self.websocket.recv(), timeout=30.0)
                    
                    # Process the raw message
                    message_data = await self._process_raw_message(raw_response)
                    if message_data:
                        # Yield the message for processing
                        yield message_data
                        
                except asyncio.TimeoutError:
                    # Send ping to keep connection alive
                    try:
                        await self.websocket.ping()
                        continue
                    except:
                        print("Connection timeout, attempting to reconnect...")
                        self.is_connected = False
                        break
                        
                except websockets.exceptions.ConnectionClosed as e:
                    print(f"Connection closed: {e}")
                    self.is_connected = False
                    break
                    
        except Exception as e:
            print(f"Error listening: {e}")
            self.is_connected = False
        finally:
            self.listening = False
    
    async def _process_raw_message(self, raw_response: str):
        """Process raw WebSocket message and extract data"""
        try:
            response_data = json.loads(raw_response)
            
            # Extract all available information
            message = response_data.get("Message", "")
            message_type = response_data.get("Type", "")
            identifier = response_data.get("Identifier", "")
            stacktrace = response_data.get("Stacktrace", "")
            
            # Clean up the message
            if isinstance(message, str):
                message = message.replace("\u0000", "").strip()
            
            return {
                "raw_response": raw_response,
                "message": message,
                "message_type": message_type,
                "identifier": identifier,
                "stacktrace": stacktrace,
                "raw_data": response_data,
                "is_json": True
            }
            
        except json.JSONDecodeError:
            # If not JSON, return raw data
            return {
                "raw_response": raw_response,
                "message": None,
                "message_type": None,
                "identifier": None,
                "stacktrace": None,
                "raw_data": None,
                "is_json": False
            }
    
    async def send_command(self, command: str, command_type: str = "", discord_channel = None, discord_message: str = "") -> bool:
        """Send command to WebSocket RCON server"""
        try:
            if not self.is_connected or not self.websocket:
                if not await self.connect():
                    return False
            
            current_id = self.command_counter
            
            # Store pending response info if we need to handle the response
            if discord_channel:
                self.pending_responses[current_id] = {
                    "type": command_type,
                    "channel": discord_channel,
                    "message": discord_message
                }
            
            command_data = {
                "Message": command,
                "Identifier": current_id,
                "Type": "Command",
                "Stacktrace": None
            }
            
            await self.websocket.send(json.dumps(command_data))
            print(f"Sent command (ID {current_id}): {command}")
            self.command_counter += 1
            return True
            
        except Exception as e:
            print(f"Error sending to RCON: {e}")
            self.is_connected = False
            return False
    
    async def reconnect(self):
        """Reconnect to the server"""
        await self.close()
        return await self.connect()
    
    async def close(self) -> None:
        """Close the connection"""
        self.listening = False
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
            self.is_connected = False

def format_command_response(command_type: str, server_response: str, original_message: str = "") -> Optional[str]:
    """Format server response for Discord based on command type"""
    
    server_response = server_response.strip()
    
    if command_type == "printpos":
        coord_pattern = r'\(([-\d\.]+),\s*([-\d\.]+),\s*([-\d\.]+)\)'
        coord_match = re.search(coord_pattern, server_response)
        
        if coord_match:
            x, y, z = coord_match.groups()
            coordinates = f"{x},{y},{z}"
            player_match = re.search(r'printpos\s*"([^"]+)"', original_message)
            player_name = player_match.group(1) if player_match else "player"
            return f"📍 **{player_name}** is at coordinates: `{coordinates}`"
    
    elif command_type == "players":
        if "id ;name" in server_response:
            return f"📊 **Online Players**:\n```\n{server_response}\n```"
    
    elif command_type == "time":
        if "env.time:" in server_response:
            return f"🕐 **Server Time**:\n```\n{server_response}\n```"
    
    return None

# Discord bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)

# Global instances
rcon_listener = None

@bot.event
async def on_ready():
    print(f'Bot ready: {bot.user}')
    
    global rcon_listener
    
    # Initialize RCON listener
    rcon_listener = RCONListener(SERVER_IP, RCON_PORT, RCON_PASSWORD)
    
    # Connect to WebSocket RCON
    if await rcon_listener.connect():
        # Start the SINGLE listening task
        bot.loop.create_task(listen_to_rcon())

async def listen_to_rcon():
    """Single task to listen to RCON messages"""
    global rcon_listener
    
    print("Starting RCON listener...")
    
    while True:
        try:
            # Reconnect if needed
            if not rcon_listener.is_connected:
                print("Not connected, attempting to reconnect...")
                if not await rcon_listener.reconnect():
                    await asyncio.sleep(5)
                    continue
            
            # Use the listen_forever generator
            async for message_data in rcon_listener.listen_forever():
                await process_rcon_message(message_data)
                
        except Exception as e:
            print(f"Error in RCON listener: {e}")
            await asyncio.sleep(5)

@bot.event
async def on_message(message):
    # Ignore messages from the bot itself
    if message.author == bot.user:
        return
    
    # Only respond in admin channel
    if message.channel.id != ADMIN_CHANNEL_ID:
        return
    
    # Handle commands
    if message.content.startswith('!'):
        content = message.content[1:].strip()
        
        if content == 'players':
            success = await rcon_listener.send_command('players', "players", message.channel)
            if success:
                await message.channel.send("📊 Requesting player list from server...")
            else:
                await message.channel.send("❌ Failed to send command. Check bot logs.")
            
        elif content == 'time':
            success = await rcon_listener.send_command('time', "time", message.channel)
            if success:
                await message.channel.send("🕐 Requesting server time...")
            else:
                await message.channel.send("❌ Failed to send command. Check bot logs.")
            
        elif content.startswith('say'):
            say_content = content[3:].strip()
            
            if '"' in say_content:
                import shlex
                try:
                    parts = shlex.split(say_content)
                    
                    if len(parts) >= 1:
                        message_text = ' '.join(parts)
                        rcon_command = f'say "{message_text}"'
                        success = await rcon_listener.send_command(rcon_command, "say", message.channel, message_text)
                        
                        if success:
                            await message.channel.send(f"📢 Broadcasting message: `{message_text}`")
                            print(f"Admin used say: {message_text}")
                        else:
                            await message.channel.send("❌ Failed to send command.")
                        
                    else:
                        await message.channel.send("❌ Usage: `!say \"message\"`")
                        
                except Exception as e:
                    await message.channel.send(f"❌ Error parsing command: {e}")
            else:
                message_text = say_content
                if message_text:
                    rcon_command = f'say "{message_text}"'
                    success = await rcon_listener.send_command(rcon_command, "say", message.channel, message_text)
                    if success:
                        await message.channel.send(f"📢 Broadcasting message: `{message_text}`")
                        print(f"Admin used say: {message_text}")
                    else:
                        await message.channel.send("❌ Failed to send command.")
                else:
                    await message.channel.send("❌ Usage: `!say \"message\"`")
            
        elif content.startswith('givedrop'):
            parts = content.split()
            if len(parts) >= 5:
                player_name = parts[1]
                item_name = parts[2]
                
                try:
                    amount = int(parts[3])
                    stacks = int(parts[4])
                    
                    rcon_command = f'givedrop {player_name} {item_name} {amount} {stacks}'
                    success = await rcon_listener.send_command(rcon_command, "givedrop", message.channel)
                    
                    if success:
                        await message.channel.send(f"🎁 Giving {amount} {item_name} (in {stacks} stacks) to `{player_name}`")
                        print(f"Admin used givedrop: {player_name} {item_name} {amount} {stacks}")
                    else:
                        await message.channel.send("❌ Failed to send command.")
                    
                except ValueError:
                    await message.channel.send("❌ Error: Amount and stacks must be numbers!")
            else:
                await message.channel.send("❌ Usage: `!givedrop <player_name> <item_name> <amount> <stacks>`")
        
        elif content.startswith('giveto'):
            parts = content.split()
            if len(parts) >= 4:
                player_name = parts[1]
                item_name = parts[2]
                
                try:
                    amount = int(parts[3])
                    
                    rcon_command = f'giveto {player_name} {item_name} {amount}'
                    success = await rcon_listener.send_command(rcon_command, "giveto", message.channel)
                    
                    if success:
                        await message.channel.send(f"🎁 Giving {amount} {item_name} to `{player_name}`")
                        print(f"Admin used giveto: {player_name} {item_name} {amount}")
                    else:
                        await message.channel.send("❌ Failed to send command.")
                    
                except ValueError:
                    await message.channel.send("❌ Error: Amount must be a number!")
            else:
                await message.channel.send("❌ Usage: `!giveto <player_name> <item_name> <amount>`")
        
        elif content.startswith('spawn'):
            parts = content.split()
            
            if len(parts) >= 3:
                item_name = parts[1]
                coordinates_str = parts[2]
                
                coord_pattern = r'^-?\d+(\.\d+)?,-?\d+(\.\d+)?,-?\d+(\.\d+)?$'
                if not re.match(coord_pattern, coordinates_str):
                    await message.channel.send("❌ Error: Invalid coordinates format!\nUsage: `!spawn <item_name> <x,y,z>`")
                    return
                
                rcon_command = f'spawn {item_name} {coordinates_str}'
                success = await rcon_listener.send_command(rcon_command, "spawn", message.channel)
                
                if success:
                    await message.channel.send(f"🎁 Spawning `{item_name}` at `{coordinates_str}`")
                    print(f"Admin used spawn: {item_name} at {coordinates_str}")
                else:
                    await message.channel.send("❌ Failed to send command.")
                
            else:
                await message.channel.send("❌ Usage: `!spawn <item_name> <x,y,z>`")
            
        elif content.startswith('printpos'):
            printpos_content = content[8:].strip()
            
            if '"' in printpos_content:
                import shlex
                try:
                    parts = shlex.split(printpos_content)
                    
                    if len(parts) == 1:
                        player_name = parts[0]
                        rcon_command = f'printpos "{player_name}"'
                        success = await rcon_listener.send_command(rcon_command, "printpos", message.channel, rcon_command)
                        
                        if success:
                            await message.channel.send(f"📍 Getting position for: `{player_name}`")
                            print(f"Admin used printpos: {player_name}")
                        else:
                            await message.channel.send("❌ Failed to send command.")
                        
                    else:
                        await message.channel.send("❌ Usage: `!printpos \"player_name\"`")
                        
                except Exception as e:
                    await message.channel.send(f"❌ Error parsing command: {e}")
            else:
                player_name = printpos_content
                if player_name:
                    rcon_command = f'printpos "{player_name}"'
                    success = await rcon_listener.send_command(rcon_command, "printpos", message.channel, rcon_command)
                    if success:
                        await message.channel.send(f"📍 Getting position for: `{player_name}`")
                        print(f"Admin used printpos: {player_name}")
                    else:
                        await message.channel.send("❌ Failed to send command.")
                else:
                    await message.channel.send("❌ Usage: `!printpos \"player_name\"`")
        
        elif content == 'help':
            help_text = """
**📊 Server Commands:**
• `!players` - List online players
• `!time` - Check server time

**📍 Player Position:**
• `!printpos "player_name"` - Get player position

**📢 Server Messages:**
• `!say "message"` - Broadcast message to all players

**🎁 Give Items:**
• `!givedrop player_name item_name amount stacks`
  Example: `!givedrop player123 wood 3000 3`
• `!giveto player_name item_name amount`
  Example: `!giveto player123 wood 5000`

**🗺️ Spawn Items:**
• `!spawn <item_name> <x,y,z>`
  Example: `!spawn wood -100,50,200`
  Example: `!spawn stone 0,100,300`
"""
            await message.channel.send(help_text)

async def process_rcon_message(message_data):
    """Process a single RCON message"""
    global rcon_listener
    
    if not message_data.get("is_json"):
        # Non-JSON message
        raw_response = message_data.get("raw_response", "")
        print(f"Non-JSON data received: {repr(raw_response)}")
        return
    
    # Extract data from message
    message = message_data.get("message", "")
    message_type = message_data.get("message_type", "")
    identifier = message_data.get("identifier", "")
    raw_data = message_data.get("raw_data", {})
    
    # Print debug info
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"\n{'='*60}")
    print(f"Message | {timestamp}")
    print(f"Type: {message_type} | ID: {identifier}")
    print(f"{'='*60}")
    
    if message:
        print(f"Message content: {repr(message)}")
    
    if not message:
        return
    
    # Check if this is a response to a command we sent
    if identifier in rcon_listener.pending_responses:
        command_info = rcon_listener.pending_responses[identifier]
        command_type = command_info.get("type", "")
        discord_channel = command_info.get("channel")
        original_message = command_info.get("message", "")
        
        response_text = format_command_response(command_type, message, original_message)
        
        if response_text and discord_channel:
            await discord_channel.send(response_text)
        
        del rcon_listener.pending_responses[identifier]

# Run the bot
bot.run(TOKEN)
