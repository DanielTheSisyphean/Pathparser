import asyncio
import typing
import aiosqlite
import os
import discord
import logging
from time import time
from typing import List
from discord import app_commands
from .config import config_cache
from unidecode import unidecode
from core.cache import autocomplete_cache, AutocompleteWorldAnvilCache
from pywaclient.api import BoromirApiClient as WaClient

CACHE_EXPIRATION = 600



async def alignment_autocomplete(interaction: discord.Interaction, current: str
                                 ) -> typing.List[app_commands.Choice[str]]:
    data = []
    guild_id = interaction.guild_id
    async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
        cursor = await db.cursor()
        current = unidecode(str.title(current))
        await cursor.execute(
            "SELECT Alignment, Economy, Loyalty, Stability FROM AA_Alignment WHERE Alignment LIKE ? Limit 20",
            (f"%{current}%",))
        alignment_list = await cursor.fetchall()
        for alignment in alignment_list:
            if current in alignment[0]:
                (alignment_name, economy, loyalty, stability) = alignment
                data.append(app_commands.Choice(
                    name=f"{alignment_name} Economy: {economy}, Loyalty: {loyalty}, Stability: {stability}",
                    value=alignment_name))
    return data


async def blueprint_autocomplete(interaction: discord.Interaction, current: str
                                 ) -> typing.List[app_commands.Choice[str]]:
    data = []
    guild_id = interaction.guild_id
    async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
        cursor = await db.cursor()
        current = unidecode(str.title(current))
        await cursor.execute(
            "SELECT Full_Name FROM kb_Buildings_Blueprints WHERE Full_Name LIKE ? Limit 20",
            (f"%{current}%",))
        blueprint_list = await cursor.fetchall()
        for blueprint in blueprint_list:
            if current in blueprint[0]:
                data.append(app_commands.Choice(name=blueprint[0], value=blueprint[0]))
    return data


async def improvement_subtype_autocomplete(interaction: discord.Interaction, current: str
                                           ) -> typing.List[app_commands.Choice[str]]:
    data = []
    guild_id = interaction.guild_id
    async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
        cursor = await db.cursor()
        current = unidecode(str.title(current))
        await cursor.execute(
            "SELECT Full_Name, Subtype FROM KB_Hexes_Improvements WHERE Full_Name LIKE ? AND Type = 'Farm' Limit 20",
            (f"%{current}%",))
        blueprint_list = await cursor.fetchall()
        for blueprint in blueprint_list:
            if current in blueprint[0]:
                data.append(app_commands.Choice(name=f"{blueprint[0]} produces {blueprint[1]}", value=blueprint[0]))
    return data


async def blueprint_repurpose_autocomplete(interaction: discord.Interaction, current: str
                                           ) -> typing.List[app_commands.Choice[str]]:
    data = []
    guild_id = interaction.guild_id
    async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
        cursor = await db.cursor()
        current = unidecode(str.title(current))
        await cursor.execute(
            "SELECT Full_name FROM kb_Buildings_Blueprints WHERE Full_Name LIKE ? AND (Subtype in ('Magical Items', 'Magical Consumables', 'Textile', 'Mundane Exotic', 'Mundane Complex', 'Metallurgy', 'Stoneworking') OR Type = 'Granary') Limit 20",
            (f"%{current}%",))
        blueprint_list = await cursor.fetchall()
        for blueprint in blueprint_list:
            if current in blueprint[0]:
                data.append(app_commands.Choice(name=blueprint[0], value=blueprint[0]))
    return data


async def blueprint_upgrade_autocomplete(interaction: discord.Interaction, current: str
                                         ) -> typing.List[app_commands.Choice[str]]:
    data = []
    guild_id = interaction.guild_id
    async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
        cursor = await db.cursor()
        current = unidecode(str.title(current))
        await cursor.execute(
            "SELECT Full_Name, Upgrade From Kb_Buildings_Blueprints WHERE Upgrade is not Null and Full_Name like ? Limit 20",
            (f"%{current}%",))
        blueprint_list = await cursor.fetchall()

        for blueprint in blueprint_list:
            if current in blueprint[0]:
                data.append(app_commands.Choice(name=f"{blueprint[0]} - {blueprint[1]}", value=blueprint[0]))
    return data


