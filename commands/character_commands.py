import json
import logging
import random
import typing
import math
from core import utils, display, views, autocomplete
import discord
import re
from unidecode import unidecode
from discord.ext import commands
from discord import app_commands
import datetime
import aiosqlite
from decimal import Decimal

from core.character import (
    CalculationAidFunctionError, get_max_level,
    level_calculation, get_max_mythic, mythic_calculation,
    gold_calculation, calculate_fame, update_character_name,
    normal_sheet_attributes, experimental_sheet_attributes, normal_sheet_skills, experimental_sheet_skills,
    server_inventory_check, CharacterChange, UpdateCharacterData, update_character
)
from core.display import stg_character_embed, character_embed, log_embed
from core.autocomplete import (settlement_autocomplete, region_autocomplete,
                               own_character_select_autocompletion, title_autocomplete, fame_autocomplete,
                               kingdom_autocomplete, character_select_autocompletion
                               )
from core.utils import (
    get_gold_breakdown, name_fix, safe_add,
)
from core.config import config_cache
from core.cache import autocomplete_cache, build_home_cache
from core.worldanvil import put_wa_article, patch_wa_article
from core import roleplay

class CharacterCommands(commands.Cog, name='character'):
    def __init__(self, bot):
        self.bot = bot

    character_group = discord.app_commands.Group(
        name='character',
        description='Commands related to characters'
    )

    @character_group.command(name='help', description='Help commands for the character tree')
    async def help(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        embed = discord.Embed(title=f"Character Help", description=f'This is a list of Character commands',
                              colour=discord.Colour.blurple())
        try:
            embed.add_field(
                name="__**Character Commands**__",
                value="""Commands related to characters\r\n
                **/Character Backstory** - Give your character a backstory if they do not already have one. \n
                **/Character Cap** - Set a cap on your character's level. \n
                **/Character Edit** -  Edit a registered character or a character in stage. \n 
                **/Character Levelup** - Consume jobs from your inventory to level up. \n
                **/Character Pouch** - Consume gold pouches from your inventory to meet WPL. \n
                **/Character Retire** - Retire a registered character. \n
                **/Character Trialup** - Consume trial catch ups from your inventory to level up. \n
                **/Character Move** - Move to a new region. \n
                """, inline=False)
            embed.add_field(
                name="**__Display Commands__**",
                value="""Commands related to displaying Character Info \r\n
                **/character display level_range** - Display characters in a level range. \n
                **/character display character** - Display information about a character. \n
                """, inline=False)
            embed.add_field(
                name="**__Gold Commands__**",
                value="""Commands related to gold for characters\r\n
                **/Character gold buy** - Mark Gold Purchases from NPCs \n
                **/Character Gold Consume** - Consume gold from your illiquid wealth to represent usage of items \n
                **/Character Gold Claim** - Claim gold from downtime or other activities.  \n
                **/Character Gold History** - View the gold audit history of a character. \n
                **/Character Gold Send** - Send gold between characters. \n
                """, inline=False)
            embed.add_field(
                name="__**Prestige Commands**__",
                value="""Commands related to Prestige for characters\r\n
                **/Character Prestige Display** - Display Prestige events in the store. \n
                **/Character Prestige History** - Display your prestige request history. \n
                **/Character Prestige Prestige** - Request a prestige event from the DM \n
                """, inline=False)
            embed.add_field(
                name="__**Title Commands**__",
                value="""Commands related to titles and entitling characters\r\n\
                **/Character Title Display** - Display Titles available in the store.  \n
                **/Character Title Swap** - Swap the Gender used in your title.  \n
                **/Character Title Use** - Use a title from the store to give your character a new title.. \n
                """, inline=False)
            embed.add_field(
                name="**__Mythweavers Commands__**",
                value="""Commands related to Mythweavers for characters\r\n
                **/Character Mythweavers Attributes** - Display Character Attributes and rolls  \n
                **/Character Mythweavers Combat** - Display Character combat attributes and rolls \n
                **/Character Mythweavers Skills** - Display character skills and rolls. \n
                **/Character Mythweavers Upload** - Upload a mythweavers sheet to the database.\n
                """, inline=False)
            await interaction.followup.send(embed=embed)
        except discord.errors.HTTPException:
            logging.exception(f"Error in help command")
            await interaction.channel.send(embed=embed)

    @character_group.command(name="rumormonger", description="Sous for a random rumor!")
    @app_commands.autocomplete(kingdom=kingdom_autocomplete)
    @app_commands.autocomplete(settlement=settlement_autocomplete)
    @app_commands.describe(check="This is the value of your roll result, and the upper ceiling for rumors you can get.")
    async def rumor(self, interaction: discord.Interaction, kingdom: str, settlement: str, check: int):
        await interaction.response.defer(thinking=True, ephemeral=False)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as conn:
                cursor = await conn.cursor()
                await cursor.execute("""
                                WITH Weighted AS (
                    SELECT
                        Rumor,
                        RumorID,
                        SUM(Weight) OVER (
                            ORDER BY rowid
                            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                        ) AS UpperBound
                    FROM rumors
                    WHERE (kingdom = ? or Kingdom = 'All')
                        AND (Settlement = ? or Settlement = 'All')
                        AND DC <= ? 
                ),
                RandomPick AS (
                    SELECT ABS(RANDOM()) % (
                        SELECT SUM(Weight) FROM Rumors
                        WHERE (kingdom = ? or Kingdom = 'All')
                            AND (Settlement = ? or Settlement = 'All')
                            AND DC <= ?
                    ) + 1 AS Roll
                )
                SELECT w.*, r.Roll
                FROM Weighted w
                CROSS JOIN RandomPick r
                WHERE w.UpperBound >= r.Roll
                ORDER BY w.UpperBound
                LIMIT 1;
                """, (kingdom, settlement, check, kingdom, settlement, check))
                rumor_results = await cursor.fetchone()
                if rumor_results:
                    rumor_titles = [
                        "So you're asking about rumors, Ay?",
                        "Seeking the fresh dirt on the road, huh?",
                        "Got a thirst for some fresh tea?",
                        "Have an ear for something new? Let's see if someone will bend it",
                        "Looking for something spicy, perhaps this will do"
                    ]
                    rumor_list_length = len(rumor_results)
                    random_slice = random.randint(1, rumor_list_length) -1
                    embed = discord.Embed(title=rumor_titles[random_slice], description=f"{rumor_results[0]}")
                    embed.set_footer(text=f"Rumor ID: {rumor_results[1]}")
                    await interaction.followup.send(embed=embed)
                else:
                    await  interaction.followup.send("The tea is poor drinking round these parts")
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"Error in Rumor command {e}")
            await interaction.followup.send(f"Error in rumor command {e}")


    @character_group.command(name='move', description="Change Region")
    @app_commands.autocomplete(region=region_autocomplete)
    @app_commands.autocomplete(character=own_character_select_autocompletion)
    async def change_region(self, interaction: discord.Interaction, region: str, character: str, reason: str):
        await interaction.response.defer(thinking=True, ephemeral=False)
        guild_id = interaction.guild_id
        author_id = interaction.user.id
        author_name = interaction.user.name
        try:
            async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as conn:
                cursor = await conn.cursor()
                await cursor.execute(
                    "SELECT Player_ID, Character_Name, Level, Region, Thread_ID FROM Player_Characters WHERE Character_Name = ? and Player_ID = ?",
                    (character, author_id))
                character_info = await cursor.fetchone()
                if character_info is None:
                    await interaction.followup.send(f"Character {character} not found")
                    return
                (player_id, character_name, level, old_region, thread) = character_info
                if old_region == region:
                    await interaction.followup.send(f"Character {character} is already in {region}")
                    return
                await cursor.execute("SELECT Role_ID, Channel_id, Coming FROM Regions WHERE Name = ?", (region,))
                region_role = await cursor.fetchone()

                if region_role is None:
                    await interaction.followup.send(f"Region {region} not found")
                    return
                if not region_role[2]:
                    await interaction.followup.send(f"Region {region} is not accepting characters")
                    return

                await cursor.execute("SELECT Role_ID, Channel_id, Going FROM Regions WHERE Name = ?", (old_region,))
                await interaction.user.add_roles(interaction.guild.get_role(region_role[0]))

                old_region_role = await cursor.fetchone()
                if old_region_role is not None:
                    (old_role_id, old_channel, going) = old_region_role
                    if not going:
                        await interaction.followup.send(
                            f"Region {old_region} cannot be escaped.\r\nYou will never leave.\r\nNo one will save you.\r\nEven The gods will abandon you.")
                        return

                    if old_channel is not None:
                        old_text_channel = interaction.guild.get_channel(old_channel)
                        if not old_text_channel:
                            await interaction.guild.fetch_channel(old_channel)
                        await old_text_channel.send(
                            f"{datetime.date.today()}\r\nCharacter {character} moved to {region} by {author_name}\r\n{reason}")
                    await cursor.execute(
                        "SELECT Role_ID, Min_Level, Max_Level from Regions_Level_Range where Name = ? AND min_level <= ? AND max_level >= ?",
                        (old_region, level, level))
                    old_level_range = await cursor.fetchone()

                    if old_level_range:
                        (role_id, min_level_old, max_level_old) = old_level_range
                    else:
                        min_level_old = 0
                        max_level_old = 0

                    await cursor.execute("""
                    SELECT COUNT(*) AS Total_Characters,
                    SUM(CASE WHEN level BETWEEN ? AND ? THEN 1 ELSE 0 END) AS Characters_In_Range
                    FROM Player_Characters
                    WHERE Player_ID = ? and Region = ?;""",
                                         (min_level_old, max_level_old, author_id, old_region))
                    character_in_old_range = await cursor.fetchone()
                    if character_in_old_range and old_region:
                        (total_characters, characters_in_range) = character_in_old_range
                        if not total_characters:
                            await interaction.user.remove_roles(interaction.guild.get_role(old_region_role[0]))
                        if not characters_in_range:
                            await interaction.user.remove_roles(interaction.guild.get_role(old_level_range[0]))
                await cursor.execute("UPDATE Player_Characters SET Region = ? WHERE Character_Name = ?",
                                     (region, character))
                await cursor.execute(
                    "SELECT Role_ID FROM Regions_Level_Range WHERE Name = ? AND Min_Level <= ? AND Max_Level >= ?",
                    (region, level, level))
                new_level_range = await cursor.fetchone()
                if new_level_range:
                    await interaction.user.add_roles(interaction.guild.get_role(new_level_range[0]))
                await conn.commit()
                new_text_channel = interaction.guild.get_channel(region_role[1])
                if not new_text_channel:
                    await interaction.guild.fetch_channel(region_role[1])
                await new_text_channel.send(
                    f"{datetime.date.today()}\r\nCharacter {character} moved from {old_region} to {region} by {interaction.user}\r\n{reason}")
                changer_changes = CharacterChange(
                    character_name=character_name,
                    author=interaction.user.name,
                    region=region,
                    source='Character Edit')
                await log_embed(guild=interaction.guild, change=changer_changes, bot=self.bot,
                                                 thread=thread)
                await interaction.followup.send(f"Character {character} moved from {old_region} to {region}")
                await character_embed(guild=interaction.guild, character_name=character)
        except aiosqlite.Error as e:
            logging.exception(f"Error in character move for {character}: {e}")
            await interaction.followup.send(f"Error in character move for {character}: {e}")

    @character_group.command(name='register', description='register a character')
    @app_commands.describe(oath="Determining future gold gain from sessions and gold claims.")
    @app_commands.choices(oath=[discord.app_commands.Choice(name='No Oath', value=1),
                                discord.app_commands.Choice(name='Oath of Offerings', value=2),
                                discord.app_commands.Choice(name='Oath of Poverty', value=3),
                                discord.app_commands.Choice(name='Oath of Absolute Poverty', value=4)])
    @app_commands.choices(heroism=[discord.app_commands.Choice(name='Hero', value=1),
                                discord.app_commands.Choice(name='Antihero', value=2)])
    @app_commands.describe(nickname='a shorthand way to look for your character in displays')
    async def register(self, interaction: discord.Interaction, character_name: str, mythweavers: str, image_link: str, heroism : discord.app_commands.Choice[int],
                       nickname: str = None,
                       titles: str = None, description: str = None, oath: discord.app_commands.Choice[int] = 1,
                       color: str = '#5865F2', backstory: str = None):
        """Command to handle registering a character for a player"""
        await interaction.response.defer(thinking=True, ephemeral=False)

        guild_id = interaction.guild_id
        author = interaction.user.name
        author_id = interaction.user.id
        time = datetime.datetime.now()
        heroism_value = heroism if isinstance(heroism, int) else heroism.value
        oath_name = 'No Oath' if oath == 1 else oath.name
        oath_name = 'Offerings' if oath_name == 'Oath of Offerings' else oath_name
        oath_name = 'Poverty' if oath_name == 'Oath of Poverty' else oath_name
        oath_name = 'Absolute' if oath_name == 'Oath of Absolute Poverty' else oath_name

        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as conn:
            cursor = await conn.cursor()

            try:
                if character_name is not None:
                    if len(character_name) > 99:
                        await interaction.followup.send(f"Character Name is too long, please shorten it.")
                        return
                    true_character_name, character_name = name_fix(character_name)
                else:
                    await interaction.followup.send(f"Character Name is required")
                    return

                if nickname is not None:
                    _, nickname = name_fix(nickname)

                if backstory is not None:
                    if len(backstory) > 2000:
                        await interaction.followup.send(
                            f"Backstory is too long, please shorten it or use a google doc.")
                        return

                if titles is not None:
                    titles, _ = name_fix(titles)

                if description is not None:
                    description = str.replace(description, ";", "")

                if mythweavers is not None:
                    validate_mythweavers = utils.validate_mythweavers(mythweavers)
                    validate_worldanvil = utils.validate_worldanvil(mythweavers)

                    if not validate_mythweavers[0] and not validate_worldanvil[0]:
                        # Handle exceptions and compare step indicators
                        if validate_mythweavers[2] == -1 and validate_worldanvil[2] != -1:
                            await interaction.followup.send(validate_worldanvil[1])
                        elif validate_worldanvil[2] == -1 and validate_mythweavers[2] != -1:
                            await interaction.followup.send(validate_mythweavers[1])
                        elif validate_mythweavers[2] >= validate_worldanvil[2]:
                            await interaction.followup.send(validate_mythweavers[1])
                        else:
                            await interaction.followup.send(validate_worldanvil[1])
                        return

                else:
                    await interaction.followup.send(f"Mythweavers link is required", ephemeral=True)
                    return

                if image_link is not None:
                    image_link = str.replace(str.replace(image_link, ";", ""), ")", "")
                    image_link_valid = str.lower(image_link[0:5])
                    if len(image_link) > 300:
                        await interaction.followup.send(
                            f"When it blocked out the sun, did you consider if it was possible that your image link is a little too long?")
                        return
                    if image_link_valid != 'https':
                        await interaction.followup.send(f"Image link is missing HTTPS:")
                        return

                else:
                    await interaction.followup.send(f"image link is required", ephemeral=True)
                    return

                regex = r'^#(?:[0-9a-fA-F]{3}){1,2}$'
                match = re.search(regex, color)

                if len(color) == 7 and match:

                    await cursor.execute(
                        "SELECT Player_Name, Character_Name from Player_Characters where Character_Name = ?",
                        (character_name,))
                    results_prod = await cursor.fetchone()

                    await cursor.execute(
                        "SELECT Player_Name, Character_Name from A_STG_Player_Characters where Character_Name = ?",
                        (character_name,))
                    results_stg = await cursor.fetchone()

                    if results_prod is None and results_stg is None:

                        try:

                            async with config_cache.lock:
                                configs = config_cache.cache.get(guild_id)
                                print(configs)
                                if configs:
                                    starting_level = configs.get('Starting_Level')
                                else:
                                    await cursor.execute(
                                        "Select Search From Admin where Identifier = 'Starting_Level'")
                                    starting_level = await cursor.fetchone()
                                    print(starting_level)
                                    starting_level = starting_level[0]

                            await cursor.execute(
                                "SELECT Minimum_Milestones, Milestones_to_level, WPL FROM Milestone_System where level = ?",
                                (starting_level,))
                            starting_level_info = await cursor.fetchone()

                            (base, milestones_to_level, wpl) = starting_level_info

                            sql = """insert into A_STG_Player_Characters (
                            Player_Name, Player_ID, Character_Name, True_Character_Name, 
                            Nickname, Titles, Description, 
                            Oath, Level, Tier, Milestones, Milestones_Required, Trials, Trials_Required, Color, Mythweavers, 
                            Image_Link, Backstory, Created_Date, Heroism) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""

                            val = (
                                author, author_id, character_name, true_character_name,
                                nickname, titles, description,
                                oath_name, starting_level, 0, base, milestones_to_level, 0, 0, color, mythweavers,
                                image_link, backstory, time, heroism_value)
                            await cursor.execute(sql, val)
                            await conn.commit()
                            embed = await stg_character_embed(character_name, interaction.guild)

                            if isinstance(embed, tuple):
                                await interaction.followup.send(embed=embed[0], content=embed[1], ephemeral=False)

                            else:
                                await interaction.followup.send(
                                    "could not send message because of an error building the embed!")

                        except discord.errors.HTTPException:

                            embed[0].set_thumbnail(
                                url=f'https://cdn.discordapp.com/attachments/977939245463392276/1194140952789536808/download.jpg?ex=65af456d&is=659cd06d&hm=1613025f9f1c1263823881c91a81fc4b93831ff91df9f4a84c813e9fab6467e9&')

                            embed[0].set_footer(text=f'Oops! You used a bad URL, please fix it.')

                            await interaction.followup.send(embed=embed[0], content=embed[1], ephemeral=False)
                            sql = "Update A_STG_Player_Characters SET Image_Link = ? AND Mythweavers = ? WHERE Character_Name = ?"
                            val = (
                                "https://cdn.discordapp.com/attachments/977939245463392276/1194140952789536808/download.jpg?ex=65af456d&is=659cd06d&hm=1613025f9f1c1263823881c91a81fc4b93831ff91df9f4a84c813e9fab6467e9&",
                                "https://cdn.discordapp.com/attachments/977939245463392276/1194141019088891984/super_saiyan_mr_bean_by_zakariajames6_defpqaz-fullview.jpg?ex=65af457d&is=659cd07d&hm=57bdefe2d376face6a842a7b7a5ed8021e854a64e798f901824242c4a939a37b&",
                                character_name)
                            await cursor.execute(sql, val)
                            await conn.commit()

                    else:
                        await interaction.followup.send(
                            f"{character_name} has already been registered by {author}",
                            ephemeral=True)

                else:
                    await interaction.followup.send(f"Invalid Hex Color Code!", ephemeral=True)
            except (aiosqlite.Error, TypeError, ValueError) as e:
                logging.exception(f"An error occurred whilst building character embed for '{character_name}': {e}")
                await interaction.followup.send(
                    f"An error occurred whilst building character embed for '{character_name}' Error: {e}.",
                    ephemeral=True)

    @character_group.command(name='edit', description='edit your character')
    @app_commands.autocomplete(character_name=own_character_select_autocompletion)
    @app_commands.describe(oath="Determining future gold gain from sessions and gold claims.")
    @app_commands.choices(oath=[discord.app_commands.Choice(name='No Oath', value=1),
                                discord.app_commands.Choice(name='Offerings', value=2),
                                discord.app_commands.Choice(name='Poverty', value=3),
                                discord.app_commands.Choice(name='Absolute', value=4),
                                discord.app_commands.Choice(name='No Change', value=5)])
    @app_commands.choices(heroism=[discord.app_commands.Choice(name='Hero', value=1),
                                   discord.app_commands.Choice(name='Antihero', value=2)])
    @app_commands.describe(new_nickname='a shorthand way to look for your character in displays')
    async def edit(self, interaction: discord.Interaction, character_name: str, new_character_name: str = None,
                   mythweavers: str = None, heroism: int = None,
                   image_link: str = None, new_nickname: str = None, titles: str = None, description: str = None,
                   oath: discord.app_commands.Choice[int] = 5, color: str = None):
        guild_id = interaction.guild_id
        guild = interaction.guild
        author = interaction.user.name
        heroism_value = heroism if isinstance(heroism, int) else heroism.value
        await interaction.response.defer(thinking=True, ephemeral=True)
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as conn:
            cursor = await conn.cursor()
            try:
                sql = ("""Select True_Character_Name, Nickname, Titles, Description, Mythweavers, Image_Link, Oath, 
                       Color, Level, Tier, Milestones, Milestones_Required, Trials, Trials_required, 
                       Gold, Gold_Value, Gold_Value_Max, Essence, Message_ID, Logging_ID, Thread_ID, Fame, Title, 
                       Personal_Cap, Prestige, Article_Link FROM Player_Characters 
                       where Player_Name = ? AND (Character_Name = ? OR Nickname = ?)""")
                val = (author, character_name, character_name)
                await cursor.execute(sql, val)
                results = await cursor.fetchone()
                if results is None:
                    sql = "SELECT True_Character_Name, Nickname, Titles, Description, Mythweavers, Image_Link, Oath, Color, Level, Tier, Milestones, Milestones_Required, Trials, Trials_required, Character_Name, Heroism from A_STG_Player_Characters where Player_Name = ? AND (Character_Name = ? OR  Nickname = ?)"
                    val = (author, character_name, character_name)
                    await cursor.execute(sql, val)
                    results = await cursor.fetchone()
                    if results is None:
                        await interaction.followup.send(
                            f"Cannot find any {character_name} owned by {author} with the supplied name or nickname.")
                    else:
                        (stg_true_character_name, stg_nickname, stg_titles, stg_description, stg_mythweavers,
                         stg_image_link, stg_oath, stg_color, stg_level, stg_tier, stg_milestones,
                         stg_milestones_required, stg_trials, stg_trials_required, stg_character_name, stg_heroim) = results
                        if new_character_name is not None:
                            if len(character_name) > 99:
                                await interaction.followup.send(f"Character Name is too long, please shorten it.")
                                return
                            true_character_name, new_character_name = name_fix(new_character_name)
                            await cursor.execute(
                                "SELECT Character_Name from A_STG_Player_Characters where Character_Name = ?",
                                (new_character_name,))
                            check_stg_name = await cursor.fetchone()
                            if check_stg_name is not None:
                                await interaction.followup.send(
                                    f"{new_character_name} is already in use, please choose a different name.")
                                return
                            await cursor.execute(
                                "SELECT Character_Name from Player_characters where character_name = ?",
                                (new_character_name,))
                            check_prod_name = await cursor.fetchone()
                            if check_prod_name is not None:
                                await interaction.followup.send(
                                    f"{new_character_name} is already in use, please choose a different name.")
                                return
                        else:
                            true_character_name = stg_true_character_name
                            new_character_name = stg_character_name
                        if new_nickname is not None:
                            new_nickname, _ = name_fix(new_nickname)
                        else:
                            new_nickname = stg_nickname
                        if titles is not None:
                            titles = str.replace(str.replace(titles, ";", ""), ")", "")
                        else:
                            titles = stg_titles
                        if description is not None:
                            description = str.replace(str.replace(description, ";", ""), ")", "")
                        else:
                            description = stg_description
                        if mythweavers is not None:
                            validate_mythweavers = utils.validate_mythweavers(mythweavers)
                            validate_worldanvil = utils.validate_worldanvil(mythweavers)
                            if not validate_mythweavers[0] and not validate_worldanvil[0]:
                                # Handle exceptions and compare step indicators
                                if validate_mythweavers[2] == -1 and validate_worldanvil[2] != -1:
                                    await interaction.followup.send(validate_worldanvil[1])
                                elif validate_worldanvil[2] == -1 and validate_mythweavers[2] != -1:
                                    await interaction.followup.send(validate_mythweavers[1])
                                elif validate_mythweavers[2] >= validate_worldanvil[2]:
                                    await interaction.followup.send(validate_mythweavers[1])
                                else:
                                    await interaction.followup.send(validate_worldanvil[1])
                                return
                        else:
                            mythweavers = stg_mythweavers
                        if image_link is not None:
                            image_link = str.replace(str.replace(image_link, ";", ""), ")", "")
                            image_link_valid = str.lower(image_link[0:5])
                            if image_link_valid != 'https':
                                await interaction.followup.send(f"Image link is missing HTTPS:")
                                return
                        else:
                            image_link = stg_image_link
                        oath = 'No Change' if oath == 5 else oath.name
                        if oath == 'No Change':
                            oath_name = stg_oath
                        else:
                            oath_name = oath
                        if color is not None:
                            regex = r'^#(?:[0-9a-fA-F]{3}){1,2}$'
                            match = re.search(regex, color)
                        else:
                            color = stg_color
                            regex = r'^#(?:[0-9a-fA-F]{3}){1,2}$'
                            match = re.search(regex, color)
                        if len(color) == 7 and match:
                            await cursor.execute("update a_stg_player_characters set "
                                                 "True_Character_Name = ?, Character_Name = ?, Nickname = ?, Titles = ?,"
                                                 " Description = ?, Mythweavers = ?, Image_Link = ?, Oath = ?, "
                                                 "Color = ? , heroism = Coalesce(?, heroism)"
                                                 "where Character_Name = ?", (
                                                     true_character_name, new_character_name, new_nickname, titles,
                                                     description, mythweavers, image_link, oath_name, color, heroism_value,
                                                     character_name))
                            await conn.commit()
                            embed = await stg_character_embed(new_character_name, interaction.guild)
                            if isinstance(embed, tuple):
                                await interaction.followup.send(content="Character Updated")
                                await interaction.channel.send(embed=embed[0], content=embed[1])
                            else:
                                await interaction.followup.send(
                                    "could not send message because of an error building the embed!")
                        else:
                            await interaction.followup.send(f"Invalid Hex Color Code!")
                else:
                    (info_true_character_name, info_nickname, info_titles, info_description, info_mythweavers,
                     info_image_link, info_oath, info_color, info_level, info_tier, info_milestones,
                     info_milestones_required,
                     info_trials, info_trials_required, info_gold, info_gold_value, info_gold_value_max, info_essence,
                     info_message_id, info_thread_message, info_thread_id, info_fame, info_title, info_personal_cap,
                     info_prestige,
                     info_article_link) = results
                    if new_character_name is not None:
                        true_character_name, new_character_name = name_fix(new_character_name)
                        await cursor.execute(
                            "SELECT Character_Name from A_STG_Player_Characters where Character_Name = ?",
                            (new_character_name,))
                        check_stg_name = await cursor.fetchone()
                        if check_stg_name is not None:
                            await interaction.followup.send(
                                f"{new_character_name} is already in use, please choose a different name.")
                            return
                        await cursor.execute("SELECT Character_Name from Player_characters where character_name = ?",
                                             (new_character_name,))
                        check_prod_name = await cursor.fetchone()
                        if check_prod_name is not None:
                            await interaction.followup.send(
                                f"{new_character_name} is already in use, please choose a different name.")
                            return
                        autocomplete_cache.cache.clear()
                        character_changes = CharacterChange(character_name=new_character_name,
                                                                             author=author,
                                                                             source='Character Edit')
                    else:
                        true_character_name, new_character_name = name_fix(info_true_character_name)
                        character_changes = CharacterChange(character_name=new_character_name,
                                                                             author=author,
                                                                             source='Character Edit')
                    if new_nickname is not None:
                        new_nickname, _ = name_fix(new_nickname)
                    else:
                        new_nickname = info_nickname
                    if titles is not None:
                        titles = str.replace(str.replace(titles, ";", ""), ")", "")
                        character_changes.titles = titles
                    else:
                        titles = info_titles
                    if description is not None:
                        description = str.replace(str.replace(description, ";", ""), ")", "")
                        character_changes.description = description
                    else:
                        description = info_description
                    if mythweavers is not None:
                        validate_mythweavers = utils.validate_mythweavers(mythweavers)
                        validate_worldanvil = utils.validate_worldanvil(mythweavers)
                        if not validate_mythweavers[0] and not validate_worldanvil[0]:
                            # Handle exceptions and compare step indicators
                            if validate_mythweavers[2] == -1 and validate_worldanvil[2] != -1:
                                await interaction.followup.send(validate_worldanvil[1])
                            elif validate_worldanvil[2] == -1 and validate_mythweavers[2] != -1:
                                await interaction.followup.send(validate_mythweavers[1])
                            elif validate_mythweavers[2] >= validate_worldanvil[2]:
                                await interaction.followup.send(validate_mythweavers[1])
                            else:
                                await interaction.followup.send(validate_worldanvil[1])
                            return
                    else:
                        mythweavers = info_mythweavers
                    if image_link is not None:
                        image_link = str.replace(str.replace(image_link, ";", ""), ")", "")
                        image_link_valid = str.lower(image_link[0:5])
                        character_changes.image_link = image_link
                        if image_link_valid != 'https':
                            await interaction.followup.send(f"Image link is missing HTTPS:")
                            return
                    else:
                        image_link = info_image_link
                    oath = 'No Change' if oath == 5 else oath.name
                    if oath == 'No Change':
                        oath_name = info_oath
                    else:
                        oath_name = oath
                        character_changes.oath = oath_name
                    if color is not None:
                        regex = r'^#(?:[0-9a-fA-F]{3}){1,2}$'
                        match = re.search(regex, color)
                    else:
                        color = info_color
                        regex = r'^#(?:[0-9a-fA-F]{3}){1,2}$'
                        match = re.search(regex, color)
                    if len(color) == 7 and match:
                        if results is not None:

                            if oath_name != info_oath and info_level < 7:
                                if oath == 'Offerings':
                                    # Only half the gold change is applied
                                    gold_total = info_gold * 0.5
                                    gold_value_total = info_gold_value - gold_total
                                    gold_value_total_max = gold_value_total
                                elif oath in ('Poverty', 'Absolute'):
                                    max_gold = 80 * info_level * info_level if oath == 'Poverty' else info_level * 5
                                    if results[15] >= max_gold:
                                        # Cannot gain more gold
                                        gold_total = info_gold + max_gold - info_gold_value
                                        gold_value_total = max_gold
                                        gold_value_total_max = info_gold_value_max
                                    else:
                                        gold_total = info_gold
                                        gold_value_total = info_gold_value
                                        gold_value_total_max = info_gold_value_max
                                else:
                                    # Other oaths gain gold normally
                                    gold_total = info_gold
                                    gold_value_total = info_gold_value
                                    gold_value_total_max = info_gold_value_max
                                await cursor.execute(
                                    "UPDATE Player_Characters SET Gold = CAST(? as numeric(16,2)), Gold_Value = CAST(? as numeric(16,2)), Gold_Value_Max = CAST(? as numeric(16,2)) WHERE Character_Name = ?",
                                    (gold_total, gold_value_total, gold_value_total_max,
                                     character_name)
                                )
                                await conn.commit()
                                sql = "INSERT INTO A_Audit_Gold(Author_Name, Author_ID, Character_Name, Gold_Value, Effective_Gold_Value, Effective_Gold_Value_Max, Reason, Source_Command, Time) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)"
                                val = (interaction.user.name, interaction.user.id, character_name, gold_total,
                                       gold_value_total, gold_value_total_max, 'Oaths were Changed',
                                       'Character Edit', datetime.datetime.now())
                                await cursor.execute(sql, val)
                                await conn.commit()
                                await cursor.execute("SELECT Max(transaction_id) FROM A_Audit_Gold")
                                transaction_id = await cursor.fetchone()
                                logging.info(
                                    f"Gold updated for character '{character_name}' Transaction ID: {transaction_id[0]}.")
                            if results[23] is not None:
                                pass
                                # await EventCommand.edit_bio(self, guild_id, new_character_name, None, results[22])
                            await cursor.execute(
                                "update Player_Characters set True_Character_Name = ?, Character_Name = ?, Nickname = ?, Titles = ?, Description = ?, Mythweavers = ?, Image_Link = ?, Oath = ?, Color = ?, heroism = coalesce(?, heroism) where Character_Name = ?",
                                (
                                    true_character_name, new_character_name, new_nickname, titles, description,
                                    mythweavers,
                                    image_link, oath_name, color, heroism_value, character_name))
                            await conn.commit()
                            validate_update = await update_character_name(guild_id, new_character_name,
                                                                          new_character_name)
                            await character_embed(character_name=new_character_name, guild=guild)
                            embedded_log = await display.log_embed(
                                change=character_changes,
                                bot=self.bot,
                                guild=guild,
                                thread=info_thread_id
                            )
                            if validate_update[0]:
                                await interaction.followup.send(embed=embedded_log)
                            if new_character_name or titles or image_link:
                                embed = discord.Embed(title=f"{true_character_name}", url=f'{mythweavers}',
                                                      description=f"Other Names: {info_titles}",
                                                      color=int(color[1:], 16))
                                embed.set_author(name=f'{interaction.user.name}')
                                embed.set_thumbnail(url=f'{image_link}')
                                async with config_cache.lock:
                                    configs = config_cache.cache.get(guild_id)
                                    if configs:
                                        channel_id = configs.get('Char_Eventlog_Channel')
                                if not channel_id:
                                    await interaction.followup.send(f"Channel ID was not found in admin!")
                                    return
                                channel = guild.get_channel(int(channel_id))
                                if not channel:
                                    channel = await guild.fetch_channel(int(channel_id))
                                thread_message = await channel.fetch_message(info_thread_message)
                                await thread_message.edit(embed=embed)
                                thread_logging = interaction.guild.get_channel(info_thread_id)
                                if not thread_logging:
                                    thread_logging = await guild.fetch_channel(info_thread_id)
                                await thread_logging.edit(name=f'{true_character_name}')

                            else:
                                await interaction.followup.send(
                                    f"An error occurred whilst updating character name for '{character_name}' \r\n failed at: {validate_update[1]}.")
                    else:
                        await interaction.followup.send(f"Invalid Hex Color Code!")
            except (aiosqlite.Error, TypeError, ValueError) as e:
                logging.exception(f"An error occurred whilst building character embed for '{character_name}': {e}")
                await interaction.followup.send(
                    f"An error occurred whilst building character embed for '{character_name}' Error: {e}.",
                    ephemeral=True)

    @character_group.command(name='retire', description='retire a character')
    @app_commands.autocomplete(character_name=own_character_select_autocompletion)
    async def retire(self, interaction: discord.Interaction, character_name: str):
        guild_id = interaction.guild_id
        author = interaction.user.name
        await interaction.response.defer(thinking=True, ephemeral=True)
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as conn:
            cursor = await conn.cursor()
            try:
                _, character_name = name_fix(character_name)
                sql = """
                    SELECT True_Character_Name, Thread_ID 
                    FROM Player_Characters 
                    WHERE Player_Name = ? AND (Character_Name = ? OR Nickname = ?)
                """
                val = (author, character_name, character_name)
                await cursor.execute(sql, val)
                results = await cursor.fetchone()
                if results is None:
                    await interaction.followup.send(
                        f"There is no character registered by character name or nickname as {character_name} owned by {interaction.user.name} to unregister.",
                        ephemeral=True
                    )
                else:
                    content = 'You are retiring me?! But you love me!'
                    view = views.RetirementView(character_name=character_name, user_id=interaction.user.id, guild_id=guild_id,
                                          interaction=interaction, content=content)
                    await view.send_initial_message()
            except (aiosqlite.Error, TypeError, ValueError) as e:
                logging.exception(f"An error occurred in the retire command whilst looking for '{character_name}': {e}")
                await interaction.followup.send(
                    f"An error occurred whilst looking for '{character_name}'. Error: {e}.",
                    ephemeral=True
                )

    @character_group.command(name='levelup', description='level up your character')
    @app_commands.autocomplete(character_name=own_character_select_autocompletion)
    async def levelup(self, interaction: discord.Interaction, character_name: str, amount: int):
        guild_id = interaction.guild_id
        guild = interaction.guild
        author = interaction.user.name
        await interaction.response.defer(thinking=True, ephemeral=True)
        if amount >= 1:
            async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as conn:
                cursor = await conn.cursor()
                try:
                    await cursor.execute(
                        "SELECT Character_Name, Personal_Cap, Level, Milestones, tier, trials, Thread_ID, region, Heroism, Hero_points, Hero_points_max FROM Player_Characters WHERE Player_Name = ? AND (Character_Name = ? OR Nickname = ?)",
                        (interaction.user.name, character_name, character_name))
                    player_info = await cursor.fetchone()
                    if player_info is None:
                        await interaction.followup.send(
                            f"Character {character_name} not found.",
                            ephemeral=True
                        )
                    else:
                        server_max_level = await get_max_level(guild_id)
                        (character_name, personal_cap, level, starting_base, tier, trials,
                         logging_thread_id, region) = player_info
                        base = starting_base

                        personal_cap = server_max_level if not personal_cap else personal_cap
                        max_level = min(server_max_level, personal_cap)
                        if level >= max_level:
                            await interaction.followup.send(
                                f"{character_name} is already at the maximum level of {max_level}.",
                                ephemeral=True
                            )
                        else:
                            async with config_cache.lock:
                                configs = config_cache.cache.get(guild_id)
                                if configs:
                                    item_id = configs.get('UBB_Medium_Job')
                                    hero_points_level = configs.get('Hero_Points_Level')
                                item = await server_inventory_check(guild_id, interaction.user.id, item_id, amount)
                            if item == 0:
                                await interaction.followup.send(
                                    f"Insufficient Medium Jobs to level up {character_name}.",
                                    ephemeral=True
                                )
                            else:
                                used = 0
                                new_level_info = (0, 0, 0, 0, 0)
                                new_level = level
                                while used < item and level <= max_level:
                                    used += 1
                                    new_level_info = await level_calculation(
                                        level=new_level,
                                        guild=interaction.guild,
                                        guild_id=interaction.guild.id,
                                        base=base,
                                        personal_cap=personal_cap,
                                        easy=0,
                                        medium=1,
                                        hard=0,
                                        deadly=0,
                                        misc=0,
                                        author_id=interaction.user.id,
                                        character_name=character_name,
                                        region=region
                                    )
                                    new_level = new_level_info[0]
                                    base = new_level_info[1]
                                character_updates = UpdateCharacterData(
                                    level_package=(new_level, base, new_level_info[4]),
                                    character_name=character_name
                                )
                                if new_level > level:
                                    if player_info[7] == 1:
                                        level_difference = new_level - level
                                        hero_points_differential = hero_points_level * level_difference + player_info[8]
                                        hero_points = min(hero_points_differential, player_info[9])
                                        if hero_points != player_info[8]:
                                            character_updates.hero_points = (player_info[7], hero_points)
                                mythic_results = await mythic_calculation(
                                    character_name=character_name,
                                    level=new_level,
                                    trials=trials,
                                    trial_change=0,
                                    guild_id=guild_id,
                                    tier=tier
                                )

                                if tier != mythic_results[0]:
                                    character_updates.mythic_package = (
                                        mythic_results[0], mythic_results[1], mythic_results[3])
                                await update_character(
                                    guild_id=guild_id,
                                    change=character_updates
                                )
                                await character_embed(
                                    character_name=character_name,
                                    guild=guild)
                                character_changes = CharacterChange(
                                    character_name=character_name,
                                    author=author,
                                    source='Level Up',
                                    level=new_level,
                                    milestone_change=base - starting_base,
                                    milestones_total=base,
                                    milestones_remaining=new_level_info[4]
                                )
                                if character_updates.hero_package:
                                    character_changes.heroism = character_updates.hero_package[0]
                                    character_changes.hero_points = character_updates.hero_package[1] - hero_points
                                await roleplay.handle_use(
                                    db=conn,
                                    interaction=interaction,
                                    user_id=interaction.user.id,
                                    item_id=item_id,
                                    amount=used
                                )
                                if mythic_results[0] != tier:
                                    character_changes.tier = mythic_results[0]
                                    character_changes.trials = mythic_results[1]
                                    character_changes.trials_remaining = mythic_results[2]
                                character_log = await log_embed(character_changes, guild,
                                                                                 logging_thread_id, self.bot)
                                await interaction.followup.send(embed=character_log, ephemeral=True)
                except aiosqlite.Error as e:
                    logging.exception(f"A SQLite error occurred in the levelup command for: '{character_name}!: {e}")
                    await interaction.followup.send(
                        f"A SQLite error occurred in the levelup command for: '{character_name}'. Error: {e}.",
                        ephemeral=True
                    )

        else:
            await interaction.followup.send("You must use at least one job.")
            return

    @character_group.command(name='trialup', description='Apply mythic tiers to your character')
    @app_commands.autocomplete(character_name=own_character_select_autocompletion)
    async def trialup(self, interaction: discord.Interaction, character_name: str, amount: int):
        guild_id = interaction.guild_id
        guild = interaction.guild
        author = interaction.user.name
        await interaction.response.defer(thinking=True, ephemeral=True)
        if amount >= 1:
            async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as conn:
                cursor = await conn.cursor()
                try:
                    await cursor.execute(
                        "SELECT Character_Name, Personal_Cap, Level, tier, trials, Thread_ID from player_characters where Player_Name = ? AND (Character_Name = ? OR Nickname = ?)",
                        (interaction.user.name, character_name, character_name))
                    player_info = await cursor.fetchone()
                    if player_info is None:
                        await interaction.followup.send(
                            f"Character {character_name} not found.",
                            ephemeral=True
                        )
                    else:
                        (character_name, personal_cap, level, tier, trials, logging_thread_id) = player_info
                        character_max_mythic = await get_max_mythic(guild_id, level)
                        print(character_max_mythic)
                        if tier >= character_max_mythic:
                            await interaction.followup.send(
                                f"{character_name} is already at the maximum tier of {character_max_mythic}.",
                                ephemeral=True
                            )
                        else:
                            async with config_cache.lock:
                                configs = config_cache.cache.get(guild_id)
                                if configs:
                                    item_id = configs.get('UBB_Mythic_Trial')
                                    use_custom_store = configs.get('Use_Custom_Store')
                            if not use_custom_store:
                                await interaction.followup.send("UBB is no longer the default and it's integrations have been removed")
                                return
                            else:
                                item = await server_inventory_check(guild_id, interaction.user.id, item_id, amount)

                            if item == 0:
                                await interaction.followup.send(
                                    f"Insufficient Mythic Trials to apply to {character_name}.",
                                    ephemeral=True
                                )

                            else:
                                used = 0
                                mythic_results = None
                                (tier, total_trials, trials_remaining, trial_change) = (0, 0, 0, 0)
                                while used < item and tier < character_max_mythic:
                                    used += 1
                                    mythic_results = await mythic_calculation(
                                        character_name=character_name,
                                        level=level,
                                        trials=trials,
                                        trial_change=1,
                                        tier=tier,
                                        guild_id=guild_id)
                                    (tier, trials, trials_remaining, trial_change) = mythic_results

                                if not mythic_results:
                                    await interaction.followup.send(
                                        f"An error occurred whilst mythic information for '{character_name}'.",
                                        ephemeral=True)
                                    return

                                character_updates = UpdateCharacterData(
                                    mythic_package=(tier, trials, trials_remaining),
                                    character_name=character_name
                                )
                                await update_character(
                                    guild_id=guild_id,
                                    change=character_updates
                                )
                                await character_embed(
                                    character_name=character_name,
                                    guild=guild)
                                character_changes = CharacterChange(
                                    character_name=character_name,
                                    author=author,
                                    source='Trial Up!',
                                    tier=tier,
                                    trial_change=used,
                                    trials_remaining=trials_remaining,
                                    trials=trials)

                                character_log = await log_embed(
                                    character_changes,
                                    guild,
                                    logging_thread_id,
                                    self.bot)
                                await interaction.followup.send(embed=character_log, ephemeral=True)
                                await roleplay.handle_use(
                                    db=conn,
                                    interaction=interaction,
                                    user_id=interaction.user.id,
                                    item_id=item_id,
                                    amount=used
                                )
                except aiosqlite.Error as e:
                    logging.exception(f"A SQLite error occurred in the trialup command for: '{character_name}!: {e}")
                    await interaction.followup.send(
                        f"A SQLite error occurred in the trialup command for: '{character_name}'. Error: {e}.",
                        ephemeral=True
                    )
        else:
            await interaction.followup.send("You must use at least one mythic trial.")

    @character_group.command(name='pouch', description='Use a gold pouch to enrich your character')
    @app_commands.autocomplete(character_name=own_character_select_autocompletion)
    async def pouch(self, interaction: discord.Interaction, character_name: str):
        guild_id = interaction.guild_id
        guild = interaction.guild
        author = interaction.user.name
        await interaction.response.defer(thinking=True, ephemeral=True)
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as conn:
            cursor = await conn.cursor()
            try:
                await cursor.execute(
                    "SELECT Character_Name, Oath, Level, Gold, Gold_Value, Gold_Value_Max, Thread_ID FROM Player_Characters WHERE Player_Name = ? AND (Character_Name = ? OR Nickname = ?)",
                    (interaction.user.name, character_name, character_name))
                player_info = await cursor.fetchone()
                if player_info is None:
                    await interaction.followup.send(
                        f"Character {character_name} not found.",
                        ephemeral=True
                    )
                else:
                    (character_name, oath, level, gold, gold_value, gold_value_max, logging_thread_id) = player_info
                    await cursor.execute("SELECT WPL FROM Milestone_System WHERE LEVEL =?", (level,))
                    gold_pouch = await cursor.fetchone()
                    if gold_pouch is None:
                        await interaction.followup.send(
                            f"Gold Pouch for level {level} not found.",
                            ephemeral=True
                        )
                    else:
                        gold_pouch = gold_pouch[0]
                        if gold_value_max >= gold_pouch:
                            await interaction.followup.send(
                                f"{character_name} is already at the maximum gold pouch value of {gold_pouch} with their total wealth of {gold_value_max}.",
                                ephemeral=True
                            )
                        else:
                            async with config_cache.lock:
                                configs = config_cache.cache.get(guild_id)
                                if configs:
                                    item_id = configs.get('UBB_Gold_Pouch')
                                    custom_store = configs.get('Use_Custom_Store')
                            if not custom_store:
                                await interaction.followup.send(
                                    "UBB is no longer the default and it's integrations have been removed")
                                return
                            else:
                                item = await server_inventory_check(guild_id, interaction.user.id, item_id, 1)
                            if item <= 0:
                                await interaction.followup.send(
                                    f"Insufficient Gold Pouches to apply to {character_name}.",
                                    ephemeral=True
                                )
                            else:
                                gold_result = await gold_calculation(
                                    guild_id=guild_id,
                                    character_name=character_name,
                                    author_name=interaction.user.name,
                                    author_id=interaction.user.id,
                                    level=level,
                                    oath=oath,
                                    gold=Decimal(gold),
                                    gold_value=Decimal(gold_value),
                                    gold_value_max=Decimal(gold_value_max),
                                    gold_change=Decimal(gold_pouch - gold_value_max),
                                    gold_value_change=None,
                                    gold_value_max_change=None,
                                    source='Gold Pouch',
                                    reason='Gold Pouch')
                                (calculated_difference, calculated_gold, calculated_gold_value,
                                 calculated_gold_value_max, transaction_id) = gold_result
                                print(calculated_difference, calculated_gold, calculated_gold_value,
                                      calculated_gold_value_max, transaction_id)
                                print(gold, gold_value)
                                if calculated_gold <= gold or calculated_gold_value <= gold_value:
                                    await interaction.followup.send(
                                        f"Your oaths fore swear further reward of gold!",
                                        ephemeral=True
                                    )
                                else:
                                    await roleplay.handle_use(
                                        db=conn,
                                        interaction=interaction,
                                        user_id=interaction.user.id,
                                        item_id=item_id
                                    )

                                    character_updates = UpdateCharacterData(

                                        gold_package=(
                                            calculated_gold, calculated_gold_value, calculated_gold_value_max),
                                        character_name=character_name)

                                    await update_character(
                                        guild_id=guild_id,
                                        change=character_updates)

                                    await character_embed(
                                        character_name=character_name,
                                        guild=guild)

                                    character_changes = CharacterChange(
                                        character_name=character_name,
                                        author=author,
                                        source=f'Pouch with transaction id of {transaction_id}',
                                        gold_change=calculated_difference,
                                        gold=calculated_gold,
                                        gold_value=calculated_gold_value)

                                    character_log = await log_embed(
                                        character_changes,
                                        guild,
                                        logging_thread_id,
                                        self.bot)
                                    await interaction.followup.send(embed=character_log, ephemeral=True)
            except aiosqlite.Error as e:
                logging.exception(f"A SQLite error occurred in the pouch command for: '{character_name}!: {e}")
                await interaction.followup.send(
                    f"A SQLite error occurred in the pouch command for: '{character_name}'. Error: {e}.",
                    ephemeral=True
                )

    @character_group.command(name='heroism', description='spend hero points!')
    @app_commands.autocomplete(character=character_select_autocompletion)
    async def hero_points(self, interaction: discord.Interaction, character: str, usage: int,
                          reason: str):
        """Add or remove from a player's fame and prestige!"""
        guild_id = interaction.guild_id
        guild = interaction.guild
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute(
                    "SELECT Thread_ID, Heroism, Hero_Points, Hero_Points_Max from Player_Characters where Character_Name = ?",
                    (character,))
                player_info = await cursor.fetchone()
                if player_info is not None:
                    (thread_id, heroism, info_hero_points, hero_points_max) = player_info
                    print(usage, info_hero_points)
                    if heroism == 2:
                        await interaction.followup.send("Fuck off, this character is an antihero.")
                        fetch_won = interaction.guild.fetch_member(179011441825677313)
                        if fetch_won:
                            await interaction.channel.send(content=f"Hey, <@179011441825677313>, {interaction.user} just tried to spend hero points when they're an antihero. Ban them.")
                        return
                    if usage > info_hero_points:
                        await interaction.followup.send("YOU ARE TOO MUCH OF A PEASANT FOR __MY__ GLORIOUS HERO POINTS")
                        return
                    new_hero_points = info_hero_points - usage
                    reason = "" if not reason else reason + "\r\n"
                    if new_hero_points != info_hero_points:
                        change = new_hero_points - info_hero_points
                        character_updates = UpdateCharacterData(
                            character_name=character,
                            hero_package=(heroism, new_hero_points))
                        await update_character(guild_id=guild_id, change=character_updates)
                        reason += f"Hero point change by {interaction.user.name}.\r\n" + reason if reason is not None else f"Hero Point change by {interaction.user.name}."

                        character_changes = CharacterChange(
                            character_name=character,
                            author=interaction.user.name,
                            heroism=heroism,
                            hero_point_change=change)
                        log_update = await log_embed(
                            guild=guild,
                            thread=thread_id,
                            change=character_changes,
                            bot=self.bot)
                        await character_embed(character_name=character,guild=interaction.guild)
                        await interaction.followup.send(embed=log_update)
                    else:
                        await interaction.followup.send("YOU ABSOLUTE MONKEY. WHAT DID YOU EVEN CHANGE?")
                else:
                    await interaction.followup.send_message(
                        f"Character {character} does not exist! Could not complete transaction!")
        except (aiosqlite, TypeError, ValueError) as e:
            logging.exception(f"An error occurred whilst updating a character's hero points: {e}")
            await interaction.followup.send_message(
                f"An error occurred whilst updating a character's hero points. {e}")

    # Nested group
    title_group = discord.app_commands.Group(
        name='title',
        description='Event settings commands',
        parent=character_group
    )

    @title_group.command(name='display', description='Display titles from the store!')
    async def display_titles(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            offset = 1
            limit = 20
            view = views.TitleShopView(
                user_id=interaction.user.id,
                guild_id=guild_id,
                offset=offset,
                limit=limit,
                interaction=interaction)
            await view.send_initial_message()
        except (TypeError, ValueError) as e:
            logging.exception(f"an error occurred attempting to generate display command!': {e}")
            await interaction.followup.send(
                f"an error occurred attempting to generate display command!'. Error: {e}.",
                ephemeral=True
            )

    @title_group.command(name='use', description='Use a title from the store!')
    @app_commands.autocomplete(title=title_autocomplete)
    @app_commands.choices(gender=[discord.app_commands.Choice(name='Masculine', value=1),
                                  discord.app_commands.Choice(name='Feminine', value=2)])
    @app_commands.autocomplete(character_name=own_character_select_autocompletion)
    async def use(self, interaction: discord.Interaction, character_name: str, title: str,
                  gender: discord.app_commands.Choice[int]):
        guild_id = interaction.guild_id
        guild = interaction.guild
        author = interaction.user.name
        await interaction.response.defer(thinking=True, ephemeral=True)
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as conn:
            cursor = await conn.cursor()
            try:
                await cursor.execute(
                    "select True_character_name, title, fame, prestige, Logging_ID from Player_Characters where Player_Name = ? and (Character_Name = ? or Nickname = ?)",
                    (author, character_name, character_name))
                #               player validation to confirm if player is the owner of the character and they exist.
                player_info = await cursor.fetchone()
                if player_info is None:
                    await interaction.followup.send(
                        f"Character {character_name} not found.",
                        ephemeral=True
                    )
                else:  # Player found
                    (true_character_name, player_title, player_fame, player_prestige, logging_thread_id) = player_info
                    await cursor.execute(
                        "SELECT ID, Fame, Masculine_Name, Feminine_Name from Store_Title where Masculine_name = ? or Feminine_name = ?",
                        (title, title))
                    title_information = await cursor.fetchone()  # Title validation
                    if title_information is None:
                        await interaction.followup.send(
                            f"Title {title} not found.",
                            ephemeral=True
                        )
                    else:  # Title Found
                        title_name = title_information[2] if gender.value == 1 else title_information[3]
                        title_fame = 0 if title_information is None else title_information[1]
                        title_id = title_information[0]
                        if player_title is not None:
                            logging.info(
                                f"Player has a title {player_title}, validating if it is superior to the new title.")
                            await cursor.execute(
                                "SELECT ID, Fame, Masculine_Name, Feminine_Name from Store_Title where Masculine_name = ? or Feminine_name = ?",
                                (player_title, player_title))
                            previous_title_information = await cursor.fetchone()
                            if previous_title_information[1] >= title_fame:
                                await interaction.followup.send(
                                    f"{character_name} already has the superior title {previous_title_information[2]}",
                                    ephemeral=True
                                )
                                return
                            else:  # New Title is superior, remove fame from the older title.
                                title_fame -= previous_title_information[1]

                        async with config_cache.lock:
                            configs = config_cache.cache.get(guild_id)
                            if configs:
                                custom_store = configs.get('Use_Custom_Store')
                        if not custom_store:
                            await interaction.followup.send(
                                "UBB is no longer the default and it's integrations have been removed")
                            return
                        else:
                            item_validation = await server_inventory_check(
                                guild_id,
                                interaction.user.id,
                                title_id,
                                1)

                        if item_validation == 0:  # UBB Validation to ensure they have the title in their inventory.
                            await interaction.followup.send(
                                f"Insufficient titles to apply to {character_name}.",
                                ephemeral=True
                            )
                        else:  # Title is in inventory
                            fame_calculation = calculate_fame(
                                character_name=character_name,
                                fame=player_fame,
                                fame_change=title_fame,
                                prestige=player_prestige,
                                prestige_change=title_fame)
                            (total_fame, adjusted_fame, total_prestige, adjusted_prestige) = fame_calculation
                            await cursor.execute(
                                "UPDATE Player_Characters SET Title = ?, Fame = ?, prestige = ? WHERE Character_Name = ?",
                                (title_name, total_fame, total_prestige, character_name))
                            await conn.commit()
                            await roleplay.handle_use(
                                db=conn,
                                interaction=interaction,
                                user_id=interaction.user.id,
                                item_id=title_id)
                            await character_embed(
                                character_name=character_name,
                                guild=guild)
                            character_changes = CharacterChange(
                                character_name=character_name,
                                author=author,
                                source=f'Entitle applying the title of {title_name}',
                                fame=total_fame,
                                fame_change=adjusted_fame,
                                prestige=total_prestige,
                                prestige_change=adjusted_prestige)
                            character_log = await log_embed(
                                character_changes,
                                guild,
                                logging_thread_id,
                                self.bot)
                            await interaction.followup.send(embed=character_log, ephemeral=True)
            except (aiosqlite.Error, TypeError, ValueError) as e:
                logging.exception(f"An error occurred in the retire command whilst looking for '{character_name}': {e}")
                await interaction.followup.send(
                    f"An error occurred whilst looking for '{character_name}'. Error: {e}.",
                    ephemeral=True
                )

    @title_group.command(name='swap', description='change the gender for your title!')
    @app_commands.autocomplete(character_name=own_character_select_autocompletion)
    async def swap(self, interaction: discord.Interaction, character_name: str):
        guild_id = interaction.guild_id
        guild = interaction.guild
        author = interaction.user.name
        await interaction.response.defer(thinking=True, ephemeral=True)
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as conn:
            cursor = await conn.cursor()
            try:
                await cursor.execute(
                    'SELECT True_Character_Name, Title, Fame, Logging_ID FROM Player_Characters WHERE Player_Name = ? AND (Character_Name = ? OR Nickname = ?)',
                    (author, character_name, character_name))
                player_info = await cursor.fetchone()
                if player_info is None:
                    await interaction.followup.send(
                        f"Character {character_name} not found.",
                        ephemeral=True
                    )
                else:  # Character Found
                    (true_character_name, player_title, player_fame, logging_thread_id) = player_info
                    if player_title is None:
                        await interaction.followup.send(
                            f"{author} does not have a title to swap.",
                            ephemeral=True
                        )
                    else:  # Character has title to swap
                        await cursor.execute(
                            "SELECT ID, Fame, Masculine_Name, Feminine_Name from Store_Title where Masculine_name = ? or Feminine_name = ?",
                            (player_title, player_title))
                        title_information = await cursor.fetchone()
                        if title_information is None:
                            logging.info(f'Title of {player_title} not found despite being assigned!')
                            await interaction.followup.send(
                                f"Title {player_title} not found.",
                                ephemeral=True
                            )
                        else:  # Title Found
                            title_name = title_information[2] if player_title == title_information[3] else \
                                title_information[3]
                            await cursor.execute(
                                "UPDATE Player_Characters SET Title = ? WHERE Character_Name = ?",
                                (title_name, character_name))
                            await conn.commit()
                            await character_embed(
                                character_name=character_name,
                                guild=guild)
                            character_changes = CharacterChange(
                                character_name=character_name,
                                author=author,
                                source=f'Entitle swapping the gender of {player_title}')
                            character_log = await log_embed(character_changes, guild,
                                                                             logging_thread_id, self.bot)
                            await interaction.followup.send(embed=character_log, ephemeral=True)
            except (aiosqlite.Error, TypeError, ValueError) as e:
                logging.exception(
                    f"An error occurred in the retire command whilst looking for '{character_name}': {e}")
                await interaction.followup.send(
                    f"An error occurred whilst looking for '{character_name}'. Error: {e}.",
                    ephemeral=True
                )

                # Nested group

    prestige_group = discord.app_commands.Group(
        name='prestige',
        description='Event settings commands',
        parent=character_group
    )

    @prestige_group.command(name='display',
                            description='Display available options from the store.')
    async def display_prestige(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            offset = 1
            limit = 20
            view = views.PrestigeShopView(user_id=interaction.user.id, guild_id=guild_id, offset=offset, limit=limit,
                                    interaction=interaction)
            await view.send_initial_message()
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"Couldn't display the store options: {e}")
            await interaction.followup.send(
                f"An error occurred whilst displaying the store options. Error: {e}.")

    @prestige_group.command(
        name='prestige',
        description='Request something of a GM using your prestige as a resource.'
    )
    @app_commands.autocomplete(character_name=own_character_select_autocompletion)
    @app_commands.autocomplete(name=fame_autocomplete)
    async def request(
            self,
            interaction: discord.Interaction,
            character_name: str,
            name: str,
            approver: discord.Member
    ):
        guild_id = interaction.guild_id
        author_id = interaction.user.id
        author_name = interaction.user.name

        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as conn:
                cursor = await conn.cursor()

                # Fetch player information
                await cursor.execute(
                    """
                    SELECT True_Character_Name, Character_Name, Fame, Prestige, Thread_ID
                    FROM Player_Characters
                    WHERE Player_Name = ? AND (Character_Name = ? OR Nickname = ?)
                    """,
                    (author_name, character_name, character_name)
                )
                player_info = await cursor.fetchone()

                if player_info is None:
                    await interaction.followup.send(
                        f"{author_name} does not have a character named '{character_name}' registered.",
                        ephemeral=True
                    )
                    return

                (true_character_name, character_name, fame, prestige, logging_thread) = player_info

                # Fetch item information
                await cursor.execute(
                    """
                    SELECT Fame_Required, Prestige_Cost, Name, Use_Limit
                    FROM Store_Fame
                    WHERE Name = ?
                    """,
                    (name,)
                )
                item_info = await cursor.fetchone()

                if item_info is None:
                    await interaction.followup.send(
                        f"The item '{name}' does not exist in the store.",
                        ephemeral=True
                    )
                    return

                (fame_required, prestige_cost, item_name, use_limit) = item_info

                # Check usage count
                await cursor.execute(
                    """
                    SELECT COUNT(Item_Name)
                    FROM A_Audit_Prestige
                    WHERE Author_ID = ? AND Character_Name = ? AND Item_Name = ? AND IsAllowed = 1
                    """,
                    (author_id, character_name, name)
                )
                usage_count_row = await cursor.fetchone()
                usage_count = usage_count_row[0] if usage_count_row else 0

                # Validate conditions
                if usage_count >= use_limit:
                    await interaction.followup.send(
                        f"{author_name} has reached the usage limit for this item.",
                        ephemeral=True
                    )
                    return

                if prestige < prestige_cost:
                    await interaction.followup.send(
                        f"{author_name} does not have enough prestige to use this item.",
                        ephemeral=True
                    )
                    return

                if fame < fame_required:
                    await interaction.followup.send(
                        f"{author_name} does not have enough fame to use this item.",
                        ephemeral=True
                    )
                    return

                # Insert proposition request
                await cursor.execute(
                    """
                    INSERT INTO A_Audit_Prestige
                    (Author_ID, Character_Name, Item_Name, Prestige_Cost, IsAllowed, Time)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (author_id, character_name, name, prestige_cost, 0, datetime.datetime.now())
                )
                await conn.commit()

                # Retrieve the proposition ID
                await cursor.execute(
                    "SELECT MAX(Transaction_ID) FROM A_Audit_Prestige WHERE Character_Name = ?",
                    (character_name,)
                )
                proposition_id_row = await cursor.fetchone()
                proposition_id = proposition_id_row[0] if proposition_id_row else None

                if proposition_id is None:
                    await interaction.followup.send(
                        "Failed to create the proposition request.",
                        ephemeral=True
                    )
                    return
                content = (
                    f"{approver.mention}, {author_name} is requesting '{name}' with proposition ID {proposition_id}.\n"
                    "Do you accept or reject this proposition?"
                )
                # Create and send the PropositionView
                view = views.PropositionViewRecipient(
                    allowed_user_id=approver.id,
                    requester_name=author_name,
                    character_name=character_name,
                    item_name=name,
                    guild_id=guild_id,
                    prestige_cost=prestige_cost,
                    proposition_id=proposition_id,
                    bot=self.bot,
                    prestige=prestige,
                    logging_thread=logging_thread,
                    interaction=interaction,
                    content=content
                )
                await view.send_initial_message()
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(
                f"An error occurred in the 'request' command for '{character_name}': {e}"
            )
            await interaction.followup.send(
                f"An error occurred while processing your request: {e}",
                ephemeral=True
            )

    @prestige_group.command(
        name='history',
        description='View your proposition history.'
    )
    @app_commands.autocomplete(character_name=own_character_select_autocompletion)
    @app_commands.autocomplete(name=fame_autocomplete)
    async def history(self, interaction: discord.Interaction, character_name: str, name: typing.Optional[str],
                      page_number: int = 1):
        guild_id = interaction.guild_id
        await interaction.response.defer(thinking=True, ephemeral=True)

        try:
            async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as conn:
                cursor = await conn.cursor()

                # Decide which query to execute based on whether 'name' is provided
                if name is not None:
                    await cursor.execute(
                        "SELECT COUNT(*) FROM A_Audit_Prestige WHERE Character_Name = ? AND Item_Name = ?",
                        (character_name, name)
                    )
                else:
                    await cursor.execute(
                        "SELECT COUNT(*) FROM A_Audit_Prestige WHERE Character_Name = ?",
                        (character_name,)
                    )

                count_row = await cursor.fetchone()
                proposition_count = count_row[0] if count_row else 0

                if proposition_count == 0:
                    await interaction.followup.send(
                        f"No propositions found for '{character_name}'.",
                        ephemeral=True
                    )
                    return

                # Set up pagination variables
                page_number = min(max(page_number, 1), math.ceil(proposition_count / 20))
                items_per_page = 20
                offset = (page_number - 1) * items_per_page

                # Create and send the view with the results
                view = views.PrestigeHistoryView(
                    user_id=interaction.user.id,
                    guild_id=guild_id,
                    character_name=character_name,
                    item_name=name,
                    limit=items_per_page,
                    offset=offset,
                    interaction=interaction
                )
                await view.send_initial_message()

        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(
                f"An error occurred in the 'history' command while fetching data for '{character_name}': {e}"
            )
            await interaction.followup.send(
                f"An error occurred while fetching your proposition history. Please try again later.",
                ephemeral=True
            )

    @character_group.command(name='cap', description='Set the personal cap of a character')
    @app_commands.autocomplete(character_name=own_character_select_autocompletion)
    async def cap(self, interaction: discord.Interaction, character_name: str, level_cap: int):
        """Set the personal level cap of a character."""
        try:
            # Clean and validate input
            character_name_cleaned = unidecode(str.title(character_name)).replace(";", "").replace(")", "")
            author_name = interaction.user.name
            author_id = interaction.user.id
            guild_id = interaction.guild_id
            guild = interaction.guild

            # Defer the response to allow for processing time
            await interaction.response.defer(thinking=True, ephemeral=True)
            # Connect to the database
            async with (aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as conn):
                cursor = await conn.cursor()
                await cursor.execute("SELECT MIN(level), MAX(level) from Milestone_System")
                level_range = await cursor.fetchone()
                if not level_range[0] <= level_cap <= level_range[1]:
                    await interaction.followup.send(
                        f"Level cap must be between {level_range[0]} and {level_range[1]}. You provided: {level_cap}",
                        ephemeral=True
                    )
                    return
                    # Fetch character information
                await cursor.execute(
                    """
                    SELECT Character_Name, Milestones, Level, tier, Trials, Thread_ID, Region, Heroism, Hero_Points, Hero_Points_Max
                    FROM Player_Characters
                    WHERE Player_Name = ? AND (Character_Name = ? OR Nickname = ?)
                    """,
                    (author_name, character_name_cleaned, character_name_cleaned)
                )
                character_info = await cursor.fetchone()

                if character_info is None:
                    await interaction.followup.send(
                        f"Character '{character_name}' not found.",
                        ephemeral=True
                    )
                    return

                (character_name_db, milestones, level, tier, trials, thread_id, region, heroism, hero_points, hero_points_max) = character_info

                # Update the personal cap in the database
                await cursor.execute(
                    "UPDATE Player_Characters SET Personal_Cap = ? WHERE Character_Name = ?",
                    (level_cap, character_name_db)
                )
                await conn.commit()

                # Initialize character changes
                character_changes = CharacterChange(
                    character_name=character_name_db,
                    author=author_name,
                    source=f'Cap Adjustment to {level_cap}'
                )
                if level_cap != level:
                    # Perform level calculation
                    character_updates = UpdateCharacterData(character_name=character_name_db)
                    try:
                        level_result = await level_calculation(
                            guild=guild,
                            guild_id=guild_id,
                            author_id=author_id,
                            character_name=character_name_db,
                            personal_cap=level_cap,
                            level=level,
                            base=milestones,
                            easy=0,
                            medium=0,
                            hard=0,
                            deadly=0,
                            misc=0,
                            region=region
                        )

                        # Check if level_result is a tuple
                        if isinstance(level_result, tuple):
                            (calculated_level,
                             calculated_total_milestones,
                             min_milestones,
                             calculated_remaining_milestones,
                             milestones_required,
                             awarded_milestone_total) = level_result
                            character_updates.level_package = (
                                calculated_level, calculated_total_milestones, calculated_remaining_milestones)
                            character_changes.level = calculated_level
                            character_changes.milestone_change = 0
                            character_changes.milestones_total = calculated_total_milestones
                            character_changes.milestones_remaining = calculated_remaining_milestones
                        else:
                            # Handle unexpected return type
                            character_changes.source += " Error adjusting level: Unexpected result from level calculation."
                            logging.error(f"Unexpected result from level_calculation: {level_result}")

                    except CalculationAidFunctionError as e:
                        character_changes.source += f" Error adjusting level: {e}"
                        logging.exception(f"Level calculation error for character '{character_name_db}': {e}")
                    # Perform mythic calculation
                    try:
                        mythic_result = await mythic_calculation(
                            guild_id=guild_id,
                            character_name=character_name_db,
                            level=level,
                            tier=tier,
                            trials=trials,
                            trial_change=0
                        )

                        if isinstance(mythic_result, tuple):
                            (tier, total_trials, trials_remaining, trial_change) = mythic_result
                            character_updates.mythic_package = (tier, total_trials, trials_remaining)
                            character_changes.tier = tier
                            character_changes.trials = total_trials
                            character_changes.trial_change = 0
                            character_changes.trials_remaining = trials_remaining
                        else:
                            # Handle unexpected return type
                            character_changes.source += " Error adjusting mythic: Unexpected result from mythic calculation."
                            logging.error(f"Unexpected result from mythic_calculation: {mythic_result}")

                    except CalculationAidFunctionError as e:
                        character_changes.source += f" Error adjusting mythic: {e}"
                        logging.exception(f"Mythic calculation error for character '{character_name_db}': {e}")

                    if calculated_level > level:
                        if heroism == 1:
                            async with config_cache.lock:
                                configs = config_cache.cache.get(guild_id)
                                if configs:
                                    hero_points_level = configs.get('Hero_Points_Level')
                            level_difference = calculated_level - level
                            hero_points_differential = hero_points_level * level_difference + hero_points
                            new_hero_points = min(hero_points_differential, hero_points_max)
                            if new_hero_points != hero_points:
                                character_updates.hero_package = (heroism, new_hero_points)
                                character_changes.hero_points = new_hero_points - hero_points
                                character_changes.heroism = heroism

                    # update the character
                    await update_character(change=character_updates, guild_id=guild_id)
                # Create and send the log embed
                character_log = await log_embed(character_changes, guild, thread_id, self.bot)
                await interaction.followup.send(embed=character_log, ephemeral=True)

                # Create and send the character embed
                embedded_character = await views.character_embed(character_name=character_name_db, guild=guild)
                if isinstance(embedded_character, str):
                    await interaction.followup.send(
                        f"An error occurred while fetching character information for '{character_name_db}'.",
                        ephemeral=True
                    )
                else:
                    (embed, embed_message_content, embed_channel_id) = embedded_character
                await interaction.followup.send(embed=embed, ephemeral=True)

        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"An error occurred in the 'cap' command: {e}")
            await interaction.followup.send(
                "An unexpected error occurred while processing your request. Please try again later.",
                ephemeral=True
            )

    home_group = discord.app_commands.Group(
        name='home',
        description='home group commands',
        parent=character_group
    )

    @home_group.command(name='create', description='Create a character owned location')
    @app_commands.autocomplete(item=autocomplete.rp_home_autocomplete)
    @app_commands.autocomplete(character_name=own_character_select_autocompletion)
    @app_commands.autocomplete(settlement=settlement_autocomplete)
    async def create_location(
            self,
            interaction: discord.Interaction,
            character_name: str,
            settlement: str,
            location_name: str,
            item: str,
            image: str=None):
        """Create a character owned location"""
        guild_id = interaction.guild_id
        author_name = interaction.user.name
        await interaction.response.defer(thinking=True, ephemeral=True)
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as conn:
            cursor = await conn.cursor()
            try:
                # Check if the character exists
                await cursor.execute(
                    "SELECT Character_Name, Message_ID FROM Player_Characters WHERE Player_Name = ? AND (Character_Name = ? OR Nickname = ?)",
                    (author_name, character_name, character_name))
                character_info = await cursor.fetchone()
                if character_info is None:
                    await interaction.followup.send(
                        f"Character '{character_name}' not found.",
                        ephemeral=True
                    )
                    return

                # Check if the location already exists
                await cursor.execute(
                    "SELECT settlement FROM Player_Homes WHERE Settlement = ? AND Character_Name = ?",
                    (settlement, character_name))
                existing_location = await cursor.fetchone()
                if existing_location:
                    await interaction.followup.send(
                        f"Characters can only have 1 Home per region",
                        ephemeral=True
                    )
                    return

                await cursor.execute(
                    "SELECT Item_Name, Item_Quantity From RP_Players_Items where Player_ID = ? and Item_Name = ?",
                    (interaction.user.id, item))
                item_info = await cursor.fetchone()
                if item_info is None:
                    await interaction.followup.send(
                        f"Item '{item}' not found.",
                        ephemeral=True
                    )
                    return

                await cursor.execute(
                    "SELECT KK.Region, KS.Settlement From KB_Kingdoms KK Left Join KB_Settlements KS on KK.Kingdom = KS.Kingdom where KS.Settlement = ?",
                    (settlement,)
                )
                settlement_info = await cursor.fetchone()
                if settlement_info is None:
                    await interaction.followup.send(
                        f"Settlement '{settlement}' not found.",
                        ephemeral=True
                    )
                    return
                (region, settlement) = settlement_info
                async with config_cache.lock:
                    configs = config_cache.cache.get(guild_id)
                    if configs:
                        channel_id = configs.get('Player_Owned_Channel')
                        bio_channel_id = configs.get('Accepted_Bio_Channel')
                        if channel_id is None:
                            await cursor.execute("Select Search From Admin where Identifier = 'Player_Owned_Channel'")
                            channel_fetch = await cursor.fetchone()
                            if channel_fetch is None:
                                await interaction.followup.send(
                                    f"Channel ID for 'Player_Owned_Channel' not found in the config.",
                                    ephemeral=True
                                )
                                return
                            channel_id = channel_fetch[0]
                        if bio_channel_id is None:
                            await cursor.execute("Select Search From Admin where Identifier = 'Accepted_Bio_Channel'")
                            bio_channel_fetch = await cursor.fetchone()
                            if bio_channel_fetch is None:
                                await interaction.followup.send(
                                    f"Channel ID for 'Accepted_Bio_Channel' not found in the config.",
                                    ephemeral=True
                                )
                                return
                            bio_channel_id = bio_channel_fetch[0]
                channel = interaction.guild.get_channel(channel_id)
                if channel is None:
                    channel = await interaction.guild.fetch_channel(channel_id)
                bio_channel = interaction.guild.get_channel(bio_channel_id)
                if bio_channel is None:
                    bio_channel = await interaction.guild.fetch_channel(bio_channel_id)
                bio_message = await bio_channel.fetch_message(character_info[1])
                title = f"{region} - {settlement} - {location_name}"

                embed = discord.Embed(
                    title=location_name,
                    description=f"region: {region} settlement: {settlement}",
                    url=f"https://discord.com/channels/{interaction.guild_id}/{bio_channel_id}/{bio_message.id}")
                if image:
                    embed.set_image(url=image)
                embed.set_footer(text=f"Belongs to {character_name}")
                message = await channel.send(embed=embed)
                thread = await message.create_thread(name=f'{title}', auto_archive_duration=10080)
                thread_message = await thread.send(f"{interaction.user.mention} Welcome to your new home! Please Send 5 base messages with '.' or similar to pin them!")
                async with build_home_cache.lock:
                    build_home_cache.cache[guild_id] = {thread.id, (6, interaction.user.id, thread_message.id)}

                if item_info[1] == 1:
                    await cursor.execute("DELETE FROM RP_Players_Items WHERE Player_ID = ? and Item_Name = ?",
                                         (interaction.user.id, item))
                else:
                    await cursor.execute(
                        "UPDATE RP_Players_Items SET Item_Quantity = Item_Quantity - 1 WHERE Player_ID = ? and Item_Name = ?",
                        (interaction.user.id, item))

                # Insert the new location into the database
                await cursor.execute(
                    "INSERT INTO Player_Homes (Settlement, Character_Name, Thread_ID) VALUES (?, ?, ?)",
                    (settlement, character_name, thread.id))
                await conn.commit()

                await interaction.followup.send(
                    f"Location '{location_name}' created successfully in '{settlement}'.",
                    ephemeral=True
                )
            except aiosqlite.Error as e:
                logging.exception(f"A SQLite error occurred in the create_location command: {e}")
                await interaction.followup.send(
                    f"An error occurred while creating the location. Error: {e}",
                    ephemeral=True
                )

    @home_group.command(name='delete', description='Delete a character owned location')
    @app_commands.autocomplete(character_name=own_character_select_autocompletion)
    @app_commands.autocomplete(settlement=settlement_autocomplete)
    async def delete_location(self, interaction: discord.Interaction, character_name: str, settlement: str):
        """Delete a character owned location"""
        guild_id = interaction.guild_id
        author_name = interaction.user.name
        await interaction.response.defer(thinking=True, ephemeral=True)
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as conn:
            cursor = await conn.cursor()
            try:
                # Check if the character exists
                await cursor.execute(
                    "SELECT Character_Name FROM Player_Characters WHERE Player_Name = ? AND (Character_Name = ? OR Nickname = ?)",
                    (author_name, character_name, character_name))
                character_info = await cursor.fetchone()
                if character_info is None:
                    await interaction.followup.send(
                        f"Character '{character_name}' not found.",
                        ephemeral=True
                    )
                    return

                # Check if the location exists
                await cursor.execute(
                    "SELECT Thread_ID FROM Player_Homes WHERE Character_Name = ? AND Settlement = ?",
                    (character_name, settlement))
                location_info = await cursor.fetchone()
                if location_info is None:
                    await interaction.followup.send(
                        f"Location for '{character_name}' not found.",
                        ephemeral=True
                    )
                    return

                async with config_cache.lock:
                    configs = config_cache.cache.get(guild_id)
                    if configs:
                        channel_id = configs.get('Player_Owned_Channel')
                        if channel_id is None:
                            await cursor.execute("Select Search From Admin where Identifier = 'Player_Owned_Channel'")
                            channel_fetch = await cursor.fetchone()
                            if channel_fetch is None:
                                await interaction.followup.send(
                                    f"Channel ID for 'Player_Owned_Channel' not found in the config.",
                                    ephemeral=True
                                )
                                return
                            channel_id = channel_fetch[0]
                channel = interaction.guild.get_channel(channel_id)
                if channel is None:
                    await interaction.guild.fetch_channel(channel_id)
                thread_id = location_info[0]
                thread = channel.get_thread(thread_id)
                if thread is None:
                    await interaction.followup.send(
                        f"Thread '{thread_id}' not found.",
                        ephemeral=True
                    )
                    return
                await thread.delete()
                message = await channel.fetch_message(thread_id)
                await message.delete()
                async with build_home_cache.lock:
                    guild_cache = build_home_cache.cache.get[guild_id]
                    if thread.id in guild_cache:
                        guild_cache.pop(thread.id)
                # Delete the location from the database
                await cursor.execute(
                    "DELETE FROM Player_Homes WHERE Character_Name = ?",
                    (character_name,))
                await conn.commit()

                await interaction.followup.send(
                    f"Location for '{character_name}' deleted successfully.",
                    ephemeral=True
                )
            except aiosqlite.Error as e:
                logging.exception(f"A SQLite error occurred in the delete_location command: {e}")
                await interaction.followup.send(
                    f"An error occurred while deleting the location. Error: {e}",
                    ephemeral=True
                )

    @home_group.command(name="modify", description="Modify a character owned location")
    @app_commands.autocomplete(character_name=own_character_select_autocompletion)
    @app_commands.autocomplete(settlement=settlement_autocomplete)
    async def modify_location(self, interaction: discord.Interaction, character_name: str, settlement: str,
                              new_location_name: str, new_image: str = None):
        """Modify a character owned location"""
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as conn:
                cursor = await conn.cursor()
                # Check if the character exists
                await cursor.execute(
                    "SELECT Character_Name, Message_ID FROM Player_Characters WHERE Player_Name = ? AND (Character_Name = ? OR Nickname = ?)",
                    (interaction.user.name, character_name, character_name))
                character_info = await cursor.fetchone()
                if character_info is None:
                    await interaction.followup.send(
                        f"Character '{character_name}' not found.",
                        ephemeral=True
                    )
                    return
                # Check if the location exists
                await cursor.execute(
                    "SELECT Thread_ID FROM Player_Homes WHERE Character_Name = ? AND Settlement = ?",
                    (character_name, settlement))
                location_info = await cursor.fetchone()
                if location_info is None:
                    await interaction.followup.send(
                        f"Location for '{character_name}' not found.",
                        ephemeral=True
                    )
                    return
                # Update the location name in the database
                async with config_cache.lock:
                    configs = config_cache.cache.get(interaction.guild.id)
                    if configs:
                        channel_id = configs.get('Player_Owned_Channel')
                        bio_channel_id = configs.get('Accepted_Bio_Channel')
                        if channel_id is None:
                            await cursor.execute("Select Search From Admin where Identifier = 'Player_Owned_Channel'")
                            channel_fetch = await cursor.fetchone()
                            if channel_fetch is None:
                                await interaction.followup.send(
                                    f"Channel ID for 'Player_Owned_Channel' not found in the config.",
                                    ephemeral=True
                                )
                                return
                            channel_id = channel_fetch[0]
                        if bio_channel_id is None:
                            await cursor.execute("Select Search From Admin where Identifier = 'Accepted_Bio_Channel'")
                            bio_channel_fetch = await cursor.fetchone()
                            if bio_channel_fetch is None:
                                await interaction.followup.send(
                                    f"Channel ID for 'Accepted_Bio_Channel' not found in the config.",
                                    ephemeral=True
                                )
                                return
                            bio_channel_id = bio_channel_fetch[0]
                channel = interaction.guild.get_channel(channel_id)
                if channel is None:
                    channel = await interaction.guild.fetch_channel(channel_id)
                bio_channel = interaction.guild.get_channel(bio_channel_id)
                if bio_channel is None:
                    bio_channel = await interaction.guild.fetch_channel(bio_channel_id)
                bio_message = await bio_channel.fetch_message(character_info[1])
                thread_id = location_info[0]
                thread = channel.get_thread(thread_id)
                message = await channel.fetch_message(thread_id)
                if not thread or not message:
                    await interaction.followup.send(
                        f"Thread '{thread_id}' not found.",
                        ephemeral=True
                    )
                    return
                await cursor.execute(
                    "SELECT KK.Region, KS.Settlement From KB_Kingdoms KK Left Join KB_Settlements KS on KK.Kingdom = KS.Kingdom where KS.Settlement = ?",
                    (settlement,)
                )
                settlement_info = await cursor.fetchone()

                title = f"{settlement_info[0]} - {settlement} - {new_location_name}"
                embed = discord.Embed(
                    title=new_location_name,
                    description=f"region: {settlement_info[0]} settlement: {settlement}",
                    url=f"https://discord.com/channels/{interaction.guild_id}/{bio_channel_id}/{bio_message.id}")
                if new_image:
                    embed.set_image(url=new_image)
                embed.set_footer(text=f"Belongs to {character_name}")
                await thread.edit(name=title)
                await message.edit(content=f"# {title}")

                await interaction.followup.send(
                    "Location name updated successfully.",
                    ephemeral=True
                )
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"An error occurred in the modify_location command: {e}")
            await interaction.followup.send(
                f"An error occurred while modifying the location. Error: {e}",
                ephemeral=True
            )

    display_group = discord.app_commands.Group(
        name='display',
        description='level_range group commands',
        parent=character_group
    )

    @display_group.command(name='character',
                           description='display all character information or specific character information.')
    @app_commands.describe(
        character_name="the character you are looking for. If you provide a character name, the command will display information for that character only prioritizing the character over the player.")
    @app_commands.autocomplete(character_name=autocomplete.character_select_autocompletion)
    async def display_info(self, interaction: discord.Interaction, player_name: typing.Optional[discord.Member],
                           character_name: typing.Optional[str],
                           page_number: int = 1):
        """Display character information.
        Display A specific view when a specific character is provided,
        refine the list of characters when a specific player is provided."""
        guild_id = interaction.guild_id
        await interaction.response.defer(thinking=True, ephemeral=False)

        try:
            async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as conn:
                cursor = await conn.cursor()
                determinate_player_name = player_name.name if player_name else interaction.user.name
                # Decide which query to execute based on whether 'name' is provided
                if not player_name:
                    await cursor.execute("SELECT COUNT(Character_Name) FROM Player_Characters")
                else:
                    await cursor.execute(
                        "SELECT COUNT(Character_Name) FROM Player_Characters WHERE Player_Name = ?",
                        (player_name.name,))
                character_count = await cursor.fetchone()
                (character_count,) = character_count
                if character_name:
                    view_type = 2
                    await cursor.execute(
                        "SELECT character_name, player_name from Player_Characters where Character_Name = ?",
                        (character_name,))
                    character = await cursor.fetchone()

                    if not character:
                        await interaction.followup.send(
                            f"Character '{character_name}' not found.",
                            ephemeral=True
                        )
                        return
                    else:
                        await cursor.execute(
                            "SELECT character_name from Player_Characters WHERE Player_Name = ? ORDER BY True_Character_Name asc",
                            (character[1],))
                        determinate_player_name = character[1]
                        results = await cursor.fetchall()
                        characters = [result[0] for result in results]
                        if len(characters) == 1:
                            offset = 0
                        else:
                            offset = characters.index(character[0]) + 1
                            print(offset)
                else:
                    view_type = 1

                # Set up pagination variables
                page_number = min(max(page_number, 1), math.ceil(character_count / 20))
                items_per_page = 5 if view_type == 1 else 1
                offset = (page_number - 1) * items_per_page if view_type == 1 else offset

                # Create and send the view with the results
                view = views.CharacterDisplayView(
                    user_id=interaction.user.id,
                    guild_id=guild_id,
                    player_name=determinate_player_name,
                    character_name=character_name,
                    limit=items_per_page,
                    offset=offset,
                    view_type=view_type,
                    interaction=interaction
                )
                await view.send_initial_message()

        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(
                f"An error occurred whilst fetching data! input values of player_name: {player_name}, character_name: {character_name}': {e}"
            )
            await interaction.followup.send(
                f"An error occurred whilst fetching data. Please try again later.",
                ephemeral=True
            )

    @display_group.command(name='level_range', description='Display all characters in a level range')
    @app_commands.describe(
        level_range="the level range of the characters you are looking for. Keep in mind, this applies only to the preset low/med/high/max ranges your admin has set")
    async def display_level_range(self, interaction: discord.Interaction, level_range: discord.Role,
                                  current_page: int = 1):
        guild_id = interaction.guild_id
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            await interaction.followup.send("Fetching character data...")
            async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as conn:
                cursor = await conn.cursor()
                await cursor.execute("Select min(level), max(level) FROM Milestone_System where Level_Range_ID = ?",
                                     (level_range.id,))
                level_range_info = await cursor.fetchone()
                if not level_range_info[0]:
                    await interaction.followup.send(
                        f"Level range {level_range.name} not found.",
                        ephemeral=True
                    )
                    return
                else:
                    (level_range_min, level_range_max) = level_range_info
                    await cursor.execute(
                        "SELECT COUNT(Character_Name) FROM Player_Characters WHERE level between ? and ?",
                        (level_range_min, level_range_max))
                character_count = await cursor.fetchone()
                (character_count,) = character_count
                view_type = 1
                if character_count == 0:
                    await interaction.followup.send(
                        f"No characters found in the level range {level_range.name}.",
                        ephemeral=True
                    )
                    return
                # Set up pagination variables
                page_number = min(max(current_page, 1), math.ceil(character_count / 20))
                items_per_page = 5 if view_type == 1 else 1
                offset = (page_number - 1) * items_per_page

                # Create and send the view with the results
                view = views.LevelRangeDisplayView(
                    user_id=interaction.user.id,
                    guild_id=guild_id,
                    level_range_min=level_range_min,
                    level_range_max=level_range_max,
                    limit=items_per_page,
                    offset=offset,
                    view_type=view_type,
                    interaction=interaction
                )
                await view.send_initial_message()

        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(
                f"An error occurred in the 'display level_range' command while fetching data for '{level_range.name}': {e}"
            )
            await interaction.followup.send(
                f"An error occurred while fetching level_range information. Please try again later.",
                ephemeral=True
            )

    @character_group.command(name='backstory', description='give or edit the backstory of your character')
    @app_commands.autocomplete(character_name=own_character_select_autocompletion)
    @app_commands.describe(
        backstory="The backstory you wish to give to your character, you may use a google drive share link")
    async def backstory(self, interaction: discord.Interaction, character_name: str, backstory: str):
        """Give or edit the backstory of a character."""
        guild_id = interaction.guild_id
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as conn:
                cursor = await conn.cursor()
                await cursor.execute(
                    "SELECT Character_Name, Article_ID, Mythweavers, Thread_ID FROM Player_Characters WHERE Player_Name = ? AND (Character_Name = ? OR Nickname = ?)",
                    (interaction.user.name, character_name, character_name)
                )
                character_info = await cursor.fetchone()
                if not character_info:
                    await interaction.followup.send(
                        f"Character '{character_name}' not found.",
                        ephemeral=True
                    )
                    return
                else:
                    (character_name, article_id, mythweavers, logging_thread_id) = character_info
                    if not article_id:
                        async with config_cache.lock:
                            configs = config_cache.cache.get(guild_id)
                            if configs:
                                category = configs.get('WA_Backstory_Category')

                        if not category:
                            await interaction.followup.send(
                                "Backstory category not found in the database.",
                                ephemeral=True
                            )
                            return
                        else:
                            article = await put_wa_article(
                                guild_id=guild_id,
                                template='person',
                                category=category,
                                author=interaction.user.name,
                                overview=backstory,
                                title=character_name)
                            await cursor.execute(
                                "Update Player_Characters SET Article_ID = ?, Article_Link = ? WHERE Character_Name = ?",
                                (article['id'], article['url'], character_name))
                            await conn.commit()
                            await character_embed(
                                character_name=character_name,
                                guild=interaction.guild)
                            character_changes = CharacterChange(
                                character_name=character_name,
                                author=interaction.user.name,
                                source=f'Backstory creation',
                                backstory=article['url'])
                            character_log = await log_embed(character_changes, interaction.guild,
                                                                             logging_thread_id, self.bot)
                            await interaction.followup.send(embed=character_log, ephemeral=True)
                    else:
                        updated_article = await patch_wa_article(guild_id=guild_id,
                                                                                  article_id=article_id,
                                                                                  overview=backstory)
                        await interaction.followup.send(
                            f"Backstory updated successfully for [{character_name}](<{updated_article['url']}>)!",
                            ephemeral=True)
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(
                f"an error occurred in the backstory command for '{character_name}': {e}"
            )
            await interaction.followup.send(
                f"An an error occurred in the backstory command. Please try again alter..",
                ephemeral=True
            )

    gold_group = discord.app_commands.Group(
        name='gold',
        description='Commands for managing gold on a character',
        parent=character_group
    )

    @gold_group.command(name='buy', description='Buy items from NPCs for non-player trades and crafts')
    @app_commands.describe(
        market_value="market value of the item regardless of crafting. Items crafted for other players have an expected value of 0.")
    @app_commands.autocomplete(character_name=own_character_select_autocompletion)
    async def buy(self, interaction: discord.Interaction, character_name: str, expenditure: float, market_value: float,
                  reason: str):
        """Buy items from NPCs for non-player trades and crafts. Expected Value is the MARKET price of what you are buying, not the price you are paying."""
        try:
            await interaction.response.defer(thinking=True, ephemeral=True)
            _, character_name = name_fix(character_name)
            reason = str.replace(reason, ";", "")
            guild_id = interaction.guild_id
            guild = interaction.guild
            author = interaction.user.name
            async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as conn:
                cursor = await conn.cursor()
                if expenditure <= 0:
                    await interaction.followup.send(
                        f"Little comrade! Please buy something of actual value! {expenditure} is too small to purchase anything with!")
                elif market_value < 0:
                    await interaction.followup.send(
                        f"Little comrade! You cannot have an expected value of: {market_value}, it is too little gold to work with!")
                elif expenditure > 0:
                    await cursor.execute(
                        "SELECT Character_Name, Level, Oath, Gold, Gold_Value, Gold_Value_Max, Thread_ID  FROM Player_Characters where Player_Name = ? AND (Character_Name = ? or Nickname = ?)",
                        (author, character_name, character_name))
                    player_info = await cursor.fetchone()
                    if not player_info:
                        await interaction.followup.send(
                            f"{interaction.user.name} does not have a character named {character_name}")
                    else:
                        (character_name, level, oath, gold, gold_value, gold_value_max, logging_thread_id) = player_info
                        if Decimal(gold) < Decimal(expenditure):
                            await interaction.followup.send(
                                f"{character_name} does not have enough gold to buy this item.")
                        else:
                            change_gold_value = Decimal(abs(Decimal(market_value)) - abs(Decimal(expenditure)))

                            gold_result = await gold_calculation(
                                guild_id=guild_id,
                                character_name=character_name,
                                level=level,
                                oath=oath,
                                gold=Decimal(gold),
                                gold_change=-abs(Decimal(expenditure)),
                                gold_value=Decimal(gold_value),
                                gold_value_max=Decimal(gold_value_max),
                                gold_value_change=Decimal(change_gold_value),
                                gold_value_max_change=Decimal(change_gold_value),
                                reason=reason,
                                source='Character Gold Buy Command',
                                author_name=interaction.user.name,
                                author_id=interaction.user.id
                            )
                            if isinstance(gold_result, tuple):
                                (difference, gold_total, gold_value_total, gold_max_value_total,
                                 transaction_id) = gold_result
                                character_changes = UpdateCharacterData(
                                    character_name=character_name,
                                    gold_package=(gold_total, gold_value_total, gold_max_value_total)
                                )
                                await update_character(change=character_changes, guild_id=guild_id)
                                character_changes = CharacterChange(
                                    character_name=character_name,
                                    author=author,
                                    source=f'Gold Buy of {expenditure} with an expected value of {market_value}',
                                    gold_change=difference,
                                    gold=gold_total,
                                    gold_value=gold_value_total,
                                    transaction_id=transaction_id
                                )
                                await character_embed(character_name=character_name, guild=guild)
                                character_log = await log_embed(character_changes, guild,
                                                                                 logging_thread_id, self.bot)
                                async with config_cache.lock:
                                    configs = config_cache.cache.get(interaction.guild_id)
                                    if configs:
                                        channel_id = configs.get('Character_Transaction_Channel')

                                if channel_id is None:
                                    await interaction.followup.send(
                                        "Character Transaction Channel not found in the database.",
                                        ephemeral=True
                                    )
                                    return
                                channel = interaction.guild.get_channel(int(channel_id))
                                if not channel:
                                    channel = await interaction.guild.fetch_channel(int(channel_id))
                                if channel:
                                    gold_spent_string = get_gold_breakdown(expenditure)
                                    market_value_string = get_gold_breakdown(market_value)
                                    embed = discord.Embed(
                                        title=f"{character_name} has spent gold to buy {reason}!",
                                        description=f"**Gold Spent:** {gold_spent_string}\n**Expected Value:** {market_value_string}")
                                    await channel.send(embed=embed)

                                await interaction.followup.send(embed=character_log)
        except (aiosqlite.Error, TypeError, ValueError, CalculationAidFunctionError) as e:
            await interaction.followup.send(f"An error occurred in the buy command: {e}")
            logging.exception(f"An error occurred in the buy command: {e}")

    @gold_group.command(name='send',
                        description='Send gold to a crafter or other players for the purposes of their transactions')
    @app_commands.autocomplete(character_from=own_character_select_autocompletion)
    @app_commands.autocomplete(character_to=autocomplete.character_select_autocompletion)
    async def send(self, interaction: discord.Interaction, character_from: str, character_to: str, amount: float,
                   expected_value: float, reason: str):
        """Send gold to a crafter or other players for the purposes of their transactions. Expected Value is the MARKET price of what they will give you in return. This will ping the player involved"""
        try:
            await interaction.response.defer(thinking=True, ephemeral=True)
            guild_id = interaction.guild_id
            author = interaction.user.name
            author_id = interaction.user.id
            async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as conn:
                cursor = await conn.cursor()
                if amount <= 0:
                    await interaction.followup.send(
                        f"Little comrade! Please send something of actual value! {amount} is too small to send!")
                elif expected_value < 0:
                    await interaction.followup.send(
                        f"Little comrade! You cannot have an expected value of: {expected_value}, it is too little gold to work with!")
                elif Decimal(expected_value) < Decimal(amount):
                    await interaction.followup.send(
                        f"Little comrade! You cannot have an expected value of: {expected_value}, it is too little gold to work with!")
                else:
                    await cursor.execute(
                        "SELECT Character_Name, Level, Oath, Gold, Gold_Value, Gold_Value_Max, Thread_ID  FROM Player_Characters where Player_Name = ? AND (Character_Name = ? or Nickname = ?)",
                        (author, character_from, character_from))
                    source_player_info = await cursor.fetchone()
                    if not source_player_info:
                        await interaction.followup.send(
                            f"{interaction.user.name} does not have a character named {character_from}")
                    else:
                        (source_character_name, source_level, source_oath, source_gold, source_gold_value,
                         source_gold_value_max, source_logging_thread_id) = source_player_info
                        if Decimal(source_gold) < Decimal(amount):
                            await interaction.followup.send(
                                f"{interaction.user.name} does not have enough gold to send this amount.")
                        else:
                            await cursor.execute(
                                "SELECT Player_ID, Character_Name, Level, Oath, Gold, Gold_Value, Gold_Value_Max, Thread_ID  FROM Player_Characters where Character_Name = ?",
                                (character_to,))
                            recipient_info = await cursor.fetchone()
                            if not recipient_info:
                                await interaction.followup.send(
                                    f"Couldn't find character named {character_to}")
                            elif recipient_info[0] == author_id:
                                await interaction.followup.send(
                                    f"You cannot send gold to yourself!")
                            else:
                                (target_player_id, character_to, target_level, target_oath, target_gold,
                                 target_gold_value, target_gold_value_max, target_logging_thread_id) = recipient_info

                                gold_results = await gold_calculation(
                                    guild_id=guild_id,
                                    character_name=character_from,
                                    level=source_level,
                                    oath=source_oath,
                                    gold=Decimal(source_gold),
                                    gold_change=-abs(Decimal(amount)),
                                    gold_value=Decimal(source_gold_value),
                                    gold_value_max=Decimal(source_gold_value_max),
                                    gold_value_change=abs(Decimal(expected_value)),
                                    gold_value_max_change=None,
                                    reason=reason,
                                    source='Character Gold Send Command',
                                    is_transaction=False,
                                    author_id=author_id,
                                    author_name=author
                                )
                                if isinstance(gold_results, tuple):
                                    (calculated_difference, calculated_gold_total, calculated_gold_value_total,
                                     calculated_gold_max_value_total, calculated_transaction_id) = gold_results
                                    view = views.GoldSendView(
                                        allowed_user_id=target_player_id,
                                        requester_name=author,
                                        requester_id=author_id,
                                        character_name=character_from,
                                        recipient_name=character_to,
                                        gold_change=abs(calculated_difference),
                                        # This is the amount of gold that will be sent. Since an earlier step performs quantize to it there is no need to quantize it a second time/..
                                        source_level=source_level,
                                        source_oath=source_oath,
                                        source_gold=source_gold,
                                        source_gold_value=source_gold_value,
                                        source_gold_value_max=source_gold_value_max,
                                        target_level=target_level,
                                        target_oath=target_oath,
                                        recipient_gold=target_gold,
                                        recipient_gold_value=target_gold_value,
                                        recipient_gold_value_max=target_gold_value_max,
                                        market_value=abs(Decimal(expected_value).quantize(Decimal('0.01'))),
                                        bot=self.bot,
                                        guild_id=guild_id,
                                        source_logging_thread=source_logging_thread_id,
                                        recipient_logging_thread=target_logging_thread_id,
                                        reason=reason,
                                        interaction=interaction)
                                    await view.send_initial_message()
                                else:
                                    embed = discord.Embed(title="Gold Send Failed!", description=gold_results)
                                    await interaction.followup.send(embed=embed)

        except (aiosqlite.Error, TypeError, ValueError, CalculationAidFunctionError) as e:
            await interaction.followup.send(f"An error occurred in the gold send command: {e}")
            logging.exception(f"An error occurred in the send command: {e}")

    @gold_group.command(name='history', description='display history transactions')
    @app_commands.autocomplete(character_name=autocomplete.character_select_autocompletion)
    async def display_gold(self, interaction: discord.Interaction, character_name: str, page_number: int = 1):
        """Display the gold transaction history of a character."""
        guild_id = interaction.guild_id
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as conn:
                cursor = await conn.cursor()
                await cursor.execute(
                    "SELECT COUNT(*) FROM A_Audit_Gold WHERE Character_Name = ?",
                    (character_name,)
                )
                count_row = await cursor.fetchone()
                transaction_count = count_row[0] if count_row else 0

                if transaction_count == 0:
                    await interaction.followup.send(
                        f"No gold transactions found for '{character_name}'.",
                        ephemeral=True
                    )
                    return

                # Set up pagination variables
                page_number = min(max(page_number, 1), math.ceil(transaction_count / 20))
                items_per_page = 20
                offset = (page_number - 1) * items_per_page

                # Create and send the view with the results
                view = views.GoldHistoryView(
                    user_id=interaction.user.id,
                    guild_id=guild_id,
                    character_name=character_name,
                    limit=items_per_page,
                    offset=offset,
                    interaction=interaction
                )
                await view.send_initial_message()

        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(
                f"An error occurred in the 'display' command while fetching data for '{character_name}': {e}"
            )
            await interaction.followup.send(
                f"An error occurred while fetching your gold transaction history. Please try again later.",
                ephemeral=True
            )

    @gold_group.command(name='consume', description='Consume equipment gold for a specific purpose')
    @app_commands.autocomplete(character_name=own_character_select_autocompletion)
    async def consume(self, interaction: discord.Interaction, character_name: str, amount: float, reason: str):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            guild_id = interaction.guild_id
            async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as conn:
                cursor = await conn.cursor()
                await cursor.execute(
                    "SELECT Character_Name, Level, Oath, Gold, Gold_Value, Gold_Value_Max, Thread_ID  FROM Player_Characters where Player_Name = ? AND (Character_Name = ? or Nickname = ?)",
                    (interaction.user.name, character_name, character_name)
                )
                player_info = await cursor.fetchone()
                if not player_info:
                    await interaction.followup.send(
                        f"Character '{character_name}' not found.",
                        ephemeral=True
                    )
                    return
                else:
                    (character_name, level, oath, gold, gold_value, gold_value_max, logging_thread_id) = player_info
                    if amount <= 0:
                        await interaction.followup.send(
                            f"Little comrade! Please consume something of actual value! {amount} is too small to consume!")
                        return
                    if gold_value - gold < amount:
                        await interaction.followup.send(
                            f"{interaction.user.name} does not have enough illiquid wealth to consume this amount.",
                            ephemeral=True
                        )
                        return
                    gold_result = await gold_calculation(
                        guild_id=guild_id,
                        character_name=character_name,
                        level=level,
                        oath=oath,
                        gold=gold,
                        gold_change=Decimal(0),
                        gold_value=Decimal(gold_value),
                        gold_value_max=Decimal(gold_value_max),
                        gold_value_change=-abs(Decimal(amount)),
                        gold_value_max_change=Decimal(0),
                        reason=reason,
                        source='Character Gold Consume Command',
                        author_id=interaction.user.id,
                        author_name=interaction.user.name
                    )
                    if isinstance(gold_result, tuple):
                        (difference, gold_total, gold_value_total, gold_max_value_total, transaction_id) = gold_result
                        character_updates = UpdateCharacterData(
                            character_name=character_name,
                            gold_package=(gold_total, gold_value_total, gold_max_value_total)
                        )
                        await update_character(change=character_updates, guild_id=guild_id)
                        character_changes = CharacterChange(
                            character_name=character_name,
                            author=interaction.user.name,
                            source=f'Gold Consume of {amount} for {reason}',
                            gold_change=difference,
                            gold=gold_total,
                            gold_value=gold_value_total,
                            transaction_id=transaction_id
                        )
                        character_log = await log_embed(character_changes, interaction.guild,
                                                                         logging_thread_id, self.bot)
                        await character_embed(character_name=character_name, guild=interaction.guild)
                        if isinstance(character_log, discord.Embed):
                            await interaction.followup.send(embed=character_log)

                        else:
                            await interaction.followup.send(
                                f"An error occurred while processing the gold consumption: {character_log}",
                                ephemeral=True
                            )

                    else:
                        await interaction.followup.send(
                            f"An error occurred while processing the gold consumption: {gold_result}",
                            ephemeral=True
                        )
        except (aiosqlite.Error, TypeError, ValueError) as e:
            await interaction.followup.send(f"An error occurred in the consume command: {e}")
            logging.exception(f"An error occurred in the consume command: {e}")

    @gold_group.command(name='claim', description='claim a set amount of gold.')
    @app_commands.autocomplete(character_name=own_character_select_autocompletion)
    async def claim(self, interaction: discord.Interaction, character_name: str, amount: float, reason: str):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            guild_id = interaction.guild_id
            async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as conn:
                cursor = await conn.cursor()
                await cursor.execute(
                    "SELECT Character_Name, level, oath, Gold, Gold_Value, Gold_Value_Max, Thread_ID  FROM Player_Characters where Player_Name = ? AND (Character_Name = ? or Nickname = ?)",
                    (interaction.user.name, character_name, character_name)
                )
                player_info = await cursor.fetchone()
                if not player_info:
                    await interaction.followup.send(
                        f"Character '{character_name}' not found.",
                        ephemeral=True
                    )
                    return
                else:
                    if amount <= 0:
                        await interaction.followup.send(
                            f"Little comrade! Please claim something of actual value! {amount} is too small to claim!")
                        return
                    (character_name, level, oath, gold, gold_value, gold_value_max, logging_thread_id) = player_info
                    gold_result = await gold_calculation(
                        author_id=interaction.user.id,
                        author_name=interaction.user.name,
                        guild_id=guild_id,
                        level=level,
                        oath=oath,
                        character_name=character_name,
                        gold=gold,
                        gold_change=Decimal(amount),
                        gold_value=gold_value,
                        gold_value_max=gold_value_max,
                        gold_value_change=None,
                        gold_value_max_change=None,
                        reason=reason,
                        source='Character Gold Claim Command'
                    )
                    if isinstance(gold_result, tuple):
                        (difference, gold_total, gold_value_total, gold_max_value_total, transaction_id) = gold_result
                        character_updates = UpdateCharacterData(
                            character_name=character_name,
                            gold_package=(gold_total, gold_value_total, gold_max_value_total)
                        )
                        await update_character(change=character_updates, guild_id=guild_id)
                        character_changes = CharacterChange(
                            character_name=character_name,
                            author=interaction.user.name,
                            source=f'Gold Claim of {amount} for {reason}',
                            gold_change=difference,
                            gold=gold_total,
                            gold_value=gold_value_total,
                            transaction_id=transaction_id
                        )
                        character_log = await log_embed(character_changes, interaction.guild,
                                                                         logging_thread_id, self.bot)
                        await character_embed(character_name=character_name, guild=interaction.guild)
                        await interaction.followup.send(embed=character_log)

                    else:
                        await interaction.followup.send(gold_result, ephemeral=True)
        except (aiosqlite.Error, TypeError, ValueError) as e:
            await interaction.followup.send(f"An error occurred in the claim command: {e}")
            logging.exception(f"An error occurred in the claim command: {e}")

    mythweavers_group = discord.app_commands.Group(
        name='mythweavers',
        description='Commands for managing gold on a character',
        parent=character_group
    )

    @mythweavers_group.command(name='upload',
                               description='Upload the Abilities and skills from your mythweavers sheet.')
    @app_commands.autocomplete(character_name=own_character_select_autocompletion)
    @app_commands.choices(sheet=[discord.app_commands.Choice(name='Sane_Person_Very_Regular', value=1),
                                 discord.app_commands.Choice(name='Experimental', value=2)])
    async def upload(self, interaction: discord.Interaction, character_name: str, mythweavers: discord.Attachment,
                     sheet: discord.app_commands.Choice[int] = 1):
        try:
            sheet_value = 1 if isinstance(sheet, int) else sheet.value
            await interaction.response.defer(thinking=True, ephemeral=True)
            guild_id = interaction.guild_id
            async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as conn:
                cursor = await conn.cursor()
                await cursor.execute(
                    "SELECT Character_Name FROM Player_Characters where Player_Name = ? AND (Character_Name = ? or Nickname = ?)",
                    (interaction.user.name, character_name, character_name)
                )
                player_info = await cursor.fetchone()
                if not player_info:
                    await interaction.followup.send(
                        f"Character '{character_name}' not found.",
                        ephemeral=True
                    )
                    return
                else:
                    (character_name_db,) = player_info
                    await cursor.execute("DELETE from Player_Characters_Attributes where Character_Name = ?",
                                         (character_name_db,))
                    await conn.commit()
                    await cursor.execute("DELETE from Player_Characters_Skills where Character_Name = ?",
                                         (character_name_db,))
                    await conn.commit()
                    file_content = await mythweavers.read()
                    # Check if the file is a json file
                    try:
                        skills_data = json.loads(file_content)
                    except json.JSONDecodeError as e:
                        await interaction.followup.send(
                            f"An error occurred while reading the uploaded file: {e}",
                            ephemeral=True
                        )
                        return
                    if sheet_value == 1:
                        attributes = normal_sheet_attributes(skills_data)
                    # Extract and safely convert Attributes
                    else:
                        attributes = experimental_sheet_attributes(skills_data)

                    await cursor.execute(
                        '''
                        INSERT OR REPLACE INTO Player_Characters_Attributes (
                            character_name, strength, strength_mod, dexterity, dexterity_mod,
                            constitution, constitution_mod, intelligence, intelligence_mod,
                            wisdom, wisdom_mod, charisma, charisma_mod, fortitude,
                            reflex, will, initiative, hit_points, armor_class,
                            touch_armor_class, cmd, Melee, Ranged, CMB
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''',
                        (
                            character_name, attributes['strength'], attributes['strength_mod'],
                            attributes['dexterity'], attributes['dexterity_mod'],
                            attributes['constitution'], attributes['constitution_mod'],
                            attributes['intelligence'], attributes['intelligence_mod'],
                            attributes['wisdom'], attributes['wisdom_mod'],
                            attributes['charisma'], attributes['charisma_mod'],
                            attributes['fortitude'], attributes['reflex'], attributes['will'],
                            attributes['initiative'], attributes['hit_points'],
                            attributes['armor_class'], attributes['touch_armor_class'],
                            attributes['cmd'], attributes['melee'], attributes['ranged'], attributes['cmb']
                        )
                    )

                    # Process skills
                    if sheet_value == 1:
                        await normal_sheet_skills(db=conn, skills_data=skills_data, character_name=character_name)
                    else:
                        await experimental_sheet_skills(db=conn, skills_data=skills_data, character_name=character_name)
                    await conn.commit()
                    await interaction.followup.send(
                        f"Mythweavers sheet uploaded successfully for {character_name}.",
                        ephemeral=True)

        except (aiosqlite.Error, TypeError, ValueError) as e:
            await interaction.followup.send(f"An error occurred in the upload command: {e}")
            logging.exception(f"An error occurred in the upload command: {e}")

    @mythweavers_group.command(name="combat", description="display the combat stats from your mythweavers sheet.")
    @app_commands.autocomplete(character_name=own_character_select_autocompletion)
    async def combat(self, interaction: discord.Interaction, character_name: str):
        try:
            await interaction.response.defer(thinking=True, ephemeral=False)
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as conn:
                cursor = await conn.cursor()
                await cursor.execute(
                    "SELECT Fortitude, Reflex, Will, Initiative, Hit_Points, Armor_Class, Touch_Armor_Class, CMD, Melee, Ranged, CMB FROM Player_Characters_Attributes WHERE Character_Name = ?",
                    (character_name,)
                )
                attributes = await cursor.fetchone()
                if not attributes:
                    await interaction.followup.send(
                        f"Character '{character_name}' not found.",
                        ephemeral=True
                    )
                    return
                else:
                    (
                        fortitude, reflex, will, initiative, hit_points, armor_class, touch_armor_class, cmd, melee,
                        ranged,
                        cmb) = attributes
                    embed = discord.Embed(
                        title=f"Defences for {character_name}",
                        description=f"**Hit Points**: {hit_points}\n"
                                    f"**Armor Class**: {armor_class} **Touch Armor Class**: {touch_armor_class} **CMD**: {cmd}\n"
                                    f"**Fortitude**: {fortitude} **Reflex**: {reflex} **Will**: {will}\n"
                                    f"**Initiative**: {initiative}\n"
                                    f"**Melee**: {melee} **Ranged**: {ranged} **CMB**: {cmb}"
                    )
                    await interaction.followup.send(embed=embed)
                    combat_dict = {
                        'Fortitude': fortitude,
                        'Reflex': reflex,
                        'Will': will,
                        'Initiative': initiative,
                        'cmb': cmb,
                        'Melee': melee,
                        'Ranged': ranged
                    }
                    view = views.AttributesView(
                        user_id=interaction.user.id,
                        guild_id=interaction.guild_id,
                        modifiers=combat_dict
                    )
                    await interaction.followup.send(embed=embed, view=view)
        except (aiosqlite.Error, TypeError, ValueError) as e:
            await interaction.followup.send(f"An error occurred in the defences command: {e}")
            logging.exception(f"An error occurred in the defences command: {e}")

    @mythweavers_group.command(name="skills", description="display the skills from your mythweavers sheet.")
    @app_commands.autocomplete(character_name=own_character_select_autocompletion)
    @app_commands.choices(ability=[discord.app_commands.Choice(name='Strength', value='str'),
                                   discord.app_commands.Choice(name='Dexterity', value='dex'),
                                   discord.app_commands.Choice(name='Constitution', value='con'),
                                   discord.app_commands.Choice(name='Intelligence', value='int'),
                                   discord.app_commands.Choice(name='Wisdom', value='wis'),
                                   discord.app_commands.Choice(name='Charisma', value='cha')])
    async def skills(self, interaction: discord.Interaction, character_name: str,
                     ability: discord.app_commands.Choice[str]):
        try:
            ability_name = ability if isinstance(ability, str) else ability.value
            await interaction.response.defer(thinking=True, ephemeral=False)
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as conn:
                cursor = await conn.cursor()

                await cursor.execute(
                    "SELECT Character_Name, Skill_Name, Ability, Skill_Rank, Skill_Modifier FROM Player_Characters_Skills WHERE Character_Name = ? AND Ability = ?",
                    (character_name, ability_name.title())
                )
                skills = await cursor.fetchall()
                if not skills:
                    await interaction.followup.send(
                        f"Character '{character_name}' not found.",
                        ephemeral=True
                    )
                    return
                else:
                    embed = discord.Embed(
                        title=f"Skills for {character_name}",
                        description=f"**{ability_name} skills**\n"
                    )
                    skill_dictionary = {}
                    for skill in skills:
                        (character_name, skill_name, ability, skill_rank, skill_modifier) = skill
                        skill_dictionary[skill_name] = skill_modifier
                        embed.add_field(
                            name=f"{skill_name}",
                            value=f"**Rank**: {skill_rank} **Modifier**: {skill_modifier}",
                            inline=False
                        )
                    view = views.AttributesView(
                        user_id=interaction.user.id,
                        guild_id=interaction.guild_id,
                        modifiers=skill_dictionary
                    )
                    await interaction.followup.send(embed=embed, view=view)

        except (aiosqlite.Error, TypeError, ValueError) as e:
            await interaction.followup.send(f"An error occurred in the skills command: {e}")
            logging.exception(f"An error occurred in the skills command: {e}")

    @mythweavers_group.command(name="attributes", description="display the attributes from your mythweavers sheet.")
    @app_commands.autocomplete(character_name=own_character_select_autocompletion)
    async def attributes(self, interaction: discord.Interaction, character_name: str):
        try:
            await interaction.response.defer(thinking=True, ephemeral=True)
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as conn:
                cursor = await conn.cursor()
                await cursor.execute(
                    "SELECT Character_Name, Strength, Strength_Mod, Dexterity, Dexterity_Mod, Constitution, Constitution_Mod, Intelligence, Intelligence_Mod, Wisdom, Wisdom_Mod, Charisma, Charisma_Mod FROM Player_Characters_Attributes WHERE Character_Name = ?",
                    (character_name,)
                )
                attributes = await cursor.fetchone()
                if not attributes:
                    await interaction.followup.send(
                        f"Character '{character_name}' not found.",
                        ephemeral=False
                    )
                    return
                else:
                    (character_name, strength, strength_mod, dexterity, dexterity_mod, constitution, constitution_mod,
                     intelligence, intelligence_mod, wisdom, wisdom_mod, charisma, charisma_mod) = attributes
                    attributes_dict = {
                        'Strength': strength_mod,
                        'Dexterity': dexterity_mod,
                        'Constitution': constitution_mod,
                        'Intelligence': intelligence_mod,
                        'Wisdom': wisdom_mod,
                        'Charisma': charisma_mod
                    }
                    embed = discord.Embed(
                        title=f"Attributes for {character_name}",
                        description=f"**Strength**: Score: {strength} Modifier: {strength_mod}\n"
                                    f"**Dexterity**: Score: {dexterity} Modifier: {dexterity_mod}\n"
                                    f"**Constitution**: Score: {constitution} Modifier: {constitution_mod}\n"
                                    f"**Intelligence**: Score: {intelligence} Modifier: {intelligence_mod} \n"
                                    f"**Wisdom**: Score: {wisdom} Modifier: {wisdom_mod}\n"
                                    f"**Charisma**: Score: {charisma} Modifier: {charisma_mod} \n"
                    )
                    view = views.AttributesView(
                        user_id=interaction.user.id,
                        guild_id=interaction.guild_id,
                        modifiers=attributes_dict
                    )
                    await interaction.followup.send(embed=embed, view=view)
        except (aiosqlite.Error, TypeError, ValueError) as e:
            await interaction.followup.send(f"An error occurred in the attributes command: {e}")
            logging.exception(f"An error occurred in the attributes command: {e}")





logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s [%(filename)s:%(lineno)d] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    filename='pathparser.log',  # Specify the log file name
    filemode='a'  # Append mode
)
