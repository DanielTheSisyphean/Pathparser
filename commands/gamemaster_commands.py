import datetime
import logging
import math
import os
import random
import typing
from dataclasses import dataclass
from decimal import Decimal
from typing import List, Optional, Union
import aiosqlite
import discord
from discord import app_commands, Embed, TextChannel
from discord.ext import commands
from matplotlib import pyplot as plt

import commands.character_commands as character_commands
import commands.player_commands as player_commands
import shared_functions
from scheduler_utils import scheduled_jobs, remind_users, scheduler, schedule_session_reminders
from shared_functions import name_fix


async def create_group_timecard_plot(dataset, day, user_id):
    try:
        # Time intervals (x-axis)
        # Time intervals (x-axis)
        time_labels = [
            "00:00", "00:30", "01:00", "01:30", "02:00", "02:30", "03:00", "03:30",
            "04:00", "04:30", "05:00", "05:30", "06:00", "06:30", "07:00", "07:30",
            "08:00", "08:30", "09:00", "09:30", "10:00", "10:30", "11:00", "11:30",
            "12:00", "12:30", "13:00", "13:30", "14:00", "14:30", "15:00", "15:30",
            "16:00", "16:30", "17:00", "17:30", "18:00", "18:30", "19:00", "19:30",
            "20:00", "20:30", "21:00", "21:30", "22:00", "22:30", "23:00", "23:30"
        ]

        daysdict = {1: 'Monday', 2: 'Tuesday', 3: 'Wednesday', 4: 'Thursday', 5: 'Friday', 6: 'Saturday', 7: 'Sunday'}

        day = daysdict[day]

        # Prepare data
        group_numbers = []
        group_availability = []

        for entry in dataset:
            group_numbers.append(entry[0])  # First element is the group number
            group_availability.append([0 if x is None else x for x in entry[1:]])  # Replace None with 0 for plotting

        # Explicitly define x-axis indices for categorical data
        x_indices = range(len(time_labels))

        # Create the plot
        plt.figure(figsize=(10, 6))  # Adjust the figure size as needed

        # Iterate through each group and plot their availability
        for group_idx, group_data in enumerate(group_availability):
            group_name = f"Group {group_numbers[group_idx]}"
            plt.plot(x_indices, group_data, label=group_name)

        # Add labels and legend
        plt.title(f"Group Availability Throughout {day}")
        plt.xlabel("Time")
        plt.ylabel("Availability")
        plt.xticks(x_indices, time_labels, rotation=45, fontsize=8)  # Use x_indices for x-ticks
        plt.yticks(range(0, max(map(max, group_availability)) + 1))  # Adjust y-ticks dynamically
        plt.legend(title="Groups")
        plt.grid(True, linestyle='--', alpha=0.7)

        # Save the plot
        plt.savefig(f'C:\\pathparser\\plots\\group_{user_id}_plot.png')  # Ensure the path is correct for your system
        plt.close()

    except Exception as e:
        logging.exception(f"An error occurred while creating the group timecard plot: {e}")


async def session_reward_reversal(
        interaction: discord.Interaction,
        session_id: int,
        character_name: str,
        author_name: str,
        session_gold: Decimal,
        session_info: Union[tuple, aiosqlite.Row],
        source: str) -> (
        Union[tuple[shared_functions.CharacterChange, int], str]):

    if not session_info:
        return f'invalid session ID of {session_id}'

    else:
        async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as conn:
            cursor = await conn.cursor()

            try:
                (info_player_id, info_player_name, info_character_name, info_level, info_tier, info_effective_gold,
                 info_received_milestones, info_received_trials, info_received_gold, info_received_fame,
                 info_received_prestige, info_received_essence, info_transaction_id) = session_info

                await cursor.execute(
                    """SELECT 
                    True_Character_Name, Oath, Level, Personal_Cap, Tier, 
                    Milestones, Trials, Gold, Gold_Value, Gold_Value_Max, 
                    Essence, Fame, Prestige, Accepted_Date, Thread_ID, Region FROM Player_Characters WHERE Character_Name = ? OR Nickname = ? or True_Character_Name = ?""",
                    (character_name, character_name, character_name))
                player_info = await cursor.fetchone()

                if not player_info:
                    return f"there is no {character_name} registered."

                else:
                    (true_character_name, oath, level, personal_cap, tier,
                     milestones, trials, gold, gold_value, gold_value_max,
                     essence, fame, prestige, accepted_date, thread_id, region) = player_info

                    try:
                        return_level = await character_commands.level_calculation(
                            level=info_level,
                            guild=interaction.guild,
                            guild_id=interaction.guild.id,
                            base=milestones,
                            personal_cap=personal_cap,
                            easy=0,
                            medium=0,
                            hard=0,
                            deadly=0,
                            misc=-info_received_milestones,
                            author_id=interaction.user.id,
                            character_name=character_name,
                            region=region)

                    except character_commands.CalculationAidFunctionError as e:
                        return_level = f"An error occurred whilst adjusting levels for {character_name} \r\n"
                        logging.exception(f"Error in level calculation: {e}")
                    level_value = info_level if isinstance(return_level, str) else return_level[0]

                    try:
                        return_mythic = await character_commands.mythic_calculation(
                            character_name=character_name,
                            level=level_value,
                            trials=trials,
                            trial_change=-info_received_trials,
                            guild_id=interaction.guild.id,
                            tier=tier)
                        return_mythic = return_mythic if tier != return_mythic[
                            0] or info_received_trials != 0 else 0

                    except character_commands.CalculationAidFunctionError as e:
                        return_mythic = f"An error occurred whilst adjusting trials for {character_name} \r\n"
                        logging.exception(f"Error in Mythic calculation: {e}")

                    try:
                        return_gold = await character_commands.gold_calculation(
                            guild_id=interaction.guild.id,
                            character_name=character_name,
                            level=level_value,
                            oath=oath,
                            gold=Decimal(gold),
                            author_name=interaction.user.name,
                            author_id=interaction.user.id,
                            gold_value=Decimal(gold_value),
                            gold_value_max=Decimal(gold_value_max),
                            gold_change=-Decimal(info_received_gold),
                            gold_value_change=None,
                            gold_value_max_change=-Decimal(session_gold),
                            reason='Session Back out',
                            source=source
                        )

                    except character_commands.CalculationAidFunctionError as e:
                        return_gold = f"An error occurred whilst adjusting gold for {character_name} \r\n"
                        logging.exception(f"Error in gold calculation: {e}")

                    try:
                        return_essence = character_commands.calculate_essence(
                            character_name=character_name,
                            essence=essence,
                            essence_change=-info_received_essence,
                            accepted_date=accepted_date)

                    except character_commands.CalculationAidFunctionError as e:
                        return_essence = f"An error occurred whilst adjusting essence for {character_name} \r\n"
                        logging.exception(f"Error in essence calculation: {e}")

                    if isinstance(return_level, tuple) and \
                            (isinstance(return_mythic, tuple) or isinstance(return_mythic, int)) and \
                            isinstance(return_gold, tuple) and \
                            isinstance(return_essence, tuple):

                        await cursor.execute("DELETE FROM Sessions_Archive WHERE Session_ID = ? AND Character_Name = ?",
                                             (session_id, character_name))
                        await conn.commit()

                    return_fame = (fame - info_received_fame, -info_received_fame, prestige - info_received_prestige,
                                   -info_received_prestige)
                    character_updates = shared_functions.UpdateCharacterData(character_name=character_name)

                    character_changes = shared_functions.CharacterChange(
                        character_name=character_name,
                        author=interaction.user.name,
                        source=source)

                    if isinstance(return_level, tuple):
                        (new_level,
                         total_milestones,
                         min_milestones,
                         milestones_to_level,
                         milestones_required,
                         awarded_total_milestones) = return_level
                        character_updates.level_package = (new_level, total_milestones, min_milestones)
                        character_changes.level = new_level
                        character_changes.milestones_total = total_milestones
                        character_changes.milestones_remaining = min_milestones
                        character_changes.milestone_change = awarded_total_milestones

                    if isinstance(return_mythic, tuple):
                        (new_tier, total_trials, trials_required, trial_change) = return_mythic
                        character_updates.trial_package = (new_tier, total_trials, trials_required)
                        character_changes.tier = new_tier
                        character_changes.trials = total_trials
                        character_changes.trials_remaining = trials_required
                        character_changes.trial_change = trial_change

                    if isinstance(return_gold, tuple):
                        (calculated_difference, gold_total, gold_value_total, gold_value_max_total,
                         transaction_id) = return_gold
                        character_updates.gold_package = (gold_total, gold_value_total, gold_value_max_total)
                        character_changes.gold = gold_total
                        character_changes.gold_change = calculated_difference
                        character_changes.effective_gold = gold_value_total
                        character_changes.effective_gold_max = gold_value_max_total
                        character_changes.transaction_id = transaction_id

                    if isinstance(return_essence, tuple):
                        (essence_total, essence_change) = return_essence
                        character_updates.essence_package = essence_total
                        character_changes.essence = essence_total
                        character_changes.essence_change = essence_change

                    if isinstance(return_fame, tuple):
                        (fame, fame_change, prestige, prestige_change) = return_fame
                        character_updates.fame_package = (fame, prestige)
                        character_changes.fame = fame
                        character_changes.fame_change = fame_change
                        character_changes.prestige = prestige
                        character_changes.prestige_change = prestige_change

                    await shared_functions.update_character(
                        guild_id=interaction.guild.id,
                        change=character_updates)
                    return character_changes, thread_id

            except (aiosqlite.Error, TypeError, ValueError) as e:
                logging.exception(
                    f"an error occurred for {author_name} whilst reversing session rewards with ID {session_id} for character {character_name}': {e}")

                return f"An error occurred whilst adjusting session with ID '{session_id}' for {character_name} Error: {e}."


@dataclass
class RewardSessionBaseInfo:
    gm_name: str
    session_name: str
    rewarded_gold: Decimal
    rewarded_essence: int
    rewarded_easy: int
    rewarded_medium: int
    rewarded_hard: int
    rewarded_deadly: int
    rewarded_trials: int
    rewarded_fame: int
    rewarded_prestige: int
    rewarded_alt_reward_all: typing.Optional[str]
    rewarded_alt_reward_party: typing.Optional[str]
    rewarded_session_thread: typing.Optional[int]
    rewarded_message: typing.Optional[int]


async def session_reward_calculation(
        interaction: discord.Interaction, session_id: int,
        session_base_info: RewardSessionBaseInfo,
        character_name: str, author_name: str, pre_session_level: int,
        pre_session_tier: int, pre_session_gold, source: str) -> (
        Union[tuple[shared_functions.CharacterChange, int], str]):
    try:
        async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as conn:
            cursor = await conn.cursor()

            await cursor.execute(
                "SELECT Player_ID, player_name, True_Character_Name, Oath, Level, Tier, Milestones, Trials, Gold, Gold_Value, Gold_Value_Max, Essence, Thread_ID, Accepted_Date, Fame, Prestige, Personal_Cap, Thread_ID, Region FROM Player_Characters WHERE Character_Name = ? OR Nickname = ? or True_Character_Name = ?",
                (character_name, character_name, character_name))
            player_info = await cursor.fetchone()

            if not player_info:
                return f"there is no {character_name} registered."

            else:
                (player_id, player_name, true_character_name, oath, character_level, character_tier, milestones, trials,
                 gold, gold_value, gold_value_max,
                 essence, thread_id, accepted_date, fame, prestige, personal_cap, thread_id, region) = player_info

                try:
                    return_level = await character_commands.level_calculation(
                        level=pre_session_level,
                        guild=interaction.guild,
                        guild_id=interaction.guild.id,
                        personal_cap=personal_cap,
                        base=milestones,
                        easy=session_base_info.rewarded_easy,
                        medium=session_base_info.rewarded_medium,
                        hard=session_base_info.rewarded_hard,
                        deadly=session_base_info.rewarded_deadly,
                        misc=0,
                        author_id=interaction.user.id,
                        character_name=character_name,
                        region=region)

                except character_commands.CalculationAidFunctionError as e:
                    return_level = f"An error occurred whilst adjusting levels for {character_name} \r\n"
                    logging.exception(f"Error in level calculation: {e}")
                level_value = pre_session_level if isinstance(return_level, str) else return_level[0]

                try:
                    return_mythic = await character_commands.mythic_calculation(
                        guild_id=interaction.guild.id,
                        character_name=character_name,
                        level=level_value,
                        trials=trials,
                        trial_change=session_base_info.rewarded_trials,
                        tier=pre_session_tier)

                except character_commands.CalculationAidFunctionError as e:
                    return_mythic = f"An error occurred whilst adjusting trials for {character_name} \r\n"
                    logging.exception(f"Error in mythic calculation: {e}")

                try:
                    return_gold = await character_commands.gold_calculation(
                        guild_id=interaction.guild_id,
                        character_name=character_name,
                        level=level_value,
                        oath=oath,
                        gold=Decimal(gold),
                        gold_value=Decimal(gold_value),
                        gold_value_max=Decimal(gold_value_max),
                        gold_change=Decimal(session_base_info.rewarded_gold),
                        gold_value_change=None,
                        gold_value_max_change=None,
                        author_name=author_name,
                        author_id=interaction.user.id,
                        reason='Session Reward',
                        source=source)

                except character_commands.CalculationAidFunctionError as e:
                    return_gold = f"An error occurred whilst adjusting gold for {character_name} \r\n"
                    logging.exception(f"Error in gold calculation: {e}")

                try:
                    return_essence = character_commands.calculate_essence(
                        character_name=character_name,
                        essence=essence,
                        essence_change=session_base_info.rewarded_essence,
                        accepted_date=accepted_date)

                except character_commands.CalculationAidFunctionError as e:
                    return_essence = f"An error occurred whilst adjusting essence for {character_name} \r\n"
                    logging.exception(f"Error in essence calculation: {e}")

                return_fame = character_commands.calculate_fame(
                    character_name=character_name,
                    fame=fame,
                    fame_change=session_base_info.rewarded_fame,
                    prestige=prestige,
                    prestige_change=session_base_info.rewarded_prestige,
                )

                character_updates = shared_functions.UpdateCharacterData(character_name=character_name)
                character_changes = shared_functions.CharacterChange(
                    character_name=character_name,
                    author=interaction.user.name,
                    source=source)

                if isinstance(return_level, tuple):
                    (
                        new_level,
                        total_milestones,
                        min_milestones,
                        milestones_to_level,
                        milestones_required,
                        awarded_total_milestones) = return_level

                    character_updates.level_package = (new_level, total_milestones, min_milestones)
                    character_changes.level = new_level
                    character_changes.milestones_total = total_milestones
                    character_changes.milestones_remaining = min_milestones
                    character_changes.milestone_change = awarded_total_milestones

                else:
                    awarded_total_milestones = None

                if isinstance(return_mythic, tuple):
                    (new_tier, total_trials, trials_required, trial_change) = return_mythic
                    new_tier = 1 if new_tier == 0 else new_tier
                    character_updates.mythic_package = (new_tier, total_trials, trials_required)

                    if new_tier != pre_session_tier:
                        character_changes.tier = new_tier
                        character_changes.trials = total_trials
                        character_changes.trials_remaining = trials_required
                        character_changes.trial_change = trial_change

                else:
                    trial_change = None

                if isinstance(return_gold, tuple):
                    (calculated_difference, gold_total, gold_value_total, gold_value_max_total,
                     transaction_id) = return_gold
                    character_updates.gold_package = (gold_total, gold_value_total, gold_value_max_total)
                    character_changes.gold = gold_total
                    character_changes.gold_change = calculated_difference
                    character_changes.gold_value = gold_value_total
                    character_changes.gold_value_max = gold_value_max_total
                    character_changes.transaction_id = transaction_id

                else:
                    transaction_id = None

                if isinstance(return_essence, tuple):
                    (essence_total, essence_change) = return_essence
                    character_updates.essence = essence_total
                    character_changes.essence = essence_total
                    character_changes.essence_change = essence_change

                else:
                    essence_change = None

                if isinstance(return_fame, tuple):
                    (fame, fame_change, prestige, prestige_change) = return_fame
                    character_updates.fame_package = (fame, prestige)

                    character_changes.fame = fame
                    character_changes.fame_change = fame_change
                    character_changes.prestige = prestige
                    character_changes.prestige_change = prestige_change

                else:
                    fame_change = None
                    prestige_change = None
                await shared_functions.update_character(
                    guild_id=interaction.guild.id,
                    change=character_updates)

                await cursor.execute(
                    "insert into Sessions_Archive (Session_ID, PLayer_Name, Player_ID, Character_Name, Level, Tier, "
                    "Effective_Gold, Received_Milestones, Received_Trials, Received_Gold, Received_Fame, "
                    "Received_Prestige, Received_Essence, Gold_Transaction_ID) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (session_id, player_name, player_id, character_name, pre_session_level, pre_session_tier, str(pre_session_gold),
                     awarded_total_milestones, trial_change, str(calculated_difference),
                     fame_change, prestige_change, essence_change, transaction_id))
                await conn.commit()
                return character_changes, thread_id

    except (aiosqlite.Error, TypeError, ValueError) as e:
        logging.exception(
            f"an error occurred for {author_name} whilst rewarding session with ID {session_id} for character {character_name}': {e}")


