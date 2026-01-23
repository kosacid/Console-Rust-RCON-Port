import discord
import os
import re
import json
import websockets
import asyncio
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

# Get the mods channel ID
MODS_CHANNEL_ID = None
channel_id_str = os.getenv('MODS')
if channel_id_str:
    try:
        MODS_CHANNEL_ID = int(channel_id_str)
        print(f"Using MODS channel ID: {MODS_CHANNEL_ID}")
    except (ValueError, TypeError):
        print(f"Warning: Invalid MODS value: {channel_id_str}")

if MODS_CHANNEL_ID is None:
    print("ERROR: No valid MODS channel ID found!")
    exit(1)

class RCONListener:
    """RCON WebSocket client that listens to ALL server messages"""
    
    def __init__(self, server_ip: str, rcon_port: int, rcon_password: str):
        self.uri = f"ws://{server_ip}:{rcon_port}/{rcon_password}"
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.command_counter = 1
        self.is_connected = False
        self.pending_responses = {}
        self.processed_ids = set()  # Track processed message IDs to prevent duplicates
    
    async def connect(self) -> bool:
        """Establish connection to server"""
        try:
            print(f"Connecting to {self.uri}")
            self.websocket = await websockets.connect(self.uri)
            self.is_connected = True
            print("Connected successfully")
            
            # Send initial command
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
    
    async def listen_continuously(self, process_callback):
        """Listen continuously for messages"""
        while True:
            try:
                if not self.is_connected or not self.websocket:
                    print("Not connected, reconnecting...")
                    if not await self.connect():
                        await asyncio.sleep(5)
                        continue
                
                raw_response = await self.websocket.recv()
                
                try:
                    response_data = json.loads(raw_response)
                    message = response_data.get("Message", "")
                    identifier = response_data.get("Identifier", 0)
                    
                    if isinstance(message, str):
                        message = message.replace("\u0000", "").strip()
                    
                    # Debug output
                    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                    print(f"\n{'='*60}")
                    print(f"Message #{identifier} | {timestamp}")
                    print(f"{'='*60}")
                    if message:
                        print(f"Message content: {repr(message)}")
                    
                    if process_callback:
                        await process_callback(message, identifier)
                        
                except json.JSONDecodeError:
                    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                    print(f"\n{'='*60}")
                    print(f"Non-JSON Message | {timestamp}")
                    print(f"{'='*60}")
                    print(f"Raw bytes: {repr(raw_response)}")
                    
            except websockets.exceptions.ConnectionClosed:
                print("Connection closed, reconnecting...")
                self.is_connected = False
                await asyncio.sleep(5)
            except Exception as e:
                print(f"Error listening: {e}")
                await asyncio.sleep(1)
    
    async def send_command(self, command: str, command_type: str = "", discord_channel = None, discord_message: str = "") -> bool:
        """Send command to WebSocket RCON server"""
        try:
            print(f"DEBUG: Attempting to send command: {command}")
            
            if not self.is_connected or not self.websocket:
                print(f"DEBUG: Not connected, attempting to connect...")
                if not await self.connect():
                    print(f"DEBUG: Connection failed!")
                    return False
            
            current_id = self.command_counter
            
            if discord_channel:
                print(f"DEBUG: Storing pending response for ID {current_id}")
                self.pending_responses[current_id] = {
                    "type": command_type,
                    "channel": discord_channel,
                    "message": discord_message or command
                }
            
            command_data = {
                "Message": command,
                "Identifier": current_id,
                "Type": "Command",
                "Stacktrace": None
            }
            
            print(f"DEBUG: Sending JSON: {json.dumps(command_data)}")
            await self.websocket.send(json.dumps(command_data))
            print(f"Sent command (ID {current_id}): {command}")
            self.command_counter += 1
            return True
            
        except Exception as e:
            print(f"Error sending to RCON: {e}")
            self.is_connected = False
            return False
    
    async def close(self) -> None:
        """Close the connection"""
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
            self.is_connected = False

def extract_coordinates(line: str) -> Optional[str]:
    """Extract coordinates from printpos response line"""
    try:
        pattern = r'\(([-\d\.]+),\s*([-\d\.]+),\s*([-\d\.]+)\)'
        match = re.search(pattern, line)
        
        if match:
            x, y, z = match.groups()
            coordinates = f"{x},{y},{z}"
            print(f"Extracted coordinates: {coordinates}")
            return coordinates
    except Exception as e:
        print(f"Error extracting coordinates: {e}")
    return None

