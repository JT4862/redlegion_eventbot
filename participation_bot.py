import discord
from discord.ext import tasks, commands
import datetime
import time
import os
import asyncio

intents = discord.Intents.default()
intents.members = True
intents.voice_states = True
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

LOG_CHANNEL_ID = os.getenv('TEXT_CHANNEL_ID')  # Fetch from environment variable
if not LOG_CHANNEL_ID:
    raise ValueError("TEXT_CHANNEL_ID environment variable not set")

active_voice_channels = {}  # Dict of channel_id: channel object
event_names = {}  # Dict of channel_id: event_name
member_times = {}  # Dict of channel_id: {member_id: duration}
last_checks = {}  # Dict of channel_id: {member_id: last_seen_time}
start_logging_lock = asyncio.Lock()  # Lock to prevent concurrent start_logging executions

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')

@bot.event
async def on_voice_state_update(member, before, after):
    for channel_id, active_channel in active_voice_channels.items():
        if active_channel and log_members.is_running():
            current_time = time.time()
            # Member joins the active voice channel
            if after.channel == active_channel and before.channel != active_channel:
                last_checks[channel_id][member.id] = current_time
            # Member leaves the active voice channel
            elif before.channel == active_channel and after.channel != active_channel:
                if member.id in last_checks.get(channel_id, {}):
                    duration = current_time - last_checks[channel_id][member.id]
                    member_times[channel_id][member.id] = member_times.get(channel_id, {}).get(member.id, 0) + duration
                    del last_checks[channel_id][member_id]

@tasks.loop(minutes=5)
async def log_members():
    log_channel = bot.get_channel(int(LOG_CHANNEL_ID))
    if not log_channel:
        print(f"Text channel ID {LOG_CHANNEL_ID} not found")
        return

    for channel_id, active_channel in active_voice_channels.items():
        if active_channel and channel_id in event_names:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            current_time = time.time()
            # Update times for members still in the channel
            for member_id in list(last_checks.get(channel_id, {}).keys()):
                if bot.get_user(member_id) in active_channel.members:
                    duration = current_time - last_checks[channel_id][member_id]
                    member_times[channel_id][member_id] = member_times.get(channel_id, {}).get(member_id, 0) + duration
                    last_checks[channel_id][member_id] = current_time
            # Build embed
            embed = discord.Embed(
                title=f"Event: {event_names[channel_id]}",
                description=f"**Channel**: {active_channel.name}\n**Time**: {timestamp}",
                color=discord.Color.blue(),
                timestamp=datetime.datetime.now()
            )
            members = active_channel.members
            if members:
                participant_list = ""
                for member in members:
                    total_seconds = member_times.get(channel_id, {}).get(member.id, 0)
                    hours, remainder = divmod(int(total_seconds), 3600)
                    minutes, seconds = divmod(remainder, 60)
                    time_str = f"{hours}h {minutes}m {seconds}s"
                    participant_list += f"{member.display_name}: {time_str}\n"
                embed.add_field(name="Participants", value=participant_list, inline=False)
            else:
                embed.add_field(name="Participants", value="No participants", inline=False)
            # Send to dedicated Discord text channel
            try:
                await log_channel.send(embed=embed)
            except discord.errors.Forbidden:
                print(f"Error: Bot lacks permission to send messages to channel {LOG_CHANNEL_ID}")

