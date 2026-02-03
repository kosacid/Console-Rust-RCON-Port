import asyncio
import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
import logging
import time

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

# Bot setup
intents = discord.Intents.default()
intents.voice_states = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Channel configuration
RUST_CHANNEL_ID = os.getenv('RUST_CHANNEL_ID')
RADIO_STREAM_URL = "http://www.rustedak.com:8024/stream.mp3"

# Track current voice client and retry state
voice_client = None
connection_attempts = 0
MAX_RETRIES = 5
RETRY_DELAY = 5  # seconds

@bot.event
async def on_ready():
    print(f'{bot.user} is ready!')
    print(f'📻 Rust Radio Bot')
    print(f'Channel ID: {RUST_CHANNEL_ID}')
    
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.listening,
        name="Rust Radio"
    ))

async def safe_connect(channel, retry_count=0):
    """Safely connect to a voice channel with retry logic"""
    global voice_client, connection_attempts
    
    if retry_count >= MAX_RETRIES:
        logger.error(f"❌ Failed to connect after {MAX_RETRIES} attempts")
        return None
    
    try:
        logger.info(f"🔗 Attempting to connect to {channel.name} (attempt {retry_count + 1}/{MAX_RETRIES})")
        
        # Try to connect
        vc = await channel.connect(timeout=10.0, reconnect=False)
        
        # Reset connection attempts on success
        connection_attempts = 0
        
        logger.info(f"✅ Successfully connected to {channel.name}")
        return vc
        
    except asyncio.TimeoutError:
        logger.warning(f"⚠️ Connection timeout to {channel.name}, retrying...")
        await asyncio.sleep(RETRY_DELAY)
        return await safe_connect(channel, retry_count + 1)
        
    except discord.errors.ClientException as e:
        if "Already connected" in str(e):
            logger.info("ℹ️ Already connected to a voice channel")
            return voice_client
        else:
            logger.error(f"❌ Client error: {e}")
            await asyncio.sleep(RETRY_DELAY)
            return await safe_connect(channel, retry_count + 1)
            
    except Exception as e:
        logger.error(f"❌ Connection error: {e}")
        await asyncio.sleep(RETRY_DELAY)
        return await safe_connect(channel, retry_count + 1)

async def safe_play_radio(vc, retry_count=0):
    """Safely play radio with retry logic"""
    if retry_count >= MAX_RETRIES:
        logger.error(f"❌ Failed to play radio after {MAX_RETRIES} attempts")
        return False
    
    try:
        # FFmpeg options for streaming
        ffmpeg_options = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            'options': '-vn -b:a 128k'
        }
        
        logger.info(f"🎵 Attempting to play radio stream (attempt {retry_count + 1}/{MAX_RETRIES})")
        
        source = discord.FFmpegPCMAudio(RADIO_STREAM_URL, **ffmpeg_options)
        vc.play(source)
        
        # Wait to confirm it's playing
        await asyncio.sleep(3)
        
        if vc.is_playing():
            logger.info("✅ Radio is now playing")
            return True
        else:
            logger.warning("⚠️ Radio not playing, retrying...")
            vc.stop()
            await asyncio.sleep(RETRY_DELAY)
            return await safe_play_radio(vc, retry_count + 1)
            
    except Exception as e:
        logger.error(f"❌ Error playing radio: {e}")
        await asyncio.sleep(RETRY_DELAY)
        return await safe_play_radio(vc, retry_count + 1)

@bot.event
async def on_voice_state_update(member, before, after):
    global voice_client, connection_attempts
    
    # Ignore bot's own voice state changes
    if member.bot:
        return
    
    # Check if the target channel is configured
    if not RUST_CHANNEL_ID:
        return
    
    target_channel_id = int(RUST_CHANNEL_ID)
    
    # User joined the target channel
    if after.channel and after.channel.id == target_channel_id:
        logger.info(f"👤 {member.name} joined {after.channel.name}")
        
        # Check if we need to connect
        if not voice_client or not voice_client.is_connected():
            try:
                # Clear previous voice client if exists but not connected
                if voice_client:
                    try:
                        await voice_client.disconnect(force=True)
                    except:
                        pass
                    voice_client = None
                
                # Try to connect
                voice_client = await safe_connect(after.channel)
                
                if voice_client and voice_client.is_connected():
                    # Try to play radio
                    success = await safe_play_radio(voice_client)
                    if success:
                        logger.info(f"▶️ Playing Darkwave Radio in {after.channel.name}")
                    else:
                        logger.error("❌ Failed to start radio, disconnecting...")
                        await safe_disconnect(voice_client)
                        voice_client = None
                
            except Exception as e:
                logger.error(f"❌ Failed to handle join: {e}")
                voice_client = None
        else:
            # Already connected, check if we should restart radio
            if voice_client and voice_client.is_connected():
                if not voice_client.is_playing():
                    logger.info("🔄 Radio stopped, restarting...")
                    success = await safe_play_radio(voice_client)
                    if not success:
                        logger.error("❌ Failed to restart radio")
    
    # User left the target channel
    if before.channel and before.channel.id == target_channel_id:
        logger.info(f"👤 {member.name} left {before.channel.name}")
        
        if voice_client and voice_client.is_connected():
            # Check if anyone is left (excluding bots)
            human_members = [m for m in before.channel.members if not m.bot]
            if len(human_members) == 0:
                logger.info("📭 No humans left in channel, disconnecting...")
                await safe_disconnect(voice_client)
                voice_client = None