def clear_session_reminders(session_id: int, start_time: str, jobs_to_schedule: scheduled_jobs):
    now = datetime.datetime.now(datetime.timezone.utc)
    session_start_time = shared_functions.parse_hammer_time_to_iso(start_time)
    time_difference = session_start_time - now
    remaining_minutes = time_difference.total_seconds() / 60
    reminder_time_periods = [0, 30, 60]

    for time in reminder_time_periods:
        if remaining_minutes >= time:
            job_key = (session_id, time)
            job = jobs_to_schedule.get(job_key)

            if job:
                job.remove()
                del jobs_to_schedule[job_key]
                logging.info(f"Canceled reminder for session {session_id} with offset {time} minutes.")

            else:
                logging.info(f"No active reminder found for session {session_id} with offset {time}")


@dataclass
class SessionBaseInfo:
    guild_id: int
    gm_name: str
    session_name: str
    session_range: str
    session_range_id: int
    player_limit: int
    hammer_time: Union[int, str]
    overflow: int
    play_location: str
    hammer_time: str
    game_link: str
    overview: str
    description: str
    plot: str
    region: int


async def create_session(
        session_info: SessionBaseInfo) -> int:
    try:

        async with aiosqlite.connect(f"pathparser_{session_info.guild_id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute(
                f"""INSERT INTO Sessions (
                GM_Name, Session_Name, 
                Session_Range, Session_Range_ID, Player_Limit, 
                Play_Location, hammer_time, game_link, 
                Overview, Description, Related_Plot,  
                Overflow, IsActive) VALUES (
                ?, ?, 
                ?, ?, ?, 
                ?, ?, ?, 
                ?, ?, ?,
                ?, ?)""",
                (
                    session_info.gm_name, session_info.session_name,
                    session_info.session_range, session_info.session_range_id, session_info.player_limit,
                    session_info.play_location, session_info.hammer_time, session_info.game_link,
                    session_info.overview, session_info.description, session_info.plot,
                    session_info.overflow, 1))
            await db.commit()

            await cursor.execute(
                "SELECT Session_ID from Sessions WHERE Session_Name = ? AND GM_Name = ? ORDER BY Session_ID Desc Limit 1",
                (session_info.session_name, session_info.gm_name))
            session_id = await cursor.fetchone()
            return session_id[0]

    except (aiosqlite, TypeError, ValueError) as e:
        logging.exception(f"An error occurred whilst creating a session: {e}")
        return 0


async def build_edit_info(
        gm_name: str,
        guild_id: int,
        session_id: int
) -> Optional[tuple[SessionBaseInfo, int, int]]:
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()

            await cursor.execute(
                "SELECT Session_Name, Session_Range, Session_Range_ID, Player_Limit, Play_Location, hammer_time, game_link, Overview, Description, Related_Plot, Overflow, Message, Session_Thread, Region FROM Sessions WHERE Session_ID = ? AND GM_Name = ? AND IsActive = 1 Limit 1",
                (session_id, gm_name))
            session_info = await cursor.fetchone()

            if session_info:
                (session_name, session_range, session_range_id, player_limit, play_location, hammer_time, game_link,
                 overview, description, plot, overflow, message, session_thread, region) = session_info

                built_session_info = SessionBaseInfo(
                    guild_id=guild_id,
                    gm_name=gm_name,
                    session_name=session_name,
                    session_range=session_range,
                    session_range_id=session_range_id,
                    player_limit=player_limit,
                    hammer_time=hammer_time,
                    play_location=play_location,
                    game_link=game_link,
                    overview=overview,
                    description=description,
                    plot=plot,
                    overflow=overflow,
                    region=region)

                return built_session_info, message, session_thread

            else:
                return None

    except (aiosqlite, TypeError, ValueError) as e:
        logging.exception(f"An error occurred whilst building session info for editing: {e}")
        return None


async def edit_session(
        session_info: SessionBaseInfo, session_id: int) -> bool:  # Overview, description
    try:
        async with aiosqlite.connect(f"pathparser_{session_info.guild_id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute(
                "UPDATE Sessions SET Session_Name = ?, Session_Range = ?, Session_Range_ID = ?, Play_Location = ?, hammer_time = ?, game_link = ?, Overview = ?, Description = ?, Player_Limit = ?, Related_plot = ?, overflow = ?, region = ? WHERE Session_ID = ?",
                (session_info.session_name, session_info.session_range, session_info.session_range_id,
                 session_info.play_location, session_info.hammer_time, session_info.game_link, session_info.overview,
                 session_info.description, session_info.player_limit, session_info.plot, session_info.overflow, session_info.region,
                 session_id))
            await db.commit()

            return True

    except (aiosqlite, TypeError, ValueError) as e:
        logging.exception(f"An error occurred whilst creating a session: {e}")
        return False


async def delete_session(
        session_id: int,
        guild_id: int) -> None:
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()

            await cursor.execute("UPDATE Sessions SET IsActive = 0 WHERE Session_ID = ?", (session_id,))
            await db.commit()

    except (aiosqlite, TypeError, ValueError) as e:
        logging.exception(f"An error occurred whilst deleting a session: {e}")
        raise e


async def validate_milestone_system_overflow(
        guild: discord.Guild,
        session_range_id: int,
        overflow: int) -> Union[tuple[discord.Role, int, int], None]:
    try:
        async with aiosqlite.connect(f"pathparser_{guild.id}.sqlite") as db:
            cursor = await db.cursor()
            # overflow 1 is current range only, 2 includes next level bracket, 3 includes lower level bracket, 4 ignores role requirements

            if overflow == 1:
                return None

            elif overflow == 2:
                await cursor.execute(
                    "SELECT min(level), max(level) FROM Milestone_System WHERE Level_range_ID = ?",
                    (session_range_id,))
                session_range_info = await cursor.fetchone()
                (min_level, max_level) = session_range_info
                if min_level or max_level:
                    await cursor.execute(
                        "SELECT level_range_id FROM Milestone_System WHERE level = ?",
                        (session_range_info[1] + 1,))
                    overflow_range_id = await cursor.fetchone()
                    await cursor.execute(
                        "SELECT Min(level), Max(level) FROM Milestone_System WHERE level_range_id = ?", (overflow_range_id[0],))
                    overflow_range_info = await cursor.fetchone()
                    session_range = guild.get_role(overflow_range_id[0])

                    if session_range is not None:
                        return session_range, min(overflow_range_info[0], session_range_info[0]) , max(overflow_range_info[1], session_range_info[1])

                    else:
                        return None

                else:
                    return None

            elif overflow == 3:
                await cursor.execute(
                    "SELECT min(level), max(level) FROM Milestone_System WHERE level_range_id = ?",
                    (session_range_id,))
                session_range_info = await cursor.fetchone()

                if session_range_info[0] is not None:
                    await cursor.execute(
                        "SELECT Role_ID FROM Level_Range WHERE level = ?",
                        (session_range_info[0] - 1,))
                    overflow_range_id = await cursor.fetchone()
                    await cursor.execute(
                        "SELECT Min(level), Max(level) FROM Milestone_System WHERE level_range_id = ?", (overflow_range_id[0],))
                    overflow_range_info = await cursor.fetchone()
                    session_range = guild.get_role(overflow_range_id[0])

                    if session_range is not None:
                        return session_range, min(overflow_range_info[0], session_range_info[0]), max(overflow_range_info[1], session_range_info[1])

                    else:
                        return None

                else:
                    return None

            else:
                return None

    except (TypeError, ValueError) as e:
        logging.exception(f"An error occurred whilst validating a level range: {e}")
        return None

    except discord.DiscordException as e:
        logging.exception(f"An error occurred whilst attempting to fetch the level range: {e}")

async def validate_region_system_overflow(
        guild: discord.Guild,
        session_range_id: int,
        overflow: int) -> Union[tuple[discord.Role, int, int], None]:
    try:
        async with aiosqlite.connect(f"pathparser_{guild.id}.sqlite") as db:
            cursor = await db.cursor()
            # overflow 1 is current range only, 2 includes next level bracket, 3 includes lower level bracket, 4 ignores role requirements

            if overflow == 1:
                return None

            elif overflow == 2:
                await cursor.execute(
                    "SELECT Min_level, Max_Level, Name FROM Regions_Level_Range WHERE Role_ID = ?",
                    (session_range_id,))
                session_range_info = await cursor.fetchone()

                if session_range_info is not None:
                    (min_level, max_level, region) = session_range_info
                    await cursor.execute(
                        "SELECT Role_ID, min_level, max_level FROM Regions_Level_Range WHERE Min_Level = ? And Name = ?",
                        (max_level + 1, region))
                    overflow_range_id = await cursor.fetchone()

                    session_range = guild.get_role(overflow_range_id[0])

                    if session_range is not None:
                        return session_range, min(min_level, overflow_range_id[1]), max(max_level, overflow_range_id[2])

                    else:
                        return None

                else:
                    return None

            elif overflow == 3:
                await cursor.execute(
                    "SELECT min_level, max_level, name FROM Regions_Level_Range WHERE Role_ID = ?",
                    (session_range_id,))
                session_range_info = await cursor.fetchone()

                if session_range_info is not None:
                    (min_level, max_level, region) = session_range_info
                    await cursor.execute(
                        "SELECT Role_ID, Min_level, Max_Level FROM Regions_Level_Range WHERE max_level = ? and name = ?", (min_level - 1, region))
                    overflow_range_id = await cursor.fetchone()

                    session_range = guild.get_role(overflow_range_id[0])

                    if session_range is not None:
                        return session_range, min(min_level, overflow_range_id[1]), max(max_level, overflow_range_id[2])

                    else:
                        return None

                else:
                    return None

            else:
                return None

    except (TypeError, ValueError) as e:
        logging.exception(f"An error occurred whilst validating a level range: {e}")
        return None

    except discord.DiscordException as e:
        logging.exception(f"An error occurred whilst attempting to fetch the level range: {e}")



@dataclass
class SessionEmbedInfo:
    guild: discord.Guild
    gm_name: str
    session_name: str
    session_range: str
    group_range: typing.Optional[str]
    player_limit: int
    hammer_time: str
    play_location: str
    hammer_time: str
    game_link: typing.Optional[str]
    overview: str
    description: str
    session_id: int


async def create_session_embed(embed_info: SessionEmbedInfo) -> Union[tuple[Embed, TextChannel], tuple[None, str]]:
    try:
        embed = discord.Embed(
            title=f"{embed_info.session_name}",
            description=f"Play Location: {embed_info.play_location}", color=discord.Colour.blue())

        if embed_info.game_link:
            embed.url = embed_info.game_link

        embed.add_field(name="Session Range", value=embed_info.session_range)
        embed.add_field(name="Player Limit", value=embed_info.player_limit)
        embed.add_field(name="Date & Time:", value=embed_info.hammer_time, inline=False)
        embed.add_field(name="Overview:", value=embed_info.overview, inline=False)
        embed.add_field(name="Description:", value=embed_info.description, inline=False)
        embed.set_footer(text=f'Session ID: {embed_info.session_id}.')
        print("getting configuration", type(embed_info.guild.id), embed_info.guild.id)
        async with shared_functions.config_cache.lock:
            print(shared_functions.config_cache.cache)
            configs = shared_functions.config_cache.cache.get(embed_info.guild.id)
            print(configs)
            if configs:
                session_channel_info = configs.get('Sessions_Channel')
            else:
                await shared_functions.add_guild_to_cache(embed_info.guild.id)
                configs = shared_functions.config_cache.cache.get(embed_info.guild.id)
                print(configs)
                if configs:
                    session_channel_info = configs.get('Sessions_Channel')

        session_channel = embed_info.guild.get_channel(session_channel_info)

        if not session_channel:
            session_channel = await embed_info.guild.fetch_channel(session_channel_info)

        if session_channel:
            return embed, session_channel

        else:
            return None, "Session channel not found!"

    except (discord.DiscordException, TypeError, ValueError) as e:
        logging.exception(f"An error occurred whilst creating a session embed: {e}")

        return None, f"An error occurred whilst creating a session embed: {e}"


async def player_signup(guild_id: int, session_name: str, session_id: int, character_name: str,
                        warning_duration: typing.Optional[int]) -> bool:
    warning_duration = -1 if warning_duration is None else warning_duration
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()

            await cursor.execute(
                """INSERT INTO Sessions_Participants (Session_ID, Session_Name, Player_Name, Player_ID, Character_Name, Level, Gold_Value, Tier, Notification_Warning) 
                SELECT ?, ?, Player_Name, Player_ID, ?, Level, Gold_Value, Tier, ? FROM Player_Characters WHERE Character_Name = ?""",
                (session_id, session_name, character_name, warning_duration, character_name))
            await db.commit()

            return True

    except aiosqlite.Error as e:
        logging.exception(
            f"Failed to sign up character {character_name} for session {session_name} ({session_id}): {e}")


