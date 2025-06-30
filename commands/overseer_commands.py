import math
import datetime
import logging
import math
import random
import typing

import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands
from unidecode import unidecode

import shared_functions
from commands import kingdom_commands


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
            if result is not None:
                function_status = f"you have already allowed the construction of **{building}**"
                return function_status
    except (TypeError, ValueError, aiosqlite.Error) as error:
        logging.exception(f"Error in add_blueprint: {error}")
        return "An error occurred while adding a blueprint."


async def general_kingdom_event(
        db: aiosqlite.Connection,
        kingdom: str, region: str) -> None:
    try:
        cursor = await db.cursor()
        await cursor.execute("Select Likelihood, Type, Subtype FROM KB_Events_General")
        event_list = await cursor.fetchall()
        event = random.choices(event_list, weights=[event[0] for event in event_list])
        if event[1] == "Kingdom" or event[1] == "Settlement":
            await randomize_event_trigger(db=db, kingdom=kingdom, region=region, scale=event[1], type=event[2])
        else:
            await kingdom_event(db=db, kingdom=kingdom, region=region, event=event[1])
    except (TypeError, ValueError, aiosqlite.Error) as error:
        logging.exception(f"Error in general_kingdom_event: {error}")


async def randomize_event_trigger(
        db: aiosqlite.Connection,
        kingdom: str, region: str,
        type: typing.Optional[str], scale: str) -> None:
    try:
        cursor = await db.cursor()
        if type:
            await cursor.execute(
                "Select Likelihood, Name FROM KB_Events WHERE Type = ? AND Scale = ? AND (Region = ? OR Region = 'All')",
                (type, scale, region))
        else:
            await cursor.execute(
                "Select Likelihood, Name FROM KB_Events WHERE Scale = ? AND (Region = ? OR Region = 'All')",
                (scale, region))
        event_list = await cursor.fetchall()
        event = random.choices(event_list, weights=[event[0] for event in event_list])
        if scale == "Settlement":
            await cursor.execute("Select Kingdom, Settlement FROM KB_Settlements WHERE Kingdom = ? order by Random() limit 1", (kingdom,))
            settlement = await cursor.fetchone()
            if not settlement:
                return
        else:
            settlement = None
        await kingdom_event(db=db, kingdom=kingdom, region=region, event=event[1], settlement=settlement)
    except (TypeError, ValueError, aiosqlite.Error) as error:
        logging.exception(f"Error in beneficial_kingdom_event: {error}")


async def kingdom_event(
        db: aiosqlite.Connection,
        kingdom: str,
        region: typing.Optional[str],
        event: str,
        settlement: typing.Optional[str],
        specified_hex: typing.Optional[str] = None) -> None:
    try:
        cursor = await db.cursor()
        await cursor.execute("SELECT Name, Type, Value, Reroll FROM KB_Events_Consequence WHERE Event = ? AND Severity = -1", (event,))
        respawn_list = await cursor.fetchall()
        spawns = 0
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
            await cursor.execute(
                "SELECT Type, Name, Effect, Special, Check_A, Check_B, Success_Requirement, Duration, Bonus, Penalty, Hex")
            event_info = await cursor.fetchone()
            if not event_info:
                raise ValueError("No event found.")
            event_type, event_name, effect, special, check_a, check_b, success_requirement, duration, bonus, penalty, hex_affect = event_info
            if specified_hex:
                hex_result = specified_hex
                specified_hex = None
            elif hex_affect == 1:
                await cursor.execute("""
                SELECT KH.ID
                FROM KB_Hexes KH LEFT OUTER Join KB_events_active KEA ON KEA.Hex = KH.ID
                WHERE KH.Kingdom = ? AND KEA.Name = ? AND KH.IsTown = 0
                order by Random() LIMIT 1""", (kingdom, event_name))
                hex_id = await cursor.fetchone()
                if hex_id:
                    hex_result = hex_id[0]
                else:
                    return
            elif hex_affect == 2:
                await cursor.execute("""
                SELECT KH.ID
                FROM KB_Hexes KH LEFT OUTER Join KB_events_active KEA ON KEA.Hex = KH.ID
                WHERE KH.Kingdom != ? AND KEA.Name = ? AND KH.IsTown = 0
                order by Random() LIMIT 1""", (kingdom, region, event_name))
                hex_id = await cursor.fetchone()
                if hex_id:
                    hex_result = hex_id[0]
                else:
                    return
            else:
                hex_result = None
            await cursor.execute("""INSERT into KB_Events_Active Kingdom, Settlement, Hex, Name, Effect, Duration, Check_A, Check_A_Status, Check_B, Check_B_Status, Active 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (
            kingdom, settlement, hex_result, event_name, effect, duration, check_a, False, check_b, False, True))
            await cursor.execute(
                """INSERT into A_Audit_All (Author, Timestamp, Database_Changed, Modification, Reason) VALUES (?, ?, ?, ?, ?)""",
                (0, datetime.datetime.now(), "KB_Events_Active", "Create", f"Created the event of {event_name}"))
            for y in range(spawn_improvement):
                await improvement_event(db=db, hex_id=hex_result, type='Spawn')
            for z in range(despawn_improvement):
                await improvement_event(db=db, hex_id=hex_result, type='Despawn')
            for a in range(spawn_building):
                await building_event(db=db, settlement=settlement, type='Spawn')
            for b in range(despawn_building):
                await building_event(db=db, settlement=settlement, type='Despawn')
        await db.commit()
    except (TypeError, ValueError, aiosqlite.Error) as error:
        logging.exception(f"Error in kingdom_event: {error}")

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
    while number_respawns == value:  # This will allow for the event to respawn multiple times.
        number_respawns = random.randint(1, abs(value))
        respawns += number_respawns
    respawns = respawns if value > 0 else -respawns
    return respawns

async def improvement_event(
        db: aiosqlite.Connection,
        hex_id: int,
        type: str) -> None:
    try:
        cursor = await db.cursor()
        if type == 'Spawn':
            await cursor.execute("SELECT Kingdom, Hex_Terrain, Farm, Ore, Stone, Wood, Water, IsTown from KB_Hexes where ID = ?", (hex_id,))
            hex_info = await cursor.fetchone()
            if not hex_info:
                raise ValueError("No hex found.")
            (kingdom, terrain, farm, ore, stone, wood, water, is_town) = hex_info
            if is_town:
                raise ValueError("Cannot spawn improvements in towns.")
            await cursor.execute("""
                SELECT 
                    SUM(CASE WHEN  name = 'Farm' THEN amount * quality ELSE 0 END) AS farm_total,
                    SUM(CASE WHEN subtype = 'Ore' THEN amount * quality ELSE 0 END) AS ore_total,
                    SUM(CASE WHEN subtype = 'Stone' THEN amount * quality ELSE 0 END) AS stone_total,
                    SUM(CASE WHEN subtype = 'Wood' THEN amount * quality ELSE 0 END) AS wood_total,
                    SUM(CASE WHEN subtype = 'Seafood' THEN amount * quality ELSE 0 END) AS seafood_total
                FROM KB_Hexes_Constructed 
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
                return
            (full_name, name, subtype, quality, economy, loyalty, stability, unrest, consumption, defence, taxation) = improvement
            await cursor.execute("select amount from KB_Hexes_Construction where ID = ? and Full_Name = ?", (hex_id, full_name))
            existing = await cursor.fetchone()
            if not existing:
                await cursor.execute(
                    "INSERT INTO KB_Hexes_Constructed (ID, Name, Subtype, Quality, Economy, Loyalty, Stability, Unrest, Consumption, Defence, Taxation) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (hex_id, full_name, name, subtype, quality, economy, loyalty, stability, unrest, consumption, defence,
                     taxation))
            else:
                await cursor.execute(
                    "UPDATE KB_Hexes_Constructed SET Amount = Amount + 1 WHERE ID = ? AND Full_Name = ?",
                    (hex_id, full_name))
            await cursor.execute(
                "INSERT INTO A_Audit_All (Author, Timestamp, Database_Changed, Modification, Reason) VALUES (?, ?, ?, ?, ?)",
                (0, datetime.datetime.now(), "KB_Hexes_Constructed", "Create",
                 f"Created the improvement of {full_name}"))
            if kingdom:
                await cursor.execute("UPDATE KB_Kingdoms SET Economy = Economy + ?, Loyalty = Loyalty + ?, Stability = Stability + ?, Unrest = Unrest + ?, Consumption = Consumption + ?, Defence = Defence + ?, Taxation = Taxation + ? WHERE Kingdom = ?", (economy, loyalty, stability, unrest, consumption, defence, taxation, kingdom))
            await db.commit()
        if type == 'Despawn':
            await cursor.execute("SELECT kingdom, Full_Name, Economy, Loyalty, Stability, Unrest, Consumption, Defence, Taxation FROM KB_Hexes_Constructed WHERE ID = ? ORDER BY Random() LIMIT 1", (hex_id,))
            improvement = await cursor.fetchone()
            if not improvement:
                return
            (kingdom, full_name, economy, loyalty, stability, unrest, consumption, defence, taxation) = improvement
            await cursor.execute("SELECT Amount FROM KB_Hexes_Constructed WHERE ID = ? AND Full_Name = ?", (hex_id, full_name))
            amount = await cursor.fetchone()
            if amount[0] == 1:
                await cursor.execute("DELETE FROM KB_Hexes_Constructed WHERE ID = ? AND Full_Name = ?", (hex_id, full_name))
            else:
                await cursor.execute("UPDATE KB_Hexes_Constructed SET Amount = Amount - 1 WHERE ID = ? AND Full_Name = ?", (hex_id, full_name))
            await cursor.execute(
                "INSERT INTO A_Audit_All (Author, Timestamp, Database_Changed, Modification, Reason) VALUES (?, ?, ?, ?, ?)",
                (0, datetime.datetime.now(), "KB_Hexes_Constructed", "Delete",
                 f"Deleted the improvement of {full_name}"))
            if kingdom:
                await cursor.execute("UPDATE KB_Kingdoms SET Economy = Economy - ?, Loyalty = Loyalty - ?, Stability = Stability - ?, Unrest = Unrest - ?, Consumption = Consumption - ?, Defence = Defence - ?, Taxation = Taxation - ? WHERE Kingdom = ?", (economy, loyalty, stability, unrest, consumption, defence, taxation, kingdom))
            await db.commit()
    except (TypeError, ValueError, aiosqlite.Error) as error:
        logging.exception(f"Error in improvement_event: {error}")

