import math
import random
import typing
import discord
import requests
from discord.ext import commands
from discord import app_commands
from typing import List, Optional
import aiosqlite
import pytz
import datetime
import logging
import os
from pywaclient.api import BoromirApiClient as WaClient

from commands import gamemaster_commands

from core.regions import (
    regions, africa_regions, asia_regions, europe_regions, north_america_regions,
    us_regions, us_state_timezones, continent_regions, region_timezones, continent_to_countries,
    timezone_cache
)
from core.player_views import (
    ContinentSelect, RegionSelect, USRegionSelect, CountrySelect, TimezoneSelect,
    DaySelect, TimeStyleSelect, HourSelect, AMPMSelect, MinuteSelect,
    AddAnotherSlotButton, StateSelect, FinishButton, BackButton, CancelButton,
    ChangeTimeFormatButton, TimezoneCompleteButton, AvailabilityView, UnavailabilityView
)
from core.time_utils import (
    fetch_timecard_data_from_db, fetch_group_availability_from_db,
    create_timecard_plot, create_timecard_group_plot, update_player_timezone,
    get_next_weekday, get_utc_offset, parse_time_input, time_to_minutes
)
from core.autocomplete import (
    search_timezones, own_character_select_autocompletion,
    player_session_autocomplete, group_id_autocompletion
)
from core.utils import get_gold_breakdown
from core.config import config_cache
from core.worldanvil import drive_word_document
from core.views import ShopView, RecipientAcknowledgementView