async def player_accept(guild_id: int, session_name, session_id: int, player_id: int) -> bool:
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()

            updated = await cursor.execute(
                """insert into Sessions_participants(Session_Name, Session_ID, Player_Name, Player_ID, Character_Name, Level, Effective_Wealth, Tier, Notification_Warning) 
                select ?, ?, Player_Name, Player_ID, Character_Name, Level, Effective_Wealth, Tier, Notification_Warning from Sessions_Signups where Player_ID = ? and Session_ID = ?""",
                (session_name, session_id, player_id, session_id))
            await db.commit()

            await cursor.execute(
                "DELETE from Sessions_Signups where Player_ID = ? and Session_ID = ?",
                (player_id, session_id))
            await db.commit()

            return True if updated else False

    except (aiosqlite.Error, TypeError) as e:
        logging.info(f"Failed to sign up player {player_id} for session {session_id}: {e}.")
        return False

async def player_accept_specific(guild_id: int, session_name: str, session_id: int, character_name: str) -> bool:
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()

            updated = await cursor.execute(
                """insert into Sessions_participants(Session_Name, Session_ID, Player_Name, Player_ID, Character_Name, Level, Effective_Wealth, Tier, Notification_Warning) 
                select ?, ?, Player_Name, Player_ID, Character_Name, Level, Gold_Value, Tier, 0 from Player_Characters where Character_Name = ?""",
                (session_name, session_id, character_name))
            await db.commit()

            await cursor.execute(
                "DELETE from Sessions_Signups where Character_Name = ? and Session_ID = ?",
                (character_name,session_id))
            await db.commit()

            return True if updated else False

    except (aiosqlite.Error, TypeError) as e:
        logging.info(f"Failed to sign up player {character_name} for session {session_id}: {e}.")
        return False


