from dataclasses import dataclass
from typing import Optional, Tuple
from decimal import Decimal, ROUND_HALF_UP
import aiosqlite
import logging
import discord
from .utils import get_gold_breakdown, safe_int, safe_int_atk
import datetime
import math
import os
from math import floor
import typing
from typing import List, Union
from .config import config_cache

@dataclass
class CharacterChange:
    character_name: str
    author: str
    titles: Optional[str] = None
    image: Optional[str] = None
    mythweavers: Optional[str] = None
    level: Optional[int] = None
    oath: Optional[str] = None
    backstory: Optional[str] = None
    description: Optional[str] = None
    milestone_change: Optional[int] = None
    milestones_total: Optional[int] = None
    milestones_remaining: Optional[int] = None
    tier: Optional[int] = None
    trial_change: Optional[int] = None
    trials: Optional[int] = None
    trials_remaining: Optional[int] = None
    gold: Optional[Decimal] = None
    gold_change: Optional[Decimal] = None
    gold_value: Optional[Decimal] = None
    gold_value_max: Optional[Decimal] = None
    transaction_id: Optional[int] = None
    essence: Optional[int] = None
    essence_change: Optional[int] = None
    tradition_name: Optional[str] = None
    tradition_link: Optional[str] = None
    template_name: Optional[str] = None
    template_link: Optional[str] = None
    alternate_reward: Optional[str] = None
    fame: Optional[int] = None
    fame_change: Optional[int] = None
    prestige: Optional[int] = None
    prestige_change: Optional[int] = None
    source: Optional[str] = None
    region: Optional[str] = None
    heroism: Optional[int] = None
    hero_point_change: Optional[int] = None

@dataclass
class UpdateCharacterData:
    character_name: str
    level_package: Optional[Tuple[int, int, int]] = None  # (Level, Milestones, Milestones_Required)
    mythic_package: Optional[Tuple[int, int, int]] = None  # (Tier, Trials, Trials_Required)
    gold_package: Optional[Tuple[Decimal, Decimal, Decimal]] = None  # (Gold, Gold_Value, Gold_Value_Max)
    essence: Optional[int] = None
    fame_package: Optional[Tuple[int, int]] = None  # (Fame, Prestige)
    hero_package: Optional[Tuple[int, int]] = None #Heroism, Hero


async def update_character(guild_id: int, change: UpdateCharacterData) -> tuple[bool, str]:
    try:
        # Lists to collect column assignments and values
        assignments = []
        values = []

        # Handle level package
        if change.level_package:
            assignments.extend(["Level = ?", "Milestones = ?", "Milestones_Required = ?"])
            values.extend(change.level_package)

        # Handle mythic package
        if change.mythic_package:
            assignments.extend(["Tier = ?", "Trials = ?", "Trials_Required = ?"])
            values.extend(change.mythic_package)

        # Handle gold package
        if change.gold_package:
            # Ensure values are Decimal and formatted to two decimal places
            gold_values = [str(Decimal(value).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)) for value in
                           change.gold_package]
            assignments.extend(["Gold = ?", "Gold_Value = ?", "Gold_Value_Max = ?"])
            values.extend(gold_values)

        # Handle essence
        if change.essence is not None:
            assignments.append("Essence = ?")
            values.append(change.essence)

        # Handle fame package
        if change.fame_package:
            assignments.extend(["Fame = ?", "Prestige = ?"])
            values.extend(change.fame_package)

        if change.hero_package:
            assignments.extend(["Hero_points = ?"])
            values.append(change.hero_package[1])
        # Check if there are any assignments to update
        if not assignments:
            return False, "No changes to update."

        # Construct the SQL statement
        sql_statement = f"UPDATE Player_Characters SET {', '.join(assignments)} WHERE Character_Name = ?"
        values.append(change.character_name)

        # Execute the SQL statement
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()

            await cursor.execute(sql_statement, values)
            updated_rows = cursor.rowcount
            if updated_rows == 0:
                return False, f"No character found with name '{change.character_name}'."
            else:
                await db.commit()
                logging.info(f"Character '{change.character_name}' updated successfully.")
                return True, f"Character '{change.character_name}' updated successfully."

    except aiosqlite.Error as e:
        logging.exception(f"Database error while updating '{change.character_name}': {e}")
        return False, f"An error occurred with the database while updating '{change.character_name}'."
    except (TypeError, ValueError) as e:
        logging.exception(f"Invalid data provided for '{change.character_name}': {e}")
        return False, f"Invalid data provided for '{change.character_name}'. Please check the input values."



class CalculationAidFunctionError(Exception):
    pass


async def get_max_level(guild_id: int) -> Optional[int]:
    async with config_cache.lock:
        configs = config_cache.cache.get(guild_id)
        if configs:
            row = configs.get('Level_Cap')
            if row:
                return row
            else:
                logging.error(f"Level cap not found for guild {guild_id}")
                return None

async def calculate_heroism(hero_status: int, current_points: int, max_points: int, change_points: int) -> Optional[int]:
    if hero_status == 1:
        hero_points = min(current_points + change_points, max_points)
        return hero_points
    else:
        return current_points


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


