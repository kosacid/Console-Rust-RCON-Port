import asyncio
import json
import websockets
from typing import Optional

class RCON:
    """Minimal RCON WebSocket client"""
    
    def __init__(self, server_ip: str, rcon_port: int, rcon_password: str):
        self.uri = f"ws://{server_ip}:{rcon_port}/{rcon_password}"
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.command_counter = 1
    
    async def connect(self) -> bool:
        """Establish connection to server"""
        try:
            print(f"Connecting to {self.uri}")
            self.websocket = await websockets.connect(self.uri)
            print("Connected successfully")
            return True
        except Exception as e:
            print(f"Connection failed: {e}")
            return False
    
    async def close(self) -> None:
        """Close the connection"""
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
    
    async def send(self, command: str) -> Optional[str]:
        """
        Send a command to the server
        
        Args:
            command: The RCON command to send
            
        Returns:
            Server response as string, or None if failed
        """
        if not self.websocket:
            print("Not connected")
            return None
        
        try:
            # Create command with unique ID
            command_id = self.command_counter
            data = {
                "Message": command,
                "Identifier": command_id,
                "Type": "Command",
                "Stacktrace": None
            }
            
            # Send command
            await self.websocket.send(json.dumps(data))
            print(f"Sent: {command}")
            
            # Wait for response
            response = await self.websocket.recv()
            response_data = json.loads(response)
            
            # Get response text
            message = response_data.get("Message", "")
            message = message.replace("\u0000", "").strip()
            
            self.command_counter += 1
            return message
            
        except Exception as e:
            print(f"Error sending command: {e}")
            return None
    
    async def __aenter__(self):
        """Context manager entry"""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        await self.close()


async def main():
    """Simple usage example"""
    
    # Your server details
    SERVER_IP = "127.0.0.1"
    RCON_PORT = 29316
    RCON_PASSWORD = "password"
    
    # Create connection
    rcon = RCON(SERVER_IP, RCON_PORT, RCON_PASSWORD)
    
    try:
        # Connect
        if not await rcon.connect():
            return
        
        print("\nConnected! Type commands below.")
        print("Examples: 'players', 'time', 'say \"Hello\"'")
        print("Type 'quit' to exit\n")
        
        # Interactive command loop
        while True:
            try:
                # Get user input
                command = input("RCON> ").strip()
                
                if command.lower() in ['quit', 'exit', 'q']:
                    break
                
                if not command:
                    continue
                
                # Send command and show response
                response = await rcon.send(command)
                if response:
                    print(f"Response: {response}")
                else:
                    print("No response or error")
                    
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Error: {e}")
                
    finally:
        # Clean up
        await rcon.close()
        print("\nDisconnected")
if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())