class GamemasterCommands(commands.Cog, name='Gamemaster'):
    def __init__(self, bot):
        self.bot = bot

    gamemaster_group = discord.app_commands.Group(
        name='gamemaster',
        description='Commands related to GMing'
    )

    fame_group = discord.app_commands.Group(
        name='fame',
        description='Commands related to games mastering fame.',
        parent=gamemaster_group
    )

    session_group = discord.app_commands.Group(
        name='session',
        description='Commands related to games mastering sessions.',
        parent=gamemaster_group
    )

    worldanvil_group = discord.app_commands.Group(
        name='worldanvil',
        description='Commands related to handling player groups.',
        parent=gamemaster_group
    )

    group_group = discord.app_commands.Group(
        name='group',
        description='Commands related to handling player groups.',
        parent=gamemaster_group
    )

    @gamemaster_group.command(name='help', description='Help commands for the associated tree')
    async def help(self, interaction: discord.Interaction):
        """Help commands for the associated tree"""
        await interaction.response.defer(thinking=True, ephemeral=True)
        embed = discord.Embed(
            title=f"Gamemaster Help",
            description=f'This is a list of GM administrative commands',
            colour=discord.Colour.blurple())

        embed.add_field(
            name=f'__**Fame Commands**__',
            value="""
            Commands for managing character fame and prestige! \r\n
            **/Gamemaster Fame Manage** - Manage a character's fame and prestige! \n
            **/Gamemaster Fame Requests** - Accept or reject a request that has timed out! \n
            """, inline=False)
        embed.add_field(
            name="__**Group Commands**__",
            value="""
            Commands for managing player groups! \r\n
            **/Gamemaster Group Display** - Display the general availability of a group. \n
            **/Gamemaster Group Delete** - Delete a group whom you are done questing for.  \n
            """, inline=False)
        embed.add_field(
            name='__**Session Commands**__',
            value="""
            Commands for managing sessions! \r\n
            **/Gamemaster Session Accept** - Accept a character into your session group! \n
            **/Gamemaster Session Create** - Create a session! \n
            **/Gamemaster Session Claim** - Claim a completed session! \n
            **/Gamemaster Session Delete** - Cancel a session! \n
            **/Gamemaster Session Display** - Display the participants and signups for your quest! \n
            **/Gamemaster Session Edit** - Edit the session information! \n
            **/gamemaster Session Endow** - Endow individual players with rewards! \n
            **/Gamemaster Session Notify** - Notify Players of a quest! \n
            **/Gamemaster Session Remove** - Remove a character from your session group! \n
            **/Gamemaster Session Reward** - Send session rewards to involved characters! \n
            """, inline=False)
        embed.add_field(
            name='__**WorldAnvil Commands**__',
            value="""
            Commands for managing WorldAnvil plots and articles! \r\n
            **/gamemaster worldanvil plot** - Create or edit a plot! \n
            **/gamemaster worldanvil report** - Report on a session! \n
            """, inline=False)

        await interaction.followup.send(embed=embed)

    @fame_group.command(name='requests', description='accept or reject a request that timeout after 24 hours!')
    @app_commands.choices(acceptance=[discord.app_commands.Choice(name='accept', value=1),
                                      discord.app_commands.Choice(name='reject', value=2)])
    async def requests(self, interaction: discord.Interaction, proposition_id: int, reason: typing.Optional[str],
                       acceptance: discord.app_commands.Choice[int] = 1):
        """Accept or reject a proposition!"""
        guild_id = interaction.guild_id
        author = interaction.user.name
        guild = interaction.guild
        await interaction.response.defer(thinking=True, ephemeral=True)
        acceptance = 1 if acceptance == 1 else acceptance.value
        try:

            async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute(
                    "SELECT Character_Name, Prestige_Cost, Item_Name from A_Audit_Prestige Where Transaction_ID = ?",
                    (proposition_id,))
                item_id = await cursor.fetchone()
                if item_id is not None:

                    (item_character_name, item_prestige_cost, item_name) = item_id
                    await cursor.execute(
                        "SELECT Thread_ID, Fame, Prestige from Player_Characters where Character_Name = ?",
                        (item_character_name,))
                    player_info = await cursor.fetchone()
                    if player_info is not None:
                        (thread_id, fame, prestige) = player_info

                        if acceptance == 1:
                            update_reason = f"Item {item_name} has been accepted by {author}!"
                            update_reason += f"\r\n Reason: {reason}" if reason is not None else ""
                            calculated_fame = character_commands.calculate_fame(character_name=item_character_name,
                                                                                fame=fame, prestige=prestige,
                                                                                fame_change=0,
                                                                                prestige_change=-abs(
                                                                                    item_prestige_cost))
                            (fame_total, fame_change, prestige_total, final_prestige_change) = calculated_fame
                            character_updates = shared_functions.UpdateCharacterData(character_name=item_id[0],
                                                                                     fame_package=(
                                                                                         fame_total, prestige_total))
                            await shared_functions.update_character(guild_id=guild_id, change=character_updates)
                            reason = "item "
                            character_changes = shared_functions.CharacterChange(
                                character_name=item_id[0],
                                author=interaction.user.name,
                                fame=fame_total,
                                prestige=prestige_total,
                                fame_change=fame_change,
                                prestige_change=final_prestige_change,
                                source=reason)
                            log_update = await shared_functions.log_embed(
                                guild=guild, thread=thread_id,
                                change=character_changes,
                                bot=self.bot)
                            await shared_functions.character_embed(character_name=item_character_name, guild=guild)
                        else:
                            update_reason = f"Item {item_name} has been rejected by {author}!"
                            update_reason += f"\r\n Reason: {reason}" if reason is not None else ""
                            character_changes = shared_functions.CharacterChange(
                                character_name=item_id[0],
                                author=interaction.user.name,
                                source=reason)
                            log_update = await shared_functions.log_embed(
                                guild=guild,
                                thread=thread_id,
                                change=character_changes,
                                bot=self.bot)
                        await interaction.followup.send(embed=log_update)

                    else:
                        await interaction.followup.send_message(
                            f"Character {item_id[0]} does not exist! Could not complete transaction!")
                else:
                    await interaction.followup.send_message(
                        f"Item {proposition_id} does not exist! Could not complete transaction!")
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"An error occurred whilst managing a proposition: {e}")
            await interaction.followup.send_message(
                f"An error occurred whilst managing a proposition. Please try again later.")

    @fame_group.command(name='manage', description='Manage a character\'s fame and prestige!')
    @app_commands.autocomplete(character=shared_functions.character_select_autocompletion)
    async def manage(self, interaction: discord.Interaction, character: str, reason: typing.Optional[str],
                     fame: int = 0, prestige: int = 0,
                     ):
        """Add or remove from a player's fame and prestige!"""
        guild_id = interaction.guild_id
        guild = interaction.guild
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute("SELECT Thread_ID, Fame, Prestige from Player_Characters where Character_Name = ?",
                                     (character,))
                player_info = await cursor.fetchone()
                if player_info is not None:
                    (thread_id, current_fame, current_prestige) = player_info
                    calculated_fame = character_commands.calculate_fame(character_name=character, fame=current_fame,
                                                                        prestige=current_prestige, fame_change=fame,
                                                                        prestige_change=prestige)
                    (fame_total, fame_change, prestige_total, final_prestige_change) = calculated_fame
                    character_updates = shared_functions.UpdateCharacterData(character_name=character,
                                                                             fame_package=(fame_total, prestige_total))
                    await shared_functions.update_character(guild_id=guild_id, change=character_updates)
                    reason = f"fame and prestige change by {interaction.user.name}.\r\n" + reason if reason is not None else f"fame and prestige change by {interaction.user.name}."

                    character_changes = shared_functions.CharacterChange(character_name=character,
                                                                         author=interaction.user.name,
                                                                         fame=fame_total,
                                                                         prestige=prestige_total,
                                                                         fame_change=fame_change,
                                                                         prestige_change=final_prestige_change,
                                                                         source=reason)
                    log_update = await shared_functions.log_embed(
                        guild=guild,
                        thread=thread_id,
                        change=character_changes,
                        bot=self.bot)
                    await interaction.followup.send(embed=log_update)
                else:
                    await interaction.followup.send_message(
                        f"Character {character} does not exist! Could not complete transaction!")
        except (aiosqlite, TypeError, ValueError) as e:
            logging.exception(f"An error occurred whilst updating a character's fame & prestige: {e}")
            await interaction.followup.send_message(
                f"An error occurred whilst managing a proposition. Please try again later.")

    @session_group.command(name='create', description='Create a new session!')
    @app_commands.describe(hammer_time="Please use the plain code hammer time provides that appears like </>, ")
    @app_commands.describe(overflow="Allow for adjust role ranges!")
    @app_commands.choices(overflow=[
        discord.app_commands.Choice(name='current range only!', value=1),
        discord.app_commands.Choice(name='include next level bracket!', value=2),
        discord.app_commands.Choice(name='include lower level bracket!', value=3),
        discord.app_commands.Choice(name='ignore role requirements!', value=4)])
    async def create(self, interaction: discord.Interaction,
                     session_name: str,
                     session_range: discord.Role,
                     player_limit: int,
                     play_location: str,
                     game_link: typing.Optional[str],
                     group_id: typing.Optional[int],
                     hammer_time: str,
                     overview: str,
                     description: str,
                     region: typing.Optional[discord.Role],
                     plot: str = '9762aebb-43ae-47d5-8c7b-30c34a55b9e5',
                     overflow: discord.app_commands.Choice[int] = 1):
        """Create a new session."""
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            session_name, _ = name_fix(session_name)
            overflow_value = overflow if overflow == 1 else overflow.value
            level_range_text = f"{session_range.mention}"
            if overflow_value == 2 or overflow_value == 3:
                evaluated_session_range = await validate_milestone_system_overflow(
                    guild=interaction.guild,
                    session_range_id=session_range.id,
                    overflow=overflow_value)
                if evaluated_session_range is not None:
                    level_range_text += f" and {evaluated_session_range[0].mention}"
                else:
                    evaluated_region_range = await validate_region_system_overflow(
                        guild=interaction.guild,
                        session_range_id=session_range.id,
                        overflow=overflow_value)
                    if evaluated_region_range is not None:
                        level_range_text += f" and {evaluated_region_range[0].mention}"
            elif overflow_value == 4:
                level_range_text += "\r\n Any level can join."
            if game_link:
                game_link_valid = shared_functions.validate_vtt(game_link)
                if not game_link_valid[0]:
                    await interaction.followup.send(
                        f"Please provide a valid VTT link. You submitted {game_link} \r\n {game_link_valid[1]}")
                    return
            complex_hammer_time_valid = await shared_functions.complex_validate_hammertime(
                guild_id=interaction.guild_id,
                author_name=interaction.user.name,
                hammertime=hammer_time)
            print(complex_hammer_time_valid)
            if complex_hammer_time_valid[0] is False:
                print("validating potential regular validation")
                hammer_time_data = shared_functions.validate_hammertime(hammer_time)
            else:
                print("I am here")
                hammer_time_data = complex_hammer_time_valid[1]
            if not hammer_time_data[0]:
                await interaction.followup.send(f"Please provide a valid time: {hammer_time_data[1]}.")
                return
            else:
                (date, time, arrival, hammer_time_stamp) = hammer_time_data[2]
                if hammer_time_data[1]:
                    hammer_time_field = f"{date} at {time} which is {arrival}"
                else:
                    hammer_time_field = f"{hammer_time}"
            # plot_valid = shared_functions.validate_worldanvil_link(guild_id=interaction.guild_id, article_id=plot)
            # if not plot_valid:
                # await interaction.followup.send(f"Please provide a valid plot link. You submitted {plot}")
                # return
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                if group_id:
                    await cursor.execute("SELECT Player_Name from Sessions_Group_Presign WHERE Group_ID = ?",
                                         (group_id,))
                    group_players = await cursor.fetchall()
                    if group_players:
                        group_range_text = "\r\n Players in this group include:"
                        for player in group_players:
                            group_range_text += f" <@{player[0]}>"
                        await cursor.execute("DELETE from Sessions_Group_Presign WHERE Group_ID = ?", (group_id,))
                        await db.commit()
                    else:
                        await interaction.followup.send(f"Group ID {group_id} does not exist!")
                        return
                else:
                    group_range_text = ""
                base_session_info = SessionBaseInfo(
                    guild_id=interaction.guild_id,
                    gm_name=interaction.user.name,
                    session_name=session_name,
                    session_range=session_range.name,
                    session_range_id=session_range.id,
                    player_limit=player_limit,
                    hammer_time=hammer_time_stamp,
                    overflow=overflow_value,
                    play_location=play_location,
                    game_link=game_link,
                    overview=overview,
                    description=description,
                    plot=plot,
                    region=region.id if region else None
                )
                session_id = await create_session(base_session_info)
                if session_id == 0:
                    await interaction.followup.send(
                        "An error occurred whilst creating a session. Please try again later.")
                    return
                else:
                    message_content = f"{level_range_text}"
                    message_content += f", {group_range_text}" if group_range_text else ""
                    message_content += f"\r\n{interaction.user.mention} is running a session"
                    message_content += f" in <@&{region.id}>!" if region else "!"
                    message_content += F"\r\n THIS IS AN LM SESSION, IF YOU HAVE NOT PREPARED TO DIE, PUSSY OUT NOW... YOU SHOULD BE SCARED. YOU SHOULD BE SCARED OF DEATH. IF YOU ARE GOING TO GET UPSETTI OVER THIS SPHAGHETTI THIS IS NOT THE SESSION FOR YOU." if interaction.user.id == 237394424815026176 else ""
                    embed_information = SessionEmbedInfo(
                        guild=interaction.guild,
                        gm_name=interaction.user.name,
                        session_name=session_name,
                        session_range=message_content,
                        group_range=group_range_text,
                        player_limit=player_limit,
                        hammer_time=hammer_time_field,
                        play_location=play_location,
                        game_link=game_link,
                        overview=overview,
                        description=description,
                        session_id=session_id
                    )
                    session_embed = await create_session_embed(embed_info=embed_information)
                    if not isinstance(session_embed, tuple):
                        await interaction.followup.send("An error occurred whilst creating the session embed.")
                    else:
                        if not session_embed[0]:
                            await interaction.followup.send(session_embed[1])
                            return
                        else:
                            (embed, session_channel) = session_embed
                            if isinstance(time, int) or isinstance(time, str):
                                now = datetime.datetime.now(datetime.timezone.utc)
                                session_start_time = shared_functions.parse_hammer_time_to_iso(hammer_time_stamp)
                                time_difference = session_start_time - now
                                timeout_time = int(time_difference.total_seconds())
                            else:
                                timeout_time = 3600 * 12  # default 12 hours

                            view = JoinOrLeaveSessionView(
                                timeout_seconds=timeout_time,
                                session_id=session_id,
                                guild=interaction.guild,
                                session_name=session_name,
                                content=message_content)
                            announcement_message = await session_channel.send(
                                content=f"{region.mention}" if region else message_content,
                                embed=embed,
                                view=view,
                                allowed_mentions=discord.AllowedMentions(roles=True))
                            if region:
                                await announcement_message.edit(content=message_content)
                            created_thread = await announcement_message.create_thread(
                                name=f"{session_id}: {session_name}",
                                auto_archive_duration=10080)
                            mini_embed = discord.Embed(title="Sign up for this session!", description=f"you can sign up using the buttons on the [original message](<{announcement_message.jump_url}>)! **WHILST ON THE CHANNEL, NOT IN THIS THREAD.**\n you can also use the /player sessions join command to sign up for this session! \n the /player sessions leave command to leave. \n if there is blue text in the session it's probably a link!")
                            await created_thread.send(embed=mini_embed)
                            await cursor.execute(
                                "UPDATE Sessions SET Message = ?, Session_Thread = ? WHERE Session_ID = ?",
                                (announcement_message.id, created_thread.id, session_id))
                            await db.commit()
                            schedule_session_reminders(
                                session_id=session_id,
                                thread_id=created_thread.id,
                                hammer_time=hammer_time_stamp,
                                guild_id=interaction.guild_id,
                                bot=self.bot
                            )
                            if game_link:
                                await interaction.followup.send(
                                    f"""Session #{session_id}: "{session_name}" was successfully created at {announcement_message.jump_url}!""")
                            else:
                                await cursor.execute("SELECT Game_Link from sessions where Game_Link is not null and GM_Name = ? order by session_id desc limit 1",
                                                     (interaction.user.name,))
                                game_link_fetch = await cursor.fetchone()
                                if game_link_fetch:
                                    game_view = UpdateGameLinkView(
                                        announcement_message=announcement_message,
                                        content=f"You didn't provide a game link in your announcement, would you like to use the last one you provided? \r\n {game_link_fetch[0]}",
                                        session_content=message_content,
                                        session_embed=embed,
                                        interaction=interaction,
                                        game_link=game_link_fetch[0],
                                        session_id=session_id)
                                    await game_view.send_initial_message()
                                else:
                                    await interaction.followup.send(
                                    f"""Session #{session_id}: "{session_name}" was successfully created at {announcement_message.jump_url}!""")
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"An error occurred whilst creating a session: {e}")
            await interaction.followup.send("An error occurred whilst creating a session. Please try again later.")

    @session_group.command()
    @app_commands.describe(hammer_time="Please use the plain code hammer time provides that appears like </>, ")
    @app_commands.describe(overflow="Allow for adjust role ranges!")
    @app_commands.choices(overflow=[
        discord.app_commands.Choice(name='current range only!', value=1),
        discord.app_commands.Choice(name='include next level bracket!', value=2),
        discord.app_commands.Choice(name='include lower level bracket!', value=3),
        discord.app_commands.Choice(name='ignore role requirements!', value=4)])
    async def edit(self, interaction: discord.Interaction,
                   session_id: int,
                   session_name: typing.Optional[str],
                   session_range: typing.Optional[discord.Role],
                   player_limit: typing.Optional[int],
                   play_location: typing.Optional[str],
                   game_link: typing.Optional[str],
                   hammer_time: typing.Optional[str],
                   overview: typing.Optional[str],
                   description: typing.Optional[str],
                   region: typing.Optional[discord.Role],
                   plot: typing.Optional[str],
                   overflow: typing.Optional[discord.app_commands.Choice[int]]):
        """Create a new session."""
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            build_info = await build_edit_info(
                gm_name=interaction.user.name,
                guild_id=interaction.guild_id,
                session_id=session_id)

            if build_info is not None:
                (build_info_base, message, session_thread) = build_info
                build_info_base.session_name = session_name if session_name is not None else build_info_base.session_name
                build_info_base.session_range_id = session_range.id if session_range is not None else build_info_base.session_range_id
                build_info_base.session_range = f'<@&{session_range.id}>' if session_range is not None else f"<@&{build_info_base.session_range_id}>"
                build_info_base.player_limit = player_limit if player_limit is not None else build_info_base.player_limit
                build_info_base.play_location = play_location if play_location is not None else build_info_base.play_location
                build_info_base.game_link = game_link if game_link is not None else build_info_base.game_link
                build_info_base.hammer_time = hammer_time if hammer_time is not None else build_info_base.hammer_time
                build_info_base.overview = overview if overview is not None else build_info_base.overview
                build_info_base.description = description if description is not None else build_info_base.description
                build_info_base.plot = plot if plot is not None else build_info_base.plot
                build_info_base.overflow = overflow.value if overflow is not None else build_info_base.overflow
                build_info_base.region = region.id if region is not None else build_info_base.region
                if overflow:
                    if build_info_base.overflow != 1:
                        evaluated_session_range = await validate_milestone_system_overflow(
                            guild=interaction.guild,
                            session_range_id=build_info_base.session_range_id,
                            overflow=build_info_base.overflow)
                        if evaluated_session_range is not None:
                            build_info_base.session_range += f" and {evaluated_session_range[0].mention}"
                        elif evaluated_session_range is None:
                            evaluated_region_range = await validate_region_system_overflow(
                                guild=interaction.guild,
                                session_range_id=build_info_base.session_range_id,
                                overflow=build_info_base.overflow)
                            if evaluated_region_range is not None:
                                build_info_base.session_range += f" and {evaluated_region_range[0].mention}"
                        elif build_info_base.overflow == 4:
                            build_info_base.session_range += "\r\n Any level can join."
                if game_link:
                    game_link_valid = shared_functions.validate_vtt(game_link)
                    if not game_link_valid[0]:
                        await interaction.followup.send(
                            f"Please provide a valid VTT link. You submitted {game_link} \r\n {game_link_valid[1]}")
                        return
                time = None
                hammer_time_valid = shared_functions.validate_hammertime(build_info_base.hammer_time)
                if not hammer_time_valid[0]:
                    hammer_time_field = hammer_time
                else:
                    if hammer_time_valid[1]:
                        (date, time, arrival, hammer_time) = hammer_time_valid[2]
                        hammer_time_field = f"{date} at {time} which is {arrival}"
                    else:
                        (date, time, arrival) = hammer_time_valid[2]
                        await interaction.followup.send(
                            f"Please provide a valid hammer time. Your session of {date} at {time} which is {arrival} would occur IN THE PAST and humans haven't discovered time travel yet..")
                        return
                if plot:
                    plot_valid = shared_functions.validate_worldanvil_link(guild_id=interaction.guild.id,
                                                                           article_id=plot)
                    if not plot_valid:
                        await interaction.followup.send(f"Please provide a valid plot link. You submitted {plot}")
                        return
                session_update = await edit_session(build_info_base, session_id=session_id)
                if not session_update:
                    await interaction.followup.send(
                        "An error occurred whilst editing the session. Please try again later.")
                    return
                else:
                    embed_information = SessionEmbedInfo(
                        session_id=session_id, guild=interaction.guild, gm_name=build_info_base.gm_name,
                        session_name=build_info_base.session_name, session_range=build_info_base.session_range,
                        group_range="",
                        player_limit=build_info_base.player_limit, hammer_time=hammer_time_field,
                        play_location=build_info_base.play_location,
                        game_link=build_info_base.game_link, overview=build_info_base.overview,
                        description=build_info_base.description
                    )

                    if isinstance(embed_information, str):
                        await interaction.followup.send(embed_information)
                        return
                    else:
                        (embed, session_channel) = await create_session_embed(embed_info=embed_information)
                        if time:
                            now = datetime.datetime.now(datetime.timezone.utc)
                            session_start_time = shared_functions.parse_hammer_time_to_iso(hammer_time)
                            time_difference = session_start_time - now
                            timeout_time = int(time_difference.total_seconds())
                        else:
                            timeout_time = 3600 * 12
                        view = JoinOrLeaveSessionView(timeout_seconds=int(timeout_time),
                                                      session_id=session_id, guild=interaction.guild,
                                                      session_name=build_info_base.session_name, content=build_info_base.session_range)

                        announcement_message = await session_channel.fetch_message(message)
                        if announcement_message:
                            content = f"{build_info_base.session_range}"
                            content += f"\r\n {interaction.user.mention} is running a session"
                            content += f" in <@&{build_info_base.region}>!" if build_info_base.region else "!"
                            content += F"\r\n THIS IS AN LM SESSION, IF YOU HAVE NOT PREPARED TO DIE, PUSSY OUT NOW... YOU SHOULD BE SCARED. YOU SHOULD BE SCARED OF DEATH. IF YOU ARE GOING TO GET UPSETTI OVER THIS SPHAGHETTI THIS IS NOT THE SESSION FOR YOU." if interaction.user.id == 237394424815026176 else ""
                            await announcement_message.edit(content=content, embed=embed,
                                                            view=view)
                            clear_session_reminders(
                                session_id=session_id,
                                start_time=hammer_time,
                                jobs_to_schedule=scheduled_jobs
                            )
                            schedule_session_reminders(
                                session_id=session_id,
                                thread_id=session_thread,
                                hammer_time=hammer_time,
                                guild_id=interaction.guild_id,
                                bot=self.bot
                            )
                            await interaction.followup.send(
                                f"Session {build_info_base.session_name} with {session_id} has been updated at {announcement_message.jump_url}!")
                        else:
                            await interaction.followup.send(
                                f"Could not find the session announcement message for session {session_id}!")
            else:
                await interaction.followup.send(
                    f"Invalid Session ID of {session_id} associated with host {interaction.user.name}")
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"An error occurred whilst editing a session: {e}")
            await interaction.followup.send("An error occurred whilst editing a session. Please try again later.")

    @session_group.command(name='delete', description='Delete a session!')
    async def delete(self, interaction: discord.Interaction, session_id: int):
        """Delete an ACTIVE Session."""
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute(
                    "SELECT Message, Session_Thread, Session_Name, Hammer_Time from Sessions WHERE Session_ID = ? AND GM_Name = ? AND IsActive = 1 ORDER BY Created_Time Desc Limit 1",
                    (session_id, interaction.user.name))
                info = await cursor.fetchone()
                if info is not None:
                    (message_id, thread_id, session_name, hammer_time) = info
                    await cursor.execute("UPDATE Sessions SET IsActive = 0 WHERE Session_ID = ?", (session_id,))
                    await db.commit()
                    clear_session_reminders(
                        session_id=session_id,
                        start_time=hammer_time,
                        jobs_to_schedule=scheduled_jobs)
                    embed = discord.Embed(title=f"{info[1]}", description=f"This session has been cancelled.",
                                          color=discord.Colour.red())
                    embed.set_author(name=f'{interaction.user.name}')
                    embed.set_footer(text=f'Session ID: {session_id}.')
                    async with shared_functions.config_cache.lock:
                        configs = shared_functions.config_cache.cache.get(interaction.guild.id)
                        if configs:
                            session_channel_info = configs.get('Sessions_Channel')

                    if not session_channel_info:
                        await interaction.followup.send(
                            "Issue with the Sessions Channel set by your Server Admin!!!! Please contact them to fix this issue. Session Channel Not Found in the DB!")
                        return
                    session_channel = interaction.guild.get_channel(session_channel_info)
                    if not session_channel:
                        session_channel = await interaction.guild.fetch_channel(session_channel_info)
                    if not session_channel:
                        await interaction.followup.send(
                            "Issue with the Sessions Channel set by your Server Admin!!!! Please contact them to fix this issue. Session Channel Not Found by the Bot!")
                        return
                    msg = await session_channel.fetch_message(info[0])
                    await msg.edit(embed=embed, view=None)
                    thread = interaction.guild.get_thread(info[1])
                    if not thread:
                        thread = await interaction.guild.fetch_channel(info[1])
                    if thread:
                        await thread.delete()
                    else:
                        await interaction.followup.send("Could not find the session thread!")
                        return
                    await interaction.followup.send(
                        f"the following session of {info[2]} located at {msg.jump_url} has been cancelled.")
                if info is None:
                    await interaction.followup.send(
                        f"Invalid Session ID of {session_id} associated with host {interaction.user.name}")
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"An error occurred whilst deleting a session: {e}")
            await interaction.followup.send("An error occurred whilst deleting a session. Please try again later.")

    @session_group.command(name='accept', description='accept the players into a session!')
    @app_commands.autocomplete(specific_character=shared_functions.character_select_autocompletion)
    @app_commands.describe(randomize="for the purposes of picking a number of randomized players")
    @app_commands.describe(
        specific_character="Picking a specific player's character. You will have to use their CHARACTER Name for this.")
    async def accept(self, interaction: discord.Interaction, session_id: int, player_1: typing.Optional[discord.Member],
                     player_2: typing.Optional[discord.Member], player_3: typing.Optional[discord.Member],
                     player_4: typing.Optional[discord.Member], player_5: typing.Optional[discord.Member],
                     player_6: typing.Optional[discord.Member], specific_character: typing.Optional[str],
                     randomize: int = 0):
        """GM: Accept player Sign-ups into your session for participation"""
        await interaction.response.defer(thinking=True)
        print(randomize)
        try:
            player_members = [player for player in [player_1, player_2, player_3, player_4, player_5, player_6] if
                              player]
            player_list = [member.id for member in player_members]
            if not specific_character and randomize == 0 and len(player_list) == 0:
                await interaction.followup.send(
                    "Please provide at least one method to accept players into the session (players, specific character, or randomize).")
            else:
                async with aiosqlite.connect(f"pathparser_{interaction.guild.id}.sqlite") as db:
                    cursor = await db.cursor()
                    await cursor.execute(
                        "SELECT Session_Name, Play_location, hammer_time, game_link, Session_thread, isactive FROM Sessions WHERE Session_ID = ? AND GM_Name = ?",
                        (session_id, interaction.user.name))
                    session_info = await cursor.fetchone()
                    if session_info is None:
                        await interaction.followup.send(
                            f"Invalid Session ID of {session_id} associated with host {interaction.user.name}")
                    else:
                        (session_name, play_location, hammer_time, game_link, session_thread, isactive) = session_info
                        hammer_validated = shared_functions.validate_hammertime(hammer_time)
                        if not isactive:
                            await interaction.followup.send(
                                f"Session {session_name} is not active and cannot accept players.")
                            return
                        if hammer_validated[1]:
                            print(hammer_validated)
                            hammer_times = hammer_validated[2]
                            (hammer_date, hammer_hour, hammer_until, hammer_time) = hammer_times
                            date_and_time = f"Date & Time: {hammer_date} at {hammer_hour} which is {hammer_until}"
                        else:
                            date_and_time = f"Date & Time: {hammer_time}"
                        embed = discord.Embed(
                            title=f"{session_info[0]}",
                            description=date_and_time,
                            color=discord.Colour.blue())
                        if game_link:
                            embed.url = game_link
                        embed.set_footer(text=f'Session ID: {session_id}.')
                        content = "The Following Players have been processed:"
                        # Handle specific character
                        if specific_character:
                            await cursor.execute(
                                """
                                SELECT pc.Player_ID, pc.Player_Name, pc.Character_Name
                                FROM Player_Characters pc
                                WHERE pc.Character_Name = ?
                                  AND NOT EXISTS (
                                    SELECT 1 FROM Sessions_Participants sp
                                    WHERE sp.Character_Name = pc.Character_Name
                                      AND sp.Session_ID = ?
                                  )
                                """,
                                (specific_character, session_id)
                            )
                            player = await cursor.fetchone()

                            if not player:
                                embed.add_field(name=f"SIGNUP FAILED: {specific_character}",
                                                value="Could not be accepted!")
                            else:
                                player_id = player[0]
                                accepted = await player_accept_specific(
                                    guild_id=interaction.guild_id,
                                    session_name=session_name,
                                    session_id=session_id,
                                    character_name=specific_character
                                )
                                if accepted:
                                    embed.add_field(name=specific_character,
                                                    value=f"Has been accepted with player: <@{player_id}>")
                                    content += f" <@{player_id}> has been accepted!"
                                else:
                                    embed.add_field(name=f"SIGNUP FAILED: {specific_character}",
                                                    value=f"Could not be accepted with player: <@{player_id}>")
                        # Handle player list
                        if len(player_list) > 0:
                            await cursor.execute(
                                "SELECT Player_ID, Character_Name FROM Sessions_Signups WHERE Session_ID = ?",
                                (session_id,)
                            )
                            signup_list = await cursor.fetchall()
                            signup_dict = {player_id: character_name for player_id, character_name in signup_list}

                            for player_id in player_list:
                                if player_id in signup_dict:
                                    character_name = signup_dict[player_id]
                                    accepted = await player_accept(
                                        guild_id=interaction.guild_id,
                                        session_name=session_name,
                                        session_id=session_id,
                                        player_id=player_id
                                    )
                                    if accepted:
                                        embed.add_field(name=character_name,
                                                        value=f"Has been accepted with player: <@{player_id}>")
                                        content += f" <@{player_id}> has been accepted!"
                                    else:
                                        embed.add_field(name=f"SIGNUP FAILED: {character_name}",
                                                        value=f"Could not be accepted with player: <@{player_id}>")
                                else:
                                    content += f" <@{player_id}> could not be accepted! Player not found in the signup list!"
                        # handle randomize
                        if randomize > 0:
                            print(randomize)
                            await cursor.execute(
                                "SELECT Player_ID, Character_Name FROM Sessions_Signups WHERE Session_ID = ?",
                                (session_id,)
                            )
                            signup_list = list(await cursor.fetchall())
                            print(signup_list)
                            if signup_list:
                                random_players = random.sample(signup_list, min(len(signup_list), randomize))
                                print(random_players)
                                for player in random_players:
                                    player_id, character_name = player
                                    accepted = await player_accept(
                                        guild_id=interaction.guild_id,
                                        session_name=session_name,
                                        session_id=session_id,
                                        player_id=player_id
                                    )
                                    if accepted:
                                        embed.add_field(name=character_name,
                                                        value=f"Has been accepted with player: <@{player_id}>")
                                        content += f" <@{player_id}> has been accepted!"
                                    else:
                                        embed.add_field(name=f"SIGNUP FAILED: {character_name}",
                                                        value=f"Could not be accepted with player: <@{player_id}>")
                            else:
                                logging.info("No players found in signup_list.")

                    session_thread_channel = interaction.guild.get_channel(int(session_thread))
                    if not session_thread_channel:
                        session_thread_channel = await interaction.guild.fetch_channel(int(session_thread))
                    if not session_thread_channel:
                        await interaction.followup.send(
                            content=content,
                            embed=embed,
                            allowed_mentions=discord.AllowedMentions(users=True))
                    else:
                        message = await session_thread_channel.send(
                            content=content,
                            embed=embed,
                            allowed_mentions=discord.AllowedMentions(users=True))
                        await interaction.followup.send(f"Players have been accepted into the session and notified! {message.jump_url}")
        except (aiosqlite.Error, discord.DiscordException, TypeError, ValueError) as e:
            logging.exception(f"An error occurred whilst accepting players into a session: {e}")
            await interaction.followup.send("An error occurred while processing your request. Please try again later.")

    @session_group.command(name='remove', description='Remove a player from a session!')
    async def remove(self, interaction: discord.Interaction, session_id: int, player: discord.Member):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute(
                    "SELECT Session_Name, Play_location, hammer_time, game_link, IsActive, Gold, Essence, Alt_Reward_All FROM Sessions WHERE Session_ID = ?",
                    (session_id,))
                session_info = await cursor.fetchone()
                if session_info is None:
                    await interaction.followup.send(f"Invalid Session ID of {session_id}")
                else:
                    (session_name, play_location, hammer_time, game_link, is_active, gold, essence,
                     alt_reward_all) = session_info
                    if session_info[4] == 1:
                        await cursor.execute(
                            "SELECT Player_Name, Character_Name FROM Sessions_Participants WHERE Session_ID = ? and Player_Name = ?",
                            (session_id, player.name))
                        participant_info = await cursor.fetchone()
                        await cursor.execute(
                            "SELECT Player_Name FROM Sessions_Signups WHERE Session_ID = ? and Player_Name = ?",
                            (session_id, player.name))

                        signup_info = await cursor.fetchone()
                        if participant_info is None and signup_info is None:
                            await interaction.followup.send(
                                f"{player.name} does not appear to be participating in the session of {session_info[0]} with session ID: {session_id}")
                        else:
                            player_name = player.name
                            await player_commands.player_leave_session(
                                guild=interaction.guild,
                                session_id=session_id,
                                player_name=player_name,
                                player=False)
                            await interaction.followup.send(
                                f"{player.name} has been removed from Session {session_info[0]} with ID: {session_id}")
                    else:
                        await cursor.execute(
                            """SELECT 
                            Player_ID, Player_Name, Character_Name, 
                            Level, Tier, Effective_Gold, Received_Milestones, Received_Trials, 
                            Received_Gold, Received_Fame, Received_Prestige, Received_Essence, 
                            Gold_Transaction_ID FROM Sessions_Archive WHERE Session_ID = ? and Player_Name = ?""",
                            (session_id, player.name))
                        reward_info = await cursor.fetchone()
                        if reward_info is None:
                            await interaction.followup.send(
                                f"{player.name} does not appear to have participated in the session of {session_info[0]} with session ID: {session_id}")
                        else:
                            (player_id, player_name, character_name,
                             level, tier, effective_gold, received_milestones, received_trials,
                             received_gold, received_fame, received_prestige, received_essence,
                             gold_transaction_id) = reward_info
                            await cursor.execute("SELECT Thread_ID FROM Player_Characters WHERE Character_Name = ?",
                                                 (character_name,))
                            thread_id = await cursor.fetchone()
                            if thread_id is None:
                                await interaction.followup.send(
                                    f"Could not find player character of {character_name} in database!")
                                logging.info(
                                    f"Could not find player character of {character_name} in database! when attempting to remove their rewards!")
                                return
                            else:
                                embed = discord.Embed(
                                    title=f"are you sure you want to revoke session rewards from {session_id}: {session_name} for {character_name}?",
                                    description=f"hit the accept button below to confirm")
                                embed.add_field(name=f"Revoking Gold", value=f"{received_gold} Gold")
                                embed.add_field(name=f"Revoking Milestones", value=f"{received_milestones} Milestones")
                                embed.add_field(name=f"Revoking Trials", value=f"{received_trials} Trials")
                                embed.add_field(name=f"Revoking Essence", value=f"{received_essence} Essence")
                                embed.add_field(name=f"Revoking Fame", value=f"{received_fame} Fame")
                                content = f"Revoking rewards from {character_name} for session {session_id}: {session_name}"
                                view = RemoveRewardsView(
                                    content=content,
                                    interaction=interaction,
                                    discord_embed=embed,
                                    session_id=session_id,
                                    character_name=character_name,
                                    bot=self.bot,
                                    session_gold=gold,
                                    session_rewards_info=reward_info,
                                )
                                await view.send_initial_message()
        except (aiosqlite.Error, discord.DiscordException, TypeError, ValueError) as e:
            logging.exception(f"An error occurred whilst removing a player from a session: {e}")
            await interaction.followup.send(
                "An error occurred whilst removing a player from a session. Please try again later.")

    @session_group.command(name='reward', description='reward the players in a session!')
    @app_commands.describe(reward_all="A reward for each individual member of the party")
    @app_commands.describe(
        party_reward="A reward for the party to divvy up amongst themselves, or not. Link a google doc if reward exceeds character limit.")
    async def reward(
            self,
            interaction: discord.Interaction,
            session_id: int,
            gold: float,
            easy: int = 0,
            medium: int = 0,
            hard: int = 0,
            deadly: int = 0,
            trials: int = 0,
            reward_all: str = None,
            fame: int = 2,
            prestige: int = 2,
            party_reward: str = None,
            summary: str = None
    ):
        """GM: Reward Players for Participating in your session."""
        awarded_essence = 10
        await interaction.response.defer(thinking=True, ephemeral=True)
        if gold < 0 or easy < 0 or medium < 0 or hard < 0 or deadly < 0 or awarded_essence < 0 or trials < 0:
            await interaction.followup.send(
                f"Your players might not judge you out loud for trying to give them a negative award, but I do...")
        elif gold == 0 and easy == 0 and medium == 0 and hard == 0 and deadly == 0 and trials == 0 and reward_all is None and party_reward is None:
            await interaction.followup.send(
                f"Your players have been rewarded wi-- wait. No! At least give them a silver or a milestone!")
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute(
                    "SELECT GM_Name, Session_Name, Session_Range, Play_Location, hammer_time, Message, Session_Thread, IsActive, Related_Plot FROM Sessions WHERE Session_ID = ?",
                    (session_id,))
                session_info = await cursor.fetchone()
                if session_info is not None:
                    (gm_name, session_name, session_range, play_location, hammer_time, message, session_thread,
                     is_active, plot) = session_info
                    if is_active == 1:
                        base_session_info = RewardSessionBaseInfo(
                            gm_name=gm_name,
                            session_name=session_name,
                            rewarded_alt_reward_all=reward_all,
                            rewarded_alt_reward_party=party_reward,
                            rewarded_easy=easy,
                            rewarded_medium=medium,
                            rewarded_hard=hard,
                            rewarded_deadly=deadly,
                            rewarded_trials=trials,
                            rewarded_gold=Decimal(gold),
                            rewarded_fame=fame,
                            rewarded_prestige=prestige,
                            rewarded_essence=awarded_essence,
                            rewarded_message=None,
                            rewarded_session_thread=None
                        )
                        mentions = f"Session Rewards for {session_name}: "
                        await cursor.execute(
                            "SELECT Player_Name, Player_ID, Character_Name, Level, Tier, Effective_Wealth  FROM Sessions_Participants WHERE Session_ID = ?",
                            (session_id,))
                        session_players = await cursor.fetchall()
                        if not session_players:
                            await interaction.followup.send(
                                f"No players could be found participating in session with {session_id}")
                        else:
                            if summary:
                                significance = max(1,
                                                   5 - (easy * 1 + medium * 2 + hard * 3 + deadly * 4 + trials * 2))
                                world_anvil = await shared_functions.put_wa_report(
                                    guild_id=interaction.guild_id,
                                    session_id=session_id,
                                    author=gm_name,
                                    overview=summary,
                                    plot=plot,
                                    significance=significance
                                )
                            else:
                                world_anvil = None
                            if world_anvil:
                                (world_anvil_link, world_anvil_id) = world_anvil
                                embed = discord.Embed(title=session_name, description=f"Reward Display",
                                                      color=discord.Colour.green(), url=world_anvil_link['url'])
                            else:
                                embed = discord.Embed(title=session_name, description=f"Reward Display",
                                                      color=discord.Colour.green())
                            embed.set_footer(text=f"Session ID is {session_id}")
                            for player in session_players:
                                (player_name, player_id, character_name, level, tier, effective_wealth) = player
                                mentions += f"<@{player[1]}> "
                                session_reward = await session_reward_calculation(
                                    interaction=interaction,
                                    author_name=gm_name,
                                    session_id=session_id,
                                    character_name=character_name,
                                    pre_session_level=level,
                                    pre_session_tier=tier,
                                    pre_session_gold=effective_wealth,
                                    source=f"Session Rewards for {session_name}, {session_id}",
                                    session_base_info=base_session_info)
                                if isinstance(session_reward, str):
                                    logging.info(
                                        f"An error occurred whilst rewarding players for a session: {session_reward}")
                                    embed.add_field(name=character_name, value=session_reward)
                                else:
                                    (session_reward_embed, player_thread) = session_reward
                                    changes = f"**<@{player_id}>'s Rewards:**"
                                    changes += f"\r\n+{session_reward_embed.milestone_change} Milestones" if session_reward_embed.milestone_change else ""
                                    changes += f"\r\n**Leveled up!** Now Level {session_reward_embed.level}!" if session_reward_embed.level != level else ""
                                    changes += f"\r\n+{session_reward_embed.trial_change} Trials" if session_reward_embed.trial_change else ""
                                    changes += f"\r\n**Tiered up!** Now Tier {session_reward_embed.tier}!" if session_reward_embed.tier != tier and session_reward_embed.tier else ""
                                    changes += f"\r\n+{session_reward_embed.gold_change} gold" if session_reward_embed.gold_change else ""
                                    changes += f"\r\n+{session_reward_embed.essence_change} essence" if session_reward_embed.essence_change else ""
                                    changes += f"\r\n+{session_reward_embed.fame_change} fame and +{session_reward_embed.prestige_change} prestige!" if session_reward_embed.fame_change or session_reward_embed.prestige_change else ""
                                    changes += "\r\n**New Totals:**"
                                    changes += f"\r\n{session_reward_embed.gold} gold" if session_reward_embed.gold else ""
                                    changes += f", {session_reward_embed.essence} essence" if session_reward_embed.essence else ""
                                    changes += f"\r\n{session_reward_embed.fame} fame, {session_reward_embed.prestige} prestige" if session_reward_embed.fame or session_reward_embed.prestige else ""
                                    changes += f"\r\n{session_reward_embed.milestones_total} Milestones" if session_reward_embed.milestones_total else ""
                                    changes += f", {session_reward_embed.trials} Trials" if session_reward_embed.trial_change else ""
                                    embed.add_field(name=character_name, value=changes)
                                    await shared_functions.log_embed(
                                        change=session_reward_embed,
                                        guild=interaction.guild,
                                        thread=player_thread,
                                        bot=self.bot)
                                    await shared_functions.character_embed(
                                        character_name=character_name,
                                        guild=interaction.guild)
                                    await cursor.execute(
                                        "Delete from Sessions_Participants where Session_ID = ? and Player_Name = ?",
                                        (session_id, player_name))
                                    await db.commit()
                            async with shared_functions.config_cache.lock:
                                configs = shared_functions.config_cache.cache.get(interaction.guild.id)
                                if configs:

                                    quest_rewards_channel_id = configs.get('Quest_Rewards_Channel')

                            quest_rewards_channel = interaction.guild.get_channel(quest_rewards_channel_id)
                            if not quest_rewards_channel:
                                quest_rewards_channel = await interaction.guild.fetch_channel(
                                    quest_rewards_channel_id)
                            if not quest_rewards_channel:
                                await interaction.followup.send(
                                    "Issue with the Quest Rewards Channel set by your Server Admin!!!! Please contact them to fix this issue. Quest Rewards Channel Not Found in the DB!")
                                return
                            else:

                                quest_message = await quest_rewards_channel.send(content=mentions, embed=embed,
                                                                                 allowed_mentions=discord.AllowedMentions(
                                                                                     users=True))
                                if party_reward:
                                    quest_thread = await quest_message.create_thread(
                                        name=f"{session_id}: {session_name} rewards", auto_archive_duration=10080)
                                    quest_thread_id = quest_thread.id
                                    await quest_thread.send(content=party_reward)
                                else:
                                    quest_thread_id = None

                                await cursor.execute(
                                    "UPDATE Sessions SET IsActive = 0, Gold = ?, Essence = ?, Easy = ?, Medium = ?, Hard = ?, Deadly = ?, Trials = ?, fame = ?, Prestige = ?, Rewards_Message = ?, Rewards_Thread = ?, Completed_Time = ? WHERE Session_ID = ?",
                                    (gold, awarded_essence, easy, medium, hard, deadly, trials, fame, prestige,
                                     quest_message.id, quest_thread_id, datetime.datetime.now(), session_id))
                                await cursor.execute(
                                    "DELETE FROM Sessions_Signups WHERE Session_ID = ? and Player_Name = ?",
                                    (session_id, player_name))

                                await db.commit()
                                await interaction.followup.send(
                                    f"Rewards have been sent to the players! Check the Quest Rewards Channel with {quest_message.jump_url} for more information!",
                                    ephemeral=True)
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"An error occurred whilst rewarding players for a session: {e}")
            await interaction.followup.send(
                "An error occurred whilst rewarding players for a session. Please try again later.")

    @session_group.command(name='endow', description='Endow the players in a session with a unique reward!')
    async def endow(
            self,
            interaction: discord.Interaction,
            session_id: int,
            player_1: typing.Optional[discord.Member], player_1_reward: typing.Optional[str],
            player_2: typing.Optional[discord.Member], player_2_reward: typing.Optional[str],
            player_3: typing.Optional[discord.Member], player_3_reward: typing.Optional[str],
            player_4: typing.Optional[discord.Member], player_4_reward: typing.Optional[str],
            player_5: typing.Optional[discord.Member], player_5_reward: typing.Optional[str],
            player_6: typing.Optional[discord.Member], player_6_reward: typing.Optional[str]
    ):
        """GM: Accept player Sign-ups into your session for participation"""
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            # Create lists of players and their corresponding rewards
            players = [player_1, player_2, player_3, player_4, player_5, player_6]
            rewards = [player_1_reward, player_2_reward, player_3_reward,
                       player_4_reward, player_5_reward, player_6_reward]

            # Zip the players and rewards together
            player_rewards = [
                (player.id, reward)
                for player, reward in zip(players, rewards)
                if player and reward  # Ensure both player and reward exist
            ]

            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute(
                    "SELECT Player_ID, Character_Name FROM Sessions_Archive WHERE Session_ID = ?",
                    (session_id,)
                )
                archive_list = await cursor.fetchall()
                archive_dict = {player_id: character_name for player_id, character_name in archive_list}
                content = "The following players have been endowed with their rewards: "
                for player_id, reward in player_rewards:
                    # Check if the player is participating in the session
                    if player_id in archive_dict:
                        character_name = archive_dict[player_id]
                        await cursor.execute(
                            "SELECT Thread_ID, True_Character_Name FROM Player_Characters WHERE Character_Name = ?",
                            (character_name,))
                        thread_id = await cursor.fetchone()
                        if thread_id:
                            logging_info = shared_functions.CharacterChange(
                                character_name=character_name,
                                author=interaction.user.name,
                                source=f"Endowment: {reward}"
                            )
                            await shared_functions.log_embed(
                                bot=self.bot,
                                change=logging_info,
                                guild=interaction.guild,
                                thread=thread_id[0])
                            player_rewards.remove((player_id, reward))
                            await cursor.execute(
                                "UPDATE Sessions_Archive SET Alt_Reward_Personal = ? where Player_ID = ? and Session_ID = ?",
                                (
                                    reward, player_id, session_id
                                ))
                            await db.commit()
                            content += f"\r\n<@{player_id}>'s {thread_id[1]} has been endowed with {reward}!"
                        else:
                            content += f"\r\n<@{player_id}> could not be found in the database!"
                    else:
                        content += f"\r\n<@{player_id}> is not participating in this session!"
                    # Endow the player with their reward

                # Inform the user that the players have been endowed with their rewards

            await interaction.followup.send(content=content)

        except (aiosqlite.Error, TypeError, ValueError) as e:
            # Handle exceptions and inform the user
            logging.exception(f"An error occurred whilst endowing players with rewards: {e}")
            await interaction.followup.send(f"An error occurred: {str(e)}")

    @session_group.command(name='claim', description='Claim rewards for a session!')
    @app_commands.autocomplete(character_name=shared_functions.own_character_select_autocompletion)
    async def claim(self, interaction: discord.Interaction, session_id: int, character_name: str):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild.id}.sqlite") as conn:
                cursor = await conn.cursor()
                await cursor.execute(
                    "SELECT GM_Name, Session_Name, Hammer_Time, Session_Range, Gold, Essence, Easy, Medium, Hard, Deadly, Trials, Alt_Reward_All, Alt_Reward_Party, Session_Thread, Message, Rewards_Message, Rewards_Thread, Fame, Prestige FROM Sessions WHERE Session_ID = ? and GM_Name = ? and IsActive = 0 LIMIT 1",
                    (session_id, interaction.user.name))
                session_info = await cursor.fetchone()
                if not session_info:
                    await interaction.followup.send(
                        f'invalid session ID of {session_id} or you are not the GM of this session.')
                else:
                    (gm_name, session_name, hammer_time, session_range, session_gold, session_essence, session_easy,
                     session_medium, session_hard, session_deadly, session_trials, session_alt_reward_all,
                     session_alt_reward_party, session_session_thread, session_message, session_rewards_message,
                     session_rewards_thread, session_fame, session_prestige) = session_info
                    base_session_info = RewardSessionBaseInfo(
                        session_name=session_name,
                        rewarded_gold=Decimal(session_gold),
                        rewarded_essence=session_essence,
                        rewarded_easy=session_easy,
                        rewarded_medium=session_medium,
                        rewarded_hard=session_hard,
                        rewarded_deadly=session_deadly,
                        rewarded_trials=session_trials,
                        rewarded_alt_reward_all=None,
                        rewarded_alt_reward_party=None,
                        rewarded_fame=session_fame,
                        rewarded_prestige=session_prestige,
                        rewarded_session_thread=None,
                        rewarded_message=None,
                        gm_name=interaction.user.name
                    )
                    await cursor.execute(
                        "SELECT True_Character_Name, level, tier, gold, milestones, trials, Fame, Prestige, Thread_ID from Player_Characters WHERE Character_Name = ? OR Nickname = ?",
                        (character_name, character_name))
                    player_info = await cursor.fetchone()
                    if not player_info:
                        await interaction.followup.send("Could not find player character in the database!")
                        return

                    else:
                        (true_character_name, level, tier, gold, milestones, trials, fame, prestige,
                         thread_id) = player_info
                        await cursor.execute(
                            "SELECT Player_ID, Player_Name, Character_Name, Level, Tier, Effective_Gold, Received_Milestones, Received_Trials, Received_Gold, Received_Fame, Received_Prestige, Received_Essence, Gold_Transaction_ID FROM Sessions_Archive WHERE Session_ID = ? and Player_Name = ?",
                            (session_id, interaction.user.name))
                        reward_info = await cursor.fetchone()
                        if reward_info:
                            (origin_player_id, origin_player_name, origin_character_name, origin_level, origin_tier,
                             origin_effective_gold,
                             origin_received_milestones,
                             origin_received_trials, origin_received_gold, origin_received_fame,
                             origin_received_prestige, origin_received_essence,
                             origin_reward_gold_transaction_id) = reward_info
                            if character_name != origin_character_name:
                                character_recipient_info = (character_name, level, tier, gold, thread_id)
                                embed = discord.Embed(
                                    title=f"are you sure you want to claim rewards for {character_name}?",
                                    description=f"You will be removing rewards from {origin_character_name} \r\nhit accept to confirm")
                                view = ReplaceRewardsView(
                                    bot=self.bot, interaction=interaction, session_id=session_id,
                                    character_origin=origin_character_name,
                                    character_recipient_info=character_recipient_info,
                                    content="", discord_embed=embed,
                                    session_received_rewards=reward_info, session_rewards_dataclass=base_session_info)
                                await view.send_initial_message()
                            else:
                                await interaction.followup.send(
                                    f"you have already claimed rewards for {origin_character_name}!")
                        else:
                            session_reward = await session_reward_calculation(
                                interaction=interaction,
                                session_id=session_id,
                                session_base_info=base_session_info,
                                author_name=interaction.user.name,
                                character_name=character_name,
                                pre_session_level=level,
                                pre_session_tier=tier,
                                pre_session_gold=Decimal(gold),
                                source=f"ClaimingSession Rewards for {session_name}, {session_id}")
                            if isinstance(session_reward, str):
                                await interaction.followup.send(session_reward)
                            else:
                                (session_reward_embed, player_thread) = session_reward
                                log_message = await shared_functions.log_embed(
                                    change=session_reward_embed,
                                    guild=interaction.guild,
                                    thread=player_thread,
                                    bot=self.bot)
                                await shared_functions.character_embed(character_name=character_name,
                                                                       guild=interaction.guild)
                                await interaction.followup.send(embed=log_message)
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"An error occurred whilst claiming rewards for a session: {e}")
            await interaction.followup.send(
                "An error occurred whilst claiming rewards for a session. Please try again later.")

    @session_group.command(name='notify', description='Notify players of a session!')
    async def notify(self, interaction: discord.Interaction, session_id: int, message: str = "Session Notice!"):
        """Notify players about an ACTIVE Session."""
        await interaction.response.defer(thinking=True, ephemeral=True)
        async with aiosqlite.connect(f"pathparser_{interaction.guild.id}.sqlite") as conn:
            try:
                cursor = await conn.cursor()
                await cursor.execute(
                    "Select Hammer_Time, Session_Thread from Sessions where Session_ID = ? And GM_Name = ? and IsActive = 1",
                    (session_id, interaction.user.name))
                session_info = await cursor.fetchone()
                if session_info is None:
                    await interaction.followup.send(
                        f"Invalid Session ID of {session_id} associated with host {interaction.user.name}")
                    return
                else:
                    await cursor.execute("SELECT Player_ID FROM Sessions_Participants WHERE Session_ID = ?",
                                         (session_id,))
                    participants = await cursor.fetchall()
                    if not participants:
                        await interaction.followup.send(f"No participants found for session {session_id}")
                        return
                    else:
                        sessions_channel = interaction.guild.get_channel(session_info[1])
                        if not sessions_channel:
                            sessions_channel = await interaction.guild.fetch_channel(session_info[1])
                        if not sessions_channel:
                            await interaction.followup.send(
                                "Issue with the Sessions Channel set by your Server Admin!!!! Please contact them to fix this issue. Sessions Channel Not Found in the DB!")
                            return
                        else:
                            ping_list = f"NOTICE: "
                            for player in participants:
                                ping_list += f"<@{player[0]}> "
                            if message == "Session Notice!":
                                message = f"Session Notice! Session is in <t:{session_info[0]}:R>"
                            ping_list += f"your GM {interaction.user.name} has the following message for you! \r\n {message}"
                            await sessions_channel.send(content=ping_list,
                                                        allowed_mentions=discord.AllowedMentions(users=True))
                await interaction.followup.send(content="message sent successfully", ephemeral=True)
            except (aiosqlite.Error, TypeError, ValueError) as e:
                logging.exception(f"An error occurred whilst notifying players of a session: {e}")
                await interaction.followup.send(
                    "An error occurred whilst notifying players of a session. Please try again later.")

    @session_group.command(name='display', description='Display all participants and signups for a session!')
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
                    count += 0 if not signups_count else signups_count[0]
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
                    view = SessionDisplayView(
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

    @group_group.command(name='delete', description='delete a group!')
    @app_commands.autocomplete(group_id=shared_functions.group_id_autocompletion)
    async def delete(self, interaction: discord.Interaction, group_id: int):
        """GM: Delete a group from the database."""
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild.id}.sqlite") as conn:
                cursor = await conn.cursor()
                await cursor.execute("SELECT Group_ID, Group_Name, Role_ID FROM Sessions_Group WHERE Group_ID = ?", (group_id,))
                group_info = await cursor.fetchone()
                if group_info is None:
                    await interaction.followup.send(f"Invalid Group ID of {group_id}")
                else:
                    (group_id, group_name, role_id) = group_info
                    await player_commands.delete_group(guild=interaction.guild, group_id=group_id, role_id=role_id)
                    await interaction.followup.send(f"Group {group_name} has been deleted.")
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"An error occurred whilst deleting group {group_id}: {e}")
            await interaction.followup.send("An error occurred whilst deleting a group. Please try again later.")

    @worldanvil_group.command(name='plot', description='Create a new world anvil article!')
    @app_commands.describe(summary="Use a google drive link, or write a summary about the occasion.")
    @app_commands.autocomplete(plot=shared_functions.get_plots_autocomplete)
    async def plot(self, interaction: discord.Interaction, plot: str, summary: str):
        """Notify players about an ACTIVE Session."""
        """Sessions Folder is: b71f939a-f72d-413b-b4d7-4ebff1e162ca"""
        try:
            guild_id = interaction.guild_id
            author = interaction.user.name
            await interaction.response.defer(thinking=True, ephemeral=True)
            print(plot)
            if summary is None:
                await interaction.followup.send(f"No summary available.")
                return
            elif plot[:2] == "1-":
                plot_length = len(plot)
                plot_id = plot[2:plot_length]
                await shared_functions.patch_wa_article(
                    guild_id=guild_id,
                    article_id=plot_id,
                    overview=summary)

                await interaction.followup.send(f"Plot {plot_id} has been edited")
            elif plot[:2] == '2-':
                plot = str.replace(
                    str.replace(str.replace(str.replace(str.replace(str.title(plot), ";", ""), "(", ""), ")", ""), "[",
                                ""),
                    "]", "")

                async with shared_functions.config_cache.lock:
                    configs = shared_functions.config_cache.cache.get(interaction.guild.id)
                    if configs:
                        plot_info = configs.get('WA_Plot_Folder')

                if plot_info is None:
                    await interaction.followup.send(
                        f"An error occurred whilst creating a plot. Please try again later.")
                    return
                else:
                    plot_length = len(plot)
                    plot_name = plot[2:plot_length]
                    await shared_functions.put_wa_article(
                        guild_id=guild_id,
                        category=plot_info,
                        overview=summary,
                        author=author,
                        title=plot_name,
                        template='Plot'
                    )
                    await interaction.followup.send(f"Plot {plot_name} has been created.")
            else:
                await interaction.followup.send(f"Please select a choice from the menu.")
        except (aiosqlite.Error, discord.DiscordException, TypeError, ValueError) as e:
            logging.exception(f"An error occurred whilst creating a plot: {e}")
            await interaction.followup.send("An error occurred whilst creating a plot. Please try again later.")

    @worldanvil_group.command(name='report', description='Create a new world anvil article!')
    @app_commands.describe(summary="Use a google drive link, or write a summary about the occasion.")
    @app_commands.autocomplete(plot=shared_functions.session_autocompletion)
    async def report(self, interaction: discord.Interaction, session_id: int, summary: str, plot: typing.Optional[str]):
        """Report on a historical session"""
        if plot is not None:
            plot = str.replace(
                str.replace(str.replace(str.replace(str.replace(str.title(plot), ";", ""), "(", ""), ")", ""), "[", ""),
                "]", "")
            if ' ' in plot or '-' not in plot:
                plot = await shared_functions.get_plots_autocomplete(interaction, plot)
        await interaction.response.defer(thinking=True, ephemeral=True)
        async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as conn:
            cursor = await conn.cursor()
            await cursor.execute(
                "SELECT GM_Name, Session_Name, Article_Link, Article_ID, History_ID, Related_Plot, Easy, Medium, Hard, Deadly, Trials FROM Sessions WHERE Session_ID = ? AND GM_Name = ? AND IsActive = 0",
                (session_id, interaction.user.name))
            session_info = await cursor.fetchone()
            if session_info is None:
                await interaction.followup.send(f"No completed Session with ID {session_id} could be found!")
            else:
                (gm_name, session_name, article_link, article_id, history_id, related_plot, easy, medium, hard, deadly,
                 trials) = session_info
                plot = related_plot if plot is None else plot
                if article_id is None:
                    significance = min(5, 0 + easy + (2 * medium) + (3 * hard) + (4 * deadly) + (2 * trials))
                    report_info = await shared_functions.put_wa_report(
                        guild_id=interaction.guild_id,
                        session_id=session_id,
                        author=interaction.user.name,
                        overview=summary,
                        plot=plot,
                        significance=significance
                    )
                    if not report_info:
                        await interaction.followup.send(
                            "An error occurred whilst creating a report. Please try again later.")
                    else:
                        (article, timeline) = report_info
                        await cursor.execute(
                            "UPDATE Related_Plot = ? history_id = ? article_id = ? article_link = ? WHERE Session_ID = ?",
                            (plot, timeline['id'], article['id'], article['url'], session_id))
                        await interaction.followup.send(
                            f"Session Report for {session_info[1]} has been created with [{session_id}: {session_name}](<{article['url']}>).")
                else:
                    await shared_functions.patch_wa_report(
                        guild_id=interaction.guild_id,
                        session_id=session_id,
                        overview=summary
                    )
                    await interaction.followup.send(f"Session Report for {session_info[1]} has been edited.")

    @group_group.command(name="display", description="display the overall availability of a group!")
    @app_commands.choices(
        day=[discord.app_commands.Choice(name='Monday', value=1), discord.app_commands.Choice(name='Tuesday', value=2),
             discord.app_commands.Choice(name='Wednesday', value=3),
             discord.app_commands.Choice(name='Thursday', value=4),
             discord.app_commands.Choice(name='Friday', value=5), discord.app_commands.Choice(name='Saturday', value=6),
             discord.app_commands.Choice(name='Sunday', value=7)])
    async def group_availability(
            self,
            interaction: discord.Interaction,
            day: discord.app_commands.Choice[int]):
        """Display the overall availability of a range of groups"""
        guild_id = interaction.guild_id
        await interaction.response.defer(thinking=True, ephemeral=True)
        day_value = day.value
        try:
            async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as conn:
                cursor = await conn.cursor()

                # Decide which query to execute based on whether 'name' is provided
                await cursor.execute("SELECT Distinct(UTC_Offset) from Player_Timecard where Player_Name = ?",
                                     (interaction.user.name,))
                host_offset = await cursor.fetchone()
                host_utc_offset = host_offset[0] if host_offset else 'UTC'
                # Set up pagination variables

                # Create and send the view with the results
                view = DisplayTimeGroupView(
                    user_id=interaction.user.id,
                    guild_id=guild_id,
                    interaction=interaction,
                    day=day_value,
                    utc_offset=host_utc_offset
                )
                await view.update_results()
                await view.create_embed()
                await interaction.followup.send(embed=view.embed, view=view)

        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(
                f"an error occurred displaying milestones: {e}"
            )
            await interaction.followup.send(
                f"An error occurred whilst fetching data. Please try again later.",
                ephemeral=True
            )


