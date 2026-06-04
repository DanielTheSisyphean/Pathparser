import datetime
import logging
import typing
import aiosqlite
import math
import random

import discord

from core.kingdom import (
    KingdomInfo, BuildingInfo, HexImprovementInfo,
    encrypt_password
)


async def generate_leadership(
        db: aiosqlite.Connection,
        kingdom: str):
    try:
        cursor = await db.cursor()
        await cursor.execute("""
        INSERT INTO kb_Leadership (Kingdom, Title, Character_Name, Stat, Modifier, Economy,  Loyalty, Stability, Unrest)
        SELECT ?, Title, 'Vacant', 0, Null, VPEconomy, VPLoyalty, VPStability, VPUnrest FROM AA_Leadership_Roles
        """, (kingdom,))
        await cursor.execute(
            """SELECT SUM(VPEconomy), SUM(VPLoyalty), SUM(VPStability), SUM(VPUnrest) FROM AA_Leadership_Roles""")
        vp_info = await cursor.fetchone()
        await cursor.execute(
            """UPDATE kb_Kingdoms SET Economy = Economy + ?, Loyalty = Loyalty + ?, Stability = Stability + ?, Unrest = Unrest + ? WHERE Kingdom = ?""",
            (vp_info[0], vp_info[1], vp_info[2], vp_info[3], kingdom))
    except (aiosqlite.Error, TypeError, ValueError) as e:
        logging.exception(f"Error generating leadership: {e}")
        return f"An error occurred while generating leadership. {e}"


async def generate_permissions(
        db: aiosqlite.Connection,
        kingdom: str):
    try:
        cursor = await db.cursor()
        await cursor.execute("""
        INSERT INTO KB_Buildings_Permits (Kingdom, Full_Name)
        SELECT ?, Full_Name FROM KB_Buildings_Blueprints WHERE Tier = 0
        """, (kingdom,))
    except (aiosqlite.Error, TypeError, ValueError) as e:
        logging.exception(f"Error generating permissions: {e}")
        return f"An error occurred while generating permissions. {e}"


async def create_a_kingdom(
        guild_id: int,
        author: str,
        kingdom: str,
        region: str,
        password: str,
        government: str,
        alignment: str,
        image_link: str,
        channel: discord.TextChannel
) -> str:
    try:
        if image_link is not None:
            image_link = str.replace(str.replace(image_link, ";", ""), ")", "")
            image_link_valid = str.lower(image_link[0:5])
            if len(image_link) > 300:
                return f"When it blocked out the sun, did you consider if it was possible that your image link is a little too long?"
            if image_link_valid != 'https':
                return f"Image link is missing HTTPS:"
        hashed_password = encrypt_password(password)
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute("""select Kingdom FROM KB_Kingdoms where Kingdom = ?""", (kingdom,))
            kingdom_presence = await cursor.fetchone()
            if kingdom_presence is not None:
                return "The kingdom already exists."
            await cursor.execute("""select Economy, Loyalty, Stability FROM AA_Alignment WHERE Alignment = ?""",
                                 (alignment,))
            alignment_type = await cursor.fetchone()
            
            if alignment_type is None:
                return "Invalid alignment."
            await cursor.execute("""select Government FROM AA_Government WHERE Government = ?""", (government,))
            government_type = await cursor.fetchone()
            if government_type is None:
                return "Invalid government type."

            (economy, loyalty, stability) = alignment_type
            await cursor.execute("""
            INSERT INTO kb_Kingdoms (
            Kingdom, Password, Government, Alignment, Region, Size, Population, 
            Economy, Loyalty, Stability, 
            Fame, Unrest, Consumption,
            Control_DC, Build_Points,
            Stored_seafood, Stored_meat, Stored_grain, Stored_produce,
            Holiday, Promotion, Taxation, Improvements, Buildings,
            Buildings_Housing, Claims, Available_Population, Heraldry, Host_Channel
            ) VALUES (
            ?, ?, ?, ?, ?, 0, 0, 
            ?, ?, ?,
            0, 0, 0,
            0, 0,
            0, 0, 0, 0,
            0, 0, 0, 0, 0,
            0, 0, 0, ?, ?
            )
            """, (kingdom, hashed_password, government, alignment, region, economy, loyalty, stability, image_link, channel.id))
            await cursor.execute(
                """Insert into A_Audit_All (Author, Timestamp, Database_Changed, Modification, Reason) VALUES (?, ?, ?, ?, ?)""",
                (author, datetime.datetime.now(), "kb_Kingdoms", "Create", f"Created the kingdom of {kingdom}"))
            await cursor.execute(
                "INSERT Into kb_Kingdoms_Custom(Kingdom, Control_DC, Economy, Loyalty, Stability, Fame, Unrest, Consumption) VALUES (?, 0, 0, 0, 0, 0, 0, 0)",
                (kingdom,))
            await generate_leadership(
                db=db,
                kingdom=kingdom)
            await generate_permissions(
                db=db,
                kingdom=kingdom)
            await db.commit()
            return f"Congratulations, you have created the kingdom of {kingdom}."

    except (aiosqlite.Error, TypeError, ValueError) as e:
        logging.exception(f"Error creating a kingdom: {e}")
        return "An error occurred while creating a kingdom."