def format_command_response(command_type: str, server_response: str, original_message: str = "") -> Optional[str]:
    """Format server response for Discord"""
    server_response = server_response.strip()
    
    # Don't send empty responses
    if not server_response:
        return None
    
    if command_type == "banlist":
        return f"📋 **Ban List**:\n```\n{server_response}\n```"
    
    elif command_type == "players":
        return f"👥 **Players Online**:\n```\n{server_response}\n```"
    
    elif command_type == "teleportpos":
        return f"🚀 **Teleport** - {server_response}"
    
    elif command_type == "printpos":
        coordinates = extract_coordinates(server_response)
        if coordinates:
            # Extract player name from original command
            player_name = "Unknown"
            match = re.search(r'printpos\s+"([^"]+)"', original_message)
            if match:
                player_name = match.group(1)
            else:
                # Try without quotes
                match = re.search(r'printpos\s+(\S+)', original_message)
                if match:
                    player_name = match.group(1)
            return f"📍 **Position for {player_name}**: `{coordinates}`"
        else:
            return f"📍 **Position** - {server_response}"
    
    elif command_type in ["mutevoice", "unmutevoice", "mutechat", "unmutechat"]:
        emoji = {"mutevoice": "🔇", "unmutevoice": "🔊", "mutechat": "🤐", "unmutechat": "🗣️"}.get(command_type, "ℹ️")
        return f"{emoji} **{command_type.title()}** - {server_response}"
    
    elif command_type == "banid":
        return f"🔨 **Ban executed** - {server_response}"
    
    elif command_type == "kick":
        return f"👢 **Kick executed** - {server_response}"
    
    elif command_type == "unban":
        return f"✅ **Unban executed** - {server_response}"
    
    return None

async def process_rcon_message(bot, rcon_listener: RCONListener, message: str, identifier: int):
    """Process incoming RCON message"""
    if not message:
        return
    
    # Skip if we've already processed this message ID
    if identifier in rcon_listener.processed_ids:
        print(f"DEBUG: Already processed ID {identifier}, skipping")
        return
    
    # Check if this is a response to a command we sent
    if identifier in rcon_listener.pending_responses:
        # Mark as processed FIRST to prevent duplicates
        rcon_listener.processed_ids.add(identifier)
        
        command_info = rcon_listener.pending_responses.pop(identifier)  # Remove immediately
        command_type = command_info.get("type", "")
        discord_channel = command_info.get("channel")
        original_message = command_info.get("message", "")
        
        # Send formatted response
        response_text = format_command_response(command_type, message, original_message)
        
        if response_text and discord_channel:
            try:
                await discord_channel.send(response_text)
            except Exception as e:
                print(f"Error sending response: {e}")

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
    rcon_listener = RCONListener(SERVER_IP, RCON_PORT, RCON_PASSWORD)
    
    if await rcon_listener.connect():
        bot.loop.create_task(rcon_listener.listen_continuously(
            lambda msg, ident: process_rcon_message(bot, rcon_listener, msg, ident)
        ))

def parse_player_command(content: str, command_length: int) -> tuple[str, str]:
    """Parse player command with or without quotes"""
    command_content = content[command_length:].strip()
    
    if not command_content:
        return "", command_content
    
    # Try to parse with quotes first
    import shlex
    try:
        parts = shlex.split(command_content)
        if len(parts) >= 1:
            player_name = parts[0]
            return player_name, command_content
    except:
        pass
    
    # If no quotes or parsing failed, take first word as player name
    parts = command_content.split(maxsplit=1)
    if len(parts) >= 1:
        player_name = parts[0]
        return player_name, command_content
    
    return "", command_content