async def building_event(
        db:aiosqlite.Connection,
        settlement: str,
        kingdom: str,
        type: str) -> None:
    try:
        cursor = await db.cursor()
        if type == 'Spawn':
            await cursor.execute("SELECT Full_Name, Type, Subtype, Quality, Lots, Economy, Loyalty, Stability, Fame, Unrest, Corruption, Crime, Productivity, Law, Lore, Society, Danger, Defence, Base_Value, Spellcasting, Supply from KB_Buildings_Blueprints order by Random() LIMIT 1")
            building_info = await cursor.fetchone()
            if not building_info:
                return
            (full_name, type, subtype, quality, lots, economy, loyalty, stability, fame, unrest, corruption, crime, productivity, law, lore, society, danger, defence, base_value, spellcasting, supply) = building_info
            await cursor.execute("SELECT Building, Constructed FROM KB_Buildings WHERE Kingdom = ? AND Settlement = ?", (kingdom, settlement))
            settlement_info = await cursor.fetchone()
            if not settlement_info:
                await cursor.execute("""
                INSERT INTO KB_Buildings (Kingdom, Settlement, Building, Constructed, Lots, 
                Economy, Loyalty, Stability, Fame, Unrest, 
                Corruption, Crime, Productivity, Law, Lore, Society, 
                Danger, Defence, Base_Value, Spellcasting, 
                Supply) VALUES(
                ?, ?, ?, ?, ?, ?, 
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, 
                ?""",( kingdom, settlement, full_name, 1, lots, economy, loyalty, stability, fame, unrest, corruption, crime, productivity, law, lore, society, danger, defence, base_value, spellcasting, supply))
            else:
                (building, constructed) = settlement_info
                await cursor.execute("UPDATE KB_Buildings SET Constructed = Constructed + 1 WHERE Kingdom = ? AND Settlement = ? AND Building = ?", (kingdom, settlement, building))
            await cursor.execute("INSERT INTO A_Audit_All (Author, Timestamp, Database_Changed, Modification, Reason) VALUES (?, ?, ?, ?, ?)", (0, datetime.datetime.now(), "KB_Buildings", "Create", f"Created the building of {full_name}"))
            await cursor.execute("UPDATE KB_Settlements SET Corruption = Corruption + ?, Crime = Crime + ?, Productivity = Productivity + ?, Law = Law + ?, Lore = Lore + ?, Society = Society + ?, Danger = Danger + ?, Defence = Defence + ?, Base_Value = Base_Value + ?, Spellcasting = Spellcasting + ?, Supply = Supply + ? WHERE Kingdom = ? AND Settlement = ?", (economy, loyalty, stability, fame, unrest, corruption, crime, productivity, law, lore, society, danger, defence, base_value, spellcasting, supply, kingdom, settlement))
            await cursor.execute("UPDATE KB_Kingdoms SET Economy = Economy + ?, Loyalty = Loyalty + ?, Stability = Stability + ?, Fame = Fame + ?, Unrest = Unrest + ?, WHERE Kingdom = ?", (economy, loyalty, stability, fame, unrest, kingdom))
            await db.commit()
        if type == 'Despawn':
            await cursor.execute("SELECT Building, Constructed, Lots, Economy, Loyalty, Stability, Fame, Unrest, Corruption, Crime, Productivity, Law, Lore, Society, Danger, Defence, Base_Value, Spellcasting, Supply FROM KB_Buildings WHERE Kingdom = ? AND Settlement = ? ORDER BY Random() LIMIT 1", (kingdom, settlement))
            building_info = await cursor.fetchone()
            if not building_info:
                return
            (building, constructed, lots, economy, loyalty, stability, fame, unrest, corruption, crime, productivity, law, lore, society, danger, defence, base_value, spellcasting, supply) = building_info
            if constructed == 1:
                await cursor.execute("DELETE FROM KB_Buildings WHERE Kingdom = ? AND Settlement = ? AND Building = ?", (kingdom, settlement, building))
            else:
                await cursor.execute("UPDATE KB_Buildings SET Constructed = Constructed - 1 WHERE Kingdom = ? AND Settlement = ? AND Building = ?", (kingdom, settlement, building))
            await cursor.execute("INSERT INTO A_Audit_All (Author, Timestamp, Database_Changed, Modification, Reason) VALUES (?, ?, ?, ?, ?)", (0, datetime.datetime.now(), "KB_Buildings", "Delete", f"Deleted the building of {building}"))
            await cursor.execute("UPDATE KB_Settlements SET Corruption = Corruption - ?, Crime = Crime - ?, Productivity = Productivity - ?, Law = Law - ?, Lore = Lore - ?, Society = Society - ?, Danger = Danger - ?, Defence = Defence - ?, Base_Value = Base_Value - ?, Spellcasting = Spellcasting - ?, Supply = Supply - ? WHERE Kingdom = ? AND Settlement = ?", (economy, loyalty, stability, fame, unrest, corruption, crime, productivity, law, lore, society, danger, defence, base_value, spellcasting, supply, kingdom, settlement))
            await cursor.execute("UPDATE KB_Kingdoms SET Economy = Economy - ?, Loyalty = Loyalty - ?, Stability = Stability - ?, Fame = Fame - ?, Unrest = Unrest - ?, WHERE Kingdom = ?", (economy, loyalty, stability, fame, unrest, kingdom))
            await db.commit()
    except (TypeError, ValueError, aiosqlite.Error) as error:
        logging.exception(f"Error in building_event: {error}")

async def handle_severity(
        db: aiosqlite.Connection,
        severity: int,
        kingdom: str,
        region: str,
        settlement: str,
        hex_id: int,
        event: str,
        success_requirement: typing.Optional[int] = None,
        duration: typing.Optional[int] = None,
        event_id: typing.Optional[int] = None
) -> None:
    try:
        cursor = db.cursor
        await cursor.execute("SELECT Name, Type, Value, Reroll FROM KB_Events_Consequence WHERE Event = ? AND Severity = ?", (event, severity))
        consequence_list = await cursor.fetchall()
        if not consequence_list:
            return
        kingdom_status_dict = {"Build Points": "Build Points",
                               "Fame": "Fame",
                               "Unrest": "Unrest",
                               "Population": "Population",}
        for consequence in consequence_list:
            (name, type, value, reroll) = consequence
            if type == 'Respawn':
                spawns = 0
                if reroll == 4:
                    spawns += exploding_roll(value)
                elif reroll == 5:
                    spawns += exploding_instance(value)
                elif reroll == 1:
                    spawns += random.randint(1, value)
                elif reroll == 0:
                    spawns += value
                for x in range(spawns):
                    await kingdom_event(db=db, kingdom=kingdom, region=region, event=name, settlement=settlement)
            elif type == 'Build Random Improvement':
                for x in range(value):
                    await improvement_event(db=db, hex_id=hex_id, type='Spawn')
            elif type == 'Destroy Random Improvement':
                for x in range(value):
                    await improvement_event(db=db, hex_id=hex_id, type='Despawn')
            elif type == 'Build Random Building':
                for x in range(value):
                    await building_event(db=db, settlement=settlement, kingdom=kingdom, type='Spawn')
            elif type == 'Destroy Random Building':
                for x in range(value):
                    await building_event(db=db, settlement=settlement, kingdom=kingdom, type='Despawn')
            elif type in kingdom_status_dict:
                await cursor.execute(f"UPDATE KB_Kingdoms SET {kingdom_status_dict[type]} = {kingdom_status_dict[type]} + ? WHERE Kingdom = ?", (value, kingdom))
        if all([success_requirement, event_id]) and severity == success_requirement:
            duration -= 1 if duration > 0 else duration
            duration += 1 if duration < 0 else duration
            if duration == 0:
                await cursor.execute("DELETE FROM KB_Events_Active WHERE ID = ?", (event_id,))
    except (TypeError, ValueError, aiosqlite.Error) as error:
        logging.exception(f"Error in handle_severity: {error}")

async def event_name_autocomplete(interaction: discord.Interaction, current: str) -> typing.List[
    app_commands.Choice[str]]:
    data = []
    guild_id = interaction.guild_id
    async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
        cursor = await db.cursor()
        current = unidecode(str.title(current))
        await cursor.execute(
            "SELECT Name from KB_Events from KB_Events where Name like ? Limit 20",
            (f"%{current}%",))
        event_list = await cursor.fetchall()
        for event in event_list:
            if current in event[0]:
                data.append(app_commands.Choice(name=event[0], value=event[0]))

    return data


async def type_value_autocomplete(interaction: discord.Interaction, current: str) -> typing.List[
    app_commands.Choice[str]]:
    data = []
    guild_id = interaction.guild_id
    async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
        cursor = await db.cursor()
        current = unidecode(str.title(current))
        await cursor.execute(
            "SELECT DISTINCT(Type) from KB_Events_Consequence WHERE Type LIKE ? Limit 20",
            (f"%{current}%",))
        type_list = await cursor.fetchall()
        for type in type_list:
            if current in type[0]:
                data.append(app_commands.Choice(name=type[0], value=type[0]))

    return data