async def edit_a_kingdom(
        guild_id: int,
        author: str,
        old_kingdom_info: KingdomInfo,
        new_kingdom: str,
        government: str,
        alignment: str,
        heraldry: str
) -> str:
    try:
        new_kingdom = old_kingdom_info.kingdom if not new_kingdom else new_kingdom
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()
            if alignment is not None:
                await cursor.execute(
                    """select Alignment, Economy, Loyalty, Stability FROM AA_Alignment WHERE Alignment = ?""",
                    (old_kingdom_info.alignment,))
                old_alignment_info = await cursor.fetchone()
                await cursor.execute(
                    """select Alignment, Economy, Loyalty, Stability FROM AA_Alignment WHERE Alignment = ?""",
                    (alignment,))
                new_alignment_info = await cursor.fetchone()
                if new_alignment_info is None:
                    return "Invalid alignment."
                old_kingdom_info.economy += new_alignment_info[1] - old_alignment_info[1]
                old_kingdom_info.loyalty += new_alignment_info[2] - old_alignment_info[2]
                old_kingdom_info.stability += new_alignment_info[3] - old_alignment_info[3]
            if government is not None:
                await cursor.execute(
                    "SELECT Government, Corruption, Crime, Law, Lore, Productivity, Society FROM AA_Government WHERE Government = ?",
                    (old_kingdom_info.government,))
                old_government_info = await cursor.fetchone()
                await cursor.execute(
                    "SELECT Government, Corruption, Crime, Law, Lore, Productivity, Society FROM AA_Government WHERE Government = ?",
                    (government,))
                new_government_info = await cursor.fetchone()
                if new_government_info is None:
                    return "Invalid government type."
                (new_government_type, new_corruption, new_crime, new_law, new_lore, new_productivity,
                 new_society) = new_government_info
                (old_government_type, old_corruption, old_crime, old_law, old_lore, old_productivity,
                 old_society) = old_government_info
                sum_corruption = new_corruption - old_corruption
                sum_crime = new_crime - old_crime
                sum_law = new_law - old_law
                sum_lore = new_lore - old_lore
                sum_productivity = new_productivity - old_productivity
                sum_society = new_society - old_society
                await cursor.execute(
                    "UPDATE kb_settlements SET Corruption = Corruption + ?, Crime = Crime + ?, Law = Law + ?, Lore = Lore + ?, Productivity = Productivity + ?, Society = Society + ? WHERE Kingdom = ?",
                    (
                        sum_corruption,
                        sum_crime,
                        sum_law,
                        sum_lore,
                        sum_productivity,
                        sum_society,
                        old_kingdom_info.kingdom))
            await cursor.execute(
                "UPDATE kb_Kingdoms SET Kingdom = ?, Password = ?, Government = ?, Alignment = ?, Economy = ?, Loyalty = ?, Stability = ?, heraldry = coalesce(?, heraldry) WHERE Kingdom = ?",
                (
                    new_kingdom,
                    old_kingdom_info.password,
                    government,
                    alignment,
                    old_kingdom_info.economy,
                    old_kingdom_info.loyalty,
                    old_kingdom_info.stability,
                    heraldry,
                    old_kingdom_info.kingdom
                ))
            await cursor.execute(
                "UPDATE kb_Kingdoms_Custom SET Kingdom = ? WHERE Kingdom = ?", (
                    new_kingdom,
                    old_kingdom_info.kingdom))
            await cursor.execute(
                "UPDATE kb_settlements SET Kingdom = ? WHERE Kingdom = ?", (
                    new_kingdom,
                    old_kingdom_info.kingdom))
            await cursor.execute(
                "UPDATE kb_settlements_Custom SET Kingdom = ? WHERE Kingdom = ?", (
                    new_kingdom,
                    old_kingdom_info.kingdom))
            await cursor.execute(
                "UPDATE kb_hexes SET Kingdom = ? WHERE Kingdom = ?", (
                    new_kingdom,
                    old_kingdom_info.kingdom))
            await cursor.execute(
                "UPDATE KB_Trade SET Source_Kingdom = ? WHERE Source_Kingdom = ?", (
                    new_kingdom,
                    old_kingdom_info.kingdom))
            await cursor.execute(
                "UPDATE KB_Trade SET End_Kingdom = ? WHERE End_Kingdom = ?", (
                    new_kingdom,
                    old_kingdom_info.kingdom))
            await cursor.execute(
                "UPDATE KB_Buildings_Permits SET Kingdom = ? WHERE Kingdom = ?", (
                    new_kingdom,
                    old_kingdom_info.kingdom))
            await cursor.execute(
                "UPDATE KB_Leadership SET Kingdom = ? WHERE Kingdom = ?", (
                    new_kingdom,
                    old_kingdom_info.kingdom))
            await cursor.execute(
                "UPDATE KB_Armies SET Kingdom = ? WHERE Kingdom = ?", (
                    new_kingdom,
                    old_kingdom_info.kingdom))
            await cursor.execute(
                "UPDATE KB_Events_Active SET Kingdom = ? WHERE Kingdom = ?", (
                    new_kingdom,
                    old_kingdom_info.kingdom))
            await cursor.execute(
                "Insert into A_Audit_All (Author, Timestamp, Database_Changed, Modification, Reason) VALUES (?, ?, ?, ?, ?)",
                (author, datetime.datetime.now(), "kb_Kingdoms", "Edit",
                 f"Edited the kingdom of {old_kingdom_info.kingdom} to {new_kingdom}"))
            await db.commit()
            return f"The kingdom of {old_kingdom_info.kingdom} has been edited to {new_kingdom}."
    except (aiosqlite.Error, TypeError, ValueError) as e:
        logging.exception(f"Error editing a kingdom: {e}")
        return "An error occurred while editing a kingdom."


async def delete_a_kingdom(
        guild_id: int, author: int, kingdom: str) -> str:
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute("DELETE FROM kb_Kingdoms WHERE Kingdom = ?", (kingdom,))
            await cursor.execute("DELETE FROM kb_Kingdoms_Custom WHERE Kingdom = ?", (kingdom,))
            await cursor.execute("Update kb_hexes Set Kingdom = Null, IsTown = 0 WHERE Kingdom = ?", (kingdom,))
            await cursor.execute("DELETE FROM KB_Trade WHERE Source_Kingdom = ? OR End_Kingdom = ?", (kingdom, kingdom))
            await cursor.execute("DELETE FROM KB_Buildings_Permits WHERE Kingdom = ?", (kingdom,))
            await cursor.execute("DELETE FROM KB_Leadership WHERE Kingdom = ?", (kingdom,))
            await cursor.execute("DELETE FROM KB_Armies WHERE Kingdom = ?", (kingdom,))
            await cursor.execute("DELETE FROM KB_Events_Active where Kingdom = ?", (kingdom,))
            await cursor.execute("DELETE FROM KB_Trade_history where Kingdom = ?", (kingdom,))
            await cursor.execute("DELETE FROM KB_Turn_History_Kingdom where Kingdom = ?", (kingdom,))
            await cursor.execute("DELETE FROM KB_Turn_History_Settlement where Kingdom = ?", (kingdom,))
            await cursor.execute("DELETE FROM KB_Turn_Penalty_Kingdom where Kingdom = ?", (kingdom,))
            await cursor.execute("DELETE FROM KB_Turn_Penalty_Settlement where Kingdom = ?", (kingdom,))
            await cursor.execute(
                "Insert into A_Audit_All (Author, Timestamp, Database_Changed, Modification, Reason) VALUES (?, ?, ?, ?, ?)",
                (author, datetime.datetime.now(), "kb_Kingdoms", "Delete", f"Deleted the kingdom of {kingdom}"))
            await db.commit()
            return f"The kingdom of {kingdom} has been deleted, its holdings cleared, and its hexes freed."
    except (aiosqlite.Error, TypeError, ValueError) as e:
        logging.exception(f"Error deleting a kingdom: {e}")
        return "An error occurred while deleting a kingdom."


async def adjust_bp(
        guild_id: int,
        author: int,
        kingdom: str,
        amount: int,
        apply_unrest: bool = True) -> str:
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()
            return_string = f"The build points of {kingdom} have been increased by {amount}."
            await cursor.execute("SELECT Build_Points FROM kb_Kingdoms WHERE Kingdom = ?", (kingdom,))
            kingdom_info = await cursor.fetchone()

            if kingdom_info is None:
                return "The kingdom does not exist."
            if apply_unrest and amount < 0:
                await cursor.execute(
                    "UPDATE kb_Kingdoms SET Unrest = Unrest + ? WHERE Kingdom = ?",
                    (abs(amount), kingdom))
                return_string += f" Unrest has been increased by {abs(amount)}."
            if amount < 0:
                amount = max(amount, -kingdom_info[0])
            await cursor.execute("UPDATE kb_Kingdoms SET Build_Points = Build_Points + ? WHERE Kingdom = ?",
                                 (amount, kingdom))
            await cursor.execute(
                "Insert into A_Audit_All (Author, Timestamp, Database_Changed, Modification, Reason) VALUES (?, ?, ?, ?, ?)",
                (author, datetime.datetime.now(), "kb_Kingdoms", "Increase BP",
                 f"Increased the build points of {kingdom} by {amount}"))
            await db.commit()

            return return_string
    except (aiosqlite.Error, TypeError, ValueError) as e:
        logging.exception(f"Error increasing build points: {e}")
        return "An error occurred while increasing build points."