def parse_ban_command(content: str, command_length: int) -> tuple[str, str, int]:
    """Parse ban command: banid player_name "reason" time"""
    ban_content = content[command_length:].strip()
    
    if not ban_content:
        return "", "", 0
    
    import shlex
    try:
        # Try to parse with shlex (handles quotes)
        parts = shlex.split(ban_content)
        
        if len(parts) >= 3:
            # Format: player_name "reason" time
            player_name = parts[0]
            reason = parts[1]
            
            try:
                time_seconds = int(parts[2])
                return player_name, reason, time_seconds
            except ValueError:
                return "", "", 0
        elif len(parts) == 2:
            # Could be: player_name time (no reason)
            player_name = parts[0]
            try:
                time_seconds = int(parts[1])
                return player_name, "", time_seconds
            except ValueError:
                return "", "", 0
    except:
        pass
    
    # Try simple parsing if shlex fails
    parts = ban_content.split(maxsplit=2)
    if len(parts) >= 3:
        # Check if middle part is quoted
        player_name = parts[0]
        if parts[1].startswith('"') and parts[2].isdigit():
            reason = parts[1].strip('"')
            time_seconds = int(parts[2])
            return player_name, reason, time_seconds
    
    return "", "", 0

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    
    if message.channel.id != MODS_CHANNEL_ID:
        return
    
    print(f"Received command in MODS channel: {message.content}")
    
    if message.content.startswith('!'):
        content = message.content[1:].strip()
        print(f"Processing command: {content}")
        
        if content == 'banlist':
            await rcon_listener.send_command('banlist', "banlist", message.channel)
            
        elif content == 'players':
            await rcon_listener.send_command('players', "players", message.channel)
            
        elif content.startswith('teleportpos'):
            # Parse coordinates and player name
            teleport_content = content[11:].strip()
            
            # Split by spaces, coordinates are first, player name is the rest
            parts = teleport_content.split(maxsplit=1)
            if len(parts) == 2:
                coordinates = parts[0].strip()
                player_name = parts[1].strip()
                
                # Validate coordinates format
                coord_pattern = r'^-?\d+(\.\d+)?,-?\d+(\.\d+)?,-?\d+(\.\d+)?$'
                if not re.match(coord_pattern, coordinates):
                    await message.channel.send("❌ Error: Invalid coordinates format! Use: x,y,z")
                    return
                
                # Send command with quotes around player name (for spaces in name)
                rcon_command = f'teleportpos {coordinates} "{player_name}"'
                await rcon_listener.send_command(rcon_command, "teleportpos", message.channel)
            else:
                await message.channel.send("❌ Usage: `!teleportpos x,y,z player_name`\nExample: `!teleportpos 100,50,200 Atomic_Acid69`")
            
        elif content.startswith('printpos'):
            player_name, _ = parse_player_command(content, 8)
            
            if player_name:
                rcon_command = f'printpos "{player_name}"'
                await rcon_listener.send_command(rcon_command, "printpos", message.channel, rcon_command)
            else:
                await message.channel.send("❌ Usage: `!printpos player_name`")
            
        elif content.startswith('mutevoice'):
            player_name, _ = parse_player_command(content, 9)
            
            if player_name:
                rcon_command = f'mutevoice {player_name}'
                await rcon_listener.send_command(rcon_command, "mutevoice", message.channel)
            else:
                await message.channel.send("❌ Usage: `!mutevoice player_name`")
            
        elif content.startswith('unmutevoice'):
            player_name, _ = parse_player_command(content, 11)
            
            if player_name:
                rcon_command = f'unmutevoice {player_name}'
                await rcon_listener.send_command(rcon_command, "unmutevoice", message.channel)
            else:
                await message.channel.send("❌ Usage: `!unmutevoice player_name`")
            
        elif content.startswith('mutechat'):
            player_name, _ = parse_player_command(content, 8)
            
            if player_name:
                rcon_command = f'mutechat {player_name}'
                await rcon_listener.send_command(rcon_command, "mutechat", message.channel)
            else:
                await message.channel.send("❌ Usage: `!mutechat player_name`")
            
        elif content.startswith('unmutechat'):
            player_name, _ = parse_player_command(content, 10)
            
            if player_name:
                rcon_command = f'unmutechat {player_name}'
                await rcon_listener.send_command(rcon_command, "unmutechat", message.channel)
            else:
                await message.channel.send("❌ Usage: `!unmutechat player_name`")
        
        elif content.startswith('kick'):
            player_name, _ = parse_player_command(content, 4)
            
            if player_name:
                rcon_command = f'kick {player_name}'
                await rcon_listener.send_command(rcon_command, "kick", message.channel)
            else:
                await message.channel.send("❌ Usage: `!kick player_name`")
        
        elif content.startswith('banid'):
            player_name, reason, time_seconds = parse_ban_command(content, 5)
            
            if player_name and time_seconds >= 0:
                # Build RCON command
                if reason:
                    rcon_command = f'banid {player_name} "{reason}" {time_seconds}'
                else:
                    rcon_command = f'banid {player_name} {time_seconds}'
                
                await rcon_listener.send_command(rcon_command, "banid", message.channel, rcon_command)
            else:
                await message.channel.send("❌ Usage: `!banid player_name \"reason\" time_in_seconds`\nExamples:\n• `!banid player_name \"being toxic\" 300`\n• `!banid player_name 0` (permanent)\n• `!banid Atomic_me 600` (10 minutes)")
        
        elif content.startswith('unban'):
            player_name, _ = parse_player_command(content, 5)
            
            if player_name:
                rcon_command = f'unban {player_name}'
                await rcon_listener.send_command(rcon_command, "unban", message.channel)
            else:
                await message.channel.send("❌ Usage: `!unban player_id`")
        
        elif content == 'help':
            help_text = """
**👥 Player Commands:**
• `!players` - List all online players
• `!printpos player_name` - Get player's position
• `!teleportpos x,y,z player_name` - Teleport player

**🔇 Voice/Chat Moderation:**
• `!mutevoice player` - Mute voice chat
• `!unmutevoice player` - Unmute voice chat
• `!mutechat player` - Mute text chat
• `!unmutechat player` - Unmute text chat

**👢 Kick/Ban Commands:**
• `!kick player` - Kick a player
• `!banid player_name "reason" time_in_seconds` - Ban a player
  Examples:
    • `!banid player_name "being toxic" 300` - Ban for 5 minutes with reason
    • `!banid player_name 0` - Permanent ban (no reason)
    • `!banid player_name 600` - Ban for 10 minutes (no reason)
• `!unban player_id` - Unban a player
• `!banlist` - List banned players

**📋 Other Commands:**
• `!help` - Show this help
"""
            await message.channel.send(help_text)
        
        else:
            await message.channel.send(f"❌ Unknown command: `{content}`")

# Run the bot
bot.run(TOKEN)