async def modifier_autocomplete(interaction: discord.Interaction, current: str) -> typing.List[
    app_commands.Choice[str]]:
    data = []
    guild_id = interaction.guild_id
    async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
        cursor = await db.cursor()
        current = unidecode(str.title(current))
        await cursor.execute(
            "SELECT DISTINCT(CASE WHEN Bonus is Null then Penalty else Bonus END) from kb_events WHERE penalty LIKE ? or bonus like ? Limit 20",
            (f"%{current}%", f"%{current}%"))
        modifier_list = await cursor.fetchall()
        for modifier in modifier_list:
            if current in modifier[0]:
                data.append(app_commands.Choice(name=modifier[0], value=modifier[0]))

    return data


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
            if result is not None:
                status = f"You have done the YEETETH of this particular building which is {building}."
                await cursor.execute("""Delete FROM Buildings_Blueprints WHERE Building = '{building}'""")
                await cursor.execute(
                    "Select Kingdom, Settlement, Building, Constructed, Lots, Economy, Loyalty, Stability, Fame, Unrest, Corruption, Crime, Productivity, Law, Lore, Society, Danger, Defence, Base_Value, Spellcasting, Supply, Settlement_Limit, District_Limit, Description FROM KB_Settlements WHERE Building = ?",
                    (building,))
                built_buildings = await cursor.fetchall()
                for built_building in built_buildings:
                    (kingdom, settlement, building, constructed, lots, economy, loyalty, stability, fame, unrest,
                     corruption, crime, productivity, law, lore, society, danger, defence, base_value, spellcasting,
                     supply, settlement_limit, district_limit, description) = built_building
                    await cursor.execute("SELECT Size from KB_Settlements WHERE Kingdom = ? AND Settlement = ?",
                                         (kingdom, settlement))
                    size = await cursor.fetchone()
                    adjusted_dc = math.floor(size[0] / 36) - math.floor((size[0] - (lots * constructed) / 36))
                    await cursor.execute(
                        "Update KB_Settlements SET Size = size - ?, population = population - ?, corruption = corruption - ?, crime = crime - ?, productivity = productivity - ?, law = law - ?, lore = lore - ?, society = society - ?, danger = danger - ?, defence = defence - ?, base_value = base_value - ?, spellcasting = spellcasting - ?, supply = supply - ? WHERE Kingdom = ? AND Settlement = ?",
                        (lots * constructed, lots * 250 * constructed, economy * constructed, loyalty * constructed,
                         stability * constructed, fame * constructed, unrest * constructed, corruption * constructed,
                         crime * constructed, productivity * constructed, law * constructed, lore * constructed,
                         society * constructed, danger * constructed, defence * constructed, base_value * constructed,
                         spellcasting * constructed, supply * constructed, kingdom, settlement))
                    await cursor.execute(
                        "Update KB_Kingdoms set population = population - ?, Control_DC = Control_DC - ?, Economy = Economy - ?, Loyalty = Loyalty - ?, Stability = Stability - ?, Fame = Fame - ?, Unrest = Unrest - ?, Consumption = Consumption - ? WHERE Kingdom = ?",
                        (lots * 250 * constructed, adjusted_dc, economy * constructed, loyalty * constructed,
                         stability * constructed, fame * constructed, unrest * constructed, corruption * constructed,
                         kingdom))
                await cursor.execute("Delete FROM KB_Settlements WHERE Building = ?", (building,))
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
        old_blueprint_info: kingdom_commands.BuildingInfo,
        building: typing.Optional[str] = None,
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
        description: typing.Optional[str] = None) -> str:
    try:
        building = building if building else old_blueprint_info.building
        build_points = build_points if build_points else old_blueprint_info.build_points
        lots = lots if lots else old_blueprint_info.lots
        economy = economy if economy else old_blueprint_info.economy
        loyalty = loyalty if loyalty else old_blueprint_info.loyalty
        stability = stability if stability else old_blueprint_info.stability
        fame = fame if fame else old_blueprint_info.fame
        unrest = unrest if unrest else old_blueprint_info.unrest
        corruption = corruption if corruption else old_blueprint_info.corruption
        crime = crime if crime else old_blueprint_info.crime
        productivity = productivity if productivity else old_blueprint_info.productivity
        law = law if law else old_blueprint_info.law
        lore = lore if lore else old_blueprint_info.lore
        society = society if society else old_blueprint_info.society
        danger = danger if danger else old_blueprint_info.danger
        defence = defence if defence else old_blueprint_info.defence
        base_value = base_value if base_value else old_blueprint_info.base_value
        spell_casting = spell_casting if spell_casting else old_blueprint_info.spellcasting
        supply = supply if supply else old_blueprint_info.supply
        settlement_limit = settlement_limit if settlement_limit else old_blueprint_info.settlement_limit
        district_limit = district_limit if district_limit else old_blueprint_info.district_limit
        description = description if description else old_blueprint_info.description
        net_lots = lots - old_blueprint_info.lots
        net_economy = economy - old_blueprint_info.economy
        net_loyalty = loyalty - old_blueprint_info.loyalty
        net_stability = stability - old_blueprint_info.stability
        net_fame = fame - old_blueprint_info.fame
        net_unrest = unrest - old_blueprint_info.unrest
        net_corruption = corruption - old_blueprint_info.corruption
        net_crime = crime - old_blueprint_info.crime
        net_productivity = productivity - old_blueprint_info.productivity
        net_law = law - old_blueprint_info.law
        net_lore = lore - old_blueprint_info.lore
        net_society = society - old_blueprint_info.society
        net_danger = danger - old_blueprint_info.danger
        net_defence = defence - old_blueprint_info.defence
        net_base_value = base_value - old_blueprint_info.base_value
        net_spell_casting = spell_casting - old_blueprint_info.spellcasting
        net_supply = supply - old_blueprint_info.supply
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()

            await cursor.execute(
                "Select Kingdom, Settlement, Building, Constructed, Lots, Economy, Loyalty, Stability, Fame, Unrest, Corruption, Crime, Productivity, Law, Lore, Society, Danger, Defence, Base_Value, Spellcasting, Supply, Settlement_Limit, District_Limit, Description FROM KB_Settlements WHERE Building = ?",
                (building,))
            built_buildings = await cursor.fetchall()
            for built_building in built_buildings:
                (kingdom, settlement, building, constructed, lots, economy, loyalty, stability, fame, unrest,
                 corruption, crime, productivity, law, lore, society, danger, defence, base_value, spellcasting,
                 supply, settlement_limit, district_limit, description) = built_building
                await cursor.execute("SELECT Size from KB_Settlements WHERE Kingdom = ? AND Settlement = ?",
                                     (kingdom, settlement))
                size = await cursor.fetchone()
                adjusted_dc = math.floor(size[0] / 36) - math.floor((size[0] + (net_lots * constructed) / 36))
                await cursor.execute(
                    "Update KB_Settlements SET Size = size + ?, population = population + ?, corruption = corruption + ?, crime = crime + ?, productivity = productivity + ?, law = law + ?, lore = lore + ?, society = society + ?, danger = danger + ?, defence = defence + ?, base_value = base_value + ?, spellcasting = spellcasting + ?, supply = supply + ? WHERE Kingdom = ? AND Settlement = ?",
                    (net_lots * constructed, net_lots * 250 * constructed, net_economy * constructed,
                     net_loyalty * constructed,
                     net_stability * constructed, net_fame * constructed, net_unrest * constructed,
                     net_corruption * constructed,
                     net_crime * constructed, net_productivity * constructed, net_law * constructed,
                     net_lore * constructed,
                     net_society * constructed, net_danger * constructed, net_defence * constructed,
                     net_base_value * constructed,
                     net_spell_casting * constructed, net_supply * constructed, kingdom, settlement))
                await cursor.execute(
                    "Update KB_Kingdoms set population = population + ?, Control_DC = Control_DC + ?, Economy = Economy + ?, Loyalty = Loyalty + ?, Stability = Stability + ?, Fame = Fame + ?, Unrest = Unrest + ?, Consumption = Consumption + ? WHERE Kingdom = ?",
                    (net_lots * 250 * constructed, adjusted_dc, net_economy * constructed, net_loyalty * constructed,
                     net_stability * constructed, net_fame * constructed, net_unrest * constructed,
                     net_corruption * constructed,
                     kingdom))
            await cursor.execute(
                "UPDATE Buildings_Blueprints SET building = ?, build_points = ?, lots = ?, economy = ?, loyalty = ?, stability = ?, fame = ?, unrest = ?, corruption = ?, crime = ?, productivity = ?, law = ?, lore = ?, society = ?, danger = ?, defence = ?, base_value = ?, spell_casting = ?, supply = ?, settlement_limit = ?, district_limit = ?, description = ? WHERE building = ?",
                (building, build_points, lots, economy, loyalty, stability, fame, unrest, corruption, crime,
                 productivity, law, lore, society, danger, defence, base_value, spell_casting, supply, settlement_limit,
                 district_limit, description, old_blueprint_info.building))
            await cursor.execute(
                "UPDATE Buildings set building = ?, lots = ?, economy = ?, loyalty = ?, stability = ?, fame = ?, unrest = ?, corruption = ?, crime = ?, productivity = ?, law = ?, lore = ?, society = ?, danger = ?, defence = ?, base_value = ?, spell_casting = ?, supply = ?, settlement_limit = ?, district_limit = ?, description = ? WHERE building = ?",
                (building, lots, economy, loyalty, stability, fame, unrest, corruption, crime, productivity, law, lore,
                 society, danger, defence, base_value, spell_casting, supply, settlement_limit, district_limit,
                 description, old_blueprint_info.building))
            await cursor.execute(
                "Insert into A_Audit_All (Author, Timestamp, Database_Changed, Modification, Reason) VALUES (?, ?, ?, ?, ?)",
                (author, datetime.datetime.now(), "Blueprints", "Update", f"Updated the blueprints of {building}"))
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
            if result is not None:
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
                    "UPDATE KB_Kingdoms SET Control_DC = Control_DC + ?, Economy = Economy + ?, Loyalty = Loyalty + ?, Stability = Stability + ?, Fame = Fame + ?, Unrest = Unrest + ?, Consumption = Consumption + ? WHERE Kingdom = ?",
                    (control_dc - old_control_dc, economy - old_economy, loyalty - old_loyalty,
                     stability - old_stability, fame - old_fame, unrest - old_unrest, consumption - old_consumption,
                     kingdom))

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
            if result is not None:
                await cursor.execute(
                    "SELECT Corruption, Crime, Productivity, Law, Lore, Society, Danger, Defence, Base_Value, Spellcasting, Supply FROM KB_Settlements_Custom WHERE Kingdom = ? AND Settlement = ?",
                    (kingdom, settlement))
                result = await cursor.fetchone()
                (old_corruption, old_crime, old_productivity, old_law, old_lore, old_society, old_danger, old_defence,
                 old_base_value, old_spellcasting, old_supply) = result
                corruption = corruption if corruption else old_corruption
                crime = crime if crime else old_crime
                productivity = productivity if productivity else old_productivity
                law = law if law else old_law
                lore = lore if lore else old_lore
                society = society if society else old_society
                danger = danger if danger else old_danger
                defence = defence if defence else old_defence
                base_value = base_value if base_value else old_base_value
                spellcasting = spellcasting if spellcasting else old_spellcasting
                supply = supply if supply else old_supply

                await cursor.execute(
                    "UPDATE KB_Settlements_Custom SET Corruption = ?, Crime = ?, Productivity = ?, Law = ?, Lore = ?, Society = ?, Danger = ?, Defence = ?, Base_Value = ?, Spellcasting = ?, Supply = ? WHERE Kingdom = ? AND Settlement = ?",
                    (corruption, crime, productivity, law, lore, society, danger, defence, base_value, spellcasting,
                     supply, kingdom, settlement))
                await cursor.execute(
                    "UPDATE KB_Settlements SET Corruption = Corruption + ?, Crime = Crime + ?, Productivity = Productivity + ?, Law = Law + ?, Lore = Lore + ?, Society = Society + ?, Danger = Danger + ?, Defence = Defence + ?, Base_Value = Base_Value + ?, Spellcasting = Spellcasting + ?, Supply = Supply + ? WHERE Kingdom = ? AND Settlement = ?",
                    (corruption - old_corruption, crime - old_crime, productivity - old_productivity, law - old_law,
                     lore - old_lore, society - old_society, danger - old_danger, defence - old_defence,
                     base_value - old_base_value, spellcasting - old_spellcasting, supply - old_supply, kingdom,
                     settlement))
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


