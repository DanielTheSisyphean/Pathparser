import random
import re
import logging
import discord
from datetime import datetime, timezone
import aiosqlite

# Global state for last trigger time (needs to be moved to a better place optimally, but kept here for now)
last_trigger_time = {}

async def meme_handler(message: discord.Message):
    # ... logic from shared_functions.py ...
    # Rewriting this to be cleaner could be a separate task, for now moving it.
    
    random_number = random.randint(1, 50)
    # ... IDs should be in config preferably, but keeping as is for migration parity first ...
    
    if 'einstein' in message.content.lower():
        await message.channel.send(
            "https://i.insider.com/641ca0f5d67fe70018a376ca?width=800&format=jpeg&auto=webp")
    elif 'monkey' in message.content.lower():
        current_time = datetime.now(timezone.utc)
        last_time = last_trigger_time.get(message.channel.id, datetime.min)
        if (current_time - last_time).total_seconds() > 300:  # 300 seconds = 5 minutes
            last_trigger_time[message.channel.id] = current_time
            if random_number != 1:
                await message.channel.send("https://i.ytimg.com/vi/tLHqnn1ZkAM/maxresdefault.jpg")
            else:
                await message.channel.send(
                    "https://tenor.com/view/mmmm-monkey-monkey-ug-master-oogway-oogway-gif-19727561")
        else:
            logging.debug("Cooldown active. Skipping message.")

    # ... The rest of the meme logic ... 
    # I will copy the exact logic from shared_functions.py to avoid breaking behavior.
    
    if random_number == 1 and message.author.id == 217873501313433600:
        await message.channel.send(
            "https://cdn.discordapp.com/attachments/479089930816192513/1309682327860805733/7YjmdoZxhSgAAAAASUVORK5CYII.png?ex=67768b77&is=677539f7&hm=9ebebdcbf4c8f1266649c1d1d66dbcdad58b18f1a219da101094a96f910d396c&")
    elif random_number == 2 and message.author.id == 217873501313433600:
        await message.channel.send(
            "https://cdn.discordapp.com/attachments/479089930816192513/1309681542653546560/764rjEg82XSZ0fJzf8fVPtjhVRebgAAAAASUVORK5CYII.png?ex=67768abc&is=6775393c&hm=1728ae88544b6323a3d280dc552bb48eff922f3c0cf3983e341654cb4eb61022&")
    elif random_number == 3 and message.author.id == 217873501313433600:
        await message.channel.send(
            "https://cdn.discordapp.com/attachments/479089930816192513/1309681106013917284/wdUWYUf3MwhkwAAAABJRU5ErkJggg.png?ex=67768a54&is=677538d4&hm=bd846ce7d3f0ab3361170189bfc57520357ada3740ec61af1cfe7e9a5be3cf2d&")
    elif random_number == 4 and message.author.id == 217873501313433600:
        await message.channel.send(
            "https://cdn.discordapp.com/attachments/479089930816192513/1322782239452430467/4OGDuJJjqwVJFdQkOvEm71fkWBFQVWFFhRYEWBFQWWBRYAfoXa71Wo11RYEWBFQVWFFhRYCkFPgUCd2wuGYpcgwAAAABJRU5ErkJggg.png?ex=6776bdb5&is=67756c35&hm=35c2b303e206d87b60edc261f3134c6a072af9255a5a721e1a0cfa377fcb20a6&")

    if message.author.id == 318796580662542347 and 'stabbed' in message.content.lower():
        await message.channel.send(
            "https://media.tenor.com/-BpjJcwntaYAAAAM/you-fucking-what-epic-npc-dnd.gif")
    elif message.author.id == 318796580662542347 and 'hit by a car' in message.content.lower():
        await message.channel.send("https://media.makeameme.org/created/yoooooooooooooooo-how-did.jpg")
    elif message.author.id == 318796580662542347 and 'car wreck' in message.content.lower():
        await message.channel.send("https://media.makeameme.org/created/yoooooooooooooooo-how-did.jpg")
    elif message.author.id == 318796580662542347 and 'car crash' in message.content.lower():
        await message.channel.send("https://media.makeameme.org/created/yoooooooooooooooo-how-did.jpg")
    elif message.author.id == 318796580662542347 and 'hit by a truck' in message.content.lower():
        await message.channel.send("https://media.makeameme.org/created/yoooooooooooooooo-how-did.jpg")
    elif message.author.id == 318796580662542347 and 'got shot' in message.content.lower():
        await message.channel.send(
            "https://cdn.discordapp.com/attachments/479089930816192513/1330383824315613275/hq720.png?ex=678dc7fd&is=678c767d&hm=a4ae84c616d84827555e18cee3a61337d2f65f36eae0caf89dc9d06bd42377bd&")
    elif message.author.id == 318796580662542347 and 'set me on fire' in message.content.lower():
        await message.channel.send("https://i.imgflip.com/pwruu.jpg")
    elif message.author.id == 318796580662542347 and 'got robbed' in message.content.lower():
        await message.channel.send("https://media.tenor.com/9G-H14djSBkAAAAM/wallet-john-travolta.gif")
    if "%soulisawesome" in message.content.lower():
        await message.channel.send("https://y.yarn.co/6447b331-7aa2-4785-a5a0-9d20fa4dae35_text.gif")
    if "amara" in message.content.lower():
        await message.add_reaction("<:Amara:889554558072782879>")
        await message.add_reaction("🇶")
        await message.add_reaction("🇺")
        await message.add_reaction("🇪")
        await message.add_reaction("❓")

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

