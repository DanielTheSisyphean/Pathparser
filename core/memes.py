import asyncio
import random
import re
import time
import platform
import logging
import discord
from datetime import datetime, timezone
import aiosqlite

# Global state for last trigger time (needs to be moved to a better place optimally, but kept here for now)
last_trigger_time = {}

""" SERVER SIDE PING.
async def ping(host: str, port: int = 443) -> float | None:
    start = time.perf_counter()

    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=5,
        )

        latency = (time.perf_counter() - start) * 1000

        writer.close()
        await writer.wait_closed()

        return latency

    except Exception:
        return None
"""


async def ping(host: str) -> float | None:
    if platform.system().lower() == "windows":
        command = ["ping", "-n", "1", host]
    else:
        command = ["ping", "-c", "1", host]

    proc = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)

    if proc.returncode != 0:
        return None

    output = stdout.decode()

    match = re.search(r"time[=<]?\s*([\d.]+)\s*ms", output, re.IGNORECASE)
    return float(match.group(1)) if match else None


async def ping_test():
    google, discord = await asyncio.gather(
        ping("google.com"),
        ping("discord.com")
    )

    return {
        "google": google,
        "discord": discord,
    }

class ResponseFollowupView(discord.ui.View):
    def __init__(self, followups):
        super().__init__(timeout=180)
        for button_name, response in followups:
            button = discord.ui.Button(label=button_name, style=discord.ButtonStyle.secondary)
            button.callback = self.get_callback(response)
            self.add_item(button)

    def get_callback(self, response):
        async def callback(interaction: discord.Interaction):
            await interaction.response.send_message(response, ephemeral=True)
        return callback

async def ensure_response_tables(db: aiosqlite.Connection):
    await db.execute("""
    CREATE TABLE IF NOT EXISTS Response_Trigger (
        TriggerID INTEGER PRIMARY KEY AUTOINCREMENT,
        Trigger TEXT NOT NULL,
        MatchType TEXT NOT NULL, -- 'contains', 'exact', 'regex'
        Response TEXT NOT NULL,
        Enabled BOOLEAN DEFAULT 1,
        Likelihood INTEGER,
        Cooldown INTEGER DEFAULT 0 -- in seconds 
    );
    """)
    # Safely migrate existing databases that don't have Cooldown column
    try:
        async with db.execute("PRAGMA table_info(Response_Trigger)") as cursor:
            cols = await cursor.fetchall()
            col_names = [col[1] for col in cols]
            if "Cooldown" not in col_names:
                await db.execute("ALTER TABLE Response_Trigger ADD COLUMN Cooldown INTEGER DEFAULT 0")
                await db.commit()
    except Exception:
        pass

    await db.execute("""
    CREATE TABLE IF NOT EXISTS Response_Roles (
        TriggerID INTEGER NOT NULL,
        RoleID INTEGER NOT NULL,
        FOREIGN KEY (TriggerID) REFERENCES Response_Trigger(TriggerID)
    );
    """)
    await db.execute("""
    CREATE TABLE IF NOT EXISTS Response_Channels (
        TriggerID INTEGER NOT NULL,
        ChannelID INTEGER NOT NULL,
        FOREIGN KEY (TriggerID) REFERENCES Response_Trigger(TriggerID)
    );
    """)
    await db.execute("""
    CREATE TABLE IF NOT EXISTS Response_Users (
        TriggerID INTEGER NOT NULL,
        UserID INTEGER NOT NULL,
        FOREIGN KEY (TriggerID) REFERENCES Response_Trigger(TriggerID)
    );
    """)
    await db.execute("""
    CREATE TABLE IF NOT EXISTS Response_Followup (
        TriggerID INTEGER NOT NULL,
        buttonname TEXT,
        response TEXT, 
        FOREIGN KEY (TriggerID) REFERENCES Response_Trigger(TriggerID)
    );
    """)
    await db.commit()