async def safe_disconnect(vc):
    """Safely disconnect from voice channel"""
    try:
        if vc.is_playing():
            vc.stop()
        
        # Small delay before disconnecting
        await asyncio.sleep(1)
        
        await vc.disconnect(force=True)
        logger.info("✅ Disconnected from voice channel")
        
    except Exception as e:
        logger.error(f"❌ Error during disconnect: {e}")
        try:
            await vc.disconnect(force=True)
        except:
            pass

@bot.event
async def on_error(event, *args, **kwargs):
    logger.error(f"⚠️ Error in event {event}: {args} {kwargs}")

@bot.event
async def on_command_error(ctx, error):
    logger.error(f"⚠️ Command error: {error}")

# Command to manually check status
@bot.command(name='radiostatus')
async def radio_status(ctx):
    """Check the radio bot status"""
    global voice_client
    
    status = []
    status.append(f"**📻 Rust Radio Bot Status**")
    status.append(f"Target Channel: <#{RUST_CHANNEL_ID}>")
    
    if voice_client and voice_client.is_connected():
        status.append(f"✅ **Connected** to {voice_client.channel.name}")
        status.append(f"🎵 **Playing**: {'Yes' if voice_client.is_playing() else 'No'}")
        status.append(f"👥 **Listeners**: {len([m for m in voice_client.channel.members if not m.bot])}")
    else:
        status.append("❌ **Not connected**")
    
    await ctx.send("\n".join(status))

# Command to manually restart radio
@bot.command(name='restartradio')
@commands.has_permissions(manage_channels=True)
async def restart_radio(ctx):
    """Manually restart the radio stream (Admin only)"""
    global voice_client
    
    if voice_client and voice_client.is_connected():
        if voice_client.is_playing():
            voice_client.stop()
        
        success = await safe_play_radio(voice_client)
        if success:
            await ctx.send("✅ Radio stream restarted!")
        else:
            await ctx.send("❌ Failed to restart radio stream")
    else:
        await ctx.send("❌ Bot is not connected to a voice channel")

# Run the bot with retry logic
async def main():
    retry_count = 0
    max_bot_retries = 3
    
    while retry_count < max_bot_retries:
        try:
            logger.info(f"🤖 Starting bot (attempt {retry_count + 1}/{max_bot_retries})")
            
            if not RUST_CHANNEL_ID:
                logger.error("❌ ERROR: RUST_CHANNEL_ID not found in .env file!")
                print("\nAdd to your .env file:")
                print("DISCORD_TOKEN=your_bot_token_here")
                print("RUST_CHANNEL_ID=your_channel_id_here")
                exit(1)
            
            token = os.getenv('DISCORD_TOKEN')
            if not token:
                logger.error("❌ ERROR: DISCORD_TOKEN not found in .env file!")
                exit(1)
            
            print("\n" + "="*50)
            print("📻 Rust Radio Bot Starting...")
            print("✅ Auto-joins when users enter the channel")
            print("✅ Auto-leaves when everyone leaves")
            print("✅ Auto-retry on failures")
            print("✅ Commands: !radiostatus, !restartradio")
            print("="*50 + "\n")
            
            await bot.start(token)
            
        except KeyboardInterrupt:
            logger.info("👋 Bot stopped by user")
            break
            
        except Exception as e:
            retry_count += 1
            logger.error(f"❌ Bot crashed: {e}")
            
            if retry_count < max_bot_retries:
                logger.info(f"🔄 Restarting bot in 10 seconds...")
                await asyncio.sleep(10)
            else:
                logger.error(f"❌ Bot failed after {max_bot_retries} attempts")
                break

if __name__ == "__main__":
    asyncio.run(main())