async def update_leader(
        guild_id: int,
        author: int,
        kingdom: str,
        title: str,
        player_id: int,
        character_name: str,
        stat: str,
        modifier: int,
        economy: int,
        loyalty: int,
        stability: int
) -> str:
    try:

        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute(
                "SELECT Economy, Loyalty, Stability, Unrest FROM kb_Leadership WHERE Kingdom = ? AND Title = ?",
                (kingdom, title))
            leader_info = await cursor.fetchone()
            if leader_info is None:
                return "The leader does not exist."
            await cursor.execute(
                "UPDATE kb_Leadership Set Character_Name = ?, Player_ID = ?, Stat = ?, Modifier = ?, Economy = ?, Loyalty = ?, Stability = ?, unrest = ? WHERE Kingdom = ? AND Title = ?",
                (character_name, player_id, stat, modifier, economy, loyalty, stability, 0, kingdom, title))
            await cursor.execute(
                "Insert into A_Audit_All (Author, Timestamp, Database_Changed, Modification, Reason) VALUES (?, ?, ?, ?, ?)",
                (author, datetime.datetime.now(), "kb_Leadership", "Update",
                 f"Updated the leader of {kingdom} to {character_name}"))
            await db.commit()
            return f"Leader updated for {kingdom}."

    except (aiosqlite.Error, TypeError, ValueError) as e:
        logging.exception(f"Error updating leader: {e}")
        return "An error occurred while updating the leader."


async def remove_leader(
        guild_id: int,
        author: int,
        kingdom: str,
        title: str) -> str:
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute(
                "SELECT Economy, Loyalty, Stability, Unrest FROM kb_Leadership WHERE Kingdom = ? AND Title = ?",
                (kingdom, title))
            leader_info = await cursor.fetchone()
            await cursor.execute(
                "SELECT VPEconomy, VPLoyalty, VPStability, VPUnrest FROM AA_Leadership_Roles WHERE Title = ?", (title,))
            base_info = await cursor.fetchone()
            (base_economy, base_loyalty, base_stability, base_unrest) = base_info
            if leader_info is None:
                return "The leader does not exist."
            await cursor.execute(
                "UPDATE kb_Leadership SET Character_Name = 'Vacant', Player_ID = Null, Stat = Null, Modifier = Null, Economy = ?, Loyalty = ? , Stability = ?, Unrest = ? WHERE Kingdom = ? AND Title = ?",
                (base_economy, base_loyalty, base_stability, base_unrest, kingdom, title))
            await cursor.execute(
                "Insert into A_Audit_All (Author, Timestamp, Database_Changed, Modification, Reason) VALUES (?, ?, ?, ?, ?)",
                (author, datetime.datetime.now(), "kb_Leadership", "Remove", f"Removed the leader of {kingdom}"))
            await db.commit()
            return f"The person in the position of {title} for {kingdom} has been removed."
    except (aiosqlite.Error, TypeError, ValueError) as e:
        logging.exception(f"Error removing leader: {e}")
        return "An error occurred while removing the leader."


async def claim_hex(
        guild_id: int,
        author: int,
        kingdom: str,
        hex_id: int) -> str:
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute("Update KB_Hexes set Kingdom = ? WHERE ID = ?", (kingdom, hex_id))
            await cursor.execute(
                "Insert into A_Audit_All (Author, Timestamp, Database_Changed, Modification, Reason) VALUES (?, ?, ?, ?, ?)",
                (author, datetime.datetime.now(), "Hexes", "Claim", f"Claimed the hex of {hex_id}"))
            await db.commit()
            return f"The hex of {hex_id} has been claimed by {kingdom}."
    except (aiosqlite.Error, TypeError, ValueError) as e:
        logging.exception(f"Error claiming hex: {e}")
        return "An error occurred while claiming the hex."


async def relinquish_hex(
        guild_id: int,
        author: int,
        kingdom: str,
        hex_id: int) -> str:
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute("Update kb_hexes set Kingdom = Null WHERE ID = ? and Kingdom = ?",
                                 (hex_id, kingdom))
            await cursor.execute(
                "Insert into A_Audit_All (Author, Timestamp, Database_Changed, Modification, Reason) VALUES (?, ?, ?, ?, ?)",
                (author, datetime.datetime.now(), "Hexes", "relinquish", f"Unclaimed the hex of {hex_id}"))
            await db.commit()
            return f"The hex of {hex_id} has been unclaimed by {kingdom}."
    except (aiosqlite.Error, TypeError, ValueError) as e:
        logging.exception(f"Error unclaiming hex: {e}")
        return "An error occurred while unclaiming the hex."