async def seed_default_triggers(db: aiosqlite.Connection):
    # Set default cooldowns for einstein and monkey if they exist but have 0/NULL cooldown
    try:
        await db.execute("UPDATE Response_Trigger SET Cooldown = 600 WHERE Trigger IN ('einstein', 'monkey') AND (Cooldown IS NULL OR Cooldown = 0)")
        await db.commit()
    except Exception:
        pass

    async with db.execute("SELECT COUNT(*) FROM Response_Trigger") as cursor:
        row = await cursor.fetchone()
        if row and row[0] > 0:
            return
            
    defaults = [
        ('einstein', 'contains', 'https://i.insider.com/641ca0f5d67fe70018a376ca?width=800&format=jpeg&auto=webp', 100, 600, [], [], []),
        ('monkey', 'contains', 'https://i.ytimg.com/vi/tLHqnn1ZkAM/maxresdefault.jpg', 98, 600, [], [], []),
        ('monkey', 'contains', 'https://tenor.com/view/mmmm-monkey-monkey-ug-master-oogway-oogway-gif-19727561', 2, 600, [], [], []),
        ('.*', 'regex', 'https://cdn.discordapp.com/attachments/479089930816192513/1309682327860805733/7YjmdoZxhSgAAAAASUVORK5CYII.png?ex=67768b77&is=677539f7&hm=9ebebdcbf4c8f1266649c1d1d66dbcdad58b18f1a219da101094a96f910d396c&', 2, 0, [217873501313433600], [], []),
        ('.*', 'regex', 'https://cdn.discordapp.com/attachments/479089930816192513/1309681542653546560/764rjEg82XSZ0fJzf8fVPtjhVRebgAAAAASUVORK5CYII.png?ex=67768abc&is=6775393c&hm=1728ae88544b6323a3d280dc552bb48eff922f3c0cf3983e341654cb4eb61022&', 2, 0, [217873501313433600], [], []),
        ('.*', 'regex', 'https://cdn.discordapp.com/attachments/479089930816192513/1309681106013917284/wdUWYUf3MwhkwAAAABJRU5ErkJggg.png?ex=67768a54&is=677538d4&hm=bd846ce7d3f0ab3361170189bfc57520357ada3740ec61af1cfe7e9a5be3cf2d&', 2, 0, [217873501313433600], [], []),
        ('.*', 'regex', 'https://cdn.discordapp.com/attachments/479089930816192513/1322782239452430467/4OGDuJJjqwVJFdQkOvEm71fkWBFQVWFFhRYEWBFQWWBRYAfoXa71Wo11RYEWBFQVWFFhRYCkFPgUCd2wuGYpcgwAAAABJRU5ErkJggg.png?ex=6776bdb5&is=67756c35&hm=35c2b303e206d87b60edc261f3134c6a072af9255a5a721e1a0cfa377fcb20a6&', 2, 0, [217873501313433600], [], []),
        ('stabbed', 'contains', 'https://media.tenor.com/-BpjJcwntaYAAAAM/you-fucking-what-epic-npc-dnd.gif', 100, 0, [318796580662542347], [], []),
        ('hit by a car', 'contains', 'https://media.makeameme.org/created/yoooooooooooooooo-how-did.jpg', 100, 0, [318796580662542347], [], []),
        ('car wreck', 'contains', 'https://media.makeameme.org/created/yoooooooooooooooo-how-did.jpg', 100, 0, [318796580662542347], [], []),
        ('car crash', 'contains', 'https://media.makeameme.org/created/yoooooooooooooooo-how-did.jpg', 100, 0, [318796580662542347], [], []),
        ('hit by a truck', 'contains', 'https://media.makeameme.org/created/yoooooooooooooooo-how-did.jpg', 100, 0, [318796580662542347], [], []),
        ('got shot', 'contains', 'https://cdn.discordapp.com/attachments/479089930816192513/1330383824315613275/hq720.png?ex=678dc7fd&is=678c767d&hm=a4ae84c616d84827555e18cee3a61337d2f65f36eae0caf89dc9d06bd42377bd&', 100, 0, [318796580662542347], [], []),
        ('set me on fire', 'contains', 'https://i.imgflip.com/pwruu.jpg', 100, 0, [318796580662542347], [], []),
        ('got robbed', 'contains', 'https://media.tenor.com/9G-H14djSBkAAAAM/wallet-john-travolta.gif', 100, 0, [318796580662542347], [], []),
        ('%soulisawesome', 'contains', 'https://y.yarn.co/6447b331-7aa2-4785-a5a0-9d20fa4dae35_text.gif', 100, 0, [], [], [])
    ]
    for trigger, match_type, response, likelihood, cooldown, users, roles, channels in defaults:
        async with db.execute(
            "INSERT INTO Response_Trigger (Trigger, MatchType, Response, Enabled, Likelihood, Cooldown) VALUES (?, ?, ?, 1, ?, ?)",
            (trigger, match_type, response, likelihood, cooldown)
        ) as cursor:
            trigger_id = cursor.lastrowid
            for u in users:
                await db.execute("INSERT INTO Response_Users (TriggerID, UserID) VALUES (?, ?)", (trigger_id, u))
            for r in roles:
                await db.execute("INSERT INTO Response_Roles (TriggerID, RoleID) VALUES (?, ?)", (trigger_id, r))
            for c in channels:
                await db.execute("INSERT INTO Response_Channels (TriggerID, ChannelID) VALUES (?, ?)", (trigger_id, c))
    await db.commit()

