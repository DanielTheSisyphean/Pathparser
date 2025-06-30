import json
import logging
import random
import typing
import math
from math import floor
from typing import List, Optional, Tuple, Union
import discord
import re
import unbelievaboat
from unidecode import unidecode
from discord.ext import commands
from discord import app_commands
import datetime
import os
import aiosqlite
import shared_functions
from commands import RP_Commands
from shared_functions import name_fix
from decimal import Decimal, ROUND_HALF_UP


class CalculationAidFunctionError(Exception):
    pass


def safe_int(value, default=0):
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def safe_int_atk(value, default=0):
    try:
        try:
            value = int(value)
        except ValueError:
            start_index = value.find('+')
            end_index_slash = value.find('/') if '/' in value else 0
            end_index_space = value.find(' ') if ' ' in value else 0
            end_index = min(end_index_slash, end_index_space) if end_index_slash and end_index_space else max(
                end_index_slash, end_index_space) if end_index_slash or end_index_space else None
            if start_index != -1 and end_index:
                value = int(value[start_index + 1:end_index])
            else:
                value = 0
        return int(value)
    except (ValueError, TypeError):
        return default


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


# LEVEL INFORMATION
async def get_max_level(guild_id: int) -> Optional[int]:
    async with shared_functions.config_cache.lock:
        configs = shared_functions.config_cache.cache.get(guild_id)
        if configs:
            row = configs.get('Level_Cap')
            if row:
                return row
            else:
                logging.error(f"Level cap not found for guild {guild_id}")
                return None


def normal_sheet_attributes(skills_data: dict) -> dict:
    attributes = {
        'strength': safe_int(skills_data.get('Str')),
        'strength_mod': safe_int(skills_data.get('StrMod')),
        'dexterity': safe_int(skills_data.get('Dex')),
        'dexterity_mod': safe_int(skills_data.get('DexMod')),
        'constitution': safe_int(skills_data.get('Con')),
        'constitution_mod': safe_int(skills_data.get('ConMod')),
        'intelligence': safe_int(skills_data.get('Int')),
        'intelligence_mod': safe_int(skills_data.get('IntMod')),
        'wisdom': safe_int(skills_data.get('Wis')),
        'wisdom_mod': safe_int(skills_data.get('WisMod')),
        'charisma': safe_int(skills_data.get('Cha')),
        'charisma_mod': safe_int(skills_data.get('ChaMod')),
        'fortitude': safe_int(skills_data.get('Fort')),
        'reflex': safe_int(skills_data.get('Reflex')),
        'will': safe_int(skills_data.get('Will')),
        'initiative': safe_int(skills_data.get('Init')),
        'hit_points': safe_int(skills_data.get('HP')),
        'armor_class': safe_int(skills_data.get('AC')),
        'touch_armor_class': safe_int(skills_data.get('ACTouch')),
        'cmd': safe_int(skills_data.get('CMD')),
        'ranged': safe_int_atk(skills_data.get('RBAB')),
        'melee': safe_int_atk(skills_data.get('MBAB')),
        'cmb': safe_int_atk(skills_data.get('CMB')),
    }
    return attributes


def experimental_sheet_attributes(skills_data: dict) -> dict:
    attributes = {
        'strength': safe_int(skills_data.get('strength_score')),
        'strength_mod': safe_int(skills_data.get('strength_mod')),
        'dexterity': safe_int(skills_data.get('dexterity_score')),
        'dexterity_mod': safe_int(skills_data.get('dexterity_mod')),
        'constitution': safe_int(skills_data.get('constitution_score')),
        'constitution_mod': safe_int(skills_data.get('constitution_mod')),
        'intelligence': safe_int(skills_data.get('intelligence_score')),
        'intelligence_mod': safe_int(skills_data.get('intelligence_mod')),
        'wisdom': safe_int(skills_data.get('wisdom_score')),
        'wisdom_mod': safe_int(skills_data.get('wisdom_mod')),
        'charisma': safe_int(skills_data.get('charisma_score')),
        'charisma_mod': safe_int(skills_data.get('charisma_mod')),
        'fortitude': safe_int(skills_data.get('fortitude_total')),
        'reflex': safe_int(skills_data.get('reflex_total')),
        'will': safe_int(skills_data.get('will_total')),
        'initiative': safe_int(skills_data.get('init_total')),
        'hit_points': safe_int(skills_data.get('hp')),
        'armor_class': safe_int(skills_data.get('ac_total')),
        'touch_armor_class': safe_int(skills_data.get('ac_touch')),
        'cmd': safe_int(skills_data.get('ac_cmd')),
        'ranged': safe_int_atk(skills_data.get('rab_ab')),
        'melee': safe_int_atk(skills_data.get('mab_ab')),
        'cmb': safe_int_atk(skills_data.get('cmb_ab')),
    }
    return attributes


async def normal_sheet_skills(db: aiosqlite.Connection, skills_data: dict, character_name: str) -> str:
    cursor = await db.cursor()
    for i in range(1, 36):
        skill_key = f"Skill{i:02}"
        if skill_key in skills_data:
            skill_name = skills_data.get(skill_key)
            ability = skills_data.get(f"{skill_key}Ab", "Unknown")
            skill_rank = safe_int(skills_data.get(f"{skill_key}Rank"))
            ability_mod = attributes.get(f"{ability.lower()}Mod", 0)
            skill_modifier = safe_int(skills_data.get(f"{skill_key}Mod"))

            # Insert or replace skill
            await cursor.execute(
                '''
                INSERT OR REPLACE INTO Player_Characters_Skills (
                    character_name, skill_name, ability, skill_rank, skill_modifier
                ) VALUES (?, ?, ?, ?, ?)
                ''',
                (
                    character_name, skill_name, ability, skill_rank, skill_modifier
                )
            )
    await db.commit()
    return "Skills updated successfully."


async def experimental_sheet_skills(db: aiosqlite.Connection, skills_data: dict, character_name: str) -> str:
    cursor = await db.cursor()
    for i in range(1, 36):
        skill_key = f"skill_{i}_name"
        if skill_key in skills_data:
            skill_name = skills_data.get(skill_key)
            ability = skills_data.get(f"skill_{i}_abil", "Unknown")
            skill_rank = safe_int(skills_data.get(f"skill_{i}_prof"))
            skill_modifier = safe_int(skills_data.get(f"skill_{i}_skill_mod"))

            # Insert or replace skill
            await cursor.execute(
                '''
                INSERT OR REPLACE INTO Player_Characters_Skills (
                    character_name, skill_name, ability, skill_rank, skill_modifier
                ) VALUES (?, ?, ?, ?, ?)
                ''',
                (
                    character_name, skill_name, ability, skill_rank, skill_modifier
                )
            )
    return "Skills updated successfully."


def calculate_milestones(
        milestone_values: Tuple[Optional[int], Optional[int], Optional[int], Optional[int]],
        multipliers: List[int],
        misc: int
) -> int:
    milestones = [
        (value if value is not None else 0) * multiplier
        for value, multiplier in zip(milestone_values, multipliers)
    ]
    return sum(milestones) + misc


async def get_new_level_info(
        cursor,
        total_milestones: int,
        maximum_level: int
) -> Optional[Tuple[int, int, int]]:
    await cursor.execute(
        "SELECT Level, Minimum_Milestones, Milestones_to_level FROM Milestone_System "
        "WHERE Minimum_Milestones <= ? AND Level <= ? "
        "ORDER BY Minimum_Milestones DESC LIMIT 1",
        (total_milestones, maximum_level)
    )
    row = await cursor.fetchone()
    if row is not None:
        return row
    logging.error(
        f"No level information found for total milestones {total_milestones} "
        f"and level cap {maximum_level}"
    )
    return None


async def level_calculation(
        guild_id: int,
        character_name: str,
        personal_cap: int,
        level: int,
        base: int,
        easy: int,
        medium: int,
        hard: int,
        deadly: int,
        misc: int,
        guild=None,
        author_id=None,
        region=None

) -> Tuple[int, int, int, int, int, int]:
    """
    Calculates the new level and milestone requirements for a character.

    Returns:
    - Tuple[int, int, int, int, int, int]: Contains:
        - New level
        - Total milestones
        - Minimum milestones for current level
        - Milestones to reach next level
        - Milestones required to reach next level
        - Awarded milestone total
    Raises:
    - CalculationAidFunctionError: If an error occurs during calculation.
    """
    try:
        logging.debug(f"Starting level calculation for character '{character_name}' in guild {guild_id}")

        # Validate inputs
        if level < 1:
            raise ValueError("Level must be at least 1.")

        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as conn:
            cursor = await conn.cursor()

            # Get maximum level cap
            max_level = await get_max_level(guild_id)
            if max_level is None:
                logging.error(f"Max level cap not found for guild {guild_id}")
                raise CalculationAidFunctionError(f"Max level cap not found for guild {guild_id}")
            logging.debug(f"Max level cap for guild {guild_id} is {max_level}")

            # Get milestone information
            await cursor.execute(
                "SELECT easy, medium, hard, deadly FROM Milestone_System WHERE level = ?",
                (level,)
            )
            milestone_information = await cursor.fetchone()
            if milestone_information is None:
                logging.error(f"Milestone information not found for level {level}")
                raise CalculationAidFunctionError(f"Milestone information not found for level {level}")
            logging.debug(f"Milestone information for level {level}: {milestone_information}")

            # Unpack milestone information
            easy_milestone, medium_milestone, hard_milestone, deadly_milestone = milestone_information

            # Calculate milestones
            multipliers = [easy, medium, hard, deadly]
            milestone_values = (easy_milestone, medium_milestone, hard_milestone, deadly_milestone)
            awarded_milestone_total = calculate_milestones(milestone_values, multipliers, misc)
            logging.debug(f"Calculated awarded milestone total: {awarded_milestone_total}")

            # Determine maximum level
            maximum_level = min(max_level, personal_cap) if personal_cap else max_level
            print("This is maximum level for", maximum_level, character_name)
            logging.debug(f"Maximum level for character '{character_name}': {maximum_level}")

            # Get new level information
            total_milestones = base + awarded_milestone_total
            new_level_info = await get_new_level_info(cursor, total_milestones, maximum_level)
            if new_level_info is None:
                raise CalculationAidFunctionError(
                    f"Error in level calculation for character '{character_name}': No level information found"
                )
            new_level, min_milestones, milestones_to_level = new_level_info
            logging.debug(
                f"New level information: Level={new_level}, "
                f"Minimum_Milestones={min_milestones}, Milestones_to_level={milestones_to_level}"
            )

            # Update player character
            milestones_required = min_milestones + milestones_to_level - total_milestones
            logging.info(
                f"Updated character '{character_name}': Level={new_level}, "
                f"Milestones={total_milestones}, Milestones_Required={milestones_required}"
            )

            # If level_ranges is required and guild and author_id are provided
            if guild and author_id and new_level != level:
                await level_ranges(cursor, guild, author_id, level, new_level, region, character_name)

            return (
                new_level,
                total_milestones,
                min_milestones,
                milestones_to_level,
                milestones_required,
                awarded_milestone_total
            )
    except (aiosqlite.Error, TypeError, ValueError) as e:
        logging.exception(f"Error in level calculation for character '{character_name}': {e}")
        raise CalculationAidFunctionError(f"Error in level calculation for character '{character_name}': {e}")
    except Exception as e:
        logging.exception(f"Unexpected error in level calculation for character '{character_name}': {e}")
        raise CalculationAidFunctionError(
            f"Unexpected error in level calculation for character '{character_name}': {e}")