async def player_signup(
        guild: discord.Guild,
        thread_id: int,
        session_name: str,
        session_id: int,
        player_id: int,
        character_name: str,
        warning_duration: typing.Optional[int]) -> bool:
    try:
        async with aiosqlite.connect(f"pathparser_{guild.id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute(
                """Select 
                player_name, True_Character_Name, title, 
                level, tier, 
                gold, gold_value, 
                tradition_name, tradition_link, template_name, template_link, 
                mythweavers, image_link, color, 
                description, titles,
                essence, oath from Player_Characters where Player_ID = ? and Character_Name = ?""",
                (player_id, character_name))
            character_info = await cursor.fetchone()
            if character_info:
                (player_name, character_name, title,
                 level, tier,
                 gold, gold_value,
                 tradition_name, tradition_link, template_name, template_link,
                 mythweavers, image_link, color,
                 description, titles,
                 essence, oath) = character_info
                await cursor.execute("SELECT Character_Name from Sessions_Signups WHERE Character_Name = ? and Session_ID = ?",
                                     (character_name,session_id))
                character_present = await cursor.fetchone()
                if character_present:
                    return False

                await cursor.execute(
                    """INSERT INTO Sessions_Signups (Session_ID, Session_Name, Player_Name, Player_ID, Character_Name, Level, Effective_Wealth, Tier, Notification_Warning) Values (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (session_id, session_name, player_name, player_id, character_name, level, gold_value - gold, tier,
                     warning_duration)
                )
                await db.commit()

                thread = guild.get_thread(thread_id)
                if not thread:
                    thread = await guild.fetch_channel(thread_id)
                if thread:
                    embed = signup_embed(
                        character_name=character_name,
                        title=titles,
                        level=level,
                        tier=tier,
                        gold=gold,
                        gold_value=gold_value,
                        tradition_name=tradition_name,
                        tradition_link=tradition_link,
                        template_name=template_name,
                        template_link=template_link,
                        mythweavers=mythweavers,
                        image_link=image_link,
                        color=color,
                        description=description)
                    await thread.send(embed=embed, content=f"<@{player_id}>",
                                      allowed_mentions=discord.AllowedMentions(users=True))
                    return True
                else:
                    raise ValueError(f"Thread {thread_id} not found in guild {guild.id}")
            else:
                raise ValueError(f"Character {character_name} not found for player {player_id}")
    except (aiosqlite.Error, TypeError) as e:
        logging.exception(f"Failed to sign up player <@{player_id}> for session {session_name} ({session_id}): {e}")


def signup_embed(
        character_name: str,
        title: str,
        level: int,
        tier: int,
        gold: int,
        gold_value: int,
        tradition_name: str,
        tradition_link: str,
        template_name: str,
        template_link: str,
        mythweavers: str,
        image_link: str,
        color: str,
        description: str) -> discord.Embed:
    try:
        if any([tradition_name, tradition_link, template_name, template_link]):
            print("Tradition or template found")
            print(tradition_name, tradition_link, template_name, template_link)
        title_field = f"{character_name} would like to participate" if title is None else f"{title} {character_name} would like to participate"
        embed = discord.Embed(title=title_field, color=int(color[1:], 16), url=mythweavers)
        embed.set_thumbnail(url=image_link)
        gold_string = get_gold_breakdown(gold_value - gold)
        embed.add_field(name="Information", value=f"**Level**: {level}, **Mythic Tier**: {tier}")
        embed.add_field(name="illiquid Wealth", value=f"**Gold**: {gold_string}")
        additional_info = f"**Tradition**: [{tradition_name}]({tradition_link})" if tradition_name else ""
        additional_info += '\r\n' if tradition_name and template_name else ""
        additional_info += f"**Template**: [{template_name}]({template_link})" if template_name else ""
        if tradition_name or template_name:
            embed.add_field(name="Additional Info", value=additional_info, inline=False)
        embed.set_footer(text=description)
        return embed
    except ValueError as e:
        logging.exception(f"Failed to create signup embed for character {character_name}: {e}")


async def player_leave_session(guild: discord.Guild, session_id: int, player_name: str, player: bool = True) -> bool:
    async with aiosqlite.connect(f"pathparser_{guild.id}.sqlite") as db:
        try:
            cursor = await db.cursor()
            await cursor.execute("SELECT Session_Thread FROM Sessions WHERE Session_ID = ?", (session_id,))
            session_info = await cursor.fetchone()
            print(session_info)

            await cursor.execute(
                "DELETE FROM Sessions_Signups WHERE Session_ID = ? AND Player_Name = ?",
                (session_id, player_name)
            )
            await cursor.execute(
                "DELETE FROM Sessions_Participants WHERE Session_ID = ? AND Player_Name = ?",
                (session_id, player_name)
            )
            await db.commit()
            print("Deleted from signups and participants")

            if session_info:
                thread_id = session_info[0]
                thread = guild.get_thread(thread_id)
                if not thread:
                    thread = await guild.fetch_channel(thread_id)
                if thread:
                    if player:
                        await thread.send(f"{player_name} has decided against participating in the session!")
                    else:
                        await thread.send(f"{player_name} has been removed from the session!")
                    return True
                else:
                    raise ValueError(f"Thread {thread_id} not found in guild {guild.id}")
            return True
        except aiosqlite.Error as e:
            logging.exception(f"Failed to remove player {player_name} from session {session_id}: {e}")


async def update_report(guild_id: int, overview: str, world_id: str, article_id: str, character_name: str,
                        author_name: str):
    try:
        if guild_id == 883009758179762208:
            time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            client = WaClient(
                'pathparser',
                'https://github.com/Solfyrism/pathparser',
                'V1.1',
                os.getenv('WORLD_ANVIL_API'),
                os.getenv('WORLD_ANVIL_USER')
            )
            overview = drive_word_document(overview)

            specific_article = client.article.get(article_id, granularity=1)

            new_overview = f'{specific_article["reportNotes"]} [br] [br] {author_name} [br] {character_name} - {time} [br] {overview}' if \
                specific_article["reportNotes"] is not None else f'{character_name} - {time} [br] {overview}'
            client.article.patch(article_id, {
                'reportNotes': f'{new_overview}',
                'world': {'id': world_id}
            })
            return True
    except (ValueError, KeyError) as e:
        logging.exception(f"Failed to update report for {character_name} in guild {guild_id}: {e}")
        return False


async def delete_group(guild: discord.Guild, group_id: int, role_id: int) -> bool:
    try:
        async with aiosqlite.connect(f"pathparser_{guild.id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute("DELETE FROM Sessions_group WHERE Group_ID = ?", (group_id,))
            await db.commit()
            await cursor.execute("DELETE FROM Sessions_Group_Presign WHERE Role_ID = ?", (role_id,))
            await db.commit()
            await guild.get_role(role_id).delete()
            return True
    except aiosqlite.Error as e:
        logging.exception(f"Failed to delete group {group_id} in guild {guild.id}: {e}.")
        return False


async def create_new_group(
        guild: discord.Guild,
        player_name: str,
        player_id: int,
        group_name: str,
        host_character: str,
        description: str) -> typing.Optional[discord.Role]:
    try:
        async with aiosqlite.connect(f"pathparser_{guild.id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute(
                "INSERT INTO Sessions_Group(Player_Name, Group_Name, Host_Character, Description) VALUES (?, ?, ?, ?)",
                (player_name, group_name, host_character, description))
            await db.commit()
            await cursor.execute(
                "SELECT Max(Group_ID) FROM Sessions_Group WHERE Player_Name = ? AND Group_Name = ? AND Host_Character = ?",
                (player_name, group_name, host_character))
            group_id = await cursor.fetchone()
            role = await guild.create_role(name=group_name, mentionable=True)

            await cursor.execute("INSERT INTO Sessions_Group_Presign(Group_ID, Player_Name) VALUES (?, ?)",
                                 (group_id[0], player_name))
            await db.commit()
            await cursor.execute("UPDATE Sessions_Group SET Role_ID = ? WHERE Group_ID = ?", (role.id, group_id[0]))
            await db.commit()
            await guild.get_member(player_id).add_roles(role)

            return role
    except aiosqlite.Error as e:
        logging.exception(f"Failed to delete group {group_id} in guild {guild.id}: {e}.")
        return None


async def join_group(
        guild: discord.Guild,
        player_name: str,
        player_id: int,
        group_id: int,
        group_role_id) -> bool:
    try:
        async with aiosqlite.connect(f"pathparser_{guild.id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute(
                "INSERT INTO Sessions_Group_Presign(Group_ID, Player_Name) VALUES (?, ?)",
                (group_id, player_name))
            await db.commit()
            await guild.get_member(player_id).add_roles(guild.get_role(group_role_id))
            return True
    except aiosqlite.Error as e:
        logging.exception(f"Failed to delete group {group_id} in guild {guild.id}: {e}.")
        return False


def random_name():
    name = ''
    url = 'https://www.mit.edu/~ecprice/wordlist.10000'
    response = requests.get(url)
    words = response.content.splitlines()
    max_length = 32
    while len(name) + 4 < max_length:
        word = random.choice(words)
        if len(name) + len(word) < max_length:
            name += word.decode('utf-8').capitalize()
        else:
            break
    return name


async def leave_group(
        guild: discord.Guild,
        player_name: str,
        player_id: int,
        group_id: int,
        group_role_id: int) -> bool:
    try:
        async with aiosqlite.connect(f"pathparser_{guild.id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute("DELETE FROM Sessions_Group_Presign WHERE Group_ID = ? AND Player_Name = ?",
                                 (group_id, player_name))
            await db.commit()
            player = guild.get_member(player_id)
            if not player:
                raise ValueError(f"Player {player_id} not found in guild {guild.id}")
            role = guild.get_role(group_role_id)
            if not role:
                raise ValueError(f"Role {group_role_id} not found in guild {guild.id}")
            await player.remove_roles(role)
            return True
    except aiosqlite.Error as e:
        logging.exception(f"Failed to delete group {group_id} in guild {guild.id}: {e}.")
        return False


async def build_timesheet(guild_id: int, player_name: str) -> bool:
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()
            day = 1
            while day < 8:
                await cursor.execute("INSERT INTO Player_Timecard (Player_Name, Day) VALUES (?, ?)", (player_name, day))
                await db.commit()
                day += 1
            return True
    except aiosqlite.Error as e:
        logging.exception(f"Failed to build timesheet for {player_name} in guild {guild_id}: {e}.")
        return False


async def clear_timesheet(guild_id: int, player_name: str) -> bool:
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute("DELETE FROM Player_Timecard WHERE Player_Name = ?", (player_name,))
            await db.commit()
            return True
    except aiosqlite.Error as e:
        logging.exception(f"Failed to clear timesheet for {player_name} in guild {guild_id}: {e}.")
        return False



class PlayerCommands(commands.Cog, name='Player'):
    def __init__(self, bot):
        self.bot = bot

    player_group = discord.app_commands.Group(
        name='player',
        description='Commands related to playing'
    )

    sessions_group = discord.app_commands.Group(
        name='sessions',
        description='commands related to participating and playing in sessions..',
        parent=player_group
    )

    group_group = discord.app_commands.Group(
        name='group',
        description='Commands related to grouping up.',
        parent=player_group
    )

    timesheet_group = discord.app_commands.Group(
        name='timesheet',
        description='Commands related to setting your availability',
        parent=player_group
    )


    @player_group.command(name='help', description="Get help with player commands")
    async def help(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        embed = discord.Embed(title="Player Commands Help", color=discord.Color.green())
        embed.add_field(
            name="__**Group**__",
            value="""Commands related to grouping up with your fellow players! \r\n
            **/player group create** - Create a new group for players to join! \n
            **/player group delete** - Delete a group that you have created! \n
            **/player group display** - Display all the groups! \n
            **/player group join** - Join a group that has been created! \n
            **/player group leave** - Leave a group that you have joined! \n
        """, inline=False)
        embed.add_field(
            name="__**Timesheet**__",
            value="""Commands related to setting up your timesheets! \r\n
                **/player timesheet availability** - Display your availability on a day! \n
                **/player timesheet group** - Display the overall availability of a group! \n
                **/player timesheet set** - Set your time and timezone! \n
                **/player timesheet timezone** - Set a specific timezone if you don't want to use the options menu! \n
                """, inline=False)
        embed.add_field(
            name="__**Sessions**__",
            value="""Commands related to participating and playing in sessions! \r\n
            **/player sessions Display** - display sessions! \n
            **/player sessions join** - Join a session! \n
            **/player sessions leave** - Leave a session! \n
            **/player sessions Notify** - Update your notification window! \n
            **/player sessions report** - report on a session and add your notes to a WA article! \n    
            """, inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @sessions_group.command(name='join', description='join a session')
    @app_commands.autocomplete(character_name=own_character_select_autocompletion)
    @app_commands.choices(notification=[
        discord.app_commands.Choice(name='an hour before', value=60),
        discord.app_commands.Choice(name='half an hour before', value=30),
        discord.app_commands.Choice(name='session start', value=0),
        discord.app_commands.Choice(name='no reminder', value=-1)])
    async def join(self, interaction: discord.Interaction, session_id: int, character_name: str,
                   notification: typing.Optional[discord.app_commands.Choice[int]]):
        """Offer your Participation in a session."""
        warning_duration = -1 if notification is None else notification.value
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute(
                    "SELECT Session_Name, Play_location, hammer_time, game_link, Session_Range_ID, Session_Range, Session_Thread, overflow FROM Sessions WHERE Session_ID = ? AND IsActive = 1",
                    (session_id,)
                )
                session_info = await cursor.fetchone()
                if session_info is None:
                    await interaction.followup.send(f"No active session with Session ID: {session_id} can be found!")
                else:
                    (session_name, play_location, hammer_time, game_link, session_range_id, session_range,
                     session_thread,
                     overflow) = session_info

                    await cursor.execute(
                        "SELECT Player_Name from Sessions_Signups WHERE Session_ID = ? AND Player_Name = ?",
                        (session_id, interaction.user.name))
                    signup_present = await cursor.fetchone()
                    await cursor.execute(
                        "SELECT Player_Name from Sessions_Participants WHERE Session_ID = ? AND Player_Name = ?", (session_id, interaction.user.name)
                    )
                    participant_present = await cursor.fetchone()
                    if signup_present or participant_present:
                        await interaction.followup.send(
                            f"Player {interaction.user.name} has already signed up for session {session_name} ({session_id})",
                            ephemeral=True)
                        return
                    else:

                        await cursor.execute(
                            "SELECT Level from Player_Characters WHERE Player_ID = ? AND Character_Name = ?",
                            (interaction.user.id, character_name))
                        character_info = await cursor.fetchone()
                        if not character_info:
                            await interaction.followup.send(
                                f"Character {character_name} not found for player {interaction.user.name}")
                            return
                        else:
                            level = character_info[0]
                            quest_thread = interaction.guild.get_thread(session_thread)
                            if not quest_thread:
                                quest_thread = await interaction.guild.fetch_channel(session_thread)
                            if not quest_thread:
                                raise ValueError(f"Thread {session_thread} not found in guild {interaction.guild_id}")
                            if overflow == 4:
                                min_level = 0
                                max_level = 999
                                join_session = await player_signup(
                                    guild=interaction.guild,
                                    thread_id=session_thread,
                                    session_name=session_name,
                                    session_id=session_id,
                                    player_id=interaction.user.id,
                                    character_name=character_name,
                                    warning_duration=warning_duration)
                                if join_session:
                                    await interaction.followup.send(
                                        content="You have submitted your request! Please wait for the GM to accept or deny your request!",
                                        ephemeral=True)
                                else:
                                    await interaction.followup.send(
                                        f"Failed to sign up player {interaction.user.name} for session {session_name} ({session_id})",
                                        ephemeral=True)
                                return
                            else:
                                secondary_role = await gamemaster_commands.validate_milestone_system_overflow(
                                    guild=interaction.guild,
                                    overflow=overflow,
                                    session_range_id=session_range_id)
                                if not secondary_role:
                                    secondary_role = await gamemaster_commands.validate_region_system_overflow(
                                        guild=interaction.guild,
                                        overflow=overflow,
                                        session_range_id=session_range_id)
                                else:
                                    (role_name, min_level, max_level) = secondary_role
                                if overflow == 1 or not secondary_role:
                                    await cursor.execute(
                                        "Select min(level), max(level), Level_Range_ID from Milestone_System WHERE Level_Range_ID = ?",
                                        (session_range_id,))
                                    level_range_info = await cursor.fetchone()
                                    (min_level, max_level, role_name) = level_range_info
                                else:
                                    (role_name, min_level, max_level) = secondary_role

                            if not min_level or not max_level:
                                role = interaction.guild.get_role(session_range_id)
                                if not role:
                                    await interaction.followup.send(
                                        f"Role {session_range_id} not found in guild {interaction.guild_id}")
                                    raise ValueError(f"Role {session_range_id} not found in guild {interaction.guild_id}")
                                if role in interaction.user.roles:
                                    join_session = await player_signup(
                                        guild=interaction.guild,
                                        thread_id=session_thread,
                                        session_name=session_name,
                                        session_id=session_id,
                                        player_id=interaction.user.id,
                                        character_name=character_name,
                                        warning_duration=warning_duration)
                                    if join_session:
                                        await interaction.followup.send(
                                            content=f"You have submitted your request! Please wait for the GM to accept or deny your request!",
                                            ephemeral=True)
                                    else:
                                        await interaction.followup.send(
                                            f"Failed to sign up player {interaction.user.name} for session {session_name} ({session_id})",
                                            ephemeral=True)
                                else:
                                    await interaction.followup.send(
                                        f"You do not have the required role to join this session.", ephemeral=True)
                            else:
                                if min_level <= level <= max_level:
                                    join_session = await player_signup(
                                        guild=interaction.guild,
                                        thread_id=session_thread,
                                        session_name=session_name,
                                        session_id=session_id,
                                        player_id=interaction.user.id,
                                        character_name=character_name,
                                        warning_duration=warning_duration)
                                    if join_session:
                                        await interaction.followup.send(
                                            content=f"You have submitted your request! Please wait for the GM to accept or deny your request!",
                                            ephemeral=True)
                                    else:
                                        await interaction.followup.send(
                                            f"Failed to sign up player {interaction.user.name} for session {session_name} ({session_id})",
                                            ephemeral=True)
                                else:
                                    await interaction.followup.send(
                                        f"Character {character_name} is not within the level range of the session.",
                                        ephemeral=True)
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(
                f"Failed to sign up player {interaction.user.name} for session with id: ({session_id}:{e}")

    @sessions_group.command(name='notify', description='Update your notification time for a session')
    @app_commands.choices(notification=[
        discord.app_commands.Choice(name='an hour before', value=60),
        discord.app_commands.Choice(name='half an hour before', value=30),
        discord.app_commands.Choice(name='session start', value=0),
        discord.app_commands.Choice(name='no reminder', value=-1)])
    async def notify_me(
            self, interaction:
            discord.Interaction,
            session_id: int,
            notification: typing.Optional[discord.app_commands.Choice[int]]):
        warning_duration = -1 if notification is None else notification.value
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                update_signups = await cursor.execute(
                    "UPDATE Sessions_Signups SET Notification_Warning = ? WHERE Session_ID = ? AND Player_ID = ?",
                    (warning_duration, session_id, interaction.user.id))
                await db.commit()
                update_participants = await cursor.execute(
                    "UPDATE Sessions_Participants SET Notification_Warning = ? WHERE Session_ID = ? AND Player_ID = ?",
                    (warning_duration, session_id, interaction.user.id))
                await db.commit()
                if update_signups.rowcount > 0 or update_participants.rowcount > 0:
                    await interaction.followup.send(content=f"Notification time updated for {session_id}!",
                                                    ephemeral=True)
        except (aiosqlite.Error, TypeError) as e:
            logging.exception(f"Failed to sign up player {interaction.user.name} for session ({session_id}): {e}")
            await interaction.followup.send(
                f"Failed to sign up player {interaction.user.name} for session ({session_id})", ephemeral=True)

    @sessions_group.command(name='leave', description='Rescind your Participation in a session')
    async def leave_session(self, interaction: discord.Interaction, session_id: int):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute(
                    "SELECT Session_Name, Play_location, hammer_time, Game_Link FROM Sessions WHERE Session_ID = ?",
                    (session_id,))
                print("i got here")
                session_info = await cursor.fetchone()
                if session_info is None:
                    await interaction.followup.send(f"No active session with {session_id} can be found!")
                if session_info is not None:
                    await cursor.execute(
                        "SELECT Character_Name, Level, Effective_Wealth from Sessions_Signups where Player_Name = ? and session_ID = ?",
                        (interaction.user.name, session_id))
                    character_info = await cursor.fetchone()
                    if character_info is None:
                        await cursor.execute(
                            "SELECT Character_Name, Level, Effective_Wealth from Sessions_Participants where Player_Name = ? and session_ID = ?",
                            (interaction.user.name,session_id))
                        character_info = await cursor.fetchone()
                        if character_info is None:
                            await interaction.followup.send(
                                f"{interaction.user.name} has no active character in this session!")
                        if character_info is not None:
                            true_name = character_info[0]
                            await db.close()
                            await player_leave_session(interaction.guild, session_id, interaction.user.name)
                            await interaction.followup.send(
                                f"{interaction.user.name}'s {true_name} has decided against participating in the session of '{session_info[0]}'!")
                    elif character_info is not None:
                        true_name = character_info[0]
                        await db.close()
                        await player_leave_session(interaction.guild, session_id, interaction.user.name)
                        await interaction.followup.send(
                            f"{interaction.user.name}'s {true_name} has decided against participating in the session of '{session_info[0]}'!")
        except aiosqlite.Error as e:
            logging.exception(f"Failed to remove player {interaction.user.name} from session {session_id} {e}")

    @sessions_group.command(name='display', description='Display all participants and signups for a session!')
    @app_commands.describe(
        group="Displaying All Participants & Signups, Active Participants Only, or Potential Sign-ups Only for a session")
    @app_commands.choices(group=[discord.app_commands.Choice(name='All', value=1),
                                 discord.app_commands.Choice(name='Participants', value=2),
                                 discord.app_commands.Choice(name='Sign-ups', value=3)])
    async def display(self, interaction: discord.Interaction, session_id: int,
                      group: discord.app_commands.Choice[int] = 1, page_number: int = 1):
        """ALL: THIS COMMAND DISPLAYS SESSION INFORMATION"""
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild.id}.sqlite") as conn:
                cursor = await conn.cursor()
                view_type = 0 if group == 1 else group.value - 1
                count = 0
                if view_type == 0 or view_type == 1:
                    await cursor.execute("SELECT COUNT(*) FROM Sessions_Participants WHERE Session_ID = ?",
                                         (session_id,))
                    participants_count = await cursor.fetchone()
                    count += 0 if not participants_count else participants_count[0]
                if view_type == 0 or view_type == 2:
                    cursor = await conn.execute("SELECT COUNT(*) FROM Sessions_Signups WHERE Session_ID = ?",
                                                (session_id,))
                    signups_count = await cursor.fetchone()
                    count += 0 if not signups_count else participants_count[0]
                max_items = count
                if max_items == 0:
                    await interaction.followup.send("No participants or signups found for this session!")
                    return
                else:
                    # Set up pagination variables
                    page_number = min(max(page_number, 1), math.ceil(max_items / 20))
                    items_per_page = 20 if view_type == 1 else 1
                    offset = (page_number - 1) * items_per_page

                    # Create and send the view with the results
                    view = gamemaster_commands.SessionDisplayView(
                        user_id=interaction.user.id,
                        guild_id=interaction.guild.id,
                        limit=items_per_page,
                        offset=offset,
                        view_type=view_type,
                        interaction=interaction,
                        session_id=session_id
                    )
                    await view.send_initial_message()
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"An error occurred whilst displaying session information: {e}")
            await interaction.followup.send(
                "An error occurred whilst displaying session information. Please try again later.")

    @sessions_group.command(name='report', description='Report on a session')
    @app_commands.describe(summary="This will use a Google Drive Link if available")
    @app_commands.autocomplete(session_id=player_session_autocomplete)
    @app_commands.autocomplete(character_name=own_character_select_autocompletion)
    async def report(self, interaction: discord.Interaction, session_id: int, summary: str, character_name: str):
        """Report on a session"""
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute(
                    "SELECT Session_ID, Session_Name, Article_Link, Article_ID, History_ID FROM Sessions WHERE Session_ID = ? AND IsActive = 0",
                    (session_id,))
                session_info = await cursor.fetchone()
                if session_info is None:
                    await interaction.followup.send(f"No completed Session with ID {session_id} could be found!")
                else:
                    (session_id, session_name, article_link, article_id, history_id) = session_info
                    await cursor.execute(
                        "SELECT Character_Name from Sessions_Archive where Session_ID = ? and Player_Name = ?",
                        (session_id, interaction.user.name))
                    character_info = await cursor.fetchone()
                    if character_info is None:
                        await interaction.followup.send(
                            f"Character {character_name} not found for player {interaction.user.name}")
                    else:
                        async with config_cache.lock:
                            configs = config_cache.cache.get(interaction.guild.id)
                            if configs:
                                world_id = configs.get('WA_World_ID')

                        if not world_id:
                            await interaction.followup.send("World ID not found!")
                        else:
                            await update_report(interaction.guild_id, summary, world_id, article_id, character_name,
                                                interaction.user.name)
                            await interaction.followup.send(f"Report has been updated for {session_name}!")
        except aiosqlite.Error as e:
            logging.exception(f"Failed to update report for session {session_id}: {e}")
            await interaction.followup.send(f"Failed to update report for session {session_id}")

    @group_group.command(name='create', description='create your group')
    @app_commands.autocomplete(character_name=own_character_select_autocompletion)
    async def create_group(self, interaction: discord.Interaction, character_name: str, group_name: str,
                           description: str):
        """Open a session Request"""
        await interaction.response.defer(thinking=True, ephemeral=False)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute("Select Group_ID, Role_ID from Sessions_Group where Player_Name = ?",
                                     (interaction.user.name,))
                group = await cursor.fetchone()
                await cursor.execute("Select Group_ID, Role_ID from Sessions_Group where Group_Name = ?",
                                     (group_name,))
                taken = await cursor.fetchone()
                if not group and not taken:
                    new_role = await create_new_group(interaction.guild, interaction.user.name, interaction.user.id,
                                                      group_name,
                                                      character_name, description)
                    await interaction.followup.send(
                        f"Group {group_name} has been created with the role <@&{new_role.id}>!")
                elif taken:
                    generated_name = random_name()
                    random_number = random.randint(0, 1000)
                    await interaction.followup.send(
                        f"Group name is taken :( Why don't you try {generated_name}{random_number}.")
                else:
                    await interaction.followup.send(
                        f"You already have a group request open! Please close it before opening another.")
        except (aiosqlite.Error, TypeError) as e:
            logging.exception(f"Failed to add a session request for {interaction.user.name}: {e}")
            await interaction.followup.send(f"Failed to add a session request for {interaction.user.name}")

    @group_group.command(name='delete', description='delete your group')
    async def delete_group(self, interaction: discord.Interaction):
        """Delete a session Request"""
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute("Select Group_ID, Role_ID from Sessions_Group where Player_Name = ?",
                                     (interaction.user.name,))
                group = await cursor.fetchone()
                if group:
                    await delete_group(interaction.guild, group[0], group[1])
                    await interaction.followup.send(f"Group {group[0]} has been deleted!")
                else:
                    await interaction.followup.send(f"Couldn't find any groups associated with {interaction.user}!")
        except (aiosqlite.Error, TypeError) as e:
            logging.exception(f"Failed to add a session request for {interaction.user.name}: {e}")
            await interaction.followup.send(f"Failed to add a session request for {interaction.user.name}")

    @group_group.command(name='join', description='Join a group')
    @app_commands.autocomplete(group_id=group_id_autocompletion)
    async def group_join(self, interaction: discord.Interaction, group_id: int):
        """Sync your Groups up for a GM to view whose in a session request group."""
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute("""
                Select
                SG.Group_Name, SG.Group_ID, SG.Role_ID, SG.Player_Name,
                PC.Player_ID 
                from Sessions_Group as SG 
                Left Join Player_Characters as PC 
                on SG.Player_Name = PC.Player_Name 
                where SG.Group_ID = ?
                """, (group_id,))
                group = await cursor.fetchone()
                if group:
                    (group_name, group_id, role_id, player_name, owner_id) = group
                    await cursor.execute(
                        "Select Group_ID, player_name from Sessions_Group_Presign where Group_ID = ? and Player_Name = ?",
                        (group_id, interaction.user.name))
                    previous_group = await cursor.fetchone()
                    if previous_group:
                        await interaction.followup.send(f"You have already joined group {group_id}!")
                    else:
                        await cursor.execute("SELECT Player_ID from Player_Characters WHERE Player_Name = ?", (interaction.user.name,))
                        player_id_info = await cursor.fetchone()
                        player_id = player_id_info[0]
                        view = GroupJoinView(
                            allowed_user_id=owner_id,
                            guild_id=interaction.guild.id,
                            group_id=group_id,
                            interaction=interaction,
                            bot=self.bot,
                            content=f"<@{owner_id}>\r\n<@{player_id}> has requested to join group {group_name}! Do you accept?",
                            group_name=group_name,
                            requester_name=interaction.user.name,
                            group_role_id=role_id
                        )
                        await view.send_initial_message()
                        await interaction.followup.send(
                            content=f"Group {group_name} has been requested to join by {interaction.user.name}!",
                            ephemeral=True)

                else:
                    await interaction.followup.send(f"Group {group_id} could not be found!")
        except (aiosqlite.Error, TypeError) as e:
            logging.exception(f"Failed to join a session request for {interaction.user.name}: {e}")
            await interaction.followup.send(
                f"Failed to Join a session request for {interaction.user.name} for group {group_id}")

    @group_group.command(name='leave', description='leave a group')
    @app_commands.autocomplete(group_id=group_id_autocompletion)
    async def group_leave(self, interaction: discord.Interaction, group_id: int):
        """leave a group because you hate everyone inside."""
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute("Select Group_ID, Role_ID from Sessions_Group where Group_ID = ?", (group_id,))
                group = await cursor.fetchone()
                if group:
                    await cursor.execute(
                        "Select Group_ID, player_name from Sessions_Group_Presign where Group_ID = ? and Player_Name = ?",
                        (group_id, interaction.user.name))
                    previous_group = await cursor.fetchone()
                    if previous_group:
                        try_leave = await leave_group(interaction.guild, interaction.user.name, interaction.user.id,
                                                      group_id, group[1])
                        if try_leave:
                            await interaction.followup.send(f"You have left group {group_id}!")
                        else:
                            await interaction.followup.send(f"Failed to leave group {group_id}!")
                    else:
                        await interaction.followup.send(f"You are not in group {group_id}!")
                else:
                    await interaction.followup.send(f"Group {group_id} could not be found!")
        except (aiosqlite.Error, TypeError) as e:
            logging.exception(f"Failed to add a session request for {interaction.user.name}: {e}")
            await interaction.followup.send(f"Failed to add a session request for {interaction.user.name}")

    @group_group.command(name='display', description='Display all participants and signups for a group!')
    @app_commands.autocomplete(group_id=group_id_autocompletion)
    async def display_groups(self, interaction: discord.Interaction, group_id: typing.Optional[int],
                             page_number: int = 1):
        """Display all participants and signups for a group"""
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild.id}.sqlite") as conn:
                cursor = await conn.cursor()
                if group_id is None:
                    await cursor.execute("SELECT COUNT(*) FROM sessions_group")
                    count = await cursor.fetchone()
                    max_items = count
                    if max_items == 0:
                        await interaction.followup.send("No groups found!")
                        return
                    else:
                        # Set up pagination variables
                        items_per_page = 20
                        page_number = min(max(page_number, 1), math.ceil(max_items[0] / 20))
                        offset = (page_number - 1) * items_per_page

                        # Create and send the view with the results
                        view = GroupView(
                            user_id=interaction.user.id,
                            guild_id=interaction.guild.id,
                            limit=items_per_page,
                            offset=offset,
                            interaction=interaction,
                            group_id=group_id
                        )
                        await view.send_initial_message()
                else:
                    await cursor.execute(
                        "SELECT Group_ID, Group_Name, Role_ID, Player_Name, Host_Character, Description FROM sessions_group WHERE Group_ID = ?",
                        (group_id,))
                    group_info = await cursor.fetchone()
                    if group_info is None:
                        await interaction.followup.send("No group found with that ID!")
                        return
                    else:
                        (group_id, group_name, role_id, player_name, host_character, description) = group_info
                        await cursor.execute("SELECT COUNT(*) FROM sessions_group_presign WHERE group_id = ?",
                                             (group_id,))
                        count = await cursor.fetchone()

                        max_items = count[0]
                        if max_items == 0:
                            await interaction.followup.send("No participants or signups found for this session!")
                            return
                        else:
                            # Set up pagination variables
                            items_per_page = 20
                            page_number = min(max(page_number, 1), math.ceil(max_items / 20))
                            offset = (page_number - 1) * items_per_page

                            # Create and send the view with the results
                            view = GroupManyView(
                                user_id=interaction.user.id,
                                guild_id=interaction.guild.id,
                                limit=items_per_page,
                                offset=offset,
                                interaction=interaction,
                                group_id=group_id,
                                group_name=group_name,
                                role_id=role_id,
                                host_player_name=player_name,
                                host_character=host_character,
                                description=description
                            )
                            await view.send_initial_message()
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"An error occurred whilst displaying session information: {e}")
            await interaction.followup.send(
                "An error occurred whilst displaying session information. Please try again later.")

    @timesheet_group.command(name="set", description="Set your availability for a day of the week")
    @app_commands.choices(change=[discord.app_commands.Choice(name='Add Time', value=1),
                                  discord.app_commands.Choice(name='Remove Time', value=2),
                                  discord.app_commands.Choice(name='Update Time-Zone', value=3),
                                  discord.app_commands.Choice(name='Clear All Availability', value=4)])
    async def timesheet_creation(self, interaction: discord.Interaction,
                                 change: typing.Optional[discord.app_commands.Choice[int]]):
        await interaction.response.defer(thinking=True, ephemeral=True)
        change_value = 1 if change is None else change.value
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild.id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute(
                    "SELECT Distinct(UTC_Offset), COUNT(*) FROM Player_Timecard WHERE Player_Name = ? Group by UTC_Offset",
                    (interaction.user.name,))
                timesheet_info = await cursor.fetchone()
                if change_value == 4:
                    # Clear all availability by deleting and remaking all timesheets
                    timesheet_clear = await clear_timesheet(interaction.guild.id, interaction.user.name)
                    if not timesheet_clear:
                        await interaction.followup.send(f"Failed to clear timesheet for {interaction.user.name}!")
                        return
                    timesheet_build = await build_timesheet(interaction.guild.id, interaction.user.name)
                    if not timesheet_build:
                        await interaction.followup.send(f"Failed to build timesheet for {interaction.user.name}!")
                        return
                    await interaction.followup.send(f"Timesheet has been cleared for {interaction.user.name}!")
                else:
                    if not timesheet_info:
                        # If the user has no timesheet, build one
                        await build_timesheet(interaction.guild.id, interaction.user.name)
                    elif timesheet_info[1] != 7:
                        # If the user has a timesheet, but it's somehow incomplete, delete and rebuild it
                        await clear_timesheet(interaction.guild.id, interaction.user.name)
                        await build_timesheet(interaction.guild.id, interaction.user.name)
                    if change_value == 3:
                        # If the user has no timezone set, or is updating their timezone, prompt them to set it
                        view = AvailabilityView(timezone=None, prompt_day_update=True)
                    elif change_value == 1 and not timesheet_info:
                        # If the user has no timezone set, prompt them to set it
                        view = AvailabilityView(timezone=None)
                    elif change_value == 1 and not timesheet_info[0]:
                        # If the user has no timezone set, prompt them to set it
                        view = AvailabilityView(timezone=None)
                    elif change_value == 1 and timesheet_info[0]:
                        # If the user has a timezone set, prompt them to set their availability
                        view = AvailabilityView(timezone=timesheet_info[0])
                    elif change_value == 2 and (not timesheet_info[0] or not timesheet_info):
                        await interaction.followup.send("You have no availability to remove!")
                        return
                    elif change_value == 2 and timesheet_info[0]:
                        view = UnavailabilityView(timezone=timesheet_info[0])

            await interaction.followup.send(content="Start by using the dropdown below!", view=view)
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"An error occurred whilst handling timesheet!: {e}")
            await interaction.followup.send(
                "An error occurred whilst handling timesheet. Please try again later.")

    @timesheet_group.command(name="timezone", description="Set your timezone for availability")
    @app_commands.autocomplete(timezone=search_timezones)
    async def set_timezone(self, interaction: discord.Interaction, timezone: str):
        """Set your timezone for availability"""
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild.id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute(
                    "SELECT Distinct(UTC_Offset), COUNT(*) FROM Player_Timecard WHERE Player_Name = ? Group by UTC_Offset",
                    (interaction.user.name,))
                timesheet_info = await cursor.fetchone()
                if not timesheet_info:
                    # If the user has no timesheet, build one
                    await build_timesheet(interaction.guild.id, interaction.user.name)
                elif timesheet_info[1] != 7:
                    # If the user has a timesheet, but it's somehow incomplete, delete and rebuild it
                    await clear_timesheet(interaction.guild.id, interaction.user.name)
                    await build_timesheet(interaction.guild.id, interaction.user.name)
                view = AvailabilityView(timezone=timezone, prompt_day_update=True)
                await interaction.followup.send(
                    content="Timezone has been manually set. Would you like to make any other changes?", view=view)
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"An error occurred whilst handling timesheet!: {e}")
            await interaction.followup.send(
                "An error occurred whilst handling timesheet. Please try again later.")

    @timesheet_group.command(name="availability", description="Display availability for a day of the week")
    @app_commands.choices(
        day=[discord.app_commands.Choice(name='Monday', value=1), discord.app_commands.Choice(name='Tuesday', value=2),
             discord.app_commands.Choice(name='Wednesday', value=3),
             discord.app_commands.Choice(name='Thursday', value=4),
             discord.app_commands.Choice(name='Friday', value=5), discord.app_commands.Choice(name='Saturday', value=6),
             discord.app_commands.Choice(name='Sunday', value=7)])
    async def availability(self, interaction: discord.Interaction, player: discord.Member,
                           day: discord.app_commands.Choice[int]):
        """Display historical Session Requests"""

        guild_id = interaction.guild.id
        day_value = day.value
        await interaction.response.defer(thinking=True, ephemeral=True)
        if day_value < 1 or day_value > 7:
            embed = discord.Embed(title=f"Day Error", description=f'{day} is not a valid day of the week!',
                                  colour=discord.Colour.red())
            await interaction.followup.send(embed=embed)
        else:
            player = interaction.user.name if player is None else player.name
            async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute("Select UTC_Offset from Player_Timecard where Player_Name = ?",
                                     (interaction.user.name,))
                host_utc_offset = await cursor.fetchone()
                await cursor.execute("Select UTC_Offset from Player_Timecard where Player_Name = ?", (player,))
                player_utc_offset = await cursor.fetchone()
                utc_offset = host_utc_offset[0] if host_utc_offset is not None else 'Universal'
                if player_utc_offset is not None:
                    await create_timecard_plot(guild_id, player, day_value, utc_offset)
                    with open('C:\\pathparser\\plots\\timecard_plot.png', 'rb') as f:
                        picture = discord.File(f)
                        await interaction.followup.send(
                            f"Here's the availability chart for {player} on {day.name}:",
                            file=picture)
                else:
                    embed = discord.Embed(title=f"Player Error",
                                          description=f'{player} did not have a valid timecard!!',
                                          colour=discord.Colour.red())
                    await interaction.followup.send(embed=embed)

    @timesheet_group.command(name="group",
                             description="Display availability for a group or groups on a day of the week")
    @app_commands.choices(
        day=[discord.app_commands.Choice(name='Monday', value=1), discord.app_commands.Choice(name='Tuesday', value=2),
             discord.app_commands.Choice(name='Wednesday', value=3),
             discord.app_commands.Choice(name='Thursday', value=4),
             discord.app_commands.Choice(name='Friday', value=5), discord.app_commands.Choice(name='Saturday', value=6),
             discord.app_commands.Choice(name='Sunday', value=7)])
    async def group_availability(self, interaction: discord.Interaction, group_id: typing.Optional[int],
                                 day: discord.app_commands.Choice[int]):
        """Display historical Session Requests"""
        guild_id = interaction.guild.id
        day_value = day.value
        try:
            await interaction.response.defer(thinking=True, ephemeral=True)
            if day_value < 1 or day_value > 7:
                embed = discord.Embed(title=f"Day Error", description=f'{day} is not a valid day of the week!',
                                      colour=discord.Colour.red())
                await interaction.followup.send(embed=embed)
            else:
                async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
                    cursor = await db.cursor()
                    await cursor.execute(
                        "Select UTC_Offset from Player_Timecard where Player_Name = ?",
                        (interaction.user.name,))
                    host_utc_offset = await cursor.fetchone()
                    view = DisplayGroupTimesheet(
                        guild_id=guild_id,
                        group_id=group_id,
                        day=day_value,
                        utc_offset=host_utc_offset[0],
                        interaction=interaction,
                        user_id=interaction.user.id)
                    await view.send_initial_message()
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"An error occurred whilst handling timesheet!: {e}")
            await interaction.followup.send(
                "An error occurred whilst handling timesheet. Please try again later.")


class GroupManyView(ShopView):
    def __init__(self, user_id: int, guild_id: int, offset: int, limit: int, group_id: typing.Optional[int],
                 group_name: str, host_player_name: str, host_character: str, description: str, role_id: int,
                 interaction: discord.Interaction):
        super().__init__(user_id=user_id, guild_id=guild_id, offset=offset, limit=limit, interaction=interaction,
                         content="")
        self.max_items = None  # Cache total number of items
        self.content = None
        self.group_id = group_id
        self.group_name = group_name
        self.host_player_name = host_player_name
        self.host_character = host_character
        self.description = description
        self.role_id = role_id

    async def update_results(self):
        """Fetch the history of prestige request  for the current page."""

        statement = """
                        SELECT Group_ID, Player_Name
                        FROM Sessions_Group_Presign
                        WHERE Group_ID = ? ORDER BY Player_Name Limit ? Offset ? 
                    """
        async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
            cursor = await db.execute(statement, (self.group_id, self.limit, self.offset))
            self.results = await cursor.fetchall()

    async def create_embed(self):
        """Create the embed for the titles."""
        current_page = (self.offset // self.limit) + 1
        total_pages = ((await self.get_max_items() - 1) // self.limit) + 1
        self.embed = discord.Embed(
            title=f"Group: {self.group_id}: {self.group_name} hosted by {self.host_player_name}'s {self.host_character}",
            description=f"Page {current_page} of {total_pages}")
        self.embed.set_footer(text=f"Group <@{self.role_id}> Description: {self.description}")
        for item in self.results:
            (group_id, player_name) = item
            self.embed.add_field(name=f'**Player**: {player_name}', value=f'**Group**: {group_id}', inline=False)

    async def get_max_items(self):
        """Get the total number of titles."""
        if self.max_items is None:
            async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
                cursor = await db.execute("SELECT COUNT(*) FROM Sessions_Group_Presign WHERE Group_ID = ?",
                                          (self.group_id,))
                count = await cursor.fetchone()
                self.max_items = count[0]
        return self.max_items


class GroupView(ShopView):
    def __init__(self, user_id: int, guild_id: int, offset: int, limit: int, group_id: typing.Optional[int],
                 interaction: discord.Interaction):
        super().__init__(user_id=user_id, guild_id=guild_id, offset=offset, limit=limit, interaction=interaction,
                         content=None)
        self.max_items = None  # Cache total number of items
        self.content = None
        self.group_id = group_id

    async def update_results(self):
        """Fetch the history of prestige request  for the current page."""

        statement = """
                        SELECT Group_ID, Group_Name, Role_ID, Player_Name, Host_Character, Description
                        FROM Sessions_Group Order by Group_ID Limit ? Offset ? 
                    """
        async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
            cursor = await db.execute(statement, (self.group_id, self.limit, self.offset))
            self.results = await cursor.fetchall()

    async def create_embed(self):
        """Create the embed for the titles."""
        current_page = (self.offset // self.limit) + 1
        total_pages = ((await self.get_max_items() - 1) // self.limit) + 1
        self.embed = discord.Embed(
            title=f"Group Requests",
            description=f"Page {current_page} of {total_pages}")
        for item in self.results:
            (group_id, group_name, role_id, host_player_name, host_character, description) = item
            self.embed.add_field(name=f'**Group**: {group_id}: {group_name} Role: <@{role_id}>',
                                 value=f'**Host**: {host_player_name}, **Character**: {host_character}\r\n**Description**: {description}',
                                 inline=False)

    async def get_max_items(self):
        """Get the total number of titles."""
        if self.max_items is None:
            async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
                cursor = await db.execute("SELECT COUNT(*) FROM Sessions_Group",
                                          (self.group_id,))
                count = await cursor.fetchone()
                self.max_items = count[0]
        return self.max_items


class DisplayGroupTimesheet(discord.ui.View):
    """Base class for shop views with pagination."""

    def __init__(
            self,
            user_id: int,
            guild_id: int,
            group_id: typing.Optional[int],
            day: int,
            utc_offset: str,
            interaction: discord.Interaction):
        super().__init__(timeout=180)
        self.range_id = None
        self.user_id = user_id
        self.guild_id = guild_id
        self.group_id = group_id
        self.day = day
        self.view_type = 1
        self.message = None
        self.interaction = interaction
        self.results = []
        self.host_results = []
        self.all_results = []
        self.embed = None
        self.max_range_id = 0
        self.utc_offset = utc_offset
        self.user_id = interaction.user.id

        # Initialize buttons
        self.first_page_button = discord.ui.Button(label='First Page', style=discord.ButtonStyle.primary)
        self.previous_page_button = discord.ui.Button(label='Previous Page', style=discord.ButtonStyle.primary)
        self.change_view_button = discord.ui.Button(label='Change View', style=discord.ButtonStyle.primary)
        self.next_page_button = discord.ui.Button(label='Next Page', style=discord.ButtonStyle.primary)
        self.last_page_button = discord.ui.Button(label='Last Page', style=discord.ButtonStyle.primary)

        self.first_page_button.callback = self.first_page
        self.previous_page_button.callback = self.previous_page
        self.change_view_button.callback = self.change_view
        self.next_page_button.callback = self.next_page
        self.last_page_button.callback = self.last_page

        self.add_item(self.first_page_button)
        self.add_item(self.previous_page_button)
        self.add_item(self.change_view_button)
        self.add_item(self.next_page_button)
        self.add_item(self.last_page_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Ensure that only the user who initiated the view can interact with the buttons."""
        try:
            if interaction.user.id != self.user_id:
                await interaction.response.send_message(
                    "You cannot interact with this button.",
                    ephemeral=True
                )
                return False
            return True
        except Exception as e:
            logging.error(f"Failed to check interaction: {e}")
            raise

    async def first_page(self, interaction: discord.Interaction):
        """Handle moving to the first page."""
        try:
            await interaction.response.defer()
            if self.view_type == 0:
                if self.day == 1:
                    await interaction.followup.send("You are on the first page.", ephemeral=True)
                    return
                else:
                    self.day = 1
            else:
                if self.range_id == 0:
                    await interaction.followup.send("You are on the first page.", ephemeral=True)
                    return
                else:
                    self.range_id = 0
            await self.update_results()
            await self.create_embed()
            await self.update_buttons()
            await interaction.message.edit(
                embed=self.embed,
                view=self
            )
            with open(f'C:\\pathparser\\pathparser\\plots\\timecard_{self.user_id}_plot.png', 'rb') as f:
                picture = discord.File(f)
                await interaction.followup.send(file=picture, ephemeral=True)
        except Exception as e:
            logging.error(f"Failed to move to the first page: {e}")
            raise

    async def previous_page(self, interaction: discord.Interaction):
        """Handle moving to the previous page."""
        try:
            await interaction.response.defer()
            if self.view_type == 0:
                if self.day == 1:
                    await interaction.followup.send("You are on the first page.", ephemeral=True)
                    return
                else:
                    self.day -= 1
            else:
                if self.range_id == 0:
                    await interaction.followup.send("You are on the first page.", ephemeral=True)
                    return
                else:
                    self.range_id -= 1
            await self.update_results()
            await self.create_embed()
            await self.update_buttons()
            await interaction.message.edit(
                embed=self.embed,
                view=self
            )
            with open(f'C:\\pathparser\\pathparser\\plots\\timecard_{self.user_id}_plot.png', 'rb') as f:
                picture = discord.File(f)
                await interaction.followup.send(file=picture, ephemeral=True)
        except Exception as e:
            logging.error(f"Failed to move to the previous page: {e}")
            raise

    async def send_initial_message(self):
        """Send the initial message with the view."""
        try:

            await self.update_results()
            await self.create_embed()
            await self.update_buttons()
            with open(f'C:\\pathparser\\pathparser\\plots\\timecard_{self.user_id}_plot.png', 'rb') as f:
                picture = discord.File(f)
            self.message = await self.interaction.followup.send(
                embed=self.embed,
                view=self, file=picture, ephemeral=True
            )

        except discord.HTTPException as e:
            logging.error(
                f"Failed to send message due to HTTPException: {e} in guild {self.interaction.guild.id} for {self.user_id}")
        except Exception as e:
            logging.error(f"Failed to send message: {e} in guild {self.interaction.guild.id} for {self.user_id}")

    async def on_timeout(self):
        """Disable buttons when the view times out."""
        try:
            os.remove(f'C:\\pathparser\\pathparser\\plots\\timecard_{self.user_id}_plot.png')
            for child in self.children:
                child.disabled = True
            if self.message:
                await self.message.edit(view=self)
        except Exception as e:
            logging.error(f"Failed to disable buttons: {e}")
            raise

    async def change_view(self, interaction: discord.Interaction):
        """Change the view type."""
        await interaction.response.defer()
        try:
            self.view_type = 1 if self.view_type == 0 else 0
            await self.update_results()
            await self.create_embed()
            await self.update_buttons()
            await interaction.message.edit(
                embed=self.embed,
                view=self
            )
        except Exception as e:
            logging.error(f"Failed to change view: {e}")
            raise

    async def next_page(self, interaction: discord.Interaction):
        """Handle moving to the next page."""
        try:
            await interaction.response.defer()
            if self.view_type == 0:
                if self.day == 7:
                    await interaction.followup.send("You are on the last page.", ephemeral=True)
                    return
                else:
                    self.day += 1
            else:
                if self.range_id == self.max_range_id:
                    await interaction.followup.send("You are on the first page.", ephemeral=True)
                    return
                else:
                    self.range_id += 1
            await self.update_results()
            await self.create_embed()
            await self.update_buttons()
            await interaction.message.edit(
                embed=self.embed,
                view=self
            )
            with open(f'C:\\pathparser\\plots\\timecard_{self.user_id}_plot.png', 'rb') as f:
                picture = discord.File(f)
                await interaction.followup.send(file=picture, ephemeral=True)
        except Exception as e:
            logging.error(f"Failed to move to the next page: {e}")
            raise

    async def last_page(self, interaction: discord.Interaction):
        """Handle moving to the last page."""
        try:
            await interaction.response.defer()
            if self.view_type == 0:
                if self.day == 7:
                    await interaction.followup.send("You are on the last page.", ephemeral=True)
                    return
                else:
                    self.day = 7
            else:
                if self.range_id == self.max_range_id:
                    await interaction.followup.send("You are on the first page.", ephemeral=True)
                    return
                else:
                    self.range_id = self.max_range_id
            await self.update_results()
            await self.create_embed()
            await self.update_buttons()
            await interaction.message.edit(
                embed=self.embed,
                view=self
            )
            with open(f'C:\\pathparser\\pathparser\\plots\\timecard_{self.user_id}_plot.png', 'rb') as f:
                picture = discord.File(f)
                await interaction.followup.send(file=picture, ephemeral=True)
        except Exception as e:
            logging.error(f"Failed to move to the last page: {e}")
            raise

    async def update_buttons(self):
        """Update the enabled/disabled state of buttons based on the current page."""
        try:

            await self.get_max_items()

            if self.view_type == 0:
                first_page = 1
                last_page = 7
            else:
                first_page = 0
                last_page = self.max_range_id

            self.first_page_button.disabled = first_page
            self.previous_page_button.disabled = first_page
            self.next_page_button.disabled = last_page
            self.last_page_button.disabled = last_page
        except Exception as e:
            logging.error(f"Failed to update buttons: {e}")
            raise

    async def update_results(self):
        """Fetch the results for the current page."""
        try:
            async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                # Fetch all group data
                await cursor.execute(
                    """SELECT Group_ID, Player_Name, Group_Name, Host_Character, Role_ID, Description 
                       FROM Sessions_Group 
                       ORDER BY Group_ID ASC"""
                )
                self.all_results = await cursor.fetchall()

                if self.group_id:
                    # Find the index of the group_id in the all_results list
                    self.range_id = next(
                        (index for index, row in enumerate(self.all_results) if row[0] == self.group_id),
                        None
                    )
                    if self.range_id is None:
                        raise ValueError(f"Group ID {self.group_id} not found in the results.")

                    self.host_results = self.all_results[self.range_id]
                    await cursor.execute(
                        """SELECT Player_Name FROM Sessions_Group_Presign WHERE Group_ID = ?""",
                        (self.group_id,)
                    )
                    self.results = await cursor.fetchall()
                else:
                    # Default to the first group
                    self.range_id = 0
                    self.host_results = self.all_results[self.range_id]
                    await cursor.execute(
                        """SELECT Player_Name FROM Sessions_Group_Presign WHERE Group_ID = ?""",
                        (self.host_results[0],)
                    )
                    self.results = await cursor.fetchall()
        except Exception as e:
            logging.error(f"Failed to update results: {e}")
            raise

    async def create_embed(self):
        """Create the embed for the current page. To be implemented in subclasses."""
        try:

            results_tuple = []
            for result in self.results:
                results_tuple.append(result[0])
            await create_timecard_group_plot(
                guild_id=self.guild_id,
                day=self.day,
                group_info=results_tuple,
                user_id=self.user_id,
                utc_offset=self.utc_offset,
                group_name=self.host_results[2]
            )
            (group_id, player_name, group_name, host_character, role_id, description) = self.host_results
            embed = discord.Embed(
                title=f"Group {group_id}: {group_name}",
                description=f"Hosted by {player_name}'s {host_character}",
                colour=discord.Colour.blurple()
            )
            embed.add_field(name=f"Group Description", value=f"{description}", inline=False)
            embed.set_footer(text=f"group {self.range_id + 1} of {self.max_range_id + 1}")
        except Exception as e:
            logging.error(f"Failed to create embed: {e}")

    async def get_max_items(self):
        """Get the total number of items. To be implemented in subclasses."""

        async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute("SELECT COUNT(*) FROM Sessions_Group""")
            count = await cursor.fetchone()

            self.max_range_id = count[0]
            return self.max_range_id




class GroupJoinView(RecipientAcknowledgementView):
    def __init__(
            self,
            allowed_user_id: int,
            requester_name: str,
            bot: commands.Bot,
            guild_id: int,
            interaction: discord.Interaction,
            group_id: int,
            group_name: str,
            group_role_id: int,
            content: str
    ):
        super().__init__(allowed_user_id=allowed_user_id, interaction=interaction, content=content)
        self.guild_id = guild_id
        self.requester_name = requester_name
        self.allowed_user_id = allowed_user_id
        self.bot = bot
        self.group_id = group_id
        self.group_name = group_name
        self.group_role_id = group_role_id
        self.interaction = interaction


    async def accepted(self, interaction: discord.Interaction):
        """Handle the approval logic."""
        # Update the database to mark the proposition as accepted
        # Adjust prestige, log the transaction, notify the requester, etc.
        self.embed = discord.Embed(
            title="Group Join Accepted!",
            description=f"<@{self.allowed_user_id}> has allowed <@{self.interaction.user.id}> to join their session!.",
            color=discord.Color.green()
        )
        # Additional logic such as notifying the requester
        async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as conn:
            cursor = await conn.cursor()
            await cursor.execute(
                "INSERT INTO Sessions_Group_Presign (Group_ID, Player_Name) VALUES (?, ?)",
                (self.group_id, self.interaction.user.name)
            )
            await conn.commit()
            group_role = interaction.guild.get_role(self.group_role_id)
            await self.interaction.user.add_roles(group_role)

    async def rejected(self, interaction: discord.Interaction):
        """Handle the rejection logic."""
        # Update the database to mark the proposition as rejected

        self.embed = discord.Embed(
            title="Group Application Rejected",
            description=f"The owner of this group did not desire you in their cohort.",
            color=discord.Color.red()
        )
        # Additional logic such as notifying the requester

    async def create_embed(self):
        """Create the initial embed for the proposition."""
        self.embed = discord.Embed(
            title=f"Group Join Request \r\nGroup Name: {self.group_name}",
            description=(
                f"**Requester:** {self.requester_name}\n"
            ),
            color=discord.Color.blue()
        )