async def government_autocompletion(
        interaction: discord.Interaction, current: str) -> typing.List[app_commands.Choice[str]]:
    data = []
    guild_id = interaction.guild_id
    async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
        cursor = await db.cursor()
        current = unidecode(str.title(current))
        await cursor.execute(
            "SELECT Government from AA_Government WHERE Government LIKE ? Limit 20",
            (f"%{current}%",))
        government_list = await cursor.fetchall()
        for government in government_list:
            if current in government[0]:
                data.append(app_commands.Choice(name=government[0], value=government[0]))

    return data


async def hex_terrain_autocomplete(
        interaction: discord.Interaction, current: str) -> typing.List[app_commands.Choice[str]]:
    data = []
    guild_id = interaction.guild_id
    async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
        cursor = await db.cursor()
        current = unidecode(str.title(current))
        await cursor.execute(
            "SELECT Hex_Terrain from AA_Hex_Terrains WHERE Hex_Terrain LIKE ? Limit 20",
            (f"%{current}%",))
        hex_list = await cursor.fetchall()
        for kb_hexes in hex_list:
            if current in kb_hexes[0]:
                data.append(app_commands.Choice(name=kb_hexes[0], value=kb_hexes[0]))

    return data


async def hex_improvement_autocomplete(
        interaction: discord.Interaction, current: str) -> typing.List[app_commands.Choice[str]]:
    data = []
    guild_id = interaction.guild_id
    async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
        cursor = await db.cursor()
        current = unidecode(str.title(current))
        await cursor.execute(
            "SELECT Full_name FROM kb_Hexes_Improvements WHERE Full_Name like ? or Type LIKE ? Limit 20",
            (f"%{current}%", f"%{current}%"))
        improvement_list = await cursor.fetchall()
        for improvement in improvement_list:
            if current in improvement[0]:
                data.append(app_commands.Choice(name=improvement[0], value=improvement[0]))
    return data

async def hex_type_autocomplete(
        interaction: discord.Interaction, current: str) -> typing.List[app_commands.Choice[str]]:
    data = []
    guild_id = interaction.guild_id
    async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
        cursor = await db.cursor()
        current = unidecode(str.title(current))
        await cursor.execute(
            "SELECT DISTINCT Type FROM kb_Hexes_Improvements WHERE Type LIKE ? Limit 20",
            (f"%{current}%",))
        improvement_list = await cursor.fetchall()
        for improvement in improvement_list:
            if current in improvement[0]:
                data.append(app_commands.Choice(name=improvement[0], value=improvement[0]))
    return data

async def hex_subtype_autocomplete(
        interaction: discord.Interaction, current: str) -> typing.List[app_commands.Choice[str]]:
    data = []
    guild_id = interaction.guild_id
    async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
        cursor = await db.cursor()
        current = unidecode(str.title(current))
        await cursor.execute(
            "SELECT DISTINCT SubType FROM kb_Hexes_Improvements WHERE SubType like ? Limit 20",
            (f"%{current}%",))
        improvement_list = await cursor.fetchall()
        for improvement in improvement_list:
            if current in improvement[0]:
                data.append(app_commands.Choice(name=improvement[0], value=improvement[0]))
    return data



async def leadership_autocomplete(
        interaction: discord.Interaction, current: str) -> typing.List[app_commands.Choice[str]]:
    data = []
    guild_id = interaction.guild_id
    async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
        cursor = await db.cursor()
        current = unidecode(str.title(current))

        await cursor.execute(
            "SELECT Title from AA_Leadership_Roles WHERE Title LIKE ? Limit 20",
            (f"%{current}%",))
        title_list = await cursor.fetchall()

        for title in title_list:
            if current in title[0]:
                data.append(app_commands.Choice(name=title[0], value=title[0]))
    return data


async def kingdom_autocomplete(interaction: discord.Interaction, current: str) -> typing.List[app_commands.Choice[str]]:
    data = []
    guild_id = interaction.guild_id
    async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
        cursor = await db.cursor()
        current = unidecode(str.title(current))
        await cursor.execute(
            "SELECT kingdom from kb_Kingdoms WHERE Kingdom LIKE ? Limit 20",
            (f"%{current}%",))
        kingdom_list = await cursor.fetchall()
        for kingdom in kingdom_list:
            if current in kingdom[0]:
                data.append(app_commands.Choice(name=kingdom[0], value=kingdom[0]))

    return data