async def meme_handler(message: discord.Message):

    random_number = random.randint(1, 50)

    if message.guild:
        try:
            async with aiosqlite.connect(f"pathparser_{message.guild.id}.sqlite") as db:
                await ensure_response_tables(db)
                await seed_default_triggers(db)
                
                async with db.execute("SELECT TriggerID, Trigger, MatchType, Response, Likelihood, Cooldown FROM Response_Trigger WHERE Enabled = 1") as cursor:
                    triggers = await cursor.fetchall()
                    
                matched_trigger = None
                for trigger_id, trigger_str, match_type, response_text, likelihood, cooldown in triggers:
                    is_match = False
                    msg_lower = message.content.lower()
                    trig_lower = trigger_str.lower()
                    
                    if match_type == 'contains':
                        is_match = trig_lower in msg_lower
                    elif match_type == 'exact':
                        is_match = trig_lower == msg_lower
                    elif match_type == 'regex':
                        try:
                            is_match = re.search(trigger_str, message.content, re.IGNORECASE) is not None
                        except Exception:
                            is_match = False
                            
                    if not is_match:
                        continue
                        
                    # 1. User constraint
                    async with db.execute("SELECT UserID FROM Response_Users WHERE TriggerID = ?", (trigger_id,)) as u_cursor:
                        allowed_users = [r[0] for r in await u_cursor.fetchall()]
                    if allowed_users and message.author.id not in allowed_users:
                        continue
                        
                    # 2. Channel constraint
                    channel_id = message.channel.id
                    if isinstance(message.channel, discord.Thread):
                        channel_id = message.channel.parent_id or message.channel.id
                    async with db.execute("SELECT ChannelID FROM Response_Channels WHERE TriggerID = ?", (trigger_id,)) as c_cursor:
                        allowed_channels = [r[0] for r in await c_cursor.fetchall()]
                    if allowed_channels and channel_id not in allowed_channels:
                        continue
                        
                    # 3. Role constraint
                    async with db.execute("SELECT RoleID FROM Response_Roles WHERE TriggerID = ?", (trigger_id,)) as r_cursor:
                        allowed_roles = [r[0] for r in await r_cursor.fetchall()]
                    if allowed_roles:
                        if not isinstance(message.author, discord.Member):
                            continue
                        member_role_ids = [role.id for role in message.author.roles]
                        if not any(role_id in member_role_ids for role_id in allowed_roles):
                            continue
                            
                    # 4. Cooldown
                    if cooldown and cooldown > 0:
                        current_time = datetime.now(timezone.utc)
                        last_time = last_trigger_time.get(
                            (message.channel.id, trig_lower),
                            datetime.min.replace(tzinfo=timezone.utc)
                        )
                        if (current_time - last_time).total_seconds() <= cooldown:
                            logging.debug(f"Cooldown active for '{trig_lower}'. Skipping message.")
                            continue
                        
                    # 5. Likelihood
                    if likelihood is not None:
                        if random.randint(1, 100) > likelihood:
                            continue
                            
                    matched_trigger = (trigger_id, response_text, trig_lower, cooldown)
                    break
                    
                if matched_trigger:
                    trigger_id, response_text, trig_lower, cooldown = matched_trigger
                    # Update cooldown timestamp
                    if cooldown and cooldown > 0:
                        last_trigger_time[(message.channel.id, trig_lower)] = datetime.now(timezone.utc)
                        
                    async with db.execute("SELECT buttonname, response FROM Response_Followup WHERE TriggerID = ?", (trigger_id,)) as f_cursor:
                        followups = await f_cursor.fetchall()
                    if followups:
                        view = ResponseFollowupView(followups)
                        await message.channel.send(response_text, view=view)
                    else:
                        await message.channel.send(response_text)
        except Exception as e:
            logging.exception(f"Error handling dynamic meme trigger: {e}")
    if "amara" in message.content.lower():
        await message.add_reaction("<:Amara:889554558072782879>")
        await message.add_reaction("🇶")
        await message.add_reaction("🇺")
        await message.add_reaction("🇪")
        await message.add_reaction("❓")

    if (message.author.id ==  243120409703088128 and message.content.lower() == 'i should really add a ping command to pathparser') \
            or  message.content.lower() == 'solfyr should really add a ping command to pathparser':
        ping_dict = await ping_test()
        if ping_dict:
            async with aiosqlite.connect(f"origin.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute("Select instances from memes where name = 'Ping'")
                instances = await cursor.fetchone()
                if not instances:
                    count_of_pings = 1
                    await cursor.execute("insert into memes(instances, name) VALUES (1, 'Ping')")
                else:
                    count_of_pings = instances[0] + 1
                    await cursor.execute("update memes set instances = ? where name = 'Ping'", (count_of_pings,))
                await db.commit()
            response = f"I've been nagged about this shit {count_of_pings} times. I'm awake. \r\nGoogle Responded with {ping_dict['google']} MS Discord Responded with {ping_dict['discord']} MS"

            await message.channel.send(response)


    swears = {
        "fuck": 0,
        "shit": 0,
        "damn": 0,
        "bitch": 0,
        "ass": 0,
    }

    # Normalize the string (optional)
    normalized_string = message.content.lower()

    # Count occurrences of each fruit in the string
    for swear in swears.keys():
        # Use regex to match whole words
        swears[swear] = len(re.findall(rf"\b{swear}\b", normalized_string))
    # Calculate total occurrences
    total_count = sum(swears.values())

    if total_count > 1 and message.author.id == 243120409703088128:

        hostility = min(100, int((total_count / 5) * 100))
        if 0 <= random_number <= 17:
            await message.channel.send(f"Hostility Detected: {hostility}% Someone's a salty boy! :)")
        elif 18 <= random_number <= 34:
            await message.channel.send(f"Wow. Someone's feeling mean today! He's {hostility}% hostile!")
        elif 35 <= random_number <= 50:
            await message.channel.send(
                f"Angry dog off the leash! he's feeling {hostility}% hostile! Someone better get his waifu before he wreck his laifu.")
    if message.author.id == 243120409703088128 and 'I mean' in message.content:
        async with aiosqlite.connect(f"origin.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute("SELECT instances from Memes where name = 'IMean'")
            instances = await cursor.fetchone()
            number = instances[0] + 1
            await cursor.execute("UPDATE Memes SET instances = ? WHERE name = 'IMean'", (number,))
            await db.commit()
            await message.channel.send(
                content=f"You have [meant](https://us-tuna-sounds-images.voicemod.net/c75f5860-13bd-4808-a2ed-3a097f0a24b1.jpg) something {number} times.")

