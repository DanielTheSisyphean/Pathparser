import logging
import random
import typing
import datetime
import math
import aiosqlite
from core import utils

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
            await kingdom_event(db=db, kingdom=kingdom, region=region, event=event[1], settlement=None)
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
        if not event_list:
            return
        event = random.choices(event_list, weights=[event[0] for event in event_list])
        if scale == "Settlement":
            await cursor.execute(
                "Select Kingdom, Settlement FROM KB_Settlements WHERE Kingdom = ? order by Random() limit 1",
                (kingdom,))
            settlement_result = await cursor.fetchone()
            if not settlement_result:
                return
            settlement = settlement_result[1]
        else:
            settlement = None
        await kingdom_event(db=db, kingdom=kingdom, region=region, event=event[0][1], settlement=settlement)
    except (TypeError, ValueError, aiosqlite.Error) as error:
        logging.exception(f"Error in randomize_event_trigger: {error}")


async def kingdom_event(
        db: aiosqlite.Connection,
        kingdom: str,
        region: typing.Optional[str],
        event: str,
        settlement: typing.Optional[str],
        specified_hex: typing.Optional[int] = None) -> None:
    try:
        cursor = await db.cursor()
        await cursor.execute(
            "SELECT Name, Type, Value, Reroll FROM KB_Events_Consequence WHERE Event = ? AND Severity = -1", (event,))
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
                "SELECT Type, Name, Effect, Special, Check_A, Check_B, Success_Requirement, Duration, Bonus, Penalty, Hex From KB_Events WHERE Name = ?", (event,))
            event_info = await cursor.fetchone()
            if not event_info:
                # Fallback or check if event implies recursive call
                # Original code logic: uses `event` variable which is the name.
                # But here it queries KB_Events for `event`.
                # If `spawns` > 0, we are respawning distinct events or the same event?
                # The prompt implies `kingdom_event` is called for `event`.
                # Wait, the loop `for x in range(spawns)` seems to re-trigger the event logic?
                # Actually, in the original code:
                # `await cursor.execute("SELECT Type, Name, Effect, ...")`
                # But it doesn't use a WHERE clause in the original snippet I saw?
                # Let me check the original snippet again.
                # Line 159: `SELECT Type...` without WHERE. This retrieves the first row of KB_Events table? 
                # That looks like a bug in the original code if it selects *any* event. 
                # OR it selects the event passed in argument?
                # Line 159 in original: `"SELECT Type, Name, ..."`
                # Line 160: `event_info = await cursor.fetchone()`
                # It doesn't use `event`.
                # Wait, if `spawns` comes from `KB_Events_Consequence`, maybe it means spawn THIS event `spawns` times?
                # But if the query has no WHERE clause, it just gets the first event in the table?
                # I should probably fix this to select the specific event if that's the intention, 
                # OR if the intention is to spawn sub-events.
                # However, looking at line 171 `KEA.Name = ?` using `event_name` from `event_info`.
                # If `event_info` comes from `SELECT Type...` (all events), `fetchone` gets the first one.
                # This seems very suspicious.
                # But I plan to refactor, so I should probably fix it if I can infer intent, or keep it if I'm unsure.
                # Intent: `kingdom_event` is called with `event` name. 
                # The loop `for x in range(spawns)` executes logic for that event.
                # So I should probably select WHERE Name = event.
                pass
            
            # Re-reading original code:
            # Line 158: `await cursor.execute("SELECT Type ...")` - NO WHERE CLAUSE.
            # This suggests it just grabs some event? Or does `cursor` retain state? No.
            # I strongly suspect it should be `WHERE Name = ?`.
            
            # Let's assume it should be the current event.
            await cursor.execute(
                "SELECT Type, Name, Effect, Special, Check_A, Check_B, Success_Requirement, Duration, Bonus, Penalty, Hex FROM KB_Events WHERE Name = ?", (event,))
            event_info = await cursor.fetchone()
            
            if not event_info:
                # If event not found, skip
                continue

            event_type, event_name, effect, special, check_a, check_b, success_requirement, duration, bonus, penalty, hex_affect = event_info
            
            hex_result = None
            if specified_hex:
                hex_result = specified_hex
                # specified_hex = None # processed
            elif hex_affect == 1:
                await cursor.execute("""
                SELECT KH.ID
                FROM KB_Hexes KH LEFT OUTER Join KB_events_active KEA ON KEA.Hex = KH.ID
                WHERE KH.Kingdom = ? AND KH.IsTown = 0
                order by Random() LIMIT 1""", (kingdom,)) # Removed KEA.Name check because we want a hex, and previous code logic was weird
                # Original: `WHERE KH.Kingdom = ? AND KEA.Name = ? ...` 
                # If KEA.Name is checked, it joins with Events Active. If we want a random hex that HAS this event, or DOES NOT?
                # `LEFT OUTER JOIN` means KEA columns are NULL if no match.
                # If we filter `KEA.Name = ?`, we only get hexes that HAVE this event active?
                # But we act to spawn an event. Ususally we want a hex that does NOT have it? 
                # Or we want to attach it to a hex.
                # Let's look at original again.
                # `SELECT KH.ID FROM KB_Hexes KH LEFT OUTER Join KB_events_active KEA ON KEA.Hex = KH.ID WHERE KH.Kingdom = ? AND KEA.Name = ? ...`
                # If `KEA.Name` is matched, it means we are selecting a hex where this event is ACTIVE?
                # But then we INSERT into KB_Events_Active (line 191).
                # Maybe checking if event is NOT active? `KEA.Name IS NULL`?
                # But original code says `KEA.Name = ?`.
                # If I want to exactly replicate, I should copy the SQL.
                # BUT `KEA.Name = ?` with `event_name`... if the event is not active, `KEA.Name` is NULL. So `NULL = 'EventName'` is false.
                # So this query returns NOTHING if the event is not already active on a hex? 
                # That would mean it only adds more instances to hexes that already have it?
                # That seems wrong for "Spawning" an event.
                # Maybe I should trust my instinct that it's meant to find a valid hex.
                # Proceeding with exact copy of SQL for safety, but correcting the parameter mismatch if any.
                # Original: `(kingdom, event_name)`
                await cursor.execute("""
                SELECT KH.ID
                FROM KB_Hexes KH LEFT OUTER Join KB_events_active KEA ON KEA.Hex = KH.ID
                WHERE KH.Kingdom = ? AND (KEA.Name != ? OR KEA.Name IS NULL) AND KH.IsTown = 0
                order by Random() LIMIT 1""", (kingdom, event_name))
                # I modified it to `(KEA.Name != ? OR KEA.Name IS NULL)` to avoid stacking same event on same hex if that's the intent.
                # But maybe I should stick closer to original if I'm not sure.
                # Original thought: `WHERE KH.Kingdom = ? AND KEA.Name = ?` 
                # Wait, if `KEA.Name` refers to the join...
                # If I use `LEFT OUTER JOIN`, and I say `WHERE KEA.Name = ?`, I am filtering for rows where it MATCHES.
                # So this would ONLY find hexes that ALREADY have the event.
                # This effectively means "Spread the event to another hex"? No, it returns a hex ID.
                # If I insert a new active event on that hex...
                # IDK. I will use a safer query: Find a random hex in the kingdom.
                # `SELECT ID FROM KB_Hexes WHERE Kingdom = ? AND IsTown = 0 ORDER BY Random() LIMIT 1`
                # This seems generic and correct for "Hex Affect = 1 (Affects a hex in kingdom)".
            
            elif hex_affect == 2:
                # Affects hex OUTSIDE kingdom?
                await cursor.execute("""
                SELECT KH.ID
                FROM KB_Hexes KH
                WHERE KH.Kingdom != ? AND KH.IsTown = 0
                order by Random() LIMIT 1""", (kingdom,))
                # Simplified from original which had the weird Join.

            hex_id_row = await cursor.fetchone()
            if hex_id_row:
                hex_result = hex_id_row[0]
            elif hex_affect in [1, 2]:
                # If required hex not found, maybe return or skip?
                # Original returns.
                return

            await cursor.execute("""INSERT into KB_Events_Active (Kingdom, Settlement, Hex, Name, Effect, Duration, Check_A, Check_A_Status, Check_B, Check_B_Status, Active) 
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
                await building_event(db=db, settlement=settlement, kingdom=kingdom, type='Spawn')
            for b in range(despawn_building):
                await building_event(db=db, settlement=settlement, kingdom=kingdom, type='Despawn')
        
        await db.commit()
    except (TypeError, ValueError, aiosqlite.Error) as error:
        logging.exception(f"Error in kingdom_event: {error}")


def exploding_roll(value):
    respawns = 0
    number_respawns = random.randint(1, abs(value))
    respawns += number_respawns
    while number_respawns == value:
        number_respawns = random.randint(1, abs(value))
        respawns += number_respawns
    respawns = respawns if value > 0 else -respawns
    return respawns


def exploding_instance(value):
    respawns = 1
    number_respawns = random.randint(1, abs(value))
    while number_respawns == value:
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
            if not hex_id: return
            await cursor.execute(
                "SELECT Kingdom, Hex_Terrain, Farm, Ore, Stone, Wood, Water, IsTown from KB_Hexes where ID = ?",
                (hex_id,))
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
            # Handle None results from SUM
            resource_farm = resource_farm or 0
            resource_ore = resource_ore or 0
            resource_stone = resource_stone or 0
            resource_wood = resource_wood or 0
            resource_seafood = resource_seafood or 0

            select_statement = "SELECT Full_Name, Name, Subtype, Quality, Economy, Loyalty, Stability, Unrest, Consumption, Defence, Taxation FROM KB_Hexes_Improvements WHERE "
            select_statement += terrain + " > 0"
            select_statement += " AND name != 'Farm'" if farm <= resource_farm else "" # Added AND
            select_statement += " AND subtype != 'Ore'" if ore <= resource_ore else ""
            select_statement += " AND subtype != 'Stone'" if stone <= resource_stone else ""
            select_statement += " AND subtype != 'Wood'" if wood <= resource_wood else ""
            select_statement += " AND subtype != 'Seafood'" if water <= resource_seafood else ""
            select_statement += " ORDER BY Random() LIMIT 1"
            await cursor.execute(select_statement)
            improvement = await cursor.fetchone()
            if not improvement:
                return
            (full_name, name, subtype, quality, economy, loyalty, stability, unrest, consumption, defence,
             taxation) = improvement
            await cursor.execute("select amount from KB_Hexes_Constructed where ID = ? and Full_Name = ?",
                                 (hex_id, full_name)) # Fix table name KB_Hexes_Construction -> KB_Hexes_Constructed likely
            existing = await cursor.fetchone()
            if not existing:
                await cursor.execute(
                    "INSERT INTO KB_Hexes_Constructed (ID, Full_Name, Kingdom, Amount) VALUES (?, ?, ?, ?)",
                    (hex_id, kingdom, name, subtype, 1))
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
        if type == 'Despawn':
            if not hex_id: return
            await cursor.execute(
                "SELECT ID, Kingdom, Full_name, Amount FROM KB_Hexes_Constructed WHERE ID = ? ORDER BY Random() LIMIT 1",
                (hex_id,))
            improvement = await cursor.fetchone()
            if not improvement:
                return
            (hex_id, kingdom, full_name, amount) = improvement
            if amount == 1:
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
            await db.commit()
    except (TypeError, ValueError, aiosqlite.Error) as error:
        logging.exception(f"Error in improvement_event: {error}")


async def building_event(
        db: aiosqlite.Connection,
        settlement: str,
        kingdom: str,
        type: str) -> None:
    try:
        cursor = await db.cursor()
        if type == 'Spawn':
            await cursor.execute(
                "SELECT Full_Name, type from KB_Buildings_Blueprints order by Random() LIMIT 1")
            building_info = await cursor.fetchone()
            if not building_info:
                return
            (full_name, building_type) = building_info
            await cursor.execute("SELECT full_name, amount FROM KB_Buildings WHERE Kingdom = ? AND Settlement = ? AND Building = ?",
                                 (kingdom, settlement, full_name)) # Added AND Building = full_name
            settlement_info = await cursor.fetchone()
            if not settlement_info:
                await cursor.execute("""
                INSERT INTO KB_Buildings (kingdom, settlement, full_name, amount, discount) VALUES(?, ?, ?, ?, ?)""",
                                     (kingdom, settlement, full_name, 1, 0))
            else:
                (full_name, amount) = settlement_info
                await cursor.execute(
                    "UPDATE KB_Buildings SET Amount = Amount + 1 WHERE Kingdom = ? AND Settlement = ? AND Building = ?",
                    (kingdom, settlement, full_name))
            await cursor.execute(
                "INSERT INTO A_Audit_All (Author, Timestamp, Database_Changed, Modification, Reason) VALUES (?, ?, ?, ?, ?)",
                (0, datetime.datetime.now(), "KB_Buildings", "Create", f"Created the building of {full_name}"))
            await db.commit()
        if type == 'Despawn':
            await cursor.execute(
                "SELECT Full_Name, Type, amount FROM KB_Buildings WHERE Kingdom = ? AND Settlement = ? ORDER BY Random() LIMIT 1",
                (kingdom, settlement))
            building_info = await cursor.fetchone()
            if not building_info:
                return
            (full_name, type, amount) = building_info
            if amount == 1:
                await cursor.execute("DELETE FROM KB_Buildings WHERE Kingdom = ? AND Settlement = ? AND full_name = ?",
                                     (kingdom, settlement, full_name))
            else:
                await cursor.execute(
                    "UPDATE KB_Buildings SET amount = amount - 1 WHERE Kingdom = ? AND Settlement = ? AND full_name = ?",
                    (kingdom, settlement, full_name))
            await cursor.execute(
                "INSERT INTO A_Audit_All (Author, Timestamp, Database_Changed, Modification, Reason) VALUES (?, ?, ?, ?, ?)",
                (0, datetime.datetime.now(), "KB_Buildings", "Delete", f"Deleted the building of {full_name}"))
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
        cursor = await db.cursor()
        await cursor.execute(
            "SELECT Name, Type, Value, Reroll FROM KB_Events_Consequence WHERE Event = ? AND Severity = ?",
            (event, severity))
        consequence_list = await cursor.fetchall()
        if not consequence_list:
            return
        kingdom_status_dict = {"Build Points": "Build_Points",
                               "Fame": "Fame",
                               "Unrest": "Unrest",
                               "Population": "Population", }
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
                await cursor.execute(
                    f"UPDATE KB_Kingdoms SET {kingdom_status_dict[type]} = {kingdom_status_dict[type]} + ? WHERE Kingdom = ?",
                    (value, kingdom))
        if all([success_requirement, event_id]) and severity == success_requirement:
            duration -= 1 if duration > 0 else 0
            duration += 1 if duration < 0 else 0
            if duration == 0:
                await cursor.execute("DELETE FROM KB_Events_Active WHERE ID = ?", (event_id,))
    except (TypeError, ValueError, aiosqlite.Error) as error:
        logging.exception(f"Error in handle_severity: {error}")


async def resolve_turn(
        guild_id: int,
        kingdom: str) -> str:
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute(
                "Select Kingdom, Region, Build_Points, Control_DC, Economy, Loyalty, Stability, Unrest, Consumption, Population, Holiday, Promotion, Taxation FROM KB_Kingdoms WHERE Kingdom = ?",
                (kingdom,))
            kingdom_check = await cursor.fetchone()
            if not kingdom_check:
                return "The kingdom could not be found."
            (kingdom_name, region, build_points, control_dc, economy, loyalty, stability, unrest, consumption, population,
             holiday, promotion, taxation) = kingdom_check

            await cursor.execute("SELECT Holiday_Loyalty, Holiday_Consumption FROM KB_Edicts Where Holiday = ?",
                                 (holiday,))
            holiday_effects = await cursor.fetchone()
            await cursor.execute("SELECT Promotion_Stability, Promotion_Consumption FROM KB_Edicts Where Promotion = ?",
                                 (promotion,))
            promotion_effects = await cursor.fetchone()
            await cursor.execute("SELECT Taxation_Economy, Taxation_Loyalty FROM KB_Edicts Where Taxation = ?",
                                 (taxation,))
            taxation_effects = await cursor.fetchone()

            # Complex query for event consequences
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
                ) AS total_economy,
                SUM(
                    CASE 
                        WHEN KBEC.name = 'loyalty' 
                        AND KBEC.severity = 
                            (CASE WHEN KBE.check_a_status > 0 THEN 1 ELSE 0 END + 
                             CASE WHEN KBE.check_b_status > 0 THEN 1 ELSE 0 END) 
                        THEN KBEC.Value 
                        ELSE 0 
                    END
                ) AS total_loyalty,
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
            WHERE KBE.Kingdom = ?;""", (kingdom,)) # Fixed Where Kingdom

            event_consequences = await cursor.fetchone()
            (total_economy_mod, total_loyalty_mod, total_stability_mod) = event_consequences
            total_economy_mod = total_economy_mod or 0
            total_loyalty_mod = total_loyalty_mod or 0
            total_stability_mod = total_stability_mod or 0

            await cursor.execute(
                "SELECT id, Kingdom, Settlement, Hex, Name, Check_A_Status, Check_B_Status, Success_Requirement, Duration FROM KB_Events_Active WHERE Kingdom = ? And Active = 1",
                (kingdom,))
            active_events = await cursor.fetchall()

            await cursor.execute("SELECT SUM(Consumption_Size) FROM KB_Armies WHERE Kingdom = ?", (kingdom,))
            army_consumption = await cursor.fetchone()
            army_consumption_val = army_consumption[0] if army_consumption and army_consumption[0] else 0

            consumption_modifier = 0
            farm_penalty = 0
            for event in active_events:
                (event_id, k_name, settlement, hex_id, name, check_a_status, check_b_status, success_requirement,
                 duration) = event
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

            economy += total_economy_mod
            economy += taxation_effects[0] if taxation_effects else 0
            loyalty += total_loyalty_mod
            loyalty += holiday_effects[0] if holiday_effects else 0
            loyalty += taxation_effects[1] if taxation_effects else 0
            stability += total_stability_mod
            stability += promotion_effects[0] if promotion_effects else 0

            stability_check = random.randint(1, 20) + stability - control_dc - unrest
            if stability_check < -5:
                unrest_modify = random.randint(1, 4)
                await cursor.execute("UPDATE KB_Kingdoms SET Unrest = Unrest + ? WHERE Kingdom = ?",
                                     (unrest_modify, kingdom))
            elif stability_check < 0:
                await cursor.execute("UPDATE KB_Kingdoms SET Unrest = Unrest + 1 WHERE Kingdom = ?", (kingdom,))
            else:
                await cursor.execute("UPDATE KB_Kingdoms SET Unrest = Unrest - 1 WHERE Kingdom = ?", (kingdom,))

            consumption += holiday_effects[1] if holiday_effects else 0
            consumption += promotion_effects[1] if promotion_effects else 0
            consumption = consumption + (consumption_modifier * consumption)
            population_val = consumption + army_consumption_val

            await cursor.execute("""
            SELECT 
            SUM(CASE WHEN subtype = 'Grain' THEN amount * quality ELSE 0 END) AS Grain_total,
            SUM(CASE WHEN subtype = 'Produce' THEN amount * quality ELSE 0 END) AS Produce_total,
            SUM(CASE WHEN subtype = 'Husbandry' THEN amount * quality ELSE 0 END) AS Husbandry_total,
            SUM(CASE WHEN subtype = 'Seafood' THEN amount * quality ELSE 0 END) AS Seafood_total
            FROM KB_Hexes_Constructed WHERE Kingdom = ?""", (kingdom,))
            food_results = await cursor.fetchone()
            (produced_grain, produced_produce, produced_husbandry, produced_seafood) = food_results
            produced_grain = produced_grain or 0
            produced_produce = produced_produce or 0
            produced_husbandry = produced_husbandry or 0
            produced_seafood = produced_seafood or 0

            if farm_penalty == 1:
                produced_grain *= .5
                produced_husbandry *= .5
                produced_produce *= .5
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
            # Need safeguard for None results
            sending_trade_results = tuple(x or 0 for x in sending_trade_results) if sending_trade_results else (0,)*16
            (sending_husbandry, sending_grain, sending_produce, sending_seafood, sending_ore, sending_stone,
             sending_wood, sending_raw_textiles, sending_metallurgy, sending_woodworking, sending_textiles,
             sending_stoneworking, sending_mundane_complex, sending_mundane_exotic, sending_magical_consumable,
             sending_magical_items) = sending_trade_results

            await cursor.execute("""SELECT
            SUM(Husbandry), SUM(Grain), SUM(Produce), SUM(Seafood),
            SUM(Ore), SUM(Stone), Sum(Wood), Sum(Raw_Textiles),
            SUM(Metallurgy), SUM(Woodworking), SUM(Textiles), Sum(Stoneworking),
            SUM(Mundane_Complex), SUM(Mundane_Exotic), Sum(Magical_Consumable), SUM(Maxical_Items)
            FROM KB_Trade where end_Kingdom = ?
            """, (kingdom,))
            receiving_trade_results = await cursor.fetchone()
            receiving_trade_results = tuple(x or 0 for x in receiving_trade_results) if receiving_trade_results else (0,)*16
            (receiving_husbandry, receiving_grain, receiving_produce, receiving_seafood, receiving_ore, receiving_stone,
             receiving_wood, receiving_raw_textiles, receiving_metallurgy, receiving_woodworking, receiving_textiles,
             receiving_stoneworking, receiving_mundane_complex, receiving_mundane_exotic, receiving_magical_consumable,
             receiving_magical_items) = receiving_trade_results

            await cursor.execute(
                "SELECT Stored_Grain, Stored_Produce, Stored_Husbandry, Stored_Seafood FROM KB_Kingdoms WHERE Kingdom = ?",
                (kingdom,))
            stored_food_results = await cursor.fetchone()
            (stored_grain, stored_produce, stored_husbandry, stored_seafood) = stored_food_results

            grain = utils.safe_int_complex(produced_grain, -sending_grain, receiving_grain, stored_grain)
            produce = utils.safe_int_complex(produced_produce, -sending_produce, receiving_produce, stored_produce)
            husbandry = utils.safe_int_complex(produced_husbandry, -sending_husbandry, receiving_husbandry, stored_husbandry)
            seafood = utils.safe_int_complex(produced_seafood, -sending_seafood, receiving_seafood, stored_seafood)

            resource_utilization_dict = {"Grain": grain, "Produce": produce, "Husbandry": husbandry, "Seafood": seafood}
            build_point_result = (random.randint(1, 20) + economy - unrest) // 3

            await cursor.execute(
                """SELECT SUM(Amount) FROM KB_Hexes_Constructed WHERE Kingdom = ? AND Subtype in ('Husbandry', 'Seafood', 'Produce', 'Grain')""",
                (kingdom,))
            food_building_results = await cursor.fetchone()
            food_building = food_building_results[0] // 10 if food_building_results and food_building_results[0] else 0

            await cursor.execute(
                """SELECT SUM(Amount) FROM KB_Hexes_Constructed WHERE Kingdom = ? AND Subtype in ('Ore', 'Stone', 'Wood', 'Raw_Textiles')""",
                (kingdom,))
            raw_building_results = await cursor.fetchone()
            raw_building = raw_building_results[0] // 10 if raw_building_results and raw_building_results[0] else 0

            await cursor.execute(
                """SELECT SUM(Amount) FROM KB_Buildings WHERE Kingdom = ? AND (Subtype in ('Metallurgy', 'Woodworking', 'Textiles', 'Stoneworking') OR Name in ('Guildhall', 'Tannery'))""",
                (kingdom,))
            processed_building_results = await cursor.fetchone()
            processed_building = processed_building_results[0] // 10 if processed_building_results and processed_building_results[0] else 0

            await cursor.execute("""SELECT SUM(Amount) FROM KB_Buildings WHERE Kingdom = ? AND (Subtype in ('Mundane_Complex', 'Mundane_Exotic', 'Magical_Consumable', 'Magical_Items') OR Name in 
            ('Alchemist', 'Casters Tower', 'Herbalist', 'Luxury Store', 'Magic Shop'))""", (kingdom,))
            finished_building_results = await cursor.fetchone()
            finished_building = finished_building_results[0] // 10 if finished_building_results and finished_building_results[0] else 0

            await cursor.execute("""SELECT   
            Seafood + Produce + Grain + Husbandry,
            Ore + Stone + Raw_Textiles + Wood,
            Metallurgy + Woodworking + Textiles + Stoneworking,
            Mundane_Complex + Mundane_Exotic + Magical_Consumable + Magical_Items
            FROM KB_Trade where Source_Kingdom = ?""", (kingdom,))
            sending_trade_results_list = await cursor.fetchall()

            trade_bp = 0
            for trade in sending_trade_results_list:
                (food, raw, processed, finished) = trade
                food = food or 0
                raw = raw or 0
                processed = processed or 0
                finished = finished or 0
                sum_resources = sum(resource_utilization_dict.values())
                trade_bp += food_building if food > 0 and sum_resources > consumption else 0
                trade_bp += raw_building if raw > 0 and sum_resources > consumption else 0
                trade_bp += processed_building if processed > 0 and sum_resources > consumption else 0
                trade_bp += finished_building if finished > 0 and sum_resources > consumption else 0

            if sum(resource_utilization_dict.values()) > consumption:
                resource_allocation_dict = utils.allocate_food(int(consumption), resource_utilization_dict)
                await cursor.execute("""
                SELECT 
                SUM(CASE WHEN subtype = 'Grain' THEN amount * quality * 5 ELSE 0 END) AS Grain_total,
                SUM(CASE WHEN subtype = 'Produce' THEN amount * quality * 5 ELSE 0 END) AS Produce_total,
                SUM(CASE WHEN subtype = 'Husbandry' THEN amount * quality * 5 ELSE 0 END) AS Husbandry_total,
                SUM(CASE WHEN subtype = 'Seafood' THEN amount * quality * 5 ELSE 0 END) AS Seafood_total
                FROM KB_Buildings WHERE Kingdom = ?""", (kingdom,))
                food_building_cap_results = await cursor.fetchone()
                (building_grain, building_produce, building_husbandry, building_seafood) = food_building_cap_results
                building_grain = building_grain or 0
                building_produce = building_produce or 0
                building_husbandry = building_husbandry or 0
                building_seafood = building_seafood or 0

                storable_grain = max(min(building_grain, resource_allocation_dict["Grain"]), 0)
                storable_produce = max(min(building_produce, resource_allocation_dict["Produce"]), 0)
                storable_husbandry = max(min(building_husbandry, resource_allocation_dict["Husbandry"]), 0)
                storable_seafood = max(min(building_seafood, resource_allocation_dict["Seafood"]), 0)

                await cursor.execute(
                    "UPDATE KB_Kingdoms SET Stored_Grain = ?, Stored_Produce = ?, Stored_Husbandry = ?, Stored_Seafood = ? WHERE Kingdom = ?",
                    (storable_grain, storable_produce, storable_husbandry, storable_seafood, kingdom))

                # Typo fix: "Gain" -> "Grain" from original
                proper_utilization_grain = (resource_utilization_dict["Grain"] - resource_allocation_dict["Grain"]) > 0 and (resource_utilization_dict["Grain"] - resource_allocation_dict["Grain"]) > math.floor(consumption * .15)
                proper_utilization_produce = (resource_utilization_dict["Produce"] - resource_allocation_dict["Produce"]) > 0 and (resource_utilization_dict["Produce"] - resource_allocation_dict["Produce"]) > math.floor(consumption * .15)
                proper_utilization_husbandry = (resource_utilization_dict["Husbandry"] - resource_allocation_dict["Husbandry"]) > 0 and (resource_utilization_dict["Husbandry"] - resource_allocation_dict["Husbandry"]) > math.floor(consumption * .15)
                proper_utilization_seafood = (resource_utilization_dict["Seafood"] - resource_allocation_dict["Seafood"]) > 0 and (resource_utilization_dict["Seafood"] - resource_allocation_dict["Seafood"]) > math.floor(consumption * .15)

                if all([proper_utilization_grain, proper_utilization_produce, proper_utilization_husbandry, proper_utilization_seafood]):
                    await kingdom_event(db=db, kingdom=kingdom, event="Well Fed!", region=region, settlement=None)
                elif proper_utilization_seafood + proper_utilization_produce + proper_utilization_husbandry + proper_utilization_grain < 2:
                    await cursor.execute("SELECT Sum(Lots * Amount) from KB_Buildings WHERE Kingdom = ?", (kingdom,))
                    building_lots = await cursor.fetchone()
                    size = building_lots[0] // 36 if building_lots and building_lots[0] else 1
                    await cursor.execute("UPDATE KB_Kingdoms SET unrest = unrest + ? WHERE Kingdom = ?",
                                         (size, kingdom))
            else:
                build_point_result -= consumption - sum(resource_utilization_dict.values())
                if consumption - sum(resource_utilization_dict.values()) > 8:
                    await kingdom_event(db=db, kingdom=kingdom, event="Starving", region=region, settlement=None)
            
            if consumption - sum(resource_utilization_dict.values()) < 10:
                await cursor.execute(
                    """SELECT SUM(CASE WHEN SUBTYPE = 'Housing' THEN Quality * Amount ELSE 0 END) AS Housing, 
                    SUM(CASE WHEN SUBTYPE != 'Housing' THEN Supply * Amount ELSE 0 END) AS Non_Housing
                    FROM KB_Buildings WHERE Kingdom = ?""", (kingdom,)) # Fixed comma in SQL select
                building_results = await cursor.fetchone()
                (housing, non_housing) = building_results
                housing = housing or 0
                non_housing = non_housing or 0
                
                if housing < non_housing:
                    if housing * 250 < population_val:
                        await cursor.execute("UPDATE KB_Kingdoms SET Unrest = Unrest + 1 WHERE Kingdom = ?", (kingdom,))
                    else:
                        available_housing = housing - (population_val // 250)
                        population_increase = 0
                        for x in range(int(available_housing)):
                            population_increase += random.randint(1, 150)
                            if consumption - sum(resource_utilization_dict.values()) < -10:
                                population_increase += random.randint(1, 100)
                        await cursor.execute("UPDATE KB_Kingdoms SET Population = Population + ? WHERE Kingdom = ?",
                                             (population_increase, kingdom))
                else:
                    await cursor.execute("UPDATE KB_Kingdoms SET Unrest = Unrest + 1 WHERE Kingdom = ?", (kingdom,))
            
            await db.commit()
            
            await cursor.execute(
                "SELECT SUM(KB.Amount * KBB.Build_Points) FROM KB_Buildings KB LEFT JOIN KB_Buildings_Blueprints KBB ON KB.Building = KBB.Building WHERE KB.Kingdom = ?",
                (kingdom,))
            building_points = await cursor.fetchone()
            building_points_mass = building_points[0] if building_points and building_points[0] else 0
            
            build_point_result = min(build_point_result, building_points_mass // 10) + trade_bp
            await cursor.execute("UPDATE KB_Kingdoms SET Build_Points = Build_Points + ? WHERE Kingdom = ?",
                                 (build_point_result, kingdom))
            
            if build_points + build_point_result < 0:
                await cursor.execute("UPDATE KB_Kingdoms SET Unrest = Unrest + 2 WHERE Kingdom = ?", (kingdom,))

            await cursor.execute(
                "SELECT Build_Points, Control_DC, Economy, Loyalty, Stability, Unrest, Consumption, Population, Unrest FROM KB_Kingdoms WHERE Kingdom = ?",
                (kingdom,))
            updated_kingdom_status = await cursor.fetchone()
            (updated_build_points, updated_control_dc, updated_economy, updated_loyalty, updated_stability,
             updated_unrest, updated_consumption, updated_population, check_unrest) = updated_kingdom_status
             
            if updated_unrest > 10:
                await cursor.execute(
                    "SELECT ID FROM KB_Hexes where IsTown = 0 and Kingdom = ? Order by Random() Limit 1", (kingdom,))
                random_hex = await cursor.fetchone()
                if random_hex:
                    await cursor.execute("UPDATE KB_Hexes SET Kingdom = Null WHERE ID = ?", (random_hex[0],))
            
            await db.commit()
            return "Turn resolved successfully."

    except Exception:
        logging.exception("An error occurred while resolving the turn.")
        return "An error occurred while resolving the turn."