@bot.command()
async def start_logging(ctx):
    async with start_logging_lock:  # Prevent concurrent executions
        if ctx.author.voice and ctx.author.voice.channel:
            channel_id = ctx.author.voice.channel.id
            active_voice_channels[channel_id] = ctx.author.voice.channel
            await ctx.send("Please provide the event name for this logging session.")
            def check(m):
                return m.author == ctx.author and m.channel == ctx.channel
            try:
                msg = await bot.wait_for('message', check=check, timeout=60.0)
                event_name = msg.content.strip()
                if event_name:
                    # Initialize tracking for this channel
                    event_names[channel_id] = event_name
                    member_times[channel_id] = {}
                    last_checks[channel_id] = {}
                    # Initialize current members
                    current_time = time.time()
                    for member in active_voice_channels[channel_id].members:
                        last_checks[channel_id][member.id] = current_time
                    # Notify logging channel with embed
                    log_channel = bot.get_channel(int(LOG_CHANNEL_ID))
                    if log_channel:
                        try:
                            embed = discord.Embed(
                                title="Logging Started",
                                description=f"**Event**: {event_name}\n**Channel**: {active_voice_channels[channel_id].name}",
                                color=discord.Color.green(),
                                timestamp=datetime.datetime.now()
                            )
                            await log_channel.send(embed=embed)
                        except discord.errors.Forbidden:
                            await ctx.send(f"Error: Bot lacks permission to send messages to channel {LOG_CHANNEL_ID}")
                            return
                    else:
                        await ctx.send(f"Text channel ID {LOG_CHANNEL_ID} not found")
                        return
                    if not log_members.is_running():
                        log_members.start()
                        await ctx.send(f"Bot is running and logging started for {active_voice_channels[channel_id].name} (Event: {event_name}, every 30 minutes).")
                    else:
                        await ctx.send(f"Logging started for {active_voice_channels[channel_id].name} (Event: {event_name}).")
                else:
                    await ctx.send("Event name cannot be empty. Please try again.")
            except discord.ext.commands.errors.CommandInvokeError:
                await ctx.send("Timed out waiting for event name. Please try again.")
                del active_voice_channels[channel_id]  # Clean up if timed out
        else:
            await ctx.send("You must be in a voice channel to start logging.")

@bot.command()
async def stop_logging(ctx):
    if ctx.author.voice and ctx.author.voice.channel:
        channel_id = ctx.author.voice.channel.id
        if channel_id in active_voice_channels:
            # Update times for members still in channel before stopping
            current_time = time.time()
            for member_id in list(last_checks.get(channel_id, {}).keys()):
                if bot.get_user(member_id) in active_voice_channels[channel_id].members:
                    duration = current_time - last_checks[channel_id][member_id]
                    member_times[channel_id][member_id] = member_times.get(channel_id, {}).get(member_id, 0) + duration
            # Build summary embed
            log_channel = bot.get_channel(int(LOG_CHANNEL_ID))
            if log_channel:
                try:
                    summary_embed = discord.Embed(
                        title="Session Summary",
                        description=f"**Event**: {event_names[channel_id]}\n**Channel**: {active_voice_channels[channel_id].name}",
                        color=discord.Color.orange(),
                        timestamp=datetime.datetime.now()
                    )
                    participant_summary = ""
                    total_participants = len(member_times.get(channel_id, {}))
                    for member_id, total_seconds in member_times.get(channel_id, {}).items():
                        member = await bot.fetch_user(member_id)
                        hours, remainder = divmod(int(total_seconds), 3600)
                        minutes, seconds = divmod(remainder, 60)
                        time_str = f"{hours}h {minutes}m {seconds}s"
                        participant_summary += f"{member.display_name}: {time_str}\n"
                    summary_embed.add_field(name=f"Participants ({total_participants})", value=participant_summary or "No participants", inline=False)
                    await log_channel.send(embed=summary_embed)
                except discord.errors.Forbidden:
                    await ctx.send(f"Error: Bot lacks permission to send messages to channel {LOG_CHANNEL_ID}")
                except discord.errors.HTTPException:
                    await ctx.send("Error: Failed to fetch user data for summary.")
            else:
                await ctx.send(f"Text channel ID {LOG_CHANNEL_ID} not found")
            # Notify logging channel with stop embed
            if log_channel:
                try:
                    embed = discord.Embed(
                        title="Logging Stopped",
                        description=f"**Event**: {event_names[channel_id]}\n**Channel**: {active_voice_channels[channel_id].name}",
                        color=discord.Color.red(),
                        timestamp=datetime.datetime.now()
                    )
                    await log_channel.send(embed=embed)
                except discord.errors.Forbidden:
                    await ctx.send(f"Error: Bot lacks permission to send messages to channel {LOG_CHANNEL_ID}")
            # Clean up
            del active_voice_channels[channel_id]
            del event_names[channel_id]
            del member_times[channel_id]
            del last_checks[channel_id]
            if not active_voice_channels:  # Stop task if no channels are being logged
                log_members.stop()
            await ctx.send("Participation logging stopped for this channel.")
        else:
            await ctx.send("No logging is active for this voice channel.")
    else:
        await ctx.send("You must be in a voice channel to stop logging.")

bot.run(os.getenv('DISCORD_TOKEN'))  # Fetch from environment variable