async def settlement_autocomplete(interaction: discord.Interaction, current: str) -> typing.List[app_commands.Choice[str]]:
    data = []
    guild_id = interaction.guild_id
    async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
        cursor = await db.cursor()
        current = unidecode(str.title(current))
        await cursor.execute(
            "SELECT Settlement, Kingdom from KB_Settlements WHERE Settlement LIKE ? Limit 20",
            (f"%{current}%",))
        settlement_list = await cursor.fetchall()
        for settlement in settlement_list:
            if current in settlement[0]:
                data.append(app_commands.Choice(name=f"{settlement[1]} - {settlement[0]}", value=settlement[0]))
    return data


async def event_name_autocomplete(interaction: discord.Interaction, current: str) -> typing.List[app_commands.Choice[str]]:
    data = []
    guild_id = interaction.guild_id
    async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
        cursor = await db.cursor()
        current = unidecode(str.title(current))
        await cursor.execute(
            "SELECT Name from KB_Events WHERE Name LIKE ? Limit 20",
            (f"%{current}%",))
        event_list = await cursor.fetchall()
        for event in event_list:
            if current in event[0]:
                data.append(app_commands.Choice(name=event[0], value=event[0]))
    return data


async def type_value_autocomplete(interaction: discord.Interaction, current: str) -> typing.List[app_commands.Choice[str]]:
    options = ['Economy', 'Loyalty', 'Stability', 'Fame', 'Unrest', 'Consumption', 'Defence', 'Taxation']
    return [
        app_commands.Choice(name=option, value=option)
        for option in options if current.lower() in option.lower()
    ]


async def modifier_autocomplete(interaction: discord.Interaction, current: str) -> typing.List[
    app_commands.Choice[str]]:
    options = ['Economy', 'Loyalty', 'Stability', 'Fame', 'Unrest', 'Consumption', 'Defence', 'Taxation', 'Corruption',
               'Crime', 'Productivity', 'Law', 'Lore', 'Society', 'Danger', 'Spellcasting', 'Base_Value', 'Supply']
    return [
        app_commands.Choice(name=option, value=option)
        for option in options if current.lower() in option.lower()
    ]


async def region_autocomplete(interaction: discord.Interaction, current: str) -> typing.List[app_commands.Choice[str]]:
    data = []
    guild_id = interaction.guild_id
    async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
        cursor = await db.cursor()
        current = unidecode(str.title(current))
        await cursor.execute(
            "SELECT Name FROM Regions WHERE Name LIKE ? Limit 20",
            (f"%{current}%",))
        region_list = await cursor.fetchall()
        for region in region_list:
            if current in region[0]:
                data.append(app_commands.Choice(name=region[0], value=region[0]))
    return data


async def search_timezones(interaction: discord.Interaction, current: str) -> typing.List[app_commands.Choice[str]]:
    # Get all available timezones
    from core.regions import timezone_cache
    # Filter timezones based on current input
    filtered_timezones = [tz for tz in timezone_cache if current.lower() in tz.lower()]

    # Return list of app_commands.Choice objects (maximum 25 choices for Discord autocomplete)
    return [
        app_commands.Choice(name=tz, value=tz)
        for tz in filtered_timezones[:25]  # Limit to 25 results to comply with Discord's limit
    ]


async def rp_inventory_autocomplete(
        interaction: discord.Interaction,
        current: str) -> typing.List[app_commands.Choice[str]]:
    data = []
    guild_id = interaction.guild.id
    current = unidecode(current.lower())
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            # Correct parameterized query
            cursor = await db.execute(
                "SELECT Item_Name FROM rp_players_items WHERE player_id = ? and item_name LIKE ? LIMIT 20",
                (interaction.user.id, f"%{current}%",))
            items_list = await cursor.fetchall()

            # Populate choices
            for item in items_list:
                if current in item[0].lower():
                    data.append(app_commands.Choice(name=item[0], value=item[0]))

    except (aiosqlite.Error, TypeError, ValueError) as e:
        print(f"An error occurred while fetching settings: {e}")
    return data


