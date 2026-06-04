import datetime
import logging
import math
import random
import typing
from dataclasses import fields
from itertools import chain

import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands

from commands import kingdom_commands
from core import autocomplete, views
from core.Weather import regenerate_weather
from core.autocomplete import modifier_autocomplete, event_name_autocomplete, type_value_autocomplete, \
    region_autocomplete, hex_terrain_autocomplete
from core.kingdom import (distribute_pain, distribute_consumption, allocate_food, KingdomInfo, settlement_dict,
                          FoodDataClass, RawMaterialsDataClass, SimpleCraftDataClass, LuxuryCraftDataClass,
                          clamp_remaining_to_zero,
                          remaining_is_total, fix_remaining_to_zero, goods_remaining_dict
                          )
from core.kingdom_actions import (remove_building)
from core.kingdom_fetching import fetch_kingdom, fetch_settlement_base, fetch_resources
from core.utils import compare_new, compare_choice

kingdom_general_list = [
    "Build_Points",
    "Population"
]

kingdom_status_list = [
    "Economy",
    "Loyalty",
    "Stability",
    "Fame",
    "Unrest"]


async def add_blueprint(
        guild_id,
        author,
        building,
        build_points,
        lots,
        economy,
        loyalty,
        stability,
        fame,
        unrest,
        corruption,
        crime,
        productivity,
        law,
        lore,
        society,
        danger,
        defence,
        base_value,
        spellcasting,
        supply,
        settlement_limit,
        district_limit,
        description) -> str:  # This will add a new blueprint for players to use.
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute("""select building FROM Buildings_Blueprints where building = ? LIMIT 1;""",
                                 (building,))
            result = await cursor.fetchone()
            if result is None:
                await cursor.execute(
                    """
                    INSERT INTO Buildings_Blueprints
                    (building, build_points, lots, 
                    economy, loyalty, stability, fame, unrest, 
                    corruption, crime, productivity, law, lore, society, danger, defence, 
                    base_value, spell_casting, supply, settlement_limit, district_limit, description) 
                    VALUES 
                    (?, ?, ?,
                    ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?);""",
                    (building, build_points, lots, economy, loyalty, stability, fame, unrest,
                     corruption, crime, productivity, law, lore, society, danger, defence, base_value,
                     spellcasting, supply, settlement_limit, district_limit, description))
                await cursor.execute(
                    """Insert into A_Audit_All (Author, Timestamp, Database_Changed, Modification, Reason) VALUES (?, ?, ?, ?, ?)""",
                    (author, datetime.datetime.now(), "Blueprints", "Create", f"Created the blueprints of {building}"))
                await db.commit()
                function_status = f"Congratulations you have allowed the construction of **{building}**"
                return function_status
            else:
                function_status = f"you have already allowed the construction of **{building}**"
                return function_status

    except (TypeError, ValueError, aiosqlite.Error) as error:
        logging.exception(f"Error in add_blueprint: {error}")
        return "An error occurred while adding a blueprint."


async def general_kingdom_event(
        db: aiosqlite.Connection,
        kingdom: str, region: str, settlement: typing.Optional[str], specified_hex: typing.Optional[int]) -> str:
    try:
        cursor = await db.cursor()
        loop = 1
        response = ""
        while loop == 1:
            await cursor.execute("""
                WITH Weighted AS (
                    SELECT
                        Type,
                        Subtype,
                        reroll,
                        SUM(Likelihood) OVER (
                            ORDER BY rowid
                            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                        ) AS UpperBound
                    FROM kb_events_general 
                ),
                RandomPick AS (
                    SELECT ABS(RANDOM()) % (
                        SELECT SUM(Likelihood) FROM kb_events_general
                    ) + 1 AS Roll
                )
                SELECT w.*, r.Roll
                FROM Weighted w
                CROSS JOIN RandomPick r
                WHERE w.UpperBound >= r.Roll
                ORDER BY w.UpperBound
                LIMIT 1;
            """)
            general_event = await cursor.fetchone()
            print('GenEvent Was' ,general_event)
            if not general_event:
                response += "how the fuck did I fail? Looking for a general event."
                continue
            else:
                (event_type, subtype, loop, upperbound, roll) = general_event
                if event_type == 'Kingdom' or event_type == 'Settlement' :
                    build_response = await choose_kingdom_event(db=db, kingdom=kingdom, region=region, specified_hex=specified_hex, event_type=subtype, localization_type=event_type)
                    response += f"\r\n {build_response}"
                else:
                    build_response = await kingdom_event(db=db, kingdom=kingdom, region=region, event=event_type, settlement=settlement, specified_hex=specified_hex)
                    response += f"\r\n {build_response}"
        return response
    except (TypeError, ValueError, aiosqlite.Error) as error:
        logging.exception(f"Error in general_kingdom_event: {error}")
        return "how the fuck did I fail? Looking for a general event"


async def choose_kingdom_event(
        db: aiosqlite.Connection,
        kingdom: str,
        region: str,
        specified_hex: typing.Optional[int],
        event_type: typing.Optional[str],
        localization_type: typing.Optional[str]):
    try:
        if event_type is None:
            event_type = "Beneficial" if random.randint(0,1) else "Problematic"
        if localization_type is None or localization_type == 'Both':
            localization_type = "Kingdom" if random.randint(0,1) else "Settlement"
        cursor = await db.cursor()
        region = region.title() if region else region
        await cursor.execute("""
            WITH Weighted AS (
                SELECT
                    Name,
                    SUM(Likelihood) OVER (
                        ORDER BY rowid
                        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                    ) AS UpperBound
                FROM kb_events
                where scale = ? 
                    and type = ? 
                    and (region = ? or Region = 'All') 
            ),
            RandomPick AS (
                SELECT ABS(RANDOM()) % (
                    SELECT SUM(Likelihood) FROM kb_events
                where scale = ? 
                    and type = ? 
                    and (region = ? or Region = 'All') 
                ) + 1 AS Roll
            )
            SELECT w.*, r.Roll
            FROM Weighted w
            CROSS JOIN RandomPick r
            WHERE w.UpperBound >= r.Roll
            ORDER BY w.UpperBound
            LIMIT 1;
        """, (localization_type.title(), event_type.title(), region, localization_type.title(), event_type.title(), region))
        event_select = await cursor.fetchone()
        if not event_select:
            return "What the fuck? I couldn't select an event based off the current parameters"
        else:
            print('EventSelect was' ,event_select)
            (name, upperbound, roll) = event_select
            return await kingdom_event(db=db, kingdom=kingdom, event=name, region=region, settlement=None, specified_hex=specified_hex)
    except (TypeError, ValueError, aiosqlite.Error) as error:
        logging.exception(f"Error in choose_kingdom_event: {error}")
        return "Error in Choose_Kingdom_Event."


async def kingdom_event(
        db: aiosqlite.Connection,
        kingdom: str,
        event: str,
        region: typing.Optional[str] = None,
        settlement: typing.Optional[str] = None,
        specified_hex: typing.Optional[str] = None) -> str:
    try:
        response = ""
        cursor = await db.cursor()
        print('event was:' ,event)
        await cursor.execute(
            "SELECT scale, Type, Name, Effect, Special, Check_A, Check_B, Success_Requirement, Duration, Bonus, Penalty, Hex from kb_events where name = ?",
            (event,))
        event_info = await cursor.fetchone()
        if not event_info:
            raise ValueError("No event found.")
        scale, event_type, event_name, effect, special, check_a, check_b, success_requirement, duration, bonus, penalty, hex_affect = event_info

        await cursor.execute(
            "SELECT Name, Type, Value, Reroll FROM KB_Events_Consequence WHERE Name = ? AND Severity = -1", (event,))
        respawn_list = await cursor.fetchall()
        spawns = 1
        spawn_building = 0
        despawn_building = 0
        spawn_improvement = 0
        despawn_improvement = 0
        for respawn in respawn_list:
            (name, type, value, reroll) = respawn
            if reroll == 4 and type == 'Respawn':
                spawns += exploding_roll(value)
            elif reroll == 5 and type == 'Respawn':
                spawns += exploding_instance(value)
            elif reroll == 1 and type == 'Respawn':
                spawns += random.randint(1, value)
            elif reroll == 0 and type == 'Respawn':
                spawns += value
            spawn_improvement += value if type == 'Build Random Improvement' else 0
            despawn_improvement += value if type == 'Destroy Random Improvement' else 0
            spawn_building += value if type == 'Build Random Building' else 0
            despawn_building += value if type == 'Destroy Random Building' else 0

        for x in range(spawns):
            if specified_hex:
                hex_result = specified_hex
                specified_hex = None
            elif hex_affect == 1:
                await cursor.execute("""
                SELECT KH.ID
                FROM KB_Hexes KH 
                WHERE KH.Kingdom = ? AND KEA.Name = ? AND (KH.IsTown = 0 or kh.IsTown is null) 
                order by Random() LIMIT 1""", (kingdom, event_name))
                hex_id = await cursor.fetchone()
                if hex_id:
                    hex_result = hex_id[0]
                else:
                    continue
            elif hex_affect == 2:
                await cursor.execute("""
                SELECT KH.ID
                FROM KB_Hexes KH 
                WHERE KH.Kingdom <> ? and Region = ? AND (KH.IsTown = 0 or kh.IsTown is null) 
                order by Random() LIMIT 1""", (kingdom, region))
                hex_id = await cursor.fetchone()
                if hex_id:
                    hex_result = hex_id[0]
                    settlement = None
                else:
                    continue
            elif hex_affect == 3:
                await cursor.execute("""
                SELECT KH.ID, Settlement
                FROM KB_Hexes KH 
                LEFT JOIN KB_Settlements KBS on KBS.hex_id = KH.ID 
                WHERE KH.Kingdom != ? 
                order by Random() LIMIT 1""", (kingdom,))
                hex_id = await cursor.fetchone()
                if hex_id:
                    hex_result = hex_id[0]
                    settlement = hex_id[1]
                else:
                    continue
            else:
                hex_result = None
            if scale == 'Settlement' and not settlement:
                print(hex_result)
                await cursor.execute(
                    "Select Settlement, Hex_ID from Kb_settlements where kingdom = ? and case when ? is not null then Hex_ID = ? else True end order by Random()",
                    (kingdom, hex_result, hex_result))
                settlement_info = await cursor.fetchone()
                if not settlement_info:
                    raise ValueError(f"No settlements underneath {kingdom} to apply the event of {event} to.")
                settlement = settlement_info[0]
            await cursor.execute("""INSERT into KB_Events_Active(Kingdom, Settlement, Hex, Name, Effect, Duration, Check_A_Status, Check_B_Status, Active) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""", (
                kingdom, settlement, hex_result, event_name, effect, duration, False, False, True))
            await cursor.execute("select max(id) from kb_events_active")
            max_id = await cursor.fetchone()
            response += f"**Inserted Event** ID - {max_id[0]}: __{event_name}__ **Duration**: {duration}\r\n**Affecting Kingdom**: {kingdom}\r\n"
            response += f"**Effecting Settlement**: {settlement}\r\n" if settlement else ""
            response += f"Hex: {hex_result}\r\n" if hex_result else ""
            await cursor.execute(
                """INSERT into A_Audit_All (Author, Timestamp, Database_Changed, Modification, Reason) VALUES (?, ?, ?, ?, ?)""",
                (0, datetime.datetime.now(), "KB_Events_Active", "Create", f"Created the event of {event_name}"))
            for y in range(spawn_improvement):
                response += await improvement_event(db=db, hex_id=hex_result, type='Spawn')
            for z in range(despawn_improvement):
                response += await improvement_event(db=db, hex_id=hex_result, type='Despawn')
            for a in range(spawn_building):
                response += await building_event(db=db, settlement=settlement, type='Spawn', kingdom=kingdom)
            for b in range(despawn_building):
                response += await building_event(db=db, settlement=settlement, type='Despawn', kingdom=kingdom)
        await db.commit()
        return response
    except (TypeError, ValueError, aiosqlite.Error) as error:
        logging.exception(f"Error in kingdom_event: {error}")
        return f"Samathe will fuck your mother, also there was an issue: {error}"

def exploding_roll(value):
    respawns = 0
    number_respawns = random.randint(1, abs(value))
    respawns += number_respawns
    while number_respawns == value:  # This will allow for the event to respawn multiple times.
        number_respawns = random.randint(1, abs(value))
        respawns += number_respawns
    respawns = respawns if value > 0 else -respawns
    return respawns


def exploding_instance(value):
    respawns = 1
    number_respawns = random.randint(1, abs(value))
    if number_respawns == value:  # This will allow for the event to respawn multiple times.
        number_respawns = random.randint(1, abs(value))
        respawns += number_respawns
    respawns = respawns if value > 0 else -respawns
    return respawns