async def level_ranges(cursor: aiosqlite.Cursor, guild, author_id: int, level: int, new_level: int,
                       region: str, character_name: str) -> None:
    try:
        print("This is the level", level, new_level, region, author_id)
        await cursor.execute("SELECT Level, Level_Range_Name, Level_Range_ID FROM Milestone_System WHERE level = ?",
                             (new_level,))
        new_role = await cursor.fetchone()

        if new_role is None:
            logging.error(f"Role not found for level {new_level}")
            return None
        else:
            member = guild.get_member(author_id)
            new_level_range_role = guild.get_role(int(new_role[2]))

            try:
                await member.add_roles(new_level_range_role)

                await cursor.execute("SELECT Level_Range_Name FROM Milestone_System WHERE level = ?", (level,))
                old_role = await cursor.fetchone()

                if old_role is not None:
                    await cursor.execute(
                        "SELECT Min(Level), Max(Level) FROM Milestone_System where Level_Range_Name = ?",
                        (old_role[0],))
                    old_role_range = await cursor.fetchone()

                    await cursor.execute(
                        "SELECT Character_Name from Player_Characters where Player_ID = ? AND level BETWEEN ? AND ?",
                        (author_id, old_role_range[0], old_role_range[1]))
                    character = await cursor.fetchone()
                    print(character)

                    if character is None:
                        old_level_range_role = guild.get_role(int(old_role[0]))

                        await member.remove_roles(old_level_range_role)
                        print("Removed role", old_level_range_role)

                if region:
                    await cursor.execute(
                        "SELECT Min_Level, Max_Level, Role_ID FROM Regions_Level_Range WHERE Name = ? AND Min_Level <= ? AND Max_Level >= ?",
                        (region, new_level, new_level))
                    region_role = await cursor.fetchone()
                    print("got region role", region_role)
                    if region_role:
                        (min_level, max_level, new_role_id) = region_role
                        if level < min_level or level > max_level:
                            region_role_object = guild.get_role(int(new_role_id))
                            await member.add_roles(region_role_object)
                            print('added region role', region_role_object)
                            await cursor.execute(
                                "SELECT Min_level, Max_Level, Role_ID FROM Regions_Level_Range WHERE Name = ? and Min_Level <= ? and Max_Level >= ?",
                                (region, level, level))
                            old_region_role_info = await cursor.fetchone()
                            if old_region_role_info:
                                (min_level_old, max_level_old, old_region_role_id) = old_region_role_info
                                print("got old region info", old_region_role_info, region, author_id)
                                await cursor.execute("""
                                                    SELECT count(character_name)
                                                    FROM Player_Characters
                                                    WHERE level BETWEEN ? AND ? AND 
                                                    Player_ID = ? and Region = ? and character_name != ? limit 1;""",
                                                     (min_level_old, max_level_old, author_id, region, character_name))
                                character_in_old_range = await cursor.fetchone()
                                print("got character in old range", character_in_old_range, min_level_old,
                                      max_level_old, )
                                if character_in_old_range:
                                    (characters_in_range,) = character_in_old_range
                                    print("got characters in range", characters_in_range)
                                    if not characters_in_range:
                                        await member.remove_roles(guild.get_role(int(old_region_role_id)))
                                        print("removed old region role", old_region_role_id)
            except discord.Forbidden:
                logging.error(f"Bot does not have permissions to add roles to <@{author_id}>")
                return None

    except (aiosqlite.Error, TypeError, ValueError) as e:
        logging.exception(f"Error in level ranges for <@{author_id}> with error: {e}")
        return None


# Mythic Information
async def get_max_mythic(guild_id: int, level: int) -> Optional[int]:
    try:
        async with shared_functions.config_cache.lock:
            configs = shared_functions.config_cache.cache.get(guild_id)
            if configs:
                max_tier = configs.get('Tier_Cap')
                rate_limit_1 = configs.get('Tier_Rate_Limit_1')
                rate_limit_2 = configs.get('Tier_Rate_Limit_2')
                rate_limit_breakpoint = configs.get('Tier_Rate_Limit_Breakpoint')
        if rate_limit_2 is not None and rate_limit_1 is not None and rate_limit_breakpoint is not None:
            rate_limit_max = floor(int(level) / int(rate_limit_1)) if int(level) < int(
                rate_limit_breakpoint) else floor(
                int(level) / int(rate_limit_2))
        else:
            rate_limit_max = 99

        if max_tier is not None:
            return min(int(rate_limit_max), int(max_tier))
        else:
            logging.error(f"Tier cap not found for guild {guild_id}")
            return None
    except aiosqlite.Error as e:
        logging.exception(f"issue with mythic calculation: {e}")
        return None


async def get_new_tier_info(
        cursor,
        total_milestones: int,
        maximum_level: int
) -> Optional[Tuple[int, int, int]]:
    await cursor.execute(
        "SELECT Level, Minimum_Milestones, Milestones_to_level FROM Milestone_System "
        "WHERE Minimum_Milestones <= ? AND Level <= ? "
        "ORDER BY Minimum_Milestones DESC LIMIT 1",
        (total_milestones, maximum_level)
    )
    row = await cursor.fetchone()
    if row is not None:
        return row
    logging.error(
        f"No level information found for total milestones {total_milestones} "
        f"and level cap {maximum_level}"
    )
    return None


async def mythic_calculation(
        character_name: str,
        level: int, trials: int,
        trial_change: int,
        tier: int,
        guild_id: int) -> Tuple[int, int, int, int]:
    try:
        logging.info(
            f"Calculating mythic for character '{character_name}', level {level}, trials {trials}, trial_change {trial_change}"
        )
        trial_total = trials + trial_change

        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as conn:
            cursor = await conn.cursor()

            # fetch server configurations.
            async with shared_functions.config_cache.lock:
                configs = shared_functions.config_cache.cache.get(guild_id)
                if configs:
                    max_tier = configs.get('Tier_Cap')
                    rate_limit_1 = configs.get('Tier_Rate_Limit_1')
                    rate_limit_2 = configs.get('Tier_Rate_Limit_2')
                    rate_limit_breakpoint = configs.get('Tier_Rate_Limit_Breakpoint')

            # check if configurations are correct
            if not max_tier:
                raise ValueError("Tier_Cap not found in Admin table.")

            if not rate_limit_1:
                raise ValueError("Tier_Rate_limit_1 not found in Admin table.")

            if not rate_limit_2:
                raise ValueError("Tier_Rate_limit_2 not found in Admin table.")

            if not rate_limit_breakpoint:
                raise ValueError("Tier_Rate_limit_Breakpoint not found in Admin table.")

            # Determine the tier rate limit modifier
            if level < rate_limit_breakpoint:
                tier_rate_limit_modifier = rate_limit_1
            else:
                tier_rate_limit_modifier = rate_limit_2

            if tier_rate_limit_modifier == 0:
                raise ValueError("Tier rate limit modifier cannot be zero.")

            print("max_tier", max_tier)
            # Calculate tier candidate and tier max
            tier_candidate = level // tier_rate_limit_modifier
            tier_max = min(tier_candidate, max_tier)

            # Fetch mythic tier information
            await cursor.execute("""
                SELECT Tier, Trials, Trials_Required
                FROM AA_Trials
                WHERE Trials <= ? AND Tier <= ?
                ORDER BY Trials DESC
                LIMIT 1
            """, (trial_total, tier_max))
            new_mythic_information = await cursor.fetchone()

            if new_mythic_information:
                new_tier, trials_minimum, trials_required = new_mythic_information
                trials_needed_for_next_tier = trials_minimum + trials_required
                trials_remaining = trials_needed_for_next_tier - trial_total
            else:
                logging.warning(f"No mythic information found for trial_total={trial_total}, tier_max={tier_max}")
                new_tier = 0
                trials_remaining = 0

            # Ensure trials_remaining is not negative
            trials_remaining = max(trials_remaining, 0)
            new_tier = 0 if tier == 0 and trial_change == 0 else new_tier
            # Return mythic tier, total trials, trials remaining, and trial change
            logging.info(
                f"Mythic calculation complete: new tier of {new_tier}, total_trials of {trial_total}, trials_remaining of {trials_remaining}, trial change: {trial_change}")
            return new_tier, trial_total, trials_remaining, trial_change

    except (aiosqlite.Error, TypeError, ValueError, ZeroDivisionError) as e:
        logging.exception(f"Error in mythic calculation for {character_name}: {e}")
        raise CalculationAidFunctionError(f"Error in mythic calculation for {character_name}: {e}")
    except Exception as e:
        logging.exception(f"Unexpected error in mythic calculation for {character_name}: {e}")
        raise CalculationAidFunctionError(f"Unexpected error in mythic calculation for {character_name}: {e}")


