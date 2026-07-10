import logging
import typing
from dataclasses import dataclass, fields

import aiosqlite
import math
from sqlite3 import Row

from google.rpc.error_details_pb2 import ResourceInfo

from core.kingdom import (
    KingdomInfo, TradeInfo, BaseSettlementInfo, BuildingInfo, HexImprovementInfo,
    reroll_dict, SettlementInfo, FoodDataClass, RawMaterialsDataClass, SimpleCraftDataClass, LuxuryCraftDataClass,
    remaining_is_total, distribute_pain, goods_remaining_dict, distribute_consumption, clamp_remaining_to_zero,
    fix_remaining_to_zero, allocate_food
)
from core.utils import safe_int_complex, safe_add


async def handle_settlement_utilization(
        db: aiosqlite.Connection,
        kingdom: str,
        crafted_dataclass: SimpleCraftDataClass,
        luxury_dataclass: LuxuryCraftDataClass
) -> tuple[SimpleCraftDataClass, LuxuryCraftDataClass, int, int, int, int]:
    try:
        cursor = await db.cursor()
        await cursor.execute(
            "SELECT settlement, coalesce(SUM(Lots * Amount), 0) FROM KB_Buildings KB Left join kb_buildings_blueprints kbb on kb.full_name = kbb.full_name WHERE Kingdom = ?",
            (kingdom,)
        )
        settlements = await cursor.fetchall()

        crafted_resource_starvation = 0
        luxury_resource_starvation = 0
        unrest_penalty = 0
        for settlement in settlements:
            (settlement_name, lots) = settlement
            crafted_utilization = lots // 20
            crafted_dataclass.woodworking.remaining -= crafted_utilization
            crafted_dataclass.stoneworking.remaining -= crafted_utilization
            crafted_dataclass.metallurgy.remaining -= crafted_utilization
            crafted_dataclass.textiles.remaining -= crafted_utilization
            unrest_penalty += 1 if any(
                getattr(crafted_dataclass, f.name).remaining < 0
                for f in fields(crafted_dataclass)
            ) else 0
            if 20 <= lots <= 40:
                (luxury_items_dict, base_target, leftover) = distribute_consumption(luxury_dataclass, max(0, (lots - 10) //10))
                luxury_resource_starvation += leftover
            else:
                luxury_dataclass.magical_items.remaining -= 1 * max(0, lots - 10)//10
                luxury_dataclass.luxury.remaining -= 1 * max(0, lots - 10)//10
                leftover = 0
            unrest_penalty += 1 if (
                    any(
                        getattr(luxury_dataclass, f.name).remaining < 0
                        for f in fields(luxury_dataclass)
                    )
                    or leftover > 0
            ) else 0
        crafted_dataclass.woodworking.depletion = abs(crafted_dataclass.woodworking.remaining) if crafted_dataclass.woodworking.remaining < 0 else 0
        crafted_dataclass.stoneworking.depletion = abs(crafted_dataclass.stoneworking.remaining) if crafted_dataclass.stoneworking.remaining < 0 else 0
        crafted_dataclass.metallurgy.depletion = abs(crafted_dataclass.metallurgy.remaining) if crafted_dataclass.metallurgy.remaining < 0 else 0
        crafted_dataclass.textiles.depletion = abs(crafted_dataclass.textiles.remaining) if crafted_dataclass.textiles.remaining < 0 else 0


        crafted_resource_starvation = crafted_dataclass.woodworking.depletion + crafted_dataclass.stoneworking.depletion + crafted_dataclass.metallurgy.depletion +crafted_dataclass.textiles.depletion
        clamp_remaining_to_zero(crafted_dataclass)
        stability_penalty = crafted_resource_starvation // 2
        luxury_dataclass.magical_items.depletion = abs(luxury_dataclass.magical_items.remaining) if luxury_dataclass.magical_items.remaining < 0 else 0
        luxury_dataclass.luxury.depletion = abs(luxury_dataclass.luxury.remaining) if luxury_dataclass.luxury.remaining < 0 else 0
        luxury_resource_starvation += luxury_dataclass.magical_items.depletion + luxury_dataclass.luxury.depletion
        luxury_resource_starvation += luxury_dataclass.luxury.remaining if luxury_dataclass.luxury.remaining < 0 else 0
        clamp_remaining_to_zero(luxury_dataclass)

        return crafted_dataclass, luxury_dataclass, crafted_resource_starvation, stability_penalty, luxury_resource_starvation, unrest_penalty
    except Exception as exception:
        logging.error(exception)
        return crafted_dataclass, luxury_dataclass, 0, 0, 0, 0

async def handle_food(
        db: aiosqlite.Connection,
        kingdom: str,
        food_dataclass: FoodDataClass,
        consumption: int
):
    try:
        cursor = await db.cursor()
        event = None
        await cursor.execute(
            "SELECT settlement, coalesce(SUM(Lots * Amount), 0) FROM KB_Buildings KB Left join kb_buildings_blueprints kbb on kb.full_name = kbb.full_name WHERE Kingdom = ?",
            (kingdom,)
        )

        building_lots = await cursor.fetchall()
        size =0
        if building_lots:
            for building_lot in building_lots:
                size += max(1, (building_lot[1] or 0) // 36)

        unrest_penalty = 0

        available_food = goods_remaining_dict(food_dataclass)

        total_available = sum(available_food.values())

        # =========================
        # STARVATION CASE
        # =========================
        if total_available < consumption:

            event='Starving'

            fix_remaining_to_zero(food_dataclass)

            unrest_penalty += size

            return food_dataclass, unrest_penalty, event

        # =========================
        # NORMAL ALLOCATION
        # =========================
        resource_allocation = allocate_food(
            required=consumption,
            available=available_food
        )

        # Remove consumed food from remaining
        for resource, consumed in resource_allocation.items():
            metric = getattr(food_dataclass, resource)

            metric.remaining = max(
                0,
                metric.remaining - consumed
            )

        # =========================
        # WELL FED / UNREST CHECKS
        # =========================
        threshold = math.floor(consumption * 0.15)

        proper_utilization_count = 0

        for resource in available_food:
            leftover = getattr(food_dataclass, resource).remaining

            if leftover > threshold:
                proper_utilization_count += 1

        if proper_utilization_count == 4:

            event="Well Fed!"


        elif proper_utilization_count < 2:
            unrest_penalty += size / 2

        return food_dataclass, unrest_penalty, event

    except Exception as e:
        logging.exception(f"Exception occurred: {e}")

        return food_dataclass, 0, None



async def fetch_kingdom(
        guild_id: int,
        kingdom: str,
        turn_id: typing.Optional[int]) -> typing.Union[KingdomInfo, None]:
    async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
        cursor = await db.cursor()
        await cursor.execute(
            """SELECT Kingdom, Region, Password, Government, Alignment, Control_DC, Build_Points, Size, Population, Economy, Loyalty, Stability, Fame, Unrest, Consumption, 0, Holiday, Promotion, Taxation, Turn, Heraldry, Host_Channel, Host_Message, Log_Thread FROM kb_Kingdoms WHERE Kingdom = ?""",
            (kingdom,))
        kingdom_info = await cursor.fetchone()
        if kingdom_info is None: return None
        (kingdom, region, password, government, alignment, control_dc, build_points, size, population, economy, loyalty, stability, fame, unrest, consumption, taxation, edict_holiday, edict_promotion, edict_taxation, turn, heraldry, host_channel, host_message, log_thread) = kingdom_info
        #Kingdom Values
        turn_id = turn_id if turn_id else turn
        kingdominfo = KingdomInfo(
            kingdom=kingdom,
            region=region,
            password=password,
            government=government,
            alignment=alignment,
            build_points=build_points,
            population=population,
            turn=turn_id,
            heraldry=heraldry,
            host_channel=host_channel,
            host_message=host_message,
            log_thread=log_thread
        )
        kingdominfo.control_dc.base = control_dc
        kingdominfo.size.base = size
        kingdominfo.economy.base = economy
        kingdominfo.loyalty.base = loyalty
        kingdominfo.stability.base = stability
        kingdominfo.fame.base = fame
        kingdominfo.unrest.base = unrest
        kingdominfo.consumption.base = consumption

        #Custom Kingdom Values
        await cursor.execute("SELECT Control_DC, Economy, Loyalty, Stability, Fame, Unrest, Consumption from KB_Kingdoms_Custom where Kingdom = ?", (kingdom_info[0],))
        kingdom_custom = await cursor.fetchone()
        (control_dc, economy, loyalty, stability, fame, unrest, consumption) = kingdom_custom
        kingdominfo.control_dc.custom_value = control_dc
        kingdominfo.economy.custom_value = economy
        kingdominfo.loyalty.custom_value = loyalty
        kingdominfo.stability.custom_value = stability
        kingdominfo.fame.custom_value = fame
        kingdominfo.unrest.custom_value = unrest
        kingdominfo.consumption.custom_value = consumption

        #Leadership
        await cursor.execute(
            "SELECT sum(economy), sum(loyalty), sum(Stability), sum(unrest) from kb_leadership where Kingdom = ?",
            (kingdom_info[0],))
        leadership = await cursor.fetchone()
        (economy, loyalty, stability, unrest) = leadership
        kingdominfo.economy.leadership_custom_value = economy
        kingdominfo.loyalty.leadership_custom_value = loyalty
        kingdominfo.stability.leadership_custom_value = stability
        kingdominfo.unrest.leadership_custom_value = unrest

        cursor = await db.cursor()
        await cursor.execute("""
        SELECT Settlement,
        SUM(KB.Amount * KBB.Lots) as lots, 
        SUM(KB.Amount * KBB.Economy) as economy, 
        SUM(KB.Amount * KBB.Loyalty) as Loyalty, 
        SUM(KB.Amount * KBB.Stability) as Stability, 
        SUM(KB.Amount * KBB.Fame) as Fame, 
        SUM(KB.Amount * KBB.unrest) as Unrest
        FROM KB_Buildings KB
        JOIN KB_Buildings_Blueprints KBB ON KB.Full_name = KBB.Full_Name
        WHERE KB.Kingdom = ?
        GROUP BY Settlement
        """, (kingdom,))
        building_results = await cursor.fetchall()
        for result in building_results:
            (settlement, lots, economy, loyalty, stability, fame, unrest) = result
            kingdominfo.control_dc.building_value = kingdominfo.control_dc.building_value + lots // 36 + 1
            kingdominfo.economy.building_value = kingdominfo.economy.building_value + economy
            kingdominfo.loyalty.building_value = kingdominfo.loyalty.building_value + loyalty
            kingdominfo.stability.building_value = kingdominfo.stability.building_value + stability
            kingdominfo.fame.building_value = kingdominfo.fame.building_value + fame
            kingdominfo.unrest.building_value = unrest + kingdominfo.unrest.building_value

        #Hex Info
        await cursor.execute("""
        SELECT 
        coalesce(SUM(KB.Amount), 0),
        coalesce(SUM(KB.Amount * KBB.Economy), 0) as economy, 
        coalesce(SUM(KB.Amount * KBB.Loyalty), 0) as Loyalty, 
        coalesce(SUM(KB.Amount * KBB.Stability), 0) as Stability, 
        coalesce(SUM(KB.Amount * KBB.Unrest), 0) as Unrest, 
        coalesce(SUM(KB.Amount * KBB.Consumption), 0) as Consumption, 
        coalesce(SUM(KB.Amount * KBB.Taxation), 0) as Taxation 
        FROM kb_hexes_constructed KB
        JOIN kb_hexes_improvements KBB ON KB.Full_name = KBB.Full_Name
        WHERE KB.Kingdom = ?
        """, (kingdom,))
        hex_results = await cursor.fetchone()
        (amount, economy, loyalty, stability, unrest, consumption, taxation) = hex_results
        kingdominfo.size.hex_value = amount
        kingdominfo.economy.hex_value = economy
        kingdominfo.loyalty.hex_value = loyalty
        kingdominfo.stability.hex_value = stability
        kingdominfo.unrest.hex_value = unrest
        kingdominfo.consumption.hex_value = consumption
        kingdominfo.taxation.hex_value = taxation
        await cursor.execute("""Select count(*) from kb_hexes where kingdom = ?""", (kingdom,))
        hex_size_results = await cursor.fetchone()
        kingdominfo.size.hex_value = hex_size_results[0]

        await cursor.execute("Select Holidays_Loyalty, Holidays_Consumption from KB_Edicts where Severity = ?",
                             (edict_holiday,))
        holiday_results = await cursor.fetchone()
        (holiday_loyalty, holiday_consumption) = holiday_results
        await cursor.execute("Select Promotion_stability, Promotion_Consumption from kb_edicts where Severity = ?",
                             (edict_promotion,))
        promotion_results = await cursor.fetchone()
        (promotion_stability, promotion_consumption) = promotion_results
        await cursor.execute("SELECT Taxation_economy, Taxation_Loyalty from kb_edicts where severity = ?",
                             (edict_taxation,))
        taxation_results = await cursor.fetchone()
        (taxation_economy, taxation_loyalty) = taxation_results
        kingdominfo.loyalty.edict = holiday_loyalty + taxation_loyalty
        kingdominfo.consumption.edict = holiday_consumption + promotion_consumption
        kingdominfo.stability.edict = promotion_stability
        kingdominfo.economy.edict = taxation_economy
        await cursor.execute("SELECT Coalesce(SUM(Consumption_Size), 0) FROM KB_Armies WHERE Kingdom = ?", (kingdom,))
        army_consumption = await cursor.fetchone()
        kingdominfo.consumption.army = army_consumption[0] if army_consumption else 0
        if turn_id:
            await cursor.execute("Select Economy, Loyalty, Stability from KB_Turn_Penalty_Kingdom where TurnID = ? and Kingdom = ?", (turn_id,kingdom))
            turn_penalty_results = await cursor.fetchone()
            if turn_penalty_results:
                kingdominfo.economy.penalty = turn_penalty_results[0]
                kingdominfo.loyalty.penalty = turn_penalty_results[1]
                kingdominfo.stability.penalty = turn_penalty_results[2]
        return kingdominfo




async def fetch_kingdom_event_list(
        db: aiosqlite.Connection,
        kingdom: str,
        offset: int = 0,
        limit: int = 1000
) -> typing.Union[typing.Iterable[Row], None]:
    try:
        cursor = await db.cursor()
        await cursor.execute("""
        SELECT
        ID, Type, Kingdom, Settlement, Hex, Name,
        Effect, Duration, 
        Check_A, Check_A_Status,
        Check_B, Check_B_Status,
        case when check_a_status  = 1 and check_b_status = 1 then 2 when check_a_status = 1 or check_b_status = 1 then 1 else 0 end as Severity
        FROM KB_Events_Active WHERE Kingdom = ? and Active = 1
        Order by Name, Severity
        LIMIT ? OFFSET ?
        """, (kingdom, limit, offset))
        event_results = await cursor.fetchall()
        return event_results
    except Exception as e:
        logging.exception(f"Error fetching kingdom events: {e}")
        return None


async def fetch_kingdom_army_state(
        db: aiosqlite.Connection,
        kingdom: str) -> typing.Union[tuple[int, str], None]:
    try:
        cursor = await db.cursor()
        await cursor.execute("""
        SELECT Army_Name, Consumption_Size
        FROM KB_Armies 
        Where Kingdom = ?
        """, (kingdom,))
        army_results = await cursor.fetchall()
        total_army_cost = 0
        army_list = []
        for army in army_results:
            (army_name, consumption_size) = army
            total_army_cost += consumption_size
            army_list.append(army_name)
        army_list_str = ', '.join(army_list)
        return total_army_cost, army_list_str
    except Exception as e:
        logging.exception(f"Error fetching army state: {e}")
        return None


async def fetch_kingdom_requirements(
        db: aiosqlite.Connection,
        kingdom: str,
        consumption: int,
        incoming_trade: TradeInfo,
        outgoing_trade: TradeInfo,
        building_info: TradeInfo,
        hex_info: TradeInfo) -> typing.Union[TradeInfo, None]:
    cursor = await db.cursor()
    return 'kys FIX ME'



async def fetch_kingdom_trade(
        db: aiosqlite.Connection,
        source_kingdom: str = None,
        end_kingdom: str = None) -> typing.Union[TradeInfo, None]:
    try:
        if source_kingdom is None and end_kingdom is None:
            return None
        sql = """
                SELECT 
                coalesce(SUM(Husbandry), 0), 
                coalesce(SUM(Seafood), 0),
                coalesce(SUM(Grain), 0),
                coalesce(SUM(Produce), 0),
                coalesce(SUM(Ore), 0),
                coalesce(SUM(Wood), 0),
                coalesce(SUM(Stone), 0),
                coalesce(SUM(Raw_textiles), 0),
                coalesce(SUM(Magical_Items), 0),
                coalesce(SUM(luxury), 0)
                FROM KB_Trade """
        if source_kingdom:
            sql += "WHERE Source_Kingdom = ?"
        else:
            sql += "WHERE End_Kingdom = ?"
        cursor = await db.cursor()
        print("executing sql", sql)
        if source_kingdom is not None:
            await cursor.execute(sql, (source_kingdom,))
        else:
            await cursor.execute(sql, (end_kingdom,))
        results = await cursor.fetchall()
        (husbandry, seafood, grain, produce, ore, wood, stone, raw_textiles,
         magical_items, luxury) = results[0] if results else (0,0,0,0,0,0,0,0,0,0)

        husbandry = husbandry if husbandry else 0
        seafood = seafood if seafood else 0
        grain = grain if grain else 0
        produce = produce if produce else 0
        ore = ore if ore else 0
        wood = wood if wood else 0
        stone = stone if stone else 0
        raw_textiles = raw_textiles if raw_textiles else 0
        magical_items = magical_items if magical_items else 0
        luxury = luxury if luxury else 0
        trade_summary = TradeInfo(
            husbandry=husbandry,
            seafood=seafood,
            grain=grain,
            produce=produce,
            ore=ore,
            wood=wood,
            stone=stone,
            raw_textiles=raw_textiles,
            magical_items=magical_items,
            luxury=luxury)
        return trade_summary
    except Exception as e:
        logging.exception(f"Error fetching kingdom trade: {e}")
        return None


async def fetch_kingdom_hex_output(
        db: aiosqlite.Connection,
        kingdom: str) -> typing.Union[TradeInfo, None]:
    try:
        cursor = await db.cursor()
        await cursor.execute("""
        SELECT 
        SUM(case when KHC.subtype = 'Husbandry' then KHC.amount * KHI.quality else 0 end) as Husbandry,
        SUM(case when KHC.subtype = 'Seafood' then KHC.amount * KHI.quality else 0 end) as Seafood,
        SUM(case when KHC.subtype = 'Grain' then KHC.amount * KHI.quality else 0 end) as Grain,
        SUM(case when KHC.subtype = 'Produce' then KHC.amount * KHI.quality else 0 end) as Produce,
        SUM(case when KHC.subtype = 'Ore' then KHC.amount * KHI.quality else 0 end) as Ore,
        SUM(case when KHC.subtype = 'Wood' then KHC.amount * KHI.quality else 0 end) as Wood,
        SUM(case when KHC.subtype = 'Stone' then KHC.amount * KHI.quality else 0 end) as Stone,
        SUM(case when KHC.subtype = 'Raw_textiles' then KHC.amount * KHI.quality else 0 end) as Raw_Textiles
        FROM KB_Hexes_Constructed KHC
        LEFT JOIN KB_Hexes_Improvements KHI ON KHC.Full_Name = KHI.Full_Name
        WHERE KHC.Kingdom = ?
        """, (kingdom,))
        results = await cursor.fetchall()

        if results:
             (husbandry, seafood, grain, produce, ore, wood, stone, raw_textiles) = results[0]
        else:
             (husbandry, seafood, grain, produce, ore, wood, stone, raw_textiles) = (0,0,0,0,0,0,0,0)

        husbandry = husbandry if husbandry else 0
        seafood = seafood if seafood else 0
        grain = grain if grain else 0
        produce = produce if produce else 0
        ore = ore if ore else 0
        wood = wood if wood else 0
        stone = stone if stone else 0
        raw_textiles = raw_textiles if raw_textiles else 0
        total_output = TradeInfo(
            husbandry=husbandry,
            seafood=seafood,
            grain=grain,
            produce=produce,
            ore=ore,
            wood=wood,
            stone=stone,
            raw_textiles=raw_textiles
        )
        return total_output
    except Exception as e:
        logging.exception(f"Error fetching hex output: {e}")
        return None


async def fetch_kingdom_building_output(
        db: aiosqlite.Connection,
        kingdom: str) -> typing.Union[TradeInfo, None]:
    try:
        cursor = await db.cursor()
        await cursor.execute("""
        SELECT 
        SUM(case when KHC.subtype = 'Stoneworking' then KHC.amount * KHI.quality else 0 end) as Stoneworking,
        SUM(case when KHC.subtype = 'Metallurgy' then KHC.amount * KHI.quality else 0 end) as Metallurgy,
        SUM(case when KHC.subtype = 'Textiles' then KHC.amount * KHI.quality else 0 end) as Textiles,
        SUM(case when KHC.subtype = 'Woodworking' then KHC.amount * KHI.quality else 0 end) as Woodworking,
        SUM(case when KHC.subtype = 'Luxury' then KHC.amount * KHI.quality else 0 end) as luxury,
        SUM(case when KHC.subtype = 'Mundane Exotic' then KHC.amount * KHI.quality else 0 end) as Mundane_Exotic,
        SUM(case when KHC.subtype = 'Magical Consumables' then KHC.amount * KHI.quality else 0 end) as Magical_Consumables,
        SUM(case when KHC.subtype = 'Magical Items' then KHC.amount * KHI.quality else 0 end) as Magical_Items
        FROM KB_Buildings KHC
        LEFT JOIN KB_Buildings_Blueprints KHI ON KHC.Full_Name = KHI.Full_Name
        WHERE KHC.Kingdom = ?
        """, (kingdom,))
        results = await cursor.fetchall()
        if results:
             (stoneworking, metallurgy, textiles, woodworking, luxury, mundane_exotic,
             magical_consumables, magical_items) = results[0]
        else:
             (stoneworking, metallurgy, textiles, woodworking, luxury, mundane_exotic,
             magical_consumables, magical_items) = (0,0,0,0,0,0,0,0)

        stoneworking = stoneworking if stoneworking else 0
        metallurgy = metallurgy if metallurgy else 0
        textiles = textiles if textiles else 0
        woodworking = woodworking if woodworking else 0
        luxury = luxury if luxury else 0
        mundane_exotic = mundane_exotic if mundane_exotic else 0
        magical_consumables = magical_consumables if magical_consumables else 0
        magical_items = magical_items if magical_items else 0
        total_output = TradeInfo(
            stoneworking=stoneworking,
            metallurgy=metallurgy,
            textiles=textiles,
            woodworking=woodworking,
            luxury=luxury,
            mundane_exotic=mundane_exotic,
            magical_consumables=magical_consumables,
            magical_items=magical_items
        )
        return total_output
    except Exception as e:
        logging.exception(f"Error fetching building output: {e}")
        return None


async def fetch_consequence_list(
        db: aiosqlite.Connection,
        event_list: typing.Iterable[Row]) -> typing.Union[str, None]:
    try:
        cursor = await db.cursor()
        old_name = ''
        response = ''
        old_severity = -1
        base_event_list = 0
        max_event_list = 0
        for event, itx in enumerate(event_list):
            (event_id, event_type, kingdom, settlement, hex_v, name,
             effect, duration, check_a, check_a_status,
             check_b, check_b_status, severity) = event
            if len(response) < 800:
                base_event_list = itx
                if event_id != old_name:

                    response += f"**{name}**: {effect} \n"
                    if severity != old_severity:
                        response_tuple = []
                        await cursor.execute(
                            "SELECT Type, Value, Reroll from KB_Events_Consequences WHERE Name = ? AND Severity = ?",
                            (name, severity)) # Fixed missing parameter binding for severity
                        consequence_list = await cursor.fetchall()
                        for consequence in consequence_list:
                            (consequence_type, value, reroll) = consequence
                            reroll_str = reroll_dict.get(reroll, "Unknown")
                            response_tuple.append(f"{consequence_type} {value} {reroll_str}")
                        response += f"**Severity: {severity}, Consequences:** {', '.join(response_tuple)}\n"
                    old_name = name
                    old_severity = severity

                response += "settlement: " + str(settlement) + "\n" if settlement else ""
                response += "hex: " + str(hex_v) + "\n" if hex_v else ""
                response += f"**Check A:** {check_a} {check_a_status}\n" if check_a else ""
                response += f"**Check B:** {check_b} {check_b_status}\n" if check_b else ""
            else:
                max_event_list = len(event_list)
                break
        if base_event_list < max_event_list:
            response += f"And {len(event_list) - base_event_list} more events..."

        return response
    except Exception as e:
        logging.exception(f"Error fetching kingdom events: {e}")
        return None


async def fetch_settlement_base(
        guild_id: int,
        settlement: str) -> typing.Union[BaseSettlementInfo, None]:
    async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
        cursor = await db.cursor()
        await cursor.execute(
            """SELECT Kingdom, Settlement, Size, Population, Corruption, Crime, Productivity, Law, Lore, Society, Danger, Defence, Base_Value, Spellcasting, Supply, Decay,  FROM kb_settlements WHERE Settlement = ?""",
            (settlement,))
        settlement_info = await cursor.fetchone()
        if settlement_info is not None:
            return BaseSettlementInfo(*settlement_info)
        return None

async def fetch_settlement(
        guild_id: int,
        settlement: str,
        turn_id: typing.Optional[int]) -> typing.Union[SettlementInfo, None]:
    async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
        cursor = await db.cursor()
        await cursor.execute(
            """SELECT Kingdom, Settlement, Size, Corruption, Crime, Productivity, Law, Lore, Society, Danger, Defence, Base_Value, Spellcasting, Supply, Decay, Image, Host_Channel, Host_Message, Latitude, Longitude  FROM kb_settlements WHERE Settlement = ?""",
            (settlement,))
        settlement_info = await cursor.fetchone()
        if settlement_info is not None:
            (kingdom, settlement, size, corruption, crime, productivity, law, lore, society, danger, defence, base_value, spellcasting, supply, decay, image, host_channel, host_message, latitude, longitude) = settlement_info
            settlement_information = SettlementInfo(
                kingdom=kingdom,
                settlement=settlement,
                image=image,
                host_channel=host_channel,
                host_message=host_message,
                latitude=latitude,
                longitude=longitude)
            settlement_information.size.base = size
            settlement_information.corruption.base = corruption
            settlement_information.crime.base = crime
            settlement_information.productivity.base = productivity
            settlement_information.law.base = law
            settlement_information.lore.base = lore
            settlement_information.society.base = society
            settlement_information.danger.base = danger
            settlement_information.defence.base = defence
            settlement_information.base_value.base = base_value
            settlement_information.spellcasting.base = spellcasting
            settlement_information.supply.base = supply
            settlement_information.decay.base = decay
            await cursor.execute(
                """SELECT Corruption, Crime, Productivity, Law, Lore, Society, Danger, Defence, Base_Value, Spellcasting, Supply FROM kb_settlements_custom WHERE Settlement = ?""",
                (settlement,))
            custom_settlement_info = await cursor.fetchone()
            (custom_corruption, custom_crime, custom_productivity, custom_law, custom_lore, custom_society, custom_danger,
             custom_defence, custom_base_value, custom_spellcasting, custom_supply) = custom_settlement_info
            settlement_information.corruption.custom_value = custom_corruption
            settlement_information.crime.custom_value = custom_crime
            settlement_information.productivity.custom_value = custom_productivity
            settlement_information.law.custom_value = custom_law
            settlement_information.lore.custom_value = custom_lore
            settlement_information.society.custom_value = custom_society
            settlement_information.danger.custom_value = custom_danger
            settlement_information.defence.custom_value = custom_defence
            settlement_information.base_value.custom_value = custom_base_value
            settlement_information.spellcasting.custom_value = custom_spellcasting
            settlement_information.supply.custom_value = custom_supply

            await cursor.execute(""" SELECT 
                    coalesce(SUM(Lots * Amount), 0), 
                    coalesce(SUM(Corruption * Amount), 0),
                    coalesce(SUM(Crime * Amount), 0),
                    coalesce(SUM(Productivity * Amount), 0),
                    coalesce(SUM(law * Amount), 0),
                    coalesce(SUM(Lore * Amount), 0),
                    coalesce(SUM(Society * Amount), 0),
                    coalesce(SUM(Danger * Amount), 0),
                    coalesce(SUM(Defence * Amount), 0),
                    coalesce(SUM(Base_Value * Amount), 0),
                    coalesce(SUM(Spellcasting * Amount), 0),
                    coalesce(SUM(Supply * Amount), 0)
                FROM KB_Buildings KB 
                LEFT JOIN KB_Buildings_Blueprints KBB on KB.full_name = kbb.full_name
                where settlement = ?          
            """, (settlement,))
            building_info = await cursor.fetchone()
            (building_lots, building_corruption, building_crime, building_productivity, building_law, building_lore, building_society,
             building_danger, building_defence, building_base_value, building_spellcasting, building_supply) = building_info
            settlement_information.size.building_value = building_lots
            settlement_information.corruption.building_value = building_corruption
            settlement_information.crime.building_value = building_crime
            settlement_information.productivity.building_value = building_productivity
            settlement_information.law.building_value = building_law
            settlement_information.lore.building_value = building_lore
            settlement_information.society.building_value = building_society
            settlement_information.danger.building_value = building_danger
            settlement_information.defence.building_value = building_defence
            settlement_information.base_value.building_value = building_base_value
            settlement_information.spellcasting.building_value = building_spellcasting
            settlement_information.supply.building_value = building_supply


            if turn_id:
                await cursor.execute("SELECT Corruption, Crime, Productivity, Law, Lore, Society, Danger, Defence from kb_turn_penalty_settlement TurnID = ? and Settlement = ?", (turn_id,settlement))
                turn_info = await cursor.fetchone()
                (turn_corruption, turn_crime, turn_productivity, turn_law, turn_lore, turn_society, turn_danger, turn_defence) = turn_info
                settlement_information.corruption.penalty = turn_corruption
                settlement_information.crime.penalty = turn_crime
                settlement_information.productivity.penalty = turn_productivity
                settlement_information.law.penalty = turn_law
                settlement_information.lore.penalty = turn_lore
                settlement_information.society.penalty = turn_society
                settlement_information.danger.penalty = turn_danger
                settlement_information.defence.penalty = turn_defence

        return settlement_information


async def fetch_settlement_building_state(
        db: aiosqlite.Connection,
        kingdom: str,
        settlement: str) -> typing.Union[BaseSettlementInfo, None]:
    try:
        cursor = await db.cursor()
        await cursor.execute("""
        SELECT 
        SUM(CASE WHEN KB.Subtype = 'Housing' THEN KB.Amount * COALESCE(KBB.Quality, 0) ELSE 0 END) AS Housing_Total,
        SUM(CASE WHEN KB.Subtype != 'Housing' THEN KB.Amount * COALESCE(KBB.Supply, 0) ELSE 0 END) AS Non_Housing_Total,
        SUM(KB.Amount * KBB.Lots) as Lots, 
        SUM(KB.Amount * KBB.Corruption) as Corruption, 
        SUM(KB.Amount * KBB.Crime) as Crime, 
        SUM(KB.Amount * KBB.Productivity) as Productivity, 
        SUM(KB.Amount * KBB.Law) as Law, 
        SUM(KB.Amount * KBB.Lore) as Lore, 
        SUM(KB.Amount * KBB.Society) as Society, 
        SUM(KB.Amount * KBB.Danger) as Danger,
        SUM(KB.Amount * KBB.Defence) as Defence,
        SUM(KB.Amount * KBB.Base_Value) as Base_value,
        SUM(KB.Amount * KBB.Spellcasting) as Spellcasting            
        FROM KB_Buildings KB
        JOIN KB_Buildings_Blueprints KBB ON KB.Full_name = KBB.Full_Name
        WHERE KB.Kingdom = ?
        AND KB.Settlement = ?
        """, (kingdom, settlement))
        building_results = await cursor.fetchall()
        if building_results:
             (housing_total, non_housing_total, lots, corruption, crime, productivity, law, lore, society, danger, defence,
             base_value, spellcasting) = building_results[0]
        else:
             (housing_total, non_housing_total, lots, corruption, crime, productivity, law, lore, society, danger, defence,
             base_value, spellcasting) = (0,0,0,0,0,0,0,0,0,0,0,0,0)

        # Handle None values
        housing_total = housing_total or 0
        non_housing_total = non_housing_total or 0
        lots = lots or 0
        corruption = corruption or 0
        crime = crime or 0
        productivity = productivity or 0
        law = law or 0
        lore = lore or 0
        society = society or 0
        danger = danger or 0
        defence = defence or 0
        base_value = base_value or 0
        spellcasting = spellcasting or 0

        settlement_info = BaseSettlementInfo(
            kingdom=kingdom,
            settlement=settlement,
            size=lots,
            corruption=corruption,
            crime=crime,
            productivity=productivity,
            law=law,
            lore=lore,
            society=society,
            danger=danger,
            defence=defence,
            base_value=base_value,
            spellcasting=spellcasting,
            supply=housing_total - non_housing_total
        )
        return settlement_info
    except Exception as e:
        logging.exception(f"Error fetching building state: {e}")
        return None


async def fetch_settlement_event_list(
        db: aiosqlite.Connection,
        settlement: str,
        offset: int = 0,
        limit: int = 1000
) -> typing.Union[typing.Iterable[Row], None]:
    try:
        cursor = await db.cursor()
        await cursor.execute("""
        SELECT
        ID, Type, Kingdom, Settlement, Hex, Name,
        Effect, Duration,
        Check_A, Check_A_Status,
        Check_B, Check_B_Status,
        case when check_a_status  = 1 and check_b_status = 1 then 2 when check_a_status = 1 or check_b_status = 1 then 1 else 0 end as Severity
        FROM KB_Events_Active WHERE Settlement = ? and Active = 1
        Order by Name, Severity
        LIMIT ? Offset ?
        """, (settlement, limit, offset))
        event_results = await cursor.fetchall()
        return event_results
    except Exception as e:
        logging.exception(f"Error fetching kingdom events: {e}")
        return None


async def fetch_building(
        guild_id: int,
        building: str) -> typing.Union[BuildingInfo, None]:
    async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
        cursor = await db.cursor()
        await cursor.execute(
            """SELECT Full_Name, Type, Subtype, Quality, Build_Points, Lots, Economy, Loyalty, Stability, Fame, Unrest, Corruption, Crime, Productivity, Law, Lore, Society, Danger, Defence, Base_Value, Spellcasting, Supply, Settlement_Limit, District_Limit, Description, Upgrade, Discount, Tier FROM kb_Buildings_Blueprints WHERE Full_Name = ? OR Type = ?""",
            (building, building))
        building_info = await cursor.fetchone()
        if building_info is not None:
            return BuildingInfo(*building_info)
        return None


async def fetch_hex_improvement(
        guild_id: int,
        full_name: str) -> typing.Union[HexImprovementInfo, None]:
    async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
        cursor = await db.cursor()
        await cursor.execute(
            """SELECT Full_name, Type, Subtype, Quality, Build_Points, Economy, Loyalty, Stability, Unrest, Consumption, Defence, Taxation, Cavernous, Coastline, Desert, Forest, Hills, Jungle, Marsh, Mountains, Plains, Water, Source, Size FROM kb_Hexes_Improvements WHERE Full_Name = ?""",
            (full_name,))
        improvement_info = await cursor.fetchone()
        if improvement_info is not None:
            return HexImprovementInfo(*improvement_info)
        return None


async def fetch_resources(
        db: aiosqlite.Connection,
        kingdom: KingdomInfo,
        farm_penalty: int = 0,
        turn_id: int = 0,
        consumption: typing.Optional[int] = None
) -> (FoodDataClass, RawMaterialsDataClass, SimpleCraftDataClass, LuxuryCraftDataClass):
    consumption = kingdom.consumption.total if consumption is None else consumption
    food_dataclass = FoodDataClass()
    raw_materials_dataclass = RawMaterialsDataClass()
    simple_crafts_dataclass = SimpleCraftDataClass()
    luxury_crafts_dataclass = LuxuryCraftDataClass()
    cursor = await db.cursor()
    await cursor.execute("""
    SELECT 
        COALESCE(SUM(CASE WHEN subtype = 'Grain' THEN amount * quality ELSE 0 END), 0) AS Grain_total,
        COALESCE(SUM(CASE WHEN subtype = 'Produce' THEN amount * quality ELSE 0 END), 0) AS Produce_total,
        COALESCE(SUM(CASE WHEN subtype = 'Husbandry' THEN amount * quality ELSE 0 END), 0) AS Husbandry_total,
        COALESCE(SUM(CASE WHEN subtype = 'Seafood' THEN amount * quality ELSE 0 END), 0) AS Seafood_total,
        COALESCE(SUM(CASE WHEN type = 'Wood' THEN amount * quality ELSE 0 END), 0) AS Wood_Total,
        COALESCE(SUM(CASE WHEN Type = 'Stone' THEN amount * quality ELSE 0 END), 0) AS Stone_Total,
        COALESCE(SUM(CASE WHEN subtype = 'Raw_Textiles' THEN amount * quality ELSE 0 END), 0) AS raw_textiles_total,
        COALESCE(SUM(CASE WHEN Type = 'Ore' THEN amount * quality ELSE 0 END), 0) AS ore_total
    FROM KB_Hexes_Constructed KHC
    LEFT JOIN KB_Hexes_Improvements KHI on KHC.Full_Name = KHI.Full_Name
    WHERE Kingdom = ?""", (kingdom.kingdom,))
    food_results = await cursor.fetchone()
    print('food_results was:', food_results)
    (produced_grain, produced_produce, produced_husbandry, produced_seafood, produced_wood, produced_stone,
     produced_raw_textiles, produced_ore) = food_results
    await cursor.execute("""
    SELECT coalesce(Stored_Grain, 0), coalesce(Stored_Produce, 0), coalesce(Stored_Meat, 0), coalesce(Stored_Seafood, 0) from KB_Kingdoms where kingdom = ?""",
                         (kingdom.kingdom,))
    food_storage_results = await cursor.fetchone()
    (stored_grain, stored_produce, stored_husbandry, stored_seafood) = food_storage_results

    if farm_penalty == 1:
        food_dataclass.grain.base = stored_grain + produced_grain * .5 if produced_grain else 0 + stored_grain
        food_dataclass.produce.base = stored_produce + produced_produce * .5 if produced_produce else 0 + stored_produce
        food_dataclass.husbandry.base = stored_husbandry + produced_husbandry * .5 if produced_husbandry else 0 + stored_husbandry
    elif farm_penalty == 2:
        food_dataclass.grain.base = 0 + stored_grain
        food_dataclass.produce.base = 0 + stored_produce
        food_dataclass.husbandry.base = 0 + stored_husbandry
    food_dataclass.seafood.base = safe_add(produced_seafood, stored_seafood)
    raw_materials_dataclass.raw_textiles.base = produced_raw_textiles
    raw_materials_dataclass.ore.base = produced_ore
    raw_materials_dataclass.wood.base = produced_wood
    raw_materials_dataclass.stone.base = produced_stone
    await cursor.execute("""SELECT 
    COALESCE(SUM(Husbandry),0), COALESCE(SUM(Grain),0), COALESCE(SUM(Produce),0), COALESCE(SUM(Seafood),0),
    COALESCE(SUM(Ore),0), COALESCE(SUM(Stone),0), COALESCE(Sum(Wood),0), COALESCE(Sum(Raw_Textiles),0),
    COALESCE(SUM(Metallurgy),0), COALESCE(SUM(Woodworking),0), COALESCE(SUM(Textiles),0), COALESCE(Sum(Stoneworking),0),
    COALESCE(SUM(luxury),0),  COALESCE(SUM(Magical_Items),0)
    FROM KB_Trade_History where kingdom = ? 
        and turn + ?;
    """, (kingdom.kingdom, turn_id))
    receiving_trade_results = await cursor.fetchone()
    (receiving_husbandry, receiving_grain, receiving_produce, receiving_seafood, receiving_ore, receiving_stone,
     receiving_wood, receiving_raw_textiles, receiving_metallurgy, receiving_woodworking, receiving_textiles,
     receiving_stoneworking, receiving_luxury,
     receiving_magical_items) = receiving_trade_results
    await cursor.execute("""SELECT 
        COALESCE(SUM(CASE WHEN subtype = 'Woodworking' THEN amount * quality ELSE 0 END), 0) AS Woodworking_Total,
        COALESCE(SUM(CASE WHEN subtype = 'Textile' THEN amount * quality ELSE 0 END), 0) AS Textile_total,
        COALESCE(SUM(CASE WHEN subtype = 'Stoneworking' THEN amount * quality ELSE 0 END), 0) AS Stoneworking_total,
        COALESCE(SUM(CASE WHEN subtype = 'Metallurgy' THEN amount * quality ELSE 0 END), 0) AS Metallurgy_total,
        COALESCE(SUM(CASE WHEN subtype = 'Luxury' THEN amount * quality ELSE 0 END), 0) AS luxury_total,
        COALESCE(SUM(CASE WHEN subtype = 'Magical Items' THEN amount * quality ELSE 0 END), 0) AS Magical_Items_total
        FROM KB_Buildings kbuild
        LEFT JOIN KB_Buildings_Blueprints kblue on kblue.Full_Name = kbuild.Full_Name 
    WHERE Kingdom = ?""", (kingdom.kingdom,))
    building_results = await cursor.fetchone()
    (woodworking, textile, stoneworking, metallurgy, luxury,
     magical_items) = building_results

    # FOOD
    food_dataclass.grain.trade = receiving_grain
    food_dataclass.produce.trade = receiving_produce
    food_dataclass.seafood.trade = receiving_seafood
    food_dataclass.husbandry.trade = receiving_husbandry
    remaining_is_total(food_dataclass)
    # RAW MATS
    raw_materials_dataclass.raw_textiles.trade = receiving_raw_textiles
    raw_materials_dataclass.ore.trade = receiving_ore
    raw_materials_dataclass.wood.trade = receiving_wood
    raw_materials_dataclass.stone.trade = receiving_stone
    remaining_is_total(raw_materials_dataclass)
    raw_materials_dataclass.raw_textiles.depletion = max(simple_crafts_dataclass.textiles.total - raw_materials_dataclass.raw_textiles.remaining, 0)
    raw_materials_dataclass.ore.depletion =  max(simple_crafts_dataclass.metallurgy.total - raw_materials_dataclass.ore.remaining, 0)
    raw_materials_dataclass.wood.depletion = max(simple_crafts_dataclass.woodworking.total - raw_materials_dataclass.wood.remaining, 0)
    raw_materials_dataclass.stone.depletion = max(simple_crafts_dataclass.stoneworking.total - raw_materials_dataclass.stone.remaining, 0)

    # Simple Crafts
    simple_crafts_dataclass.textiles.base = min(raw_materials_dataclass.raw_textiles.remaining, textile)
    simple_crafts_dataclass.metallurgy.base = min(raw_materials_dataclass.ore.remaining, metallurgy)
    simple_crafts_dataclass.woodworking.base = min(raw_materials_dataclass.wood.remaining, woodworking)
    simple_crafts_dataclass.stoneworking.base = min(raw_materials_dataclass.stone.remaining, stoneworking)
    raw_materials_dataclass.raw_textiles.remaining = raw_materials_dataclass.raw_textiles.remaining - simple_crafts_dataclass.textiles.base
    raw_materials_dataclass.ore.remaining = raw_materials_dataclass.ore.remaining - simple_crafts_dataclass.metallurgy.base
    raw_materials_dataclass.wood.remaining = raw_materials_dataclass.wood.remaining - simple_crafts_dataclass.woodworking.base
    raw_materials_dataclass.stone.remaining = raw_materials_dataclass.stone.remaining - simple_crafts_dataclass.stoneworking.base

    simple_crafts_dataclass.textiles.trade = receiving_textiles
    simple_crafts_dataclass.metallurgy.trade = receiving_metallurgy
    simple_crafts_dataclass.woodworking.trade = receiving_woodworking
    simple_crafts_dataclass.stoneworking.trade = receiving_stoneworking
    remaining_is_total(simple_crafts_dataclass)
    # Luxury Items
    luxury_crafts_dataclass.luxury.base = luxury
    luxury_crafts_dataclass.magical_items.base = magical_items
    luxury_crafts_dataclass.luxury.trade = receiving_luxury
    luxury_crafts_dataclass.magical_items.trade = receiving_magical_items

    # 2 Raw makes 1 Luxury. Distribute this as evenly as possible both for incoming and outgoing.
    (raw_materials_dataclass, luxury_crafts_dataclass, overdraft) = distribute_pain(raw_materials_dataclass,
                                                                         luxury_crafts_dataclass)
    remaining_is_total(luxury_crafts_dataclass)

    (crafted_materials_dict, complex_materials_dict,
     economy_penalty, stability_penalty,
     loyalty_penalty, unrest_penalty) = await handle_settlement_utilization(db=db, kingdom=kingdom.kingdom,
                                                                      crafted_dataclass=simple_crafts_dataclass,
                                                                      luxury_dataclass=luxury_crafts_dataclass)

    (food_dict, food_unrest_penalty, event) = await handle_food(db=db, kingdom=kingdom.kingdom, food_dataclass=food_dataclass,
                                                         consumption=consumption)

    available_food = goods_remaining_dict(food_dataclass)
    penalty_dict = {
        'loyalty': loyalty_penalty if loyalty_penalty else 0,
        'economy': economy_penalty if economy_penalty else 0,
        'stability': stability_penalty if stability_penalty else 0,
        'food_unrest': food_unrest_penalty if food_unrest_penalty else 0,
        'utilization_unrest': unrest_penalty if unrest_penalty else 0,
        'overdraft': overdraft
    }

    return (food_dataclass, raw_materials_dataclass, simple_crafts_dataclass, luxury_crafts_dataclass,
            available_food, penalty_dict, event)