async def rp_store_autocomplete(
        interaction: discord.Interaction,
        current: str) -> typing.List[app_commands.Choice[str]]:
    data = []
    guild_id = interaction.guild.id
    current = unidecode(current.lower())
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.execute(
                "SELECT Name FROM RP_Store_Items WHERE Name LIKE ? LIMIT 20",
                (f"%{current}%",))
            items_list = await cursor.fetchall()

            for item in items_list:
                if current in item[0].lower():
                    data.append(app_commands.Choice(name=item[0], value=item[0]))

    except (aiosqlite.Error, TypeError, ValueError) as e:
        print(f"An error occurred while fetching settings: {e}")
    return data


async def own_character_select_autocompletion(
        interaction: discord.Interaction, current: str
) -> typing.List[app_commands.Choice[str]]:
    data = []
    guild_id = interaction.guild_id
    user_id = interaction.user.id
    current = unidecode(str.title(current))
    async with autocomplete_cache.lock:
        if (user_id, current) in autocomplete_cache.cache:
            return [app_commands.Choice(name=name, value=value) for name, value in autocomplete_cache.cache[(user_id, current)]]

    async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
        cursor = await db.cursor()
        await cursor.execute(
            "SELECT Character_Name FROM Player_Characters WHERE Player_ID = ? AND Character_Name LIKE ? Limit 20",
            (user_id, f"%{current}%"))
        character_list = await cursor.fetchall()
        for character in character_list:
            data.append(app_commands.Choice(name=character[0], value=character[0]))
    
    async with autocomplete_cache.lock:
        formatted_data = [(choice.name, choice.value) for choice in data]
        autocomplete_cache.cache[(user_id, current)] = formatted_data
    return data


async def character_select_autocompletion(
        interaction: discord.Interaction, current: str
) -> typing.List[app_commands.Choice[str]]:
    data = []
    guild_id = interaction.guild_id
    current = unidecode(str.title(current))
    async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
        cursor = await db.cursor()
        await cursor.execute(
            "SELECT Character_Name FROM Player_Characters WHERE Character_Name LIKE ? Limit 20",
            (f"%{current}%",))
        character_list = await cursor.fetchall()
        for character in character_list:
            data.append(app_commands.Choice(name=character[0], value=character[0]))
    return data


async def title_autocomplete(interaction: discord.Interaction, current: str) -> typing.List[app_commands.Choice[str]]:
    data = []
    guild_id = interaction.guild_id
    current = unidecode(str.title(current))
    async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
        cursor = await db.cursor()
        await cursor.execute(
            "SELECT Masculine_Name, Feminine_Name, ID FROM Store_Title WHERE Masculine_Name LIKE ? OR Feminine_Name LIKE ? Limit 20",
            (f"%{current}%", f"%{current}%"))
        title_list = await cursor.fetchall()
        for title in title_list:
            data.append(app_commands.Choice(name=f"{title[0]}/{title[1]}", value=str(title[0])))
    return data


async def fame_autocomplete(interaction: discord.Interaction, current: str) -> typing.List[app_commands.Choice[str]]:
    data = []
    guild_id = interaction.guild_id
    current = unidecode(str.title(current))
    async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
        cursor = await db.cursor()
        await cursor.execute(
            "SELECT Name FROM Store_Fame WHERE Name LIKE ? Limit 20",
            (f"%{current}%",))
        fame_list = await cursor.fetchall()
        for fame in fame_list:
            data.append(app_commands.Choice(name=fame[0], value=fame[0]))
    return data


async def group_id_autocompletion(interaction: discord.Interaction, current: str) -> typing.List[app_commands.Choice[int]]:
    data = []
    guild_id = interaction.guild_id
    current = unidecode(str.title(current))
    async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
        cursor = await db.cursor()
        await cursor.execute(
            "SELECT Group_ID, Group_Name FROM Sessions_Group WHERE Group_Name LIKE ? OR Group_ID LIKE ? Limit 20",
            (f"%{current}%", f"%{current}%"))
        group_list = await cursor.fetchall()
        for group in group_list:
            data.append(app_commands.Choice(name=f"{group[0]}: {group[1]}", value=group[0]))
    return data