async def improvement_event(
        db: aiosqlite.Connection,
        hex_id: int,
        type: str) -> str:
    try:
        cursor = await db.cursor()
        if type == 'Spawn':
            await cursor.execute(
                "SELECT Region, Kingdom, Hex_Terrain, Farm, Ore, Stone, Wood, Water, IsTown from KB_Hexes where ID = ?",
                (hex_id,))
            hex_info = await cursor.fetchone()
            if not hex_info:
                raise ValueError("No hex found.")
            (region, kingdom, terrain, farm, ore, stone, wood, water, is_town) = hex_info
            if is_town:
                raise ValueError("Cannot spawn improvements in towns.")
            await cursor.execute("""
                SELECT 
                    SUM(CASE WHEN type = 'Farm' THEN amount * quality ELSE 0 END) AS farm_total,
                    SUM(CASE WHEN subtype = 'Ore' THEN amount * quality ELSE 0 END) AS ore_total,
                    SUM(CASE WHEN subtype = 'Stone' THEN amount * quality ELSE 0 END) AS stone_total,
                    SUM(CASE WHEN subtype = 'Wood' THEN amount * quality ELSE 0 END) AS wood_total,
                    SUM(CASE WHEN subtype = 'Seafood' THEN amount * quality ELSE 0 END) AS seafood_total
                FROM KB_Hexes_Constructed KHC
                LEFT JOIN KB_Hexes_Improvements KHI on KHC.Full_Name = KHI.Full_Name 
                WHERE ID = ?;""",
                                 (hex_id,))
            resource_totals = await cursor.fetchone()
            (resource_farm, resource_ore, resource_stone, resource_wood, resource_seafood) = resource_totals
            select_statement = "SELECT Full_Name, Name, Subtype, Quality, Economy, Loyalty, Stability, Unrest, Consumption, Defence, Taxation FROM KB_Hexes_Improvements WHERE "
            select_statement += terrain + " > 0"
            select_statement += " name != 'Farm'" if farm <= resource_farm else ""
            select_statement += " subtype != 'Ore'" if ore <= resource_ore else ""
            select_statement += " subtype != 'Stone'" if stone <= resource_stone else ""
            select_statement += " subtype != 'Wood'" if wood <= resource_wood else ""
            select_statement += " subtype != 'Seafood'" if water <= resource_seafood else ""
            select_statement += " ORDER BY Random() LIMIT 1"
            await cursor.execute(select_statement)
            improvement = await cursor.fetchone()
            if not improvement:
                return "nothing to improve here chief!"
            (full_name, name, subtype, quality, economy, loyalty, stability, unrest, consumption, defence,
             taxation) = improvement
            await cursor.execute("select amount from KB_Hexes_Construction where ID = ? and Full_Name = ?",
                                 (hex_id, full_name))
            existing = await cursor.fetchone()
            if not existing:
                await cursor.execute(
                    "INSERT INTO KB_Hexes_Constructed (ID, Kingdom, Full_name, Amount) VALUES (?, ?, ?, ?)",
                    (hex_id, full_name, kingdom, 1))
            else:
                await cursor.execute(
                    "UPDATE KB_Hexes_Constructed SET Amount = Amount + 1 WHERE ID = ? AND Full_Name = ?",
                    (hex_id, full_name))
            await cursor.execute(
                "INSERT INTO A_Audit_All (Author, Timestamp, Database_Changed, Modification, Reason) VALUES (?, ?, ?, ?, ?)",
                (0, datetime.datetime.now(), "KB_Hexes_Constructed", "Create",
                 f"Created the improvement of {full_name}"))
            if kingdom:
                pass
            await db.commit()
            return f"added an improvement of {full_name} from hex {hex_id} in region {region} for kingdom {kingdom}"
        else:
            await cursor.execute(
                "SELECT ID, kingdom, full_name, amount FROM KB_Hexes_Constructed WHERE ID = ? ORDER BY Random() LIMIT 1",
                (hex_id,))
            improvement = await cursor.fetchone()
            if not improvement:
                return "Tell this poor motherfucker to go build a damn improvement."
            (hex_id, kingdom, full_name, amount) = improvement
            amount = await cursor.fetchone()
            if amount[0] == 1:
                await cursor.execute("DELETE FROM KB_Hexes_Constructed WHERE ID = ? AND Full_Name = ?",
                                     (hex_id, full_name))
            else:
                await cursor.execute(
                    "UPDATE KB_Hexes_Constructed SET Amount = Amount - 1 WHERE ID = ? AND Full_Name = ?",
                    (hex_id, full_name))
            await cursor.execute(
                "INSERT INTO A_Audit_All (Author, Timestamp, Database_Changed, Modification, Reason) VALUES (?, ?, ?, ?, ?)",
                (0, datetime.datetime.now(), "KB_Hexes_Constructed", "Delete",
                 f"Deleted the improvement of {full_name}"))
            if kingdom:
                pass
            return f"removed an improvement of {full_name} from hex {hex_id} for kingdom {kingdom}"
    except (TypeError, ValueError, aiosqlite.Error) as error:
        logging.exception(f"Error in improvement_event: {error}")
        return error


async def building_event(
        db: aiosqlite.Connection,
        settlement: str,
        kingdom: str,
        type: str) -> str:
    try:
        cursor = await db.cursor()
        if type == 'Spawn':
            await cursor.execute(
                "SELECT Full_Name, Type from KB_Buildings_Blueprints order by Random() LIMIT 1")
            building_info = await cursor.fetchone()
            if not building_info:
                return "could not find building"
            (full_name, building_type) = building_info
            await cursor.execute("SELECT Full_Name, amount FROM KB_Buildings WHERE Kingdom = ? AND Settlement = ?",
                                 (kingdom, settlement))
            settlement_info = await cursor.fetchone()
            if not settlement_info:
                await cursor.execute("""
                INSERT INTO KB_Buildings (kingdom, settlement, Full_Name, Amount, discounted) VALUES(
                ?, ?, ?, ?, ?""", (kingdom, settlement, full_name, 1, 0))
            else:
                (building, constructed) = settlement_info
                await cursor.execute(
                    "UPDATE KB_Buildings SET Amount = Amount + 1 WHERE Kingdom = ? AND Settlement = ? AND Full_Name = ?",
                    (kingdom, settlement, building))
            await cursor.execute(
                "INSERT INTO A_Audit_All (Author, Timestamp, Database_Changed, Modification, Reason) VALUES (?, ?, ?, ?, ?)",
                (0, datetime.datetime.now(), "KB_Buildings", "Create", f"Created the building of {full_name}"))
            await db.commit()
            return f"spawned building of {full_name} in settlement {settlement} of kingdom {kingdom}"
        else:
            await cursor.execute("""
                SELECT kbuild.full_name, amount
                FROM KB_Buildings kbuild
                WHERE Kingdom = ? AND Settlement = ? 
                ORDER BY Random() LIMIT 1""",
                (kingdom, settlement))
            building_info = await cursor.fetchone()
            if not building_info:
                return f"could not identify a building to despawn in kingdom of {kingdom} and settlement of {settlement}"
            (full_name, amount) = building_info
            if amount == 1:
                await cursor.execute("DELETE FROM KB_Buildings WHERE Kingdom = ? AND Settlement = ? AND full_name = ?",
                                     (kingdom, settlement, full_name))
            else:
                await cursor.execute(
                    "UPDATE KB_Buildings SET Constructed = Constructed - 1 WHERE Kingdom = ? AND Settlement = ? AND full_name = ?",
                    (kingdom, settlement, full_name))
            await cursor.execute(
                "INSERT INTO A_Audit_All (Author, Timestamp, Database_Changed, Modification, Reason) VALUES (?, ?, ?, ?, ?)",
                (0, datetime.datetime.now(), "KB_Buildings", "Delete", f"Deleted the building of {full_name}"))
            await db.commit()
            return f"despawned building of {full_name} from settlement {settlement} of kingdom {kingdom}"
    except (TypeError, ValueError, aiosqlite.Error) as error:
        logging.exception(f"Error in building_event: {error}")
        return f"Error in building_event: {error}"

async def handle_event_duration(
        db: aiosqlite.Connection,
        kingdom: str
):
    try:
        cursor = await db.cursor()
        await cursor.execute("""
        UPDATE KB_Events_active
        SET Duration = CASE
            WHEN KB_Events_active.Duration > 0 THEN
                KB_Events_active.Duration - 1
            WHEN KB_Events_active.Duration < 0 THEN
                CASE
                    WHEN COALESCE(check_a_status, 0)
                       + COALESCE(check_b_status, 0) >= KE.Success_requirement
                    THEN KB_Events_active.Duration + 1
                    ELSE KB_Events_active.Duration
                END
            ELSE 0
        END
        FROM KB_Events KE
        WHERE KB_Events_active.name = KE.name;
            and kea.kingdom = ?
        """, (kingdom,))
        await cursor.execute("""DELETE FROM Kb_Events_Active where Kingdom = ? and duration = 0""")
    except (TypeError, ValueError, aiosqlite.Error) as error:
        logging.exception(f"Error in event_duration: {error}")



async def handle_event_summary(
        db: aiosqlite.Connection,
        kingdom_info: KingdomInfo,
        guild_id: int
) -> (KingdomInfo, dict, int, int, str):
    cursor = await db.cursor()
    await cursor.execute("""
        "SELECT 
            id, settlement, hex, kea.Name, duration, check_a_status, check_b_status, kec.Type, kec.Value, kec.Reroll 
            FROM KB_Events_Active KEA
            LEFT JOIN KB_Events_Consequence KEC ON KEC.Name = KEA.Name and KEC.Severity =  check_a_status, check_b_status
            WHERE Kingdom = ? And Active = 1 Order by settlement asc, kea.name desc
        """,
                         (kingdom_info.kingdom,))
    active_events = await cursor.fetchall()
    consumption_modifier = 0
    farm_penalty = 0
    settlements_info_masterdict = {}
    response = "Kingdom Events"
    for event in active_events:
        (event_id, settlement, hex_id, event_name, duration, check_a_status, check_b_status, event_type, event_value, reroll) = event
        severity = 0
        severity += check_a_status if check_a_status > 0 else 0
        severity += check_b_status if check_b_status > 0 else 0
        if reroll == 0:
            event_value = event_value
        elif reroll == 1:
            event_value = random.randint(1, event_value)
        elif reroll == 2:
            consumption_modifier += event_value
        elif reroll == 3:
            event_value = exploding_roll(event_value)
        elif reroll == 4:
            event_value = exploding_instance(event_value)
        elif reroll == 5:
            if event_type in kingdom_status_list or event_type in settlement_dict.keys():
                await cursor.execute(f"Select count(*) from kb_buildings kb left join kb_buildings_blueprints kbb on kbb.full_name = kb.full_name where settlement = ? and {event_type} > 0")
                event_value_get = await cursor.fetchone()
                event_value = event_value_get[0]
            else:
                event_value = 0
        else:
            event_value = event_value
        if event_type == "Crop Failure" and severity == 0:
            farm_penalty += 2
        elif event_type == "Crop Failure" and severity == 1:
            farm_penalty += 1
        elif event_type == 'Respawn':
            for x in range(event_value):
                response += "\r\n" + await kingdom_event(db=db, kingdom=kingdom_info.kingdom, region=kingdom_info.kingdom, event=event_type, settlement=settlement)
        elif event_type == 'Build Random Improvement':
            for x in range(event_value):
                response += "\r\n" + await improvement_event(db=db, hex_id=hex_id, type='Spawn')
        elif event_type == 'Destroy Random Improvement':
            for x in range(event_value):
                response += "\r\n" + await improvement_event(db=db, hex_id=hex_id, type='Despawn')
        elif event_type == 'Build Random Building':
            for x in range(event_value):
                response += "\r\n" + await building_event(db=db, settlement=settlement, kingdom=kingdom_info.kingdom, type='Spawn')
        elif event_type == 'Destroy Random Building':
            for x in range(event_value):
                response += "\r\n" + await building_event(db=db, settlement=settlement, kingdom=kingdom_info.kingdom, type='Despawn')
        elif event_type in kingdom_general_list:
            current_val = getattr(kingdom_info, event_type, 0)
            setattr(kingdom_info, event_type, current_val + event_value)
        elif event_type in kingdom_status_list:
            getattr(kingdom_info, event_type).base += event_value
        elif event_type in settlement_dict.keys():
            if settlement not in settlements_info_masterdict.keys():
                settlement_info = fetch_settlement_base(guild_id=guild_id, settlement=settlement)
                settlements_info_masterdict[settlement] = settlement_info
            else:
                settlement_info = settlements_info_masterdict[settlement]
            current_val = getattr(settlement_info, event_type, 0)
            setattr(settlement_info, event_type, current_val + event_value)
            if settlement not in settlements_info_masterdict.keys():
                settlements_info_masterdict[settlement] = settlement_info
            else:
                current_val = getattr(kingdom_info, event_type, 0)
                setattr(kingdom_info, event_type, current_val + event_value)
    return kingdom_info, settlements_info_masterdict, farm_penalty, consumption_modifier


async def remove_blueprint(
        guild_id: int,
        author: int,
        building: str) -> str:  # This will remove a blueprint from play.
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute("""select Building FROM Buildings_Blueprints WHERE Building = '{building}'""")
            result = await cursor.fetchone()
            if result is None:
                status = f"The building of {building} did not previously exist."
                await db.commit()
                return status
            else:
                status = f"You have done the YEETETH of this particular building which is {building}."
                await cursor.execute("""Delete FROM KB_Buildings_Blueprints WHERE Full_name = ?""", (result[0],))
                await cursor.execute("Delete FROM KB_Buildings WHERE Full_name = ?", (building,))
                await cursor.execute(
                    "Insert into A_Audit_All (Author, Timestamp, Database_Changed, Modification, Reason) VALUES (?, ?, ?, ?, ?)",
                    (
                        author, datetime.datetime.now(), "KB_Settlements", "Update",
                        f"Removed the building of {building}"))
                await db.commit()
                return status
    except (TypeError, ValueError, aiosqlite.Error) as error:
        logging.exception(f"Error in remove_blueprint: {error}")
        return "An error occurred while removing a blueprint."


async def modify_blueprint(
        guild_id: int,
        author: int,
        old_blueprint_name: str,
        full_name: typing.Optional[str] = None,
        type: typing.Optional[int] = None,
        subtype: typing.Optional[int] = None,
        quality: typing.Optional[int] = None,
        build_points: typing.Optional[int] = None,
        lots: typing.Optional[int] = None,
        economy: typing.Optional[int] = None,
        loyalty: typing.Optional[int] = None,
        stability: typing.Optional[int] = None,
        fame: typing.Optional[int] = None,
        unrest: typing.Optional[int] = None,
        corruption: typing.Optional[int] = None,
        crime: typing.Optional[int] = None,
        productivity: typing.Optional[int] = None,
        law: typing.Optional[int] = None,
        lore: typing.Optional[int] = None,
        society: typing.Optional[int] = None,
        danger: typing.Optional[int] = None,
        defence: typing.Optional[int] = None,
        base_value: typing.Optional[int] = None,
        spell_casting: typing.Optional[int] = None,
        supply: typing.Optional[int] = None,
        settlement_limit: typing.Optional[int] = None,
        district_limit: typing.Optional[int] = None,
        description: typing.Optional[str] = None,
        upgrade: typing.Optional[str] = None,
        discount: typing.Optional[str] = None,
        tier: typing.Optional[int] = None
        ) -> typing.Union[str, bool]:
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute("""
                UPDATE KB_Buildings_Blueprints SET 
                    Full_Name = coalesce(?, Full_Name),
                    Type = coalesce(?, Type),
                    Subtype = coalesce(?, Subtype),
                    Quality = coalesce(?, Quality),
                    Build_Points = coalesce(?, Build_Points),
                    Lots = coalesce(?, Lots),
                    Economy = coalesce(?, economy),
                    Loyalty = coalesce(?, loyalty),
                    Stability = coalesce(?, stability),
                    Fame = coalesce(?, fame),
                    Unrest = coalesce(?, unrest),
                    corruption = coalesce(?, corruption),
                    crime = coalesce(?, crime),
                    productivity = coalesce(?, productivity),
                    law = coalesce(?, law),
                    lore = coalesce(?, lore),
                    society = coalesce(?, society),
                    danger = coalesce(?, danger),
                    defence = coalesce(?, defence),
                    base_value = coalesce(?, base_value),
                    spellcasting = coalesce(?, spellcasting),
                    supply = coalesce(?, supply),
                    settlement_limit = coalesce(?, settlement_limit),
                    district_limit = coalesce(?, district_limit),
                    description = coalesce(?, description),
                    upgrade = coalesce(?, upgrade),
                    discount = coalesce(?, discount),
                    tier = coalesce(?, tier)
                where Full_Name = ?
                """,
                (full_name, type, subtype, quality, build_points,
                 lots, economy, loyalty, stability, fame, unrest, corruption, crime,
                 productivity, law, lore, society, danger, defence,
                 base_value, spell_casting, supply, settlement_limit,
                 district_limit, description, upgrade, discount, tier,
                 old_blueprint_name))
            await cursor.execute(
                "UPDATE kb_Buildings set full_name = ?, WHERE building = ?",
                (full_name, ))
            await cursor.execute(
                "Insert into A_Audit_All (Author, Timestamp, Database_Changed, Modification, Reason) VALUES (?, ?, ?, ?, ?)",
                (author, datetime.datetime.now(), "Blueprints", "Update", f"Updated the blueprints of {full_name}"))

            return True
    except (TypeError, ValueError, aiosqlite.Error) as error:
        logging.exception(f"Error in modify_blueprint: {error}")
        return "An error occurred while modifying a blueprint."