async def level_ranges(cursor: aiosqlite.Cursor, guild, author_id: int, level: int, new_level: int,
                       region: str, character_name: str) -> None:
    try:
        logging.debug(f"Checking level ranges for {character_name} (Level {level} -> {new_level}) in {region}")
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

                    if character is None:
                        old_level_range_role = guild.get_role(int(old_role[0]))
                        await member.remove_roles(old_level_range_role)
                        logging.debug(f"Removed role {old_level_range_role}")

                if region:
                    await cursor.execute(
                        "SELECT Min_Level, Max_Level, Role_ID FROM Regions_Level_Range WHERE Name = ? AND Min_Level <= ? AND Max_Level >= ?",
                        (region, new_level, new_level))
                    region_role = await cursor.fetchone()
                    if region_role:
                        (min_level, max_level, new_role_id) = region_role
                        if level < min_level or level > max_level:
                            region_role_object = guild.get_role(int(new_role_id))
                            await member.add_roles(region_role_object)
                            logging.debug(f"Added region role {region_role_object}")
                            await cursor.execute(
                                "SELECT Min_level, Max_Level, Role_ID FROM Regions_Level_Range WHERE Name = ? and Min_Level <= ? and Max_Level >= ?",
                                (region, level, level))
                            old_region_role_info = await cursor.fetchone()
                            if old_region_role_info:
                                (min_level_old, max_level_old, old_region_role_id) = old_region_role_info
                                await cursor.execute("""
                                                    SELECT count(character_name)
                                                    FROM Player_Characters
                                                    WHERE level BETWEEN ? AND ? AND 
                                                    Player_ID = ? and Region = ? and character_name != ? limit 1;""",
                                                     (min_level_old, max_level_old, author_id, region, character_name))
                                character_in_old_range = await cursor.fetchone()
                                if character_in_old_range:
                                    (characters_in_range,) = character_in_old_range
                                    if not characters_in_range:
                                        await member.remove_roles(guild.get_role(int(old_region_role_id)))
                                        logging.debug(f"Removed old region role {old_region_role_id}")
            except discord.Forbidden:
                logging.error(f"Bot does not have permissions to manage roles for <@{author_id}>")
                return None

    except (aiosqlite.Error, TypeError, ValueError) as e:
        logging.exception(f"Error in level ranges for <@{author_id}> with error: {e}")
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

            # Get milestone information
            await cursor.execute(
                "SELECT easy, medium, hard, deadly FROM Milestone_System WHERE level = ?",
                (level,)
            )
            milestone_information = await cursor.fetchone()
            if milestone_information is None:
                logging.error(f"Milestone information not found for level {level}")
                raise CalculationAidFunctionError(f"Milestone information not found for level {level}")

            # Unpack milestone information
            easy_milestone, medium_milestone, hard_milestone, deadly_milestone = milestone_information

            # Calculate milestones
            multipliers = [easy, medium, hard, deadly]
            milestone_values = (easy_milestone, medium_milestone, hard_milestone, deadly_milestone)
            awarded_milestone_total = calculate_milestones(milestone_values, multipliers, misc)

            # Determine maximum level
            maximum_level = min(max_level, personal_cap) if personal_cap else max_level

            # Get new level information
            total_milestones = base + awarded_milestone_total
            new_level_info = await get_new_level_info(cursor, total_milestones, maximum_level)
            if new_level_info is None:
                raise CalculationAidFunctionError(
                    f"Error in level calculation for character '{character_name}': No level information found"
                )
            new_level, min_milestones, milestones_to_level = new_level_info

            # Update player character
            milestones_required = min_milestones + milestones_to_level - total_milestones

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


async def get_max_mythic(guild_id: int, level: int) -> Optional[int]:
    try:
        async with config_cache.lock:
            configs = config_cache.cache.get(guild_id)
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
            async with config_cache.lock:
                configs = config_cache.cache.get(guild_id)
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

    except (TypeError, ValueError) as e:
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
    except (TypeError, ValueError) as e:
        logging.exception(f"Error in essence calculation for {character_name} with error: {e}")
        raise CalculationAidFunctionError(f"Error in essence calculation for {character_name} with error: {e}")



async def server_inventory_check(guild_id: int, player_id: int, item_id: str, amount: int) -> int:
    try:
        logging.debug(f"Retrieving server inventory item {item_id}")
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
    except Exception as e:
        logging.exception(f"Failed to retrieve server inventory item {item_id}: {e}")
        return 0


async def update_character_name(guild_id: int, character_name: str, new_character_name: str) -> tuple[bool, str]:
    try:
        return_string = f"Updating character name for '{character_name}' to '{new_character_name}' failed."
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as conn:
            cursor = await conn.cursor()
            tables = [
                ("Sessions_Archive", "Character_Name"),
                ("Sessions_Participants", "Character_Name"),
                ("A_Audit_All", "Character_Name"),
                ("A_Audit_Gold", "Character_Name"),
                ("A_Audit_Prestige", "Character_Name"),
                ("KB_Leadership", "Character_Name")
            ]
            for table, column in tables:
                await cursor.execute(
                    f"UPDATE {table} SET {column} = ? WHERE {column} = ?",
                    (new_character_name, character_name))

            # Sessions_Group uses Host_Character
            await cursor.execute(
                "UPDATE Sessions_Group SET Host_Character = ? WHERE Host_Character = ?",
                (new_character_name, character_name))

            await conn.commit()
            return_string = f"Update {character_name} to {new_character_name} is successful"
            return True, return_string
    except (aiosqlite.Error, TypeError, ValueError) as e:
        logging.exception(f"An error occurred whilst updating character name for '{character_name}': {e}")
        return False, return_string


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