async def add_an_improvement(
        guild_id: int,
        hex_id: int,
        kingdom: str,
        improvement: str,
        amount: int,
        build_points: int,
        kingdom_size: int,
        iscost: bool = True
) -> str:
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.cursor()
            await cursor.execute(
                "SELECT Kingdom, Hex_Terrain, Farm, Ore, Stone, Wood, Istown, Road FROM KB_Hexes WHERE ID = ?",
                (hex_id,))
            base_hex_info = await cursor.fetchone()
            if not base_hex_info:
                return f"The hex terrain of {hex_id} does not exist."
            if base_hex_info['Kingdom'] != kingdom:
                return f"The hex terrain of {hex_id} is not in the kingdom of {kingdom}."
            if base_hex_info['Istown'] == 1:
                return f"The hex of {hex_id} is a town."
            await cursor.execute(
                """SELECT Full_name, Type, Subtype, Build_Points, Cavernous, Coastline, Desert, Forest, Hills, Jungle, Marsh, Mountains, Plains, Water, Source, Size FROM kb_Hexes_Improvements WHERE full_name = ?""",
                (improvement,))
            improvement_info = await cursor.fetchone()
            if not improvement_info:
                return f"The improvement of {improvement} does not exist."
            if improvement_info[f'{base_hex_info["Hex_Terrain"]}'] == 0:
                return f"The improvement of {improvement} cannot be built on {base_hex_info['Hex_Terrain']}."
            if improvement_info['Size'] > kingdom_size:
                return f"The improvement of {improvement} requires a kingdom size of {improvement_info['Size']} or greater."
            await cursor.execute("Select Sum(Amount) From KB_Hexes_Constructed KHC left join KB_Hexes_Improvements KHI on KHC.Full_name = KHI.Full_Name   where Type = ? and ID = ?",
                                 (improvement_info['Type'], hex_id))
            constructed = await cursor.fetchone()
            constructed = constructed[0] if constructed[0] else 0
            hex_multiple = ('Farm', 'Ore', 'Stone', 'Wood', 'Seafood')
            if improvement_info['Type'] in hex_multiple:
                if constructed >= base_hex_info[improvement_info['Type']]:
                    return f"The improvement of {improvement} has reached its maximum amount. \r\nIf it is a farm You may want to convert an existing improvement to a different type."


                max_buildable = max(min(amount, base_hex_info[improvement_info['Type']] - constructed ), 0)
            else:
                max_buildable = 1

            if iscost:
                cost_modifier = improvement_info['Build_Points'] * improvement_info[f'{base_hex_info["Hex_Terrain"]}']
                max_amount = min(max_buildable, build_points // cost_modifier)
                build_cost = max_amount * cost_modifier
            else:
                max_amount = max_buildable
                build_cost = 0
            await cursor.execute(
                "Update KB_Kingdoms Set Build_Points = Build_Points - ? WHERE Kingdom = ?",
                (build_cost, kingdom))
            if not constructed:
                await cursor.execute("""
                INSERT into KB_Hexes_Constructed(ID, Full_Name, kingdom, Amount) 
                VALUES 
                (?, ?, ?)
                """, (hex_id, improvement_info['Full_name'], kingdom,
                      max_amount))
            else:
                await cursor.execute(
                    "UPDATE kb_hexes_constructed SET Amount = Amount + ? WHERE Full_Name = ? and ID = ?",
                    (max_amount, improvement, hex_id))
            await db.commit()
            return f"The improvement of {improvement} has been added to the hex of {hex_id}."
    except (aiosqlite.Error, TypeError, ValueError) as e:
        logging.exception(f"Error adding improvement: {e}")
        return f"An error occurred while adding the improvement. {e}"


async def degrade_improvement(
        guild_id: int,
        author: int,
        hex_information: HexImprovementInfo,
        hex_id: int,
        amount: int
) -> str:
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute(
                "SELECT Amount FROM kb_hexes_constructed WHERE ID = ? and Full_Name = ?",
                (hex_id, hex_information.full_name))
            availability = await cursor.fetchone()
            if not availability:
                return f"Hex {hex_id} has no the improvements of {hex_information.full_name}."
            amount = min(amount, availability[0])
            if availability[0] == amount:
                await cursor.execute(
                    "DELETE FROM kb_hexes_constructed WHERE ID = ? and Full_Name = ?",
                    (hex_id, hex_information.full_name))
            else:
                await cursor.execute(
                    "UPDATE kb_hexes_constructed SET Amount = Amount - ? WHERE ID = ? and Full_Name = ?",
                    (amount, hex_id, hex_information.full_name))
            await cursor.execute(
                "Insert into A_Audit_All (Author, Timestamp, Database_Changed, Modification, Reason) VALUES (?, ?, ?, ?, ?)",
                (author, datetime.datetime.now(), "Hexes", "Remove Improvement",
                 f"Removed the improvement of {hex_information.full_name} from the hex of {hex_id}"))
            await db.commit()
            return f"The improvement of {hex_information.full_name} has been removed from the hex of {hex_id}."
    except (aiosqlite.Error, TypeError, ValueError) as e:
        logging.exception(f"Error removing improvement: {e}")
        return "An error occurred while removing the improvement."


async def repurpose_an_improvement(
        guild_id: int,
        hex_id: int,
        old_full_name: str,
        new_full_name: str,
        amount: int):
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()
            if old_full_name == new_full_name:
                return "The new improvement must be different from the old improvement."
            await cursor.execute("Select Amount from KB_Hexes_Constructed where Full_Name = ? and id = ?",
                                 (old_full_name, hex_id))
            availability = await cursor.fetchone()
            if not availability:
                return f"No improvements of {old_full_name} are present."
            amount = min(amount, availability[0])
            await cursor.execute("Select consumption from KB_Hexes_Improvements where Full_Name = ?",
                                 (new_full_name,))
            new_improvement = await cursor.fetchone()
            if not new_improvement:
                return f"The improvement of {new_full_name} does not exist as a choice."
            await cursor.execute("Select Amount from KB_Hexes_Constructed where Full_Name = ?", (new_full_name,))
            new_availability = await cursor.fetchone()
            if availability[0] == amount and not new_availability:
                await cursor.execute("UPDATE KB_Hexes_Constructed set Full_Name = ? where Full_Name = ? and id = ?",
                                     (new_full_name, old_full_name, hex_id))
            elif availability[0] == amount and new_availability:
                await cursor.execute(
                    "UPDATE KB_Hexes_Constructed set Amount = Amount + ? where Full_Name = ? and id = ?",
                    (amount, new_full_name, hex_id))
                await cursor.execute("DELETE from KB_Hexes_Constructed where Full_Name = ? and id = ?",
                                     (old_full_name, hex_id))
            elif availability[0] != amount and not new_availability:
                await cursor.execute(
                    "UPDATE KB_Hexes_Constructed set Amount = Amount - ? where Full_Name = ? and id = ?",
                    (amount, old_full_name, hex_id))
                await cursor.execute("""INSERT into KB_Hexes_Constructed (ID, Full_Name, Type, Subtype, Amount)
                SELECT ?, full_name, Type, Subtype, ? FROM KB_Hexes_Improvements where Full_Name = ?""",
                                     (hex_id, amount, new_full_name))
            else:
                await cursor.execute(
                    "UPDATE KB_Hexes_Constructed set Amount = Amount + ? where Full_Name = ? and id = ?",
                    (amount, new_full_name, hex_id))
                await cursor.execute(
                    "UPDATE KB_Hexes_Constructed set Amount = Amount - ? where Full_Name = ? and id = ?",
                    (amount, old_full_name, hex_id))
            await db.commit()
            return f"{amount} improvements of {old_full_name} have been repurposed to {new_full_name}."
    except (aiosqlite.Error, TypeError, ValueError) as e:
        logging.exception(f"Error repurposing improvement: {e}")
        return "An error occurred while repurposing the improvement."


async def add_building(
        guild_id: int,
        author: int,
        kingdom: str,
        settlement: str,
        building_info: BuildingInfo,
        amount) -> str:
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute("SELECT Full_Name FROM KB_Buildings WHERE Full_Name = ? and Settlement = ?",
                                 (building_info.full_name, settlement))
            building_presence = await cursor.fetchone()
            if not building_presence:
                await cursor.execute("""
                INSERT INTO KB_Buildings (
                Kingdom, Settlement, 
                Full_Name, Amount, Discounted) 
                VALUES (
                ?, ?, 
                ?, ?, 0)""", (
                    kingdom, settlement,
                    building_info.full_name,
                    amount))
            else:
                await cursor.execute(
                    "Update KB_Buildings Set Amount = Amount + ? WHERE Full_Name = ? and Settlement = ?",
                    (amount, building_info.full_name, settlement))
            await cursor.execute(
                "Insert into A_Audit_All (Author, Timestamp, Database_Changed, Modification, Reason) VALUES (?, ?, ?, ?, ?)",
                (author, datetime.datetime.now(), "Buildings", "Add",
                 f"Added the building of {building_info.full_name} to the settlement of {settlement}"))
            await db.commit()
            return f"{amount} building(s) of {building_info.full_name} have been added. Costing {building_info.build_points * amount} build points."
    except (aiosqlite.Error, TypeError, ValueError) as e:
        logging.exception(f"Error adding building: {e}")
        return "An error occurred while adding the building."


async def remove_building(
        guild_id: int,
        author: int,
        settlement: str,
        building_info: BuildingInfo,
        amount) -> tuple[str, int]:
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute("SELECT Amount FROM KB_Buildings WHERE Full_Name = ? and Settlement = ?",
                                 (building_info.full_name, settlement))
            building_presence = await cursor.fetchone()
            if not building_presence:
                return f"No buildings of {building_info.full_name} are present in the settlement of {settlement}.", 0
            built = building_presence[0]
            amount = min(int(built), amount)
            if amount == built:
                await cursor.execute("DELETE FROM KB_Buildings WHERE Full_Name = ? and Settlement = ?",
                                     (building_info.full_name, settlement))
            else:
                await cursor.execute(
                    "Update KB_Buildings Set Amount = Amount - ? WHERE Full_Name = ? and Settlement = ?",
                    (amount, building_info.full_name, settlement))

            await cursor.execute(
                "Insert into A_Audit_All (Author, Timestamp, Database_Changed, Modification, Reason) VALUES (?, ?, ?, ?, ?)",
                (author, datetime.datetime.now(), "Buildings", "Remove",
                 f"Removed the building of {building_info.full_name} from the settlement of {settlement}"))
            await db.commit()
            return f"{amount} building(s) of {building_info.full_name} have been removed. Refunding {math.floor((building_info.build_points * amount) * .5)} build points.", amount
    except (aiosqlite.Error, TypeError, ValueError) as e:
        logging.exception(f"Error removing building: {e}")
        return "An error occurred while removing the building.", 0


async def claim_a_settlement(
        guild_id: int,
        author: int,
        kingdom: str,
        settlement: str,
        hex_id: int,
        image_link: str,
        channel: discord.TextChannel
) -> str:
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()

            await cursor.execute(
                "INSERT INTO kb_settlements (Kingdom, Settlement, Size, Population, Corruption, Crime, Productivity, Law, Lore, Society, Danger, Defence, Base_Value, Spellcasting, Supply, Decay, hex_id, image, Host_Channel) VALUES (?, ?, 1, 250, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, ?, ?, ?)",
                (kingdom, settlement, hex_id, image_link, channel.id))
            await cursor.execute(
                "INSERT INTO kb_settlements_Custom (Kingdom, Settlement, Corruption, Crime, Productivity, Law, Lore, Society, Danger, Defence, Base_Value, Spellcasting, Supply) VALUES (?, ?, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)",
                (kingdom, settlement))
            await cursor.execute("UPDATE KB_Hexes set IsTown = 1 WHERE ID = ?", (hex_id,))
            await cursor.execute(
                "Insert into A_Audit_All (Author, Timestamp, Database_Changed, Modification, Reason) VALUES (?, ?, ?, ?, ?)",
                (author, datetime.datetime.now(), "kb_settlements", "Claim", f"Claimed the settlement of {settlement}"))
            await db.commit()
            return f"The settlement of {settlement} has been claimed by {kingdom}."
    except (aiosqlite.Error, TypeError, ValueError) as e:
        logging.exception(f"Error claiming settlement: {e}")
        return "An error occurred while claiming the settlement."


async def relinquish_settlement(
        guild_id: int,
        author: int,
        kingdom: str,
        settlement: str) -> str:
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute("SELECT Kingdom, Hex_ID FROM kb_settlements WHERE Settlement = ?", (settlement,))
            settlement_info = await cursor.fetchone()
            if settlement_info is None:
                return "The settlement is not claimed."
            await cursor.execute("DELETE FROM KB_Buildings WHERE Kingdom = ? and Settlement = ?", (kingdom, settlement))
            await cursor.execute("DELETE FROM kb_settlements WHERE Settlement = ?", (settlement,))
            await cursor.execute("DELETE FROM kb_settlements_Custom WHERE Settlement = ?", (settlement,))
            await cursor.execute("DELETE FROM kb_turn_history_settlement WHERE Settlement = ?", (settlement,))
            await cursor.execute("DELETE FROM kb_turn_penalty_settlement WHERE Settlement = ?", (settlement,))
            await cursor.execute("UPDATE KB_Hexes set IsTown = 0 WHERE ID = ?", (settlement_info[1],))
            await cursor.execute(
                "Insert into A_Audit_All (Author, Timestamp, Database_Changed, Modification, Reason) VALUES (?, ?, ?, ?, ?)",
                (author, datetime.datetime.now(), "kb_settlements", "relinquish",
                 f"Unclaimed the settlement of {settlement}"))
            await db.commit()
            return f"The settlement of {settlement} has been unclaimed by {kingdom}."
    except (aiosqlite.Error, TypeError, ValueError) as e:
        logging.exception(f"Error unclaiming settlement: {e}")
        return "An error occurred while unclaiming the settlement."


async def add_blueprint(
        guild_id,
        author,
        full_name,
        building_type,
        subtype,
        quality,
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
        description,
        discount,
        tier
) -> str:  # This will add a new blueprint for players to use.
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute("""select building FROM Buildings_Blueprints where building = ? LIMIT 1;""",
                                 (full_name,))
            result = await cursor.fetchone()
            if result is None:
                await cursor.execute(
                    """
                    INSERT INTO Buildings_Blueprints
                    (full_name, type, subtype, quality, build_points, lots, 
                    economy, loyalty, stability, fame, unrest, 
                    corruption, crime, productivity, law, lore, society, danger, defence, 
                    base_value, spell_casting, supply, settlement_limit, district_limit, description,
                    discount, tier) 
                    VALUES 
                    (?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?,
                    ?, ?
                    );""",
                    (full_name, building_type, subtype, quality, build_points, lots, economy, loyalty, stability, fame, unrest,
                     corruption, crime, productivity, law, lore, society, danger, defence, base_value,
                     spellcasting, supply, settlement_limit, district_limit, description, discount, tier))
                await cursor.execute(
                    """Insert into A_Audit_All (Author, Timestamp, Database_Changed, Modification, Reason) VALUES (?, ?, ?, ?, ?)""",
                    (author, datetime.datetime.now(), "Blueprints", "Create", f"Created the blueprints of {full_name}"))
                await db.commit()
                function_status = f"Congratulations you have allowed the construction of **{full_name}**.**"
                return function_status
            else:
                function_status = f"you have already allowed the construction of **{full_name}**"
                return function_status
    except (TypeError, ValueError, aiosqlite.Error) as error:
        logging.exception(f"Error in add_blueprint: {error}")
        return "An error occurred while adding a blueprint."


async def remove_blueprint(
        guild_id: int,
        author: int,
        building: str) -> str:  # This will remove a blueprint from play.
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute("select Building FROM Buildings_Blueprints WHERE Building = ?", (building,))
            result = await cursor.fetchone()
            if result is None:
                status = f"The building of {building} did not previously exist."
                await db.commit()
                return status
            else:
                status = f"You have done the YEETETH of this particular building which is {building}."
                await cursor.execute("Delete FROM Buildings_Blueprints WHERE Building = ?", (building,))
                await cursor.execute("Delete FROM KB_Buildings WHERE Building = ?", (building,))
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
        old_blueprint_info: BuildingInfo,
        full_name: typing.Optional[str] = None,
        type: typing.Optional[str] = None,
        subtype: typing.Optional[str] = None,
        quality: typing.Optional[str] = None,
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
        discount: typing.Optional[int] = None,
        tier: typing.Optional[int] = None,
) -> str:
    try:
        full_name = old_blueprint_info.full_name if not full_name else full_name
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()
            if full_name and full_name != old_blueprint_info.full_name:
                await cursor.execute(
                    "UPDATE KB_Buildings set building = ? where full_name = ?",
                    (full_name, old_blueprint_info.full_name))

            await cursor.execute("""UPDATE Buildings_Blueprints SET 
                    full_name = coalesce(?, full_name)
                    type = coalesce(?, type),
                    subtype = coalesce(?, subtype),
                    quality = coalesce(?, quality),
                    build_points = coalesce(?, build_points),
                    lots = coalesce(?, lots),
                    economy = coalesce(?, economy),
                    loyalty = coalesce(?, loyalty),
                    stability = coalesce(?, stability),
                    fame = coalesce(?, fame),
                    unrest = coalesce(?, unrest),
                    corruption = coalesce(?, corruption),
                    crime = coalesce(?, crime),
                    productivity = coalesce(?, productivity),
                    law = coalesce(?, law),
                    lore = coalesce(?, lore),
                    society = coalesce(?, society),
                    danger = coalesce(?, danger),
                    defence = coalesce(?, defence),
                    base_value = coalesce(?, base_value),
                    spell_casting = coalesce(?, spell_casting),
                    supply = coalesce(?, supply),
                    settlement_limit = coalesce(?, settlement_limit),
                    district_limit = coalesce(?, district_limit),
                    description = coalesce(?, description),
                    discount = coalesce(?, discount),
                    tier = coalesce(?, tier)
                WHERE building = ?""",
                (full_name, type, subtype, quality, build_points, lots, economy, loyalty,
                 stability, fame, unrest, corruption, crime, productivity, law, lore,
                 society, danger, defence, base_value, spell_casting,
                 supply, settlement_limit, district_limit, description,
                 discount, tier, old_blueprint_info.full_name))


            await cursor.execute(
                "Insert into A_Audit_All (Author, Timestamp, Database_Changed, Modification, Reason) VALUES (?, ?, ?, ?, ?)",
                (author, datetime.datetime.now(), "Blueprints", "Update", f"Updated the blueprints of {full_name}"))
            await db.commit()
            return f"Updated blueprints for {full_name}."
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
        full_name: str,
        improvement_type: int,
        subtype: int,
        quality: int,
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
        water: int,
        source: int,
        size: int

) -> str:
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute("""select Improvement from KB_Hexes_Improvements where Improvement = ?""",
                                 (full_name,))
            result = await cursor.fetchone()
            if result is None:
                await cursor.execute(
                    """INSERT INTO KB_Hexes_Improvements (
                    Full_Name, Type, Subtype, Quality, Build_Points, Economy, Loyalty, Stability, Unrest, Consumption, Defence, Taxation, Cavernous, Coastline, Desert, Forest, Hills, Jungle, Marsh, Mountain, Plains, Water, source, size) 
                    VALUES 
                    (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ;""",
                    (full_name, improvement_type, subtype, quality, build_points, economy, loyalty, stability, unrest, consumption,
                     defence, taxation, cavernous, coastline, desert, forest, hills, jungle, marsh, mountain, plains,
                     water, source, size))
                await cursor.execute(
                    """Insert into A_Audit_All (Author, Timestamp, Database_Changed, Modification, Reason) VALUES (?, ?, ?, ?, ?)""",
                    (author, datetime.datetime.now(), "KB_Hexes_Improvements", "Create",
                     f"Created the hex improvement of {full_name}"))
                await db.commit()
                status = f"You have allowed the creation the new hex improvement: {full_name}!"
                return status
            else:
                status = f"You cannot add a improvement with the same name of {full_name}!"
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
            await cursor.execute("""select Full_name FROM KB_Hexes_Improvements WHERE Full_name = ?""",
                                 (improvement,))
            result = await cursor.fetchone()
            if result is None:
                status = f"The improvement of {improvement} did not previously exist."
                await db.commit()
                return status
            else:
                await cursor.execute("""Delete FROM KB_Hexes_Improvements WHERE Full_name = ?""", (improvement,))
                await cursor.execute("delete from kb_hexes_constructed where full_name = ?", (improvement,))
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
        old_hex_info: HexImprovementInfo,
        full_name: typing.Optional[str] = None,
        improvement_type: typing.Optional[int] = None,
        subtype: typing.Optional[int] = None,
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
        mountain: typing.Optional[int] = None,
        plains: typing.Optional[int] = None,
        water: typing.Optional[int] = None,
        source: typing.Optional[int] = None,
        size: typing.Optional[int] = None
) -> str:
    try:

        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute("select full_name from kb_hexes_improvements where full_name = ?", (old_hex_info.full_name,))
            result = await cursor.fetchone()
            if not result:
                return "cannot find improvement to modify."
            if full_name:
                await cursor.execute("select full_name from kb_hexes_improvements where full_name = ?", (full_name,))
                dupe_name = await cursor.fetchone()
                if dupe_name:
                    return "fuck off with trying to set it to the same name as another improvement asshole."
                await cursor.execute("Update KB_Hexes_Constructed Set Full_Name = ? where full_name = ?", (full_name, old_hex_info.full_name))
            else:
                full_name = old_hex_info.full_name
            await cursor.execute("""UPDATE Kb_Hexes_Improvements SET 
                Full_name = Coalesce(?, full_name),
                type = Coalesce(?, type),
                subtype = Coalesce(?, subtype),
                quality = Coalesce(?, quality),
                Build_Points = Coalesce(?, Build_Points),
                Economy = Coalesce(?, Economy),
                Loyalty = Coalesce(?, Loyalty),
                Stability = Coalesce(?, Stability),
                Unrest = Coalesce(?, Unrest),
                Consumption = Coalesce(?, Consumption),
                Defence = Coalesce(?, Defence),
                Taxation = Coalesce(?, Taxation),
                Cavernous = Coalesce(?, Cavernous),
                Coastline = Coalesce(?, Coastline),
                Desert = Coalesce(?, Desert),
                Forest = Coalesce(?, Forest),
                Hills = Coalesce(?, Hills),
                Jungle = Coalesce(?, Jungle),
                Marsh = Coalesce(?, Marsh),
                Mountain = Coalesce(?, Mountain),
                Plains = Coalesce(?, Plains),
                Water = Coalesce(?, Water),
                Source = Coalesce(?, Source),
                Size = Coalesce(?, Size)
            WHERE full_name = ?
            """,(full_name, improvement_type, subtype, quality, build_points, economy, loyalty, stability,
                 unrest, consumption, defence, taxation, cavernous, coastline, desert, forest, hills, jungle, marsh,
                 mountain, plains, water, source, size))
            await db.commit()
            return f"Improvement of {full_name} successfully modified."
    except (TypeError, ValueError, aiosqlite.Error) as e:
        logging.exception(f"Error in modify_hex_improvements: {e}")
        return "An error occurred while modifying a hex improvement."




