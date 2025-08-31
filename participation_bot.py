import discord
from discord.ext import tasks, commands
import datetime
import time
import os

intents = discord.Intents.default()
intents.members = True
intents.voice_states = True

bot = commands.Bot(command_prefix='!', intents=intents)

LOG_CHANNEL_ID = os.getenv('TEXT_CHANNEL_ID')  # Fetch from environment variable
if not LOG_CHANNEL_ID:
    raise ValueError("TEXT_CHANNEL_ID environment variable not set")

active_voice_channel = None  # Store the voice channel to log
event_name = None  # Store the event name
member_times = {}  # Track member participation times
last_check = {}  # Store last seen time for each member

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')

@bot.event
async def on_voice_state_update(member, before, after):
    global active_voice_channel, member_times, last_check
    if active_voice_channel and log_members.is_running():
        current_time = time.time()
        # Member joins the active voice channel
        if after.channel == active_voice_channel and before.channel != active_voice_channel:
            last_check[member.id] = current_time
        # Member leaves the active voice channel
        elif before.channel == active_voice_channel and after.channel != active_voice_channel:
            if member.id in last_check:
                duration = current_time - last_check[member.id]
                member_times[member.id] = member_times.get(member.id, 0) + duration
                del last_check[member.id]

@tasks.loop(minutes=30)
async def log_members():
    global active_voice_channel, event_name, member_times, last_check
    if active_voice_channel and event_name:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        current_time = time.time()
        
        # Update times for members still in the channel
        for member_id in list(last_check.keys()):
            if bot.get_user(member_id) in active_voice_channel.members:
                duration = current_time - last_check[member_id]
                member_times[member_id] = member_times.get(member.id, 0) + duration
                last_check[member.id] = current_time
        
        # Build log message
        log = f"{timestamp} - Event: {event_name} (Channel: {active_voice_channel.name})\nParticipants:\n"
        members = active_voice_channel.members
        if members:
            for member in members:
                total_seconds = member_times.get(member.id, 0)
                hours, remainder = divmod(int(total_seconds), 3600)
                minutes, seconds = divmod(remainder, 60)
                time_str = f"{hours}h {minutes}m {seconds}s"
                log += f"  {member.name}#{member.discriminator}: {time_str}\n"
        else:
            log += "  None\n"
        
        # Send to dedicated Discord text channel
        log_channel = bot.get_channel(int(LOG_CHANNEL_ID))  # Convert to int for channel ID
        if log_channel:
            await log_channel.send(log)
        else:
            print(f"Text channel ID {LOG_CHANNEL_ID} not found")
    else:
        print("No active voice channel or event name set for logging")

@bot.command()
async def start_logging(ctx):
    global active_voice_channel, event_name, member_times, last_check
    if ctx.author.voice and ctx.author.voice.channel:
        active_voice_channel = ctx.author.voice.channel
        await ctx.send("Please provide the event name for this logging session.")
        
        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel
        
        try:
            msg = await bot.wait_for('message', check=check, timeout=60.0)
            event_name = msg.content.strip()
            if event_name:
                # Reset tracking for new logging session
                member_times = {}
                last_check = {}
                # Initialize current members
                current_time = time.time()
                for member in active_voice_channel.members:
                    last_check[member.id] = current_time
                if not log_members.is_running():
                    log_members.start()
                    await ctx.send(f"Bot is running and logging started for {active_voice_channel.name} (Event: {event_name}, every 30 minutes). Everything is set up correctly!")
                else:
                    await ctx.send(f"Logging is already running, now updated to log {active_voice_channel.name} (Event: {event_name}). Bot is running and everything is set up correctly!")
            else:
                await ctx.send("Event name cannot be empty. Please try again.")
        except discord.ext.commands.errors.CommandInvokeError:
            await ctx.send("Timed out waiting for event name. Please try again.")
    else:
        await ctx.send("You must be in a voice channel to start logging.")

@bot.command()
async def stop_logging(ctx):
    global active_voice_channel, event_name, member_times, last_check
    if log_members.is_running():
        # Update times for members still in channel before stopping
        current_time = time.time()
        for member_id in list(last_check.keys()):
            if bot.get_user(member_id) in active_voice_channel.members:
                duration = current_time - last_check[member.id]
                member_times[member.id] = member_times.get(member.id, 0) + duration
        log_members.stop()
        active_voice_channel = None
        event_name = None
        member_times = {}
        last_check = {}
        await ctx.send("Participation logging stopped.")
    else:
        await ctx.send("Logging is not running.")

bot.run(os.getenv('DISCORD_TOKEN'))  # Fetch from environment variable