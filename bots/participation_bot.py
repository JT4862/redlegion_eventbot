import discord
from discord.ext import tasks, commands
import datetime
import time
import os
import asyncio
import psycopg2

intents = discord.Intents.default()
intents.members = True
intents.voice_states = True
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

LOG_CHANNEL_ID = os.getenv('TEXT_CHANNEL_ID')
if not LOG_CHANNEL_ID:
    raise ValueError("TEXT_CHANNEL_ID environment variable not set")
ORG_ROLE_ID = "1143413611184795658"

active_voice_channels = {}
event_names = {}
member_times = {}
last_checks = {}
start_logging_lock = asyncio.Lock()

# Custom check for role-based command permission
def has_org_role():
    def predicate(ctx):
        role = discord.utils.get(ctx.author.roles, id=int(ORG_ROLE_ID))
        if not role:
            raise commands.MissingPermissions("You need the OrgMember role to use this command.")
        return True
    return commands.check(predicate)

# Initialize database
def init_db():
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS entries (
        user_id TEXT,
        month_year TEXT,
        entry_count INTEGER DEFAULT 0,
        PRIMARY KEY (user_id, month_year)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS events (
        event_id SERIAL PRIMARY KEY,
        channel_id TEXT,
        event_name TEXT,
        start_time TEXT,
        end_time TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS participation (
        channel_id TEXT,
        member_id TEXT,
        duration REAL
    )''')
    conn.commit()
    conn.close()

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    init_db()

@bot.event
async def on_voice_state_update(member, before, after):
    for channel_id, active_channel in active_voice_channels.items():
        if active_channel and log_members.is_running():
            current_time = time.time()
            if after.channel == active_channel and before.channel != active_channel:
                last_checks[channel_id][member.id] = current_time
            elif before.channel == active_channel and after.channel != active_channel:
                if member.id in last_checks.get(channel_id, {}):
                    duration = current_time - last_checks[channel_id][member.id]
                    member_times[channel_id][member.id] = member_times.get(channel_id, {}).get(member.id, 0) + duration
                    del last_checks[channel_id][member.id]

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
            for member_id in list(last_checks.get(channel_id, {}).keys()):
                if bot.get_user(member_id) in active_channel.members:
                    duration = current_time - last_checks[channel_id][member_id]
                    member_times[channel_id][member_id] = member_times.get(channel_id, {}).get(member_id, 0) + duration
                    last_checks[channel_id][member_id] = current_time
            embed = discord.Embed(
                title=f"Event: {event_names[channel_id]}",
                description=f"**Channel**: {active_channel.name}\n**Time**: {timestamp}",
                color=discord.Color.blue(),
                timestamp=datetime.datetime.now()
            )
            members = active_channel.members
            org_participants = ""
            non_org_participants = ""
            if members:
                for member in members:
                    total_seconds = member_times.get(channel_id, {}).get(member.id, 0)
                    hours, remainder = divmod(int(total_seconds), 3600)
                    minutes, seconds = divmod(remainder, 60)
                    time_str = f"{hours}h {minutes}m {seconds}s"
                    if str(ORG_ROLE_ID) in [str(role.id) for role in member.roles]:
                        org_participants += f"{member.display_name}: {time_str}\n"
                    else:
                        non_org_participants += f"{member.display_name}: {time_str}\n"
                if org_participants:
                    embed.add_field(name="Org Members", value=org_participants, inline=False)
                if non_org_participants:
                    embed.add_field(name="Non-Org Members", value=non_org_participants, inline=False)
                if not org_participants and not non_org_participants:
                    embed.add_field(name="Participants", value="No participants", inline=False)
            else:
                embed.add_field(name="Participants", value="No participants", inline=False)
            try:
                await log_channel.send(embed=embed)
            except discord.errors.Forbidden:
                print(f"Error: Bot lacks permission to send messages to channel {LOG_CHANNEL_ID}")

@bot.command()
@has_org_role()
async def start_logging(ctx):
    async with start_logging_lock:
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
                    event_names[channel_id] = event_name
                    member_times[channel_id] = {}
                    last_checks[channel_id] = {}
                    current_time = time.time()
                    for member in active_voice_channels[channel_id].members:
                        last_checks[channel_id][member.id] = current_time
                    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
                    c = conn.cursor()
                    c.execute("INSERT INTO events (channel_id, event_name, start_time) VALUES (%s, %s, %s)",
                              (channel_id, event_name, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                    conn.commit()
                    conn.close()
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
                    if not log_members.is_running():
                        log_members.start()
                    await ctx.send(f"Bot is running and logging started for {active_voice_channels[channel_id].name} (Event: {event_name}, every 5 minutes).")
                else:
                    await ctx.send("Event name cannot be empty. Please try again.")
            except discord.ext.commands.errors.CommandInvokeError:
                await ctx.send("Timed out waiting for event name. Please try again.")
                del active_voice_channels[channel_id]
        else:
            await ctx.send("You must be in a voice channel to start logging.")

@bot.command()
@has_org_role()
async def stop_logging(ctx):
    if ctx.author.voice and ctx.author.voice.channel:
        channel_id = ctx.author.voice.channel.id
        print(f"Active channels: {active_voice_channels}")
        print(f"Channel ID: {channel_id}")
        if channel_id in active_voice_channels:
            current_time = time.time()
            conn = psycopg2.connect(os.getenv("DATABASE_URL"))
            c = conn.cursor()
            for member_id in list(last_checks.get(channel_id, {}).keys()):
                member = ctx.guild.get_member(member_id)
                if member:
                    duration = current_time - last_checks[channel_id][member_id]
                    member_times[channel_id][member_id] = member_times.get(channel_id, {}).get(member_id, 0) + duration
                    c.execute("INSERT INTO participation (channel_id, member_id, duration) VALUES (%s, %s, %s)",
                              (channel_id, str(member_id), duration))
            c.execute("UPDATE events SET end_time = %s WHERE channel_id = %s AND end_time IS NULL",
                      (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), channel_id))
            conn.commit()
            conn.close()
            log_channel = bot.get_channel(int(LOG_CHANNEL_ID))
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
            del active_voice_channels[channel_id]
            del event_names[channel_id]
            del member_times[channel_id]
            del last_checks[channel_id]
            if not active_voice_channels:
                log_members.stop()
            await ctx.send("Successfully stopped logging for this channel.")
        else:
            await ctx.send("No logging is active for this voice channel.")
    else:
        await ctx.send("You must be in a voice channel to stop logging.")

@bot.command()
@has_org_role()
async def pick_winner(ctx):
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    c = conn.cursor()
    current_month = datetime.datetime.now().strftime("%B-%Y")
    c.execute("SELECT user_id, entry_count FROM entries WHERE month_year = %s", (current_month,))
    entries = c.fetchall()
    if not entries:
        await ctx.send("No entries available for this month.")
        conn.close()
        return
    winner_id = max(entries, key=lambda x: x[1])[0]
    winner = await bot.fetch_user(int(winner_id))
    await ctx.send(f"Congratulations {winner.display_name}! You are the winner for {current_month} with {max(entries, key=lambda x: x[1])[1]} entries!")
    conn.close()

bot.run(os.getenv('DISCORD_TOKEN'))