async def add_hex(
        guild_id: int,
        kingdom: typing.Optional[str],
        terrain: str,
        region: str,
        farm: int,
        ore: int,
        stone: int,
        wood: int,
        fish: int,
        randomize: bool = False
) -> str:
    try:
        if randomize:
            farm = random.randint(1, farm)
            ore = random.randint(1, ore)
            stone = random.randint(1, stone)
            wood = random.randint(1, wood)
            fish = random.randint(1, fish)
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()
            if kingdom:
                await cursor.execute("SELECT kingdom FROM KB_Kingdoms WHERE Kingdom = ?", (kingdom,))
                kingdom_info = await cursor.fetchone()
                if not kingdom_info:
                    return f"The kingdom of {kingdom} does not exist."
            await cursor.execute(
                "INSERT INTO KB_Hexes (Kingdom, Hex_Terrain, Region, Farm, Ore, Stone, wood, fish) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (kingdom, terrain, region, farm, ore, stone, wood, fish))
            await cursor.execute("SELECT Max(ID) from KB_Hexes")
            hex_id = await cursor.fetchone()
            if kingdom:
                status = f"The hex with ID {hex_id[0]} has been created and added to the kingdom of {kingdom}!\r\nit can support {farm} farms, {ore} mines, {stone} quarries, {wood} woodcutters and {fish} fisheries."
            else:
                status = f"The hex with ID {hex_id[0]} has been created!\r\nit can support {farm} farms, {ore} mines, {stone} quarries, {wood} woodcutters and {fish} fisheries."
            await db.commit()
            return status
    except(TypeError, ValueError, aiosqlite.Error) as e:
        logging.exception(f"Error in add_hex: {e}")
        return "An error occurred while adding a hex."


async def edit_hex(
        guild_id: int,
        hex_id: int,
        kingdom: typing.Optional[str] = None,
        terrain: typing.Optional[str] = None,
        region: typing.Optional[str] = None,
        farm: typing.Optional[int] = None,
        ore: typing.Optional[int] = None,
        stone: typing.Optional[int] = None,
        wood: typing.Optional[int] = None,
        fish: typing.Optional[int] = None,
        randomize: bool = False
) -> str:
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute(
                "SELECT Kingdom, Region, Hex_Terrain, Farm, Ore, Stone, Wood, Fish From KB_Hexes where ID = ?",
                (hex_id,))
            hex_info = await cursor.fetchone()
            if not hex_info:
                return "The hex with that ID does not exist."
            
            old_kingdom = hex_info[0]
            change_kingdom = kingdom if kingdom else old_kingdom
            change_kingdom = None if change_kingdom == "None" else change_kingdom
            
            new_region = region if region else hex_info[1]
            new_terrain = terrain if terrain else hex_info[2]

            if randomize:
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
                "UPDATE KB_Hexes SET Kingdom = ?, Hex_Terrain = ?, Region = ?, Farm = ?, Ore = ?, Stone = ?, wood = ?, fish = ? WHERE ID = ?",
                (change_kingdom, new_terrain, new_region, farm, ore, stone, wood, fish, hex_id))
            await cursor.execute("UPDATE KB_Hexes_Constructed SET Kingdom = ? WHERE ID = ?", (change_kingdom, hex_id))
            
            status = ""
            if change_kingdom != old_kingdom:
                if change_kingdom:
                    status = f"The hex with ID {hex_id} has been updated and added to the kingdom of {change_kingdom}!"
                else:
                    status = f"The hex with ID {hex_id} has been updated and removed from the original kingdom!"
            else:
                status = f"The hex with ID {hex_id} has been updated!"
            
            status += f"\r\nit can support {farm} farms, {ore} mines, {stone} quarries, {wood} woodcutters, and {fish} fisheries."
            await db.commit()
            return status
    except(TypeError, ValueError, aiosqlite.Error) as e:
        logging.exception(f"Error in edit_hex: {e}")
        return "An error occurred while editing a hex."