async def gold_calculation(
        guild_id: int,
        author_name: str,
        author_id: int,
        character_name: str,
        level: int,
        oath: str,
        gold: Decimal,
        gold_value: Decimal,
        gold_value_max: Decimal,
        gold_change: Decimal,
        gold_value_change: typing.Optional[Decimal],
        gold_value_max_change: typing.Optional[Decimal],
        source: str,
        reason: str,
        ignore_limitations: bool = False,
        is_transaction: bool = True,
        related_transaction: int = None
) -> Tuple[Decimal, Decimal, Decimal, Decimal, int]:
    time = datetime.datetime.now()
    try:
        gold_value_calc = gold_value + gold_value_change if isinstance(gold_value_change, Decimal) else Decimal(
            gold_value) + Decimal(gold_change)

        if gold_change > Decimal(0):
            if oath == 'Offerings' and not ignore_limitations:
                # Only half the gold change is applied
                adjusted_gold_change = (gold_change * Decimal('0.5')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            else:
                # Other oaths gain gold normally. When receiving gold sent by another player, ignore limitations 
                adjusted_gold_change = gold_change
        else:
            # For gold loss, apply the change directly
            adjusted_gold_change = gold_change
            evaluate_gold_value_change = False if gold_value_change is None else gold_value_change > 0
            if evaluate_gold_value_change:
                if oath in ('Poverty', 'Absolute'):
                    max_gold = (Decimal('80') * Decimal(level) ** 2)
                    print(oath, gold_value, gold_value_change, gold, max_gold)
                    if gold_value + gold_value_change >= gold + max_gold:
                        # Cannot gain more gold
                        raise ValueError(
                            f"Gold Value cannot exceed max of {max_gold}, you have {gold_value - gold}, this gives you {gold_value + gold_value_change - gold}")

        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as conn:
            cursor = await conn.cursor()

            final_gold_value_change = (
                gold_value_change.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                if isinstance(gold_value_change, Decimal) else
                adjusted_gold_change.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))

            final_gold_max_value_change = (
                gold_value_max_change.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                if isinstance(gold_value_max_change, Decimal) else
                adjusted_gold_change.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            )

            gold_total = (Decimal(gold) + Decimal(adjusted_gold_change)).quantize(Decimal('0.01'),
                                                                                  rounding=ROUND_HALF_UP)
            new_effective_gold = (
                    Decimal(gold_value) + Decimal(final_gold_value_change).quantize(Decimal('0.01'),
                                                                                    rounding=ROUND_HALF_UP))
            gold_value_max_total = (
                    Decimal(gold_value_max) + Decimal(final_gold_max_value_change)).quantize(Decimal('0.01'),
                                                                                             rounding=ROUND_HALF_UP)

            # Ensure gold values are not negative
            if gold_total < 0 or new_effective_gold < 0:
                raise ValueError(
                    f"Gold cannot be negative: Gold of {gold_total}, effective gold of {new_effective_gold}.")

            # Before inserting into the database, convert Decimal to string after rounding
            adjusted_gold_change_str = str(adjusted_gold_change.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
            gold_value_change_str = str(final_gold_value_change)

            gold_value_total_change_str = str(final_gold_max_value_change)
            # Update the database
            if is_transaction:
                sql = """
                INSERT INTO A_Audit_Gold(
                    Author_Name, Author_ID, Character_Name, Gold_Value,
                    Effective_Gold_Value, Effective_Gold_Value_Max, Reason, Related_Transaction_ID,
                    Source_Command, Time
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
                val = (
                    author_name,
                    author_id,
                    character_name,
                    adjusted_gold_change_str,
                    gold_value_change_str,
                    gold_value_total_change_str,
                    reason,
                    related_transaction,
                    source,
                    time
                )
                await cursor.execute(sql, val)
                await conn.commit()
                await cursor.execute("SELECT Max(transaction_id) FROM A_Audit_Gold")
                transaction_id_row = await cursor.fetchone()
                transaction_id = transaction_id_row[0]
            else:
                transaction_id = 0
            logging.info(f"Gold updated for character '{character_name}', transaction_id: {transaction_id}.")

            return adjusted_gold_change, gold_total, new_effective_gold, gold_value_max_total, transaction_id
    except Exception as e:
        logging.exception(f"Error in gold calculation for character '{character_name}': {e}")
        raise CalculationAidFunctionError(f"Error in gold calculation for character '{character_name}': {e}")


def calculate_essence(character_name: str, essence: int, essence_change: int,
                      accepted_date: typing.Optional[str]):
    try:
        if accepted_date is not None:
            try:
                start_date = datetime.datetime.strptime(accepted_date.split('.')[0], '%Y-%m-%d %H:%M:%S')
            except ValueError:
                start_date = datetime.datetime.strptime(accepted_date, '%Y-%m-%d %H:%M')

            current_date = datetime.datetime.now()
            date_difference = (current_date - start_date).days

            # Determine the essence multiplier
            if 90 <= date_difference < 120:
                essence_multiplier = 2
            elif date_difference >= 120:
                essence_multiplier = 2 + floor((date_difference - 90) / 30)
                essence_multiplier = min(essence_multiplier, 4)
            else:
                essence_multiplier = 1

            essence_change *= essence_multiplier

        logging.info(f"Calculating essence for character '{character_name}'")
        essence_total = essence + essence_change
        return essence_total, essence_change

    except (aiosqlite.Error, TypeError, ValueError) as e:
        logging.exception(f"Error in essence calculation for {character_name} with error: {e}")
        raise CalculationAidFunctionError(f"Error in essence calculation for {character_name} with error: {e}")


def calculate_fame(character_name: str, fame: int, fame_change: int,
                   prestige: int, prestige_change: int):
    try:
        logging.info(f"Calculating fame for character '{character_name}'")
        fame_total = fame + fame_change
        prestige_total = prestige + prestige_change if prestige + prestige_change <= fame_total else fame_total
        final_prestige_change = prestige_total - prestige
        return_value = fame_total, fame_change, prestige_total, final_prestige_change
        return return_value
    except (aiosqlite.Error, TypeError, ValueError) as e:
        logging.exception(f"Error in essence calculation for {character_name} with error: {e}")
        raise CalculationAidFunctionError(f"Error in essence calculation for {character_name} with error: {e}")


async def ubb_inventory_check(guild_id: int, author_id: int, item_id: str, amount: int) -> int:
    client = unbelievaboat.Client(os.getenv('UBB_TOKEN'))
    try:
        logging.info(f"Retrieving inventory item {item_id} for user {author_id}")
        inventory = await client.get_inventory_item(guild_id, author_id, int(item_id))
        inventory_remaining = 0 if not inventory else inventory.quantity
        amount = min(amount, inventory_remaining)
        await client.close()
        return amount
    except unbelievaboat.errors.HTTPError:
        logging.exception(f"Failed to retrieve inventory item {item_id} for user {author_id}")
        return 0


async def server_inventory_check(guild_id: int, player_id: int, item_id: str, amount: int) -> int:
    try:
        logging.info(f"Retrieving server inventory item {item_id}")
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as conn:
            cursor = await conn.cursor()
            await cursor.execute("SELECT item_quantity FROM RP_Players_Items WHERE Player_ID = ? and Item_ID = ?",
                                 (player_id, item_id,))
            item = await cursor.fetchone()
            if item is None:
                logging.error(f"Item {item_id} not found in in inventory")
                return 0
            item_quantity = min(item[0], amount)
            return item_quantity
    except unbelievaboat.errors.HTTPError:
        logging.exception(f"Failed to retrieve server inventory item {item_id}")
        return 0


async def stg_character_embed(guild_id, character_name) -> (Union[Tuple[discord.Embed, str], str]):
    try:
        # 7 7 1
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as conn:
            cursor = await conn.cursor()
            await cursor.execute(
                "SELECT player_name, player_id, True_Character_Name, Titles, Description, Oath, Level, "
                "Tier, Milestones, Milestones_Required, Trials, Trials_Required, Color, Mythweavers, "
                "Image_Link, Backstory"
                " FROM A_STG_Player_Characters WHERE Character_Name = ?", (character_name,))
            character_info = await cursor.fetchone()
            (player_name, player_id, character_name, titles, description, oath, level, tier, milestones,
             milestones_required,
             trials, trials_required, color, mythweavers, image_link, backstory) = character_info
            int_color = int(color[1:], 16)
            description_field = f" "
            if titles is not None:
                description_field += f"**Other Names**: {titles} \r\n"  # Titles
            if description is not None:  # Description
                description_field += f"**Description**: {description}"
            titled_character_name = character_name
            embed = discord.Embed(title=f"{titled_character_name}", url=f'{character_info[13]}',
                                  description=f"{description_field}",  # Character Name, Mythweavers, Description
                                  color=int_color)
            embed.set_author(name=f'{player_name}')  # Player Name
            embed.set_thumbnail(url=f'{image_link}')  # Image Link
            embed.add_field(name="Information",
                            value=f'**Level**: {level}, '
                                  f'**Mythic Tier**: {tier}, ',
                            # Level, Tier, Fame, Prestige
                            inline=False)
            embed.add_field(name="Experience",
                            value=f'**Milestones**: {milestones}, '
                                  f'**Remaining**: {milestones_required}')  # Milestones, Remaining Milestones
            embed.add_field(name="Mythic",
                            value=f'**Trials**: {trials}, '
                                  f'**Remaining**: {trials_required}')  # Trials, Remaining Trials
            message = f"<@{character_info[1]}>"
            check_backstory = shared_functions.drive_word_document(backstory)
            if backstory:
                if backstory.startswith("http"):
                    document_id = shared_functions.extract_document_id(backstory)
                    if document_id is None:
                        if oath == 'Offerings':
                            embed.set_footer(text=f'{oath}, Could not parse Document Link!',
                                             icon_url=f'https://i.imgur.com/dSuLyJd.png')
                        elif oath == 'Poverty':
                            embed.set_footer(text=f'{oath}, Could not parse Document Link!',
                                             icon_url=f'https://i.imgur.com/4Fr9ZnZ.png')
                        elif oath == 'Absolute':
                            embed.set_footer(text=f'{oath}, Could not parse Document Link!',
                                             icon_url=f'https://i.imgur.com/ibE5vSY.png')
                        else:
                            embed.set_footer(text=f'Could not parse Document Link!')
                    else:
                        embed.add_field(name="Backstory", value=f"{backstory}", inline=False)
                        if oath == 'Offerings':
                            embed.set_footer(text=f'{oath}', icon_url=f'https://i.imgur.com/dSuLyJd.png')
                        elif oath == 'Poverty':
                            embed.set_footer(text=f'{oath}', icon_url=f'https://i.imgur.com/4Fr9ZnZ.png')
                        elif oath == 'Absolute':
                            embed.set_footer(text=f'{oath} Poverty', icon_url=f'https://i.imgur.com/ibE5vSY.png')
                else:
                    if oath == 'Offerings':
                        embed.set_footer(text=f'{backstory}', icon_url=f'https://i.imgur.com/dSuLyJd.png')
                    elif oath == 'Poverty':
                        embed.set_footer(text=f'{backstory}', icon_url=f'https://i.imgur.com/4Fr9ZnZ.png')
                    elif oath == 'Absolute':
                        embed.set_footer(text=f'{backstory} Poverty', icon_url=f'https://i.imgur.com/ibE5vSY.png')
                    else:
                        embed.set_footer(text=f'{backstory}')
            else:
                if oath == 'Offerings':
                    embed.set_footer(text=f'{oath}', icon_url=f'https://i.imgur.com/dSuLyJd.png')
                elif oath == 'Poverty':
                    embed.set_footer(text=f'{oath}', icon_url=f'https://i.imgur.com/4Fr9ZnZ.png')
                elif oath == 'Absolute':
                    embed.set_footer(text=f'{oath}', icon_url=f'https://i.imgur.com/ibE5vSY.png')

            return_message = embed, message

    except (aiosqlite.Error, TypeError, ValueError) as e:
        logging.exception(f"An error occurred whilst building character embed for '{character_name}': {e}")
        return_message = f"An error occurred whilst building character embed for '{character_name}'."
    return return_message


async def update_character_name(guild_id: int, character_name: str, new_character_name: str) -> tuple[bool, str]:
    try:
        return_string = f"Updating character name for '{character_name}' to '{new_character_name}' turbo failed."
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as conn:
            cursor = await conn.cursor()
            return_string = f"Updating character name for '{character_name}' to '{new_character_name}' for Sessions_Archive"
            await cursor.execute(
                "UPDATE Sessions_Archive SET Character_Name = ? WHERE Character_Name = ?",
                (new_character_name, character_name))
            await conn.commit()
            return_string = f"Updating character name for '{character_name}' to '{new_character_name}' for Sessions_Group"
            await cursor.execute(
                "UPDATE Sessions_Group SET Host_Character = ? WHERE Host_Character = ?",
                (new_character_name, character_name))
            await conn.commit()
            return_string = f"Updating character name for '{character_name}' to '{new_character_name}' for Sessions_Participants"
            await cursor.execute(
                "UPDATE Sessions_Participants SET Character_Name = ? WHERE Character_Name = ?",
                (new_character_name, character_name))
            await conn.commit()
            return_string = f"Updating character name for '{character_name}' to '{new_character_name}' for A_Audit_All"
            await cursor.execute(
                "UPDATE A_Audit_All SET Character_Name = ? WHERE Character_Name = ?",
                (new_character_name, character_name))
            await conn.commit()
            return_string = f"Updating character name for '{character_name}' to '{new_character_name}' for A_Audit_Gold"
            await cursor.execute(
                "UPDATE A_Audit_Gold SET Character_Name = ? WHERE Character_Name = ?",
                (new_character_name, character_name))
            await conn.commit()
            return_string = f"Updating character name for '{character_name}' to '{new_character_name}' for A_Audit_Prestige"
            await cursor.execute(
                "UPDATE A_Audit_Prestige SET Character_Name = ? WHERE Character_Name = ?",
                (new_character_name, character_name))
            await conn.commit()
            return_string = f"Updating character name for '{character_name}' to '{new_character_name}' for Leadership"
            await cursor.execute(
                "UPDATE KB_Leadership SET Character_Name = ? WHERE Character_Name = ?",
                (new_character_name, character_name))
            await conn.commit()
            return_string = f"Update {character_name} to {new_character_name} is successful"
            return True, return_string
    except (aiosqlite.Error, TypeError, ValueError) as e:
        logging.exception(f"An error occurred whilst updating character name for '{character_name}': {e}")
        return False, return_string


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
        finally:
            return

    @character_group.command(name='move', description="Change Region")
    @app_commands.autocomplete(region=shared_functions.region_autocomplete)
    @app_commands.autocomplete(character=shared_functions.own_character_select_autocompletion)
    async def change_region(self, interaction: discord.Interaction, region: str, character: str, reason: str):
        await interaction.response.defer(thinking=True, ephemeral=False)
        guild_id = interaction.guild_id
        author_id = interaction.user.id
        author_name = interaction.user.name
        time = datetime.datetime.now()
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
                changer_changes = shared_functions.CharacterChange(
                    character_name=character_name,
                    author=interaction.user.name,
                    region=region,
                    source='Character Edit')
                await shared_functions.log_embed(guild=interaction.guild, change=changer_changes, bot=self.bot,
                                                 thread=thread)
                await interaction.followup.send(f"Character {character} moved from {old_region} to {region}")
                await shared_functions.character_embed(guild=interaction.guild, character_name=character)
        except aiosqlite.Error as e:
            logging.exception(f"Error in character move for {character}: {e}")
            await interaction.followup.send(f"Error in character move for {character}: {e}")

    @character_group.command(name='register', description='register a character')
    @app_commands.describe(oath="Determining future gold gain from sessions and gold claims.")
    @app_commands.choices(oath=[discord.app_commands.Choice(name='No Oath', value=1),
                                discord.app_commands.Choice(name='Oath of Offerings', value=2),
                                discord.app_commands.Choice(name='Oath of Poverty', value=3),
                                discord.app_commands.Choice(name='Oath of Absolute Poverty', value=4)])
    @app_commands.describe(nickname='a shorthand way to look for your character in displays')
    async def register(self, interaction: discord.Interaction, character_name: str, mythweavers: str, image_link: str,
                       nickname: str = None,
                       titles: str = None, description: str = None, oath: discord.app_commands.Choice[int] = 1,
                       color: str = '#5865F2', backstory: str = None):
        """Command to handle registering a character for a player"""
        await interaction.response.defer(thinking=True, ephemeral=False)

        guild_id = interaction.guild_id
        author = interaction.user.name
        author_id = interaction.user.id
        time = datetime.datetime.now()

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
                    validate_mythweavers = shared_functions.validate_mythweavers(mythweavers)
                    validate_worldanvil = shared_functions.validate_worldanvil(mythweavers)

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

                            async with shared_functions.config_cache.lock:
                                configs = shared_functions.config_cache.cache.get(guild_id)
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
                            Image_Link, Backstory, Created_Date) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""

                            val = (
                                author, author_id, character_name, true_character_name,
                                nickname, titles, description,
                                oath_name, starting_level, 0, base, milestones_to_level, 0, 0, color, mythweavers,
                                image_link, backstory, time)
                            await cursor.execute(sql, val)
                            await conn.commit()
                            embed = await stg_character_embed(guild_id, character_name)

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
    @app_commands.autocomplete(character_name=shared_functions.own_character_select_autocompletion)
    @app_commands.describe(oath="Determining future gold gain from sessions and gold claims.")
    @app_commands.choices(oath=[discord.app_commands.Choice(name='No Oath', value=1),
                                discord.app_commands.Choice(name='Offerings', value=2),
                                discord.app_commands.Choice(name='Poverty', value=3),
                                discord.app_commands.Choice(name='Absolute', value=4),
                                discord.app_commands.Choice(name='No Change', value=5)])
    @app_commands.describe(new_nickname='a shorthand way to look for your character in displays')
    async def edit(self, interaction: discord.Interaction, character_name: str, new_character_name: str = None,
                   mythweavers: str = None,
                   image_link: str = None, new_nickname: str = None, titles: str = None, description: str = None,
                   oath: discord.app_commands.Choice[int] = 5, color: str = None):
        guild_id = interaction.guild_id
        guild = interaction.guild
        author = interaction.user.name
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
                    sql = "SELECT True_Character_Name, Nickname, Titles, Description, Mythweavers, Image_Link, Oath, Color, Level, Tier, Milestones, Milestones_Required, Trials, Trials_required, Character_Name from A_STG_Player_Characters where Player_Name = ? AND (Character_Name = ? OR  Nickname = ?)"
                    val = (author, character_name, character_name)
                    await cursor.execute(sql, val)
                    results = await cursor.fetchone()
                    if results is None:
                        await interaction.followup.send(
                            f"Cannot find any {character_name} owned by {author} with the supplied name or nickname.")
                    else:
                        (stg_true_character_name, stg_nickname, stg_titles, stg_description, stg_mythweavers,
                         stg_image_link, stg_oath, stg_color, stg_level, stg_tier, stg_milestones,
                         stg_milestones_required, stg_trials, stg_trials_required, stg_character_name) = results
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
                            validate_mythweavers = shared_functions.validate_mythweavers(mythweavers)
                            validate_worldanvil = shared_functions.validate_worldanvil(mythweavers)
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
                                                 "Color = ? "
                                                 "where Character_Name = ?", (
                                                     true_character_name, new_character_name, new_nickname, titles,
                                                     description, mythweavers, image_link, oath_name, color,
                                                     character_name))
                            await conn.commit()
                            embed = await stg_character_embed(guild_id, new_character_name)
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
                        shared_functions.autocomplete_cache.cache.clear()
                        character_changes = shared_functions.CharacterChange(character_name=new_character_name,
                                                                             author=author,
                                                                             source='Character Edit')
                    else:
                        true_character_name, new_character_name = name_fix(info_true_character_name)
                        character_changes = shared_functions.CharacterChange(character_name=new_character_name,
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
                        validate_mythweavers = shared_functions.validate_mythweavers(mythweavers)
                        validate_worldanvil = shared_functions.validate_worldanvil(mythweavers)
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
                                "update Player_Characters set True_Character_Name = ?, Character_Name = ?, Nickname = ?, Titles = ?, Description = ?, Mythweavers = ?, Image_Link = ?, Oath = ?, Color = ? where Character_Name = ?",
                                (
                                    true_character_name, new_character_name, new_nickname, titles, description,
                                    mythweavers,
                                    image_link, oath_name, color, character_name))
                            await conn.commit()
                            validate_update = await update_character_name(guild_id, new_character_name,
                                                                          new_character_name)
                            await shared_functions.character_embed(character_name=new_character_name, guild=guild)
                            log_embed = await shared_functions.log_embed(
                                change=character_changes,
                                bot=self.bot,
                                guild=guild,
                                thread=info_thread_id
                            )
                            if validate_update[0]:
                                await interaction.followup.send(embed=log_embed)
                            if new_character_name or titles or image_link:
                                embed = discord.Embed(title=f"{true_character_name}", url=f'{mythweavers}',
                                                      description=f"Other Names: {info_titles}",
                                                      color=int(color[1:], 16))
                                embed.set_author(name=f'{interaction.user.name}')
                                embed.set_thumbnail(url=f'{image_link}')
                                async with shared_functions.config_cache.lock:
                                    configs = shared_functions.config_cache.cache.get(guild_id)
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
    @app_commands.autocomplete(character_name=shared_functions.own_character_select_autocompletion)
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
                    view = RetirementView(character_name=character_name, user_id=interaction.user.id, guild_id=guild_id,
                                          interaction=interaction, content=content)
                    await view.send_initial_message()
            except (aiosqlite.Error, TypeError, ValueError) as e:
                logging.exception(f"An error occurred in the retire command whilst looking for '{character_name}': {e}")
                await interaction.followup.send(
                    f"An error occurred whilst looking for '{character_name}'. Error: {e}.",
                    ephemeral=True
                )

    @character_group.command(name='levelup', description='level up your character')
    @app_commands.autocomplete(character_name=shared_functions.own_character_select_autocompletion)
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
                        "SELECT Character_Name, Personal_Cap, Level, Milestones, tier, trials, Thread_ID, region FROM Player_Characters WHERE Player_Name = ? AND (Character_Name = ? OR Nickname = ?)",
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
                        print(max_level, personal_cap, server_max_level)
                        if level >= max_level:
                            await interaction.followup.send(
                                f"{character_name} is already at the maximum level of {max_level}.",
                                ephemeral=True
                            )
                        else:
                            async with shared_functions.config_cache.lock:
                                configs = shared_functions.config_cache.cache.get(guild_id)
                                if configs:
                                    item_id = configs.get('UBB_Medium_Job')
                                    custom_store = configs.get('Use_Custom_Store')
                            if not custom_store:
                                item = await ubb_inventory_check(guild_id, interaction.user.id, item_id, amount)
                            else:
                                item = await server_inventory_check(guild_id, interaction.user.id, item_id, amount)
                            if item == 0:
                                await interaction.followup.send(
                                    f"Insufficient Medium Jobs to level up {character_name}.",
                                    ephemeral=True
                                )
                            else:
                                used = 0
                                new_level_info = (0, 0, 0, 0, 0)
                                while used < item and level <= max_level:
                                    used += 1
                                    new_level_info = await level_calculation(
                                        level=level,
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
                                    level = new_level_info[0]
                                    base = new_level_info[1]
                                client = unbelievaboat.Client(os.getenv('UBB_TOKEN'))

                                mythic_results = await mythic_calculation(
                                    character_name=character_name,
                                    level=level,
                                    trials=trials,
                                    trial_change=0,
                                    guild_id=guild_id,
                                    tier=tier
                                )
                                character_updates = shared_functions.UpdateCharacterData(
                                    level_package=(level, base, new_level_info[4]),
                                    character_name=character_name
                                )
                                if tier != mythic_results[0]:
                                    character_updates.mythic_package = (
                                        mythic_results[0], mythic_results[1], mythic_results[3])
                                await shared_functions.update_character(
                                    guild_id=guild_id,
                                    change=character_updates
                                )
                                await shared_functions.character_embed(
                                    character_name=character_name,
                                    guild=guild)
                                character_changes = shared_functions.CharacterChange(
                                    character_name=character_name,
                                    author=author,
                                    source='Level Up',
                                    level=level,
                                    milestone_change=base - starting_base,
                                    milestones_total=base,
                                    milestones_remaining=new_level_info[4]
                                )
                                if not custom_store:
                                    await client.delete_inventory_item(guild_id, interaction.user.id, item_id, used)
                                    await client.close()
                                else:
                                    await RP_Commands.handle_use(
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
                                character_log = await shared_functions.log_embed(character_changes, guild,
                                                                                 logging_thread_id, self.bot)
                                await interaction.followup.send(embed=character_log, ephemeral=True)
                except aiosqlite.Error as e:
                    logging.exception(f"A SQLite error occurred in the levelup command for: '{character_name}!: {e}")
                    await interaction.followup.send(
                        f"A SQLite error occurred in the levelup command for: '{character_name}'. Error: {e}.",
                        ephemeral=True
                    )
                except unbelievaboat.errors.HTTPError as e:
                    logging.exception(f"An error occurred contacting unbelievabot API! check {item_id}!: {e}")
                    await interaction.followup.send(
                        f"An error occurred contacting unbelievabot API! check {item_id}!: Error: {e}.",
                        ephemeral=True
                    )
        else:
            await interaction.followup.send("You must use at least one job.")
            return

    @character_group.command(name='trialup', description='Apply mythic tiers to your character')
    @app_commands.autocomplete(character_name=shared_functions.own_character_select_autocompletion)
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
                            async with shared_functions.config_cache.lock:
                                configs = shared_functions.config_cache.cache.get(guild_id)
                                if configs:
                                    item_id = configs.get('UBB_Mythic_Trial')
                                    use_custom_store = configs.get('Use_Custom_Store')
                            if not use_custom_store:
                                item = await ubb_inventory_check(guild_id, interaction.user.id, item_id, amount)
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

                                character_updates = shared_functions.UpdateCharacterData(
                                    mythic_package=(tier, trials, trials_remaining),
                                    character_name=character_name
                                )
                                await shared_functions.update_character(
                                    guild_id=guild_id,
                                    change=character_updates
                                )
                                await shared_functions.character_embed(
                                    character_name=character_name,
                                    guild=guild)
                                character_changes = shared_functions.CharacterChange(
                                    character_name=character_name,
                                    author=author,
                                    source='Trial Up!',
                                    tier=tier,
                                    trial_change=used,
                                    trials_remaining=trials_remaining,
                                    trials=trials)

                                character_log = await shared_functions.log_embed(
                                    character_changes,
                                    guild,
                                    logging_thread_id,
                                    self.bot)
                                await interaction.followup.send(embed=character_log, ephemeral=True)
                                if not use_custom_store:
                                    client = unbelievaboat.Client(os.getenv('UBB_TOKEN'))
                                    await client.delete_inventory_item(guild_id, interaction.user.id, item_id, used)
                                    await client.close()
                                else:
                                    await RP_Commands.handle_use(
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
                except unbelievaboat.errors.HTTPError as e:
                    logging.exception(f"An error occurred contacting unbelievabot API! check {item_id}!: {e}")
                    await interaction.followup.send(
                        f"An error occurred contacting unbelievabot API! check {item_id}!: Error: {e}.",
                        ephemeral=True
                    )
        else:
            await interaction.followup.send("You must use at least one mythic trial.")

    @character_group.command(name='pouch', description='Use a gold pouch to enrich your character')
    @app_commands.autocomplete(character_name=shared_functions.own_character_select_autocompletion)
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
                            async with shared_functions.config_cache.lock:
                                configs = shared_functions.config_cache.cache.get(guild_id)
                                if configs:
                                    item_id = configs.get('UBB_Gold_Pouch')
                                    custom_store = configs.get('Use_Custom_Store')
                            if not custom_store:
                                item = await ubb_inventory_check(guild_id, interaction.user.id, item_id, 1)
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
                                    client = unbelievaboat.Client(os.getenv('UBB_TOKEN'))
                                    if not custom_store:
                                        await client.delete_inventory_item(guild_id, interaction.user.id, item_id)
                                        await client.close()
                                    else:
                                        await RP_Commands.handle_use(
                                            db=conn,
                                            interaction=interaction,
                                            user_id=interaction.user.id,
                                            item_id=item_id
                                        )

                                    character_updates = shared_functions.UpdateCharacterData(

                                        gold_package=(
                                            calculated_gold, calculated_gold_value, calculated_gold_value_max),
                                        character_name=character_name)

                                    await shared_functions.update_character(
                                        guild_id=guild_id,
                                        change=character_updates)

                                    await shared_functions.character_embed(
                                        character_name=character_name,
                                        guild=guild)

                                    character_changes = shared_functions.CharacterChange(
                                        character_name=character_name,
                                        author=author,
                                        source=f'Pouch with transaction id of {transaction_id}',
                                        gold_change=calculated_difference,
                                        gold=calculated_gold,
                                        gold_value=calculated_gold_value)

                                    character_log = await shared_functions.log_embed(
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
            except unbelievaboat.errors.HTTPError as e:
                logging.exception(f"An error occurred contacting unbelievabot API! check {item_id}!: {e}")
                await interaction.followup.send(
                    f"An error occurred contacting unbelievabot API! check {item_id}!: Error: {e}.",
                    ephemeral=True
                )

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
            view = TitleShopView(
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
    @app_commands.autocomplete(title=shared_functions.title_autocomplete)
    @app_commands.choices(gender=[discord.app_commands.Choice(name='Masculine', value=1),
                                  discord.app_commands.Choice(name='Feminine', value=2)])
    @app_commands.autocomplete(character_name=shared_functions.own_character_select_autocompletion)
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

                        async with shared_functions.config_cache.lock:
                            configs = shared_functions.config_cache.cache.get(guild_id)
                            if configs:
                                custom_store = configs.get('Use_Custom_Store')
                        if not custom_store:
                            item_validation = await ubb_inventory_check(
                                guild_id,
                                interaction.user.id,
                                title_id,
                                1)
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
                            if not custom_store:
                                client = unbelievaboat.Client(os.getenv('UBB_TOKEN'))
                                await client.delete_inventory_item(guild_id, interaction.user.id, title_id)
                                await client.close()
                            else:
                                await RP_Commands.handle_use(
                                    db=conn,
                                    interaction=interaction,
                                    user_id=interaction.user.id,
                                    item_id=title_id)
                            await shared_functions.character_embed(
                                character_name=character_name,
                                guild=guild)
                            character_changes = shared_functions.CharacterChange(
                                character_name=character_name,
                                author=author,
                                source=f'Entitle applying the title of {title_name}',
                                fame=total_fame,
                                fame_change=adjusted_fame,
                                prestige=total_prestige,
                                prestige_change=adjusted_prestige)
                            character_log = await shared_functions.log_embed(
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
    @app_commands.autocomplete(character_name=shared_functions.own_character_select_autocompletion)
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
                            await shared_functions.character_embed(
                                character_name=character_name,
                                guild=guild)
                            character_changes = shared_functions.CharacterChange(
                                character_name=character_name,
                                author=author,
                                source=f'Entitle swapping the gender of {player_title}')
                            character_log = await shared_functions.log_embed(character_changes, guild,
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
            view = PrestigeShopView(user_id=interaction.user.id, guild_id=guild_id, offset=offset, limit=limit,
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
    @app_commands.autocomplete(character_name=shared_functions.own_character_select_autocompletion)
    @app_commands.autocomplete(name=shared_functions.fame_autocomplete)
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
                view = PropositionViewRecipient(
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
    @app_commands.autocomplete(character_name=shared_functions.own_character_select_autocompletion)
    @app_commands.autocomplete(name=shared_functions.fame_autocomplete)
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
                view = PrestigeHistoryView(
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
    @app_commands.autocomplete(character_name=shared_functions.own_character_select_autocompletion)
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
                    SELECT Character_Name, Milestones, Level, tier, Trials, Thread_ID, Region
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

                (character_name_db, milestones, level, tier, trials, thread_id, region) = character_info

                # Update the personal cap in the database
                await cursor.execute(
                    "UPDATE Player_Characters SET Personal_Cap = ? WHERE Character_Name = ?",
                    (level_cap, character_name_db)
                )
                await conn.commit()

                # Initialize character changes
                character_changes = shared_functions.CharacterChange(
                    character_name=character_name_db,
                    author=author_name,
                    source=f'Cap Adjustment to {level_cap}'
                )
                if level_cap != level:
                    # Perform level calculation
                    character_updates = shared_functions.UpdateCharacterData(character_name=character_name_db)
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

                    # update the character
                    await shared_functions.update_character(change=character_updates, guild_id=guild_id)
                # Create and send the log embed
                character_log = await shared_functions.log_embed(character_changes, guild, thread_id, self.bot)
                await interaction.followup.send(embed=character_log, ephemeral=True)

                # Create and send the character embed
                character_embed = await shared_functions.character_embed(character_name=character_name_db, guild=guild)
                if isinstance(character_embed, str):
                    await interaction.followup.send(
                        f"An error occurred while fetching character information for '{character_name_db}'.",
                        ephemeral=True
                    )
                else:
                    (embed, embed_message_content, embed_channel_id) = character_embed
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
    @app_commands.autocomplete(item=rp_home_autocomplete)
    @app_commands.autocomplete(character_name=shared_functions.own_character_select_autocompletion)
    @app_commands.autocomplete(settlement=shared_functions.settlement_autocomplete)
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
                async with shared_functions.config_cache.lock:
                    configs = shared_functions.config_cache.cache.get(guild_id)
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
                async with shared_functions.build_home_cache.lock:
                    shared_functions.build_home_cache.cache[guild_id] = {thread.id, (6, interaction.user.id, thread_message.id)}

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
    @app_commands.autocomplete(character_name=shared_functions.own_character_select_autocompletion)
    @app_commands.autocomplete(settlement=shared_functions.settlement_autocomplete)
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

                async with shared_functions.config_cache.lock:
                    configs = shared_functions.config_cache.cache.get(guild_id)
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
                async with shared_functions.build_home_cache.lock:
                    guild_cache = shared_functions.build_home_cache.cache.get[guild_id]
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
    @app_commands.autocomplete(character_name=shared_functions.own_character_select_autocompletion)
    @app_commands.autocomplete(settlement=shared_functions.settlement_autocomplete)
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
                async with shared_functions.config_cache.lock:
                    configs = shared_functions.config_cache.cache.get(guild_id)
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
                if image:
                    embed.set_image(url=image)
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
    @app_commands.autocomplete(character_name=shared_functions.character_select_autocompletion)
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
                view = CharacterDisplayView(
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
                view = LevelRangeDisplayView(
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
    @app_commands.autocomplete(character_name=shared_functions.own_character_select_autocompletion)
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
                        async with shared_functions.config_cache.lock:
                            configs = shared_functions.config_cache.cache.get(guild_id)
                            if configs:
                                category = configs.get('WA_Backstory_Category')

                        if not category:
                            await interaction.followup.send(
                                "Backstory category not found in the database.",
                                ephemeral=True
                            )
                            return
                        else:
                            article = await shared_functions.put_wa_article(
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
                            await shared_functions.character_embed(
                                character_name=character_name,
                                guild=interaction.guild)
                            character_changes = shared_functions.CharacterChange(
                                character_name=character_name,
                                author=interaction.user.name,
                                source=f'Backstory creation',
                                backstory=article['url'])
                            character_log = await shared_functions.log_embed(character_changes, interaction.guild,
                                                                             logging_thread_id, self.bot)
                            await interaction.followup.send(embed=character_log, ephemeral=True)
                    else:
                        updated_article = await shared_functions.patch_wa_article(guild_id=guild_id,
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
    @app_commands.autocomplete(character_name=shared_functions.own_character_select_autocompletion)
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
                                character_changes = shared_functions.UpdateCharacterData(
                                    character_name=character_name,
                                    gold_package=(gold_total, gold_value_total, gold_max_value_total)
                                )
                                await shared_functions.update_character(change=character_changes, guild_id=guild_id)
                                character_changes = shared_functions.CharacterChange(
                                    character_name=character_name,
                                    author=author,
                                    source=f'Gold Buy of {expenditure} with an expected value of {market_value}',
                                    gold_change=difference,
                                    gold=gold_total,
                                    gold_value=gold_value_total,
                                    transaction_id=transaction_id
                                )
                                await shared_functions.character_embed(character_name=character_name, guild=guild)
                                character_log = await shared_functions.log_embed(character_changes, guild,
                                                                                 logging_thread_id, self.bot)
                                async with shared_functions.config_cache.lock:
                                    configs = shared_functions.config_cache.cache.get(interaction.guild_id)
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
                                    gold_spent_string = shared_functions.get_gold_breakdown(expenditure)
                                    market_value_string = shared_functions.get_gold_breakdown(market_value)
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
    @app_commands.autocomplete(character_from=shared_functions.own_character_select_autocompletion)
    @app_commands.autocomplete(character_to=shared_functions.character_select_autocompletion)
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
                                    view = GoldSendView(
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
    @app_commands.autocomplete(character_name=shared_functions.character_select_autocompletion)
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
                view = GoldHistoryView(
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
    @app_commands.autocomplete(character_name=shared_functions.own_character_select_autocompletion)
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
                        character_updates = shared_functions.UpdateCharacterData(
                            character_name=character_name,
                            gold_package=(gold_total, gold_value_total, gold_max_value_total)
                        )
                        await shared_functions.update_character(change=character_updates, guild_id=guild_id)
                        character_changes = shared_functions.CharacterChange(
                            character_name=character_name,
                            author=interaction.user.name,
                            source=f'Gold Consume of {amount} for {reason}',
                            gold_change=difference,
                            gold=gold_total,
                            gold_value=gold_value_total,
                            transaction_id=transaction_id
                        )
                        character_log = await shared_functions.log_embed(character_changes, interaction.guild,
                                                                         logging_thread_id, self.bot)
                        await shared_functions.character_embed(character_name=character_name, guild=interaction.guild)
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
    @app_commands.autocomplete(character_name=shared_functions.own_character_select_autocompletion)
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
                        character_updates = shared_functions.UpdateCharacterData(
                            character_name=character_name,
                            gold_package=(gold_total, gold_value_total, gold_max_value_total)
                        )
                        await shared_functions.update_character(change=character_updates, guild_id=guild_id)
                        character_changes = shared_functions.CharacterChange(
                            character_name=character_name,
                            author=interaction.user.name,
                            source=f'Gold Claim of {amount} for {reason}',
                            gold_change=difference,
                            gold=gold_total,
                            gold_value=gold_value_total,
                            transaction_id=transaction_id
                        )
                        character_log = await shared_functions.log_embed(character_changes, interaction.guild,
                                                                         logging_thread_id, self.bot)
                        await shared_functions.character_embed(character_name=character_name, guild=interaction.guild)
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
    @app_commands.autocomplete(character_name=shared_functions.own_character_select_autocompletion)
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
    @app_commands.autocomplete(character_name=shared_functions.own_character_select_autocompletion)
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
                    view = AttributesView(
                        user_id=interaction.user.id,
                        guild_id=interaction.guild_id,
                        modifiers=combat_dict
                    )
                    await interaction.followup.send(embed=embed, view=view)
        except (aiosqlite.Error, TypeError, ValueError) as e:
            await interaction.followup.send(f"An error occurred in the defences command: {e}")
            logging.exception(f"An error occurred in the defences command: {e}")

    @mythweavers_group.command(name="skills", description="display the skills from your mythweavers sheet.")
    @app_commands.autocomplete(character_name=shared_functions.own_character_select_autocompletion)
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
                    view = AttributesView(
                        user_id=interaction.user.id,
                        guild_id=interaction.guild_id,
                        modifiers=skill_dictionary
                    )
                    await interaction.followup.send(embed=embed, view=view)

        except (aiosqlite.Error, TypeError, ValueError) as e:
            await interaction.followup.send(f"An error occurred in the skills command: {e}")
            logging.exception(f"An error occurred in the skills command: {e}")

    @mythweavers_group.command(name="attributes", description="display the attributes from your mythweavers sheet.")
    @app_commands.autocomplete(character_name=shared_functions.own_character_select_autocompletion)
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
                    view = AttributesView(
                        user_id=interaction.user.id,
                        guild_id=interaction.guild_id,
                        modifiers=attributes_dict
                    )
                    await interaction.followup.send(embed=embed, view=view)
        except (aiosqlite.Error, TypeError, ValueError) as e:
            await interaction.followup.send(f"An error occurred in the attributes command: {e}")
            logging.exception(f"An error occurred in the attributes command: {e}")


# Modified RetirementView with character deletion
class RetirementView(shared_functions.SelfAcknowledgementView):
    """A view that allows a user to confirm or cancel the retirement of their character."""

    def __init__(self, character_name: str, user_id: int, guild_id: int, interaction: discord.Interaction,
                 content: str):
        super().__init__(content=content, interaction=interaction)
        self.character_name = character_name
        self.user_id = user_id
        self.guild_id = guild_id
        self.message = None  # Will be set when the view is sent

    async def accepted(self, interaction: discord.Interaction):
        """Handle the confirmation of character retirement."""
        async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as conn:
            cursor = await conn.cursor()
            try:
                # Optional: Check if character exists before deletion
                sql_check = """
                    SELECT Thread_ID, Message_ID FROM Player_Characters
                    WHERE Player_ID = ? AND (Character_Name = ? OR Nickname = ?)
                """
                await cursor.execute(sql_check, (interaction.user.id, self.character_name, self.character_name))
                row = await cursor.fetchone()
                if not row:
                    await self.message.edit(
                        content="Character not found or already retired.",
                        view=None
                    )
                    return

                (thread_id, message_id) = row
                logging_thread = interaction.guild.get_channel(thread_id)
                if not logging_thread:
                    logging_thread = await interaction.guild.fetch_channel(thread_id)
                await logging_thread.edit(name=f"{self.character_name} - Retired")

                # Fetch channel ID
                async with shared_functions.config_cache.lock:
                    configs = shared_functions.config_cache.cache.get(interaction.guild_id)
                    if configs:
                        channel_id_row = configs.get('Accepted_Bio_Channel')
                if not channel_id_row:
                    return f"No channel found with Identifier 'Accepted_Bio_Channel' in Admin table."
                channel_id = channel_id_row

                # Fetch the bio channel
                bio_channel = interaction.guild.get_channel(channel_id)
                if bio_channel is None:
                    bio_channel = await interaction.guild.fetch_channel(channel_id)
                if bio_channel is None:
                    return f"Channel with ID {channel_id} not found."

                # Fetch and edit the message
                try:
                    bio_message = await bio_channel.fetch_message(message_id)
                    await bio_message.delete()
                except discord.NotFound:
                    logging.exception("Bio message not found and could not be deleted.")

                sql_archive_statement = """INSERT INTO Archive_Player_Characters(Player_Name, Player_ID, True_Character_Name,
                Title, Titles, Description, Oath, Level, Tier, Milestones, Trials, Gold, Gold_Value, Gold_Value_Max, Essence,
                Fame, Prestige, Mythweavers, Image_Link, Tradition_Name, Tradition_Link, Template_Name, Template_Link,
                Article_Link) 
                SELECT Player_Name, Player_ID, True_Character_Name, Title, Titles, Description, Oath, Level, Tier, Milestones,
                Trials, Gold, Gold_Value, Gold_Value_Max, Essence, Fame, Prestige, Mythweavers, Image_Link, Tradition_Name,
                Tradition_Link, Template_Name, Template_Link, Article_Link FROM Player_Characters WHERE Player_ID = ? AND
                (Character_Name = ? OR Nickname = ?)"""
                await cursor.execute(sql_archive_statement,
                                     (interaction.user.id, self.character_name, self.character_name))
                await conn.commit()

                # Proceed with deletion
                sql_delete = """
                    DELETE FROM Player_Characters 
                    WHERE Character_Name = ?
                """
                await cursor.execute(sql_delete, (self.character_name,))
                await conn.commit()
                self.embed = discord.Embed(
                    title="Character Retirement",
                    description=f"Character '{self.character_name}' has been successfully retired and deleted from the database."
                )
                await interaction.edit_original_response(
                    content="Character successfully retired and deleted from the database.",
                    embed=self.embed,
                    view=None
                )
            except Exception as e:
                logging.exception(f"Failed to delete character '{self.character_name}': {e}")
                await interaction.followup.send(
                    "An unexpected error occurred while trying to retire your character. Please try again later or contact support.",
                    ephemeral=True
                )

    async def rejected(self, interaction: discord.Interaction):
        """Handle the cancellation of character retirement."""
        self.embed = discord.Embed(
            title="Character Retirement",
            description=f"You have chosen against retiring '{self.character_name}'."
        )
        await self.message.edit(
            content="Character retirement cancelled.",

            view=None
        )

    async def create_embed(self):
        """Create the embed for the retirement confirmation."""
        self.embed = discord.Embed(
            title="Character Retirement",
            description=f"Are you sure you want to retire the character '{self.character_name}'?"
        )


# Modified ShopView with additional logic
class TitleShopView(shared_functions.ShopView):
    def __init__(self, user_id: int, guild_id: int, offset: int, limit: int, interaction: discord.Interaction):
        super().__init__(user_id=user_id, guild_id=guild_id, offset=offset, limit=limit, interaction=interaction,
                         content="")
        self.max_items = None  # Cache total number of items

    async def update_results(self):
        """Fetch the title results for the current page."""
        statement = """
            SELECT ID, Effect, Fame, Masculine_Name, Feminine_Name
            FROM Store_Title ORDER BY Fame Asc
            LIMIT ? OFFSET ?
        """
        async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
            cursor = await db.execute(statement, (self.limit, self.offset - 1))
            self.results = await cursor.fetchall()

    async def create_embed(self):
        """Create the embed for the titles."""

        current_page = (self.offset // self.limit) + 1

        total_pages = ((await self.get_max_items() - 1) // self.limit) + 1
        self.embed = discord.Embed(title="Titles", description=f"Page {current_page} of {total_pages}")
        for title in self.results:
            self.embed.add_field(
                name=f"ID: {title[0]} - {title[3]} / {title[4]}",
                value=f"Effect: {title[1]}, Fame: {title[2]}",
                inline=False
            )

    async def get_max_items(self):
        """Get the total number of titles."""
        if self.max_items is None:
            async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
                cursor = await db.execute("SELECT COUNT(*) FROM Store_Title")
                count = await cursor.fetchone()
                self.max_items = count[0]
        return self.max_items


class PrestigeShopView(shared_functions.ShopView):
    def __init__(self, user_id, guild_id: int, offset: int, limit: int, interaction: discord.Interaction):
        super().__init__(user_id=user_id, guild_id=guild_id, offset=offset, limit=limit, interaction=interaction,
                         content="")
        self.max_items = None  # Cache total number of items

    async def update_results(self):
        """Fetch the title results for the current page."""
        statement = """
            SELECT fame_Required, Prestige_Cost, Name, Effect, Use_Limit
            FROM Store_Fame 
            LIMIT ? OFFSET ?
        """
        async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
            cursor = await db.execute(statement, (self.limit, self.offset - 1))
            self.results = await cursor.fetchall()

    async def create_embed(self):
        """Create the embed for the titles."""
        current_page = ((self.offset) // self.limit) + 1
        total_pages = ((await self.get_max_items() - 1) // self.limit) + 1
        self.embed = discord.Embed(title="Fame Store", description=f"Page {current_page} of {total_pages}")
        for fame in self.results:
            (fame_required, prestige_cost, name, effect, limit) = fame
            self.embed.add_field(name=f'**Name**: {name}',
                                 value=f'**Fame Required**: {fame_required} **Prestige Cost**: {prestige_cost}, **Limit**: {limit} '
                                       f'\r\n **Effect**: {effect}',
                                 inline=False)

    async def get_max_items(self):
        """Get the total number of titles."""
        if self.max_items is None:
            async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
                cursor = await db.execute("SELECT COUNT(*) FROM Store_Title")
                count = await cursor.fetchone()
                self.max_items = count[0]
        return self.max_items


class PrestigeHistoryView(shared_functions.ShopView):
    def __init__(self, user_id: int, guild_id: int, offset: int, limit: int, character_name: str, item_name: str,
                 interaction: discord.Interaction):
        super().__init__(user_id=user_id, guild_id=guild_id, offset=offset, limit=limit, interaction=interaction,
                         content="")
        self.max_items = None  # Cache total number of items
        self.character_name = character_name
        self.item_name = item_name

    async def update_results(self):
        """Fetch the history of prestige request  for the current page."""
        if self.item_name is None:
            statement = """
                SELECT Item_Name, Prestige_Cost, Transaction_ID, Time, IsAllowed
                FROM A_Audit_Prestige WHERE Character_Name = ? 
                ORDER BY Transaction_ID DESC LIMIT ? OFFSET ? 
            """
            async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
                cursor = await db.execute(statement, (self.character_name, self.limit, self.offset - 1))
                self.results = await cursor.fetchall()

        else:
            statement = """
                            SELECT Item_Name, Prestige_Cost, Transaction_ID, Time, IsAllowed
                            FROM A_Audit_Prestige WHERE Character_Name = ? AND Item_Name = ?
                            ORDER BY Transaction_ID DESC LIMIT ? OFFSET ? 
                        """
            async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
                cursor = await db.execute(statement, (self.character_name, self.item_name, self.limit, self.offset - 1))
                self.results = await cursor.fetchall()

    async def create_embed(self):
        """Create the embed for the titles."""
        current_page = ((self.offset) // self.limit) + 1
        total_pages = ((await self.get_max_items() - 1) // self.limit) + 1
        self.embed = discord.Embed(title=f"Prestige History for {self.character_name}",
                                   description=f"Page {current_page} of {total_pages}")
        for fame in self.results:
            (item_name, prestige_cost, transaction_id, time, allowed) = fame
            allowed = "Approved" if allowed == 1 else "Rejected"
            self.embed.add_field(name=f'**Item Name**: {item_name}',
                                 value=f'**Prestige Cost**: {prestige_cost} **Transaction ID**: {transaction_id}, **Allowed**: {allowed} '
                                       f'\r\n **Time**: {time}',
                                 inline=False)

    async def get_max_items(self):
        """Get the total number of titles."""
        if self.max_items is None:
            async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
                if not self.character_name:
                    cursor = await db.execute("SELECT COUNT(*) FROM Player_Characters")
                else:
                    cursor = await db.execute("SELECT COUNT(*) FROM Player_Characters WHERE Player_Name = ?",
                                              (self.character_name,))
                count = await cursor.fetchone()
                self.max_items = count[0]
        return self.max_items


class GoldHistoryView(shared_functions.ShopView):
    def __init__(self, user_id: int, guild_id: int, offset: int, limit: int, character_name: str,
                 interaction: discord.Interaction):
        super().__init__(user_id=user_id, guild_id=guild_id, offset=offset, limit=limit, interaction=interaction,
                         content="")
        self.max_items = None  # Cache total number of items
        self.character_name = character_name

    async def update_results(self):
        """Fetch the history of Gold Actions  for the current page."""

        statement = """
                        SELECT Transaction_ID, Author_Name, Author_ID, Character_Name, 
                        gold_value, Effective_Gold_Value, Effective_Gold_Value_Max, 
                        Reason, Source_Command, Time, Related_Transaction_ID
                        FROM A_Audit_Gold WHERE Character_Name = ?
                        ORDER BY Transaction_ID DESC LIMIT ? OFFSET ? 
                    """
        async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
            cursor = await db.execute(statement, (self.character_name, self.limit, self.offset - 1))
            self.results = await cursor.fetchall()

    async def create_embed(self):
        """Create the embed for the titles."""
        current_page = (self.offset // self.limit) + 1
        total_pages = ((await self.get_max_items() - 1) // self.limit) + 1
        self.embed = discord.Embed(title=f"Gold History for {self.character_name}",
                                   description=f"Page {current_page} of {total_pages}")
        for item in self.results:
            (transaction_id, author_name, author_id, character_name,
             gold_value, effective_gold_value, effective_gold_value_max,
             reason, source_command, time, related_transaction_id) = item
            transaction_id_field = f"**Transaction ID**: {transaction_id}"
            transaction_id_field += f" **Related Transaction ID**: {related_transaction_id}" if related_transaction_id else ""
            self.embed.add_field(name=transaction_id_field,
                                 value=f'**Author**: {author_name} Source: {source_command}\r\n ***Gold Changes***: **Gold Value**: {gold_value}, **Effective Gold Value**: {effective_gold_value}, **Effective Gold Value Max**: {effective_gold_value_max}\r\n{reason}',
                                 inline=False)

    async def get_max_items(self):
        """Get the total number of titles."""
        if self.max_items is None:
            async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
                cursor = await db.execute("SELECT COUNT(*) FROM A_AUDIT_GOLD WHERE Character_Name = ?",
                                          (self.character_name,))
                count = await cursor.fetchone()
                self.max_items = count[0]
        return self.max_items


# Dual View Type Views
class CharacterDisplayView(shared_functions.DualView):
    def __init__(self, user_id: int, guild_id: int, offset: int, limit: int, player_name: str, character_name: str,
                 view_type: int, interaction: discord.Interaction):
        super().__init__(user_id=user_id, guild_id=guild_id, offset=offset, limit=limit, view_type=view_type,
                         interaction=interaction, content="")
        self.max_items = None  # Cache total number of items
        self.character_name = character_name
        self.view_type = view_type
        self.player_name = player_name

    async def update_results(self):
        """Fetch the history of prestige request  for the current page."""
        if not self.player_name:

            statement = """SELECT player_name, player_id, True_Character_Name, Title, Titles, Description, Oath, Level, 
                            Tier, Milestones, Milestones_Required, Trials, Trials_Required, Gold, Gold_Value, 
                            Essence, Fame, Prestige, Color, Mythweavers, Image_Link, Tradition_Name, 
                            Tradition_Link, Template_Name, Template_Link, Article_Link
                            FROM Player_Characters ORDER BY True_Character_Name ASC LIMIT ? OFFSET ?"""
            val = (self.limit, self.offset - 1)

        else:

            statement = """SELECT player_name, True_Character_Name, Title, Titles, Description, Oath, Level, 
                            Tier, Milestones, Milestones_Required, Trials, Trials_Required, Gold, Gold_Value, 
                            Essence, Fame, Prestige, Color, Mythweavers, Image_Link, Tradition_Name, 
                            Tradition_Link, Template_Name, Template_Link, Article_Link
                            FROM Player_Characters WHERE Player_Name = ? ORDER BY True_Character_Name ASC LIMIT ? OFFSET ? """
            val = (self.player_name, self.limit, self.offset - 1)
        async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
            cursor = await db.execute(statement, val)
            self.results = await cursor.fetchall()

    async def create_embed(self):
        """Create the embed for the titles."""
        if self.view_type == 1:
            if not self.player_name:
                current_page = (self.offset // self.limit)
                total_pages = ((await self.get_max_items() - 1) // self.limit) + 1
                self.embed = discord.Embed(title=f"Character Summary",
                                           description=f"Page {current_page} of {total_pages}")
            else:
                current_page = (self.offset // self.limit) + 1
                total_pages = ((await self.get_max_items() - 1) // self.limit) + 1
                self.embed = discord.Embed(title=f"Character Summary for {self.player_name}",
                                           description=f"Page {current_page} of {total_pages}")
            for result in self.results:
                (player_name, true_character_name, title, titles, description, oath, level, tier, milestones,
                 milestones_required, trials, trials_required, gold, gold_value, essence, fame, prestige, color,
                 mythweavers, image_link, tradition_name, tradition_link, template_name, template_link,
                 article_link) = result
                gold_string = shared_functions.get_gold_breakdown(gold)
                self.embed.add_field(name=f'Character Name', value=f'**Name**:[{true_character_name}](<{mythweavers}>)')
                self.embed.add_field(name=f'Information',
                                     value=f'**Level**: {level}, **Mythic Tier**: {tier}', inline=False)
                self.embed.add_field(name=f'Total Experience',
                                     value=f'**Milestones**: {milestones}, **Trials**: {trials}',
                                     inline=False)
                self.embed.add_field(name=f'Current Wealth', value=f'**Gold**: {gold_string}, **Essence**: {essence}',
                                     inline=False)
                linkage = ""
                linkage += f"**Tradition**: [{tradition_name}]({tradition_link})" if tradition_name else ""
                linkage += f" " if tradition_name and template_name else ""
                linkage += f"**Template**: [{template_name}]({template_link})" if template_name else ""
                if tradition_name or template_name:
                    self.embed.add_field(name=f'Additional Info', value=linkage, inline=False)
        else:
            current_page = (self.offset // self.limit)
            total_pages = ((await self.get_max_items() - 1) // self.limit) + 1
            for result in self.results:
                (player_name, true_character_name, title, titles, description, oath, level, tier, milestones,
                 milestones_required, trials, trials_required, gold, gold_value, essence, fame, prestige, color,
                 mythweavers, image_link, tradition_name, tradition_link, template_name, template_link,
                 article_link) = result
                gold_string = shared_functions.get_gold_breakdown(gold)
                illiquid_gold_string = shared_functions.get_gold_breakdown(gold_value - gold)
                self.embed = discord.Embed(title=f"Detailed view for {true_character_name}",
                                           description=f"Page {current_page} of {total_pages}",
                                           color=int(color[1:], 16))
                self.embed.set_author(name=f'{player_name}')
                self.embed.set_thumbnail(url=f'{image_link}')
                self.embed.add_field(name=f'Character Name', value=f'**Name**:[{true_character_name}](<{mythweavers}>)')
                self.embed.add_field(name=f'Information',
                                     value=f'**Level**: {level}, **Mythic Tier**: {tier}')
                self.embed.add_field(name=f'Total Experience',
                                     value=f'**Milestones**: {milestones}, **Trials**: {trials}',
                                     inline=False)
                self.embed.add_field(name=f'Current Wealth',
                                     value=f'**Gold**: {gold_string}, **Illiquid Gold**: {illiquid_gold_string} **Essence**: {essence}',
                                     inline=False)
                self.embed.add_field(name=f'Fame and Prestige', value=f'**Fame**: {fame}, **Prestige**: {prestige}',
                                     inline=False)
                linkage = ""
                linkage += f"**Tradition**: [{tradition_name}]({tradition_link})" if tradition_name else ""
                linkage += f" " if tradition_name and template_name else ""
                linkage += f"**Template**: [{template_name}]({template_link})" if template_name else ""
                if tradition_name or template_name:
                    self.embed.add_field(name=f'Additional Info', value=linkage, inline=False)

    async def get_max_items(self):
        """Get the total number of titles."""
        if self.max_items is None:
            async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
                if not self.player_name:
                    cursor = await db.execute("SELECT COUNT(*) FROM Player_Characters")
                else:
                    cursor = await db.execute("SELECT COUNT(*) FROM Player_Characters WHERE Player_Name = ?",
                                              (self.player_name,))
                count = await cursor.fetchone()
                self.max_items = count[0]
        return self.max_items

    async def on_view_change(self):
        self.view_type = 1 if self.view_type == 2 else 2
        if self.view_type == 1:
            self.limit = 5  # Change the limit to 5 for the summary view
        else:
            self.limit = 1  # Change the limit to 1 for the detailed view


class LevelRangeDisplayView(shared_functions.DualView):
    def __init__(self, user_id: int, guild_id: int, offset: int, limit: int, level_range_min: int, level_range_max: int,
                 view_type: int, interaction: discord.Interaction):
        super().__init__(user_id=user_id, guild_id=guild_id, offset=offset, limit=limit, view_type=view_type,
                         interaction=interaction, content="")
        self.max_items = None  # Cache total number of items
        self.view_type = view_type
        self.level_range_max = level_range_max
        self.level_range_min = level_range_min

    async def update_results(self):
        """Fetch the history of prestige request  for the current page."""
        statement = """SELECT player_name, player_id, True_Character_Name, Title, Titles, Description, Oath, Level, 
                        Tier, Milestones, Milestones_Required, Trials, Trials_Required, Gold, Gold_Value, 
                        Essence, Fame, Prestige, Color, Mythweavers, Image_Link, Tradition_Name, 
                        Tradition_Link, Template_Name, Template_Link, Article_Link
                        FROM Player_Characters WHERE level BETWEEN ? AND ? ORDER BY True_Character_Name ASC LIMIT ? OFFSET ? """
        val = (self.level_range_min, self.level_range_max, self.limit, self.offset - 1)
        async with (aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db):
            cursor = await db.cursor()
            await cursor.execute(statement, val)
            self.results = await cursor.fetchall()

    async def create_embed(self):
        """Create the embed for the titles."""
        if self.view_type == 1:
            current_page = (self.offset // self.limit) + 1
            total_pages = ((await self.get_max_items() - 1) // self.limit) + 1
            self.embed = discord.Embed(title=f"Character Summary",
                                       description=f"Page {current_page} of {total_pages}")
            for result in self.results:

                (player_name, player_id, true_character_name, title, titles, description, oath, level, tier, milestones,
                 milestones_required, trials, trials_required, gold, gold_value, essence, fame, prestige, color,
                 mythweavers, image_link, tradition_name, tradition_link, template_name, template_link,
                 article_link) = result
                gold_string = shared_functions.get_gold_breakdown(gold)
                self.embed.add_field(name=f'Character Name', value=f'**Name**:{true_character_name}', inline=False)
                self.embed.add_field(name=f'Information',
                                     value=f'**Level**: {level}, **Mythic Tier**: {tier}')
                self.embed.add_field(name=f'Total Experience',
                                     value=f'**Milestones**: {milestones},  **Trials**: {trials}')
                self.embed.add_field(name=f'Current Wealth', value=f'**Gold**: {gold_string}, **Essence**: {essence}',
                                     inline=False)
                linkage = ""
                linkage += f"**Tradition**: [{tradition_name}]({tradition_link})" if tradition_name else ""
                linkage += f" " if tradition_name and template_name else ""
                linkage += f"**Template**: [{template_name}]({template_link})" if template_name else ""
                if not tradition_name or not template_name:
                    self.embed.add_field(name=f'Additional Info', value=linkage, inline=False)
        else:
            current_page = (self.offset // self.limit) + 1
            total_pages = ((await self.get_max_items() - 1) // self.limit) + 1
            for result in self.results:
                (player_name, player_id, true_character_name, title, titles, description, oath, level, tier, milestones,
                 milestones_required, trials, trials_required, gold, gold_value, essence, fame, prestige, color,
                 mythweavers, image_link, tradition_name, tradition_link, template_name, template_link,
                 article_link) = result
                gold_string = shared_functions.get_gold_breakdown(gold)
                illiquid_gold_string = shared_functions.get_gold_breakdown(gold_value - gold)
                self.embed = discord.Embed(title=f"Detailed view for {true_character_name}",
                                           description=f"Page {current_page} of {total_pages}",
                                           color=int(color[1:], 16))
                self.embed.set_author(name=f'{player_name}')
                self.embed.set_thumbnail(url=f'{image_link}')
                self.embed.add_field(name=f'Character Name', value=f'**Name**:{true_character_name}', inline=False)
                self.embed.add_field(name=f'Information',
                                     value=f'**Level**: {level}, **Mythic Tier**: {tier}', inline=False)
                self.embed.add_field(name=f'Total Experience',
                                     value=f'**Milestones**: {milestones}, **Trials**: {trials},')
                self.embed.add_field(name=f'Current Wealth',
                                     value=f'**gold**: {gold_string}, **Illiquid Gold**: {illiquid_gold_string} **Essence**: {essence}')
                self.embed.add_field(name=f'Fame and Prestige', value=f'**Fame**: {fame}, **Prestige**: {prestige}',
                                     inline=False)
                linkage = ""
                linkage += f"**Tradition**: [{tradition_name}]({tradition_link})" if tradition_name else ""
                linkage += f" " if tradition_name and template_name else ""
                linkage += f"**Template**: [{template_name}]({template_link})" if template_name else ""
                if not tradition_name or not template_name:
                    self.embed.add_field(name=f'Additional Info', value=linkage, inline=False)
                if oath == 'Offerings':
                    self.embed.set_footer(text=f'{description}', icon_url=f'https://i.imgur.com/dSuLyJd.png')
                elif oath == 'Poverty':
                    self.embed.set_footer(text=f'{description}', icon_url=f'https://i.imgur.com/4Fr9ZnZ.png')
                elif oath == 'Absolute':
                    self.embed.set_footer(text=f'{description}', icon_url=f'https://i.imgur.com/ibE5vSY.png')
                else:
                    self.embed.set_footer(text=f'{description}')

    async def get_max_items(self):
        """Get the total number of titles."""
        if self.max_items is None:
            async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute(
                    "SELECT COUNT(*) FROM Player_Characters WHERE Level BETWEEN ? AND ?",
                    (self.level_range_min, self.level_range_max))
                count = await cursor.fetchone()
                self.max_items = count[0]
                return self.max_items
        else:
            return self.max_items

    async def on_view_change(self):
        self.view_type = 1 if self.view_type == 2 else 2
        if self.view_type == 1:
            self.limit = 5  # Change the limit to 5 for the summary view
        else:
            self.limit = 1  # Change the limit to 1 for the detailed view


# Modified RecipientAcknowledgementView with additional logic
class PropositionViewRecipient(shared_functions.RecipientAcknowledgementView):
    def __init__(
            self,
            allowed_user_id: int,
            requester_name: str,
            character_name: str,
            item_name: str,
            prestige_cost: int,
            proposition_id: int,
            bot: commands.Bot,
            guild_id: int,
            prestige: int,
            logging_thread: int,
            interaction: discord.Interaction,
            content: str
    ):
        super().__init__(allowed_user_id=allowed_user_id, interaction=interaction, content=content)
        self.guild_id = guild_id
        self.requester_name = requester_name
        self.character_name = character_name
        self.item_name = item_name
        self.prestige_cost = prestige_cost
        self.proposition_id = proposition_id
        self.bot = bot
        self.prestige = prestige
        self.logging_thread = logging_thread
        self.embed = None

    async def accepted(self, interaction: discord.Interaction):
        """Handle the approval logic."""
        # Update the database to mark the proposition as accepted
        # Adjust prestige, log the transaction, notify the requester, etc.
        self.embed = discord.Embed(
            title="Proposition Accepted",
            description=f"The proposition {self.proposition_id} has been accepted.",
            color=discord.Color.green()
        )
        # Additional logic such as notifying the requester
        async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as conn:
            await conn.execute(
                "UPDATE A_Audit_Prestige SET IsAllowed = ? WHERE Transaction_ID = ?",
                (1, self.proposition_id)
            )
            await conn.commit()
            await conn.execute(
                "UPDATE Player_Characters SET Prestige = Prestige - ? WHERE Character_Name = ?",
                (self.prestige_cost, self.character_name)
            )
            await conn.commit()
            await shared_functions.character_embed(character_name=self.character_name, guild=interaction.guild)
            character_changes = shared_functions.CharacterChange(
                character_name=self.character_name,
                author=self.requester_name,
                source=f'Prestige Request',
                prestige_change=-abs(self.prestige_cost),
                prestige=self.prestige - self.prestige_cost)
            await shared_functions.log_embed(
                change=character_changes,
                guild=interaction.guild,
                thread=self.logging_thread,
                bot=self.bot)

    async def rejected(self, interaction: discord.Interaction):
        """Handle the rejection logic."""
        # Update the database to mark the proposition as rejected

        self.embed = discord.Embed(
            title="Proposition Rejected",
            description=f"The proposition {self.proposition_id} has been rejected.",
            color=discord.Color.red()
        )
        # Additional logic such as notifying the requester

    async def create_embed(self):
        """Create the initial embed for the proposition."""
        self.embed = discord.Embed(
            title="Proposition Request",
            description=(
                f"**Requester:** {self.requester_name}\n"
                f"**Character:** {self.character_name}\n"
                f"**Item:** {self.item_name}\n"
                f"**Prestige Cost:** {self.prestige_cost}\n"
                f"**Proposition ID:** {self.proposition_id}"
            ),
            color=discord.Color.blue()
        )


class GoldSendView(shared_functions.RecipientAcknowledgementView):
    def __init__(
            self,
            allowed_user_id: int,
            requester_name: str,
            requester_id: int,
            character_name: str,
            recipient_name: str,
            source_level: int,
            source_oath: str,
            source_gold: Decimal,
            source_gold_value: Decimal,
            source_gold_value_max: Decimal,
            target_level: int,
            target_oath: str,
            recipient_gold: Decimal,
            recipient_gold_value: Decimal,
            recipient_gold_value_max: Decimal,
            gold_change: Decimal,
            market_value: Decimal,
            bot: commands.Bot,
            guild_id: int,
            source_logging_thread: int,
            recipient_logging_thread: int,
            reason: str,
            interaction: discord.Interaction
    ):
        super().__init__(allowed_user_id=allowed_user_id, interaction=interaction,
                         content=f"<@{allowed_user_id}>, please accept or request this transaction.")
        self.guild_id = guild_id
        self.requester_name = requester_name
        self.requester_id = requester_id
        self.character_name = character_name
        self.recipient_name = recipient_name  # Name of the recipient
        self.source_level = source_level  # Level of the source character
        self.source_oath = source_oath
        self.source_gold = source_gold
        self.source_gold_value = source_gold_value
        self.source_gold_value_max = source_gold_value_max
        self.target_level = target_level  # Level of the recipient character
        self.target_oath = target_oath
        self.recipient_gold = recipient_gold
        self.recipient_gold_value = recipient_gold_value
        self.recipient_gold_value_max = recipient_gold_value_max
        self.gold_change = gold_change  # Amount of gold to be sent
        self.market_value = market_value  # Market value of the item
        self.bot = bot
        self.source_logging_thread = source_logging_thread
        self.recipient_logging_thread = recipient_logging_thread
        self.reason = reason
        self.embed = None

    async def accepted(self, interaction: discord.Interaction):
        """Handle the approval logic."""
        # Update the database to mark the proposition as accepted
        # Adjust prestige, log the transaction, notify the requester, etc.

        self.embed = discord.Embed(
            title=f"{self.character_name} Transaction Accepted",
            description=f"The request of \r\n{self.reason}\r\n has been accepted by <@{self.allowed_user_id}>'s {self.recipient_name}.",
            color=discord.Color.green()
        )
        # Additional logic such as notifying the requester
        async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as conn:
            cursor = await conn.cursor()
            print("Source Gold Info is", self.source_gold, self.source_gold_value, self.source_gold_value_max)
            source_gold_calculation = await gold_calculation(
                guild_id=self.guild_id,
                character_name=self.character_name,
                level=self.source_level,
                oath=self.source_oath,
                gold=Decimal(self.source_gold),
                gold_value=Decimal(self.source_gold_value),
                gold_value_max=Decimal(self.source_gold_value_max),
                gold_change=Decimal(-abs(self.gold_change)),
                gold_value_change=Decimal(abs(self.market_value)) + Decimal(-abs(self.gold_change)),
                gold_value_max_change=None,
                source=f"Gold Send",
                reason=self.reason,
                author_id=interaction.user.id,
                author_name=interaction.user.name)
            if isinstance(source_gold_calculation, tuple):
                recipient_gold_calculation = await gold_calculation(
                    guild_id=self.guild_id,
                    character_name=self.recipient_name,
                    level=self.target_level,
                    oath=self.target_oath,
                    gold=Decimal(self.recipient_gold),
                    gold_value=Decimal(self.recipient_gold_value),
                    gold_value_max=Decimal(self.recipient_gold_value_max),
                    gold_change=Decimal(abs(self.gold_change)),
                    gold_value_change=None,
                    gold_value_max_change=None,
                    source=f"Gold Send",
                    reason=self.reason,
                    related_transaction=source_gold_calculation[4],
                    author_name=self.requester_name,
                    author_id=interaction.user.id,
                    ignore_limitations=True)
                if isinstance(recipient_gold_calculation, str):
                    await interaction.message.edit(
                        content=f"An error occurred in the gold send command: {recipient_gold_calculation}")
                    return
            else:
                await interaction.message.edit(
                    content=f"An error occurred in the gold send command: {source_gold_calculation}")
            if isinstance(source_gold_calculation, tuple) and isinstance(recipient_gold_calculation, tuple):
                (source_calc_difference, source_calc_gold_total, source_calc_gold_value_total,
                 source_calc_gold_max_total, source_calc_transaction_id) = source_gold_calculation
                (recipient_calc_difference, recipient_calc_gold_total, recipient_calc_gold_value_total,
                 recipient_calc_gold_max_total, recipient_calc_transaction_id) = recipient_gold_calculation
                print("Source Gold Info is", source_calc_gold_total, source_calc_gold_value_total,
                      source_calc_gold_max_total)
                await cursor.execute(
                    "UPDATE Player_Characters SET Gold = ?, Gold_Value = ?, Gold_Value_max = ? WHERE Character_Name = ?",
                    (str(source_calc_gold_total), str(source_calc_gold_value_total), str(source_calc_gold_value_total),
                     self.character_name)
                )
                await conn.commit()
                await shared_functions.character_embed(character_name=self.character_name, guild=interaction.guild)
                character_changes = shared_functions.CharacterChange(
                    character_name=self.character_name,
                    author=self.requester_name,
                    source=f'Gold Send',
                    gold_change=-abs(Decimal(source_calc_difference)),
                    gold=Decimal(source_calc_gold_total),
                    gold_value=Decimal(source_calc_gold_value_total),
                    transaction_id=source_calc_transaction_id
                )
                await shared_functions.log_embed(character_changes, guild=interaction.guild,
                                                 thread=self.source_logging_thread, bot=self.bot)
                await conn.execute(
                    "UPDATE Player_Characters SET Gold = ?, Gold_Value = ?, Gold_Value_max = ? WHERE Character_Name = ?",
                    (str(recipient_calc_gold_total), str(recipient_calc_gold_value_total),
                     str(recipient_calc_gold_max_total),
                     self.recipient_name)
                )
                await conn.commit()
                await cursor.execute("UPDATE A_Audit_Gold SET Related_Transaction_ID = ? WHERE Transaction_ID = ?",
                                     (recipient_calc_transaction_id, source_calc_transaction_id))
                await conn.commit()
                await shared_functions.character_embed(character_name=self.recipient_name, guild=interaction.guild)
                character_changes = shared_functions.CharacterChange(
                    character_name=self.recipient_name,
                    author=self.requester_name,
                    source=f'Gold Send',
                    gold_change=abs(Decimal(recipient_calc_difference)),
                    gold=Decimal(recipient_calc_gold_total),
                    gold_value=Decimal(recipient_calc_gold_value_total),
                    transaction_id=recipient_calc_transaction_id
                )
                await shared_functions.log_embed(character_changes, guild=interaction.guild,
                                                 thread=self.recipient_logging_thread, bot=self.bot)
                await shared_functions.character_embed(character_name=self.recipient_name, guild=interaction.guild)
                await shared_functions.character_embed(character_name=self.character_name, guild=interaction.guild)
                gold_string = shared_functions.get_gold_breakdown(self.gold_change)
                embed = discord.Embed(
                    title=f"Gold Transaction Completed",
                    description=f"{self.character_name} has sent {gold_string} to {self.recipient_name}.\r\n {self.reason}",
                    color=discord.Color.green()
                )
                embed.set_footer(
                    text=f"Transaction ID: {source_calc_transaction_id}>, Recipient Transaction ID: {recipient_calc_transaction_id}")
                await interaction.message.edit(content=None, embed=embed, view=None)
            else:
                await interaction.message.edit(
                    content=f"An error occurred in the gold send command: {recipient_gold_calculation}")

    async def rejected(self, interaction: discord.Interaction):
        """Handle the rejection logic."""
        # Update the database to mark the proposition as rejected
        self.embed = discord.Embed(
            title=f"{self.character_name}'s Transaction Rejected",
            description=f"The request of \r\n {self.reason} \r\n has been rejected by <@{self.allowed_user_id}>'s {self.recipient_name}.",
            color=discord.Color.red()
        )
        # Additional logic such as notifying the requester

    async def create_embed(self):
        """Create the initial embed for the proposition."""
        gold_string = shared_functions.get_gold_breakdown(self.gold_change)
        self.embed = discord.Embed(
            title=f"{self.character_name} is sending {gold_string}to {self.recipient_name}",
            description=self.reason,
            color=discord.Color.blue()
        )
        self.embed.set_author(name=self.requester_name)
        self.embed.set_footer(text="Please accept or reject this transaction before it expires.")


# Mythweavers Views
class AttributesView(discord.ui.View):
    def __init__(self, user_id: int, guild_id: int, modifiers: dict):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.guild_id = guild_id
        self.modifiers = modifiers  # Dictionary of attribute names and their modifiers

        # Dynamically create buttons and add callbacks
        for attribute in self.modifiers.keys():
            button = discord.ui.Button(
                label=attribute.capitalize(),
                style=discord.ButtonStyle.primary
            )
            button.callback = self.create_roll_callback(attribute)  # Assign callback
            self.add_item(button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Ensure that only the user who initiated the view can interact with the buttons."""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "You cannot interact with this button.",
                ephemeral=True
            )
            return False
        return True

    def create_roll_callback(self, attribute: str):
        """Generate a callback function for rolling the given attribute."""

        async def callback(interaction: discord.Interaction):
            roll = random.randint(1, 20)
            content = f"**Rolling :game_die: {attribute.capitalize()}** base: {roll}: total: {roll + self.modifiers[attribute]}"
            content += ":broken_heart: **Critical Failure**" if roll == 1 else ""
            content += ":sparkles: **Critical Success**" if roll == 20 else ""
            await interaction.response.send_message(content=content)

        return callback


logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s [%(filename)s:%(lineno)d] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    filename='pathparser.log',  # Specify the log file name
    filemode='a'  # Append mode
)