async def customize_kingdom_modifiers(
        guild_id: int,
        author: int,
        kingdom: str,
        control_dc: typing.Optional[int],
        economy: typing.Optional[int],
        loyalty: typing.Optional[int],
        stability: typing.Optional[int],
        fame: typing.Optional[int],
        unrest: typing.Optional[int],
        consumption: typing.Optional[int],
        region: typing.Optional[str]) -> str:
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute("""select Kingdom, Password FROM KB_Kingdoms where Kingdom = ?""", (kingdom,))
            result = await cursor.fetchone()
            if result is None:
                status = f"the kingdom of {kingdom} which you have attempted to set new modifiers for couldn't be found."
                await db.commit()
                return status
            else:
                await cursor.execute(
                    "SELECT Control_DC, Economy, loyalty, Stability, Fame, Unrest, Consumption, Region FROM KB_Kingdoms_Custom WHERE Kingdom = ?",
                    (kingdom,))
                result = await cursor.fetchone()
                (
                    old_control_dc, old_economy, old_loyalty, old_stability, old_fame, old_unrest,
                    old_consumption, old_region) = result
                control_dc = control_dc if isinstance(control_dc, int) else old_control_dc
                economy = economy if isinstance(economy, int) else old_economy
                loyalty = loyalty if isinstance(loyalty, int) else old_loyalty
                stability = stability if isinstance(stability, int) else old_stability
                fame = fame if isinstance(fame, int) else old_fame
                unrest = unrest if isinstance(unrest, int) else old_unrest
                consumption = consumption if isinstance(consumption, int) else old_consumption
                if region != old_region:
                    await cursor.execute("UPDATE KB_Kingdoms SET Region = ? WHERE Kingdom = ?", (region, kingdom))
                    await cursor.execute("UPDATE KB_Hexes SET Region = ? WHERE Kingdom = ?", (region, kingdom))

                await cursor.execute(
                    "UPDATE KB_Kingdoms_Custom SET Control_DC = ?, Economy = ?, Loyalty = ?, Stability = ?, Fame = ?, Unrest = ?, Consumption = ? WHERE Kingdom = ?",
                    (control_dc, economy, loyalty, stability, fame, unrest, consumption, kingdom))

                await cursor.execute(
                    "Insert into A_Audit_All (Author, Timestamp, Database_Changed, Modification, Reason) VALUES (?, ?, ?, ?, ?)",
                    (author, datetime.datetime.now(), "KB_Kingdoms", "Update",
                     f"Updated the custom modifiers of {kingdom}"))
                await db.commit()
                status = f"The kingdom of {kingdom} which you have set new modifiers for has been adjusted"
                return status
    except (TypeError, ValueError, aiosqlite.Error) as error:
        logging.exception(f"Error in customize_kingdom_modifiers: {error}")
        return "An error occurred while customizing kingdom modifiers."


async def custom_settlement_modifiers(
        guild_id: int,
        author: int,
        kingdom: str,
        settlement: str,
        corruption: typing.Optional[int],
        crime: typing.Optional[int],
        productivity: typing.Optional[int],
        law: typing.Optional[int],
        lore: typing.Optional[int],
        society: typing.Optional[int],
        danger: typing.Optional[int],
        defence: typing.Optional[int],
        base_value: typing.Optional[int],
        spellcasting: typing.Optional[int],
        supply: typing.Optional[int]) -> str:
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute("""select Settlement FROM KB_Settlements WHERE Settlement = ? AND Kingdom = ?""",
                                 (settlement, kingdom))
            result = await cursor.fetchone()
            if result is None:
                status = f"you cannot apply custom modifiers if the settlement of {settlement} doesn't exist for the kingdom of {kingdom}!"
                await db.commit()
                return status
            else:
                await cursor.execute("""
                    UPDATE KB_Settlements_Custom SET 
                        Corruption = coalesce(?, corruption), 
                        Crime = coalesce(?, Crime), 
                        Productivity = coalesce(?, Productivity), 
                        Law = coalesce(?, Law), 
                        Lore = coalesce(?, Lore), 
                        Society = coalesce(?, Society), 
                        Danger = coalesce(?, Danger), 
                        Defence = coalesce(?, Defence), 
                        Base_Value = coalesce(?, Base_Value), 
                        Spellcasting = coalesce(?, Spellcasting), 
                        Supply = coalesce(?, Supply) 
                    WHERE Kingdom = ? AND Settlement = ?""",
                    (corruption, crime, productivity, law, lore, society, danger, defence, base_value, spellcasting,
                     supply, kingdom, settlement))
                await cursor.execute(
                    "Insert into A_Audit_All (Author, Timestamp, Database_Changed, Modification, Reason) VALUES (?, ?, ?, ?, ?)",
                    (author, datetime.datetime.now(), "KB_Settlements", "Update",
                     f"Updated the custom modifiers of {settlement}"))
                await db.commit()
                status = f"You have modified the settlement of {settlement} congratulations!"
                return status
    except (TypeError, ValueError, aiosqlite.Error) as error:
        logging.exception(f"Error in custom_settlement_modifiers: {error}")
        return "An error occurred while customizing settlement modifiers."


async def add_hex_improvements(
        guild_id: int,
        author: int,
        improvement: str,
        type: str,
        subtype: str,
        quality: int,
        build_points: int,
        economy: float,
        loyalty: float,
        stability: float,
        unrest: float,
        consumption: float,
        defence: float,
        taxation: float,
        cavernous: int,
        coastline: int,
        desert: int,
        forest: int,
        hills: int,
        jungle: int,
        marsh: int,
        mountains: int,
        plains: int,
        water: int,
        source,
        size) -> str:
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute("""select Full_name from KB_Hexes_Improvements where Full_name = ?""",
                                 (improvement,))
            result = await cursor.fetchone()
            if result is None:
                await cursor.execute(
                    """INSERT INTO KB_Hexes_Improvements (
                        Full_Name, 
                        Type, Subtype, Quality, Build_Points, 
                        Economy, Loyalty, Stability, Unrest, Consumption, Defence, Taxation, 
                        Cavernous, Coastline, Desert, Forest, Hills, Jungle, Marsh, Mountains, Plains, Water, 
                        Source, Size
                    ) VALUES (
                        ?, 
                        ?, ?, ?, ?, 
                        round(?, 3), round(?, 3), round(?, 3), round(?, 3), round(?, 3), round(?, 3), round(?, 3),
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 
                        ?, ?
                    );""", (
                        improvement,
                        type, subtype, quality, build_points,
                        economy, loyalty, stability, unrest, consumption, defence, taxation,
                        cavernous, coastline, desert, forest, hills, jungle, marsh, mountains, plains, water,
                        source, size))
                await cursor.execute(
                    """Insert into A_Audit_All (Author, Timestamp, Database_Changed, Modification, Reason) VALUES (?, ?, ?, ?, ?)""",
                    (author, datetime.datetime.now(), "KB_Hexes_Improvements", "Create",
                     f"Created the hex improvement of {improvement}"))
                await db.commit()
                status = f"You have allowed the creation of the new hex improvement: {improvement}!"
                return status
            else:
                status = f"You cannot add a improvement with the same name of {improvement}!"
                return status
    except (TypeError, ValueError, aiosqlite.Error) as error:
        logging.exception(f"Error in add_hex_improvements: {error}")
        return "An error occurred while adding a hex improvement."


async def remove_hex_improvements(
        guild_id: int,
        author: int,
        improvement: str) -> str:
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute("""select Full_Name FROM KB_Hexes_Improvements WHERE Full_Name = ?""",
                                 (improvement,))
            result = await cursor.fetchone()
            if result is None:
                return "nothing to remove bozo"
            else:
                await cursor.execute("""Delete FROM KB_Hexes_Improvements WHERE Full_Name = ?""", (improvement,))
                await cursor.execute("""Delete FROM KB_Hexes_Constructed WHERE Full_Name = ?""", (improvement,))
                await cursor.execute(
                    """Insert into A_Audit_All (Author, Timestamp, Database_Changed, Modification, Reason) VALUES (?, ?, ?, ?, ?)""",
                    (author, datetime.datetime.now(), "KB_Hexes_Improvements", "Delete",
                     f"Deleted the hex improvement of {improvement}"))
                await db.commit()
                status = f"You have removed the hex improvement of {improvement}!"
                return status
    except (TypeError, ValueError, aiosqlite.Error) as e:
        logging.exception(f"Error in remove_hex_improvements: {e}")
        return "An error occurred while removing a hex improvement."


async def modify_hex_improvements(
        guild_id: int,
        author: int,
        improvement: typing.Optional[str] = None,
        new_improvement: typing.Optional[str] = None,
        type: typing.Optional[str] = None,
        subtype: typing.Optional[str] = None,
        quality: typing.Optional[int] = None,
        build_points: typing.Optional[int] = None,
        economy: typing.Optional[int] = None,
        loyalty: typing.Optional[int] = None,
        stability: typing.Optional[int] = None,
        unrest: typing.Optional[int] = None,
        consumption: typing.Optional[int] = None,
        defence: typing.Optional[int] = None,
        taxation: typing.Optional[int] = None,
        cavernous: typing.Optional[int] = None,
        coastline: typing.Optional[int] = None,
        desert: typing.Optional[int] = None,
        forest: typing.Optional[int] = None,
        hills: typing.Optional[int] = None,
        jungle: typing.Optional[int] = None,
        marsh: typing.Optional[int] = None,
        mountains: typing.Optional[int] = None,
        plains: typing.Optional[int] = None,
        water: typing.Optional[int] = None,
        source: typing.Optional[int] = None,
        size: typing.Optional[int] = None) -> str:
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute("Select 1 from kb_hexes_improvements WHERE Full_Name = ?", (improvement,))
            test = await cursor.fetchone()
            if test is None:
                return f"Hex Improvement of {improvement} was not found."
            if new_improvement is not None:
                await cursor.execute("select 1 from kb_hexes_improvement where full_name = ?", (new_improvement,))
                duplicate = await cursor.fetchone()
                if duplicate:
                    return f"Hex Improvement of {new_improvement} was found. Please do not try and duplicate names."

            if new_improvement is not None:
                await cursor.execute("""UPDATE KB_Hexes_Constructed Set Full_Name = ? WHERE Full_Name = ?""", (new_improvement,improvement))

            await cursor.execute("""UPDATE kb_hexes_improvements SET 
                Full_Name = Coalesce(?, Full_Name),
                Type = Coalesce(?, Type),
                Subtype = Coalesce(?, subtype),
                Quality = Coalesce(?, Quality),
                build_points = Coalesce(?, build_points),   
                Economy = round(Coalesce(?, Economy), 3), 
                Loyalty = round(Coalesce(?, loyalty), 3),
                Stability = round(Coalesce(?, stability), 3),
                Unrest = round(Coalesce(?, unrest), 3),
                Consumption = round(Coalesce(?, consumption), 3),
                Defence = round(Coalesce(?, defence), 3),
                Taxation = round(Coalesce(?, Taxation), 3),
                Cavernous = Coalesce(?, Cavernous),
                Coastline = Coalesce(?, Coastline),
                Desert =  Coalesce(?, Desert),
                Forest = Coalesce(?, Forest),
                Hills = Coalesce(?, Hills),
                Jungle = Coalesce(?, Jungle),
                Marsh = Coalesce(?, Marsh),
                mountains = Coalesce(?, mountains),
                Plains = Coalesce(?, Plains),
                Water = Coalesce(?, Water),
                source = Coalesce(?, source),
                size = Coalesce(?, size)
                WHERE Full_Name = ?""",
                (new_improvement, type, subtype, quality, build_points, economy, loyalty, stability, unrest, consumption, defence, taxation, cavernous, coastline, desert,
                 forest, hills, jungle, marsh, mountains, plains, water, improvement, source, size))

            await cursor.execute(
                """Insert into A_Audit_All (Author, Timestamp, Database_Changed, Modification, Reason) VALUES (?, ?, ?, ?, ?)""",
                (author, datetime.datetime.now(), "KB_Hexes_Improvements", "Update",
                 f"Updated the hex improvement of {improvement}"))
            await db.commit()
            status = f"The hex improvement of {improvement} has been modified!"
            return status
    except (TypeError, ValueError, aiosqlite.Error) as e:
        logging.exception(f"Error in modify_hex_improvements: {e}")
        return "An error occurred while modifying a hex improvement."


async def rebalance_kingdom_building(
        guild_id: int,
        author: int) -> str:
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute(
                """UPDATE KB_Kingdoms SET Control_DC = 1, Size = 1, Economy = a.economy, Loyalty = a.loyalty, Stability = a.stability, Fame = 0, Unrest = 0, Consumption = 0
                from AA_Alignment A where KB_Kingdoms.Alignment = A.alignment 
                """)
            await cursor.execute(
                "UPDATE KB_Settlements SET Size = 1, Population = 1, Economy = 0, Loyalty = 0, Stability = 0, Fame = 0, Unrest = 0, Corruption = 0, Crime = 0, Productivity = 0, Law = 0, Lore = 0, Society = 0, Danger = 0, Defence = 0, Base_Value = 0, Spellcasting = 0, Supply = 0")
            await cursor.execute(
                "INSERT into A_Audit_All (Author, Timestamp, Database_Changed, Modification, Reason) VALUES (?, ?, ?, ?, ?)",
                (author, datetime.datetime.now(), "KB_Kingdoms", "Update", "Rebalanced all kingdom buildings"))
            await db.commit()

            status = "All kingdom buildings have been reset to base values."
            return status


    except (TypeError, ValueError, aiosqlite.Error) as e:
        logging.exception(f"Error in rebalance_kingdom_building: {e}")
        return "An error occurred while balancing kingdom buildings."


