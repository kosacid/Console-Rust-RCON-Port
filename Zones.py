import discord
import os
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
ZONES_CHANNEL_ID = int(os.getenv('ZONES'))

class RCONListener:
    """RCON WebSocket client that listens to ALL server messages"""
    
    def __init__(self, server_ip: str, rcon_port: int, rcon_password: str):
        self.uri = f"ws://{server_ip}:{rcon_port}/{rcon_password}"
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.command_counter = 1
        self.is_connected = False
        self.pending_responses = {}
    
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
            if not self.is_connected or not self.websocket:
                if not await self.connect():
                    return False
            
            current_id = self.command_counter
            
            if discord_channel:
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

async def process_rcon_message(bot, rcon_listener: RCONListener, message: str, identifier: int):
    """Process incoming RCON message"""
    if not message:
        return
    
    # Check if this is a response to a command we sent
    if identifier in rcon_listener.pending_responses:
        command_info = rcon_listener.pending_responses[identifier]
        command_type = command_info.get("type", "")
        discord_channel = command_info.get("channel")
        
        if message and discord_channel:
            try:
                await discord_channel.send(f"🗺️ **Zone Command Response**:\n```\n{message}\n```")
            except Exception as e:
                print(f"Error sending response: {e}")
        
        # Clean up
        if identifier in rcon_listener.pending_responses:
            del rcon_listener.pending_responses[identifier]

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

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    
    if message.channel.id != ZONES_CHANNEL_ID:
        return
    
    print(f"Received command in ZONES channel: {message.content}")
    
    if message.content.startswith('!'):
        content = message.content[1:].strip()
        print(f"Processing command in zones channel: {content}")
        
        # CREATE CUSTOM ZONE
        if content.startswith('createcustomzone'):
            try:
                parts = content.split(maxsplit=1)
                if len(parts) < 2:
                    await message.channel.send("""
❌ **Incorrect format for createcustomzone**
**Usage:** `!createcustomzone "Test" x,y,z rotation shape size pvp npcdamage radiation buildingdamage building`
""")
                    return
                
                rcon_command = f'zones.createcustomzone {parts[1]}'
                success = await rcon_listener.send_command(rcon_command, "zone_create", message.channel)
                
                if success:
                    await message.channel.send(f"🏗️ **Creating Custom Zone**\n`{rcon_command}`")
                
            except Exception as e:
                await message.channel.send(f"❌ Error: {str(e)}")
        
        # EDIT CUSTOM ZONE
        elif content.startswith('editcustomzone'):
            try:
                parts = content.split(maxsplit=3)
                if len(parts) < 4:
                    await message.channel.send("❌ Usage: `!editcustomzone \"ZoneName\" \"Setting\" \"Value\"`\nExample: `!editcustomzone \"Test\" showarea 1`")
                    return
                
                zone_name = parts[1]
                setting = parts[2]
                value = parts[3]
                
                rcon_command = f'zones.editcustomzone {zone_name} {setting} {value}'
                success = await rcon_listener.send_command(rcon_command, "zone_edit", message.channel)
                
                if success:
                    await message.channel.send(f"⚙️ **Editing Zone '{zone_name}'**\n`{rcon_command}`")
                
            except Exception as e:
                await message.channel.send(f"❌ Error: {str(e)}")
        
        # CUSTOM ZONE INFO
        elif content.startswith('customzoneinfo'):
            try:
                parts = content.split(maxsplit=1)
                if len(parts) < 2:
                    await message.channel.send("❌ Usage: `!customzoneinfo \"ZoneName\"`")
                    return
                
                zone_name = parts[1].strip('"')
                rcon_command = f'zones.customzoneinfo "{zone_name}"'
                success = await rcon_listener.send_command(rcon_command, "zone_info", message.channel)
                
                if success:
                    await message.channel.send(f"📊 **Getting info for zone: {zone_name}**")
                
            except Exception as e:
                await message.channel.send(f"❌ Error: {str(e)}")
        
        # LIST CUSTOM ZONES
        elif content == 'listcustomzones':
            rcon_command = 'zones.listcustomzones'
            success = await rcon_listener.send_command(rcon_command, "zone_list", message.channel)
            
            if success:
                await message.channel.send("📋 **Listing all custom zones...**")
        
        # DELETE CUSTOM ZONE
        elif content.startswith('deletecustomzone'):
            try:
                parts = content.split(maxsplit=1)
                if len(parts) < 2:
                    await message.channel.send("❌ Usage: `!deletecustomzone \"ZoneName\"`")
                    return
                
                zone_name = parts[1].strip('"')
                rcon_command = f'zones.deletecustomzone "{zone_name}"'
                success = await rcon_listener.send_command(rcon_command, "zone_delete", message.channel)
                
                if success:
                    await message.channel.send(f"🗑️ **Deleting zone: {zone_name}**")
                
            except Exception as e:
                await message.channel.send(f"❌ Error: {str(e)}")
        
        # LIST MONUMENT KILLZONES
        elif content == 'listmonumentkillzones':
            rcon_command = 'zones.listmonumentkillzones'
            success = await rcon_listener.send_command(rcon_command, "monument_list", message.channel)
            
            if success:
                await message.channel.send("🏛️ **Listing all monument killzones...**")
        
        # CLEAR MONUMENT KILLZONES
        elif content == 'clearmonumentkillzones':
            rcon_command = 'zones.clearmonumentkillzones'
            success = await rcon_listener.send_command(rcon_command, "monument_clear", message.channel)
            
            if success:
                await message.channel.send("🧹 **Clearing all monument killzones...**")
        
        # SET MONUMENT KILLZONE
        elif content.startswith('setmonumentkillzone'):
            try:
                parts = content.split(maxsplit=2)
                if len(parts) < 3:
                    await message.channel.send("❌ Usage: `!setmonumentkillzone \"monumentname\" 0/1`\nExample: `!setmonumentkillzone gas_station_1 1`")
                    return
                
                monument_name = parts[1]
                state = parts[2]
                
                if state not in ['0', '1']:
                    await message.channel.send("❌ State must be 0 (deactivate) or 1 (activate)")
                    return
                
                rcon_command = f'zones.setmonumentkillzone {monument_name} {state}'
                success = await rcon_listener.send_command(rcon_command, "monument_set", message.channel)
                
                if success:
                    action = "Activating" if state == '1' else "Deactivating"
                    await message.channel.send(f"🏛️ **{action} monument killzone: {monument_name}**")
                
            except Exception as e:
                await message.channel.send(f"❌ Error: {str(e)}")
        
        # EDIT MONUMENT ZONE
        elif content.startswith('editmonumentzone'):
            try:
                parts = content.split(maxsplit=3)
                if len(parts) < 4:
                    await message.channel.send("❌ Usage: `!editmonumentzone \"MonumentName\" \"Setting\" \"Value\"`\nExample: `!editmonumentzone \"gas_station_1\" \"radiation\" \"25\"`")
                    return
                
                monument_name = parts[1]
                setting = parts[2]
                value = parts[3]
                
                rcon_command = f'zones.editcustomzone {monument_name} {setting} {value}'
                success = await rcon_listener.send_command(rcon_command, "monument_edit", message.channel)
                
                if success:
                    await message.channel.send(f"🏛️ **Editing monument zone: {monument_name}**\n`{rcon_command}`")
                
            except Exception as e:
                await message.channel.send(f"❌ Error: {str(e)}")
        
        # HELP COMMAND
        elif content == 'help':
            help_text = """
**🏗️ ZONE COMMANDS:**
  `!createcustomzone "Test" x,y,z rotation shape size pvp npcdamage radiation buildingdamage building`
  `!createcustomzone "Test" 10,10,10 45 box 150,150,150 1 1 0 1 1`
  `!createcustomzone "Test" 10,10,10 45 sphere 150 1 1 0 1 1`

  `!editcustomzone "Test" enabled 0/1`
  `!editcustomzone "Test" position 10,10,10`
  `!editcustomzone "Test" rotation 45`
  `!editcustomzone "Test" type box/sphere`
  `!editcustomzone "Test" size 150,150,150 (box=150,150,150/`sphere=150)
  `!editcustomzone "Test" allowpvpdamage 0/1`
  `!editcustomzone "Test" allownpcdamage 0/1`
  `!editcustomzone "Test" radiationdamage 0`
  `!editcustomzone "Test" allowbuildingdamage 0/1`
  `!editcustomzone "Test" allowbuilding 0/1`
  `!editcustomzone "Test" showarea 0/1`
  `!editcustomzone "Test" color 0,0,0/255,255,255`
  `!editcustomzone "Test" showchatmessage 0/1`
  `!editcustomzone "Test" entermessage "hello"`
  `!editcustomzone "Test" leavemessage "by"`

• `!customzoneinfo "ZoneName"`
• `!listcustomzones`
• `!deletecustomzone "ZoneName"`

**🏛️ MONUMENT ZONES:**
• `!listmonumentkillzones`
• `!clearmonumentkillzones`
• `!setmonumentkillzone "monumentname" 0/1`
• `!editmonumentzone "gas_station_1" radiation 25`
"""
            await message.channel.send(help_text)
        
        else:
            await message.channel.send(f"❌ Unknown command: `{content}`. Type `!help` for available commands.")

# Run the bot
bot.run(TOKEN)