async def player_session_autocomplete(interaction: discord.Interaction, current: str) -> typing.List[app_commands.Choice[int]]:
    data = []
    guild_id = interaction.guild_id
    current = unidecode(str.title(current))
    async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
        cursor = await db.cursor()
        # Filtering for inactive sessions as this is primarily used for reporting
        await cursor.execute(
            "SELECT Session_ID, Session_Name FROM Sessions WHERE (Session_Name LIKE ? OR Session_ID LIKE ?) AND IsActive = 0 Limit 25",
            (f"%{current}%", f"%{current}%"))
        session_list = await cursor.fetchall()
        for session in session_list:
            data.append(app_commands.Choice(name=f"{session[0]}: {session[1]}", value=session[0]))
    return data


async def get_plots_autocomplete(
        interaction: discord.Interaction,
        current: str) -> List[app_commands.Choice[str]]:
    """Provide autocomplete suggestions for plots."""
    data = []
    guild_id = interaction.guild_id
    cache_key = guild_id
    current_lower = current.lower()

    async with AutocompleteWorldAnvilCache.lock:
        cached_entry = AutocompleteWorldAnvilCache.cache.get(cache_key)
        if cached_entry:
            plot_list, timestamp = cached_entry
            if time() - timestamp < CACHE_EXPIRATION:
                # Cache is valid
                pass
            else:
                # Cache expired
                plot_list = None
        else:
            plot_list = None

    if plot_list is None:
        # Fetch data from World Anvil API
        try:
            client = WaClient(
                'pathparser',
                'https://github.com/Solfyrism/pathparser',
                'V1.1',
                os.getenv('WORLD_ANVIL_API'),
                os.getenv(f'WORLD_ANVIL_{guild_id}')
            )

            async with config_cache.lock:
                configs = config_cache.cache.get(guild_id)
                if configs:
                    wa_world_id = configs.get('WA_World_ID')
                    wa_plot_folder = configs.get('WA_Plot_Folder')

            # Ensure that the client methods are asynchronous or use an executor
            loop = asyncio.get_event_loop()
            plot_list = await loop.run_in_executor(
                None,
                client.world.articles,
                wa_world_id,
                wa_plot_folder
            )

            # Cache the result with a timestamp
            async with AutocompleteWorldAnvilCache.lock:
                AutocompleteWorldAnvilCache.cache[cache_key] = (plot_list, time())
        except Exception as e:
            logging.error(f"Error fetching articles from World Anvil: {e}")
            return []

    # Filter the plots based on the current input
    for plot in plot_list:
        plot_title = plot[1]['title']
        if current_lower in plot_title.lower():
            data.append(app_commands.Choice(name=plot_title, value=f"2-{plot[1]['id']}"))

    # If the current input doesn't match any existing plots, offer to create a new one
    if len(data) < 25:
        data.append(app_commands.Choice(name=f"NEW: {current.title()}", value=f"1-{current.title()}"))

    # Limit the number of choices to Discord's maximum
    data = data[:25]

    return data


async def get_precreated_plots_autocompletion(
        interaction: discord.Interaction,
        current: str) -> typing.List[app_commands.Choice[str]]:
    """This is a test command for the wa command."""
    data = []
    client = WaClient(
        'pathparser',
        'https://github.com/Solfyrism/pathparser',
        'V1.1',
        os.getenv('WORLD_ANVIL_API'),
        os.getenv('WORLD_ANVIL_USER')
    )
    articles_list = [article for article in client.world.articles('f7a60480-ea15-4867-ae03-e9e0c676060a',
                                                                  '9ad3d530-1a42-4e99-9a09-9c4dccddc70a')]
    for articles in articles_list:
        if str.lower(current) in str.lower(articles['title']):
            data.append(app_commands.Choice(name=articles['title'], value=f"{articles['id']}"))
    return data



async def rp_home_autocomplete(
        interaction: discord.Interaction,
        current: str) -> list[app_commands.Choice[str]]:
    data = []
    guild_id = interaction.guild.id
    current = unidecode(current.lower())
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            # Correct parameterized query
            cursor = await db.execute("""
            SELECT name FROM rp_store_items 
            WHERE name LIKE ? and 
            Name in ('House', 'Mansion', 'Palace', 'Castle', 'Private', 'Island Vista')
            LIMIT 20
             """, (f"%{current}%",))
            items_list = await cursor.fetchall()

            # Populate choices
            for item in items_list:
                if current in item[0].lower():
                    data.append(app_commands.Choice(name=item[0], value=item[0]))
    except (aiosqlite.Error, TypeError, ValueError) as e:
        logging.exception(f"An error occurred while fetching settings: {e}")
    return data