"""
async def settlement_decay_set(
        guild_id: int,
        author: int,
        kingdom: str,
        settlement: str,
        decay: int) -> str:
    try:
        async with shared_functions.config_cache.lock:
            configs = shared_functions.config_cache.cache.get(guild_id)
            if configs:
                decay_bool = configs.get('Decay')
        if decay_bool == 'False':
            return "Decay is disabled on this server."
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute("Select Kingdom FROM KB_Settlements where Kingdom = ? AND Settlement = ?",
                                 (kingdom, settlement))
            result = await cursor.fetchone()
            if result is None:
                status = f"You have failed to specify a valid settlement to adjust the decay!!"
                await db.commit()
                return status
            if result is not None:
                await cursor.execute("UPDATE KB_Settlements SET Decay = ? WHERE Kingdom = ? AND Settlement = ?",
                                     (decay, kingdom, settlement))
                await cursor.execute(
                    "Insert into A_Audit_All (Author, Timestamp, Database_Changed, Modification, Reason) VALUES (?, ?, ?, ?, ?)",
                    (author, datetime.datetime.now(), "KB_Settlements", "Update", f"Updated the decay of {settlement}"))
                await db.commit()
                status = f"The settlement of {settlement} within the kingdom of {kingdom} has had it's decay set to {decay}!"
                return status
    except (TypeError, ValueError, aiosqlite.Error) as error:
        logging.exception(f"Error in settlement_decay_set: {error}")
        return "An error occurred while setting settlement decay."
"""


async def add_hex_improvements(
        guild_id: int,
        author: int,
        improvement: str,
        road_multiplier: int,
        build_points: int,
        economy: int,
        loyalty: int,
        stability: int,
        unrest: int,
        consumption: int,
        defence: int,
        taxation: int,
        cavernous: int,
        coastline: int,
        desert: int,
        forest: int,
        hills: int,
        jungle: int,
        marsh: int,
        mountain: int,
        plains: int,
        water: int) -> str:
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute("""select Improvement from KB_Hexes_Improvements where Improvement = ?""",
                                 (improvement,))
            result = await cursor.fetchone()
            if result is None:
                await cursor.execute(
                    """INSERT INTO KB_Hexes_Improvements (
                    Improvement, Road_Multiplier, Build_Points, Economy, Loyalty, Stability, Unrest, Consumption, Defence, Taxation, Cavernous, Coastline, Desert, Forest, Hills, Jungle, Marsh, Mountain, Plains, Water) 
                    VALUES 
                    (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);""",
                    (improvement, road_multiplier, build_points, economy, loyalty, stability, unrest, consumption,
                     defence, taxation, cavernous, coastline, desert, forest, hills, jungle, marsh, mountain, plains,
                     water))
                await cursor.execute(
                    """Insert into A_Audit_All (Author, Timestamp, Database_Changed, Modification, Reason) VALUES (?, ?, ?, ?, ?)""",
                    (author, datetime.datetime.now(), "KB_Hexes_Improvements", "Create",
                     f"Created the hex improvement of {improvement}"))
                await db.commit()
                status = f"You have allowed the creation the new hex improvement: {improvement}!"
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
            await cursor.execute("""select Improvement FROM KB_Hexes_Improvements WHERE Improvement = ?""",
                                 (improvement,))
            result = await cursor.fetchone()
            if result is None:
                status = f"The improvement of {improvement} did not previously exist."
                await db.commit()
                return status
            else:
                await cursor.execute("""Delete FROM KB_Hexes_Improvements WHERE Improvement = ?""", (improvement,))
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
        old_hex_info: kingdom_commands.HexImprovementInfo,
        improvement: typing.Optional[str] = None,
        road_multiplier: typing.Optional[int] = None,
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
        mountain: typing.Optional[int] = None,
        plains: typing.Optional[int] = None,
        water: typing.Optional[int] = None) -> str:
    try:
        improvement = improvement if improvement else old_hex_info.improvement
        road_multiplier = road_multiplier if road_multiplier else old_hex_info.road_multiplier
        build_points = build_points if build_points else old_hex_info.build_points
        economy = economy if economy else old_hex_info.economy
        loyalty = loyalty if loyalty else old_hex_info.loyalty
        stability = stability if stability else old_hex_info.stability
        unrest = unrest if unrest else old_hex_info.unrest
        consumption = consumption if consumption else old_hex_info.consumption
        defence = defence if defence else old_hex_info.defence
        taxation = taxation if taxation else old_hex_info.taxation
        cavernous = cavernous if cavernous else old_hex_info.cavernous
        coastline = coastline if coastline else old_hex_info.coastline
        desert = desert if desert else old_hex_info.desert
        forest = forest if forest else old_hex_info.forest
        hills = hills if hills else old_hex_info.hills
        jungle = jungle if jungle else old_hex_info.jungle
        marsh = marsh if marsh else old_hex_info.marsh
        mountain = mountain if mountain else old_hex_info.mountains
        plains = plains if plains else old_hex_info.plains
        water = water if water else old_hex_info.water
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()
            difference_economy = economy - old_hex_info.economy
            difference_loyalty = loyalty - old_hex_info.loyalty
            difference_stability = stability - old_hex_info.stability
            difference_unrest = unrest - old_hex_info.unrest
            difference_consumption = consumption - old_hex_info.consumption
            difference_defence = defence - old_hex_info.defence
            difference_taxation = taxation - old_hex_info.taxation
            await cursor.execute("SELECT Kingdom, Amount from KB_Hexes WHERE Improvement = ?", (improvement,))
            improvements = await cursor.fetchall()
            for improvement in improvements:
                (kingdom, amount) = improvement
                await cursor.execute(
                    "UPDATE KB_Hexes SET Economy = ?, Loyalty = ?, Stability = ?, Unrest = ?, Consumption = ?, Defence = ?, Taxation = ?, Cavernous = ?, Coastline = ?, Desert =  ?, Forest = ?, Hills = ?, Jungle = ?, Marsh = ?, Mountain = ?, Plains = ?, Water = ? WHERE Improvement = ?",
                    (economy, loyalty, stability, unrest, consumption, defence, taxation, cavernous, coastline, desert,
                     forest, hills, jungle, marsh, mountain, plains, water, improvement))
                await cursor.execute(
                    "UPDATE KB_Kingdoms SET Economy = Economy + ?, Loyalty = Loyalty + ?, Stability = Stability + ?, Unrest = Unrest + ?, Consumption = Consumption + ?, Defence = Defence + ?, Taxation = Taxation + ? WHERE Kingdom = ?",
                    (difference_economy * amount, difference_loyalty * amount, difference_stability * amount,
                     difference_unrest * amount, difference_consumption * amount, difference_defence * amount,
                     difference_taxation * amount, kingdom))
            await cursor.execute("""select Improvement FROM KB_Hexes_Improvements WHERE Improvement = ?""",
                                 (improvement,))
            result = await cursor.fetchone()
            if result is None:
                await cursor.execute(
                    """UPDATE KB_Hexes_Improvements SET Improvement = ?, Road_Multiplier = ?, Build_Points = ?, Economy = ?, Loyalty = ?, Stability = ?, Unrest = ?, Consumption = ?, Defence = ?, Taxation = ?, Cavernous = ?, Coastline = ?, Desert = ?, Forest = ?, Hills = ?, Jungle = ?, Marsh = ?, Mountain = ?, Plains = ?, Water = ? WHERE Improvement = ?""",
                    (improvement, road_multiplier, build_points, economy, loyalty, stability, unrest, consumption,
                     defence, taxation, cavernous, coastline, desert, forest, hills, jungle, marsh, mountain, plains,
                     water, old_hex_info.improvement))
                await cursor.execute(
                    """Insert into A_Audit_All (Author, Timestamp, Database_Changed, Modification, Reason) VALUES (?, ?, ?, ?, ?)""",
                    (author, datetime.datetime.now(), "KB_Hexes_Improvements", "Update",
                     f"Updated the hex improvement of {improvement}"))
                await db.commit()
                status = f"The hex improvement of {improvement} has been modified!"
                return status
            else:
                status = f"You cannot modify a hex improvement with the same name of {improvement}!"
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
                "UPDATE KB_Kingdoms SET Control_DC = 1, Size = 1, Economy = 0, Loyalty = 0, Stability = 0, Fame = 0, Unrest = 0, Consumption = 0")
            await cursor.execute(
                "UPDATE KB_Settlements SET Size = 1, Population = 1, Economy = 0, Loyalty = 0, Stability = 0, Fame = 0, Unrest = 0, Corruption = 0, Crime = 0, Productivity = 0, Law = 0, Lore = 0, Society = 0, Danger = 0, Defence = 0, Base_Value = 0, Spellcasting = 0, Supply = 0")
            await cursor.execute(
                "INSERT into A_Audit_All (Author, Timestamp, Database_Changed, Modification, Reason) VALUES (?, ?, ?, ?, ?)",
                (author, datetime.datetime.now(), "KB_Kingdoms", "Update", "Rebalanced all kingdom buildings"))
            await db.commit()
            await cursor.execute("SELECT Kingdom from KB_Kingdoms")
            kingdoms = await cursor.fetchall()
            for kingdom in kingdoms:
                await rebalance_settlements(db, kingdom[0])
                await rebalance_hexes(db, kingdom[0])
            status = "All kingdom buildings have been rebalanced."

            return status

    except (TypeError, ValueError, aiosqlite.Error) as e:
        logging.exception(f"Error in rebalance_kingdom_building: {e}")
        return "An error occurred while balancing kingdom buildings."


async def rebalance_hexes(
        db: aiosqlite.Connection,
        kingdom: str) -> None:
    cursor = await db.cursor()
    await cursor.execute(
        "SELECT Improvement, Amount, Economy, Loyalty, Stability, Unrest, Consumption, Defence, Taxation FROM KB_Hexes WHERE Kingdom = ?",
        (kingdom,))
    improvements = await cursor.fetchall()
    total_hexes = 0
    total_economy = 0
    total_loyalty = 0
    total_stability = 0
    total_unrest = 0
    total_consumption = 0
    total_defence = 0
    total_taxation = 0
    for improvement in improvements:
        (improvement, amount, economy, loyalty, stability, unrest, consumption, defence, taxation) = improvement
        total_hexes += amount
        total_economy += economy * amount
        total_loyalty += loyalty * amount
        total_stability += stability * amount
        total_unrest += unrest * amount
        total_consumption += consumption * amount
        total_defence += defence * amount
        total_taxation += taxation * amount
    await cursor.execute(
        "Update KB_Kingdoms SET Control_DC = Control_DC + ?, Size = Size + ?, economy = economy + ?, loyalty = loyalty + ?, stability = stability + ?, unrest = unrest + ?, consumption = consumption + ?, defence = defence + ?, taxation = taxation + ? WHERE Kingdom = ?",
        (total_hexes, total_hexes, total_economy, total_loyalty, total_stability, total_unrest, total_consumption,
         total_defence, total_taxation, kingdom))
    await db.commit()