# Base Views for displaying a session
# Dual View Type Views
class SessionDisplayView(shared_functions.DualView):
    def __init__(self, user_id: int, guild_id: int, offset: int, limit: int, view_type: int,
                 interaction: discord.Interaction, session_id: int):
        super().__init__(user_id=user_id, guild_id=guild_id, offset=offset, limit=limit, view_type=view_type,
                         interaction=interaction, content="")
        self.max_items = None  # Cache total number of items
        self.view_type = view_type
        self.session_id = session_id
        self.max_participants = None

    async def update_results(self):
        """Fetch the history of prestige requests for the current page."""
        await self.get_max_items()
        participant_limit = min(20, self.max_items - self.offset) if self.view_type == 0 else 20
        signup_limit = max(0, min(20, self.offset + 1 - self.max_participants)) if self.view_type == 0 else 20
        signup_offset = max(0, -20 + self.offset) if self.view_type == 0 else self.offset
        self_results = []
        async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
            cursor = await db.cursor()
            if self.view_type == 0 or self.view_type == 1:
                participant_statement = """SELECT SP.Player_Name, SP.Player_ID, PC.True_Character_Name, SP.Level, SP.Tier, SP.Effective_Wealth, PC.Tradition_Name, PC.Tradition_Link, PC.Template_Name, PC.Template_Link
                                           FROM Sessions_Participants SP  Left Join Player_Characters PC on SP.Character_Name = PC.Character_Name WHERE SP.Session_ID = ?  ORDER BY SP.Player_Name ASC LIMIT ? OFFSET ?"""
                participant_statement_val = (self.session_id, participant_limit, self.offset - 1)
                await cursor.execute(participant_statement, participant_statement_val)
                self_results.extend(await cursor.fetchall())
                print(self_results, participant_limit, self.offset)
            if self.view_type == 0 or self.view_type == 2:
                signup_statement = """SELECT SU.Player_Name, SU.Player_ID, PC.True_Character_Name, SU.Level, SU.Tier, SU.Effective_Wealth, PC.Tradition_Name, PC.Tradition_Link, PC.Template_Name, PC.Template_Link
                                      FROM Sessions_Signups SU  Left Outer Join Player_Characters PC on SU.Character_Name = PC.Character_Name WHERE SU.Session_ID = ? ORDER BY SU.Player_Name ASC LIMIT ? OFFSET ?"""
                val = (self.session_id, signup_limit, signup_offset)
                await cursor.execute(signup_statement, val)
                print(self_results, signup_limit, signup_offset)
                self_results.extend(await cursor.fetchall())
            self.results = self_results

    async def create_embed(self):
        """Create the embed for the titles."""
        current_page = (self.offset // self.limit) + 1
        total_pages = ((await self.get_max_items() - 1) // self.limit) + 1
        title = "Participants Summary" if self.view_type == 1 else "Sign-ups Summary"
        title = "All Players Summary" if self.view_type == 0 else title
        self.embed = discord.Embed(title=title,
                                   description=f"Page {current_page} of {total_pages}")
        for result in self.results:
            (player_name, player_id, character_name, level, tier, effective_gold,
             tradition_name, tradition_link, template_name, template_link) = result
            information = f"**Level**: {level}, **Mythic Tier**: {tier}, **Effective Gold**: {effective_gold}"
            information += f"\r\n**Tradition**: [{tradition_name}]({tradition_link})" if tradition_name else ""
            information += f"\r\n**Template**: [{template_name}]({template_link})" if template_name else ""
            self.embed.add_field(name=character_name, value=information, inline=False)

    async def get_max_items(self):
        """Get the total number of titles."""
        if self.max_items is None:
            async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
                count = 0
                if self.view_type == 0 or self.view_type == 1:
                    cursor = await db.execute("SELECT COUNT(*) FROM Sessions_Participants WHERE Session_ID = ?",
                                              (self.session_id,))
                    participants_count = await cursor.fetchone()
                    count += 0 if not participants_count else participants_count[0]
                    self.max_participants = participants_count[0]
                if self.view_type == 0 or self.view_type == 2:
                    cursor = await db.execute("SELECT COUNT(*) FROM Sessions_Signups WHERE Session_ID = ?",
                                              (self.session_id,))
                    signups_count = await cursor.fetchone()
                    count += 0 if not signups_count else signups_count[0]
                self.max_items = count
        return self.max_items

    async def on_view_change(self):
        self.view_type += 1  # Change the view type
        self.view_type %= 3  # Wrap the view type
        self.max_items = None  # Reset the max items
        await self.get_max_items()  # Update the results


# Base Views for accepting or rejecting a decision
class ReplaceRewardsView(shared_functions.SelfAcknowledgementView):
    def __init__(self,
                 content: str,
                 interaction: discord.Interaction,
                 discord_embed: discord.Embed,
                 session_id: int,
                 character_origin: str,
                 character_recipient_info: tuple,
                 session_received_rewards: aiosqlite.Row,
                 session_rewards_dataclass: RewardSessionBaseInfo,
                 bot: commands.Bot):
        super().__init__(content=content, interaction=interaction)
        self.embed = discord_embed
        self.content = content
        self.session_id = session_id
        self.session_received_rewards = session_received_rewards
        self.session_rewards_info = session_rewards_dataclass
        self.character_origin = character_origin
        self.character_recipient_info = character_recipient_info
        self.bot = bot

    async def accepted(self, interaction: discord.Interaction):
        """Handle the approval logic."""
        # Update the database to mark the proposition as accepted
        # Adjust prestige, log the transaction, notify the requester, etc.
        field = ""
        session_reversal = await session_reward_reversal(
            interaction=interaction,
            session_id=self.session_id,
            character_name=self.character_origin,
            author_name=interaction.user.name,
            session_gold=self.session_rewards_info.rewarded_gold,
            session_info=self.session_received_rewards,
            source=f'Gamemaster Session Removal for {self.session_id}')
        if isinstance(session_reversal, str):
            field += "failed to remove rewards, skipping adjustment. \r\n "
        else:
            (reversal_dataclass, thread_id) = session_reversal
            await shared_functions.log_embed(change=reversal_dataclass, guild=interaction.guild,
                                             thread=thread_id, bot=self.bot)
            await shared_functions.character_embed(
                character_name=self.character_origin,
                guild=interaction.guild)
            (recipient_character_name, recipient_level, recipient_tier, recipient_gold,
             recipient_thread_id) = self.character_recipient_info
            add_rewards = await session_reward_calculation(
                interaction=self.interaction,
                session_id=self.session_id,
                character_name=recipient_character_name,
                author_name=interaction.user.name,
                pre_session_level=recipient_level,
                pre_session_tier=recipient_tier,
                pre_session_gold=recipient_gold,
                source="Session Adjustment",
                session_base_info=self.session_rewards_info
            )
            if isinstance(add_rewards, str):
                field += "failed to calculate rewards, skipping adjustment. \r\n "
            else:
                (add_reward_dataclass, thread_id) = add_rewards
                await shared_functions.log_embed(change=add_reward_dataclass, guild=interaction.guild,
                                                 thread=thread_id, bot=self.bot)
                await shared_functions.character_embed(
                    character_name=recipient_character_name,
                    guild=interaction.guild)

        self.embed = discord.Embed(
            title="Rewards Removed",
            description=f"{interaction.user.name} has decided to remove the rewards from {self.character_origin} and give the rewards to {self.character_recipient_info[0]}.",
            color=discord.Color.green()
        )

    async def create_embed(self):
        """Dummy because this breaks without it, but just sets the embed to the one I made outside, so I don't have to pass as many variables in."""
        self.embed = self.embed


class UpdateGameLinkView(shared_functions.SelfAcknowledgementView):
    def __init__(self,
                 announcement_message: discord.Message,
                 content: str,
                 session_content: str,
                 session_embed: discord.Embed,
                 interaction: discord.Interaction,
                 session_id: int,
                 game_link: str):
        super().__init__(content=content, interaction=interaction)
        self.announcement_message = announcement_message
        self.session_content = session_content
        self.session_embed = session_embed
        self.session_id = session_id
        self.game_link = game_link

    async def accepted(self, interaction: discord.Interaction):
        """Handle the approval logic."""
        # Update the database to mark the proposition as accepted
        # Adjust prestige, log the transaction, notify the requester, etc.
        self.session_embed.url = self.game_link
        print("i got here")

        await self.announcement_message.edit(content=self.session_content, embed=self.session_embed)
        async with aiosqlite.connect(f"pathparser_{interaction.guild.id}.sqlite") as conn:
            cursor = await conn.cursor()
            await cursor.execute("UPDATE Sessions SET Game_Link = ? WHERE Session_ID = ?",
                                 (self.game_link, self.session_id))
            await conn.commit()

    async def create_embed(self):
        """Dummy because this breaks without it, but just sets the embed to the one I made outside, so I don't have to pass as many variables in."""
        self.embed = self.embed


class RemoveRewardsView(shared_functions.SelfAcknowledgementView):
    def __init__(self, content: str, interaction: discord.Interaction, discord_embed: discord.Embed, session_id: int,
                 character_name: str, session_gold: Decimal, session_rewards_info: aiosqlite.Row, bot: commands.Bot):
        super().__init__(content=content, interaction=interaction)
        self.embed = discord_embed
        self.session_id = session_id
        self.character_name = character_name
        self.session_gold = session_gold
        self.session_rewards_info = session_rewards_info
        self.bot = bot

    async def accepted(self, interaction: discord.Interaction):
        """Handle the approval logic."""
        # Update the database to mark the proposition as accepted
        # Adjust prestige, log the transaction, notify the requester, etc.
        self.embed = discord.Embed(
            title="Rewards Removed",
            description=f"{interaction.user.name} has decided to remove the rewards.",
            color=discord.Color.green()
        )
        session_reversal = await session_reward_reversal(
            interaction=interaction,
            session_id=self.session_id,
            character_name=self.character_name,
            author_name=interaction.user.name,
            session_gold=self.session_gold,
            session_info=self.session_rewards_info,
            source=f'Gamemaster Session Removal for {self.session_id}')
        if isinstance(session_reversal, str):
            self.embed.description += f" However, {session_reversal}"
        else:
            (reversal_dataclass, thread_id) = session_reversal
            await shared_functions.log_embed(change=reversal_dataclass, guild=interaction.guild, thread=thread_id,
                                             bot=self.bot)
            await shared_functions.character_embed(character_name=self.character_name, guild=interaction.guild, )

    async def rejected(self, interaction: discord.Interaction):
        """Handle the rejection logic."""
        # Update the database to mark the proposition as rejected
        self.embed = discord.Embed(
            title="Database Reset Rejected",
            description=f"{interaction.user.name} has decided against removing the rewards.",
            color=discord.Color.red()
        )
        # Additional logic such as notifying the requester

    async def create_embed(self):
        """Create the embed for the titles."""
        self.embed = self.embed


# Base Views for handling Session Announcements
class JoinOrLeaveSessionView(discord.ui.View):
    """Base class for views requiring acknowledgment."""

    def __init__(self, session_id: int, guild: typing.Optional[discord.Guild], timeout_seconds: int, session_name: str,
                 content: str):
        super().__init__(timeout=timeout_seconds)
        self.session_id = session_id
        self.session_name = session_name
        self.thread_id = None
        self.guild = guild
        self.content = content
        self.message = None
        self.embed = None

    async def on_timeout(self):
        """Disable buttons when the view times out."""
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(content=self.content, embed=self.embed, view=self)
            except (discord.HTTPException, AttributeError) as e:
                logging.error(
                    f"Failed to edit message on timeout: {e}")

    @discord.ui.button(label='Join', style=discord.ButtonStyle.primary)
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_join(interaction)

    async def handle_join(self, interaction: discord.Interaction):
        # Fetch the user's characters suitable for the session
        character_names = await self.get_suitable_characters(interaction)
        # Create the character selection view

        if isinstance(character_names, list):
            if len(character_names) == 0:
                await interaction.response.send_message(
                    "You do not have a character suitable for this session.",
                    ephemeral=True
                )
            else:
                view = CharacterSelectionView(character_names=character_names, interaction=interaction,
                                              session_id=self.session_id, session_name=self.session_name,
                                              thread_id=self.thread_id)
                await interaction.response.send_message(
                    "Please select a character to join the session:",
                    view=view,
                    ephemeral=True
                )
        else:
            await interaction.response.send_message(
                character_names,
                ephemeral=True
            )

    async def get_suitable_characters(self, interaction: discord.Interaction) -> Union[List[str], str]:
        # Fetch the user's characters
        try:
            print(interaction.user.name)
            async with aiosqlite.connect(f'pathparser_{self.guild.id}.sqlite') as db:
                cursor = await db.cursor()
                # Check if the user has already signed up for the session
                await cursor.execute(
                    "Select Character_Name from Sessions_Signups where Session_ID = ? and Player_ID = ?",
                    (self.session_id, interaction.user.id))
                signups_presence = await cursor.fetchone()
                if signups_presence:
                    return 'You have already signed up for this session.'
                await cursor.execute(
                    "Select Character_Name from Sessions_Participants where Session_ID = ? and Player_ID = ?",
                    (self.session_id, interaction.user.id))
                participants_presence = await cursor.fetchone()
                if participants_presence:
                    return 'You have already signed up for this session.'

                # Fetch the session information
                await cursor.execute(
                    "SELECT Session_Range_ID, Overflow, Session_Thread FROM Sessions WHERE Session_ID = ? And IsActive = 1",
                    (self.session_id,))
                session_info = await cursor.fetchone()

                if not session_info:
                    return 'No active session with that ID could be found.'
                else:
                    (session_range_id, overflow, self.thread_id) = session_info
                    # Fetch the user's characters suitable for the session
                    if overflow == 4:  # All Characters Suitable as Overflow is 4
                        await cursor.execute("SELECT Character_Name FROM Player_Characters WHERE Player_ID = ?",
                                             (interaction.user.id,))
                    else:  # Fetch characters based on the session range
                        await cursor.execute(
                            "Select Min(Level), Max(Level) from Milestone_System where Level_Range_ID = ?",
                            (session_range_id,))
                        level_range = await cursor.fetchone()
                        if level_range[0]:
                            print("found level range", level_range)
                            overflow_validation = await validate_milestone_system_overflow(
                                guild=interaction.guild,
                                overflow=overflow,
                                session_range_id=session_range_id)  # Overflow is typing.Optional[discord.Role]
                            range_results = overflow_validation
                            if range_results:
                                await cursor.execute(
                                    "SELECT Character_Name FROM Player_Characters WHERE Player_ID = ? AND Level >= ? AND Level <= ?",
                                    (interaction.user.id, range_results[1], range_results[2]))
                                character_names = await cursor.fetchall()
                                return [character_name[0] for character_name in character_names]
                            else:  # Overflow is not a role
                                await cursor.execute(
                                    "SELECT Character_Name FROM Player_Characters WHERE Player_ID = ? AND Level >= ? AND Level <= ?",
                                    (interaction.user.id, level_range[0], level_range[1]))
                                character_names = await cursor.fetchall()
                                return [character_name[0] for character_name in character_names]
                        else:  # No level range found in milestone system. Matching Role to user permissions or region.
                            await cursor.execute(
                                "Select name, min_level, max_level from regions_level_range where role_id = ?",
                                (session_range_id,))
                            level_range = await cursor.fetchone()
                            if level_range:
                                print("found region level range", level_range)
                                overflow_validation = await validate_region_system_overflow(
                                    guild=interaction.guild,
                                    overflow=overflow,
                                    session_range_id=session_range_id)  # Overflow is typing.Optional[discord.Role]
                                range_results = overflow_validation
                                print("overflow validation", range_results)
                                if range_results:
                                    await cursor.execute(
                                        "SELECT Character_Name FROM Player_Characters WHERE Player_ID = ? AND Level >= ? AND Level <= ?",
                                        (interaction.user.id, range_results[1], range_results[2]))
                                    character_names = await cursor.fetchall()
                                    return [character_name[0] for character_name in character_names]
                                else:  # Overflow is not a role
                                    print("no overflow validation, using level_restuls", level_range)
                                    await cursor.execute(
                                        "SELECT Character_Name FROM Player_Characters WHERE Player_ID = ? AND Level >= ? AND Level <= ?",
                                        (interaction.user.id, level_range[1], level_range[2]))
                                    character_names = await cursor.fetchall()
                                    return [character_name[0] for character_name in character_names]
                            else:
                                user_valid = interaction.user.get_role(int(session_range_id))
                                if user_valid:
                                    await cursor.execute("SELECT Character_Name FROM Player_Characters WHERE Player_ID = ?",
                                                         (interaction.user.id,))
                                    character_names = await cursor.fetchall()
                                    return [character_name[0] for character_name in character_names]
                                else:
                                    return 'You do not have a character suitable for this session.'
        except aiosqlite.Error as e:
            logging.exception(
                f"Failed to fetch characters for user {interaction.user.id} in guild {interaction.guild.id}: {e}")

    @discord.ui.button(label='Leave', style=discord.ButtonStyle.danger)
    async def leave_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_leave(interaction)

    async def handle_leave(self, interaction: discord.Interaction):
        # Remove the user's character from the session participants in the database
        async with (aiosqlite.connect(f'pathparser_{interaction.guild.id}.sqlite')) as db:
            cursor = await db.cursor()
            await cursor.execute(
                "Select Character_Name from Sessions_Participants where Session_ID = ? and Player_ID = ?",
                (self.session_id, interaction.user.id))
            participants_presence = await cursor.fetchone()
            await cursor.execute("Select Character_Name from Sessions_Signups where Session_ID = ? and Player_ID = ?",
                                 (self.session_id, interaction.user.id))
            signups_presence = await cursor.fetchone()
            if participants_presence or signups_presence:
                await player_commands.player_leave_session(guild=interaction.guild, session_id=self.session_id,
                                                           player_name=interaction.user.name)
                await interaction.response.send_message(
                    "You have left the session.",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "You have not signed up for this session.",
                    ephemeral=True
                )


class CharacterSelectionView(discord.ui.View):
    def __init__(self, character_names: List[str], interaction: discord.Interaction, session_id: int, session_name: str,
                 thread_id: int):
        super().__init__(timeout=900)  # 15 minutes
        self.interaction = interaction
        self.session_id = session_id
        self.session_name = session_name
        self.thread_id = thread_id
        for name in character_names:
            button = discord.ui.Button(label=name, style=discord.ButtonStyle.primary)
            button.callback = self.create_button_callback(name)
            self.add_item(button)

    def create_button_callback(self, name):
        async def button_callback(interaction: discord.Interaction):
            await self.handle_character_selection(interaction, name)

        return button_callback

    async def handle_character_selection(self, interaction: discord.Interaction, character_name: str):
        # Prompt for reminder preference
        print("reacting to the button?")
        view = ReminderPreferenceView(character_name, self.interaction, self.session_id)
        await player_commands.player_signup(
            guild=interaction.guild,
            session_id=self.session_id,
            session_name=self.session_name,
            player_id=interaction.user.id,
            character_name=character_name,
            warning_duration=None,
            thread_id=self.thread_id
        )
        await interaction.response.send_message(
            f"You have selected {character_name}. Would you like to receive a reminder before the session?",
            view=view,
            ephemeral=True
        )


class ReminderPreferenceView(discord.ui.View):
    def __init__(self, character_name: str, interaction: discord.Interaction, session_id: int):
        super().__init__(timeout=900)
        self.character_name = character_name
        self.interaction = interaction
        self.session_id = session_id

    @discord.ui.button(label='60 minutes', style=discord.ButtonStyle.danger)
    async def sixty_minutes_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("You will receive a reminder 60 minutes before the session.",
                                                ephemeral=True)
        await self.update_notification_warning(interaction, 60)

    @discord.ui.button(label='30 minutes', style=discord.ButtonStyle.danger)
    async def thirty_minutes_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("You will receive a reminder 30 minutes before the session.",
                                                ephemeral=True)
        await self.update_notification_warning(interaction, 30)

    @discord.ui.button(label='at start', style=discord.ButtonStyle.danger)
    async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("You will receive a reminder at the start of the session.",
                                                ephemeral=True)
        await self.update_notification_warning(interaction, 0)

    @discord.ui.button(label='none', style=discord.ButtonStyle.danger)
    async def none_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("You will not receive a reminder.",
                                                ephemeral=True)
        await self.update_notification_warning(interaction, -1)

    async def update_notification_warning(self, interaction: discord.Interaction, warning_duration: int):
        try:
            async with aiosqlite.connect(f'pathparser_{interaction.guild.id}.sqlite') as db:
                await db.execute(
                    "UPDATE Sessions_Signups SET Notification_Warning = ? WHERE Session_ID = ? AND Player_ID = ?",
                    (warning_duration, self.session_id, interaction.user.id)
                )
                await db.commit()
        except aiosqlite.Error as e:
            logging.error(
                f"Failed to update notification warning for user {interaction.user.id} in guild {interaction.guild.id}: {e}")

        # Add the character to the session participants in the database


class DisplayTimeGroupView(discord.ui.View):
    def __init__(
            self,
            user_id: int,
            guild_id: int,
            day: int,
            utc_offset: str,
            interaction: discord.Interaction):
        super().__init__(timeout=180)
        self.limit = 5
        self.offset = 0
        self.max_items = None
        self.group_results = None
        self.range_id = None
        self.user_id = user_id
        self.guild_id = guild_id
        self.day = day
        self.view_type = 1
        self.message = None
        self.interaction = interaction
        self.results = []
        self.embed = None
        self.max_range_id = None
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
            await interaction.edit_original_response(
                embed=self.embed,
                view=self
            )
            with open(f'C:\\pathparser\\plots\\group_{interaction.user.name}_plot.png', 'rb') as f:
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
                    self.range_id -= 5 if self.range_id > 5 else 0
            await self.update_results()
            await self.create_embed()
            await self.update_buttons()
            await interaction.edit_original_response(
                embed=self.embed,
                view=self
            )
            with open(f'C:\\pathparser\\plots\\group_{interaction.user.name}_plot.png', 'rb') as f:
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
            with open(f'C:\\pathparser\\plots\\group_{self.interaction.user.name}_plot.png', 'rb') as f:
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
            os.remove(f'C:\\pathparser\\plots\\timecard_{self.user_id}_plot.png')
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
            await interaction.edit_original_response(
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
                    await interaction.followup.send("You are on the last page.", ephemeral=True)
                    return
                else:
                    self.range_id += 5 if self.range_id + 5 <= self.max_range_id else self.max_range_id
            await self.update_results()
            await self.create_embed()
            await self.update_buttons()
            await interaction.edit_original_response(
                embed=self.embed,
                view=self
            )
            with open(f'C:\\pathparser\\plots\\group_{interaction.user.name}_plot.png', 'rb') as f:
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
                if self.range_id >= self.max_range_id:

                    await interaction.followup.send("You are on the last  page.", ephemeral=True)
                    return
                else:
                    self.range_id = self.max_range_id
            await self.update_results()
            await self.create_embed()
            await self.update_buttons()
            await interaction.edit_original_response(
                embed=self.embed,
                view=self
            )
            with open(f'C:\\pathparser\\plots\\group_{interaction.user.name}_plot.png', 'rb') as f:
                picture = discord.File(f)
                await interaction.followup.send(file=picture, ephemeral=True)
        except Exception as e:
            logging.error(f"Failed to move to the last page: {e}")
            raise

    async def update_buttons(self):
        """Update the enabled/disabled state of buttons based on the current page."""
        try:
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
        """Fetch the history of prestige request  for the current page."""

        statement = """
                        SELECT Group_ID, Group_Name, Role_ID, Player_Name, Host_Character, Description
                        FROM Sessions_Group Order by Group_ID Limit ? Offset ? 
                    """
        async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
            cursor = await db.cursor()
            self.range_id = self.range_id if self.range_id else 0
            print(self.range_id, self.range_id)
            await cursor.execute(statement, (5, self.range_id - 1))
            self.results = await cursor.fetchall()

            self.group_results = []
            for group_id in self.results:
                group_availability = await player_commands.fetch_group_availability_from_db(
                    guild_id=self.guild_id,
                    day=self.day,
                    group_id=group_id[0],
                    utc_offset=self.utc_offset)

                self.group_results.append(group_availability)

            await create_group_timecard_plot(dataset=self.group_results, user_id=self.interaction.user.name, day=self.day)

    async def create_embed(self):
        """Create the embed for the titles."""
        current_page = (self.offset // self.limit) + 1
        total_pages = ((await self.get_max_items() - 1) // self.limit) + 1
        self.embed = discord.Embed(
            title=f"Group Requests",
            description=f"Page {current_page} of {total_pages}")
        for item in self.results:
            (group_id, group_name, role_id, host_player_name, host_character, description) = item
            self.embed.add_field(name=f'**Group**: {group_id}: {group_name}',
                                 value=f'**Host**: {host_player_name}, **Character**: {host_character}, **Role**: <@&{role_id}>\r\n**Description**: {description}',
                                 inline=False)

    async def get_max_items(self):
        """Get the total number of titles."""
        if self.max_items is None:
            async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
                cursor = await db.execute("SELECT COUNT(*) FROM Sessions_Group")
                count = await cursor.fetchone()
                self.max_range_id = count[0]
        return self.max_range_id


logging.basicConfig(
    level=logging.INFO,  # Set the minimum logging level
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='application.log',  # Log to a file
    filemode='a'  # Append to the file
)