async def delete_hex(guild_id: int, hex_id: int) -> str:
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute("SELECT Kingdom from KB_Hexes where ID = ?", (hex_id,))
            kingdom = await cursor.fetchone()
            if not kingdom:
                return "The hex with that ID does not exist."
            await cursor.execute("DELETE FROM KB_Hexes where ID = ?", (hex_id,))
            await cursor.execute("DELETE FROM KB_Hexes_Constructed where ID = ?", (hex_id,))
            await db.commit()
            return f"The hex with ID {hex_id} has been deleted."
    except(TypeError, ValueError, aiosqlite.Error) as e:
        logging.exception(f"Error in delete_hex: {e}")
        return "An error occurred while deleting a hex."


async def create_event(
        guild_id: int,
        name: str,
        scale: int,
        likelihood: int,
        description: str,
        special: typing.Optional[str],
        type: int,
        first_check: typing.Optional[int],
        second_check: typing.Optional[int],
        region: str = 'All',
        hex_affect: int = 0,
        requirements: int = 0
) -> str:
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute("SELECT Name from KB_Events where Name = ?", (name,))
            event = await cursor.fetchone()
            if event:
                return "An event with that name already exists."
            
            if second_check and not first_check:
                if second_check == 4 or second_check == 5:
                     return "You must select a first check to demand a building or improvement."
                first_check = second_check
                second_check = None

            await cursor.execute(
                "INSERT INTO KB_Events (scale, likelihood, Region, Name, Effect, Special, Type, Check_A, Check_b, Hex, Success_Requirements) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (scale, likelihood, region, name, description, special, type, first_check,
                 second_check, hex_affect, requirements))
            await db.commit()
            return f"Event {name} created successfully."
    except (TypeError, ValueError, aiosqlite.Error) as e:
        logging.exception(f"Error in create_event: {e}")
        return "An error occurred while creating an event."