async def rebalance_settlements(
        db: aiosqlite.Connection,
        kingdom: str) -> None:
    cursor = await db.cursor()
    await cursor.execute("SELECT Settlement FROM KB_Settlements WHERE Kingdom = ?", (kingdom,))
    settlements = await cursor.fetchall()
    total_size = 0
    total_economy = 0
    total_loyalty = 0
    total_stability = 0
    total_fame = 0
    total_unrest = 0
    for settlement in settlements:
        buildings = await rebalance_buildings(db, kingdom, settlement[0])
        (size, economy, loyalty, stability, fame, unrest) = buildings
        total_size += size
        total_economy += economy
        total_loyalty += loyalty
        total_stability += stability
        total_fame += fame
        total_unrest += unrest
    await cursor.execute(
        "Update KB_Kingdoms SET Control_DC = Control_DC + ?, Size = Size + ?, economy = economy + ?, loyalty = loyalty + ?, stability = stability + ?, fame = fame + ?, unrest = unrest + ? WHERE Kingdom = ?",
        (math.floor(total_size / 36), total_size, total_economy, total_loyalty, total_stability, total_fame,
         total_unrest, kingdom))


async def rebalance_buildings(
        db: aiosqlite.Connection,
        kingdom: str,
        settlement: str) -> typing.Tuple[int, int, int, int, int, int]:
    cursor = await db.cursor()
    await cursor.execute("SELECT Building, Constructed FROM KB_Settlements WHERE Kingdom = ? AND Settlement = ?",
                         (kingdom, settlement))
    buildings = await cursor.fetchall()
    size = 0
    economy = 0
    loyalty = 0
    stability = 0
    fame = 0
    unrest = 0
    for building in buildings:
        (building, constructed) = building
        await cursor.execute("SELECT Lots, Economy, Loyalty, Stability, Fame, Unrest FROM Buildings WHERE Building = ?",
                             (building,))
        building_info = await cursor.fetchone()
        (lots, economy, loyalty, stability, fame, unrest) = building_info
        size += lots * constructed
        economy += economy * constructed
        loyalty += loyalty * constructed
        stability += stability * constructed
        fame += fame * constructed
        unrest += unrest * constructed
    await cursor.execute(
        "UPDATE KB_Settlements SET Size = ?, population = ?, Economy = ?, Loyalty = ?, Stability = ?, Fame = ?, Unrest = ? WHERE Kingdom = ? AND Settlement = ?",
        (size, size * 250, economy, loyalty, stability, fame, unrest, kingdom, settlement))
    await db.commit()
    return size, economy, loyalty, stability, fame, unrest



