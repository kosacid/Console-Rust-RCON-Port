import discord
import asyncio
import os
import re
import configparser
import json
import websockets
from typing import Optional, Dict, Set
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get values from .env
TOKEN = os.getenv('DISCORD_TOKEN')
SERVER_IP = os.getenv('SERVER_IP')
RCON_PORT = int(os.getenv('RCON_PORT'))
RCON_PASSWORD = os.getenv('RCON_PASSWORD')
LOGS_CHANNEL_ID = int(os.getenv('LOGS_CHANNEL'))

class RCONListener:
    """RCON WebSocket client that listens to ALL server messages"""
    
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
    
    async def listen_continuously(self, process_callback):
        """Listen continuously for messages and call the callback for each"""
        while True:
            try:
                if not self.is_connected or not self.websocket:
                    print("Not connected, reconnecting...")
                    if not await self.connect():
                        await asyncio.sleep(5)
                        continue
                
                # Wait for message
                raw_response = await self.websocket.recv()
                
                # Process the message
                try:
                    response_data = json.loads(raw_response)
                    message = response_data.get("Message", "")
                    
                    if isinstance(message, str):
                        message = message.replace("\u0000", "").strip()
                    
                    # Call the callback with the message
                    if message and process_callback:
                        await process_callback(message)
                        
                except json.JSONDecodeError:
                    print(f"Non-JSON message: {raw_response}")
                    
            except websockets.exceptions.ConnectionClosed:
                print("Connection closed, reconnecting...")
                self.is_connected = False
                await asyncio.sleep(5)
            except Exception as e:
                print(f"Error listening: {e}")
                await asyncio.sleep(1)
    
    async def send_command(self, command: str) -> bool:
        """Send command to WebSocket RCON server"""
        try:
            if not self.is_connected or not self.websocket:
                if not await self.connect():
                    return False
            
            command_data = {
                "Message": command,
                "Identifier": self.command_counter,
                "Type": "Command",
                "Stacktrace": None
            }
            
            await self.websocket.send(json.dumps(command_data))
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