async def modify_event(
        guild_id: int,
        old_name: str,
        scale: typing.Optional[int],
        likelihood: typing.Optional[int],
        new_name: typing.Optional[str],
        description: typing.Optional[str],
        special: typing.Optional[str],
        type: typing.Optional[int],
        first_check: typing.Optional[int],
        second_check: typing.Optional[int],
        region: typing.Optional[str],
        hex_affect: typing.Optional[int],
        requirements: typing.Optional[int]
) -> str:
    try:
         async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute(
                "SELECT Scale, Likelihood, Region, Type, Name, Effect, Special, Check_A, Check_B, Success_Requirement, Duration, Bonus, Penalty, Hex from KB_Events where Name = ?",
                (old_name,))
            event = await cursor.fetchone()
            if not event:
                return "An event with that name does not exist."
            (
                info_scale, info_likelihood, info_region, info_type, info_name, info_effect, info_special,
                info_check_a,
                info_check_b, info_requirements, info_duration, info_bonus, info_penalty, info_hex) = event
            
            scale = scale if scale is not None else info_scale
            likelihood = likelihood if likelihood is not None else info_likelihood
            region = region if region else info_region
            name = new_name if new_name else info_name
            description = description if description else info_effect
            special = special if special else info_special
            type = type if type is not None else info_type
            first_check = first_check if first_check is not None else info_check_a
            second_check = second_check if second_check is not None else info_check_b
            hex_affect = hex_affect if hex_affect is not None else info_hex
            requirements = requirements if requirements is not None else info_requirements

            if second_check and not first_check:
                if second_check == 4 or second_check == 5:
                    return "You must select a first check to demand a building or improvement."
                first_check = second_check
                second_check = None
            
            await cursor.execute(
                "UPDATE KB_Events SET name = ?, scale = ?, likelihood = ?, Region = ?, Name = ?, Effect = ?, Special = ?, Type = ?, Check_a = ?, Check_b = ?, Hex = ?, Success_Requirements = ? WHERE Name = ?",
                (name, scale, likelihood, region, name, description, special, type, first_check,
                 second_check, hex_affect, requirements, old_name))
            if new_name and new_name != old_name:
                await cursor.execute("UPDATE KB_Events_Consequence SET Name = ? WHERE Name = ?",
                                     (new_name, old_name))
            await db.commit()
            return f"Event {old_name} modified successfully."
    except (TypeError, ValueError, aiosqlite.Error) as e:
        logging.exception(f"Error in modify_event: {e}")
        return "An error occurred while modifying an event."


