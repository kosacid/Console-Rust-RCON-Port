import asyncio
import json
import websockets
from typing import Optional
from datetime import datetime

class RCONListener:
    """RCON WebSocket client that listens to ALL server messages"""
    
    def __init__(self, server_ip: str, rcon_port: int, rcon_password: str):
        self.uri = f"ws://{server_ip}:{rcon_port}/{rcon_password}"
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
    
    async def connect(self) -> bool:
        """Establish connection to server"""
        try:
            print(f"Connecting to {self.uri}")
            self.websocket = await websockets.connect(self.uri)
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
            return False
    
    async def listen(self) -> None:
        """Continuously listen for ALL server messages"""
        if not self.websocket:
            print("Not connected")
            return
        
        print("\nListening for ALL server messages...")
        print("Raw JSON data will be displayed")
        print("Press Ctrl+C to stop\n")
        
        message_count = 0
        
        try:
            while True:
                # Wait for message from server
                raw_response = await self.websocket.recv()
                
                # Try to parse as JSON first
                try:
                    response_data = json.loads(raw_response)
                    
                    # Extract all available information
                    message = response_data.get("Message", "")
                    message_type = response_data.get("Type", "")
                    identifier = response_data.get("Identifier", "")
                    stacktrace = response_data.get("Stacktrace", "")
                    
                    message_count += 1
                    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                    
                    print(f"\n{'='*60}")
                    print(f"Message #{message_count} | {timestamp}")
                    print(f"Type: {message_type} | ID: {identifier}")
                    print(f"{'='*60}")
                    
                    # Print message content if it exists
                    if message:
                        print("Message content:")
                        if isinstance(message, str):
                            # Show raw string with escape sequences
                            print(f"Raw: {repr(message)}")
                            # Show cleaned version
                            clean_message = message.replace("\u0000", "").strip()
                            if clean_message:
                                print(f"Clean: {clean_message}")
                        else:
                            print(f"Type: {type(message).__name__} | Value: {message}")
                    
                    # Print stacktrace if it exists
                    if stacktrace:
                        print(f"Stacktrace: {stacktrace}")
                    
                    # Print full JSON for debugging
                    print(f"\nFull JSON:")
                    print(json.dumps(response_data, indent=2))
                    
                except json.JSONDecodeError:
                    # If not JSON, show raw data
                    message_count += 1
                    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                    
                    print(f"\n{'='*60}")
                    print(f"Message #{message_count} | {timestamp}")
                    print(f"{'='*60}")
                    print("Non-JSON data received:")
                    print(f"Raw bytes: {repr(raw_response)}")
                    print(f"Length: {len(raw_response)} bytes")
                    
                except Exception as parse_error:
                    message_count += 1
                    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                    
                    print(f"\n{'='*60}")
                    print(f"Message #{message_count} | {timestamp}")
                    print(f"{'='*60}")
                    print(f"Parse error: {parse_error}")
                    print(f"Raw data: {repr(raw_response)}")
                    
        except websockets.exceptions.ConnectionClosed as e:
            print(f"\nConnection closed: {e}")
        except Exception as e:
            print(f"\nError listening: {e}")
            import traceback
            traceback.print_exc()
    
    async def close(self) -> None:
        """Close the connection"""
        if self.websocket:
            await self.websocket.close()
            self.websocket = None


async def main():
    """Listen-only RCON client that shows EVERYTHING"""
    
    # Your server details
    SERVER_IP = "127.0.0.1"
    RCON_PORT = 29316
    RCON_PASSWORD = "password"
    
    # Create listener
    listener = RCONListener(SERVER_IP, RCON_PORT, RCON_PASSWORD)
    
    try:
        # Connect
        if not await listener.connect():
            return
        
        # Start listening
        await listener.listen()
                
    except KeyboardInterrupt:
        print("\nStopping listener...")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Clean up
        await listener.close()
        print("\nDisconnected")


if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())