class EmoteManager:
    """Manages emote commands and cooldowns"""
    
    def __init__(self):
        self.emote_cooldowns: Dict[str, datetime] = {}
        self.coordinates_config = configparser.ConfigParser()
        self.emotes_data: Dict = {}
        self.COORDINATES_FILE = 'player_coordinates.ini'
        self.EMOTES_FILE = 'emote_commands.ini'
        self.current_printpos_player: Optional[str] = None
        self.processed_chat_ids: Set[str] = set()
        self.start_time = datetime.now()
        
        # List of ALL emotes
        self.ALL_EMOTES = self._get_all_emotes()
        
        # Load configurations
        self._load_configurations()
    
    def _get_all_emotes(self):
        """Get list of ALL emotes"""
        return [
            # Combat slots
            "d11_quick_chat_combat_slot_7",
            "d11_quick_chat_combat_slot_6",
            "d11_quick_chat_combat_slot_5",
            "d11_quick_chat_combat_slot_4",
            "d11_quick_chat_combat_slot_3",
            "d11_quick_chat_combat_slot_2",
            "d11_quick_chat_combat_slot_1",
            "d11_quick_chat_combat_slot_0",
            
            # Building slots
            "d11_quick_chat_building_slot_7",
            "d11_quick_chat_building_slot_6",
            "d11_quick_chat_building_slot_5",
            "d11_quick_chat_building_slot_4",
            "d11_quick_chat_building_slot_3",
            "d11_quick_chat_building_slot_2",
            "d11_quick_chat_building_slot_1",
            "d11_quick_chat_building_slot_0",
            
            # Activities phrase format
            "d11_quick_chat_activities_phrase_format d11_Medicine",
            "d11_quick_chat_activities_phrase_format d11_Metal_Fragments",
            "d11_quick_chat_activities_phrase_format d11_Scrap",
            "d11_quick_chat_activities_phrase_format d11_Water",
            "d11_quick_chat_activities_phrase_format d11_Food",
            "d11_quick_chat_activities_phrase_format d11_Metal",
            "d11_quick_chat_activities_phrase_format d11_Wood",
            "d11_quick_chat_activities_phrase_format d11_Stone",
            
            # Questions slots
            "d11_quick_chat_questions_slot_7",
            "d11_quick_chat_questions_slot_6",
            "d11_quick_chat_questions_slot_5",
            "d11_quick_chat_questions_slot_4",
            "d11_quick_chat_questions_slot_3",
            "d11_quick_chat_questions_slot_2",
            "d11_quick_chat_questions_slot_1",
            "d11_quick_chat_questions_slot_0",
            
            # Responses slots
            "d11_quick_chat_responses_slot_7",
            "d11_quick_chat_responses_slot_6",
            "d11_quick_chat_responses_slot_5",
            "d11_quick_chat_responses_slot_4",
            "d11_quick_chat_responses_slot_3",
            "d11_quick_chat_responses_slot_2",
            "d11_quick_chat_responses_slot_1",
            "d11_quick_chat_responses_slot_0",
            
            # Orders slots
            "d11_quick_chat_orders_slot_7",
            "d11_quick_chat_orders_slot_6",
            "d11_quick_chat_orders_slot_5",
            "d11_quick_chat_orders_slot_4",
            "d11_quick_chat_orders_slot_3",
            "d11_quick_chat_orders_slot_2",
            "d11_quick_chat_orders_slot_1",
            "d11_quick_chat_orders_slot_0",
            
            # Location slots
            "d11_quick_chat_location_slot_7",
            "d11_quick_chat_location_slot_6",
            "d11_quick_chat_location_slot_5",
            "d11_quick_chat_location_slot_4",
            "d11_quick_chat_location_slot_3",
            "d11_quick_chat_location_slot_2",
            "d11_quick_chat_location_slot_1",
            "d11_quick_chat_location_slot_0",
            
            # I need phrase format
            "d11_quick_chat_i_need_phrase_format d11_Scrap",
            "d11_quick_chat_i_need_phrase_format metal.refined",
            "d11_quick_chat_i_need_phrase_format d11_Metal_Fragments",
            "d11_quick_chat_i_need_phrase_format stones",
            "d11_quick_chat_i_need_phrase_format d11_Wood",
            "d11_quick_chat_i_need_phrase_format d11_Water",
            "d11_quick_chat_i_need_phrase_format d11_Food",
            "d11_quick_chat_i_need_phrase_format lowgradefuel",
            
            # I have phrase format
            "d11_quick_chat_i_have_phrase_format d11_Scrap",
            "d11_quick_chat_i_have_phrase_format lowgradefuel",
            "d11_quick_chat_i_have_phrase_format d11_Food",
            "d11_quick_chat_i_have_phrase_format d11_Water",
            "d11_quick_chat_i_have_phrase_format bow.hunting",
            "d11_quick_chat_i_have_phrase_format pickaxe",
            "d11_quick_chat_i_have_phrase_format hatchet",
            "d11_quick_chat_i_have_phrase_format metal.refined"
        ]
    
    def _load_configurations(self):
        """Load coordinate and emote configurations"""
        # Load existing coordinates
        if os.path.exists(self.COORDINATES_FILE):
            self.coordinates_config.read(self.COORDINATES_FILE)
            print(f"Loaded coordinates for {len(self.coordinates_config.sections())} players from file")
        
        # Load or create emote configuration
        self._create_default_emotes_config()
        self.emotes_data = self._read_emote_config()
        print(f"Loaded {len(self.emotes_data)} emote configurations from file")
    
    def _read_emote_config(self) -> Dict:
        """Read emote configuration from file with custom parsing"""
        emotes_data_dict = {}
        
        if not os.path.exists(self.EMOTES_FILE):
            return emotes_data_dict
        
        with open(self.EMOTES_FILE, 'r') as f:
            lines = f.readlines()
        
        current_section = None
        time_value = '0'
        commands = []
        
        for line in lines:
            line = line.strip()
            
            # Skip comments and empty lines
            if not line or line.startswith('#'):
                continue
            
            # Section header
            if line.startswith('[') and line.endswith(']'):
                # Save previous section if exists
                if current_section:
                    emotes_data_dict[current_section] = {
                        'time': time_value,
                        'commands': commands.copy()
                    }
                
                # Start new section
                current_section = line[1:-1]
                time_value = '0'
                commands = []
            
            # Time setting
            elif line.startswith('time ='):
                time_value = line.split('=', 1)[1].strip()
            
            # Command (any other non-empty line in a section)
            elif current_section and line:
                commands.append(line)
        
        # Save the last section
        if current_section:
            emotes_data_dict[current_section] = {
                'time': time_value,
                'commands': commands.copy()
            }
        
        return emotes_data_dict
    
    def _create_default_emotes_config(self):
        """Create default emote configuration file if it doesn't exist"""
        if not os.path.exists(self.EMOTES_FILE):
            print(f"Creating default emote configuration file: {self.EMOTES_FILE}")
            
            # Create initial emotes data for ALL emotes
            default_emotes_data = {}
            
            for emote in self.ALL_EMOTES:
                default_emotes_data[emote] = {
                    'time': '0',  # All disabled by default
                    'commands': []
                }
            
            # Add example configurations for some emotes
            # Wood request (60 minute cooldown with commands)
            if "d11_quick_chat_i_need_phrase_format d11_Wood" in default_emotes_data:
                default_emotes_data["d11_quick_chat_i_need_phrase_format d11_Wood"] = {
                    'time': '60',
                    'commands': [
                        'giveto {player} wood 3000',
                        'givedrop {player} stones 3000 3'
                    ]
                }
            
            # Building slot 1 (store position, 1 minute cooldown)
            if "d11_quick_chat_building_slot_1" in default_emotes_data:
                default_emotes_data["d11_quick_chat_building_slot_1"] = {
                    'time': '10',
                    'commands': ['printpos {player}']
                }
            
            # Combat slot 1 (teleport to stored position, 10 min cooldown)
            if "d11_quick_chat_combat_slot_1" in default_emotes_data:
                default_emotes_data["d11_quick_chat_combat_slot_1"] = {
                    'time': '10',
                    'commands': ['teleportpos {player}']
                }
            
            # Metal fragments request (30 minute cooldown)
            if "d11_quick_chat_i_need_phrase_format d11_Metal_Fragments" in default_emotes_data:
                default_emotes_data["d11_quick_chat_i_need_phrase_format d11_Metal_Fragments"] = {
                    'time': '30',
                    'commands': ['giveto {player} metal.fragments 1000']
                }
            
            # Water request (20 minute cooldown)
            if "d11_quick_chat_i_need_phrase_format d11_Water" in default_emotes_data:
                default_emotes_data["d11_quick_chat_i_need_phrase_format d11_Water"] = {
                    'time': '20',
                    'commands': ['giveto {player} water 5']
                }
            
            # Food request (20 minute cooldown)
            if "d11_quick_chat_i_need_phrase_format d11_Food" in default_emotes_data:
                default_emotes_data["d11_quick_chat_i_need_phrase_format d11_Food"] = {
                    'time': '20',
                    'commands': ['giveto {player} can.beans 10']
                }
            
            # Scrap request (45 minute cooldown)
            if "d11_quick_chat_i_need_phrase_format d11_Scrap" in default_emotes_data:
                default_emotes_data["d11_quick_chat_i_need_phrase_format d11_Scrap"] = {
                    'time': '45',
                    'commands': ['giveto {player} scrap 500']
                }
            
            # Save to file
            self._write_emote_config(default_emotes_data)
            
            print(f"Default emote configuration created with {len(self.ALL_EMOTES)} emotes")
    
    def _write_emote_config(self, emotes_data_dict: Dict):
        """Write emote configuration to file"""
        with open(self.EMOTES_FILE, 'w') as f:
            f.write("# Emote Configuration File\n")
            f.write("# Format:\n")
            f.write("# [emote_name]\n")
            f.write("# time = 60  # Cooldown in minutes (0 = disabled)\n")
            f.write("# command1\n")
            f.write("# command2\n")
            f.write("# ...\n\n")
            
            for emote_name, data in sorted(emotes_data_dict.items()):
                f.write(f"[{emote_name}]\n")
                f.write(f"time = {data['time']}\n")
                
                for command in data['commands']:
                    f.write(f"{command}\n")
                
                f.write("\n")
    
    def extract_coordinates(self, line: str) -> Optional[str]:
        """Extract coordinates from printpos response line"""
        try:
            pattern = r'\(([-\d\.]+),\s*([-\d\.]+),\s*([-\d\.]+)\)'
            match = re.search(pattern, line)
            
            if match:
                x, y, z = match.groups()
                return f"{x},{y},{z}"
        except Exception as e:
            print(f"Error extracting coordinates: {e}")
        return None
    
    def store_player_coordinates(self, player_name: str, coordinates: str) -> bool:
        """Store or update coordinates for a player"""
        try:
            if not self.coordinates_config.has_section(player_name):
                self.coordinates_config.add_section(player_name)
            
            self.coordinates_config.set(player_name, 'position', coordinates)
            
            with open(self.COORDINATES_FILE, 'w') as configfile:
                self.coordinates_config.write(configfile)
            
            print(f"Stored coordinates for {player_name}: {coordinates}")
            return True
            
        except Exception as e:
            print(f"Error storing coordinates: {e}")
            return False
    
    def get_player_coordinates(self, player_name: str) -> Optional[str]:
        """Get stored coordinates for a player"""
        if self.coordinates_config.has_section(player_name):
            return self.coordinates_config.get(player_name, 'position', fallback=None)
        return None
    
    async def handle_emote_request(self, rcon_listener, logs_channel, player_name: str, emote_name: str):
        """Handle emote request with cooldown check and command execution"""
        current_time = datetime.now()
        
        # Check if emote exists in configuration
        if emote_name not in self.emotes_data:
            print(f"Emote not found in configuration: {emote_name}")
            return
        
        # Get cooldown time from config
        try:
            cooldown_minutes = int(self.emotes_data[emote_name]['time'])
        except ValueError:
            cooldown_minutes = 0
        
        # If cooldown is 0, emote is disabled
        if cooldown_minutes == 0:
            print(f"Emote {emote_name} is disabled (cooldown=0)")
            return
        
        # Create a unique key for player+emote cooldown
        cooldown_key = f"{player_name}_{emote_name}"
        
        # Check if player is on cooldown for this emote
        if cooldown_key in self.emote_cooldowns:
            last_request = self.emote_cooldowns[cooldown_key]
            time_diff = current_time - last_request
            
            if time_diff < timedelta(minutes=cooldown_minutes):
                # Still on cooldown
                cooldown_left = timedelta(minutes=cooldown_minutes) - time_diff
                minutes_left = int(cooldown_left.total_seconds() / 60)
                seconds_left = int(cooldown_left.total_seconds() % 60)
                
                message = f"⏳ {player_name} used {emote_name} but has {minutes_left}m {seconds_left}s cooldown left."
                print(message)
                await self._send_to_logs(logs_channel, message)
                return
        
        # Get commands from config
        commands = self.emotes_data[emote_name]['commands']
        
        # Track if any commands were successfully executed
        commands_executed = 0
        teleport_failed = False
        
        # Handle commands
        if commands:
            # Execute each command
            for command in commands:
                if not command.strip():
                    continue
                    
                # Replace {player} placeholder with actual player name
                formatted_command = command.replace('{player}', player_name)
                
                # Special handling for specific commands
                if command.startswith('printpos'):
                    # Add quotes for printpos command
                    formatted_command = f'printpos "{player_name}"'
                    if await rcon_listener.send_command(formatted_command):
                        commands_executed += 1
                        print(f"Executed command for {player_name}: {formatted_command}")
                        
                        # Store player name for coordinate response
                        self.current_printpos_player = player_name
                    
                elif command.startswith('teleportpos'):
                    # Teleport player to their stored coordinates
                    coordinates = self.get_player_coordinates(player_name)
                    if coordinates:
                        formatted_command = f'teleportpos {coordinates} "{player_name}"'
                        if await rcon_listener.send_command(formatted_command):
                            commands_executed += 1
                            print(f"Executed command for {player_name}: {formatted_command}")
                    else:
                        # Mark teleport as failed but don't send message yet
                        teleport_failed = True
                        # Don't count this as executed since it failed
                        continue
                else:
                    # Regular command (giveto, givedrop, etc.)
                    if await rcon_listener.send_command(formatted_command):
                        commands_executed += 1
                        print(f"Executed command for {player_name}: {formatted_command}")
            
            # Only update cooldown if commands were successfully executed
            if commands_executed > 0:
                self.emote_cooldowns[cooldown_key] = current_time
                
                # Log the request
                log_message = f"✅ {player_name} used {emote_name} at {current_time.strftime('%Y-%m-%d %H:%M:%S')} - executed {commands_executed} commands"
                print(log_message)
                await self._send_to_logs(logs_channel, log_message)
                return
            else:
                # No commands were executed successfully
                if teleport_failed:
                    # Send teleport failure message
                    log_message = f"❌ {player_name} has no coordinates stored for teleport."
                else:
                    # Send general failure message
                    log_message = f"❌ {player_name} used {emote_name} but no commands were executed successfully."
                
                print(log_message)
                await self._send_to_logs(logs_channel, log_message)
                return
        else:
            # No commands configured, just log the usage
            log_message = f"📝 {player_name} used {emote_name} at {current_time.strftime('%Y-%m-%d %H:%M:%S')} (no commands configured)"
            print(log_message)
            await self._send_to_logs(logs_channel, log_message)
            return
    
    async def _send_to_logs(self, logs_channel, message: str):
        """Send message to logs channel"""
        if logs_channel:
            try:
                await logs_channel.send(message)
            except Exception as e:
                print(f"Error sending to logs Discord: {e}")
    
    async def process_message(self, rcon_listener, logs_channel, message: str):
        """Process incoming RCON message"""
        # Check for chat messages
        if message.strip().startswith('{'):
            try:
                chat_data = json.loads(message)
                username = chat_data.get("Username", "")
                message_content = chat_data.get("Message", "").strip()
                user_id = chat_data.get("UserId", 0)
                timestamp = chat_data.get("Time", 0)
                
                chat_id = f"{user_id}_{timestamp}_{message_content}"
                
                if chat_id in self.processed_chat_ids:
                    return
                
                self.processed_chat_ids.add(chat_id)
                print(f"Chat: {username} - {message_content}")
                
                # Check for any emote in the message
                for emote_name in self.emotes_data.keys():
                    if emote_name in message_content:
                        print(f"Found emote in chat: {emote_name}")
                        await self.handle_emote_request(rcon_listener, logs_channel, username, emote_name)
                        return  # Process only one emote per chat message
                        
            except json.JSONDecodeError:
                pass
        
        # Check for coordinate responses from printpos command
        elif re.search(r'\([-\d\.]+,\s*[-\d\.]+,\s*[-\d\.]+\)', message):
            print(f"Found possible coordinates in message: {message}")
            coordinates = self.extract_coordinates(message)
            if coordinates and self.current_printpos_player:
                player_name = self.current_printpos_player
                self.store_player_coordinates(player_name, coordinates)
                
                log_message = f"📍 Saved coordinates for {player_name}: `{coordinates}`"
                print(log_message)
                await self._send_to_logs(logs_channel, log_message)
                
                self.current_printpos_player = None

# Discord bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)

# Global instances
rcon_listener = None
emote_manager = None
logs_channel = None

@bot.event
async def on_ready():
    print(f'Bot ready: {bot.user}')
    
    global rcon_listener, emote_manager, logs_channel
    
    # Get logs channel
    logs_channel = bot.get_channel(LOGS_CHANNEL_ID)
    
    # Initialize managers
    emote_manager = EmoteManager()
    rcon_listener = RCONListener(SERVER_IP, RCON_PORT, RCON_PASSWORD)
    
    # Connect and start listening
    if await rcon_listener.connect():
        # Start listening with callback
        bot.loop.create_task(rcon_listener.listen_continuously(
            lambda msg: emote_manager.process_message(rcon_listener, logs_channel, msg)
        ))

@bot.event
async def on_message(message):
    # Bot doesn't respond to Discord commands
    if message.author == bot.user:
        return
    return

# Run the bot
bot.run(TOKEN)