async def settings_autocomplete(
        interaction: discord.Interaction,
        current: str) -> list[app_commands.Choice[str]]:
    data = []
    guild_id = interaction.guild.id
    current = unidecode(current.lower())
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            # Correct parameterized query

            cursor = await db.execute("SELECT Identifier FROM Admin WHERE Identifier LIKE ? LIMIT 20",
                                      (f"%{current}%",))
            settings_list = await cursor.fetchall()

            # Populate choices
            for setting in settings_list:
                if current in setting[0].lower():
                    data.append(app_commands.Choice(name=setting[0], value=setting[0]))

    except (aiosqlite.Error, TypeError, ValueError) as e:
        logging.exception(f"An error occurred while fetching settings: {e}")
    return data


async def stg_character_select_autocompletion(
        interaction: discord.Interaction,
        current: str) -> typing.List[app_commands.Choice[str]]:
    data = []
    guild_id = interaction.guild_id
    async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
        current = unidecode(str.title(current))
        cursor = await db.execute(
            "SELECT True_Character_Name, Character_Name from A_STG_Player_Characters where Character_Name LIKE ? OR Nickname LIKE ? LIMIT 5",
            (f"%{current}%", f"%{current}%"))
        character_list = await cursor.fetchall()
        for characters in character_list:
            if current in characters[1]:
                data.append(app_commands.Choice(name=characters[0], value=characters[0]))

        return data


async def response_trigger_autocomplete(
        interaction: discord.Interaction,
        current: str) -> typing.List[app_commands.Choice[str]]:
    """Autocomplete for Response_Trigger entries, returning TriggerID as the value."""
    data = []
    guild_id = interaction.guild_id
    current_lower = current.lower()
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.execute(
                "SELECT TriggerID, Trigger, MatchType FROM Response_Trigger "
                "WHERE Trigger LIKE ? OR CAST(TriggerID AS TEXT) LIKE ? LIMIT 25",
                (f"%{current_lower}%", f"%{current_lower}%")
            )
            rows = await cursor.fetchall()
            for row in rows:
                trigger_id, trigger, match_type = row
                label = f"[{trigger_id}] {trigger} ({match_type})"
                data.append(app_commands.Choice(name=label[:100], value=str(trigger_id)))
    except (aiosqlite.Error, TypeError, ValueError) as e:
        logging.exception(f"Error in response_trigger_autocomplete: {e}")
    return data


async def response_followup_autocomplete(
        interaction: discord.Interaction,
        current: str) -> typing.List[app_commands.Choice[str]]:
    """Autocomplete for Response_Followup button names, scoped to the trigger_id in the interaction namespace."""
    data = []
    guild_id = interaction.guild_id
    current_lower = current.lower()
    # Try to read trigger_id from already-filled options
    trigger_id = None
    try:
        namespace = interaction.namespace
        trigger_id_raw = getattr(namespace, 'trigger_id', None)
        if trigger_id_raw is not None:
            trigger_id = int(trigger_id_raw)
    except (ValueError, AttributeError):
        trigger_id = None
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            if trigger_id is not None:
                cursor = await db.execute(
                    "SELECT rowid, buttonname FROM Response_Followup "
                    "WHERE TriggerID = ? AND buttonname LIKE ? LIMIT 25",
                    (trigger_id, f"%{current_lower}%")
                )
            else:
                cursor = await db.execute(
                    "SELECT rowid, buttonname FROM Response_Followup "
                    "WHERE buttonname LIKE ? LIMIT 25",
                    (f"%{current_lower}%",)
                )
            rows = await cursor.fetchall()
            for row in rows:
                rowid, button_name = row
                data.append(app_commands.Choice(name=button_name[:100], value=button_name))
    except (aiosqlite.Error, TypeError, ValueError) as e:
        logging.exception(f"Error in response_followup_autocomplete: {e}")
    return data