async def delete_event(guild_id: int, name: str) -> str:
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute("SELECT Name from KB_Events where Name = ?", (name,))
            event = await cursor.fetchone()
            if not event:
                return "An event with that name does not exist."
            await cursor.execute("DELETE FROM KB_Events where Name = ?", (name,))
            await cursor.execute("DELETE FROM KB_Events_Consequence where Name = ?", (name,))
            await db.commit()
            return f"The event with the name {name} has been deleted."
    except (TypeError, ValueError, aiosqlite.Error) as e:
        logging.exception(f"Error in delete_event: {e}")
        return "An error occurred while deleting an event."


async def create_complication(
        guild_id: int,
        name: str,
        severity: int,
        type: str,
        value: int,
        reroll: int
) -> str:
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute("SELECT Name from KB_Events where Name = ?", (name,))
            event = await cursor.fetchone()
            if not event:
                return "An event with that name does not exist."
            await cursor.execute(
                "INSERT INTO KB_Events_Consequence (Name, Severity, Type, Value, Reroll) VALUES (?, ?, ?, ?, ?)",
                (name, severity, type, value, reroll))
            await db.commit()
            await cursor.execute("SELECT MAX(ID) from KB_Events_Consequence")
            id = await cursor.fetchone()
            return f"The complication has been added to the event with ID {id[0]}."
    except (TypeError, ValueError, aiosqlite.Error) as e:
        logging.exception(f"Error in create_complication: {e}")
        return "An error occurred while creating a complication."


async def modify_complication(
        guild_id: int,
        id: int,
        name: typing.Optional[str] = None,
        severity: typing.Optional[int] = None,
        type: typing.Optional[str] = None,
        value: typing.Optional[int] = None,
        reroll: typing.Optional[int] = None
) -> str:
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute(
                "SELECT Name, Severity, Type, Value, Reroll from KB_Events_Consequence where ID = ?", (id,))
            event = await cursor.fetchone()
            if not event:
                return "A complication with that ID does not exist."
            (old_name, old_severity, old_type, old_value, old_reroll) = event
            
            name = name if name else old_name
            severity = severity if severity is not None else old_severity
            type = type if type else old_type
            value = value if value is not None else old_value
            reroll = reroll if reroll is not None else old_reroll
            
            await cursor.execute(
                "UPDATE KB_Events_Consequence SET Name = ?, Severity = ?, Type = ?, Value = ?, Reroll = ? WHERE ID = ?",
                (name, severity, type, value, reroll, id))
            await db.commit()
            return f"The complication has been modified."
    except (TypeError, ValueError, aiosqlite.Error) as e:
        logging.exception(f"Error in modify_complication: {e}")
        return "An error occurred while modifying a complication."


async def delete_complication(guild_id: int, name: str, id: int) -> str:
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute("SELECT Name from KB_Events where Name = ?", (name,))
            event = await cursor.fetchone()
            if not event:
               return "An event with that name does not exist."
            await cursor.execute("DELETE FROM KB_Events_Consequence where ID = ?", (id,))
            await db.commit()
            return "The complication has been removed."
    except (TypeError, ValueError, aiosqlite.Error) as e:
        logging.exception(f"Error in delete_complication: {e}")
        return "An error occurred while deleting a complication."


async def add_kingdom_event_entry(
    guild_id: int,
    kingdom: str,
    event: typing.Optional[str] = None,
    randomize: bool = False,
    number: int = 1
) -> str:
     try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()
            if randomize:
                await cursor.execute("SELECT Name from KB_Events ORDER BY RANDOM() LIMIT 1")
                event_row = await cursor.fetchone()
                if event_row:
                    event = event_row[0]
            
            if not event:
                 return "No event specified or found."

            await cursor.execute("SELECT Name from KB_Events where Name = ?", (event,))
            event_info = await cursor.fetchone()
            if not event_info:
                return "The event with that name does not exist."
            
            await cursor.execute("SELECT Name from KB_Kingdoms where Kingdom = ?", (kingdom,))
            kingdom_info = await cursor.fetchone()
            if not kingdom_info:
                return "The kingdom with that name does not exist."
            
            for _ in range(number):
                await cursor.execute("INSERT INTO KB_Kingdom_Events (Kingdom, Event) VALUES (?, ?)",
                                     (kingdom, event))
            await db.commit()
            return f"The event {event} has been spawned for the kingdom of {kingdom}."
     except (TypeError, ValueError, aiosqlite.Error) as e:
        logging.exception(f"Error in add_kingdom_event_entry: {e}")
        return "An error occurred while spawning an event."


async def adjust_population(
    guild_id: int,
    kingdom: str,
    population: int,
    randomize: bool = False
) -> str:
     try:
        if randomize:
             adjust_amount = random.randint(1, abs(population))
             population = -abs(adjust_amount) if population < 0 else adjust_amount
        
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute("SELECT Population from KB_Kingdoms where Kingdom = ?", (kingdom,))
            kingdom_info = await cursor.fetchone()
            if not kingdom_info:
                return "The kingdom with that name does not exist."
            
            await cursor.execute("UPDATE KB_Kingdoms SET Population = Population + ? WHERE Kingdom = ?",
                                 (population, kingdom))
            await db.commit()
            return f"The population of {kingdom} has been adjusted to {kingdom_info[0] + population}."
     except (TypeError, ValueError, aiosqlite.Error) as e:
        logging.exception(f"Error in adjust_population: {e}")
        return "An error occurred while adjusting the population."


async def set_bid(
    guild_id: int,
    region: str,
    population: int,
    randomize: bool = False
) -> str:
    try:
        if randomize:
            adjust_amount = random.randint(1, abs(population))
            population = -abs(adjust_amount) if population < 0 else adjust_amount
        
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
             cursor = await db.cursor()
             await cursor.execute("Select Region from Regions where region = ?", (region,))
             region_info = await cursor.fetchone()
             if not region_info:
                 return "The region with that name does not exist."
             
             await cursor.execute("SELECT Population from KB_Bids where Region = ?", (region,))
             bid_info = await cursor.fetchone()
             if not bid_info:
                 await cursor.execute("INSERT INTO KB_Bids (Region, Population) VALUES (?, ?)", (region, population))
             else:
                 await cursor.execute("UPDATE KB_Bids SET Population = Population + ? WHERE Region = ?",
                                      (population, region))
             await db.commit()
             return f"The population bid pool of {region} has been adjusted to {population}."
    except (TypeError, ValueError, aiosqlite.Error) as e:
         logging.exception(f"Error in set_bid: {e}")
         return "An error occurred while adjusting the bid."