async def handle_population(
        db: aiosqlite.Connection,
        kingdom: str,
        population: int,
        available_food: int
):
    try:
        unrest = 0
        population_increase = 0
        cursor = await db.cursor()
        await cursor.execute(
            """SELECT SUM(CASE WHEN SUBTYPE = 'Housing' THEN Quality * Amount ELSE 0 END) AS Housing 
            SELECT SUM(CASE WHEN SUBTYPE != 'Housing' THEN Supply * Amount ELSE 0 END) AS Non_Housing
            FROM KB_Buildings WHERE Kingdom = ?""", (kingdom,))
        building_results = await cursor.fetchone()
        (housing, non_housing) = building_results
        housing = housing if housing else 0
        non_housing = non_housing if non_housing else 0
        if housing < non_housing:
            if housing * 250 < population:
                unrest += 1
            else:
                available_housing = housing - (population // 250)
                for x in range(available_housing):
                    population_increase += random.randint(1, 150)
                    if available_food > 5:
                        population_increase += random.randint(1, 100)
        else:
            unrest += 1
        await db.commit()
        return unrest, population_increase
    except Exception as exception:
        logging.error(exception)
        return 0, 0

async def handle_trade(
        db: aiosqlite.Connection,
        kingdom: str,
        food_dataclass: FoodDataClass,
        raw_materials_dataclass: RawMaterialsDataClass,
        simple_crafts_dataclass: SimpleCraftDataClass,
        luxury_crafts_dataclass: LuxuryCraftDataClass,
        turn_id: int,
        eot: bool = False
) -> tuple[int, int, int, int, int, int]:
    try:
        build_points = 0
        cursor= await db.cursor()
        await cursor.execute("Select End_Kingdom, Distance, Husbandry, Seafood, Produce, Grain, Raw_textiles, Ore, Stone, Wood, Textiles, Metallurgy, Woodworking, Stoneworking, Magical_items, luxury from KB_Trade where source_kingdom = ? Order by Random() ", (kingdom,))
        active_trades = await cursor.fetchall()
        if not active_trades:
            return 0, 0, 0, 0, 0, 0
        else:
            food_dict = goods_remaining_dict(food_dataclass)
            raw_materials_dict = goods_remaining_dict(raw_materials_dataclass)
            crafted_materials_dict = goods_remaining_dict(simple_crafts_dataclass)
            complex_materials_dict = goods_remaining_dict(luxury_crafts_dataclass)
            fame_penalty = 0
            for trade in active_trades:
                (end_kingdom, distance, husbandry, seafood, produce, grain, raw_textiles, ore, stone, wood, textiles, metallurgy, woodworking, stoneworking, magical_items, luxury) = trade
                if sum(chain(food_dict.values(), raw_materials_dict.values(), crafted_materials_dict.values(), complex_materials_dict.values())) == 0:
                    break
                resources_requested = sum(chain(husbandry, seafood, produce, grain, raw_textiles, ore, stone, wood, textiles, metallurgy, woodworking, stoneworking, magical_items, luxury))
                husbandry = min(food_dict['husbandry'], husbandry)
                seafood = min(food_dict['seafood'], seafood)
                produce = min(food_dict['produce'], produce)
                grain = min(food_dict['grain'], grain)
                raw_textiles = min(raw_materials_dict['raw_textiles'], raw_textiles)
                ore = min(raw_materials_dict['ore'], ore)
                stone = min(raw_materials_dict['stone'], stone)
                wood = min(raw_materials_dict['wood'], wood)
                textiles = min(crafted_materials_dict['textiles'], textiles)
                metallurgy = min(crafted_materials_dict['metallurgy'], metallurgy)
                woodworking = min(crafted_materials_dict['woodworking'], woodworking)
                stoneworking = min(crafted_materials_dict['stoneworking'], stoneworking)
                magical_items = min(complex_materials_dict['magical_items'], magical_items)
                luxury = min(complex_materials_dict['luxury'], luxury)
                food_dict['husbandry'] -= husbandry
                food_dict['seafood'] -= seafood
                food_dict['produce'] -= produce
                food_dict['grain'] -= grain
                raw_materials_dict['raw_textiles'] -= raw_textiles
                raw_materials_dict['ore'] -= ore
                raw_materials_dict['stone'] -= stone
                raw_materials_dict['wood'] -= wood
                crafted_materials_dict['textiles'] -= textiles
                crafted_materials_dict['metallurgy'] -= metallurgy
                crafted_materials_dict['woodworking'] -= woodworking
                crafted_materials_dict['stoneworking'] -= stoneworking
                complex_materials_dict['magical_items'] -= magical_items
                complex_materials_dict['luxury'] -= luxury
                if eot:
                    await cursor.execute("""
                        Insert into KB_Trade_History(
                            kingdom,
                            date, 
                            husbandry,
                            seafood,
                            produce,
                            grain,
                            raw_textiles,
                            ore,
                            Stone,
                            wood,
                            textiles,
                            Metallurgy,
                            Woodworking,
                            Stoneworking,
                            Magical_Items,
                            luxury,
                            Date) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ? ,? ,? ,? ,? ,? ,?)                    
                    """, (kingdom, turn_id + distance, husbandry, seafood, produce, grain, raw_textiles, ore, stone, wood, textiles, metallurgy, woodworking, stoneworking, magical_items, luxury))
                    basic_sent = sum([husbandry, seafood, produce, grain, raw_textiles, ore, stone, wood])
                    simple_sent = sum([textiles, metallurgy, woodworking, stoneworking])
                    complex_sent = sum([magical_items, luxury])
                    fame_penalty += resources_requested - basic_sent - simple_sent - complex_sent // 10
                    build_points += basic_sent / 10 + simple_sent / 8 + complex_sent / 4
        await cursor.execute("""
        SELECT 
        SUM(CASE WHEN subtype = 'Grain' THEN amount * quality * 5 ELSE 0 END) AS Grain_total,
        SUM(CASE WHEN subtype = 'Produce' THEN amount * quality * 5 ELSE 0 END) AS Produce_total
        SUM(CASE WHEN subtype = 'Husbandry' THEN amount * quality * 5 ELSE 0 END) AS Husbandry_total
        SUM(CASE WHEN subtype = 'Seafood' THEN amount * quality * 5 ELSE 0 END) AS Seafood_total
        FROM KB_Buildings WHERE Kingdom = ?""", (kingdom,))
        food_building_results = await cursor.fetchone()
        (building_grain, building_produce, building_husbandry, building_seafood) = food_building_results
        storable_grain = max(min(building_grain, food_dict["Grain"]), 0)
        storable_produce = max(min(building_produce, food_dict["Produce"]), 0)
        storable_husbandry = max(min(building_husbandry, food_dict["Husbandry"]), 0)
        storable_seafood = max(min(building_seafood, food_dict["Seafood"]), 0)
        await cursor.execute("update KB_Kingdoms set Stored_Grain = ?, Stored_Produce = ?, Stored_Meat = ?, stored_seafood = ? where kingdom = ?",
                             (storable_grain, storable_produce, storable_husbandry, storable_seafood, kingdom))
        await db.commit()
        return round(build_points), storable_grain, storable_produce, storable_husbandry, storable_seafood, round(fame_penalty)
    except Exception as exception:
        logging.exception(exception)
        return 0, 0, 0, 0, 0, 0


async def resolve_turn(
        guild_id: int,
        kingdom: str,
        turn_id: int) -> typing.Union[str, tuple[KingdomInfo, dict, str]]:
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()
            kingdom_info = await fetch_kingdom(guild_id, kingdom, turn_id)
            if kingdom_info is None:
                return f"THe kingdom of {kingdom} could not be fetched."

            await handle_event_duration(db=db, kingdom=kingdom)
            (kingdom_info, settlement_master_dict, farm_penalty, consumption_change, event_status) = handle_event_summary(db=db, kingdom_info=kingdom_info, guild_id=guild_id)

            consumption = kingdom_info.consumption.total * consumption_change
            (food_dataclass, raw_materials_dataclass, simple_crafts_dataclass, luxury_crafts_dataclass,
             available_food, penalty_dict, event) = fetch_resources(db=db, kingdom=kingdom_info, farm_penalty=farm_penalty, consumption=consumption)
            if event:
                await kingdom_event(
                    db=db,
                    kingdom=kingdom,
                    event=event,
                    settlement=None)



            (population_unrest, population_increase) = await handle_population(
                db=db,
                kingdom=kingdom,
                population=kingdom_info.population,
                available_food=sum(available_food.values())
            )
            kingdom_info.unrest.base += population_unrest + penalty_dict['utilization_unrest'] + penalty_dict['food_unrest']
            kingdom_info.stability.turn_penalty = penalty_dict['stability']
            kingdom_info.economy.turn_penalty = penalty_dict['economy']
            kingdom_info.loyalty.turn_penalty = penalty_dict['loyalty']
            stability_check = random.randint(1, 20) + kingdom_info.stability.total - kingdom_info.control_dc.total - kingdom_info.unrest.total
            if stability_check < -5:
                kingdom_info.unrest.base += random.randint(1, 4)
            elif stability_check < 0:
                kingdom_info.unrest.base += 1
            else:
                kingdom_info.unrest.base -= 1


            (build_points_received, storable_grain, storable_produce, storable_husbandry, storable_seafood, fame_penalty) = await handle_trade(db, kingdom, food_dataclass, raw_materials_dataclass, simple_crafts_dataclass, luxury_crafts_dataclass, turn_id)

            kingdom_info.build_points += (random.randint(1, 20) + kingdom_info.economy.total - kingdom_info.unrest.total) // 3 + build_points_received
            if kingdom_info.build_points < 0:
                kingdom_info.stability.base += 1
            kingdom_info.fame.base -= fame_penalty
            await cursor.execute(
                "Update KB_Kingdoms Set Build_Points = ?, population = ?, fame = ?, unrest = ?, stability = ?, economy = ?, loyalty = ? where kingdom = ?",
                (kingdom_info.build_points,
                 kingdom_info.population,
                 kingdom_info.fame.base,
                 kingdom_info.unrest.base,
                 kingdom_info.stability.base,
                 kingdom_info.economy.base,
                 kingdom_info.loyalty.base,
                 kingdom_info.kingdom))
            await cursor.execute("Insert into KB_Turn_Penalty_Kingdom(TurnID, Kingdom, Economy, Loyalty, Stability, Unrest, Fame) Values (?, ?, ?, ?, ?, ?, ?",
                                 (turn_id + 1, penalty_dict['economy'], penalty_dict['loyalty'], penalty_dict['stability'], 0, 0))

            await db.commit()
            new_kingdom_status = await fetch_kingdom(guild_id=guild_id, kingdom=kingdom, turn_id=turn_id)
            for settlement_info in settlement_master_dict.keys():
                info = settlement_master_dict[settlement_info]
                await cursor.execute(
                    "INSERT INTO KB_Turn_Penalty_Settlement(TurnID, Settlement, Corruption, Crime, Productivity, Law, Lore, Society, Danger, Defence",
                    (turn_id + 1, info.settlement, info.corruption, info.crime, info.productivity, info.law, info.lore,
                     info.society, info.danger, info.defence))
            if new_kingdom_status.unrest.total > 10:
                await cursor.execute(
                    "SELECT ID FROM KB_Hexes where IsTown = 0 and Kingdom = ? Order by Random() Limit 1", (kingdom,))
                random_hex = await cursor.fetchone()
                await cursor.execute("UPDATE KB_Hexes SET Kingdom = Null WHERE ID = ?", (random_hex,))
                new_kingdom_status.size.hex_value -= 1
            return new_kingdom_status, settlement_master_dict, event_status
    except Exception as e:
        return f"An error occurred while resolving the turn. {e}"




def safe_int_complex(a, b, c, d):
    """Safely add two values together, treating None as zero and converting to Decimal if necessary."""
    # Treat None as zero
    a = a if a is not None else 0
    b = b if b is not None else 0
    c = c if c is not None else 0
    d = d if d is not None else 0

    # If either value is a Decimal, convert both to Decimal
    if isinstance(a, int) or isinstance(b, int) or isinstance(c, int):
        a = int(a)
        b = int(b)
        c = int(c)
        d = int(d)
    return a + b + c + d


class OverseerCommands(commands.Cog, name='overseer'):
    def __init__(self, bot):
        self.bot = bot

    overseer_group = discord.app_commands.Group(
        name='overseer',
        description='Commands related to kingdom management'
    )

    kingdom_group = discord.app_commands.Group(
        name='kingdom',
        description='Commands related to kingdom management',
        parent=overseer_group
    )

    settlement_group = discord.app_commands.Group(
        name='settlement',
        description='Commands related to settlement management',
        parent=overseer_group
    )

    hex_group = discord.app_commands.Group(
        name='hex',
        description='Commands related to settlement management',
        parent=overseer_group
    )

    blueprint_group = discord.app_commands.Group(
        name='blueprint',
        description='Commands related to blueprint management',
        parent=overseer_group
    )

    leadership_group = discord.app_commands.Group(
        name='leadership',
        description='Commands related to event management',
        parent=overseer_group
    )

    event_group = discord.app_commands.Group(
        name='event',
        description='Commands related to event management',
        parent=overseer_group
    )

    weather_group = discord.app_commands.Group(
        name='weather',
        description='Commands related to weather management',
        parent=overseer_group
    )

    @overseer_group.command()
    async def help(self, interaction: discord.Interaction):
        """Help commands for the associated tree"""
        embed = discord.Embed(title=f"Overseer Help", description=f'This is a list of Overseer help commands',
                              colour=discord.Colour.blurple())
        embed.add_field(name=f'**blueprint_add**',  # Done
                        value=f'The command for an overseer to create a new blueprint for players to use..',
                        inline=False)
        embed.add_field(name=f'**blueprint_remove**', value=f'This command removes blueprints from player usage.',
                        # Done
                        inline=False)
        embed.add_field(name=f'**blueprint_modify**',
                        value=f'This command modifies a blueprint that is already in use.',  # Done
                        inline=False)
        embed.add_field(name=f'**kingdom_modifiers**',  # Done
                        value=f'This command adjusts the custom modifiers associated with a kingdom.', inline=False)
        embed.add_field(name=f'**settlement_modifiers**',  # Done
                        value=f'This command adjusts the custom modifiers associated with a settlement.', inline=False)
        embed.add_field(name=f'**settlement_decay**',  # Done
                        value=f'This command modifies the multiplier for stabilization points a settlement requires in order to build.',
                        inline=False)  # Done
        embed.add_field(name=f'**improvement_add**',
                        value=f'This command adds a new hex improvement for players to build',
                        inline=False)  # Done
        embed.add_field(name=f'**improvement_remove**',  # Done
                        value=f'This command removes hex improvements from options players can build.', inline=False)
        embed.add_field(name=f'**improvement_modify**',  # Done
                        value=f'This command modifies hex improvements that are available to build, or have been built',
                        inline=False)  # Done
        embed.add_field(name=f'**kingdom_tables_rebalance**',  # Done
                        value=f'Forced the kingdom and settlement tables to rebalance.', inline=False)
        await interaction.response.send_message(embed=embed)

    @kingdom_group.command(name='modifiers', description='Adjust the custom modifiers associated with a kingdom')
    @app_commands.autocomplete(kingdom=kingdom_commands.kingdom_autocomplete)
    @app_commands.autocomplete(region=autocomplete.region_autocomplete)
    async def kingdom_modifiers(self, interaction: discord.Interaction, kingdom: str, region: typing.Optional[str],
                                control_dc: typing.Optional[int],
                                economy: typing.Optional[int], loyalty: typing.Optional[int],
                                stability: typing.Optional[int], fame: typing.Optional[int],
                                unrest: typing.Optional[int], consumption: typing.Optional[int]):
        """Adjust the custom modifiers associated with a kingdom"""
        await interaction.response.defer(thinking=True)
        try:
            status = await customize_kingdom_modifiers(interaction.guild_id, interaction.user.id, kingdom, control_dc,
                                                       economy, loyalty, stability, fame, unrest, consumption, region)
            await interaction.followup.send(status)
        except (TypeError, ValueError) as e:
            logging.exception(f"Error in kingdom_modifiers: {e}")
            await interaction.followup.send("An error occurred while customizing kingdom modifiers.")

    @kingdom_group.command(name='overpower', description='Overpower a kingdom and assume direct control.')
    @app_commands.autocomplete(kingdom=kingdom_commands.kingdom_autocomplete)
    async def kingdom_overpower(self, interaction: discord.Interaction, kingdom: str, password: str,
                                character_name: str):
        """Overpower a kingdom and assume direct control."""
        await interaction.response.defer(thinking=True)
        try:
            new_password = kingdom_commands.encrypt_password(password)
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute("Update KB_Kingdoms SET Password = ? WHERE Kingdom = ?", (new_password, kingdom))
                await cursor.execute("Update KB_Leadership SET Character_Name = ?, Player_ID = ? where kingdom = ?",
                                     (character_name, interaction.user.id, kingdom))
                await db.commit()
                await interaction.followup.send(
                    "You have successfully overpowered the kingdom, assigning yourself as King and setting all leaders to be you.")

        except (TypeError, ValueError) as e:
            logging.exception(f"Error in kingdom_overpower: {e}")
            await interaction.followup.send(f"An error occurred while overpowering a kingdom. {e}")

    @kingdom_group.command(name="build_points", description="Adjust the build points of a kingdom.")
    @app_commands.autocomplete(kingdom=kingdom_commands.kingdom_autocomplete)
    async def kingdom_build_points(self, interaction: discord.Interaction, kingdom: str, build_points: int):
        """Adjust the build points of a kingdom."""
        await interaction.response.defer(thinking=True)
        try:
            status = await kingdom_commands.adjust_bp(interaction.guild_id, interaction.user.id, kingdom, build_points,
                                                      False)
            await interaction.followup.send(status)
        except (TypeError, ValueError) as e:
            logging.exception(f"Error in kingdom_build_points: {e}")
            await interaction.followup.send("An error occurred while adjusting kingdom build points.")

    @kingdom_group.command(name="resolve_turn", description="Resolve a kingdom's end of turn.")
    @app_commands.autocomplete(kingdom=kingdom_commands.kingdom_autocomplete)
    async def kingdom_eot(self, interaction: discord.Interaction, kingdom: str, turn_id: int):
        """Resolve a kingdom's end of turn."""
        await interaction.response.defer(thinking=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute("Select Kingdom from KB_Kingdoms where Kingdom = ?", (kingdom))
                if not kingdom:
                    await interaction.followup.send("Ya need a kingdom dingus"
                    )
                    return
                (kingdom_info, eot_string) = resolve_turn(interaction.guild_id, kingdom, turn_id)
                pass
        except Exception as e:
            logging.exception(f"Error in kingdom_eot: {e}")
            await interaction.followup.send("An error occurred while attempting to resolve a kingdom.")


    @settlement_group.command(name='modifiers', description='Adjust the custom modifiers associated with a settlement')
    @app_commands.autocomplete(kingdom=kingdom_commands.kingdom_autocomplete)
    @app_commands.autocomplete(settlement=kingdom_commands.settlement_autocomplete)
    async def settlement_modifiers(self, interaction: discord.Interaction, kingdom: str, settlement: str,
                                   corruption: typing.Optional[int], crime: typing.Optional[int],
                                   productivity: typing.Optional[int], law: typing.Optional[int],
                                   lore: typing.Optional[int], society: typing.Optional[int],
                                   danger: typing.Optional[int], defence: typing.Optional[int],
                                   base_value: typing.Optional[int], spellcasting: typing.Optional[int],
                                   supply: typing.Optional[int]):
        """Adjust the custom modifiers associated with a settlement"""
        await interaction.response.defer(thinking=True)
        try:
            status = await custom_settlement_modifiers(
                interaction.guild_id, interaction.user.id, kingdom, settlement,
                corruption, crime, productivity, law, lore, society, danger,
                defence, base_value, spellcasting, supply)
            await interaction.followup.send(status)
        except (TypeError, ValueError) as e:
            logging.exception(f"Error in settlement_modifiers: {e}")
            await interaction.followup.send("An error occurred while customizing settlement modifiers.")

    @settlement_group.command(name='build', description='Add buildings in a specified settlement.')
    @app_commands.autocomplete(kingdom=kingdom_commands.kingdom_autocomplete)
    @app_commands.autocomplete(settlement=kingdom_commands.settlement_autocomplete)
    async def build_in_settlement(self, interaction: discord.Interaction, kingdom: str, settlement: str, building: str,
                                  amount: int):
        """Add a new blueprint for players to use."""
        await interaction.response.defer(thinking=True)
        try:
            building_info = await kingdom_commands.fetch_building(interaction.guild_id, building)
            if building_info is None:
                await interaction.followup.send(f"The building of {building} does not exist.")
                return
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute("Select Size from KB_Settlements where Kingdom = ? AND Settlement = ?",
                                     (kingdom, settlement))
                size = await cursor.fetchone()
                status = await kingdom_commands.add_building(
                    guild_id=interaction.guild_id,
                    author=interaction.user.id,
                    kingdom=kingdom,
                    settlement=settlement,
                    amount=amount,
                    building_info=building_info,
                    size=size[0])
            await interaction.followup.send(status)
        except (TypeError, ValueError) as e:
            logging.exception(f"Error in build_in_settlement: {e}")
            await interaction.followup.send("An error occurred while adding a building to a settlement.")

    @settlement_group.command(name='remove', description='Remove buildings from a specified KB_Settlements.')
    @app_commands.autocomplete(kingdom=kingdom_commands.kingdom_autocomplete)
    @app_commands.autocomplete(settlement=kingdom_commands.settlement_autocomplete)
    async def remove_from_settlement(
            self, interaction: discord.Interaction, kingdom: str, settlement: str,
            building: str, amount: int):
        """Remove buildings from a specified settlement."""
        await interaction.response.defer(thinking=True)
        try:
            building_info = await kingdom_commands.fetch_building(interaction.guild_id, building)
            if building_info is None:
                await interaction.followup.send(f"The building of {building} does not exist.")
                return
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute("Select Size from KB_Settlements where Kingdom = ? AND Settlement = ?",
                                     (kingdom, settlement))
                size = await cursor.fetchone()
                status = await remove_building(
                    guild_id=interaction.guild_id,
                    author=interaction.user.id,
                    settlement=settlement,
                    amount=amount,
                    building_info=building_info)
            await interaction.followup.send(status)
        except (TypeError, ValueError) as e:
            logging.exception(f"Error in remove_from_settlement: {e}")
            await interaction.followup.send("An error occurred while removing a building from a settlement.")

    @hex_group.command(name='add', description='Add a new hex improvement for players to build')
    @app_commands.autocomplete(type=autocomplete.hex_type_autocomplete)
    @app_commands.autocomplete(subtype=autocomplete.hex_subtype_autocomplete)
    async def add_hex_improvement(
            self, interaction: discord.Interaction, improvement: str, type: str, subtype:str, quality: int,
            build_points: int, economy: float, loyalty: float, stability: float, unrest: float,
            consumption: float, defence: float, taxation: float, cavernous: int, coastline: int,
            desert: int, forest: int, hills: int, jungle: int, marsh: int, mountains: int,
            plains: int, water: int, source: int, size: int):
        """Add a new hex improvement for players to build"""
        await interaction.response.defer(thinking=True)
        try:
            status = await add_hex_improvements(
                interaction.guild_id,
                interaction.user.id,
                improvement,
                type, subtype, quality,
                build_points,
                economy, loyalty, stability, unrest, consumption, defence, taxation,
                cavernous, coastline, desert, forest, hills, jungle, marsh, mountains, plains, water, source, size)
            await interaction.followup.send(status)
        except (TypeError, ValueError) as e:
            logging.exception(f"Error in add_hex_improvement: {e}")
            await interaction.followup.send("An error occurred while adding a hex improvement.")

    @hex_group.command(name='remove', description='Remove hex improvements from options players can build.')
    async def remove_hex_improvement(self, interaction: discord.Interaction, improvement: str):
        """Remove hex improvements from options players can build."""
        await interaction.response.defer(thinking=True)
        try:
            status = await remove_hex_improvements(interaction.guild_id, interaction.user.id, improvement)
            await interaction.followup.send(status)
        except (TypeError, ValueError) as e:
            logging.exception(f"Error in remove_hex_improvement: {e}")
            await interaction.followup.send("An error occurred while removing a hex improvement.")

    @hex_group.command(name='modify',
                       description='Modify hex improvements that are available to build, or have been built')
    @app_commands.autocomplete(type=autocomplete.hex_type_autocomplete)
    @app_commands.autocomplete(subtype=autocomplete.hex_subtype_autocomplete)
    async def modify_hex_improvement(
            self, interaction: discord.Interaction, improvement: str, new_improvement: typing.Optional[str],
            type: typing.Optional[str], subtype: typing.Optional[str], quality: typing.Optional[int],
            build_points: typing.Optional[int],
            economy: typing.Optional[int], loyalty: typing.Optional[int],
            stability: typing.Optional[int], unrest: typing.Optional[int],
            consumption: typing.Optional[int], defence: typing.Optional[int],
            taxation: typing.Optional[int], cavernous: typing.Optional[int],
            coastline: typing.Optional[int], desert: typing.Optional[int],
            forest: typing.Optional[int], hills: typing.Optional[int],
            jungle: typing.Optional[int], marsh: typing.Optional[int],
            mountains: typing.Optional[int], plains: typing.Optional[int],
            water: typing.Optional[int],
            source: typing.Optional[int], size: typing.Optional[int]
            ):
        """Modify hex improvements that are available to build, or have been built"""
        await interaction.response.defer(thinking=True)
        try:
            status = await modify_hex_improvements(
                guild_id=interaction.guild_id,
                author=interaction.user.id,
                improvement=improvement,
                new_improvement=new_improvement,
                type=type,
                subtype=subtype,
                quality=quality,
                build_points=build_points,
                economy=economy,
                loyalty=loyalty,
                stability=stability,
                unrest=unrest,
                consumption=consumption,
                defence=defence,
                taxation=taxation,
                cavernous=cavernous,
                coastline=coastline,
                desert=desert,
                forest=forest,
                hills=hills,
                jungle=jungle,
                marsh=marsh,
                mountains=mountains,
                plains=plains,
                water=water,
                source=source,
                size=size)
            await interaction.followup.send(status)
        except (TypeError, ValueError) as e:
            logging.exception(f"Error in modify_hex_improvement: {e}")
            await interaction.followup.send("An error occurred while modifying a hex improvement.")

    @hex_group.command(name='create', description='create and add a hex into play.')
    @app_commands.autocomplete(kingdom=kingdom_commands.kingdom_autocomplete)
    @app_commands.autocomplete(terrain=hex_terrain_autocomplete)
    @app_commands.autocomplete(region=autocomplete.region_autocomplete)
    @app_commands.choices(
        behavior=[discord.app_commands.Choice(name='set', value=1),
                  discord.app_commands.Choice(name='random', value=2)])
    async def add_hex(self, interaction: discord.Interaction, kingdom: typing.Optional[str], terrain: str, region: str,
                      farm: int,
                      ore: int, stone: int, wood: int, fish: int, behavior: discord.app_commands.Choice[int] = 1):
        await interaction.response.defer(thinking=True)
        try:
            behavior_value = behavior.value if isinstance(behavior, discord.app_commands.Choice) else 1
            if behavior_value == 2:
                farm = random.randint(1, farm) if farm > 0 else 0
                ore = random.randint(1, ore) if ore > 0 else 0
                stone = random.randint(1, stone) if stone > 0 else 0
                wood = random.randint(1, wood) if wood > 0 else 0
                fish = random.randint(1, fish) if fish > 0 else 0
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                if kingdom:
                    await cursor.execute("SELECT kingdom FROM KB_Kingdoms WHERE Kingdom = ?", (kingdom,))
                    kingdom_info = await cursor.fetchone()
                    if not kingdom_info:
                        await interaction.followup.send("The kingdom you are trying to add the hex to does not exist.")
                        return
                await cursor.execute(
                    "INSERT INTO KB_Hexes (Kingdom, Hex_Terrain, Region, Farm, Ore, Stone, wood, fish) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (kingdom, terrain, region, farm, ore, stone, wood, fish))
                await cursor.execute("SELECT Max(ID) from KB_Hexes")
                hex_id = await cursor.fetchone()
                await db.commit()
                await interaction.followup.send(f"You have created the hex id of {hex_id[0]} with the following stats: \r\n" +
                                                f"Kingdom: {kingdom}, Terrain: {terrain}, in region: {region} \r\n" +
                                                f"it can support the following: {farm} farms, {ore} mines, {stone} quarries, {wood} sawmills, {fish} fisheries.")
        except(TypeError, ValueError) as e:
            logging.exception(f"Error in add_hex: {e}")
            await interaction.followup.send("An error occurred while adding a hex.")

    @hex_group.command(name='edit', description='edit a hex in play.')
    @app_commands.autocomplete(kingdom=kingdom_commands.kingdom_autocomplete)
    @app_commands.autocomplete(terrain=hex_terrain_autocomplete)
    @app_commands.autocomplete(region=autocomplete.region_autocomplete)
    @app_commands.choices(
        behavior=[discord.app_commands.Choice(name='set', value=1),
                  discord.app_commands.Choice(name='random', value=2)])
    async def edit_hex(self, interaction: discord.Interaction, hex_id: int, kingdom: typing.Optional[str],
                       terrain: typing.Optional[str], region: typing.Optional[str], farm: typing.Optional[int],
                       ore: typing.Optional[int], stone: typing.Optional[int], wood: typing.Optional[int],
                       fish: typing.Optional[int], behavior: discord.app_commands.Choice[int] = 1):
        await interaction.response.defer(thinking=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute(
                    "SELECT Kingdom, Region, Hex_Terrain, Farm, Ore, Stone, Wood, Fish From KB_Hexes where ID = ?",
                    (hex_id,))
                hex_info = await cursor.fetchone()
                if not hex_info:
                    await interaction.followup.send("The hex with that ID does not exist.")
                    return
                change_kingdom = kingdom if kingdom else hex_info[0]
                change_kingdom = None if change_kingdom == "None" else change_kingdom
                region = region if region else hex_info[1]
                terrain = terrain if terrain else hex_info[2]

            behavior_value = behavior.value if isinstance(behavior, discord.app_commands.Choice) else 1
            if behavior_value == 2:
                if farm:
                    farm = random.randint(1, farm) if farm > 0 else farm
                else:
                    farm = hex_info[3]
                if ore:
                    ore = random.randint(1, ore) if ore > 0 else ore
                else:
                    ore = hex_info[4]
                if stone:
                    stone = random.randint(1, stone) if stone > 0 else stone
                else:
                    stone = hex_info[5]
                if wood:
                    wood = random.randint(1, wood) if wood > 0 else wood
                else:
                    wood = hex_info[6]
                if fish:
                    fish = random.randint(1, fish) if fish > 0 else fish
                else:
                    fish = hex_info[7]
            else:
                farm = farm if farm else hex_info[3]
                ore = ore if ore else hex_info[4]
                stone = stone if stone else hex_info[5]
                wood = wood if wood else hex_info[6]
                fish = fish if fish else hex_info[7]
            await cursor.execute(
                "UPDATE KB_Hexes SET Kingdom = ?, Terrain = ?, Region = ?, Farm = ?, Ore = ?, Stone = ?, wood = ?, fish = ? WHERE ID = ?",
                (change_kingdom, terrain, region, farm, ore, stone, wood, fish, hex_id))
            await cursor.execute("UPDATE KB_Hexes_Constructed SET Kingdom = ? WHERE ID = ?", (change_kingdom, hex_id))
            if kingdom != hex_info[0]:
                if kingdom:
                    status = f"The hex with ID {hex_id} has been updated and added to the kingdom of {kingdom}!\r\nit can support {farm} farms, {ore} mines, {stone} quarries, {wood} woodcutters,and {fish} fisheries."
                else:
                    status = f"The hex with ID {hex_id} has been updated and removed from the original kingdom!\r\nit can support {farm} farms, {ore} mines, {stone} quarries, {wood} woodcutters, and {fish} fisheries."
            else:
                status = f"The hex with ID {hex_id}has been updated!\r\nit can support {farm} farms, {ore} mines, {stone} quarries, {wood} woodcutters, and {fish} fisheries."
            await db.commit()

            await interaction.followup.send(status)
        except(TypeError, ValueError) as e:
            logging.exception(f"Error in add_hex: {e}")
            await interaction.followup.send("An error occurred while adding a hex.")

    @hex_group.command(name='delete', description='delete a hex from play.')
    async def delete_hex(self, interaction: discord.Interaction, hex_id: int):
        await interaction.response.defer(thinking=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute("SELECT Kingdom from KB_Hexes where ID = ?", (hex_id,))
                kingdom = await cursor.fetchone()
                if not kingdom:
                    await interaction.followup.send("The hex with that ID does not exist.")
                    return
                await cursor.execute("DELETE FROM KB_Hexes where ID = ?", (hex_id,))
                await cursor.execute("DELETE FROM KB_Hexes_Constructed where ID = ?", (hex_id,))
                await db.commit()
                await interaction.followup.send(f"The hex with ID {hex_id} has been deleted.")
        except(TypeError, ValueError) as e:
            logging.exception(f"Error in delete_hex: {e}")
            await interaction.followup.send("An error occurred while deleting a hex.")

    @blueprint_group.command(name='add', description='Add a new blueprint for players to use.')
    async def add_blueprint(
            self,
            interaction: discord.Interaction,
            name: str,
            lots: int,
            economy: int,
            loyalty: int,
            stability: int,
            fame: int,
            unrest: int,
            build_points: int,
            defence: int,
            corruption: int,
            crime: int,
            productivity: int,
            law: int,
            lore: int,
            society: int,
            danger: int,
            base_value: int,
            spellcasting: int,
            supply: int,
            district_limit: int,
            settlement_limit: int,
            description: str
    ):
        """Add a new blueprint for players to use."""
        await interaction.response.defer(thinking=True)
        try:
            status = await add_blueprint(
                guild_id=interaction.guild_id,
                author=interaction.user.id,
                building=name,
                build_points=build_points,
                lots=lots,
                economy=economy,
                loyalty=loyalty,
                stability=stability,
                fame=fame,
                unrest=unrest,
                defence=defence,
                corruption=corruption,
                crime=crime,
                productivity=productivity,
                law=law,
                lore=lore,
                society=society,
                danger=danger,
                base_value=base_value,
                spellcasting=spellcasting,
                supply=supply,
                district_limit=district_limit,
                settlement_limit=settlement_limit,
                description=description
            )
            await interaction.followup.send(status)
        except (TypeError, ValueError) as e:
            logging.exception(f"Error in add_blueprint: {e}")
            await interaction.followup.send("An error occurred while adding a blueprint.")

    @blueprint_group.command(name='remove', description='This command removes blueprints from player usage.')
    async def remove_blueprint(self, interaction: discord.Interaction, name: str):
        """This command removes blueprints from player usage."""
        await interaction.response.defer(thinking=True)
        try:
            status = await remove_blueprint(interaction.guild_id, interaction.user.id, name)
            await interaction.followup.send(status)
        except (TypeError, ValueError) as e:
            logging.exception(f"Error in remove_blueprint: {e}")
            await interaction.followup.send("An error occurred while removing a blueprint.")

    @blueprint_group.command(name='modify', description='This command modifies a blueprint that is already in use.')
    async def modify_blueprint(
            self, interaction: discord.Interaction, old_name: str,
            name: typing.Optional[str],
            size: typing.Optional[int],
            economy: typing.Optional[int], loyalty: typing.Optional[int],
            stability: typing.Optional[int], fame: typing.Optional[int],
            unrest: typing.Optional[int], corruption: typing.Optional[int],
            crime: typing.Optional[int], productivity: typing.Optional[int],
            law: typing.Optional[int], lore: typing.Optional[int],
            society: typing.Optional[int], danger: typing.Optional[int],
            defence: typing.Optional[int], base_value: typing.Optional[int],
            spellcasting: typing.Optional[int], supply: typing.Optional[int],
            settlement_limit: typing.Optional[int], district_limit: typing.Optional[int],
            description: typing.Optional[str]):
        """This command modifies a blueprint that is already in use."""
        await interaction.response.defer(thinking=True)
        try:
            status = await modify_blueprint(
                guild_id=interaction.guild_id,
                author=interaction.user.id,
                old_blueprint_name=old_name,
                full_name=name,
                lots=size,
                economy=economy,
                loyalty=loyalty,
                stability=stability,
                fame=fame,
                unrest=unrest,
                corruption=corruption,
                crime=crime,
                productivity=productivity,
                law=law,
                lore=lore,
                society=society,
                danger=danger,
                defence=defence,
                base_value=base_value,
                spell_casting=spellcasting,
                supply=supply,
                settlement_limit=settlement_limit,
                district_limit=district_limit,
                description=description
            )

            await interaction.followup.send(status)
        except (TypeError, ValueError) as e:
            logging.exception(f"Error in modify_blueprint: {e}")
            await interaction.followup.send("An error occurred while modifying a blueprint.")

    @leadership_group.command(name="modify",
                              description="Modify a leader, by changing their ability score or who is in charge")
    @app_commands.autocomplete(kingdom=kingdom_commands.kingdom_autocomplete)
    @app_commands.autocomplete(title=kingdom_commands.leadership_autocomplete)
    async def modify_leadership(self, interaction: discord.Interaction, kingdom: str,
                                character_name: str, title: str,
                                modifier: int):
        """This command is used to modify a leader's ability score or who is in charge of a kingdom"""
        await interaction.response.defer(thinking=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute("SELECT Password, Size FROM kb_Kingdoms WHERE Kingdom = ?", (kingdom,))
                kingdom_results = await cursor.fetchone()

                await cursor.execute(
                    "SELECT Ability, Economy, Loyalty, Stability FROM AA_Leadership_Roles WHERE Title = ?",
                    (title,))
                leadership_info = await cursor.fetchone()
                (ability, economy, loyalty, stability) = leadership_info
                abilities = ability.split(" / ")
                options = [
                    discord.SelectOption(label=ability) for ability in abilities
                ]

                additional = 1 if title != "Ruler" and kingdom_results[1] < 26 else 2
                additional = 3 if title == "Ruler" and kingdom_results[1] < 101 else additional
                view = kingdom_commands.LeadershipView(
                    options, interaction.guild_id, interaction.user.id, kingdom, title, character_name,
                    additional, economy, loyalty, stability, kingdom_results[1], modifier=modifier,
                    recipient_id=interaction.user.id)

                await interaction.followup.send("Please select an attribute:", view=view)
            # Store the message object
            view.message = await interaction.original_response()
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"Error modifying  Leadership: {e}")
            await interaction.followup.send(content="An error occurred while modifying  Leadership.")

    @leadership_group.command(name="remove", description="Remove a leader from a kingdom")
    @app_commands.autocomplete(kingdom=kingdom_commands.kingdom_autocomplete)
    @app_commands.autocomplete(title=kingdom_commands.leadership_autocomplete)
    async def remove(self, interaction: discord.Interaction, kingdom: str, title: str):
        """This command is used to remove a leader and make it a vacant position"""
        await interaction.response.defer(thinking=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute("SELECT Password FROM kb_Kingdoms WHERE Kingdom = ?", (kingdom,))
                kingdom_results = await cursor.fetchone()
                if not kingdom_results:
                    await interaction.followup.send(content=f"The kingdom of {kingdom} does not exist.")
                    return
                status = await kingdom_commands.remove_leader(interaction.guild_id, interaction.user.id, kingdom, title)
                await interaction.followup.send(content=status)
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"Error removing leader: {e}")
            await interaction.followup.send(content="An error occurred while removing the leader.")

    @event_group.command(name="create", description="Create a new event for the kingdom")
    @app_commands.choices(
        scale=[discord.app_commands.Choice(name='Kingdom Event', value=1),
               discord.app_commands.Choice(name='Settlement Event', value=0)])
    @app_commands.choices(
        effects_hex=[discord.app_commands.Choice(name='affects a hex', value=1),
             discord.app_commands.Choice(name='does not affect hexes', value=0)])
    @app_commands.choices(
        requirements=[discord.app_commands.Choice(name='succeed at one check', value=1),
                      discord.app_commands.Choice(name='succeed at both checks', value=2)])
    @app_commands.choices(
        event_type=[discord.app_commands.Choice(name='beneficial', value=1),
              discord.app_commands.Choice(name='problematic', value=2)])
    @app_commands.choices(
        first_check=[discord.app_commands.Choice(name='Loyalty', value=1),
                     discord.app_commands.Choice(name='Stability', value=2),
                     discord.app_commands.Choice(name='Economy', value=3)])
    @app_commands.choices(
        second_check=[discord.app_commands.Choice(name='Loyalty', value=1),
                      discord.app_commands.Choice(name='Stability', value=2),
                      discord.app_commands.Choice(name='Economy', value=3),
                      discord.app_commands.Choice(name='Demand Building', value=4),
                      discord.app_commands.Choice(name='Demand Improvement', value=5)])
    @app_commands.autocomplete(region=autocomplete.region_autocomplete)
    @app_commands.autocomplete(bonus=modifier_autocomplete)
    @app_commands.autocomplete(penalty=modifier_autocomplete)
    async def create_event(
            self, interaction: discord.Interaction, scale: discord.app_commands.Choice[int], likelihood: int, name: str,
            description: str, special: typing.Optional[str],
            event_type: discord.app_commands.Choice[int], first_check: typing.Optional[discord.app_commands.Choice[int]],
            penalty: str, bonus: str,
            second_check: typing.Optional[discord.app_commands.Choice[int]], region: str = 'All', duration: int =1,
            effects_hex: discord.app_commands.Choice[int] = 0, requirements: discord.app_commands.Choice[int] = 0):
        """Create a new event for the KB_Events Table"""
        await interaction.response.defer(thinking=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute("SELECT Name from KB_Events where Name = ?", (name,))
                event = await cursor.fetchone()
                if event:
                    await interaction.followup.send("An event with that name already exists.")
                    return
                scale_value = scale.value if isinstance(scale, discord.app_commands.Choice) else scale
                hex_value = effects_hex.value if isinstance(effects_hex, discord.app_commands.Choice) else effects_hex
                requirements_value = requirements.value if isinstance(requirements,
                                                                      discord.app_commands.Choice) else requirements
                type_value = event_type.value if isinstance(event_type, discord.app_commands.Choice) else event_type
                first_check_value = first_check.value if isinstance(first_check,
                                                                    discord.app_commands.Choice) else first_check
                second_check_value = second_check.value if isinstance(second_check,
                                                                      discord.app_commands.Choice) else second_check
                if second_check_value and not first_check_value:
                    if second_check_value == 4 or second_check_value == 5:
                        await interaction.followup.send(
                            "You must select a first check to demand a building or improvement.")
                        return
                    first_check_value = second_check_value
                    second_check_value = None
                await cursor.execute("""INSERT INTO KB_Events(
                scale, likelihood, Region, Type, 
                Name, Effect, Special,  
                Check_A, Check_B, Success_Requirements, 
                Duration, Bonus, Penalty, Hex) 
                VALUES 
                (?, ?, ?, ?, 
                ?, ?, ?, 
                ?, ?, ?,
                ?, ?, ?, ?
                )""", (
                    scale_value, likelihood, region, type_value,
                    name, description, special,
                    first_check_value, second_check_value, requirements_value,
                    duration, penalty, bonus, hex_value
                ))
                await db.commit()
        except (TypeError, ValueError) as e:
            logging.exception(f"Error in create_event: {e}")
            await interaction.followup.send("An error occurred while creating an event.")

    @event_group.command(name="modify", description="update an event for the kingdom building")
    @app_commands.choices(
        scale=[discord.app_commands.Choice(name='Kingdom Event', value=1),
               discord.app_commands.Choice(name='Settlement Event', value=0)])
    @app_commands.choices(
        hex=[discord.app_commands.Choice(name='affects a hex', value=1),
             discord.app_commands.Choice(name='does not affect hexes', value=0)])
    @app_commands.choices(
        requirements=[discord.app_commands.Choice(name='succeed at one check', value=1),
                      discord.app_commands.Choice(name='succeed at both checks', value=2)])
    @app_commands.choices(
        type=[discord.app_commands.Choice(name='beneficial', value=1),
              discord.app_commands.Choice(name='problematic', value=2)])
    @app_commands.choices(
        first_check=[discord.app_commands.Choice(name='Loyalty', value=1),
                     discord.app_commands.Choice(name='Stability', value=2),
                     discord.app_commands.Choice(name='Economy', value=3)])
    @app_commands.choices(
        second_check=[discord.app_commands.Choice(name='Loyalty', value=1),
                      discord.app_commands.Choice(name='Stability', value=2),
                      discord.app_commands.Choice(name='Economy', value=3),
                      discord.app_commands.Choice(name='Demand Building', value=4),
                      discord.app_commands.Choice(name='Demand Improvement', value=5)])
    @app_commands.autocomplete(region=autocomplete.region_autocomplete)
    @app_commands.autocomplete(bonus=modifier_autocomplete)
    @app_commands.autocomplete(penalty=modifier_autocomplete)
    @app_commands.autocomplete(old_name=event_name_autocomplete)
    async def modify_event(
            self, interaction: discord.Interaction, old_name: str,
            scale: typing.Optional[discord.app_commands.Choice[int]],
            likelihood: typing.Optional[int], new_name: typing.Optional[str], description: typing.Optional[str],
            special: typing.Optional[str],
            type: typing.Optional[discord.app_commands.Choice[int]],
            first_check: typing.Optional[discord.app_commands.Choice[int]],
            second_check: typing.Optional[discord.app_commands.Choice[int]], region: typing.Optional[str],
            hex: typing.Optional[discord.app_commands.Choice[int]],
            requirements: typing.Optional[discord.app_commands.Choice[int]],
            bonus: typing.Optional[str], penalty: typing.Optional[str]):
        """Create a new event for the kingdom"""
        await interaction.response.defer(thinking=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute(
                    "SELECT Scale, Likelihood, Region, Type, Name, Effect, Special, Check_A, Check_B, Success_Requirement, Duration, Bonus, Penalty, Hex from KB_Events where Name = ?",
                    (old_name,))
                event = await cursor.fetchone()
                if not event:
                    await interaction.followup.send("An event with that name does not exist.")
                    return
                (
                    info_scale, info_likelihood, info_region, info_type, info_name, info_effect, info_special,
                    info_check_a,
                    info_check_b, info_requirements, info_duration, info_bonus, info_penalty, info_hex) = event
                scale_value = compare_choice(scale, info_scale)
                hex_value = compare_choice(hex, info_hex)
                requirements_value = compare_choice(requirements, info_requirements)
                type_value = compare_choice(type, info_type)
                first_check_value = compare_choice(first_check, info_check_a)
                second_check_value = compare_choice(second_check, info_check_b)
                likelihood = compare_new(likelihood, info_likelihood)
                region = compare_new(region, info_region)
                name = compare_new(info_name, info_name)
                description = compare_new(description, info_effect)
                special = compare_new(special, info_special)
                bonus = compare_new(bonus, info_bonus)
                penalty = compare_new(penalty, info_penalty)
                if second_check_value and not first_check_value:
                    if second_check_value == 4 or second_check_value == 5:
                        await interaction.followup.send(
                            "You must select a first check to demand a building or improvement.")
                        return
                    first_check_value = second_check_value
                    second_check_value = None
                await cursor.execute(
                    "UPDATE KB_Events SET name = ?, scale = ?, likelihood = ?, Region = ?, Name = ?, Effect = ?, Special = ?, Type = ?, Check_a = ?, Check_b = ?, Penalty = ?, Bonus = ?, Hex = ?, Success_Requirements = ? WHERE Name = ?",
                    (name, scale_value, likelihood, region, name, description, special, type_value, first_check_value,
                     second_check_value, penalty, bonus, hex_value, requirements_value, old_name))
                if new_name:
                    await cursor.execute("UPDATE KB_Events_Consequence SET Name = ? WHERE Name = ?",
                                         (new_name, old_name))
                await db.commit()
        except (TypeError, ValueError) as e:
            logging.exception(f"Error in create_event: {e}")
            await interaction.followup.send("An error occurred while creating an event.")

    @event_group.command(name="delete", description="Delete an event from the kingdom")
    @app_commands.autocomplete(name=event_name_autocomplete)
    async def delete_event(self, interaction: discord.Interaction, name: str):
        """Create a new event for the kingdom"""
        await interaction.response.defer(thinking=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute("SELECT Name from KB_Events where Name = ?", (name,))
                event = await cursor.fetchone()
                if not event:
                    await interaction.followup.send("An event with that name does not exist.")
                    return
                await cursor.execute("DELETE FROM KB_Events where Name = ?", (name,))
                await cursor.execute("DELETE FROM KB_Events_Active where Name = ?", (name,))
                await cursor.execute("DELETE FROM KB_Events_Consequence where Name = ?", (name,))
                await db.commit()
                await interaction.followup.send(f"The event with the name {name} has been deleted.")
        except (TypeError, ValueError) as e:
            logging.exception(f"Error in create_event: {e}")
            await interaction.followup.send("An error occurred while creating an event.")

    @event_group.command(name="complication", description="Add an Event Effect to an event")
    @app_commands.choices(
        severity=[discord.app_commands.Choice(name='on creation', value=-1),
                  discord.app_commands.Choice(name='passive / failed result', value=0),
                  discord.app_commands.Choice(name='single pass', value=1),
                  discord.app_commands.Choice(name='passed both', value=2)])
    @app_commands.choices(
        reroll_behavior=[discord.app_commands.Choice(name='set as result', value=-0),
                       discord.app_commands.Choice(name='randomize result', value=1),
                       discord.app_commands.Choice(name='percentile effect', value=2),
                       discord.app_commands.Choice(name='exploding on max', value=3),
                       discord.app_commands.Choice(name='Explodes into multiple on max', value=4),
                       discord.app_commands.Choice(name='boost type', value=5)
                         ])
    @app_commands.autocomplete(name=event_name_autocomplete)
    @app_commands.autocomplete(effect_type=type_value_autocomplete)
    async def create_complication(
            self, interaction: discord.Interaction, name: str,
            severity: typing.Optional[discord.app_commands.Choice[int]],
            effect_type: str, value: int, reroll_behavior: typing.Optional[discord.app_commands.Choice[int]]):
        """Create a new event for the kingdom"""
        await interaction.response.defer(thinking=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute("SELECT Name, Scale from KB_Events where Name = ?", (name,))
                event = await cursor.fetchone()
                if not event:
                    await interaction.followup.send("An event with that name does not exist.")
                    return
                await cursor.execute("Select 1 from kb_events where Type = ? limit 1", (effect_type,))
                type_of_effect = await cursor.fetchone()
                if not type_of_effect:
                    await interaction.followup.send(f"Nothing that affects {effect_type} is programmed in you wally.")
                    return
                severity_value = severity.value if isinstance(severity, discord.app_commands.Choice) else severity
                reroll_value = reroll_behavior.value if isinstance(reroll_behavior, discord.app_commands.Choice) else reroll_behavior
                if reroll_value == 5 and (effect_type not in kingdom_status_list or effect_type not in settlement_dict.keys() or event[1] != 'Settlement'):
                    await interaction.followup.send("A Reroll value of 5 can only be applied to buildings which modify settlement or kingdom stats. (Like Economy, Loyalty, Stability, etc) and MUST be a settlement Event")
                    return
                if reroll_value == 2 and (effect_type != 'Consumption' or event[1] != "Kingdom"):
                    await interaction.followup.send("A reroll value of 2 is finicky as fuck and only applies to consumption and even then, only kingdom level events")
                    return


                await cursor.execute(
                    "INSERT INTO KB_Events_Consequence (Name, Severity, Type, Value, Reroll) VALUES (?, ?, ?, ?, ?)",
                    (name, severity_value, effect_type, value, reroll_value))
                await db.commit()
                await cursor.execute("SELECT MAX(ID) from KB_Events_Consequence")
                event_id = await cursor.fetchone()
                await interaction.followup.send(f"The complication has been added to the event with ID {event_id[0]}.")
        except (TypeError, ValueError) as e:
            logging.exception(f"Error in create_complication: {e}")
            await interaction.followup.send("An error occurred while creating an event.")

    @event_group.command(name="modify_complication", description="Modify an Event Effect to an event")
    @app_commands.choices(
        severity=[discord.app_commands.Choice(name='on creation', value=-1),
                  discord.app_commands.Choice(name='passive / failed result', value=0),
                  discord.app_commands.Choice(name='single pass', value=1),
                  discord.app_commands.Choice(name='passed both', value=2)])
    @app_commands.choices(
        reroll_behavior=[discord.app_commands.Choice(name='set as result', value=-0),
                       discord.app_commands.Choice(name='randomize result', value=1),
                       discord.app_commands.Choice(name='percentile effect', value=2),
                       discord.app_commands.Choice(name='exploding on max', value=3),
                       discord.app_commands.Choice(name='Explodes into multiple on max', value=4),
                       discord.app_commands.Choice(name='boost type', value=5)])
    @app_commands.autocomplete(name=event_name_autocomplete)
    @app_commands.autocomplete(effect_type=type_value_autocomplete)
    async def modify_complication(
            self, interaction: discord.Interaction, name: typing.Optional[str], event_id: int,
            severity: typing.Optional[discord.app_commands.Choice[int]],
            effect_type: typing.Optional[str], value: typing.Optional[int],
            reroll_behavior: typing.Optional[discord.app_commands.Choice[int]]):
        """Modify an existing event consequence for the kingdom"""
        await interaction.response.defer(thinking=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute(
                    "SELECT Name, Severity, Type, Value, Reroll from KB_Events_Consequence where ID = ?", (event_id,))
                event = await cursor.fetchone()
                if not event:
                    await interaction.followup.send("An event with that name does not exist.")
                    return
                (old_name, old_severity, old_type, old_value, old_reroll) = event
                name = compare_new(name, old_name)
                severity_value = compare_choice(severity, old_severity)
                reroll_value = compare_choice(reroll_behavior, old_reroll)
                effect_type = compare_new(effect_type, old_type)
                value = compare_new(value, old_value)
                if reroll_value == 5 and (effect_type not in kingdom_status_list or effect_type not in settlement_dict.keys()):
                    await interaction.followup.send("A Reroll value of 5 can only be applied to buildings which modify settlement or kingdom stats. (Like Economy, Loyalty, Stability, etc)")
                    return
                if reroll_value == 2 and effect_type != 'Consumption':
                    await interaction.followup.send("A reroll value of 2 is finicky as fuck and only applies to consumption")
                    return


                await cursor.execute(
                    "UPDATE KB_Events_Consequence SET Name = ?, Severity = ?, Type = ?, Value = ?, Reroll = ? WHERE ID = ?",
                    (name, severity_value, effect_type, value, reroll_value, event_id))
                await db.commit()
                await interaction.followup.send(f"The complication has been modified.")
        except (TypeError, ValueError) as e:
            logging.exception(f"Error in create_complication: {e}")
            await interaction.followup.send("An error occurred while creating an event.")

    @event_group.command(name="delete_complication", description="Delete an Event Effect to an event")
    @app_commands.autocomplete(name=event_name_autocomplete)
    async def delete_complication(self, interaction: discord.Interaction, name: str, event_id: int):
        """Delete an Event from a kingdom"""
        await interaction.response.defer(thinking=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute("SELECT Name from KB_Events where Name = ?", (name,))
                event = await cursor.fetchone()
                if not event:
                    await interaction.followup.send("An event with that name does not exist.")
                    return
                await cursor.execute("DELETE FROM KB_Events_Consequence where ID = ?", (event_id,))
                await db.commit()
                await interaction.followup.send(f"The complication has been removed.")
        except (TypeError, ValueError) as e:
            logging.exception(f"Error in create_complication: {e}")
            await interaction.followup.send("An error occurred while creating an event.")

    @event_group.command(name="display", description="display a list of events")
    @app_commands.autocomplete(name=event_name_autocomplete)
    @app_commands.choices(
        view_type=[discord.app_commands.Choice(name='all', value=0),
              discord.app_commands.Choice(name='problematic', value=1),
              discord.app_commands.Choice(name='beneficial', value=2)])
    async def display_event(self, interaction: discord.Interaction, name: typing.Optional[str],
                            view_type: discord.app_commands.Choice[int] = 1):
        """Display a list of events"""
        await interaction.response.defer(thinking=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                view_type_value = int(view_type.value) if isinstance(view_type, discord.app_commands.Choice) else view_type
                if name:
                    if view_type_value == 1:
                        await cursor.execute("SELECT Name from KB_Events", (name,))
                    elif view_type_value == 2:
                        await cursor.execute("SELECT Name from KB_Events where Type = 'Problematic'", (name,))
                    else:
                        await cursor.execute("SELECT Name from KB_Events where Type = 'Beneficial'", (name,))
                    events = await cursor.fetchall()
                    for idx, event in enumerate(events):
                        if name in event:
                            offset = idx
                            break
                    if not offset:
                        offset = 0
                else:
                    offset = 0

                view = views.EventDisplayView(
                    user_id=interaction.user.id, guild_id=interaction.guild_id, offset=offset, limit=10,
                    view_type=view_type_value,
                    interaction=interaction)
                await view.update_results()
                await view.create_embed()
                await interaction.followup.send(embed=view.embed, view=view)
        except (TypeError, ValueError) as e:
            logging.exception(f"Error in display_event: {e}")
            await interaction.followup.send("An error occurred while displaying events.")

    @event_group.command(name="spawn", description="spawn an event for a kingdom")
    @app_commands.autocomplete(kingdom=kingdom_commands.kingdom_autocomplete)
    @app_commands.autocomplete(event=event_name_autocomplete)
    @app_commands.autocomplete(region=region_autocomplete)
    @app_commands.choices(
        event_type=[discord.app_commands.Choice(name='general', value='general'),
                   discord.app_commands.Choice(name='beneficial', value='beneficial'),
                   discord.app_commands.Choice(name='problematic', value='problematic')])
    @app_commands.choices(
        localization=[discord.app_commands.Choice(name='Kingdom', value='Kingdom'),
                    discord.app_commands.Choice(name='Settlement', value='Settlement'),
                    discord.app_commands.Choice(name='Both', value='Both')])
    @app_commands.describe(event="This selects a specific event and has the highest priority.")
    async def spawn_event(self, interaction: discord.Interaction, kingdom: str, event: typing.Optional[str], region: typing.Optional[str], settlement: typing.Optional[str], hex_id: typing.Optional[int],
                          event_type: discord.app_commands.Choice[str] = 'general', localization: discord.app_commands.Choice[str] = 'both'):
        """Spawn an event for a kingdom"""
        await interaction.response.defer(thinking=True)
        try:
            event_value = event_type.value if isinstance(event_type, discord.app_commands.Choice) else event_type
            localization_value = localization.value  if isinstance(localization, discord.app_commands.Choice) else localization
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute("SELECT Kingdom from KB_Kingdoms where Kingdom = ?", (kingdom,))
                kingdom_info = await cursor.fetchone()
                if not kingdom_info:
                    await interaction.followup.send("The kingdom with that name does not exist.")
                    return
                if settlement:
                    await cursor.execute("select settlement from KB_Settlements where Settlement = ?", (settlement,))
                    settlement_info = await cursor.fetchone()
                    if not settlement_info:
                        await interaction.followup.send("The settlement with that name does not exist.")
                        return
                if hex_id:
                    await cursor.execute("select hex from KB_Hexes where Hex = ?", (hex_id, kingdom))
                    hex_info = await cursor.fetchone()
                    if not hex_info:
                        await interaction.followup.send(f"The hex id {hex_id} either does not exist.")
                if event:
                    await cursor.execute("SELECT Name, Scale, Hex from KB_Events where Name = ? or id = ?", (event,))
                    event_info = await cursor.fetchone()
                    if not event_info:
                        await interaction.followup.send(f"The event with the name of {event} does not exist.")
                        return
                    else:
                        response = await kingdom_event(
                            db=db,
                            kingdom=kingdom,
                            event=event,
                            region=region,
                            settlement=settlement,
                            specified_hex=hex_id
                        )
                        await interaction.followup.send(response)
                elif event_value.lower() == 'general' and localization_value.lower() == 'both':
                    response = await general_kingdom_event(db=db, kingdom=kingdom, region=region, settlement=settlement, specified_hex=hex_id)
                    description = f'Prompt Info was kingdom: {kingdom}'
                    description += f"\r\nSettlement: {settlement}" if settlement else ""
                    description += f"\r\nHex: {hex_id}" if hex_id else ""
                    description += f"\r\nRolling off of the general events table."
                    embed = discord.Embed(title=f"General Kingdom Event Generated",
                                          description=description,
                                          colour=discord.Colour.blurple())
                    embed = embed.add_field(name="Event Generated", value=response)
                    await interaction.followup.send(embed=embed)
                else:
                    response = await choose_kingdom_event(db=db, kingdom=kingdom, region=region, specified_hex=hex_id, event_type=event_value, localization_type=localization_value)
                    embed = discord.Embed(title=f"General Kingdom Event Generated",
                                          description=f'Prompt Info was kingdom: {kingdom}, Settlement: {settlement}, Hex: {hex_id} Rolling off the  Events Table affecting {localization_value} with event type options of {event_type}',
                                          colour=discord.Colour.blurple())
                    embed = embed.add_field(name="Event Generated", value=response)
                    await interaction.followup.send(embed=embed)


        except Exception as e:
            logging.exception(f"Error in spawn_event: {e}")
            await interaction.followup.send("An error occurred while spawning an event.")

    population_group = discord.app_commands.Group(
        name='population',
        description='Commands related to population management',
        parent=overseer_group
    )

    @population_group.command(name='adjust', description='adjust the population in a kingdom')
    @app_commands.autocomplete(kingdom=kingdom_commands.kingdom_autocomplete)
    @app_commands.choices(
        randomize=[discord.app_commands.Choice(name='set', value=0),
                   discord.app_commands.Choice(name='random', value=1)])
    async def adjust_population(self, interaction: discord.Interaction, kingdom: str, population: int,
                                randomize: discord.app_commands.Choice[int] = 1):
        """Adjust the population in a kingdom"""
        await interaction.response.defer(thinking=True)
        try:
            randomize_value = randomize.value if isinstance(randomize, discord.app_commands.Choice) else randomize
            if randomize_value == 2:
                adjust_population = random.randint(1, abs(population))
                population = -abs(adjust_population) if population < 0 else adjust_population
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute("SELECT Population from KB_Kingdoms where Kingdom = ?", (kingdom,))
                kingdom_info = await cursor.fetchone()
                if not kingdom_info:
                    await interaction.followup.send("The kingdom with that name does not exist.")
                    return
                await cursor.execute("UPDATE KB_Kingdoms SET Population = Population + ? WHERE Kingdom = ?",
                                     (population, kingdom))
                await db.commit()
                await interaction.followup.send(
                    f"The population of {kingdom} has been adjusted to {kingdom_info[0] + population}.")
        except (TypeError, ValueError) as e:
            logging.exception(f"Error in adjust_population: {e}")
            await interaction.followup.send("An error occurred while adjusting the population.")

    @population_group.command(name='bid', description='adjust the bid in a region')
    @app_commands.autocomplete(region=autocomplete.region_autocomplete)
    @app_commands.choices(
        randomize=[discord.app_commands.Choice(name='set', value=0),
                   discord.app_commands.Choice(name='random', value=1)])
    async def set_bid(self, interaction: discord.Interaction, region: str, population: int,
                      randomize: discord.app_commands.Choice[int] = 1):
        """Adjust the population in a kingdom"""
        await interaction.response.defer(thinking=True)
        try:
            randomize_value = randomize.value if isinstance(randomize, discord.app_commands.Choice) else randomize
            if randomize_value == 2:
                adjust_population = random.randint(1, abs(population))
                population = -abs(adjust_population) if population < 0 else adjust_population
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute("Select Region from Regions where region = ?", (region,))
                region_info = await cursor.fetchone()
                if not region_info:
                    await interaction.followup.send("The region with that name does not exist.")
                    return
                await cursor.execute("SELECT Population from KB_Bids where Region = ?", (region,))
                region_info = await cursor.fetchone()
                if not region_info:
                    await cursor.exeucte("INSERT INTO KB_Bids (Region, Population) VALUES (?, ?)", (region, population))
                else:
                    await cursor.execute("UPDATE KB_Bids SET Population = Population + ? WHERE Region = ?",
                                         (population, region))
                await db.commit()
                await interaction.followup.send(
                    f"The population bid pool of {region} has been adjusted to {population}.")
        except (TypeError, ValueError) as e:
            logging.exception(f"Error in adjust_population: {e}")
            await interaction.followup.send("An error occurred while adjusting the population.")

    @weather_group.command(
        name='location',
        description='Define the location for a settlement'
    )
    @app_commands.autocomplete(
        settlement=autocomplete.settlement_autocomplete
    )
    async def set_location(
            self,
            interaction: discord.Interaction,
            settlement: str,
            latitude: float,
            longitude: float
    ):

        await interaction.response.defer(thinking=True)

        try:

            if not (-90 <= latitude <= 90):
                await interaction.followup.send(
                    "Latitude must be between -90 and 90."
                )
                return

            if not (-180 <= longitude <= 180):
                await interaction.followup.send(
                    "Longitude must be between -180 and 180."
                )
                return

            async with aiosqlite.connect(
                    f"pathparser_{interaction.guild_id}.sqlite"
            ) as db:

                cursor = await db.cursor()

                await cursor.execute("""
                    SELECT Settlement
                    FROM KB_Settlements
                    WHERE Settlement = ?
                """, (settlement,))

                settlement_info = await cursor.fetchone()

                if not settlement_info:
                    await interaction.followup.send(
                        "That settlement does not exist."
                    )
                    return

                await cursor.execute("""
                    UPDATE KB_Settlements
                    SET latitude = ?, longitude = ?
                    WHERE Settlement = ?
                """, (
                    latitude,
                    longitude,
                    settlement
                ))

                await cursor.execute("""
                    DELETE FROM Weather_History
                    WHERE Settlement = ?
                """, (settlement,))

                result = await regenerate_weather(
                    db=db,
                    settlement=settlement,
                    latitude=latitude,
                    longitude=longitude
                )

                await interaction.followup.send(result)
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"Error in set_location: {e}")
            await interaction.followup.send(f"An error occurred while setting settlement geography for an area {e}.")


    @weather_group.command(
        name='wmo',
        description='Define a WMO code for a settlement'
    )
    @app_commands.autocomplete(
        settlement=autocomplete.settlement_autocomplete
    )
    async def set_wmo(
            self,
            interaction: discord.Interaction,
            settlement: str,
            code: int,
            result: str
    ):

        await interaction.response.defer(thinking=True)
        try:
            if not (0 <= code < 100):
                await interaction.followup.send("Not a valid WMO code.")
                return


            async with aiosqlite.connect(
                    f"pathparser_{interaction.guild_id}.sqlite"
            ) as db:

                cursor = await db.cursor()

                await cursor.execute("""
                    SELECT Settlement
                    FROM KB_Settlements
                    WHERE Settlement = ?
                """, (settlement,))

                settlement_info = await cursor.fetchone()

                if not settlement_info and settlement != 'All':
                    await interaction.followup.send(
                        "That settlement does not exist."
                    )
                    return

                await cursor.execute("""
                    INSERT OR Replace INTO Weather_WMO (
                        Settlement,
                        Code,
                        Result
                    ) VALUES (?, ?, ?)
                    """, (settlement, code, result))
                await db.commit()

                await interaction.followup.send(f"WMO Code {code} successfully updated. for {settlement}.\r\nNew result: {result}")

        except Exception as e:
            logging.exception(f"Error in set_location: {e}")

            await interaction.followup.send(
                "An error occurred while setting the location."
            )

    @weather_group.command(
        name='remove_wmo',
        description='remove a WMO code for a settlement'
    )
    @app_commands.autocomplete(
        settlement=autocomplete.settlement_autocomplete
    )
    async def remove_wmo(
            self,
            interaction: discord.Interaction,
            settlement: str,
            code: int,
            result: str
    ):

        await interaction.response.defer(thinking=True)
        try:
            if not (0 <= code < 100):
                await interaction.followup.send("Not a valid WMO code.")
                return

            async with aiosqlite.connect(
                    f"pathparser_{interaction.guild_id}.sqlite"
            ) as db:

                cursor = await db.cursor()

                await cursor.execute("""
                      SELECT Settlement
                      FROM KB_Settlements
                      WHERE Settlement = ?
                  """, (settlement,))

                settlement_info = await cursor.fetchone()

                if not settlement_info or settlement == 'All':
                    await interaction.followup.send(
                        f"The Settlement of {settlement} does not exist. Either that or you tried to delete an All code... Jackass."
                    )
                    return

                await cursor.execute("""
                      delete from Weather_WMO where settlement = ? and code = ? 
                      """, (settlement, code))
                await db.commit()

                await interaction.followup.send(
                    f"WMO Code {code} successfully deleted for {settlement}")

        except Exception as e:
            logging.exception(f"Error in delete wmo code: {e}")

            await interaction.followup.send(
                f"An error occurred while deleting the wmo code {e}."
            )

    @weather_group.command(
        name='override',
        description="override information for a settlement's date"
    )
    @app_commands.autocomplete(
        settlement=autocomplete.settlement_autocomplete
    )
    async def override_settlement(
            self,
            interaction: discord.Interaction,
            settlement: str,
            date: str,
            high: typing.Optional[float],
            low: typing.Optional[float],
            wind_speed: typing.Optional[int],
            precipitation: typing.Optional[int],
            cloud_cover: typing.Optional[int],
            wmo: typing.Optional[int],

    ):
        await interaction.response.defer(thinking=True)
        try:
            if not any((high, low, wind_speed, precipitation, cloud_cover, wmo)):
                await interaction.followup.send("You must update SOMETHING when you use this command.")
            if not (0 <= wmo < 100):
                await interaction.followup.send("Not a valid WMO code.")
                return

            async with aiosqlite.connect(
                    f"pathparser_{interaction.guild_id}.sqlite"
            ) as db:

                cursor = await db.cursor()

                await cursor.execute("""
                    SELECT Settlement, Date, Temp_high, temp_low, wind_speed, precipitation_probability, cloud_cover, wmo_code
                    FROM KB_Settlements
                    WHERE Settlement = ? and Date = ?
                """, (settlement,date))

                settlement_info = await cursor.fetchone()

                if not settlement_info:
                    await interaction.followup.send(
                        f"One of three potential fuckups happened \r\n 1 - settlement: {settlement} was invalid.\r\n2 - date {date} was not formatted in YYYY-MM-DD.\r\n3 - Your date occurred mroe than 7 days in the future."
                    )
                    return
                (settlement_name, date_old, stored_temp_high, stored_temp_low, stored_wind_speed, stored_precipitation, stored_cloud_cover, stored_wmo_code) = settlement_info
                temp_high = high if high is not None else stored_temp_high
                temp_low = low if low is not None else stored_temp_low
                wind_speed = wind_speed if wind_speed is not None else stored_wind_speed
                precipitation = precipitation if precipitation is not None else stored_precipitation
                cloud_cover = cloud_cover if cloud_cover is not None else stored_cloud_cover
                wmo_code = wmo if wmo else stored_wmo_code

                await cursor.execute("""
                    UPDATE Weather_History SET 
                        temp_high = ?,
                        temp_low = ?,
                        wind_speed = ? 
                        precipitation_probability = ?,
                        cloud_cover = ?,
                        wmo_code = ? 
                        where settlement = ? and Date  ? 
                        
                    """, (temp_high, temp_low, wind_speed, precipitation, cloud_cover, wmo_code, settlement_name, date_old))
                await db.commit()




                await interaction.followup.send(
                    f"Updated {settlement}'s upcoming weather for {date}\r\nHigh: {temp_high}, Low{temp_low}\r\nWind Speed{wind_speed} MPH, Precipitation Likelihood: {precipitation}, Cloud Cover: {cloud_cover}\r\n{wmo} code.")

        except Exception as e:
            logging.exception(f"Error in set_location: {e}")

            await interaction.followup.send(
                "An error occurred while setting the location."
            )


logging.basicConfig(
    level=logging.INFO,  # Set the minimum logging level
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='application.log',  # Log to a file
    filemode='a'  # Append to the file
)