async def resolve_turn(
        guild_id: int,
        kingdom: str) -> str:
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute("Select Kingdom, Region, Build_Points, Control_DC, Economy, Loyalty, Stability, Unrest, Consumption, Population, Holiday, Promotion, Taxation FROM KB_Kingdoms WHERE Kingdom = ?", (kingdom,))
            kingdom_check = await cursor.fetchone()
            if not kingdom_check:
                return "The kingdom could not be found."
            (kingdom, region, build_points, control_dc, economy, loyalty, stability, unrest, consumption, population, holiday, promotion, taxation) = kingdom_check
            await cursor.execute("SELECT Holiday_Loyalty, Holiday_Consumption FROM KB_Edicts Where Holiday = ?", (holiday,))
            holiday_effects = await cursor.fetchone()
            await cursor.execute("SELECT Promotion_Stability, Promotion_Consumption FROM KB_Edicts Where Promotion = ?", (promotion,))
            promotion_effects = await cursor.fetchone()
            await cursor.execute("SELECT Taxation_Economy, Taxation_Loyalty FROM KB_Edicts Where Taxation = ?", (taxation,))
            taxation_effects = await cursor.fetchone()
            await cursor.execute("""
            SELECT 
                SUM(
                    CASE 
                        WHEN KBEC.name = 'economy' 
                        AND KBEC.severity = 
                            (CASE WHEN KBE.check_a_status > 0 THEN 1 ELSE 0 END + 
                             CASE WHEN KBE.check_b_status > 0 THEN 1 ELSE 0 END) 
                        THEN KBEC.Value 
                        ELSE 0 
                    END
                ) AS total_economy
                SUM(
                    CASE 
                        WHEN KBEC.name = 'loyalty' 
                        AND KBEC.severity = 
                            (CASE WHEN KBE.check_a_status > 0 THEN 1 ELSE 0 END + 
                             CASE WHEN KBE.check_b_status > 0 THEN 1 ELSE 0 END) 
                        THEN KBEC.Value 
                        ELSE 0 
                    END
                ) AS total_loyalty
                SUM(
                    CASE 
                        WHEN KBEC.name = 'stability' 
                        AND KBEC.severity = 
                            (CASE WHEN KBE.check_a_status > 0 THEN 1 ELSE 0 END + 
                             CASE WHEN KBE.check_b_status > 0 THEN 1 ELSE 0 END) 
                        THEN KBEC.Value 
                        ELSE 0 
                    END
                ) AS total_stability
                
            FROM KB_Events_Consequence KBEC
            LEFT JOIN KB_Events_Active KBE ON KBEC.Name = KBE.Name
            WHERE Kingdom = ?;""", (kingdom,))
            event_consequences = await cursor.fetchone()
            (total_economy, total_loyalty, total_stability) = event_consequences
            await cursor.execute("SELECT id, Kingdom, Settlement, Hex, Name, Check_A_Status, Check_B_Status, Success_Requirement, Duration FROM KB_Events_Active WHERE Kingdom = ? And Active = 1", (kingdom,))
            active_events = await cursor.fetchall()
            await cursor.execute("SELECT SUM(Consumption_Size) FROM KB_Armies WHERE Kingdom = ?", (kingdom,))
            army_consumption = await cursor.fetchone()
            consumption_modifier = 0
            farm_penalty = 0
            for event in active_events:
                (event_id, kingdom, settlement, hex_id, name, check_a_status, check_b_status, success_requirement, duration, holiday, promotion, taxation) = event
                severity = 0
                severity += check_a_status if check_a_status > 0 else 0
                severity += check_b_status if check_b_status > 0 else 0
                await handle_severity(
                    db=db,
                    severity=severity,
                    kingdom=kingdom,
                    region=region,
                    settlement=settlement,
                    hex_id=hex_id,
                    event=name,
                    success_requirement=success_requirement,
                    duration=duration,
                    event_id=event_id)
                if name == "Food Shortage" and severity == 0:
                    consumption_modifier += 1
                elif name == "Food Shortage" and severity == 1:
                    consumption_modifier += .5
                elif name == "Food Surplus":
                    consumption_modifier -= .5
                elif name == "Crop Failure" and severity == 0:
                    farm_penalty += 2
                elif name == "Crop Failure" and severity == 1:
                    farm_penalty += 1
            economy += total_economy
            economy += taxation_effects[0] if taxation_effects else 0
            loyalty += total_loyalty
            loyalty += holiday_effects[0] if holiday_effects else 0
            loyalty += taxation_effects[1] if taxation_effects else 0
            stability += total_stability
            stability += promotion_effects[0] if promotion_effects else 0
            stability_check = random.randint(1, 20) + stability - control_dc - unrest
            if stability_check < -5:
                unrest_modify = random.randint(1, 4)
                await cursor.execute("UPDATE KB_Kingdoms SET Unrest = Unrest + ? WHERE Kingdom = ?", (unrest_modify, kingdom))
            elif stability_check < 0:
                await cursor.execute("UPDATE KB_Kingdoms SET Unrest = Unrest + 1 WHERE Kingdom = ?", (kingdom, ))
            else:
                await cursor.execute("UPDATE KB_Kingdoms SET Unrest = Unrest - 1 WHERE Kingdom = ?", (kingdom, ))
            consumption += holiday_effects[1] if holiday_effects else 0
            consumption += promotion_effects[1] if promotion_effects else 0
            consumption = consumption + (consumption_modifier * consumption)
            population = consumption + army_consumption[0] if army_consumption else consumption
            await cursor.execute("""
            SELECT 
            SUM(CASE WHEN subtype = 'Grain' THEN amount * quality ELSE 0 END) AS Grain_total,
            SUM(CASE WHEN subtype = 'Produce' THEN amount * quality ELSE 0 END) AS Produce_total
            SUM(CASE WHEN subtype = 'Husbandry' THEN amount * quality ELSE 0 END) AS Husbandry_total
            SUM(CASE WHEN subtype = 'Seafood' THEN amount * quality ELSE 0 END) AS Seafood_total
            FROM KB_Hexes_Constructed WHERE Kingdom = ?""", (kingdom,))
            food_results = await cursor.fetchone()
            (produced_grain, produced_produce, produced_husbandry, produced_seafood) = food_results
            if farm_penalty == 1:
                produced_grain = produced_grain * .5 if produced_grain else 0
                produced_husbandry = produced_husbandry * .5 if produced_husbandry else 0
                produced_produce = produced_produce * .5 if produced_produce else 0
            elif farm_penalty == 2:
                produced_grain = 0
                produced_husbandry = 0
                produced_produce = 0
            await cursor.execute("""SELECT 
            SUM(Husbandry), SUM(Grain), SUM(Produce), SUM(Seafood),
            SUM(Ore), SUM(Stone), Sum(Wood), Sum(Raw_Textiles),
            SUM(Metallurgy), SUM(Woodworking), SUM(Textiles), Sum(Stoneworking),
            SUM(Mundane_Complex), SUM(Mundane_Exotic), Sum(Magical_Consumable), SUM(Maxical_Items)
            FROM KB_Trade where Source_Kingdom = ?
            """, (kingdom,))
            sending_trade_results = await cursor.fetchone()
            (sending_husbandry, sending_grain, sending_produce, sending_seafood, sending_ore, sending_stone, sending_wood, sending_raw_textiles, sending_metallurgy, sending_woodworking, sending_textiles, sending_stoneworking, sending_mundane_complex, sending_mundane_exotic, sending_magical_consumable, sending_magical_items) = sending_trade_results
            await cursor.execute("""SELECT
            SUM(Husbandry), SUM(Grain), SUM(Produce), SUM(Seafood),
            SUM(Ore), SUM(Stone), Sum(Wood), Sum(Raw_Textiles),
            SUM(Metallurgy), SUM(Woodworking), SUM(Textiles), Sum(Stoneworking),
            SUM(Mundane_Complex), SUM(Mundane_Exotic), Sum(Magical_Consumable), SUM(Maxical_Items)
            FROM KB_Trade where end_Kingdom = ?
            """, (kingdom,))
            receiving_trade_results = await cursor.fetchone()
            (receiving_husbandry, receiving_grain, receiving_produce, receiving_seafood, receiving_ore, receiving_stone, receiving_wood, receiving_raw_textiles, receiving_metallurgy, receiving_woodworking, receiving_textiles, receiving_stoneworking, receiving_mundane_complex, receiving_mundane_exotic, receiving_magical_consumable, receiving_magical_items) = receiving_trade_results
            await cursor.execute("SELECT Stored_Grain, Stored_Produce, Stored_Husbandry, Stored_Seafood FROM KB_Kingdoms WHERE Kingdom = ?", (kingdom,))
            stored_food_results = await cursor.fetchone()
            (stored_grain, stored_produce, stored_husbandry, stored_seafood) = stored_food_results
            grain = safe_int_complex(produced_grain, -sending_grain, receiving_grain, stored_grain)
            produce = safe_int_complex(produced_produce, -sending_produce, receiving_produce, stored_produce)
            husbandry = safe_int_complex(produced_husbandry - sending_husbandry + receiving_husbandry, stored_husbandry, None, None)
            seafood = safe_int_complex(produced_seafood - sending_seafood + receiving_seafood, stored_seafood, None, None)
            resource_utilization_dict = {"Grain": grain, "Produce": produce, "Husbandry": husbandry, "Seafood": seafood}
            build_point_result = (random.randint(1, 20) + economy - unrest) // 3
            await cursor.execute("""SELECT SUM(Amount) FROM KB_Hexes_Constructed WHERE Kingdom = ? AND Subtype in ('Husbandry', 'Seafood', 'Produce', 'Grain')""", (kingdom,))
            food_building_results = await cursor.fetchone()
            food_building = food_building_results[0] // 10 if food_building_results else 0
            await cursor.execute("""SELECT SUM(Amount) FROM KB_Hexes_Constructed WHERE Kingdom = ? AND Subtype in ('Ore', 'Stone', 'Wood', 'Raw_Textiles')""", (kingdom,))
            raw_building_results = await cursor.fetchone()
            raw_building = raw_building_results[0] // 10 if raw_building_results else 0
            await cursor.execute("""SELECT SUM(Amount) FROM KB_Buildings WHERE Kingdom = ? AND (Subtype in ('Metallurgy', 'Woodworking', 'Textiles', 'Stoneworking') OR Name in ('Guildhall', 'Tannery'))""", (kingdom,))
            processed_building_results = await cursor.fetchone()
            processed_building = processed_building_results[0] // 10 if processed_building_results else 0
            await cursor.execute("""SELECT SUM(Amount) FROM KB_Buildings WHERE Kingdom = ? AND (Subtype in ('Mundane_Complex', 'Mundane_Exotic', 'Magical_Consumable', 'Magical_Items') OR Name in 
            ('Alchemist', 'Casters Tower', 'Herbalist', 'Luxury Store', 'Magic Shop'))""", (kingdom,))
            finished_building_results = await cursor.fetchone()
            finished_building = finished_building_results[0] // 10 if finished_building_results else 0
            await cursor.execute("""SELECT   
            Seafood + Produce + Grain + Husbandry,
            Ore + Stone + Raw_Textiles + Wood,
            Metallurgy + Woodworking + Textiles + Stoneworking,
            Mundane_Complex + Mundane_Exotic + Magical_Consumable + Magical_Items
            FROM KB_Trade where Source_Kingdom = ?""", (kingdom,))
            sending_trade_results = await cursor.fetchall()
            trade_bp = 0
            for trade in sending_trade_results:
                (food, raw, processed, finished) = trade
                trade_bp += food_building if food > 0 and sum(resource_utilization_dict.values()) > consumption else 0
                trade_bp += raw_building if raw > 0 and sum(resource_utilization_dict.values()) > consumption else 0
                trade_bp += processed_building if processed > 0 and sum(resource_utilization_dict.values()) > consumption else 0
                trade_bp += finished_building if finished > 0 and sum(resource_utilization_dict.values()) > consumption else 0

            if sum(resource_utilization_dict.values()) > consumption:
                resource_allocation_dict = shared_functions.allocate_food(consumption, resource_utilization_dict)
                await cursor.execute("""
                SELECT 
                SUM(CASE WHEN subtype = 'Grain' THEN amount * quality * 5 ELSE 0 END) AS Grain_total,
                SUM(CASE WHEN subtype = 'Produce' THEN amount * quality * 5 ELSE 0 END) AS Produce_total
                SUM(CASE WHEN subtype = 'Husbandry' THEN amount * quality * 5 ELSE 0 END) AS Husbandry_total
                SUM(CASE WHEN subtype = 'Seafood' THEN amount * quality * 5 ELSE 0 END) AS Seafood_total
                FROM KB_Buildings WHERE Kingdom = ?""", (kingdom,))
                food_building_results = await cursor.fetchone()
                (building_grain, building_produce, building_husbandry, building_seafood) = food_building_results
                storable_grain = max(min(building_grain, resource_allocation_dict["Grain"]),0)
                storable_produce = max(min(building_produce, resource_allocation_dict["Produce"]), 0)
                storable_husbandry = max(min(building_husbandry, resource_allocation_dict["Husbandry"]), 0)
                storable_seafood = max(min(building_seafood, resource_allocation_dict["Seafood"]), 0)
                await cursor.execute("UPDATE KB_Kingdoms SET Stored_Grain = ?, Stored_Produce = ?, Stored_Husbandry = ?, Stored_Seafood = ? WHERE Kingdom = ?", (storable_grain, storable_produce, storable_husbandry, storable_seafood, kingdom))
                proper_utilization_grain = (resource_utilization_dict["Grain"] - resource_allocation_dict["Gain"]) > 0 and (resource_utilization_dict["Grain"] - resource_allocation_dict["Gain"]) > math.floor(consumption * .15)
                proper_utilization_produce = (resource_utilization_dict["Produce"] - resource_allocation_dict["Produce"]) > 0 and (resource_utilization_dict["Produce"] - resource_allocation_dict["Produce"]) > math.floor(consumption * .15)
                proper_utilization_husbandry = (resource_utilization_dict["Husbandry"] - resource_allocation_dict["Husbandry"]) > 0 and (resource_utilization_dict["Husbandry"] - resource_allocation_dict["Husbandry"]) > math.floor(consumption * .15)
                proper_utilization_seafood = (resource_utilization_dict["Seafood"] - resource_allocation_dict["Seafood"]) > 0 and (resource_utilization_dict["Seafood"] - resource_allocation_dict["Seafood"]) > math.floor(consumption * .15)
                if all([proper_utilization_grain, proper_utilization_produce, proper_utilization_husbandry, proper_utilization_seafood]):
                    await kingdom_event(db=db, kingdom=kingdom, event="Well Fed!", region=region, settlement=None)
                elif proper_utilization_seafood + proper_utilization_produce + proper_utilization_husbandry + proper_utilization_grain < 2:
                    await cursor.execute("SELECT Sum(Lots * Amount) from KB_Buildings WHERE Kingdom = ?", (kingdom,))
                    building_lots = await cursor.fetchone()
                    size = building_lots[0] // 36 if building_lots else 1
                    await cursor.execute("UPDATE KB_Kingdoms SET unrest = unrest + ? WHERE Kingdom = ?", (size, kingdom))
            else:
                build_point_result -= consumption - sum(resource_utilization_dict.values())
                if consumption - sum(resource_utilization_dict.values()) > 8:
                    await kingdom_event(db=db, kingdom=kingdom, event="Starving", region=region, settlement=None)
            if consumption - sum(resource_utilization_dict.values()) < 10:
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
                        await cursor.execute("UPDATE KB_Kingdoms SET Unrest = Unrest + 1 WHERE Kingdom = ?", (kingdom,))
                    else:
                        available_housing = housing - (population // 250)
                        population_increase = 0
                        for x in range(available_housing):
                            population_increase += random.randint(1, 150)
                            if consumption - sum(resource_utilization_dict.values()) < -10:
                                population_increase += random.randint(1, 100)
                        await cursor.execute("UPDATE KB_Kingdoms SET Population = Population + ? WHERE Kingdom = ?", (population_increase, kingdom))
                else:
                        await cursor.execute("UPDATE KB_Kingdoms SET Unrest = Unrest + 1 WHERE Kingdom = ?", (kingdom,))
            await db.commit()
            await cursor.execute("SELECT SUM(KB.Amount * KBB.Build_Points) FROM KB_Buildings KB LEFT JOIN KB_Buildings_Blueprints KBB ON KB.Building = KBB.Building WHERE KB.Kingdom = ?", (kingdom,))
            building_points = await cursor.fetchone()
            building_points_mass = building_points[0] if building_points else 0
            build_point_result = min(build_point_result, building_points_mass // 10) + trade_bp
            await cursor.execute("UPDATE KB_Kingdoms SET Build_Points = Build_Points + ? WHERE Kingdom = ?", (build_point_result, kingdom))
            if build_points + build_point_result < 0:
                await cursor.execute("UPDATE KB_Kingdoms SET Unrest = Unrest + 2 WHERE Kingdom = ?", (kingdom,))

            await cursor.execute(
                "SELECT Build_Points, Control_DC, Economy, Loyalty, Stability, Unrest, Consumption, Population, Unrest FROM KB_Kingdoms WHERE Kingdom = ?",
                (kingdom,))
            updated_kingdom_status = await cursor.fetchone()
            (updated_build_points, updated_control_dc, updated_economy, updated_loyalty, updated_stability, updated_unrest, updated_consumption, updated_population, updated_unrest) = updated_kingdom_status
            if updated_unrest > 10:
                await cursor.execute("SELECT ID FROM KB_Hexes where IsTown = 0 and Kingdom = ? Order by Random() Limit 1", (kingdom,))
                random_hex = await cursor.fetchone()
                await cursor.execute("UPDATE KB_Hexes SET Kingdom = Null WHERE ID = ?", (random_hex,))

    except:
        return "An error occurred while resolving the turn."
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
    @app_commands.autocomplete(region=shared_functions.region_autocomplete)
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
            status = await kingdom_commands.adjust_bp(interaction.guild_id, interaction.user.id, kingdom, build_points, False)
            await interaction.followup.send(status)
        except (TypeError, ValueError) as e:
            logging.exception(f"Error in kingdom_build_points: {e}")
            await interaction.followup.send("An error occurred while adjusting kingdom build points.")

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
                status = await kingdom_commands.remove_building(
                    guild_id=interaction.guild_id,
                    author=interaction.user.id,
                    kingdom=kingdom,
                    settlement=settlement,
                    amount=amount,
                    building_info=building_info,
                    size=size[0])
            await interaction.followup.send(status)
        except (TypeError, ValueError) as e:
            logging.exception(f"Error in remove_from_settlement: {e}")
            await interaction.followup.send("An error occurred while removing a building from a settlement.")

    @hex_group.command(name='add', description='Add a new hex improvement for players to build')
    async def add_hex_improvement(
            self, interaction: discord.Interaction, improvement: str, road_multiplier: int,
            build_points: int, economy: int, loyalty: int, stability: int, unrest: int,
            consumption: int, defence: int, taxation: int, cavernous: int, coastline: int,
            desert: int, forest: int, hills: int, jungle: int, marsh: int, mountain: int,
            plains: int, water: int):
        """Add a new hex improvement for players to build"""
        await interaction.response.defer(thinking=True)
        try:
            status = await add_hex_improvements(
                interaction.guild_id,
                interaction.user.id,
                improvement,
                road_multiplier,
                build_points,
                economy, loyalty, stability, unrest, consumption, defence, taxation,
                cavernous, coastline, desert, forest, hills, jungle, marsh, mountain, plains, water)
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
    async def modify_hex_improvement(
            self, interaction: discord.Interaction, improvement: str,
            road_multiplier: typing.Optional[int], build_points: typing.Optional[int],
            economy: typing.Optional[int], loyalty: typing.Optional[int],
            stability: typing.Optional[int], unrest: typing.Optional[int],
            consumption: typing.Optional[int], defence: typing.Optional[int],
            taxation: typing.Optional[int], cavernous: typing.Optional[int],
            coastline: typing.Optional[int], desert: typing.Optional[int],
            forest: typing.Optional[int], hills: typing.Optional[int],
            jungle: typing.Optional[int], marsh: typing.Optional[int],
            mountain: typing.Optional[int], plains: typing.Optional[int],
            water: typing.Optional[int]):
        """Modify hex improvements that are available to build, or have been built"""
        await interaction.response.defer(thinking=True)
        try:
            old_hex_info = await kingdom_commands.fetch_hex_improvement(interaction.guild_id, improvement)
            status = await modify_hex_improvements(
                guild_id=interaction.guild_id,
                author=interaction.user.id,
                old_hex_info=old_hex_info,
                improvement=improvement,
                road_multiplier=road_multiplier,
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
                mountain=mountain,
                plains=plains,
                water=water)
            await interaction.followup.send(status)
        except (TypeError, ValueError) as e:
            logging.exception(f"Error in modify_hex_improvement: {e}")
            await interaction.followup.send("An error occurred while modifying a hex improvement.")

    @hex_group.command(name='create', description='create and add a hex into play.')
    @app_commands.autocomplete(kingdom=kingdom_commands.kingdom_autocomplete)
    @app_commands.autocomplete(terrain=kingdom_commands.hex_terrain_autocomplete)
    @app_commands.autocomplete(region=shared_functions.region_autocomplete)
    @app_commands.choices(
        behavior=[discord.app_commands.Choice(name='set', value=1),
                  discord.app_commands.Choice(name='random', value=2)])
    async def add_hex(self, interaction: discord.Interaction, kingdom: typing.Optional[str], terrain: str, region: str, farm: int,
                      ore: int, stone: int, wood: int, fish: int, behavior: discord.app_commands.Choice[int] = 1):
        await interaction.response.defer(thinking=True)
        try:
            behavior_value = behavior.value if isinstance(behavior, discord.app_commands.Choice) else 1
            if behavior_value == 2:
                farm = random.randint(1, farm)
                ore = random.randint(1, ore)
                stone = random.randint(1, stone)
                wood = random.randint(1, wood)
                fish = random.randint(1, fish)
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
                if kingdom:
                    await cursor.execute("UPDATE KB_Kingdoms SET Control_DC = Control_DC + 1 WHERE Kingdom = ?",
                                         (kingdom,))
                    status = f"The hex with ID {hex_id[0]} has been created and added to the kingdom of {kingdom}!\r\nit can support {farm} farms, {ore} mines, {stone} quarries, {wood} woodcutters and {fish} fisheries."
                else:
                    status = f"The hex with ID {hex_id[0]} has been created!\r\nit can support {farm} farms, {ore} mines, {stone} quarries, {wood} woodcutters and {fish} fisheries."
                await db.commit()

                await interaction.followup.send(status)
        except(TypeError, ValueError) as e:
            logging.exception(f"Error in add_hex: {e}")
            await interaction.followup.send("An error occurred while adding a hex.")

    @hex_group.command(name='edit', description='edit a hex in play.')
    @app_commands.autocomplete(kingdom=kingdom_commands.kingdom_autocomplete)
    @app_commands.autocomplete(terrain=kingdom_commands.hex_terrain_autocomplete)
    @app_commands.autocomplete(region=shared_functions.region_autocomplete)
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
                farm = random.randint(1, farm) if farm else hex_info[3]
                ore = random.randint(1, ore) if ore else hex_info[4]
                stone = random.randint(1, stone) if stone else hex_info[5]
                wood = random.randint(1, wood) if wood else hex_info[6]
                fish = random.randint(1, fish) if fish else hex_info[7]
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
                await cursor.execute("UPDATE KB_Kingdoms SET Control_DC = Control_DC - 1 WHERE Kingdom = ?",
                                     (hex_info[0],))
                if kingdom:
                    await cursor.exeucte("UPDATE KB_Kingdoms SET Control_DC = Control_DC + 1 WHERE Kingdom = ?",
                                         (kingdom,))
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

                await cursor.execute("UPDATE KB_Kingdoms SET Control_DC = Control_DC - 1 WHERE Kingdom = ?",
                                     (kingdom[0],))
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
            old_blueprint = await kingdom_commands.fetch_building(interaction.guild_id, old_name)
            status = await modify_blueprint(
                guild_id=interaction.guild_id,
                author=interaction.user.id,
                old_blueprint_info=old_blueprint,
                building=name,
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
    async def modify_leadership(self, interaction: discord.Interaction, kingdom: str, password: str,
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
    async def remove(self, interaction: discord.Interaction, kingdom: str, password: str, title: str):
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
    @app_commands.autocomplete(region=shared_functions.region_autocomplete)
    @app_commands.autocomplete(bonus=modifier_autocomplete)
    @app_commands.autocomplete(penalty=modifier_autocomplete)
    async def create_event(
            self, interaction: discord.Interaction, scale: discord.app_commands.Choice[int], likelihood: int, name: str,
            description: str, special: typing.Optional[str],
            type: discord.app_commands.Choice[int], first_check: typing.Optional[discord.app_commands.Choice[int]], penalty: str, bonus: str,
            second_check: typing.Optional[discord.app_commands.Choice[int]], region: str = 'All',
            hex: discord.app_commands.Choice[int] = 0, requirements: discord.app_commands.Choice[int] = 0):
        """Create a new event for the kingdom"""
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
                hex_value = hex.value if isinstance(hex, discord.app_commands.Choice) else hex
                requirements_value = requirements.value if isinstance(requirements,
                                                                      discord.app_commands.Choice) else requirements
                type_value = type.value if isinstance(type, discord.app_commands.Choice) else type
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
                await cursor.execute(
                    "INSERT INTO KB_Events (scale, likelihood, Region, Name, Effect, Special, Type, Check_A, Check_b, Hex, Success_Requirements) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (scale_value, likelihood, region, name, description, special, type_value, first_check_value,
                     second_check_value, hex_value, requirements_value))
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
    @app_commands.autocomplete(region=shared_functions.region_autocomplete)
    @app_commands.autocomplete(bonus=modifier_autocomplete)
    @app_commands.autocomplete(penalty=modifier_autocomplete)
    @app_commands.autocomplete(old_name=event_name_autocomplete)
    async def create_event(
            self, interaction: discord.Interaction, old_name: str, scale: typing.Optional[discord.app_commands.Choice[int]],
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
                scale_value = scale.value if isinstance(scale, discord.app_commands.Choice) else info_scale
                hex_value = hex.value if isinstance(hex, discord.app_commands.Choice) else info_hex
                requirements_value = requirements.value if isinstance(requirements,
                                                                      discord.app_commands.Choice) else info_requirements
                type_value = type.value if isinstance(type, discord.app_commands.Choice) else info_type
                first_check_value = first_check.value if isinstance(first_check,
                                                                    discord.app_commands.Choice) else info_check_a
                second_check_value = second_check.value if isinstance(second_check,
                                                                      discord.app_commands.Choice) else info_check_b
                scale_value = scale_value if scale_value else info_scale
                likelihood = likelihood if likelihood else info_likelihood
                region = region if region else info_region
                name = new_name if new_name else info_name
                description = description if description else info_effect
                special = special if special else info_special
                if second_check_value and not first_check_value:
                    if second_check_value == 4 or second_check_value == 5:
                        await interaction.followup.send(
                            "You must select a first check to demand a building or improvement.")
                        return
                    first_check_value = second_check_value
                    second_check_value = None
                await cursor.execute(
                    "UPDATE KB_Events SET name = ?, scale = ?, likelihood = ?, Region = ?, Name = ?, Effect = ?, Special = ?, Type = ?, Check_a = ?, Check_b = ?, Hex = ?, Success_Requirements = ? WHERE Name = ?",
                    (name, scale_value, likelihood, region, name, description, special, type_value, first_check_value,
                     second_check_value, hex_value, requirements_value, old_name))
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
                await cursor.execute("DELETE FROM KB_Events_Consequence where Name = ?", (name,))
                await db.commit()
                await interaction.followup.send(f"The event with the name {name} has been deleted.")
        except (TypeError, ValueError) as e:
            logging.exception(f"Error in create_event: {e}")
            await interaction.followup.send("An error occurred while creating an event.")

    @event_group.command(name="complification", description="Add an Event Effect to an event")
    @app_commands.choices(
        severity=[discord.app_commands.Choice(name='on creation', value=-1),
                  discord.app_commands.Choice(name='passive / failed result', value=0),
                  discord.app_commands.Choice(name='single pass', value=1),
                  discord.app_commands.Choice(name='passed both', value=2)])
    @app_commands.choices(
        roll_behavior=[discord.app_commands.Choice(name='set as result', value=-0),
                       discord.app_commands.Choice(name='randomize result', value=1),
                       discord.app_commands.Choice(name='percentile effect', value=2),
                       discord.app_commands.Choice(name='exploding on max', value=3),
                       discord.app_commands.Choice(name='Explodes into multiple on max', value=4)])
    @app_commands.autocomplete(name=event_name_autocomplete)
    @app_commands.autocomplete(type=type_value_autocomplete)
    async def create_complication(
            self, interaction: discord.Interaction, name: str,
            severity: typing.Optional[discord.app_commands.Choice[int]],
            type: str, value: int, reroll: typing.Optional[discord.app_commands.Choice[int]],
    roll_behavior: discord.app_commands.Choice[int]):
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
                severity_value = severity.value if isinstance(severity, discord.app_commands.Choice) else severity
                reroll_value = reroll.value if isinstance(reroll, discord.app_commands.Choice) else reroll
                await cursor.execute(
                    "INSERT INTO KB_Events_Consequence (Name, Severity, Type, Value, Reroll) VALUES (?, ?, ?, ?, ?)",
                    (name, severity_value, type, value, reroll_value))
                await db.commit()
                await cursor.execute("SELECT MAX(ID) from KB_Events_Consequence")
                id = await cursor.fetchone()
                await interaction.followup.send(f"The complication has been added to the event with ID {id[0]}.")
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
        roll_behavior=[discord.app_commands.Choice(name='set as result', value=-0),
                       discord.app_commands.Choice(name='randomize result', value=1),
                       discord.app_commands.Choice(name='percentile effect', value=2),
                       discord.app_commands.Choice(name='exploding on max', value=3),
                       discord.app_commands.Choice(name='Explodes into multiple on max', value=4)])
    @app_commands.autocomplete(name=event_name_autocomplete)
    @app_commands.autocomplete(type=type_value_autocomplete)
    async def modify_complication(
            self, interaction: discord.Interaction, name: typing.Optional[str], id: int,
            severity: typing.Optional[discord.app_commands.Choice[int]],
            type: typing.Optional[str], value: typing.Optional[int],
            reroll: typing.Optional[discord.app_commands.Choice[int]],
    roll_behavior: typing.Optional[discord.app_commands.Choice[int]]):
        """Modify an existing event consequence for the kingdom"""
        await interaction.response.defer(thinking=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute(
                    "SELECT Name, Severity, Type, Value, Reroll from KB_Events_Consequence where ID = ?", (id,))
                event = await cursor.fetchone()
                if not event:
                    await interaction.followup.send("An event with that name does not exist.")
                    return
                (old_name, old_severity, old_type, old_value, old_reroll) = event
                name = name if name else old_name
                severity_value = severity.value if isinstance(severity, discord.app_commands.Choice) else old_severity
                reroll_value = reroll.value if isinstance(reroll, discord.app_commands.Choice) else old_reroll
                type = type if type else old_type
                value = value if value else old_value
                await cursor.execute(
                    "UPDATE KB_Events_Consequence SET Name = ?, Severity = ?, Type = ?, Value = ?, Reroll = ? WHERE ID = ?",
                    (name, severity_value, type, value, reroll_value, id))
                await db.commit()
                await interaction.followup.send(f"The complication has been modified.")
        except (TypeError, ValueError) as e:
            logging.exception(f"Error in create_complication: {e}")
            await interaction.followup.send("An error occurred while creating an event.")

    @event_group.command(name="delete_complication", description="Delete an Event Effect to an event")
    @app_commands.autocomplete(name=event_name_autocomplete)
    async def delete_complication(self, interaction: discord.Interaction, name: str, id: int):
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
                await cursor.execute("DELETE FROM KB_Events_Consequence where ID = ?", (id,))
                await db.commit()
                await interaction.followup.send(f"The complication has been removed.")
        except (TypeError, ValueError) as e:
            logging.exception(f"Error in create_complication: {e}")
            await interaction.followup.send("An error occurred while creating an event.")

    @event_group.command(name="display", description="display a list of events")
    @app_commands.autocomplete(name=event_name_autocomplete)
    @app_commands.choices(
        type=[discord.app_commands.Choice(name='all', value=0),
              discord.app_commands.Choice(name='problematic', value=1),
              discord.app_commands.Choice(name='beneficial', value=2)])
    async def display_event(self, interaction: discord.Interaction, name: typing.Optional[str],
                            view_type: discord.app_commands.Choice[int] = 1,
                            type: discord.app_commands.Choice[int] = 0):
        """Display a list of events"""
        await interaction.response.defer(thinking=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                view_type_value = view_type.value if isinstance(view_type, discord.app_commands.Choice) else view_type
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

                view = EventDisplayView(
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
    @app_commands.describe(event="This selects a specific event and has the highest priority.")
    @app_commands.choices(
        randomize=[discord.app_commands.Choice(name='set', value=0),
                   discord.app_commands.Choice(name='random', value=1)])
    @app_commands.choices(
        event_type=[discord.app_commands.Choice(name='Kingdom', value=0),
                    discord.app_commands.Choice(name='Settlement', value=1)])
    async def spawn_event(self, interaction: discord.Interaction, kingdom: str, event: typing.Optional[str], event_type: discord.app_commands.Choice[int],
                          randomize: discord.app_commands.Choice[int] = 1, number: int = 1, ):
        """Spawn an event for a kingdom"""
        await interaction.response.defer(thinking=True)
        try:
            randomize_value = randomize.value if isinstance(randomize, discord.app_commands.Choice) else randomize
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                if randomize_value == 1:
                    await cursor.execute("SELECT Name from KB_Events ORDER BY RANDOM() LIMIT 1")
                    event = await cursor.fetchone()
                await cursor.execute("SELECT Name from KB_Events where Name = ?", (event,))
                event_info = await cursor.fetchone()
                if not event_info:
                    await interaction.followup.send("The event with that name does not exist.")
                    return
                await cursor.execute("SELECT Name from KB_Kingdoms where Kingdom = ?", (kingdom,))
                kingdom_info = await cursor.fetchone()
                if not kingdom_info:
                    await interaction.followup.send("The kingdom with that name does not exist.")
                    return
                for _ in range(number):
                    await cursor.execute("INSERT INTO KB_Kingdom_Events (Kingdom, Event) VALUES (?, ?)",
                                         (kingdom, event))
                await db.commit()
                await interaction.followup.send(f"The event {event} has been spawned for the kingdom of {kingdom}.")
        except (TypeError, ValueError) as e:
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
    @app_commands.autocomplete(region=shared_functions.region_autocomplete)
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


logging.basicConfig(
    level=logging.INFO,  # Set the minimum logging level
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='application.log',  # Log to a file
    filemode='a'  # Append to the file
)


class EventDisplayView(shared_functions.DualView):
    def __init__(self, user_id: int, guild_id: int, offset: int, limit: int, view_type: int,
                 interaction: discord.Interaction):
        super().__init__(user_id=user_id, guild_id=guild_id, offset=offset, limit=limit, view_type=view_type,
                         interaction=interaction, content="")
        self.max_items = None  # Cache total number of items
        self.view_type = view_type

    async def update_results(self):
        """Update the results based on the current offset."""
        if self.view_type == 1:
            statement = """
            SELECT Scale, Likelihood, Region, Type, Name, Effect, Special, 
            Check_A, Check_B, Hex, Success_Requirements, 
            Duration, Bonus, Penalty, Hex 
            from KB_Events ORDER BY Name LIMIT ? OFFSET ?
            """
        elif self.view_type == 2:
            statement = """
                        SELECT Scale, Likelihood, Region, Type, Name, Effect, Special, 
                        Check_A, Check_B, Hex, Success_Requirements, 
                        Duration, Bonus, Penalty, Hex from 
                        KB_Events WHERE Type = "Problematic" 
                        ORDER BY Name LIMIT ? OFFSET ?
                        """
        else:
            statement = """
                        SELECT Scale, Likelihood, Region, Type, Name, Effect, Special, 
                        Check_A, Check_B, Hex, Success_Requirements, 
                        Duration, Bonus, Penalty, Hex from 
                        KB_Events WHERE Type = "Beneficial" 
                        ORDER BY Name LIMIT ? OFFSET ?
                        """
        async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
            cursor = await db.execute(statement, (self.limit, self.offset))
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
                self.embed.add_field(name=f'Character Name', value=f'**Name**:{true_character_name}')
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
                (scale, likelihood, region, type, name, effect, special,
                 check_a, check_b, hex, success_requirements,
                 duration, bonus, penalty, hex) = result
                duration = f"{duration} turns" if duration > 0 else "Ongoing"
                check_dict = {1: "Loyalty", 2: "Stability", 3: "Economy", 4: "Demand Building", 5: "Demand Improvement"}
                check_a = check_dict[check_a]
                check_b = check_dict[check_b]
                type_dict = {1: "Beneficial", 2: "Problematic"}
                hex_dict = {0: "Does not affect hexes", 1: "Affects a hex"}
                requirements_dict = {0: "No requirements", 1: "Succeed at one check", 2: "Succeed at both checks"}
                field_content = f"""**Likelihood**: {likelihood} **Type**: {type_dict[type]} 
                \r\n**Scale**: {scale}, **Region**: {region}, **Hex**: {hex_dict[hex]}, **Duration**: {duration}
                \r\n**Effect**: {effect}
                \r\n**Special**: {special}, 
                \r\n**Check A**: {check_a}, **Check B**: {check_b}, **Success Requirements**: {requirements_dict[success_requirements]}'
                \r\n**Bonus**: {bonus}, **Penalty**: {penalty}
                """
                self.embed.add_field(name=f'**Event**: {name}', value=field_content, inline=False)
                field_content = ""
                async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
                    cursor = await db.execute(
                        "SELECT ID, Name, Severity, Type, Value, Reroll FROM KB_Events_Consequence where Name = ? Order BY Severity asc",
                        (name,))
                    unforeseen_consequences = await cursor.fetchall()
                    consequence_rolltype_dict = {0: "Set", 1: "Randomized", 2: "Per building sharing this trait",
                                                 3: "Percentile Effect", 4: "Randomized with 'exploding' reroll on max",
                                                 5: "Singular Effect that explodes on Max"}
                    if type == "Problematic":
                        consequence_severity_dict = {0: "No Action or failed rolls", 1: "Passed 1 Check",
                                                     2: "passed 2 checks"}
                    else:
                        consequence_severity_dict = {0: "No Action Required"}
                    for consequence in unforeseen_consequences:
                        (id, name, severity, type, value, reroll) = consequence
                        field_content += f"\r\n**ID**: {id} **Consequence**: {name}, **Severity**: {consequence_severity_dict[severity]}, **Effects**: {type}, **Value**: {value}, **Reroll**: {consequence_rolltype_dict[reroll]}"
                    self.embed.add_field(name=f'**{name} consequences**', value=field_content, inline=False)

    async def get_max_items(self):
        """Get the total number of titles."""
        if self.max_items is None:
            async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
                if self.view_type == 1:
                    cursor = await db.execute("SELECT COUNT(*) from KB_Events")
                elif self.view_type == 2:
                    cursor = await db.execute("SELECT COUNT(*) from KB_Events where Type = 'Problematic'")
                else:
                    cursor = await db.execute("SELECT COUNT(*) from KB_Events where Type = 'Beneficial'")
                count = await cursor.fetchone()
                self.max_items = count[0]
        return self.max_items

    async def on_view_change(self):
        self.view_type = 1 if self.view_type == 2 else 2
        if self.view_type == 1:
            self.limit = 5  # Change the limit to 5 for the summary view
        else:
            self.limit = 1  # Change the limit to 1 for the detailed view
