import asyncio
import datetime
import logging
import math
import random
import typing
from dataclasses import dataclass
from decimal import Decimal
from sqlite3 import Row
from typing import Optional, Any
import aiosqlite
import bcrypt
import discord
from discord import app_commands
from discord.ext import commands
from unidecode import unidecode
import shared_functions
from shared_functions import safe_add, safe_int_complex, settlement_autocomplete
from commands import character_commands

settlement_dict = {
    "Corruption": "Corruption",
    "Crime": "Crime",
    "Productivity": "Productivity",
    "Law": "Law",
    "Lore": "Lore",
    "Society": "Society",
    "Danger": "Danger",
    "Defence": "Defence",
    "Base Value": "Base_Value",
    "Spellcasting": "Spellcasting",
    "Supply": "Supply",
}
kingdom_dict = {
    "Size": "Size",
    "Population": "Population",
    "Unallocated Population": "Unallocated_Population",
    "Economy": "Economy",
    "Loyalty": "Loyalty",
    "Stability": "Stability",
    "Fame": "Fame",
    "Unrest": "Unrest",
    "Consumption": "Consumption"
}
reroll_dict = {
    0: "Set Result",
    1: "Roll Randomly",
    2: "All Buildings with same trait",
    3: "Explode result on Max",
    4: "A single instance that explodes on the max roll."
}


@dataclass
class TradeInfo:
    source_kingdom: str = None
    end_kingdom: str = None
    husbandry: int = 0
    seafood: int = 0
    produce: int = 0
    grain: int = 0
    raw_textiles: int = 0
    ore: int = 0
    stone: int = 0
    wood: int = 0
    textiles: int = 0
    metallurgy: int = 0
    woodworking: int = 0
    stoneworking: int = 0
    magical_consumables: int = 0
    magical_items: int = 0
    mundane_exotic: int = 0
    mundane_complex: int = 0


# Dataclasses
@dataclass
class KingdomInfo:
    kingdom: str
    password: Optional[str] = None
    government: Optional[str] = None
    alignment: Optional[str] = None
    control_dc: Optional[int] = None
    build_points: Optional[int] = None
    size: Optional[int] = None
    population: Optional[int] = None
    economy: Optional[int] = None
    loyalty: Optional[int] = None
    stability: Optional[int] = None
    fame: Optional[int] = None
    unrest: Optional[int] = None
    consumption: Optional[int] = None


@dataclass
class SettlementInfo:
    kingdom: str
    settlement: str
    size: Optional[int] = None
    population: Optional[int] = None
    corruption: Optional[int] = None
    crime: Optional[int] = None
    productivity: Optional[int] = None
    law: Optional[int] = None
    lore: Optional[int] = None
    society: Optional[int] = None
    danger: Optional[int] = None
    defence: Optional[int] = None
    base_value: Optional[int] = None
    spellcasting: Optional[int] = None
    supply: Optional[int] = None
    decay: Optional[int] = None


@dataclass
class BuildingInfo:
    full_name: str
    type: str
    subtype: str
    quality: int
    build_points: int
    lots: int
    economy: int
    loyalty: int
    stability: int
    fame: int
    unrest: int
    corruption: int
    crime: int
    productivity: int
    law: int
    lore: int
    society: int
    danger: int
    defence: int
    base_value: int
    spellcasting: int
    supply: int
    settlement_limit: int
    district_limit: int
    description: str
    upgrade: str
    discount: str
    tier: int


@dataclass
class HexImprovementInfo:
    full_name: str
    name: str
    subtype: str
    quality: int
    build_points: int
    economy: int
    loyalty: int
    stability: int
    unrest: int
    consumption: int
    defence: int
    taxation: int
    cavernous: int
    coastline: int
    desert: int
    forest: int
    hills: int
    jungle: int
    marsh: int
    mountains: int
    plains: int
    water: int
    source: int
    size: int


def safe_min(a, b):
    """Safely add two values together, treating None as zero and converting to Decimal if necessary."""
    # Treat None as zero
    a = a if a is not None else 0
    b = b if b is not None else 0

    # If either value is a Decimal, convert both to Decimal
    if isinstance(a, int) or isinstance(b, int):
        a = int(a)
        b = int(b)

    return max(min(a, b), 0)


def safe_sub(a, b):
    """Safely add two values together, treating None as zero and converting to Decimal if necessary."""
    # Treat None as zero
    a = a if a is not None else 0
    b = b if b is not None else 0

    # If either value is a Decimal, convert both to Decimal
    if isinstance(a, int) or isinstance(b, int):
        a = int(a)
        b = int(b)

    return a - b


# autocompletes functions for kingdom
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


# Purpose FUnctions
def encrypt_password(plain_password: str):
    # Generate a salt and hash the password
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(plain_password.encode(), salt)
    return hashed_password


def validate_password(plain_password, stored_hashed_password):
    return bcrypt.checkpw(plain_password.encode('utf-8'), stored_hashed_password)


class AttributeSelect(discord.ui.Select):
    def __init__(self, options):
        super().__init__(
            placeholder='Select an Attribute...',
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer()
            self.view.attribute = self.values[0]
            # Remove the attribute select from the view
            self.view.clear_items()
            # Proceed to modifier selection
            await self.view.proceed_to_modifier_selection()
        except Exception as e:
            logging.exception(f"Error in AttributeSelect callback: {e}")
            await interaction.followup.send(
                "An error occurred while selecting the attribute.", ephemeral=True
            )
            self.view.stop()


class LeadershipModifier(discord.ui.Select):
    def __init__(self, options):
        super().__init__(
            placeholder='Select a kingdom stat to modify...',
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer()
            selected_modifier = self.values[0]
            modifier_value = getattr(self.view, selected_modifier.lower())
            # Update the modified value
            setattr(self.view, f'{selected_modifier.lower()}_modified', modifier_value)
            self.view.modifier_selection_count += 1
            # Remove previous modifier select
            self.view.clear_items()
            # Proceed to the next modifier selection
            await self.view.proceed_to_modifier_selection()
        except Exception as e:
            logging.exception(f"Error in  LeadershipModifier callback: {e}")
            await interaction.followup.send(
                "An error occurred while selecting the modifier.", ephemeral=True
            )
            self.view.stop()


class LeadershipView(discord.ui.View):
    def __init__(self, options, guild_id: int, user_id: int, kingdom: str, role: str,
                 character_name: str, additional: int, economy: float, loyalty: float,
                 stability: float, hexes: int, modifier: int, recipient_id: int, content: str,
                 interaction: discord.Interaction):
        super().__init__()
        self.options = options  # Store options
        self.guild_id = guild_id
        self.user_id = user_id
        self.kingdom = kingdom
        self.role = role
        self.character_name = character_name
        self.economy = economy
        self.economy_modified = 0
        self.loyalty = loyalty
        self.loyalty_modified = 0
        self.stability = stability
        self.stability_modified = 0
        self.hexes = hexes
        self.recipient_id = recipient_id
        self.additional = additional
        self.modifier_selection_count = 0  # Counter for modifiers selected
        self.modifier = modifier
        self.interaction = interaction
        self.message = None
        self.content = content

        # Determine which modifiers are applicable
        self.modifier_fields = []
        if self.economy > 0:
            self.modifier_fields.append('Economy')
        if self.loyalty > 0:
            self.modifier_fields.append('Loyalty')
        if self.stability > 0:
            self.modifier_fields.append('Stability')
        print(self.modifier_fields, len(self.modifier_fields), options, len(options))
        # Attribute Selection
        if options is None or len(options) == 0:
            self.stop()
        elif len(options) == 1:
            asyncio.create_task(self.send_initial_message())
            print("singular attribute")
            self.attribute = options[0].value
            # Proceed to modifier selection
            asyncio.create_task(self.proceed_to_modifier_selection())
        else:
            asyncio.create_task(self.send_initial_message())
            # Multiple attributes, show selection
            print("Multiple attributes")
            self.add_item(AttributeSelect(options=options))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "You cannot interact with this button.",
                ephemeral=True
            )
            return False
        return True

    async def send_initial_message(self):
        await self.interaction.followup.send(
            "Please select an attribute to modify:",
            view=self
        )
        self.message = await self.interaction.original_response()

    async def proceed_to_modifier_selection(self):
        print(self.modifier_selection_count, self.modifier_fields, len(self.modifier_fields))
        if self.modifier_selection_count < len(self.modifier_fields) and self.additional > 0:
            # Create options for modifiers

            options = [
                discord.SelectOption(label=field, value=field)
                for field in self.modifier_fields
                if getattr(self, f'{field.lower()}_modified') == 0  # Skip already selected
            ]
            print(options)
            if options:
                # Remove previous modifier select if exists
                for child in self.children.copy():
                    if isinstance(child, LeadershipModifier):
                        self.remove_item(child)
                # Add new modifier select
                self.add_item(LeadershipModifier(options=options))
                # Edit the message to update the view
                message = await self.interaction.original_response()
                await message.edit(content="Please select a kingdom stat to modify:", view=self)
                self.additional -= 1
            else:
                # All modifiers selected
                await self.finish_selection()
        else:
            # No modifiers to select
            await self.finish_selection()

    async def finish_selection(self):
        # Remove all items from the view
        self.clear_items()
        # Provide feedback to the user
        confirmation_message = (
            f"You have completed the selection process for your role '{self.role}' "
            f"in kingdom '{self.kingdom}'."
        )
        # Update the leader with the selected attributes and modifiers
        try:
            await update_leader(
                guild_id=self.guild_id,
                author=self.user_id,
                kingdom=self.kingdom,
                title=self.role,
                character_name=self.character_name,
                stat=self.attribute,
                modifier=self.modifier,
                player_id=self.recipient_id,
                economy=self.modifier if self.economy_modified else 0,
                loyalty=self.modifier if self.loyalty_modified else 0,
                stability=self.modifier if self.stability_modified else 0
            )
            # Edit the original message to show confirmation
            await self.message.edit(content=confirmation_message, view=None)
        except Exception as e:
            logging.exception(f"Error in finish_selection: {e}")
            # Inform the user of the error
            await self.message.edit(
                content="An error occurred while updating your leadership role.", view=None
            )
        # Stop the view
        self.stop()


async def create_a_kingdom(
        guild_id: int,
        author: str,
        kingdom: str,
        region: str,
        password: str,
        government: str,
        alignment: str) -> str:
    try:
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
            print(alignment_type)
            if alignment_type is None:
                return "Invalid alignment."
            await cursor.execute("""select Government FROM AA_Government WHERE Government = ?""", (government,))
            government_type = await cursor.fetchone()
            if government_type is None:
                return "Invalid government type."
            if alignment_type is not None and kingdom_presence is None and government_type is not None:
                (economy, loyalty, stability) = alignment_type
                await cursor.execute("""
                INSERT INTO kb_Kingdoms (
                Kingdom, Password, Government, Alignment, Region, Size, Population, 
                Economy, Loyalty, Stability, 
                Fame, Unrest, Consumption,
                Control_DC, Build_Points,
                Stored_seafood, Stored_meat, Stored_grain, Stored_produce,
                Holiday, Promotion, Taxation, Improvements, Buildings,
                Buildings_Housing, Claims, Available_Population, Phase
                ) VALUES (
                ?, ?, ?, ?, ?, 0, 0, 
                ?, ?, ?,
                0, 0, 0,
                0, 0,
                0, 0, 0, 0,
                0, 0, 0, 0, 0,
                0, 0, 0, 0
                )
                """, (kingdom, hashed_password, government, alignment, region, economy, loyalty, stability))
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
        INSERT INTO KB_Building_Permits (Kingdom, Full_Name)
        SELECT ?, Full_Name FROM KB_Buildings_Blueprints WHERE Tier = 0
        """, (kingdom,))
    except (aiosqlite.Error, TypeError, ValueError) as e:
        logging.exception(f"Error generating permissions: {e}")
        return f"An error occurred while generating permissions. {e}"


async def edit_a_kingdom(
        guild_id: int,
        author: str,
        old_kingdom_info: KingdomInfo,
        new_kingdom: str,
        government: str,
        alignment: str) -> str:
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
                "UPDATE kb_Kingdoms SET Kingdom = ?, Password = ?, Government = ?, Alignment = ?, Economy = ?, Loyalty = ?, Stability = ? WHERE Kingdom = ?",
                (
                    new_kingdom,
                    old_kingdom_info.password,
                    government,
                    alignment,
                    old_kingdom_info.economy,
                    old_kingdom_info.loyalty,
                    old_kingdom_info.stability,
                    old_kingdom_info.kingdom))
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
            await cursor.execute("DELETE FROM kb_settlements WHERE Kingdom = ?", (kingdom,))
            await cursor.execute("DELETE FROM kb_settlements_Custom WHERE Kingdom = ?", (kingdom,))
            await cursor.execute("Update FROM kb_hexes Set Kingdom = Null, IsTown = 0 WHERE Kingdom = ?", (kingdom,))
            await cursor.execute("DELETE FROM KB_Trade WHERE Source_Kingdom = ? OR End_Kingdom = ?", (kingdom, kingdom))
            await cursor.execute("DELETE FROM KB_Buildings_Permits WHERE Kingdom = ?", (kingdom,))
            await cursor.execute("DELETE FROM KB_Leadership WHERE Kingdom = ?", (kingdom,))
            await cursor.execute("DELETE FROM KB_Armies WHERE Kingdom = ?", (kingdom,))
            await cursor.execute("DELETE FROM KB_Events_Active where Kingdom = ?", (kingdom,))
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


"""
async def adjust_sp(
        guild_id: int,
        author: int,
        kingdom: str,
        amount: int) -> str:
    try:
        async with shared_functions.config_cache.lock:
            configs = shared_functions.config_cache.cache.get(guild_id)
            if configs:
                decay_bool = configs.get('Decay')
        if decay_bool == 'False':
            return "Decay is disabled on this server."
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute("SELECT Stabilization_Points FROM kb_Kingdoms WHERE Kingdom = ?", (kingdom,))
            kingdom_info = await cursor.fetchone()
            if kingdom_info is None:
                return "The kingdom does not exist."
            if amount < 0:
                amount = min(amount, -kingdom_info[0])
            await cursor.execute(
                "UPDATE kb_Kingdoms SET Stabilization_Points = Stabilization_Points + ? WHERE Kingdom = ?",
                (amount, kingdom))
            await cursor.execute(
                "Insert into A_Audit_All (Author, Timestamp, Database_Changed, Modification, Reason) VALUES (?, ?, ?, ?, ?)",
                (author, datetime.datetime.now(), "kb_Kingdoms", "Increase SP",
                 f"Increased the stabilization points of {kingdom} by {amount}"))
            await db.commit()
            return f"The stabilization points of {kingdom} have been increased by {amount}."
    except (aiosqlite.Error, TypeError, ValueError) as e:
        logging.exception(f"Error increasing stabilization points: {e}")
        return "An error occurred while increasing stabilization points."
"""


async def fetch_kingdom(
        guild_id: int,
        kingdom: str) -> typing.Union[KingdomInfo, None]:
    async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
        cursor = await db.cursor()
        await cursor.execute(
            """SELECT Kingdom, Password, Government, Alignment, Control_DC, Build_Points, Size, Population, Economy, Loyalty, Stability, Fame, Unrest, Consumption FROM kb_Kingdoms WHERE Kingdom = ?""",
            (kingdom,))
        kingdom_info = await cursor.fetchone()
        if kingdom_info is not None:
            return KingdomInfo(*kingdom_info)
        return None


async def fetch_kingdom_hex_state(
        db: aiosqlite.Connection,
        kingdom: str) -> typing.Union[KingdomInfo, None]:
    try:
        cursor = await db.cursor()
        await cursor.execute("""
        SELECT 
        SUM(KH.Amount * KBB.Economy) as economy, 
        SUM(KH.Amount * KBB.Loyalty) as Loyalty, 
        SUM(KH.Amount * KBB.Stability) as Stability, 
        SUM(KH.Amount * KBB.Unrest) as Unrest, 
        SUM(KH.Amount * KBB.Consumption) as Consumption, 
        SUM(KH.Amount * KBB.Taxation) as Taxation 
        FROM KB_Buildings KB
        JOIN KB_Buildings_Blueprints KBB ON KB.Full_name = KBB.Full_Name
        WHERE KB.Kingdom = ?
        GROUP BY Settlement
        """, (kingdom,))
        building_results = await cursor.fetchone()
        (total_economy, total_loyalty, total_stability,
         total_unrest, total_consumption, total_taxation) = building_results
        await cursor.execute("""
        SELECT Count(ID) from KB_Hexes
        WHERE Kingdom = ?
        """, (kingdom,))
        hex_count = await cursor.fetchone()
        control_dc = 0 if not hex_count else hex_count[0]

        kingdom_info = KingdomInfo(
            kingdom=kingdom,
            control_dc=control_dc,
            economy=total_economy,
            loyalty=total_loyalty,
            stability=total_stability,
            unrest=total_unrest,
            consumption=total_consumption,
            build_points=total_taxation
        )
        return kingdom_info
    except Exception as e:
        logging.exception(f"Error fetching building state: {e}")
        return None


async def fetch_kingdom_building_state(
        db: aiosqlite.Connection,
        kingdom: str) -> typing.Union[KingdomInfo, None]:
    try:
        cursor = await db.cursor()
        await cursor.execute("""
        SELECT Settlement,
        SUM(KB.Amount * KBB.Lots) as lots, 
        SUM(KB.Amount * KBB.Economy) as economy, 
        SUM(KB.Amount * KBB.Loyalty) as Loyalty, 
        SUM(KB.Amount * KBB.Stability) as Stability, 
        SUM(KB.Amount * KBB.Fame) as Fame, 
        SUM(KB.Amount * KBB.unrest) as Unrest, 
        SUM(KB.Amount * KBB.Supply) as Supply 
        FROM KB_Buildings KB
        JOIN KB_Buildings_Blueprints KBB ON KB.Full_name = KBB.Full_Name
        WHERE KB.Kingdom = ?
        GROUP BY Settlement
        """, (kingdom,))
        building_results = await cursor.fetchall()
        total_control_dc = 0
        total_economy = 0
        total_loyalty = 0
        total_stability = 0
        total_fame = 0
        total_unrest = 0
        total_supply = 0
        for result in building_results:
            (settlement, lots, economy, loyalty, stability, fame, unrest, supply) = result
            total_control_dc += math.floor(lots / 36) + 1
            total_economy += economy
            total_loyalty += loyalty
            total_stability += stability
            total_fame += fame
            total_unrest += unrest
            total_supply += supply
        kingdom_info = KingdomInfo(
            kingdom=kingdom,
            economy=total_economy,
            loyalty=total_loyalty,
            stability=total_stability,
            fame=total_fame,
            unrest=total_unrest,
            control_dc=total_control_dc
        )
        return kingdom_info
    except Exception as e:
        logging.exception(f"Error fetching building state: {e}")
        return None


async def fetch_kingdom_event_list(
        db: aiosqlite.Connection,
        kingdom: str,
        offset: int = 0,
        limit: int = 1000
) -> typing.Iterable[Row] | None:
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
        army_list = ', '.join(army_list)
        return total_army_cost, army_list
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
    await cursor.execute("""
    SELECT 
    KB.Settlement, SUM(KBB.Lots * KB.Amount) as Lots
    FROM KB_Buildings KB
    LEFT JOIN KB_Buildings_Blueprints KBB ON KB.Full_Name = KBB.Full_Name
    WHERE KB.Kingdom = ?
    GROUP BY KB.Settlement
    """, (kingdom,))
    results = await cursor.fetchall()
    luxury_requirements = 0
    double_luxury_requirements = 0
    goods_requirements = 0
    for result in results:
        (settlement, lots) = result
        luxury_requirements += lots // 8 if lots < 40 else 0
        double_luxury_requirements += lots // 4 if lots <= 40 else 0
        goods_requirements = lots // 20
    grain = safe_int_complex(
        incoming_trade.grain,
        -outgoing_trade.grain,
        building_info.grain,
        hex_info.grain)
    produce = safe_int_complex(
        incoming_trade.produce,
        -outgoing_trade.produce,
        building_info.produce,
        hex_info.produce)
    husbandry = safe_int_complex(
        incoming_trade.husbandry,
        -outgoing_trade.husbandry,
        building_info.husbandry,
        hex_info.husbandry)
    seafood = safe_int_complex(
        incoming_trade.seafood,
        -outgoing_trade.seafood,
        building_info.seafood,
        hex_info.seafood)
    ore = safe_int_complex(
        incoming_trade.ore,
        -outgoing_trade.ore,
        -math.floor(building_info.metallurgy / 2),
        hex_info.ore)
    wood = safe_int_complex(
        incoming_trade.wood,
        -outgoing_trade.wood,
        -math.floor(building_info.woodworking / 2),
        hex_info.wood)
    stone = safe_int_complex(
        incoming_trade.stone,
        -outgoing_trade.stone,
        -math.floor(building_info.stoneworking / 2),
        hex_info.stone)
    raw_textiles = safe_int_complex(
        incoming_trade.raw_textiles,
        -outgoing_trade.raw_textiles,
        --math.floor(building_info.textiles / 2),
        hex_info.raw_textiles)
    stoneworking = safe_int_complex(
        incoming_trade.stoneworking,
        -outgoing_trade.stoneworking,
        building_info.stoneworking,
        -goods_requirements)
    woodworking = safe_int_complex(
        incoming_trade.woodworking,
        -outgoing_trade.woodworking,
        building_info.woodworking,
        -goods_requirements)
    metallurgy = safe_int_complex(
        incoming_trade.metallurgy,
        -outgoing_trade.metallurgy,
        building_info.metallurgy,
        -goods_requirements)
    textiles = safe_int_complex(
        incoming_trade.textiles,
        -outgoing_trade.textiles,
        building_info.textiles,
        -goods_requirements)
    magical_consumables = safe_int_complex(
        incoming_trade.magical_consumables,
        -outgoing_trade.magical_consumables,
        building_info.magical_consumables,
        hex_info.magical_consumables)
    magical_items = safe_int_complex(
        incoming_trade.magical_items,
        -outgoing_trade.magical_items,
        building_info.magical_items,
        hex_info.magical_items)
    mundane_exotic = safe_int_complex(
        incoming_trade.mundane_exotic,
        -outgoing_trade.mundane_exotic,
        building_info.mundane_exotic,
        hex_info.mundane_exotic)
    mundane_complex = safe_int_complex(
        incoming_trade.mundane_complex,
        -outgoing_trade.mundane_complex,
        building_info.mundane_complex,
        hex_info.mundane_complex)
    resource_utilization_dict = {"Grain": max(0, grain), "Produce": max(0, produce), "Husbandry": max(0, husbandry),
                                 "Seafood": max(0, seafood)}
    if consumption > sum(resource_utilization_dict.values()):
        deficit = consumption - sum(resource_utilization_dict.values())
        grain -= min(max(deficit, consumption * .15 - grain), math.floor(consumption * .5))
        produce -= min(max(deficit, consumption * .15 - produce), math.floor(consumption * .5))
        husbandry -= min(max(deficit, consumption * .15 - husbandry), math.floor(consumption * .5))
        seafood -= min(max(deficit, consumption * .15 - seafood), math.floor(consumption * .5))
    else:
        resource_allocation = shared_functions.allocate_food(consumption, resource_utilization_dict)
        grain -= max(resource_allocation["Grain"], math.floor(consumption * .15))
        produce -= max(resource_allocation["Produce"], math.floor(consumption * .15))
        husbandry -= max(resource_allocation["Husbandry"], math.floor(consumption * .15))
        seafood -= max(resource_allocation["Seafood"], math.floor(consumption * .15))
    total_luxury = magical_consumables + magical_items + mundane_exotic + mundane_complex
    raw_usable = min(ore, total_luxury * .5) + min(wood, total_luxury * .5) + min(stone, total_luxury * .5) + min(
        raw_textiles, total_luxury * .5)
    if raw_usable < total_luxury:
        remaining_required = total_luxury - raw_usable
        ore -= min(max(ore, remaining_required), total_luxury * .5)
        wood -= min(max(wood, remaining_required), total_luxury * .5)
        stone -= min(max(stone, remaining_required), total_luxury * .5)
        raw_textiles -= min(max(raw_textiles, remaining_required), total_luxury * .5)
    else:
        raw_material_dict = {"Ore": ore, "Wood": wood, "Stone": stone, "Raw_textiles": raw_textiles}
        raw_material_allocation = equalize_goods_integer_strict(raw_material_dict, total_luxury)
        ore -= raw_material_allocation[0]["Ore"]
        wood -= raw_material_allocation[0]["Wood"]
        stone -= raw_material_allocation[0]["Stone"]
        raw_textiles -= raw_material_allocation[0]["Raw_textiles"]
    luxury_dict = {"magic": magical_consumables + magical_items, "mundane": mundane_exotic + mundane_complex}
    magic_dict = {"Magical_Consumables": magical_consumables, "Magical_Items": magical_items}
    mundane_dict = {"Mundane_Exotic": mundane_exotic, "Mundane_Complex": mundane_complex}
    if luxury_requirements > 0:
        balanced_utilization = equalize_goods_integer_strict(luxury_dict, luxury_requirements)
        magic_requirements = balanced_utilization[0]['magic'] + double_luxury_requirements
        magic_dict = equalize_goods_integer_strict(magic_dict, magic_requirements)
        magical_consumables -= magic_dict[0]['Magical_Consumables']
        magical_items -= magic_dict[0]['Magical_Items']
        mundane_requirements = balanced_utilization[0]['mundane'] + double_luxury_requirements
        mundane_dict = equalize_goods_integer_strict(mundane_dict, mundane_requirements)
        mundane_exotic -= mundane_dict[0]['Mundane_Exotic']
        mundane_complex -= mundane_dict[0]['Mundane_Complex']
    elif double_luxury_requirements > 0:
        magic_requirements = double_luxury_requirements
        magic_dict = equalize_goods_integer_strict(magic_dict, magic_requirements)
        magical_consumables -= magic_dict[0]['Magical_Consumables']
        magical_items -= magic_dict[0]['Magical_Items']
        mundane_requirements = double_luxury_requirements
        mundane_dict = equalize_goods_integer_strict(mundane_dict, mundane_requirements)
        mundane_exotic -= mundane_dict[0]['Mundane_Exotic']
        mundane_complex -= mundane_dict[0]['Mundane_Complex']
    goods_status = TradeInfo(
        grain=grain,
        produce=produce,
        husbandry=husbandry,
        seafood=seafood,
        ore=ore,
        wood=wood,
        stone=stone,
        stoneworking=stoneworking,
        woodworking=woodworking,
        metallurgy=metallurgy,
        textiles=textiles,
        raw_textiles=raw_textiles,
        magical_consumables=magical_consumables,
        magical_items=magical_items,
        mundane_exotic=mundane_exotic,
        mundane_complex=mundane_complex
    )

    return


def equalize_goods_integer_strict(goods, utilization):
    goods = goods.copy()  # Don't modify the original
    max_value = max(goods.values())

    # Step 1: Find the best base target equalization
    for target in range(max_value, -1, -1):
        # Total consumption needed to bring all goods down to `target`
        total_used = sum(max(0, value - target) for value in goods.values())

        if total_used <= utilization:
            base_target = target
            break
    else:
        raise ValueError("Not enough resources to equalize.")

    # Step 2: Apply base target
    reduced_goods = {}
    consumption_used = {}
    total_used = 0
    for name, value in goods.items():
        reduction = max(0, value - base_target)
        reduced_goods[name] = value - reduction
        consumption_used[name] = reduction
        total_used += reduction

    # Step 3: Fine-tune by reducing highest remaining goods further
    leftover = utilization - total_used
    while leftover > 0:
        # Pick the good with the highest current value that can still be reduced
        candidates = sorted(
            [(name, val) for name, val in reduced_goods.items() if val > 0],
            key=lambda x: -x[1]
        )
        for name, _ in candidates:
            reduced_goods[name] -= 1
            consumption_used[name] += 1
            leftover -= 1
            if leftover == 0:
                break

    return reduced_goods, consumption_used, base_target


async def fetch_kingdom_trade(
        db: aiosqlite.Connection,
        source_kingdom: str = None,
        end_kingdom: str = None) -> typing.Union[TradeInfo, None]:
    try:
        if source_kingdom is None and end_kingdom is None:
            return None
        sql = """
                SELECT 
                SUM(Husbandry), 
                SUM(Seafood),
                SUM(Grain),
                SUM(Produce),
                SUM(Ore),
                SUM(Wood),
                SUM(Stone),
                SUM(Raw_textiles),
                SUM(Magical_Consumables),
                SUM(Magical_Items),
                SUM(Mundane_Exotic),
                SUM(Mundane_Complex)
                FROM KB_Trades"""
        if source_kingdom is not None and end_kingdom is not None:
            sql += "WHERE Source_Kingdom = ?"
        else:
            sql += "WHERE End_Kingdom = ?"
        cursor = await db.cursor()
        if source_kingdom is not None:
            await cursor.execute(sql, (source_kingdom,))
        else:
            await cursor.execute(sql, (end_kingdom,))
        results = await cursor.fetchall()
        (husbandry, seafood, grain, produce, ore, wood, stone, raw_textiles,
         magical_consumables, magical_items, mundane_exotic, mundane_complex) = results
        husbandry = husbandry if husbandry else 0
        seafood = seafood if seafood else 0
        grain = grain if grain else 0
        produce = produce if produce else 0
        ore = ore if ore else 0
        wood = wood if wood else 0
        stone = stone if stone else 0
        raw_textiles = raw_textiles if raw_textiles else 0
        magical_consumables = magical_consumables if magical_consumables else 0
        magical_items = magical_items if magical_items else 0
        mundane_exotic = mundane_exotic if mundane_exotic else 0
        mundane_complex = mundane_complex if mundane_complex else 0
        trade_summary = TradeInfo(
            husbandry=husbandry,
            seafood=seafood,
            grain=grain,
            produce=produce,
            ore=ore,
            wood=wood,
            stone=stone,
            raw_textiles=raw_textiles,
            magical_consumables=magical_consumables,
            magical_items=magical_items,
            mundane_exotic=mundane_exotic,
            mundane_complex=mundane_complex)
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
        SUM(case when KHC.subtype = 'Raw_textiles' then KHC.amount * KHI.quality else 0 end) as Raw_Textiles,
        FROM KB_Hexes_Construct KHC
        LEFT JOIN KB_Hexes_Improvements KHI ON KHC.Full_Name = KHI.Full_Name
        WHERE KHC.Kingdom = ?
        """, (kingdom,))
        results = await cursor.fetchall()
        (husbandry, seafood, grain, produce, ore, wood, stone, raw_textiles) = results
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
        SUM(case when KHC.subtype = 'Mundane Complex' then KHC.amount * KHI.quality else 0 end) as Mundane_Complex,
        SUM(case when KHC.subtype = 'Mundane Exotic' then KHC.amount * KHI.quality else 0 end) as Mundane_Exotic,
        SUM(case when KHC.subtype = 'Magical Consumables' then KHC.amount * KHI.quality else 0 end) as Magical_Consumables,
        SUM(case when KHC.subtype = 'Magical Items' then KHC.amount * KHI.quality else 0 end) as Magical_Items,
        FROM KB_Buildings KHC
        LEFT JOIN KB_Buildings_Blueprints KHI ON KHC.Full_Name = KHI.Full_Name
        WHERE KHC.Kingdom = ?
        """, (kingdom,))
        results = await cursor.fetchall()
        (stoneworking, metallurgy, textiles, woodworking, mundane_complex, mundane_exotic,
         magical_consumables, magical_items) = results
        stoneworking = stoneworking if stoneworking else 0
        metallurgy = metallurgy if metallurgy else 0
        textiles = textiles if textiles else 0
        woodworking = woodworking if woodworking else 0
        mundane_complex = mundane_complex if mundane_complex else 0
        mundane_exotic = mundane_exotic if mundane_exotic else 0
        magical_consumables = magical_consumables if magical_consumables else 0
        magical_items = magical_items if magical_items else 0
        total_output = TradeInfo(
            stoneworking=stoneworking,
            metallurgy=metallurgy,
            textiles=textiles,
            woodworking=woodworking,
            mundane_complex=mundane_complex,
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
            (event_id, event_type, kingdom, settlement, hex, name,
             effect, duration, check_a, check_a_status,
             check_b, check_b_status, severity) = event
            if len(response) < 800:
                base_event_list = itx
                if event_id != old_name:

                    response += f"**{name}**: {effect} \n"
                    if severity != old_severity:
                        response_tuple = []
                        await cursor.execute(
                            "SELECT Type, Value, Reroll from KB_Events_Consequences WHERE Name = ? AND Severity = ",
                            (name,))
                        consequence_list = await cursor.fetchall()
                        for consequence in consequence_list:
                            (consequence_type, value, reroll) = consequence
                            reroll_str = reroll_dict.get(reroll, "Unknown")
                            response_tuple.append(f"{consequence_type} {value} {reroll_str}")
                        response += f"**Severity: {severity}, Consequences:** {', '.join(response_tuple)}\n"
                    old_name = name
                    old_severity = severity

                response += "settlement: " + str(settlement) + "\n" if settlement else ""
                response += "hex: " + str(hex) + "\n" if hex else ""
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


async def fetch_settlement(
        guild_id: int,
        settlement: str) -> typing.Union[SettlementInfo, None]:
    async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
        cursor = await db.cursor()
        await cursor.execute(
            """SELECT Kingdom, Settlement, Size, Population, Corruption, Crime, Productivity, Law, Lore, Society, Danger, Defence, Base_Value, Spellcasting, Supply, Decay FROM kb_settlements WHERE Settlement = ?""",
            (settlement,))
        settlement_info = await cursor.fetchone()
        if settlement_info is not None:
            return SettlementInfo(*settlement_info)
        return None


async def fetch_settlement_building_state(
        db: aiosqlite.Connection,
        kingdom: str,
        settlement: str) -> typing.Union[SettlementInfo, None]:
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
        """, (kingdom,))
        building_results = await cursor.fetchall()
        (housing_total, non_housing_total, lots, corruption, crime, productivity, law, lore, society, danger, defence,
         base_value, spellcasting) = building_results

        settlement_info = SettlementInfo(
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
            (old_economy, old_loyalty, old_stability, old_unrest) = leader_info
            sum_economy = economy - old_economy
            sum_loyalty = loyalty - old_loyalty
            sum_stability = stability - old_stability
            await cursor.execute(
                "UPDATE kb_Leadership Set Character_Name = ?, Player_ID = ?, Stat = ?, Modifier = ?, Economy = ?, Loyalty = ?, Stability = ?, unrest = ? WHERE Kingdom = ? AND Title = ?",
                (character_name, player_id, stat, modifier, economy, loyalty, stability, 0, kingdom, title))
            await cursor.execute(
                "UPDATE kb_Kingdoms SET Economy = Economy + ?, Loyalty = Loyalty + ?, Stability = Stability + ?, Unrest = Unrest + ? WHERE Kingdom = ?",
                (sum_economy, sum_loyalty, sum_stability, -old_unrest, kingdom))
            await cursor.execute(
                "Insert into A_Audit_All (Author, Timestamp, Database_Changed, Modification, Reason) VALUES (?, ?, ?, ?, ?)",
                (author, datetime.datetime.now(), "kb_Leadership", "Update",
                 f"Updated the leader of {kingdom} to {character_name}"))
            await db.commit()

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
            (old_economy, old_loyalty, old_stability, old_unrest) = leader_info
            sum_economy = -old_economy + base_economy
            sum_loyalty = -old_loyalty + base_loyalty
            sum_stability = -old_stability + base_stability
            sum_unrest = -old_unrest + base_unrest
            await cursor.execute(
                "UPDATE kb_Leadership SET Character_Name = 'Vacant', Player_ID = Null, Stat = Null, Modifier = Null, Economy = ?, Loyalty = ? , Stability = ?, Unrest = ? WHERE Kingdom = ? AND Title = ?",
                (base_economy, base_loyalty, base_stability, base_unrest, kingdom, title))
            await cursor.execute(
                "UPDATE kb_Kingdoms SET Economy = Economy - ?, Loyalty = Loyalty - ?, Stability = Stability - ?, Unrest = Unrest - ? WHERE Kingdom = ?",
                (sum_economy, sum_loyalty, sum_stability, sum_unrest, kingdom))
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
                "UPDATE kb_Kingdoms SET Size = Size + 1, Control_DC = Control_DC + 1 WHERE Kingdom = ?",
                (kingdom,))
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
                "UPDATE kb_Kingdoms SET Size = Size - 1, Control_DC = Control_DC - 1 WHERE Kingdom = ?",
                (kingdom,))
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
                "SELECT Kingdom, Hex_Terrain, Farm, Ore, Stone, Wood, Istown FROM KB_Hexes WHERE ID = ?",
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
            await cursor.execute("Select Sum(Amount) From KB_Hexes_Constructed where Type = ? and ID = ?",
                                 (improvement_info['Type'], hex_id))
            constructed = await cursor.fetchone()
            constructed = constructed[0] if constructed[0] else 0
            print(improvement_info['Type'])
            if constructed >= base_hex_info[improvement_info['Type']]:
                return f"The improvement of {improvement} has reached its maximum amount. \r\nIf it is a farm You may want to convert an existing improvement to a different type."
            await cursor.execute("SELECT Amount FROM kb_hexes_constructed WHERE full_name = ? and id = ?",
                                 (improvement, hex_id))
            availability = await cursor.fetchone()
            if iscost:
                cost_modifier = improvement_info['Build_Points'] * improvement_info[f'{base_hex_info["Hex_Terrain"]}']
                max_amount = min(base_hex_info[f'{improvement_info["Type"]}'] - constructed, amount,
                                 build_points // cost_modifier)
                build_cost = max_amount * cost_modifier
            else:
                max_amount = min(base_hex_info[f'{improvement_info["Type"]}'] - constructed, amount)
                build_cost = 0
            await cursor.execute(
                "Update KB_Kingdoms Set Build_Points = Build_Points - ? WHERE Kingdom = ?",
                (build_cost, kingdom))
            if not availability:
                await cursor.execute("""
                INSERT into KB_Hexes_Constructed(ID, Full_Name, Type, Subtype, Amount) 
                VALUES 
                (?, ?, ?, ?, ?)
                """, (hex_id, improvement_info['Full_name'], improvement_info['Type'], improvement_info['Subtype'],
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
        size: int,
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
                Full_Name, Type, Subtype, 
                Amount, Discounted) 
                VALUES (
                ?, ?, 
                ?, ?, ?, 
                ?, 0)""", (
                    kingdom, settlement,
                    building_info.full_name, building_info.type, building_info.subtype,
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
        hex_id: int) -> str:
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()

            await cursor.execute(
                "INSERT INTO kb_settlements (Kingdom, Settlement, Size, Population, Corruption, Crime, Productivity, Law, Lore, Society, Danger, Defence, Base_Value, Spellcasting, Supply, Decay, hex_id) VALUES (?, ?, 1, 250, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, ?)",
                (kingdom, settlement, hex_id))
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


class KingdomCommands(commands.Cog, name='kingdom'):
    def __init__(self, bot):
        self.bot = bot

    kingdom_group = discord.app_commands.Group(
        name='kingdom',
        description='Commands related to kingdom management'
    )

    leadership_group = discord.app_commands.Group(
        name='leadership',
        description='Commands related to Leadership management',
        parent=kingdom_group
    )

    hex_group = discord.app_commands.Group(
        name='hex',
        description='Commands related to hex management',
        parent=kingdom_group
    )

    settlement_group = discord.app_commands.Group(
        name='settlement',
        description='Commands related to settlement management',
        parent=kingdom_group
    )

    edict_group = discord.app_commands.Group(
        name='edict',
        description='Commands related to edict management',
        parent=kingdom_group
    )

    @kingdom_group.command(name="create", description="Create a kingdom")
    @app_commands.autocomplete(government=government_autocompletion)
    @app_commands.autocomplete(alignment=alignment_autocomplete)
    @app_commands.autocomplete(region=shared_functions.region_autocomplete)
    async def create(
            self,
            interaction: discord.Interaction,
            kingdom: str,
            password: str,
            region: str,
            government: str,
            alignment: str):
        """This creates allows a player to create a new kingdom"""
        await interaction.response.defer(thinking=True)
        try:

            kingdom_create = await create_a_kingdom(
                guild_id=interaction.guild_id,
                author=interaction.user.name,
                kingdom=kingdom,
                alignment=alignment,
                government=government,
                region=region,
                password=password)
            await interaction.followup.send(content=kingdom_create)
        except Exception as e:
            logging.exception(f"Error creating a kingdom: {e}")
            await interaction.followup.send(content="An error occurred while creating a kingdom.")

    @kingdom_group.command(name="destroy", description="Remove a kingdom")
    @app_commands.autocomplete(kingdom=kingdom_autocomplete)
    async def destroy(self, interaction: discord.Interaction, kingdom: str, password: str):
        """This is a player command to remove a kingdom THEY OWN from play"""
        await interaction.response.defer(thinking=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute("""select Kingdom, Password FROM kb_Kingdoms where Kingdom = ?""", (kingdom,))
                result = await cursor.fetchone()
                if result is None:
                    status = f"the kingdom which you have elected to make a war crime out of couldn't be found."
                    await interaction.followup.send(content=status)
                    return
                valid_password = validate_password(password, result[1])
                if valid_password:
                    status = await delete_a_kingdom(guild_id=interaction.guild_id, author=interaction.user.id,
                                                    kingdom=kingdom)
                    await interaction.followup.send(content=status)
                else:
                    status = f"You have entered an invalid password for this kingdom."
                    await interaction.followup.send(content=status)
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"Error deleting a kingdom: {e}")
            await interaction.followup.send(content="An error occurred while deleting a kingdom.")

    @kingdom_group.command(name="edit", description="Modify a kingdom")
    @app_commands.autocomplete(old_kingdom=kingdom_autocomplete)
    @app_commands.autocomplete(new_government=government_autocompletion)
    @app_commands.autocomplete(new_alignment=alignment_autocomplete)
    async def edit_kingdom(
            self,
            interaction: discord.Interaction,
            old_kingdom: str,
            new_kingdom: typing.Optional[str],
            old_password: typing.Optional[str],
            new_password: typing.Optional[str],
            new_government: typing.Optional[str],
            new_alignment: typing.Optional[str]):
        """This is a player command to modify a kingdom THEY OWN."""
        await interaction.response.defer(thinking=True)
        try:
            kingdom_info = await fetch_kingdom(interaction.guild_id, old_kingdom)
            if not kingdom_info:
                await interaction.followup.send(content=f"The kingdom of {old_kingdom} does not exist.")
                return
            valid_password = validate_password(old_password, kingdom_info.password)
            if not valid_password:
                await interaction.followup.send(content="The password provided is incorrect.")
                return
            kingdom_info.password = encrypt_password(new_password) if new_password else kingdom_info.password
            status = await edit_a_kingdom(
                guild_id=interaction.guild_id,
                author=interaction.user.name,
                old_kingdom_info=kingdom_info,
                new_kingdom=new_kingdom,
                government=new_government,
                alignment=new_alignment)
            await interaction.followup.send(content=status)
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"Error fetching kingdom: {e}")
            await interaction.followup.send(content="An error occurred while fetching kingdom.")
            return

    @kingdom_group.command(name="build_points", description="Adjust the build points of a kingdom")
    @app_commands.autocomplete(kingdom=kingdom_autocomplete)
    @app_commands.autocomplete(character_name=shared_functions.own_character_select_autocompletion)
    async def bp(
            self,
            interaction: discord.Interaction,
            kingdom: str,
            password: str,
            character_name: str,
            amount: int):
        """This modifies the number of build points in a kingdom"""
        await interaction.response.defer(thinking=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute("SELECT Password, Build_Points FROM kb_Kingdoms WHERE Kingdom = ?", (kingdom,))
                kingdom_results = await cursor.fetchone()
                if not kingdom_results:
                    await interaction.followup.send(content=f"The kingdom of {kingdom} does not exist.")
                    return
                valid_password = validate_password(password, kingdom_results[0])
                if not valid_password:
                    await interaction.followup.send(content="The password provided is incorrect.")
                    return
                await cursor.execute(
                    "SELECT Gold, Gold_Value, Gold_Value_Max, Level, Oath, Thread_ID FROM Player_Characters WHERE Player_ID = ? AND (Character_Name = ? OR Nickname = ?)",
                    (interaction.user.id, character_name, character_name))
                character_info = await cursor.fetchone()
                if not character_info:
                    await interaction.followup.send(content=f"The character of {character_name} does not exist.")
                    return
                (gold, gold_value, gold_value_max, level, oath, thread_id) = character_info
                if amount < 0:
                    bought_points = max(amount, -kingdom_results[1])
                    cost = bought_points * 4000
                    gold_reward = await character_commands.gold_calculation(
                        guild_id=interaction.guild_id,
                        author_name=interaction.user.name,
                        author_id=interaction.user.id,
                        character_name=character_name,
                        level=character_info[3],
                        oath=character_info[4],
                        gold=Decimal(gold),
                        gold_value=Decimal(gold_value),
                        gold_value_max=Decimal(gold_value_max),
                        gold_change=Decimal(cost),
                        reason="selling build points",
                        source="Adjust BP Commands",
                        gold_value_change=Decimal(cost),
                        gold_value_max_change=Decimal(cost),
                        is_transaction=False
                    )
                    await adjust_bp(interaction.guild_id, interaction.user.id, kingdom, bought_points)

                    update_character_info = shared_functions.UpdateCharacterData(
                        character_name=character_name,
                        gold_package=(gold_reward[0], gold_reward[1], gold_reward[2])
                    )

                    update_character_log = shared_functions.CharacterChange(
                        author=interaction.user.name,
                        character_name=character_name,
                        transaction_id=gold_reward[4],
                        gold_change=gold_reward[0],
                        gold=gold_reward[1],
                        gold_value=gold_reward[2],
                        gold_value_max=gold_reward[3],
                        source=f"Adjust BP Command selling {bought_points} build points",
                    )
                    await shared_functions.update_character(interaction.guild_id, update_character_info)
                    await shared_functions.log_embed(
                        bot=self.bot,
                        thread=character_info[5],
                        guild=interaction.guild,
                        change=update_character_log)
                    await shared_functions.character_embed(guild=interaction.guild, character_name=character_name)
                    await interaction.followup.send(
                        content=f"The character of {character_name} has sold {bought_points} build points for {gold_reward[0]} GP.")
                else:
                    maximum_points = math.floor(character_info[0] / 4000)
                    bought_points = min(amount, maximum_points)
                    cost = bought_points * 4000
                    adjusted_bp_result = await adjust_bp(
                        interaction.guild_id,
                        interaction.user.id,
                        kingdom,
                        bought_points)
                    gold_used = await character_commands.gold_calculation(
                        guild_id=interaction.guild_id,
                        author_name=interaction.user.name,
                        author_id=interaction.user.id,
                        character_name=character_name,
                        level=character_info[3],
                        oath=character_info[4],
                        gold=Decimal(gold),
                        gold_value=Decimal(gold_value),
                        gold_value_max=Decimal(gold_value_max),
                        gold_change=-Decimal(cost),
                        reason="selling build points",
                        source="Adjust BP Commands",
                        gold_value_change=-Decimal(cost),
                        gold_value_max_change=Decimal(0),
                    )
                    update_character_info = shared_functions.UpdateCharacterData(
                        character_name=character_name,
                        gold_package=(gold_used[0], gold_used[1], gold_used[2])
                    )
                    update_character_log = shared_functions.CharacterChange(
                        author=interaction.user.name,
                        character_name=character_name,
                        transaction_id=gold_used[4],
                        gold_change=gold_used[0],
                        gold=gold_used[1],
                        gold_value=gold_used[2],
                        gold_value_max=gold_used[3],
                        source=f"Adjust BP Command buying {bought_points} build points",
                    )
                    await shared_functions.update_character(interaction.guild_id, update_character_info)
                    await shared_functions.log_embed(
                        bot=self.bot,
                        thread=character_info[5],
                        guild=interaction.guild,
                        change=update_character_log)
                    await shared_functions.character_embed(
                        guild=interaction.guild,
                        character_name=character_name)
                    await interaction.followup.send(adjusted_bp_result)
        except (aiosqlite, TypeError, ValueError, character_commands.CalculationAidFunctionError) as e:
            logging.exception(f"Error increasing build points: {e}")
            await interaction.followup.send(content="An error occurred while increasing build points.")

    @edict_group.command(name="set", description="set the severity of your edicts")
    @app_commands.autocomplete(kingdom=kingdom_autocomplete)
    async def set_edicts(self, interaction: discord.Interaction, kingdom: str, password: str,
                         holiday: typing.Optional[int], promotion: typing.Optional[int], taxation: typing.Optional[int]):
        """This command is used to set the severity of your edicts"""
        await interaction.response.defer(thinking=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute("SELECT Password, Holiday, Promotion, Taxation FROM kb_Kingdoms WHERE Kingdom = ?", (kingdom,))
                kingdom_results = await cursor.fetchone()
                if not kingdom_results:
                    await interaction.followup.send(content=f"The kingdom of {kingdom} does not exist.")
                    return
                valid_password = validate_password(password, kingdom_results[0])
                if not valid_password:
                    await interaction.followup.send(content="The password provided is incorrect.")
                    return
                (password, old_holiday, old_promotion, old_taxation) = kingdom_results
                content = ""
                if holiday is not None:
                    await cursor.execute("SELECT Holidays_Loyalty, Holidays_Consumption FROM KB_Edicts WHERE severity = ?",(old_holiday,))
                    old_edict = await cursor.fetchone()
                    await cursor.execute("SELECT Holidays_Loyalty, Holidays_Consumption FROM KB_Edicts WHERE severity = ?",(holiday,))
                    new_edict = await cursor.fetchone()
                    await cursor.execute("UPDATE KB_Kingdoms Set Loyalty = Loyalty + ?, Consumption = Consumption + ?, Holiday = ? WHERE Kingdom = ?",
                                         (old_edict[0] - new_edict[0], old_edict[1] - new_edict[1], holiday, kingdom))
                    content += f"Holiday set to {holiday}.\n"
                if promotion is not None:
                    await cursor.execute("SELECT Promotion_Stability, Promotion_Consumption FROM KB_Edicts WHERE severity = ?",(old_promotion,))
                    old_edict = await cursor.fetchone()
                    await cursor.execute("SELECT Promotion_Stability, Promotion_Consumption FROM KB_Edicts WHERE severity = ?",(promotion,))
                    new_edict = await cursor.fetchone()
                    await cursor.execute("UPDATE KB_Kingdoms Set Stability = Stability + ?, Consumption = Consumption + ?, Promotion = ? WHERE Kingdom = ?",
                                         (old_edict[0] - new_edict[0], old_edict[1] - new_edict[1], promotion, kingdom))
                    content += f"Promotion set to {promotion}.\n"
                if taxation is not None:
                    await cursor.execute("SELECT Taxation_Economy, Taxation_Loyalty FROM KB_Edicts WHERE severity = ?",(old_taxation,))
                    old_edict = await cursor.fetchone()
                    await cursor.execute("SELECT Taxation_Economy, Taxation_Loyalty FROM KB_Edicts WHERE severity = ?",(taxation,))
                    new_edict = await cursor.fetchone()
                    await cursor.execute("UPDATE KB_Kingdoms Set Economy = Economy + ?, Loyalty = Loyalty + ?, Taxation = ? WHERE Kingdom = ?",
                                         (old_edict[0] - new_edict[0], old_edict[1] - new_edict[1], taxation, kingdom))
                    content += f"Taxation set to {taxation}.\n"
                await db.commit()
                await interaction.followup.send(content=f"The edict severity has been set to:\n{content}")
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"Error setting edict severity: {e}")
            await interaction.followup.send(content="An error occurred while setting edict severity.")

    @edict_group.command(name="display", description="Display the edict severity of a kingdom")
    async def display_dicts(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        try:
            embed = discord.Embed(title="Edict Information", color=0x00ff00, description="information about edicts")
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute("""
                SELECT severity,
                    Holidays, Holidays_Loyalty, Holidays_Consumption, 
                    Promotion, Promotion_Stability, Promotion_Consumption,
                    Taxation, Taxation_Economy, Taxation_Loyalty
                    FROM KB_Edicts Order by Severity Asc""")
                edict_results = await cursor.fetchall()
                holiday_edict = ""
                promotion_edict = ""
                taxation_edict = ""
                for edict in edict_results:
                    (severity, holiday, holiday_loyalty, holiday_consumption, promotion, promotion_stability,
                    promotion_consumption, taxation, taxation_economy, taxation_loyalty) = edict
                    holiday_edict += f"{holiday} - Loyalty: {holiday_loyalty}, Consumption: {holiday_consumption}\n"
                    promotion_edict += f"{promotion} - Stability: {promotion_stability}, Consumption: {promotion_consumption}\n"
                    taxation_edict += f"{taxation} - Economy: {taxation_economy}, Loyalty: {taxation_loyalty}\n"
                await cursor.execute("""
                SELECT 
                Size,  Settlements, Buildings, Improvements, HExes
                FROM KB_Improvements
                Order by Size Asc""")
                improvement_results = await cursor.fetchall()
                improvement_edict = ""
                for improvement in improvement_results:
                    (size, settlements, buildings, improvements, hexes) = improvement
                    improvement_edict += f"{size} - Settlements: {settlements}, Buildings: {buildings}, Improvements: {improvements}, Hexes: {hexes}\n"
                embed.add_field(name="Holiday Edict", value=holiday_edict, inline=False)
                embed.add_field(name="Promotion Edict", value=promotion_edict, inline=False)
                embed.add_field(name="Taxation Edict", value=taxation_edict, inline=False)
                embed.add_field(name="Improvement Edict", value=improvement_edict, inline=False)
                embed.set_footer(text="Edicts are used to modify the kingdom's stats.")
                await interaction.followup.send(embed=embed)
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"Error displaying edict severity: {e}")
            await interaction.followup.send(content="An error occurred while displaying edict severity.")


    @leadership_group.command(name="modify",
                              description="Modify a leader, by changing their ability score or who is in charge")
    @app_commands.autocomplete(kingdom=kingdom_autocomplete)
    @app_commands.autocomplete(title=leadership_autocomplete)
    @app_commands.autocomplete(character_name=shared_functions.character_select_autocompletion)
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
                if not kingdom_results:
                    await interaction.followup.send(content=f"The kingdom of {kingdom} does not exist.")
                    return
                valid_password = validate_password(password, kingdom_results[0])
                if not valid_password:
                    await interaction.followup.send(content="The password provided is incorrect.")
                    return
                await cursor.execute("Select Player_ID, Character_Name from Player_Characters where Character_Name = ?",
                                     (character_name,))
                recipient = await cursor.fetchone()
                recipient_id = recipient[0]
                await cursor.execute(
                    "SELECT Ability, Economy, Loyalty, Stability FROM AA_Leadership_Roles WHERE Title = ?",
                    (title,))
                leadership_info = await cursor.fetchone()
                await cursor.execute(
                    "SELECT Character_Name from KB_Leadership where Character_Name = ?",
                    (character_name,))
                character_presence = await cursor.fetchone()
                if character_presence:
                    await interaction.followup.send(content=f"The character of {character_name} is already a leader.")
                    return
                (ability, economy, loyalty, stability) = leadership_info
                abilities = ability.split(" / ")
                options = [
                    discord.SelectOption(label=ability) for ability in abilities
                ]

                additional = 1
                if title == "Ruler":
                    additional = 1 if kingdom_results[1] < 26 else 2
                    additional = 3 if kingdom_results[1] > 101 else additional
                print(additional, economy, loyalty, stability)
                view = LeadershipView(
                    options, interaction.guild_id, interaction.user.id, kingdom, title, character_name,
                    additional, economy, loyalty, stability, kingdom_results[1], modifier=modifier,
                    recipient_id=recipient_id, content="Please select an attribute:", interaction=interaction)
            # Store the message object
            view.message = await interaction.original_response()
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"Error modifying  Leadership: {e}")
            await interaction.followup.send(content="An error occurred while modifying  Leadership.")

    @leadership_group.command(name="remove", description="Remove a leader from a kingdom")
    @app_commands.autocomplete(kingdom=kingdom_autocomplete)
    @app_commands.autocomplete(title=leadership_autocomplete)
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
                valid_password = validate_password(password, kingdom_results[0])
                if not valid_password:
                    await interaction.followup.send(content="The password provided is incorrect.")
                    return
                status = await remove_leader(interaction.guild_id, interaction.user.id, kingdom, title)
                await interaction.followup.send(content=status)
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"Error removing leader: {e}")
            await interaction.followup.send(content="An error occurred while removing the leader.")

    @hex_group.command(name="claim", description="Claim a hex for a kingdom")
    @app_commands.autocomplete(kingdom=kingdom_autocomplete)
    async def claim(self, interaction: discord.Interaction, kingdom: str, password: str, hex_id: int):
        """This command is used to claim a hex for a kingdom"""
        await interaction.response.defer(thinking=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute("SELECT Password, Region FROM kb_Kingdoms WHERE Kingdom = ?", (kingdom,))
                kingdom_results = await cursor.fetchone()
                if not kingdom_results:
                    await interaction.followup.send(content=f"The kingdom of {kingdom} does not exist.")
                    return
                valid_password = validate_password(password, kingdom_results[0])
                if not valid_password:
                    await interaction.followup.send(content="The password provided is incorrect.")
                    return
                await cursor.execute("SELECT Kingdom, Region FROM KB_Hexes WHERE ID = ?", (hex_id,))
                hex_results = await cursor.fetchone()
                if not hex_results:
                    await interaction.followup.send(content=f"The hex of {hex_id} does not exist.")
                    return
                elif hex_results[0]:
                    await interaction.followup.send(
                        content=f"The hex of {hex_id} is already claimed by {hex_results[0]}.")
                    return
                elif hex_results[1] != kingdom_results[1]:
                    await interaction.followup.send(
                        content=f"The hex of {hex_id} is not in the kingdom's region of {kingdom_results[1]}.")
                    return
                status = await claim_hex(guild_id=interaction.guild_id, author=interaction.user.id, kingdom=kingdom,
                                         hex_id=hex_id)
                await interaction.followup.send(content=status)
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"Error claiming hex: {e}")
            await interaction.followup.send(content="An error occurred while claiming a hex.")

    @hex_group.command(name="relinquish", description="relinquish a hex for a kingdom")
    @app_commands.autocomplete(kingdom=kingdom_autocomplete)
    async def relinquish_hex(self, interaction: discord.Interaction, kingdom: str, password: str, hex_id: int):
        """This command is used to relinquish a hex for a kingdom"""
        await interaction.response.defer(thinking=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute("SELECT Password FROM kb_Kingdoms WHERE Kingdom = ?", (kingdom,))
                kingdom_results = await cursor.fetchone()
                if not kingdom_results:
                    await interaction.followup.send(content=f"The kingdom of {kingdom} does not exist.")
                    return
                valid_password = validate_password(password, kingdom_results[0])
                if not valid_password:
                    await interaction.followup.send(content="The password provided is incorrect.")
                    return
                await cursor.execute("SELECT ID FROM KB_Hexes WHERE ID = ? and Kingdom = ?", (hex_id, kingdom))
                hex_results = await cursor.fetchone()
                if not hex_results:
                    await interaction.followup.send(content=f"The hex terrain of {hex_id} does not exist.")
                    return
                status = await relinquish_hex(interaction.guild_id, interaction.user.id, kingdom, hex_id)
                await interaction.followup.send(content=status)
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"Error unclaiming hex: {e}")
            await interaction.followup.send(content="An error occurred while unclaiming a hex.")

    @hex_group.command(name="improve", description="Add an improvement to a hex")
    @app_commands.autocomplete(kingdom=kingdom_autocomplete)
    @app_commands.autocomplete(improvement=hex_improvement_autocomplete)
    async def add_improvement(
            self,
            interaction: discord.Interaction,
            kingdom: str,
            password: str,
            hex_id: int,
            improvement: str,
            amount: int):
        """This command is used to add an improvement to a hex"""
        await interaction.response.defer(thinking=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.cursor()
                await cursor.execute("SELECT Password, Build_Points, Size FROM kb_Kingdoms WHERE Kingdom = ?",
                                     (kingdom,))
                kingdom_results = await cursor.fetchone()
                if not kingdom_results:
                    await interaction.followup.send(content=f"The kingdom of {kingdom} does not exist.")
                    return
                valid_password = validate_password(password, kingdom_results['Password'])
                if not valid_password:
                    await interaction.followup.send(content="The password provided is incorrect.")
                    return

                status = await add_an_improvement(
                    guild_id=interaction.guild_id,
                    hex_id=hex_id,
                    kingdom=kingdom,
                    improvement=improvement,
                    amount=amount,
                    build_points=kingdom_results['Build_Points'],
                    kingdom_size=kingdom_results['Size']
                )
                await interaction.followup.send(content=status)
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"Error adding improvement: {e}")
            await interaction.followup.send(content="An error occurred while adding an improvement.")

    @hex_group.command(name="degrade", description="Remove an improvement from a hex")
    @app_commands.autocomplete(kingdom=kingdom_autocomplete)
    @app_commands.autocomplete(improvement=hex_improvement_autocomplete)
    async def remove_improvement(
            self,
            interaction: discord.Interaction,
            kingdom: str,
            password: str,
            hex_id: int,
            improvement: str,
            amount: int):
        """This command is used to remove an improvement from a hex"""
        await interaction.response.defer(thinking=True)
        try:
            async with (aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite")) as db:
                cursor = await db.cursor()
                await cursor.execute("SELECT Password FROM kb_Kingdoms WHERE Kingdom = ?", (kingdom,))
                kingdom_results = await cursor.fetchone()
                if not kingdom_results:
                    await interaction.followup.send(content=f"The kingdom of {kingdom} does not exist.")
                    return
                valid_password = validate_password(password, kingdom_results[0])
                if not valid_password:
                    await interaction.followup.send(content="The password provided is incorrect.")
                    return
                hex_information = await fetch_hex_improvement(interaction.guild_id, improvement)
                if not hex_information:
                    await interaction.followup.send(content=f"The improvement of {improvement} does not exist.")
                    return
                status = await degrade_improvement(
                    guild_id=interaction.guild_id,
                    author=interaction.user.id,
                    hex_information=hex_information,
                    hex_id=hex_id,
                    amount=amount)
                await interaction.followup.send(content=status)
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"Error removing improvement: {e}")
            await interaction.followup.send(content="An error occurred while removing an improvement.")

    @hex_group.command(name='repurpose', description='Change the behavior of an improvement')
    @app_commands.autocomplete(kingdom=kingdom_autocomplete)
    @app_commands.autocomplete(original_purpose=improvement_subtype_autocomplete)
    @app_commands.autocomplete(new_purpose=improvement_subtype_autocomplete)
    async def repurpose_improvement(
            self,
            interaction: discord.Interaction,
            hex_id: int,
            kingdom: str,
            original_purpose: str,
            new_purpose: str,
            password: str,
            amount: int):
        """This command is used to repurpose an improvement in a hex"""
        await interaction.response.defer(thinking=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute("SELECT Password FROM kb_Kingdoms WHERE Kingdom = ?", (kingdom,))
                kingdom_results = await cursor.fetchone()
                if not kingdom_results:
                    await interaction.followup.send(content=f"The kingdom of {kingdom} does not exist.")
                    return
                valid_password = validate_password(password, kingdom_results[0])
                if not valid_password:
                    await interaction.followup.send(content="The password provided is incorrect.")
                    return
                status = await repurpose_an_improvement(
                    guild_id=interaction.guild_id,
                    hex_id=hex_id,
                    old_full_name=original_purpose,
                    new_full_name=new_purpose,
                    amount=amount
                )
                await interaction.followup.send(content=status)
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"Error repurposing improvement: {e}")
            await interaction.followup.send(content="An error occurred while repurposing an improvement.")

    @settlement_group.command(name="claim", description="Claim a settlement for a kingdom")
    @app_commands.autocomplete(kingdom=kingdom_autocomplete)
    async def claim_settlement(self, interaction: discord.Interaction, kingdom: str, password: str, settlement: str,
                               hex_id: int):
        """This command is used to claim a settlement for a kingdom"""
        await interaction.response.defer(thinking=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute("SELECT Password FROM kb_Kingdoms WHERE Kingdom = ?", (kingdom,))
                kingdom_results = await cursor.fetchone()
                if not kingdom_results:
                    await interaction.followup.send(content=f"The kingdom of {kingdom} does not exist.")
                    return
                valid_password = validate_password(password, kingdom_results[0])
                if not valid_password:
                    await interaction.followup.send(content="The password provided is incorrect.")
                    return

                await cursor.execute("SELECT Kingdom FROM kb_settlements WHERE Settlement = ?", (settlement,))
                settlement_info = await cursor.fetchone()
                if settlement_info is not None:
                    await interaction.followup.send(
                        content=f"A settlement with this name is already claimed by {settlement_info[0]}.")
                await cursor.execute("SELECT ID, IsTown from KB_Hexes where ID = ?", (hex_id,))
                hex_results = await cursor.fetchone()
                if not hex_results:
                    await interaction.followup.send(content=f"The hex of {hex_id} does not exist.")
                    return
                if hex_results[1]:
                    await interaction.followup.send(content="The hex is already a town.")
                    return
                await cursor.execute("Select Count(Full_Name) from KB_Hexes_Constructed Where ID = ?", (hex_id,))
                improvements = await cursor.fetchone()
                if improvements[0] > 0:
                    await interaction.followup.send(
                        content="The hex has improvements built upon it and cannot share them with a settlement!")
                    return
                status = await claim_a_settlement(interaction.guild_id, interaction.user.id, kingdom, settlement,
                                                  hex_id)
                await interaction.followup.send(content=status)
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"Error claiming settlement: {e}")
            await interaction.followup.send(content="An error occurred while claiming a settlement.")

    @settlement_group.command(name="edit", description="Edit a settlement for a kingdom")
    @app_commands.autocomplete(kingdom=kingdom_autocomplete)
    async def edit_settlement(self, interaction: discord.Interaction, kingdom: str, password: str, old_name: str,
                              new_name: str):
        """This command is used to Edit a settlement for a kingdom"""
        await interaction.response.defer(thinking=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute("SELECT Password FROM kb_Kingdoms WHERE Kingdom = ?", (kingdom,))
                kingdom_results = await cursor.fetchone()
                if not kingdom_results:
                    await interaction.followup.send(content=f"The kingdom of {kingdom} does not exist.")
                    return
                valid_password = validate_password(password, kingdom_results[0])
                if not valid_password:
                    await interaction.followup.send(content="The password provided is incorrect.")
                    return

                await cursor.execute("SELECT Kingdom FROM kb_settlements WHERE Settlement = ?", (old_name,))
                settlement_info = await cursor.fetchone()
                if not settlement_info:
                    await interaction.followup.send(content=f"The settlement of {old_name} was a fukkin lie.")
                    return
                await cursor.execute("SELECT Kingdom from kb_settlements where Settlement = ?", (new_name,))
                new_settlement_info = await cursor.fetchone()
                if new_settlement_info:
                    await interaction.followup.send(
                        content=f"The settlement of {new_name} is already claimed by {new_settlement_info[0]}.")
                    return
                await cursor.execute("UPDATE kb_settlements SET Settlement = ? WHERE Settlement = ?",
                                     (new_name, old_name))
                await cursor.execute("UPDATE KB_Buildings SET Settlement = ? WHERE Settlement = ?",
                                     (new_name, old_name))
                await db.commit()
                await interaction.followup.send(content=f"The settlement of {old_name} has been renamed to {new_name}.")
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"Error claiming settlement: {e}")
            await interaction.followup.send(content="An error occurred while claiming a settlement.")

    @settlement_group.command(name="relinquish", description="relinquish a settlement for a kingdom")
    @app_commands.autocomplete(kingdom=kingdom_autocomplete)
    @app_commands.autocomplete(settlement=settlement_autocomplete)
    async def relinquish_settlement(self, interaction: discord.Interaction, kingdom: str, password: str,
                                    settlement: str):
        """This command is used to relinquish a settlement for a kingdom"""
        await interaction.response.defer(thinking=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute("SELECT Password FROM kb_Kingdoms WHERE Kingdom = ?", (kingdom,))
                kingdom_results = await cursor.fetchone()
                if not kingdom_results:
                    await interaction.followup.send(content=f"The kingdom of {kingdom} does not exist.")
                    return
                valid_password = validate_password(password, kingdom_results[0])
                if not valid_password:
                    await interaction.followup.send(content="The password provided is incorrect.")
                    return
            status = await relinquish_settlement(interaction.guild_id, interaction.user.id, kingdom, settlement)
            await interaction.followup.send(content=status)
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"Error unclaiming settlement: {e}")
            await interaction.followup.send(content="An error occurred while unclaiming a settlement.")

    @settlement_group.command(name="build", description="Build a building in a settlement")
    @app_commands.autocomplete(kingdom=kingdom_autocomplete)
    @app_commands.autocomplete(settlement=settlement_autocomplete)
    @app_commands.autocomplete(building=blueprint_autocomplete)
    async def build_building(self, interaction: discord.Interaction, kingdom: str, password: str, settlement: str,
                             building: str, amount: int):
        """This command is used to build a building in a settlement"""
        await interaction.response.defer(thinking=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute("SELECT Password, Build_Points, population FROM kb_Kingdoms WHERE Kingdom = ?",
                                     (kingdom,))
                kingdom_results = await cursor.fetchone()
                if not kingdom_results:
                    await interaction.followup.send(content=f"The kingdom of {kingdom} does not exist.")
                    return
                valid_password = validate_password(password, kingdom_results[0])

                if not valid_password:
                    await interaction.followup.send(content="The password provided is incorrect.")
                    return

                await cursor.execute("Select Size from kb_settlements where Settlement = ?", (settlement,))
                settlement_info = await cursor.fetchone()

                if settlement_info is None:
                    await interaction.followup.send(content="The settlement is not found.")
                    return

                await cursor.execute("SELECT Kingdom from KB_Buildings_Permits where Kingdom = ? AND Full_Name = ?",
                                     (kingdom, building))
                permits = await cursor.fetchone()
                if permits is None:
                    await interaction.followup.send(content="The kingdom does not have a permit for this building.")
                    return
                building_info = await fetch_building(interaction.guild_id, building)
                cost = building_info.build_points * amount

                await cursor.execute("""
                SELECT 
                SUM(CASE WHEN KB.Subtype = 'Housing' THEN KB.Amount * COALESCE(KBB.Quality, 0) ELSE 0 END) AS Housing_Total,
                SUM(CASE WHEN KB.Subtype != 'Housing' THEN KB.Amount * COALESCE(KBB.Supply, 0) ELSE 0 END) AS Non_Housing_Total
                FROM KB_Buildings AS KB
                LEFT JOIN KB_Buildings_Blueprints AS KBB
                ON KB.Full_Name = KBB.Full_Name
                WHERE KB.Kingdom = ?
                AND KB.Settlement = ?;
                """, (
                    kingdom, settlement))
                supply = await cursor.fetchone()
                print(supply, amount, building_info.supply)
                housing_total = supply[0] if supply[0] else 0
                non_housing_total = supply[1] if supply[1] else 0
                if non_housing_total + (amount * building_info.supply) > housing_total:
                    await interaction.followup.send(
                        content=f"The settlement does not have enough housing. it has {supply[0]} and needs {supply[1] - supply[0] + (amount * building_info.supply)} more.")
                    return
                await cursor.execute("""
                SELECT Build.Full_Name, sum(Build.amount), sum(Build.discounted) from KB_Buildings Build 
                left join KB_Buildings_Blueprints Blue on Blue.Full_Name = Build.Full_Name 
                where Build.Kingdom = ? and Build.Settlement = ? and Build.Full_Name = ? and Blue.discount like ?
                group by Build.Full_Name""", (kingdom, settlement, building, f"%{building_info.type}%"))
                discount_info = await cursor.fetchall()
                discount_count = amount
                for discount in discount_info:
                    (full_name, amount_built, discounted) = discount
                    discountable = amount_built - discounted
                    discounted_change = min(discountable, discount_count)
                    discount_count -= min(discountable, discount_count)
                    await cursor.execute(
                        "UPDATE KB_Buildings SET Discounted = Discounted + ? WHERE Kingdom = ? and Settlement = ? and Full_Name = ?",
                        (discounted_change, kingdom, settlement, full_name))
                    if discount_count == 0:
                        break
                cost -= building_info.build_points * .5 * (amount - discount_count)
                if cost > kingdom_results[1]:
                    await interaction.followup.send(
                        content=f"The kingdom does not have enough build points. it has {kingdom_results[1]} and needs {cost}.")
                    return
                await cursor.execute("UPDATE kb_Kingdoms SET build_points = build_points - ? WHERE Kingdom = ?",
                                     (cost, kingdom))
                await db.commit()

                status = await add_building(guild_id=interaction.guild_id, author=interaction.user.id, kingdom=kingdom,
                                            settlement=settlement, building_info=building_info, amount=amount,
                                            size=settlement_info[0])
                await interaction.followup.send(content=status)
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"Error building building: {e}")
            await interaction.followup.send(content="An error occurred while building a building.")

    @settlement_group.command(name="destroy", description="Destroy a building in a settlement")
    @app_commands.autocomplete(kingdom=kingdom_autocomplete)
    @app_commands.autocomplete(settlement=settlement_autocomplete)
    @app_commands.autocomplete(building=blueprint_autocomplete)
    async def destroy_building(self, interaction: discord.Interaction, kingdom: str, password: str, settlement: str,
                               building: str, amount: int):
        """This command is used to destroy a building in a settlement"""
        await interaction.response.defer(thinking=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute("SELECT Password, Build_Points FROM kb_Kingdoms WHERE Kingdom = ?", (kingdom,))
                kingdom_results = await cursor.fetchone()
                if not kingdom_results:
                    await interaction.followup.send(content=f"The kingdom of {kingdom} does not exist.")
                    return
                valid_password = validate_password(password, kingdom_results[0])
                if not valid_password:
                    await interaction.followup.send(content="The password provided is incorrect.")
                    return
                await cursor.execute("Select Size from kb_settlements where Settlement = ?", (settlement,))
                settlement_info = await cursor.fetchone()
                if not settlement_info:
                    await interaction.followup.send(content="The settlement is not claimed.")
                    return
                building_info = await fetch_building(interaction.guild_id, building)
                status = await remove_building(
                    guild_id=interaction.guild_id,
                    author=interaction.user.id,
                    settlement=settlement,
                    building_info=building_info,
                    amount=amount)
                bp_return = (building_info.build_points * status[1]) * .5
                await cursor.execute("UPDATE kb_Kingdoms SET Build_Points = Build_Points + ? WHERE Kingdom = ?",
                                     (bp_return, kingdom))
                await interaction.followup.send(content=status[0])
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"Error destroying building: {e}")
            await interaction.followup.send(content="An error occurred while destroying a building.")

    @settlement_group.command(name="upgrade", description="upgrade a building in a settlement")
    @app_commands.autocomplete(kingdom=kingdom_autocomplete)
    @app_commands.autocomplete(settlement=settlement_autocomplete)
    @app_commands.autocomplete(building=blueprint_upgrade_autocomplete)
    async def upgrade_building(
            self, interaction: discord.Interaction, kingdom: str, password: str, settlement: str,
            building: str, amount: int):
        """This command is used to upgrade a building in a settlement"""
        await interaction.response.defer(thinking=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute("SELECT Password, Build_Points FROM kb_Kingdoms WHERE Kingdom = ?", (kingdom,))
                kingdom_results = await cursor.fetchone()
                if not kingdom_results:
                    await interaction.followup.send(content=f"The kingdom of {kingdom} does not exist.")
                    return
                valid_password = validate_password(password, kingdom_results[0])
                if not valid_password:
                    await interaction.followup.send(content="The password provided is incorrect.")
                    return
                await cursor.execute(
                    "Select Amount from KB_Buildings where Kingdom = ? and Settlement = ? and Full_Name = ?",
                    (kingdom, settlement, building))
                settlement_info = await cursor.fetchone()
                if not settlement_info:
                    await interaction.followup.send(content=f"Settlement of {settlement} has no {building}s built!")
                    return
                amount = min(amount, settlement_info[0])
                old_building_info = await fetch_building(interaction.guild_id, building)
                new_building_info = await fetch_building(interaction.guild_id, old_building_info.upgrade)
                cost = (new_building_info.build_points - old_building_info.build_points) * amount
                if cost > kingdom_results[1]:
                    await interaction.followup.send(
                        content=f"The kingdom does not have enough build points. it has {kingdom_results[1]} and needs {cost}.")
                    return
                await cursor.execute("UPDATE kb_Kingdoms SET Build_Points = Build_Points - ? WHERE Kingdom = ?",
                                     (cost, kingdom))
                await db.commit()
                await remove_building(
                    guild_id=interaction.guild_id,
                    author=interaction.user.id,
                    settlement=settlement,
                    building_info=old_building_info,
                    amount=amount)
                status = await add_building(guild_id=interaction.guild_id, author=interaction.user.id, kingdom=kingdom,
                                            settlement=settlement, building_info=new_building_info, amount=amount,
                                            size=settlement_info[0])
                await interaction.followup.send(content=status)
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"Error upgrading building: {e}")
            await interaction.followup.send(content="An error occurred while upgrading a building.")

    @settlement_group.command(name="repurpose", description="Change the behavior of a building")
    @app_commands.autocomplete(kingdom=kingdom_autocomplete)
    @app_commands.autocomplete(settlement=settlement_autocomplete)
    @app_commands.autocomplete(old_purpose=blueprint_repurpose_autocomplete)
    @app_commands.autocomplete(new_purpose=blueprint_repurpose_autocomplete)
    async def repurpose_building(
            self, interaction: discord.Interaction, kingdom: str, password: str, settlement: str,
            old_purpose: str, new_purpose: str, amount: int):
        """This command is used to repurpose a building in a settlement"""
        await interaction.response.defer(thinking=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute("SELECT Password, Build_Points FROM kb_Kingdoms WHERE Kingdom = ?", (kingdom,))
                kingdom_results = await cursor.fetchone()
                if not kingdom_results:
                    await interaction.followup.send(content=f"The kingdom of {kingdom} does not exist.")
                    return
                valid_password = validate_password(password, kingdom_results[0])
                if not valid_password:
                    await interaction.followup.send(content="The password provided is incorrect.")
                    return
                await cursor.execute(
                    "Select Amount from KB_Buildings where Kingdom = ? and Settlement = ? and Full_Name = ?",
                    (kingdom, settlement, old_purpose))
                settlement_info = await cursor.fetchone()
                if not settlement_info:
                    await interaction.followup.send(
                        content=f"Settlement of {settlement} has no {old_purpose} buildings built!")
                    return
                amount = min(amount, settlement_info[0])
                await cursor.execute(
                    "Select Amount from KB_Buildings where Kingdom = ? and Settlement = ? and Full_Name = ?",
                    (kingdom, settlement, new_purpose))
                new_building_count = await cursor.fetchone()
                old_building_info = await fetch_building(interaction.guild_id, old_purpose)
                new_building_info = await fetch_building(interaction.guild_id, new_purpose)
                if old_building_info.type != new_building_info.type:
                    await interaction.followup.send(content=f"Building types do not match!")
                    return
                if not new_building_count and amount == settlement_info[0]:
                    await cursor.execute(
                        "UPDATE KB_Buildings Set Full_Name = ?, Subtype = ? where Kingdom = ? and Settlement = ? and Full_Name = ?",
                        (new_purpose, new_building_info.subtype, kingdom, settlement, old_purpose))
                elif new_building_count and amount == settlement_info[0]:
                    await cursor.execute(
                        "UPDATE KB_Buildings Set Amount = Amount + ? where Kingdom = ? and Settlement = ? and Full_Name = ?",
                        (amount, kingdom, settlement, new_purpose))
                    await cursor.execute(
                        "DELETE FROM KB_Buildings where Kingdom = ? and Settlement = ? and Full_Name = ?",
                        (kingdom, settlement, old_purpose))
                else:
                    await cursor.execute(
                        "UPDATE KB_Buildings Set Amount = Amount + ? where Kingdom = ? and Settlement = ? and Full_Name = ?",
                        (amount, kingdom, settlement, new_purpose))
                    await cursor.execute(
                        "UPDATE KB_Buildings Set Amount = Amount - ? where Kingdom = ? and Settlement = ? and Full_Name = ?",
                        (amount, kingdom, settlement, old_purpose))
                await db.commit()
                await interaction.followup.send(
                    content=f"{amount} {old_purpose} buildings have been repurposed into {new_purpose}!")
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"Error repurposing building: {e}")
            await interaction.followup.send(content="An error occurred while repurposing a building.")

    @kingdom_group.command(name="event", description="display and handle kingdom events")
    @app_commands.autocomplete(kingdom=kingdom_autocomplete)
    @app_commands.choices(
        intent=[discord.app_commands.Choice(name='Problematic', value=1),
                discord.app_commands.Choice(name='Ongoing', value=2),
                discord.app_commands.Choice(name='Temporary', value=3)]
    )
    async def kingdom_event(self, interaction: discord.Interaction, kingdom: str, password: str, intent: int):
        """This command is used to display and handle kingdom events"""
        await interaction.response.defer(thinking=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute("SELECT Password FROM kb_Kingdoms WHERE Kingdom = ?", (kingdom,))
                kingdom_results = await cursor.fetchone()
                if not kingdom_results:
                    await interaction.followup.send(content=f"The kingdom of {kingdom} does not exist.")
                    return
                valid_password = validate_password(password, kingdom_results[0])
                if not valid_password:
                    await interaction.followup.send(content="The password provided is incorrect.")
                    return
                view = KingdomEventView(user_id=interaction.user.id, guild_id=interaction.guild_id, intent=intent,
                                        kingdom=kingdom)
                await view.update_results()
                await view.create_embed()
                await view.send()
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"Error displaying kingdom events: {e}")
            await interaction.followup.send(content="An error occurred while displaying kingdom events.")

    trade_group = discord.app_commands.Group(
        name='trade',
        description='Commands related to kingdom management',
        parent=kingdom_group
    )

    @trade_group.command(name="request", description="Request a trade route to another kingdom")
    @app_commands.autocomplete(kingdom=kingdom_autocomplete)
    @app_commands.autocomplete(target_kingdom=kingdom_autocomplete)
    async def request_trade(
            self, interaction: discord.Interaction, kingdom: str, password: str, target_kingdom: str,
            seafood: typing.Optional[int], husbandry: typing.Optional[int], produce: typing.Optional[int],
            grain: typing.Optional[int],
            ore: typing.Optional[int], lumber: typing.Optional[int], stone: typing.Optional[int],
            raw_textiles: typing.Optional[int],
            textiles: typing.Optional[int], metallurgy: typing.Optional[int], woodworking: typing.Optional[int],
            stoneworking: typing.Optional[int],
            magical_consumables: typing.Optional[int], magical_items: typing.Optional[int],
            mundane_exotic: typing.Optional[int], mundane_complex: typing.Optional[int]
    ):
        """This command is used to request a trade route to another kingdom"""
        await interaction.response.defer(thinking=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute("SELECT Password FROM kb_Kingdoms WHERE Kingdom = ?", (kingdom,))
                kingdom_results = await cursor.fetchone()
                if not kingdom_results:
                    await interaction.followup.send(content=f"The kingdom of {kingdom} does not exist.")
                    return
                valid_password = validate_password(password, kingdom_results[0])
                if not valid_password:
                    await interaction.followup.send(content="The password provided is incorrect.")
                    return
                await cursor.execute(
                    "SELECT Character_Name, PLayer_ID FROM KB_Leadership WHERE Kingdom = ? And Title = 'Ruler'",
                    (target_kingdom,))
                target_kingdom_results = await cursor.fetchone()
                if not target_kingdom_results:
                    await interaction.followup.send(content=f"The kingdom of {target_kingdom} does not exist.")
                    return
                (target_ruler_name, target_ruler_id) = target_kingdom_results
                await cursor.execute(
                    "SELECT Character_Name, PLayer_ID FROM KB_Leadership WHERE Kingdom = ? And Title = 'Ruler'",
                    (kingdom,))
                kingdom_results = await cursor.fetchone()
                if not kingdom_results:
                    await interaction.followup.send(content=f"The kingdom of {kingdom} does not exist.")
                    return
                (source_ruler_name, source_ruler_id) = kingdom_results
                await cursor.execute("SELECT * FROM KB_Trade WHERE Source_Kingdom = ? AND End_Kingdom = ?",
                                     (kingdom, target_kingdom))
                trade_results = await cursor.fetchone()
                if trade_results:
                    await interaction.followup.send(
                        content="There is already a trade route between these kingdoms. You have to end it before starting a new one.")
                    return

                await cursor.execute("""
                SELECT 
                SUM(Husbandry), SUM(Produce), SUM(Grain), SUM(Seafood), 
                SUM(Ore), SUM(Stone), SUM(Wood), SUM(Raw_Textiles),
                SUM(Textiles), SUM(Metallurgy), SUM(Woodworking), SUM(Stoneworking),
                SUM(Magical_Consumables), SUM(Magical_Items), SUM(Mundane_Exotic), SUM(Mundane_Complex)
                FROM KB_Trade 
                WHERE Source_Kingdom = ?
                """, (kingdom,))
                trade_results = await cursor.fetchone()
                (trade_husbandry, trade_produce, trade_grain, trade_seafood,
                 trade_ore, trade_stone, trade_wood, trade_raw_textiles,
                 trade_textiles, trade_metallurgy, trade_woodworking, trade_stoneworking,
                 trade_magical_consumables, trade_magical_items, trade_mundane_exotic, trade_mundane_complex
                 ) = trade_results
                await cursor.execute("""
                SELECT 
                    SUM(CASE WHEN KHI.subtype = 'Grain' THEN KHC.amount * KHI.quality ELSE 0 END) AS Grain_total,
                    SUM(CASE WHEN KHI.subtype = 'Produce' THEN KHC.amount * KHI.quality ELSE 0 END) AS Produce_total,
                    SUM(CASE WHEN KHI.subtype = 'Husbandry' THEN KHC.amount * KHI.quality ELSE 0 END) AS Husbandry_total,
                    SUM(CASE WHEN KHI.subtype = 'Seafood' THEN KHC.amount * KHI.quality ELSE 0 END) AS Seafood_total,
                    SUM(CASE WHEN KHI.subtype = 'Ore' THEN KHC.amount * KHI.quality ELSE 0 END) AS ore_total,
                    SUM(CASE WHEN KHI.subtype = 'Stone' THEN KHC.amount * KHI.quality ELSE 0 END) AS stone_total,
                    SUM(CASE WHEN KHI.subtype = 'Wood' THEN KHC.amount * KHI.quality ELSE 0 END) AS wood_total,
                    SUM(CASE WHEN KHI.subtype = 'Raw Textiles' THEN KHC.amount * KHI.quality ELSE 0 END) AS raw_textile_total
                FROM KB_Hexes_Constructed KHC 
                LEFT JOIN KB_Hexes_Improvements KHI ON KHC.Full_Name = KHI.Full_Name
                LEFT JOIN KB_Hexes H ON KHC.ID = H.ID
                WHERE H.kingdom = ?;""", (kingdom,))
                resources = await cursor.fetchone()
                (grain_total, produce_total, husbandry_total, seafood_total, ore_total, stone_total, lumber_total,
                 raw_textiles_total) = resources
                await cursor.execute("""
                SELECT 
                    SUM(CASE WHEN KBB.subtype = 'Textiles' THEN KB.amount * KBB.quality ELSE 0 END) AS Textiles_total,
                    SUM(CASE WHEN KBB.subtype = 'Metallurgy' THEN KB.amount * KBB.quality ELSE 0 END) AS Metallurgy_total,
                    SUM(CASE WHEN KBB.subtype = 'Woodworking' THEN KB.amount * KBB.quality ELSE 0 END) AS Woodworking_total,
                    SUM(CASE WHEN KBB.subtype = 'Stoneworking' THEN KB.amount * KBB.quality ELSE 0 END) AS Stoneworking_total,
                    SUM(CASE WHEN KBB.subtype = 'Magical Consumables' THEN KB.amount * KBB.quality ELSE 0 END) AS magical_consumables_total,
                    SUM(CASE WHEN KBB.subtype = 'Magical Items' THEN KB.amount * KBB.quality ELSE 0 END) AS magical_items_total,
                    SUM(CASE WHEN KBB.subtype = 'Mundane Exotic' THEN KB.amount * KBB.quality ELSE 0 END) AS mundane_exotic_total,
                    SUM(CASE WHEN KBB.subtype = 'Mundane Complex' THEN KB.amount * KBB.quality ELSE 0 END) AS mundane_complex_total
                FROM KB_Buildings KB LEFT JOIN KB_Buildings_Blueprints KBB ON KB.Full_Name = KBB.Full_Name
                WHERE kingdom = ?;""", (kingdom,))
                goods = await cursor.fetchone()
                (textiles_total, metallurgy_total, woodworking_total, stoneworking_total, magical_consumables_total,
                 magical_items_total, mundane_exotic_total, mundane_complex_total) = goods
                tradeable_husbandry = safe_min(husbandry, safe_sub(husbandry_total, trade_husbandry))
                tradeable_produce = safe_min(produce, safe_sub(produce_total, trade_produce))
                tradeable_grain = safe_min(grain, safe_sub(grain_total, trade_grain))
                tradeable_seafood = safe_min(seafood, safe_sub(seafood_total, trade_seafood))
                tradeable_ore = safe_min(ore, safe_sub(ore_total, trade_ore))
                tradeable_stone = safe_min(stone, safe_sub(stone_total, trade_stone))
                tradeable_wood = safe_min(lumber, safe_sub(lumber_total, trade_wood))
                tradeable_raw_textiles = safe_min(raw_textiles, safe_sub(raw_textiles_total, trade_raw_textiles))
                tradeable_textiles = safe_min(textiles, safe_sub(textiles_total, trade_textiles))
                tradeable_metallurgy = safe_min(metallurgy, safe_sub(metallurgy_total, trade_metallurgy))
                tradeable_woodworking = safe_min(woodworking, safe_sub(woodworking_total, trade_woodworking))
                tradeable_stoneworking = safe_min(stoneworking, safe_sub(stoneworking_total, trade_stoneworking))
                tradeable_magical_consumables = safe_min(magical_consumables,
                                                         safe_sub(magical_consumables_total, trade_magical_consumables))
                tradeable_magical_items = safe_min(magical_items, safe_sub(magical_items_total, trade_magical_items))
                tradeable_mundane_exotic = safe_min(mundane_exotic,
                                                    safe_sub(mundane_exotic_total, trade_mundane_exotic))
                tradeable_mundane_complex = safe_min(mundane_complex,
                                                     safe_sub(mundane_complex_total, trade_mundane_complex))
                view = TradeView(
                    allowed_user_id=target_ruler_id,
                    requester_name=interaction.user.name,
                    requester_id=interaction.user.id,
                    character_name=source_ruler_name,
                    recipient_name=target_ruler_name,
                    requesting_kingdom=kingdom,
                    sending_kingdom=target_kingdom,
                    bot=self.bot,
                    guild_id=interaction.guild_id,
                    interaction=interaction,
                    seafood=tradeable_seafood,
                    husbandry=tradeable_husbandry,
                    produce=tradeable_produce,
                    grain=tradeable_grain,
                    ore=tradeable_ore,
                    lumber=tradeable_wood,
                    stone=tradeable_stone,
                    raw_textiles=tradeable_raw_textiles,
                    textiles=tradeable_textiles,
                    metallurgy=tradeable_metallurgy,
                    woodworking=tradeable_woodworking,
                    stoneworking=tradeable_stoneworking,
                    magical_consumables=tradeable_magical_consumables,
                    magical_items=tradeable_magical_items,
                    mundane_exotic=tradeable_mundane_exotic,
                    mundane_complex=tradeable_mundane_complex
                )

                await view.create_embed()
                await view.send_initial_message()
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"Error requesting trade route: {e}")
            await interaction.followup.send(content="An error occurred while requesting a trade route.")

    @trade_group.command(name="cancel", description="Cancel a trade route with another kingdom")
    @app_commands.choices(
        intent=[discord.app_commands.Choice(name='outgoing', value=1),
                discord.app_commands.Choice(name='incoming', value=2)])
    @app_commands.autocomplete(kingdom=kingdom_autocomplete)
    @app_commands.autocomplete(target_kingdom=kingdom_autocomplete)
    async def cancel_trade(
            self,
            interaction: discord.Interaction,
            kingdom: str,
            password: str,
            target_kingdom: str,
            intent: int
    ):
        """This command is used to cancel a trade route with another kingdom"""
        await interaction.response.defer(thinking=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute("SELECT Password FROM kb_Kingdoms WHERE Kingdom = ?", (kingdom,))
                kingdom_results = await cursor.fetchone()
                if not kingdom_results:
                    await interaction.followup.send(content=f"The kingdom of {kingdom} does not exist.")
                    return
                valid_password = validate_password(password, kingdom_results[0])
                if not valid_password:
                    await interaction.followup.send(content="The password provided is incorrect.")
                    return
                await cursor.execute(
                    "SELECT Character_Name, PLayer_ID FROM KB_Leadership WHERE Kingdom = ? And Title = 'Ruler'",
                    (target_kingdom,))
                target_kingdom_results = await cursor.fetchone()
                if not target_kingdom_results:
                    await interaction.followup.send(content=f"The kingdom of {target_kingdom} does not exist.")
                    return
                (target_ruler_name, target_ruler_id) = target_kingdom_results
                await cursor.execute(
                    "SELECT Character_Name, PLayer_ID FROM KB_Leadership WHERE Kingdom = ? And Title = 'Ruler'",
                    (kingdom,))
                kingdom_results = await cursor.fetchone()
                if not kingdom_results:
                    await interaction.followup.send(content=f"The kingdom of {kingdom} does not exist.")
                    return
                (source_ruler_name, source_ruler_id) = kingdom_results
                statement = """
                SELECT Source_Kingdom, End_Kingdom, 
                Husbandry, Seafood, Grain, Produce,
                Ore, Stone, Wood, Raw_Textiles, 
                Textiles, Metallurgy, Woodworking, Stoneworking,
                Magical_Consumables, Magical_Items, Mundane_Exotic, Mundane_Complex
                FROM KB_Trade
                WHERE Source_Kingdom = ? AND End_Kingdom = ?"""
                if intent == 2:
                    await cursor.execute(statement, (target_kingdom, kingdom))
                else:
                    await cursor.execute(statement, (kingdom, target_kingdom))
                trade_results = await cursor.fetchone()
                if not trade_results:
                    await interaction.followup.send(content="No trade route exists between these kingdoms.")
                    return
                (source_kingdom, end_kingdom,
                 husbandry, seafood, grain, produce,
                 ore, stone, wood, raw_textiles,
                 textiles, metallurgy, woodworking, stoneworking,
                 magical_consumables, magical_items, mundane_exotic, mundane_complex) = trade_results
                embed = discord.Embed(
                    title=f"Trade Route Cancellation",
                    description=f"{source_ruler_name} is canceling a trade route with {target_ruler_name}."
                )
                if any((husbandry, seafood, grain, produce)):
                    embed.add_field(name="Food",
                                    value=f"Husbandry: {husbandry}, Seafood: {seafood}, Grain: {grain}, Produce: {produce}")
                if any((ore, stone, wood, raw_textiles)):
                    embed.add_field(name="Resources",
                                    value=f"Ore: {ore}, Stone: {stone}, Wood: {wood}, Raw Textiles: {raw_textiles}")
                if any((textiles, metallurgy, woodworking, stoneworking)):
                    embed.add_field(name="Goods",
                                    value=f"Textiles: {textiles}, Metallurgy: {metallurgy}, Woodworking: {woodworking}, Stoneworking: {stoneworking}")
                if any((magical_consumables, magical_items, mundane_exotic, mundane_complex)):
                    embed.add_field(name="Items",
                                    value=f"Magical Consumables: {magical_consumables}, Magical Items: {magical_items}, Mundane Exotic: {mundane_exotic}, Mundane Complex: {mundane_complex}")
                target_ruler = interaction.guild.get_member(target_ruler_id)
                if not target_ruler:
                    target_ruler = await interaction.guild.fetch_member(target_ruler_id)
                    if not target_ruler:
                        await interaction.followup.send(content="Target ruler not found.")
                        return
                content = f"{interaction.user.mention} is cancelling their trade with {target_ruler.mention}"
                await interaction.followup.send(content=content, embed=embed)
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"Error canceling trade route: {e}")
            await interaction.followup.send(content="An error occurred while canceling a trade route.")

    population_group = discord.app_commands.Group(
        name='population',
        description='Commands related to kingdom management',
        parent=kingdom_group
    )

    @population_group.command(name="bid", description="Bid for a portion of the population pool")
    @app_commands.autocomplete(kingdom=kingdom_autocomplete)
    async def bid_population(self, interaction: discord.Interaction, kingdom: str, password: str, amount: int):
        """This command is used to bid for a portion of the population pool"""
        await interaction.response.defer(thinking=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute("SELECT Password, Build_Points, Region FROM kb_Kingdoms WHERE Kingdom = ?",
                                     (kingdom,))
                kingdom_results = await cursor.fetchone()
                if not kingdom_results:
                    await interaction.followup.send(content=f"The kingdom of {kingdom} does not exist.")
                    return
                valid_password = validate_password(password, kingdom_results[0])
                if not valid_password:
                    await interaction.followup.send(content="The password provided is incorrect.")
                    return
                amount = min(amount, kingdom_results[1])
                await cursor.execute("Select Build_points from KB_Population_Bids where Kingdom = ?", (kingdom,))
                population_bid = await cursor.fetchone()
                if not population_bid:
                    await cursor.execute("INSERT INTO KB_Population_Bids (Kingdom, Amount, Region) VALUES (?, ?, ?)",
                                         (kingdom, amount, kingdom_results[2]))
                    await interaction.followup.send(content=f"{amount} Build Points have been bid for population on.")
                else:
                    await cursor.execute("UPDATE KB_Population_Bids SET Amount = Amount + ? WHERE Kingdom = ?",
                                         (amount, kingdom))
                    await interaction.followup.send(
                        content=f"{amount} Build Points have been added to the population bid.")
                await cursor.execute("UPDATE kb_Kingdoms SET Build_Points = Build_Points - ? WHERE Kingdom = ?",
                                     (amount, kingdom))
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"Error bidding on population: {e}")
            await interaction.followup.send(content="An error occurred while bidding on population.")

    @population_group.command(name="display", description="Display the current population bid")
    @app_commands.autocomplete(region=shared_functions.region_autocomplete)
    async def display_population(self, interaction: discord.Interaction, region: str):
        """This command is used to display the current population bid"""
        await interaction.response.defer(thinking=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute("SELECT Population FROM KB_Population WHERE region = ?", (region,))
                region = await cursor.fetchone()
                if not region:
                    await interaction.followup.send(content=f"The region of {region} does not exist.")
                    return
                await cursor.execute("SELECT sum(Amount) FROM KB_Population_Bids WHERE Region = ?", (region,))
                total_bid = await cursor.fetchone()
                await cursor.execute("SELECT Kingdom, Amount FROM KB_Population_Bids WHERE Region = ?", (region,))
                bids = await cursor.fetchall()
                if not bids:
                    await interaction.followup.send(content="There are no bids for this region.")
                    return
                embed = discord.Embed(
                    title=f"Population Bids for {region}",
                    description="The following kingdoms have bid for this region."
                )
                list_of_kingdoms = ""
                for idx, bid in enumerate(bids):
                    (kingdom, amount) = bid
                    list_of_kingdoms += f"{kingdom} has bid {amount} BP, potentially claiming {(amount / total_bid[0]) * region[0]} people.\r\n"
                    if idx % 10 == 0:
                        embed.add_field(name="Bids", value=list_of_kingdoms)
                        list_of_kingdoms = ""
                embed.add_field(name="Bids", value=list_of_kingdoms)
                await interaction.followup.send(embed=embed)
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"Error displaying population bid: {e}")
            await interaction.followup.send(content="An error occurred while displaying the population bid.")

    army_group = discord.app_commands.Group(
        name='army',
        description='Commands related to kingdom management',
        parent=kingdom_group
    )

    @army_group.command(name="manage", description="Create or manage an army")
    @app_commands.autocomplete(kingdom=kingdom_autocomplete)
    async def create_army(self, interaction: discord.Interaction, kingdom: str, password: str, army_name: str,
                          consumption_size: int):
        """This command is used to create an army"""
        await interaction.response.defer(thinking=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute("SELECT Password FROM kb_Kingdoms WHERE Kingdom = ?", (kingdom,))
                kingdom_results = await cursor.fetchone()
                if not kingdom_results:
                    await interaction.followup.send(content=f"The kingdom of {kingdom} does not exist.")
                    return
                valid_password = validate_password(password, kingdom_results[0])
                if not valid_password:
                    await interaction.followup.send(content="The password provided is incorrect.")
                    return
                await cursor.execute("Select Kingdom from KB_Armies where Army_Name = ?", (army_name,))
                army = await cursor.fetchone()
                if army:
                    if army[0] != kingdom:
                        await interaction.followup.send(content=f"Army {army_name} already exists in another kingdom.")
                    await cursor.execute(
                        "UPDATE KB_Armies SET consumption_size = ? WHERE Kingdom = ? and Army_Name = ?",
                        (consumption_size, kingdom, army_name))
                    await db.commit()
                    await interaction.followup.send(content=f"Army {army_name} has been updated.")
                else:
                    await cursor.execute(
                        "INSERT INTO KB_Armies (Kingdom, Army_Name, consumption_size) VALUES (?, ?, ?)",
                        (kingdom, army_name, consumption_size))
                    await db.commit()
                    await interaction.followup.send(content=f"Army {army_name} has been created.")
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"Error creating army: {e}")
            await interaction.followup.send(content="An error occurred while creating an army.")

    @army_group.command(name="delete", description="Delete an army")
    @app_commands.autocomplete(kingdom=kingdom_autocomplete)
    async def delete_army(self, interaction: discord.Interaction, kingdom: str, password: str, army_name: str):
        """This command is used to delete an army"""
        await interaction.response.defer(thinking=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute("SELECT Password FROM kb_Kingdoms WHERE Kingdom = ?", (kingdom,))
                kingdom_results = await cursor.fetchone()
                if not kingdom_results:
                    await interaction.followup.send(content=f"The kingdom of {kingdom} does not exist.")
                    return
                valid_password = validate_password(password, kingdom_results[0])
                if not valid_password:
                    await interaction.followup.send(content="The password provided is incorrect.")
                    return
                await cursor.execute("Select Army_Name from KB_Armies where Kingdom = ? and Army_Name = ?",
                                     (kingdom, army_name))
                army = await cursor.fetchone()
                if not army:
                    await interaction.followup.send(content=f"Army {army_name} does not exist.")
                    return
                await cursor.execute("DELETE FROM KB_Armies where Kingdom = ? and Army_Name = ?", (kingdom, army_name))
                await db.commit()
                await interaction.followup.send(content=f"Army {army_name} has been deleted.")
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"Error deleting army: {e}")
            await interaction.followup.send(content="An error occurred while deleting an army.")

    @kingdom_group.command(name="display", description="Display kingdom information")
    @app_commands.autocomplete(kingdom=kingdom_autocomplete)
    async def display_kingdom(self, interaction: discord.Interaction, kingdom: typing.Optional[str], page: int = 0):
        await interaction.response.defer(thinking=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                if kingdom:
                    await cursor.execute("SELECT Kingdom FROM KB_Kingdoms")
                    kingdom_results = await cursor.fetchall()
                    offset = -1
                    for kingdom, itx in enumerate(kingdom_results):
                        if kingdom == kingdom:
                            offset = kingdom
                            break
                    if offset == -1:
                        await interaction.followup.send(content=f"The kingdom of {kingdom} does not exist.")
                        return
                    view = KingdomView(
                        user_id=interaction.user.id,
                        guild_id=interaction.guild_id,
                        offset=offset,
                        limit=1,
                        player_name=interaction.user.name,
                        view_type=1,
                        interaction=interaction)
                else:
                    await cursor.execute("SELECT Count(Kingdom) FROM KB_Kingdoms")
                    kingdom_results = await cursor.fetchone()
                    if kingdom_results[0] == 0:
                        await interaction.followup.send(content="No kingdoms exist.")
                        return
                    offset = page * 5 if page * 5 < kingdom_results[0] else kingdom_results[0] - 5
                    view = KingdomView(
                        user_id=interaction.user.id,
                        guild_id=interaction.guild_id,
                        offset=offset,
                        limit=5,
                        player_name=interaction.user.name,
                        view_type=2,
                        interaction=interaction)
                await view.update_results()
                await view.create_embed()
                await view.send_initial_message()
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"Error displaying kingdom information: {e}")
            await interaction.followup.send(content="An error occurred while displaying kingdom information.")

    @settlement_group.command(name='display', description='Display settlement information')
    @app_commands.autocomplete(kingdom=kingdom_autocomplete)
    @app_commands.autocomplete(settlement=settlement_autocomplete)
    async def display_settlement(self, interaction: discord.Interaction, kingdom: str, settlement: str = None, page: int = 0):
        """This command is used to display settlement information"""
        await interaction.response.defer(thinking=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute("SELECT Kingdom FROM KB_Kingdoms")
                kingdom_results = await cursor.fetchall()
                if not kingdom_results:
                    await interaction.followup.send(content="No kingdoms exist.")
                    return
                offset = page * 5 if page * 5 < len(kingdom_results) else len(kingdom_results) - 5
                if not settlement:
                    view = SettlementView(
                        user_id=interaction.user.id,
                        guild_id=interaction.guild_id,
                        offset=offset,
                        limit=5,
                        player_name=interaction.user.name,
                        kingdom=kingdom,
                        view_type=2,
                        interaction=interaction)
                else:
                    await cursor.execute("SELECT Settlement FROM KB_Settlements WHERE Kingdom = ?", (kingdom,))
                    settlement_results = await cursor.fetchall()
                    if not settlement_results:
                        await interaction.followup.send(content=f"The kingdom of {kingdom} does not have any settlements.")
                        return
                    offset = -1
                    for idx, settlement_name in enumerate(settlement_results):
                        if settlement_name[0] == settlement:
                            offset = idx
                            break
                    if offset == -1:
                        await interaction.followup.send(content=f"The settlement of {settlement} does not exist.")
                        return
                    view = SettlementView(
                        user_id=interaction.user.id,
                        guild_id=interaction.guild_id,
                        offset=offset,
                        limit=1,
                        player_name=interaction.user.name,
                        kingdom=kingdom,
                        view_type=1,
                        interaction=interaction)
                await view.update_results()
                await view.create_embed()
                await view.send_initial_message()
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"Error displaying settlement information: {e}")
            await interaction.followup.send(content="An error occurred while displaying settlement information.")

    @hex_group.command(name='display', description='Display hex information')
    @app_commands.autocomplete(kingdom=kingdom_autocomplete)
    @app_commands.autocomplete(region=shared_functions.region_autocomplete)
    async def display_hex(self, interaction: discord.Interaction, region: str, kingdom: str = None, page: int = 0):
        try:
            await interaction.response.defer(thinking=True)
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                if kingdom:
                    await cursor.execute("SELECT Kingdom FROM KB_Kingdoms")
                    kingdom_results = await cursor.fetchall()
                    if not kingdom_results:
                        await interaction.followup.send(content="No kingdoms exist.")
                        return
                await cursor.execute("SELECT Count(Kingdom) FROM KB_Kingdoms WHERE Region = ?", (region,))
                kingdom_results = await cursor.fetchone()
                offset = page * 5 if page * 5 < kingdom_results[0] else kingdom_results[0] - 5
                view = HexView(
                    user_id=interaction.user.id,
                    guild_id=interaction.guild_id,
                    offset=offset,
                    limit=5,
                    kingdom=kingdom,
                    interaction=interaction,
                    region=region)
                await view.update_results()
                await view.create_embed()
                await view.send_initial_message()
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"Error displaying hex information: {e}")
            await interaction.followup.send(content="An error occurred while displaying hex information.")

    @hex_group.command(name='buildable', description='Display buildable hex improvements')
    async def display_buildable_hex(self, interaction: discord.Interaction, page: int = 0):
        """This command is used to display buildable hex improvements"""
        await interaction.response.defer(thinking=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute("SELECT Count(Kingdom) FROM KB_Kingdoms")
                kingdom_results = await cursor.fetchone()
                offset = page * 5 if page * 5 < kingdom_results[0] else kingdom_results[0] - 5
                view = ImprovementView(
                    user_id=interaction.user.id,
                    guild_id=interaction.guild_id,
                    offset=offset,
                    limit=5,
                    interaction=interaction)
                await view.update_results()
                await view.create_embed()
                await view.send_initial_message()
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"Error displaying buildable hex improvements: {e}")
            await interaction.followup.send(content="An error occurred while displaying buildable hex improvements.")

    @settlement_group.command(name='blueprints', description='Display settlement blueprints')
    @app_commands.autocomplete(kingdom=kingdom_autocomplete)
    async def display_settlement_blueprints(self, interaction: discord.Interaction, kingdom: str = None, page: int = 0):
        """This command is used to display settlement blueprints"""
        await interaction.response.defer(thinking=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                if kingdom:
                    await cursor.execute("SELECT Kingdom FROM KB_Kingdoms")
                    kingdom_results = await cursor.fetchall()
                    if not kingdom_results:
                        await interaction.followup.send(content="No kingdoms exist.")
                        return
                await cursor.execute("SELECT Count(Kingdom) FROM KB_Kingdoms")
                kingdom_results = await cursor.fetchone()
                offset = page * 5 if page * 5 < kingdom_results[0] else kingdom_results[0] - 5
                view = BlueprintView(
                    user_id=interaction.user.id,
                    guild_id=interaction.guild_id,
                    offset=offset,
                    limit=5,
                    interaction=interaction,
                    kingdom=kingdom
                )
                await view.update_results()
                await view.create_embed()
                await view.send_initial_message()
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"Error displaying settlement blueprints: {e}")
            await interaction.followup.send(content="An error occurred while displaying settlement blueprints.")

    @settlement_group.command(name='constructed', description='Display built settlement buildings')
    @app_commands.autocomplete(settlement=settlement_autocomplete)
    async def display_constructed_settlement(self, interaction: discord.Interaction, settlement: str = None, page: int = 0):
        """This command is used to display built settlement buildings"""
        await interaction.response.defer(thinking=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                if settlement:
                    await cursor.execute("SELECT Settlement FROM KB_Settlements")
                    settlement_results = await cursor.fetchall()
                    if not settlement_results:
                        await interaction.followup.send(content="No settlements exist.")
                        return
                await cursor.execute("SELECT Count(Kingdom) FROM KB_Kingdoms")
                kingdom_results = await cursor.fetchone()
                offset = page * 5 if page * 5 < kingdom_results[0] else kingdom_results[0] - 5
                view = SettlementBuildingsView(
                    user_id=interaction.user.id,
                    guild_id=interaction.guild_id,
                    offset=offset,
                    limit=5,
                    interaction=interaction,
                    settlement=settlement
                )
                await view.update_results()
                await view.create_embed()
                await view.send_initial_message()
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"Error displaying built settlement buildings: {e}")
            await interaction.followup.send(content="An error occurred while displaying built settlement buildings.")

    @army_group.command(name='display', description='Display army information')
    @app_commands.autocomplete(kingdom=kingdom_autocomplete)
    async def display_army(self, interaction: discord.Interaction, kingdom: str = None, page: int = 0):
        """This command is used to display army information"""
        await interaction.response.defer(thinking=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                if kingdom:
                    await cursor.execute("SELECT Kingdom FROM KB_Kingdoms")
                    kingdom_results = await cursor.fetchall()
                    if not kingdom_results:
                        await interaction.followup.send(content="No kingdoms exist.")
                        return
                await cursor.execute("SELECT Count(Kingdom) FROM KB_Kingdoms")
                kingdom_results = await cursor.fetchone()
                offset = page * 5 if page * 5 < kingdom_results[0] else kingdom_results[0] - 5
                view = ArmyView(
                    user_id=interaction.user.id,
                    guild_id=interaction.guild_id,
                    offset=offset,
                    limit=5,
                    interaction=interaction,
                    kingdom=kingdom
                )
                await view.update_results()
                await view.create_embed()
                await view.send_initial_message()
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"Error displaying army information: {e}")
            await interaction.followup.send(content="An error occurred while displaying army information.")


class KingdomView(shared_functions.DualView):
    def __init__(
            self,
            user_id: int,
            guild_id: int,
            offset: int,
            limit: int,
            player_name: str,
            kingdom: str,
            view_type: int,
            interaction: discord.Interaction):
        super().__init__(
            user_id=user_id,
            guild_id=guild_id,
            offset=offset,
            limit=limit,
            view_type=view_type,
            content="",
            interaction=interaction)
        self.max_items = None  # Cache total number of items
        self.view_type = view_type
        self.kingdom = kingdom
        self.player_name = player_name

    async def update_results(self):
        """Fetch the history of prestige request  for the current page."""
        try:
            async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute("""
                SELECT Kingdom FROM KB_Kingdoms 
                LIMIT ? OFFSET ?""", (self.limit, self.offset))
                kingdom_results = await cursor.fetchall()
                self.results = kingdom_results
        except aiosqlite.Error as e:
            logging.exception(
                f"Error fetching kingdom data: {e}"
            )

    async def create_embed(self):
        """Create the embed for the titles."""
        async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
            if self.view_type == 1:
                for kingdom in self.results:
                    self.kingdom = kingdom[0]
                    kingdom_information = await fetch_kingdom(guild_id=self.guild_id, kingdom=self.kingdom)
                    hex_information = await fetch_kingdom_hex_state(db=db, kingdom=self.kingdom)
                    building_information = await fetch_kingdom_building_state(db=db, kingdom=self.kingdom)
                    event_list = await fetch_kingdom_event_list(db=db, kingdom=self.kingdom)
                    event_state = await fetch_consequence_list(db=db, event_list=event_list)
                    army_state = await fetch_kingdom_army_state(db=db, kingdom=self.kingdom)
                    outgoing_trade = await fetch_kingdom_trade(db=db, source_kingdom=self.kingdom)
                    incoming_trade = await fetch_kingdom_trade(db=db, end_kingdom=self.kingdom)
                    hex_productivity = await fetch_kingdom_hex_output(db=db, kingdom=self.kingdom)
                    building_productivity = await fetch_kingdom_building_output(db=db, kingdom=self.kingdom)
                    self.embed = discord.Embed(
                        title=f"Detailed Kingdom Information for {self.kingdom}",
                        description=f"Kingdom {self.offset + 1} of {self.max_items // self.limit + 1}"
                    )
                    control_dc = safe_add(kingdom_information.control_dc, hex_information.control_dc)
                    size = hex_information.control_dc
                    economy = safe_add(kingdom_information.economy, hex_information.economy)
                    loyalty = safe_add(kingdom_information.loyalty, hex_information.loyalty)
                    stability = safe_add(kingdom_information.stability, hex_information.stability)
                    fame = safe_add(kingdom_information.fame, hex_information.fame)
                    unrest = safe_add(kingdom_information.unrest, hex_information.unrest)
                    consumption = safe_add(kingdom_information.consumption, hex_information.consumption)
                    consumption = safe_add(consumption, hex_information.size)
                    consumption = safe_add(consumption, army_state[0])
                    taxation = hex_information.build_points
                    control_dc = safe_add(control_dc, building_information.control_dc)
                    economy = safe_add(economy, building_information.economy)
                    loyalty = safe_add(loyalty, building_information.loyalty)
                    stability = safe_add(stability, building_information.stability)
                    fame = safe_add(fame, building_information.fame)
                    unrest = safe_add(unrest, building_information.unrest)
                    resource_utilization = await fetch_kingdom_requirements(
                        db=db,
                        kingdom=self.kingdom,
                        hex_info=hex_productivity,
                        building_info=building_productivity,
                        consumption=consumption,
                        incoming_trade=incoming_trade,
                        outgoing_trade=outgoing_trade
                    )
                    kingdom_info_content = f"""
                    **Size**: {size}, **Control DC**: {control_dc}, **Unrest**: {unrest} \r\n
                    **Economy**: {economy} **Loyalty**: {loyalty} **Stability**: {stability}\r\n
                    **Fame**: {fame} **Consumption**: {consumption}, Taxation {taxation}\r\n
                    """

                    self.embed.add_field(name="Kingdom Information", value=kingdom_info_content)
                    self.embed.add_field(name="Events", value=event_state)

                    resource_utilization_content = f"""
                    ***Grain***: {resource_utilization.grain}, **Produce**: {resource_utilization.produce}, **Husbandry**: {resource_utilization.husbandry}, **Seafood**: {resource_utilization.seafood}\r\n
                    **Ore**: {resource_utilization.ore}, **Stone**: {resource_utilization.stone}, **Wood**: {resource_utilization.lumber}, **Raw Textiles**: {resource_utilization.raw_textiles}\r\n
                    **Textiles**: {resource_utilization.textiles}, **Metallurgy**: {resource_utilization.metallurgy}, **Woodworking**: {resource_utilization.woodworking}, **Stoneworking**: {resource_utilization.stoneworking}\r\n
                    **Magical Consumables**: {resource_utilization.magical_consumables}, **Magical Items**: {resource_utilization.magical_items}, **Mundane Exotic**: {resource_utilization.mundane_exotic}, **Mundane Complex**: {resource_utilization.mundane_complex}\r\n
                    """
                    self.embed.add_field(name="Resource Utilization", value=resource_utilization_content)
            else:
                self.embed = discord.Embed(
                    title=f"Kingdom Information",
                    description=f"Page {self.offset // self.limit + 1} of {self.max_items // self.limit + 1}"
                )
                for kingdom in self.results:
                    self.kingdom = kingdom[0]
                    kingdom_information = await fetch_kingdom(guild_id=self.guild_id, kingdom=self.kingdom)
                    hex_information = await fetch_kingdom_hex_state(db=db, kingdom=self.kingdom)
                    building_information = await fetch_kingdom_building_state(db=db, kingdom=self.kingdom)
                    army_state = await fetch_kingdom_army_state(db=db, kingdom=self.kingdom)

                    control_dc = safe_add(kingdom_information.control_dc, hex_information.control_dc)
                    size = hex_information.control_dc
                    economy = safe_add(kingdom_information.economy, hex_information.economy)
                    loyalty = safe_add(kingdom_information.loyalty, hex_information.loyalty)
                    stability = safe_add(kingdom_information.stability, hex_information.stability)
                    fame = safe_add(kingdom_information.fame, hex_information.fame)
                    unrest = safe_add(kingdom_information.unrest, hex_information.unrest)
                    consumption = safe_add(kingdom_information.consumption, hex_information.consumption)
                    consumption = safe_add(consumption, hex_information.size)
                    consumption = safe_add(consumption, army_state[0])
                    taxation = hex_information.build_points
                    control_dc = safe_add(control_dc, building_information.control_dc)
                    economy = safe_add(economy, building_information.economy)
                    loyalty = safe_add(loyalty, building_information.loyalty)
                    stability = safe_add(stability, building_information.stability)
                    fame = safe_add(fame, building_information.fame)
                    unrest = safe_add(unrest, building_information.unrest)
                    kingdom_info_content = f"""
                                    **Size**: {size}, **Control DC**: {control_dc}, **Unrest**: {unrest} \r\n
                                    **Economy**: {economy} **Loyalty**: {loyalty} **Stability**: {stability}\r\n
                                    **Fame**: {fame} **Consumption**: {consumption}, Taxation {taxation}\r\n
                                    """
                    self.embed.add_field(name=f"Kingdom of {self.kingdom}", value=kingdom_info_content)

    async def get_max_items(self):
        """Get the total number of titles."""
        if self.max_items is None:
            async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
                cursor = await db.execute("SELECT COUNT(*) FROM KB_Kingdoms")
                count = await cursor.fetchone()
                self.max_items = count[0]
        return self.max_items

    async def on_view_change(self):
        self.view_type = 1 if self.view_type == 2 else 2
        if self.view_type == 1:
            self.limit = 5  # Change the limit to 5 for the summary view
        else:
            self.limit = 1  # Change the limit to 1 for the detailed view


class SettlementView(shared_functions.DualView):
    def __init__(
            self,
            user_id: int,
            guild_id: int,
            offset: int,
            limit: int,
            player_name: str,
            kingdom: str,
            view_type: int,
            interaction: discord.Interaction):
        super().__init__(
            user_id=user_id,
            guild_id=guild_id,
            offset=offset,
            limit=limit,
            view_type=view_type,
            content="",
            interaction=interaction)
        self.max_items = None  # Cache total number of items
        self.view_type = view_type
        self.kingdom = kingdom
        self.player_name = player_name

    async def update_results(self):
        """Fetch the history of prestige request  for the current page."""
        try:
            async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                if self.kingdom:
                    await cursor.execute("""
                    SELECT Settlement FROM KB_Settlements
                    WHERE Kingdom = ? 
                    LIMIT ? OFFSET ?""", (self.kingdom, self.limit, self.offset))
                else:
                    await cursor.execute("""
                    SELECT Settlement FROM KB_Settlements 
                    LIMIT ? OFFSET ?""", (self.limit, self.offset))
                self.results = await cursor.fetchall()

        except aiosqlite.Error as e:
            logging.exception(
                f"Error fetching kingdom data: {e}"
            )

    async def create_embed(self):
        """Create the embed for the titles."""
        async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
            if self.view_type == 1:
                for settlement in self.results:
                    settlement = settlement[0]
                    settlement_information = await fetch_settlement(guild_id=self.guild_id, settlement=settlement)
                    building_information = await fetch_settlement_building_state(db=db, settlement=settlement,
                                                                                 kingdom=settlement_information.kingdom)
                    event_list = await fetch_settlement_event_list(db=db, settlement=settlement)
                    event_state = await fetch_consequence_list(db=db, event_list=event_list)
                    self.embed = discord.Embed(
                        title=f"Detailed Kingdom Information for {settlement} of {settlement_information.kingdom}",
                        description=f"Settlement {self.offset + 1} of {self.max_items // self.limit + 1}"
                    )
                    size = safe_add(settlement_information.size, building_information.size)
                    population = size * 75
                    corruption = safe_add(settlement_information.corruption, building_information.corruption)
                    crime = safe_add(settlement_information.crime, building_information.crime)
                    productivity = safe_add(settlement_information.productivity, building_information.productivity)
                    law = safe_add(settlement_information.law, building_information.law)
                    lore = safe_add(settlement_information.lore, building_information.lore)
                    society = safe_add(settlement_information.society, building_information.society)
                    danger = safe_add(settlement_information.danger, building_information.danger)
                    defence = safe_add(settlement_information.defence, building_information.defence)
                    base_value = safe_add(settlement_information.base_value, building_information.base_value)
                    spellcasting = safe_add(settlement_information.spellcasting, building_information.spellcasting)
                    supply = safe_add(settlement_information.supply, building_information.supply)
                    decay = safe_add(settlement_information.decay, building_information.decay)

                    kingdom_info_content = f"""
                    **Size**: {size}, **Population**: {population}\r\n
                    **Corruption**: {corruption} **Crime**: {crime} **Productivity**: {productivity}\r\n
                    **Law**: {law} **Lore**: {lore} **Society**: {society}\r\n
                    **Danger**: {danger} **Defence**: {defence} **Base Value**: {base_value}\r\n
                    **Spellcasting**: {spellcasting} **Available Supply**: {supply}\r\n
                    """

                    self.embed.add_field(name="Kingdom Information", value=kingdom_info_content)
                    self.embed.add_field(name="Events", value=event_state)
            else:
                if self.kingdom:
                    self.embed = discord.Embed(
                        title=f"Settlement Information for {self.kingdom}",
                        description=f"Page {self.offset // self.limit + 1} of {self.max_items // self.limit + 1}"
                    )
                else:
                    self.embed = discord.Embed(
                        title=f"Settlement Information",
                        description=f"Page {self.offset // self.limit + 1} of {self.max_items // self.limit + 1}"
                    )
                for kingdom in self.results:
                    settlement = settlement[0]
                    settlement_information = await fetch_settlement(guild_id=self.guild_id, settlement=settlement)
                    building_information = await fetch_settlement_building_state(db=db, settlement=settlement,
                                                                                 kingdom=settlement_information.kingdom)
                    event_list = await fetch_settlement_event_list(db=db, settlement=settlement)
                    event_state = await fetch_consequence_list(db=db, event_list=event_list)
                    self.embed = discord.Embed(
                        title=f"Detailed Kingdom Information for {settlement} of {settlement_information.kingdom}",
                        description=f"Settlement {self.offset + 1} of {self.max_items // self.limit + 1}"
                    )
                    size = safe_add(settlement_information.size, building_information.size)
                    population = size * 75
                    corruption = safe_add(settlement_information.corruption, building_information.corruption)
                    crime = safe_add(settlement_information.crime, building_information.crime)
                    productivity = safe_add(settlement_information.productivity, building_information.productivity)
                    law = safe_add(settlement_information.law, building_information.law)
                    lore = safe_add(settlement_information.lore, building_information.lore)
                    society = safe_add(settlement_information.society, building_information.society)
                    danger = safe_add(settlement_information.danger, building_information.danger)
                    defence = safe_add(settlement_information.defence, building_information.defence)
                    base_value = safe_add(settlement_information.base_value, building_information.base_value)
                    spellcasting = safe_add(settlement_information.spellcasting, building_information.spellcasting)
                    supply = safe_add(settlement_information.supply, building_information.supply)
                    decay = safe_add(settlement_information.decay, building_information.decay)

                    kingdom_info_content = f"""
                    **Size**: {size}, **Population**: {population}\r\n
                    **Corruption**: {corruption} **Crime**: {crime} **Productivity**: {productivity}\r\n
                    **Law**: {law} **Lore**: {lore} **Society**: {society}\r\n
                    **Danger**: {danger} **Defence**: {defence} **Base Value**: {base_value}\r\n
                    **Spellcasting**: {spellcasting} **Available Supply**: {supply}\r\n
                    """

    async def get_max_items(self):
        """Get the total number of titles."""
        if self.max_items is None:
            async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
                cursor = await db.execute("SELECT COUNT(*) FROM KB_Kingdoms")
                count = await cursor.fetchone()
                self.max_items = count[0]
        return self.max_items

    async def on_view_change(self):
        self.view_type = 1 if self.view_type == 2 else 2
        if self.view_type == 1:
            self.limit = 5  # Change the limit to 5 for the summary view
        else:
            self.limit = 1  # Change the limit to 1 for the detailed view


class HexView(shared_functions.ShopView):
    """
    A paginated view for displaying hex data (kb_hexes) for a particular kingdom.
    """

    def __init__(self, user_id: int, guild_id: int, offset: int, limit: int,
                 region: str, kingdom: str, interaction: discord.Interaction):
        super().__init__(user_id=user_id, guild_id=guild_id, offset=offset, limit=limit, interaction=interaction,
                         content="")
        self.max_items = None
        self.results = []
        self.embed = None
        self.region = region
        self.kingdom = kingdom

    async def update_results(self):
        """
        Fetch hex rows for the current page for the given kingdom.
        """
        try:
            async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                if self.kingdom:
                    statement = """
                        SELECT 
                            KH.ID, KH.Kingdom, KS.Settlement, KH.Hex_Terrain, 
                            KH.Farm, KH.Ore, KH.Stone, KH.Wood, KH.Fish, KH.IsTown
                       FROM kb_hexes KH
                       LEFT JOIN KB_Settlements KS ON KH.ID = KS.Hex_ID
                       WHERE (KH.Kingdom = ? or KH.Kingdom = Null) and KH.Region = ? 
                        LIMIT ? OFFSET ?
                    """
                    await cursor.execute(statement, (self.kingdom, self.region, self.limit, self.offset))
                else:
                    statement = """
                                    SELECT 
                                        KH.ID, KH.Kingdom, KS.Settlement, KH.Hex_Terrain, 
                                        KH.Farm, KH.Ore, KH.Stone, KH.Wood, KH.Fish, KH.IsTown
                                    FROM kb_hexes KH
                                    LEFT JOIN KB_Settlements KS ON KH.ID = KS.Hex_ID
                                    WHERE KH.Region = ? 
                                    LIMIT ? OFFSET ?
                                """
                    await cursor.execute(statement, (self.region, self.limit, self.offset))
                self.results = await cursor.fetchall()
        except aiosqlite.Error as e:
            logging.exception(
                f"Error fetching hex data: {e}"
            )

    async def create_embed(self):
        """
        Create the embed showing hex data for the current page.
        """
        current_page = (self.offset // self.limit) + 1
        total_pages = ((await self.get_max_items() - 1) // self.limit) + 1
        if self.kingdom:
            self.embed = discord.Embed(
                title=f"Hexes for {self.kingdom}",
                description=f"Page {current_page} of {total_pages}"
            )
        else:
            self.embed = discord.Embed(
                title=f"Hexes for {self.region}",
                description=f"Page {current_page} of {total_pages}"
            )
        for row in self.results:
            (
                hex_id, kingdom, hex_terrain, settlement,
                farm, ore, stone, wood, fish, is_town
            ) = row
            if is_town:
                desc = f"Settlement: {settlement}\n"
            else:
                desc = f"Hex ID: {hex_id}\n"
                async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
                    cursor = await db.cursor()
                    await cursor.execute(
                        "SELECT Full_Name, Type, Subtype, Amount FROM KB_Hexes_Constructed WHERE ID = ?", (hex_id,))
                    hex_built = await cursor.fetchall()
                    if hex_built:
                        desc += f"Built: {', '.join([f'{amount} {name}(s) type: {type}, produces: {subtype} ' for name, type, subtype, amount in hex_built])}\n"
                    else:
                        desc += "Built: None\n"
            desc += (
                f"Max Farms: {farm}, Max Ore: {ore}, Max Stone: {stone}, Max Wood: {wood},  Max Fish: {fish}\n"
            )
            self.embed.add_field(name=f"Hex ID: {hex_id} of kingdom {kingdom}", value=desc, inline=False)

    async def get_max_items(self):
        """
        Return the total number of hexes for the given kingdom.
        """
        if self.max_items is None:
            async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
                if self.kingdom:
                    cursor = await db.execute(
                        "SELECT COUNT(*) FROM kb_hexes WHERE region = ? and (Kingdom = ? or Kingdom = Null)",
                        (self.kingdom,)
                    )
                else:
                    cursor = await db.execute(
                        "SELECT COUNT(*) FROM kb_hexes WHERE region = ?",
                        (self.region,)
                    )
                count = await cursor.fetchone()
                self.max_items = count[0]
        return self.max_items


class ImprovementView(shared_functions.ShopView):
    """
    A paginated view for displaying possible improvements for hexes (kb_Hexes_Improvements).
    """

    def __init__(self, user_id: int, guild_id: int, offset: int, limit: int,
                 interaction: discord.Interaction):
        super().__init__(user_id=user_id, guild_id=guild_id, offset=offset, limit=limit, interaction=interaction,
                         content="")
        self.max_items = None
        self.results = []
        self.embed = None

    async def update_results(self):
        """
        Fetch improvement rows for the current page.
        """
        statement = """
            SELECT 
                Full_Name, Type, Subtype, Quality, Build_Points,
                Economy, Loyalty, Stability, Unrest, Consumption, Defence, Taxation,
                Cavernous, Coastline, Desert, Forest, Hill, Jungle, Marsh, Mountain, 
                Plains, Swamp, Tundra, Water, Size
            FROM kb_Hexes_Improvements
            LIMIT ? OFFSET ?
        """
        async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
            cursor = await db.execute(statement, (self.limit, self.offset))
            self.results = await cursor.fetchall()

    async def create_embed(self):
        """
        Create the embed showing each improvement's stats.
        """
        current_page = (self.offset // self.limit) + 1
        total_pages = ((await self.get_max_items() - 1) // self.limit) + 1
        self.embed = discord.Embed(
            title="Hex Improvements",
            description=f"Page {current_page} of {total_pages}"
        )

        for row in self.results:
            (
                full_name, type, subtype, quality, build_points,
                economy, loyalty, stability, unrest, consumption, defence, taxation,
                cavernous, coastline, desert, forest, hill, jungle, marsh, mountain,
                plains, swamp, tundra, water
            ) = row

            # Gather all possible terrains
            terrains = []
            if cavernous: terrains.append(f"Cavernous Multiplier: {cavernous}")
            if coastline: terrains.append(f"Coastline Multiplier: {coastline}")
            if desert: terrains.append(f"Desert Multiplier: {desert}")
            if forest: terrains.append(f"Forest Multiplier: {forest}")
            if hill: terrains.append(f"Hill Multiplier: {hill}")
            if jungle: terrains.append(f"Jungle Multiplier: {jungle}")
            if marsh: terrains.append(f"Marsh Multiplier: {marsh}")
            if mountain: terrains.append(f"Mountain Multiplier: {mountain}")
            if plains: terrains.append(f"Plains Multiplier: {plains}")
            if swamp: terrains.append(f"Swamp Multiplier: {swamp}")
            if tundra: terrains.append(f"Tundra Multiplier: {tundra}")
            if water: terrains.append(f"Water Multiplier: {water}")
            if not terrains:
                terrains.append(
                    "Oops. For some reason THIS CANNOT BE BUILT ON ANY TERRAIN. Please report this to the devs.")
            terrain_str = ", ".join(terrains)

            desc = (
                f"**Type**: {type}, **Subtype**: {subtype}, **Quality**: {quality}\n"
                f"**Build Points required**: {build_points}\n"
                f"**Economy**: {economy}, **Loyalty**: {loyalty}, **Stability**: {stability}\n"
                f"**Unrest**: {unrest}, **Consumption**: {consumption}\n"
                f"**Defence**: {defence}, **Taxation**: {taxation}\n\n"
                f"__Available Terrains__:\n{terrain_str}"
            )

            self.embed.add_field(
                name=f"Improvement: {full_name}",
                value=desc,
                inline=False
            )

    async def get_max_items(self):
        """
        Return the total number of improvements in kb_Hexes_Improvements.
        """
        if self.max_items is None:
            async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
                cursor = await db.execute("SELECT COUNT(*) FROM kb_Hexes_Improvements")
                count = await cursor.fetchone()
                self.max_items = count[0]
        return self.max_items


class BlueprintView(shared_functions.ShopView):
    """
    A paginated view for displaying building blueprint data (kb_Buildings_Blueprints).
    """

    def __init__(
            self,
            user_id: int,
            guild_id: int,
            offset: int,
            limit: int,
            kingdom: str,
            interaction: discord.Interaction,
            order_by: str = 'Default'):
        super().__init__(user_id=user_id, guild_id=guild_id, offset=offset, limit=limit, interaction=interaction,
                         content="")
        self.max_items = None
        self.results = []
        self.embed = None
        self.order_by = order_by
        self.kingdom = kingdom

    async def update_results(self):
        """
        Fetch building blueprint rows for the current page.
        NOTE: We unify the table references to 'kb_Buildings_Blueprints'.
        """
        if self.kingdom:
            statement = """
                SELECT 
                    Full_Name, Type, Subtype, Quality, Build_Points, 
                    Economy, Loyalty, Stability, Corruption, Crime, Productivity, Law, Lore, Society, 
                    Fame, Unrest, Danger, Defence,
                    Base_Value, Spellcasting, Supply,
                    Settlement_Limit, District_Limit, Description
                FROM KB_Buildings_Permits KBP
                LEFT JOIN kb_Buildings_Blueprints ON KBB.Full_Name = KBP.Full_Name
                WHERE KBP.Kingdom = ?
            """
        else:
            statement = """
                SELECT 
                    Full_Name, Type, Subtype, Quality, Build_Points, 
                    Economy, Loyalty, Stability, Corruption, Crime, Productivity, Law, Lore, Society, 
                    Fame, Unrest, Danger, Defence,
                    Base_Value, Spellcasting, Supply,
                    Settlement_Limit, District_Limit, Description
                FROM kb_Buildings_Blueprints
            """
        if self.order_by == 'Default':
            statement += "Order by Full_Name Limit ? Offset ?"
        else:
            statement += "Order by Subtype desc, Full_Name LIMIT ? OFFSET ?"
        async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
            if self.kingdom:
                cursor = await db.execute(statement, (self.kingdom, self.limit, self.offset))
            else:
                cursor = await db.execute(statement, (self.limit, self.offset))
            self.results = await cursor.fetchall()

    async def create_embed(self):
        """
        Create the embed showing building blueprint data for the current page.
        """
        current_page = (self.offset // self.limit) + 1
        total_pages = ((await self.get_max_items() - 1) // self.limit) + 1
        self.embed = discord.Embed(
            title="Building Blueprints",
            description=f"Page {current_page} of {total_pages}"
        )

        for row in self.results:
            (
                full_name, type, subtype, quality, build_points,
                economy, loyalty, stability, corruption, crime, productivity, law, lore, society,
                fame, unrest, danger, defence,
                base_value, spellcasting, supply,
                settlement_limit, district_limit, description,
                upgrade, discount, tier
            ) = row

            desc = (
                f"""**Type**: {type}, **Subtype**: {subtype}, **Quality**: {quality}, **Tier**: {tier}\n"""
                f"**Economy**: {economy}, **Loyalty**: {loyalty}, **Stability**: {stability}, **Fame**: {fame}\n"
                f"**Unrest**: {unrest}, **Corruption**: {corruption}, **Crime**: {crime}, **Productivity**: {productivity}\n"
                f"**Law**: {law}, **Lore**: {lore}, **Society**: {society}, **Danger**: {danger}\n"
                f"**Defence**: {defence}, **Base Value**: {base_value}, **Spellcasting**: {spellcasting}, **Supply**: {supply}\n"
                f"**Settlement Limit**: {settlement_limit}, **District Limit**: {district_limit}"
            )
            desc += f"\n Upgrades to: {upgrade}\n" if upgrade else ""
            desc += f"\n Discounts: {discount}\n" if discount else ""

            desc += f"\n**Description**: {description}"
            self.embed.add_field(
                name=f"{full_name} (Cost: {build_points} BP)",
                value=desc,
                inline=False
            )

    async def get_max_items(self):
        """
        Return the total number of building blueprints in kb_Buildings_Blueprints.
        """
        if self.max_items is None:
            async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
                if self.kingdom:
                    cursor = await db.execute(
                        "SELECT COUNT(*) FROM kb_Buildings_Permits WHERE Kingdom = ?", (self.kingdom,)
                    )
                else:
                    cursor = await db.execute("SELECT COUNT(*) FROM kb_Buildings_Blueprints")
                count = await cursor.fetchone()
                self.max_items = count[0]
        return self.max_items


class SettlementBuildingsView(shared_functions.ShopView):
    """
    A paginated view for displaying building blueprint data (kb_Buildings_Blueprints).
    """

    def __init__(
            self,
            user_id: int,
            guild_id: int,
            settlement: str,
            offset: int,
            limit: int,
            interaction: discord.Interaction,
            order_by: str = 'Default'):
        super().__init__(user_id=user_id, guild_id=guild_id, offset=offset, limit=limit, interaction=interaction,
                         content="")
        self.max_items = None
        self.results = []
        self.embed = None
        self.settlement = settlement
        self.order_by = order_by

    async def update_results(self):
        """
        Fetch building blueprint rows for the current page.
        NOTE: We unify the table references to 'kb_Buildings_Blueprints'.
        """
        if self.order_by == 'Default':

            statement = """
                SELECT 
                    KB.Full_Name, KB.Type, KB.Subtype, KB.Amount, KB.Discounted,
                    KBB.Quality, KBB.Build_Points, 
                    KBB.Economy, KBB.Loyalty, KBB.Stability, KBB.Corruption, KBB.Crime, KBB.Productivity, KBB.Law, KBB.Lore, KBB.Society, 
                    KBB.Fame, KBB.Unrest, KBB.Danger, KBB.Defence,
                    KBB.Base_Value, KBB.Spellcasting, KBB.Supply,
                    KBB.Settlement_Limit, KBB.District_Limit, KBB.Description,
                    KBB.Upgrade, KBB.Discount, KBB.Tier
                FROM KB_Buildings KB
                LEFT JOIN kb_Buildings_Blueprints KBB ON KB.Full_Name = KBB.Full_Name 
                WHERE KB.Settlement = ?
                Order by Full_name
                LIMIT ? OFFSET ?
            """
        else:
            statement = f"""
                SELECT 
                    KB.Full_Name, KB.Type, KB.Subtype, KB.Amount, KB.Discounted,
                    KBB.Quality, KBB.Build_Points, 
                    KBB.Economy, KBB.Loyalty, KBB.Stability, KBB.Corruption, KBB.Crime, KBB.Productivity, KBB.Law, KBB.Lore, KBB.Society, 
                    KBB.Fame, KBB.Unrest, KBB.Danger, KBB.Defence,
                    KBB.Base_Value, KBB.Spellcasting, KBB.Supply,
                    KBB.Settlement_Limit, KBB.District_Limit, KBB.Description
                FROM KB_Buildings KB
                LEFT JOIN kb_Buildings_Blueprints KBB ON KB.Full_Name = KBB.Full_Name 
                WHERE KB.Settlement = ?
                Order by Subtype desc, Full_Name
                LIMIT ? OFFSET ?
            """
        async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
            cursor = await db.execute(statement, (self.settlement, self.limit, self.offset))
            self.results = await cursor.fetchall()

    async def create_embed(self):
        """
        Create the embed showing building blueprint data for the current page.
        """
        current_page = (self.offset // self.limit) + 1
        total_pages = ((await self.get_max_items() - 1) // self.limit) + 1
        self.embed = discord.Embed(
            title="Building Blueprints",
            description=f"Page {current_page} of {total_pages}"
        )

        for row in self.results:
            (
                full_name, type, subtype, amount, discounted,
                quality, build_points,
                economy, loyalty, stability, corruption, crime, productivity, law, lore, society,
                fame, unrest, danger, defence,
                base_value, spellcasting, supply,
                settlement_limit, district_limit, description,
                upgrade, discount, tier
            ) = row

            desc = (
                f"""**Type**: {type}, **Subtype**: {subtype}, **Quality**: {quality}, **Tier**: {tier}\n"""
                f"**Economy**: {economy}, **Loyalty**: {loyalty}, **Stability**: {stability}, **Fame**: {fame}\n"
                f"**Unrest**: {unrest}, **Corruption**: {corruption}, **Crime**: {crime}, **Productivity**: {productivity}\n"
                f"**Law**: {law}, **Lore**: {lore}, **Society**: {society}, **Danger**: {danger}\n"
                f"**Defence**: {defence}, **Base Value**: {base_value}, **Spellcasting**: {spellcasting}, **Supply**: {supply}\n"
                f"**Settlement Limit**: {settlement_limit}, **District Limit**: {district_limit}\n"
            )
            desc += f"\n Upgrades to: {upgrade}\n" if upgrade else ""
            desc += f"\n Discounts: {discount}\n, discounted: {discounted} buildings" if discount else ""

            desc += f"\n**Description**: {description}"
            self.embed.add_field(
                name=f"{amount} {full_name}",
                value=desc,
                inline=False
            )

    async def get_max_items(self):
        """
        Return the total number of building blueprints in kb_Buildings_Blueprints.
        """
        if self.max_items is None:
            async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
                cursor = await db.execute("SELECT COUNT(*) FROM KB_Buildings WHERE Settlement = ?", (self.settlement,))
                count = await cursor.fetchone()
                self.max_items = count[0]
        return self.max_items


class ArmyView(shared_functions.ShopView):
    """
    A paginated view for displaying building blueprint data (kb_Buildings_Blueprints).
    """

    def __init__(self, user_id: int, guild_id: int, offset: int, limit: int,
                 kingdom: str, interaction: discord.Interaction):
        super().__init__(user_id=user_id, guild_id=guild_id, offset=offset, limit=limit, interaction=interaction,
                         content="")
        self.max_items = None
        self.results = []
        self.embed = None
        self.kingdom = kingdom

    async def update_results(self):
        """
        Fetch building blueprint rows for the current page.
        NOTE: We unify the table references to 'kb_Buildings_Blueprints'.
        """
        statement = """
            SELECT 
                Kingdom, Army_Name, Consumption_Size
            FROM KB_Armies
            WHERE Kingdom = ?
            LIMIT ? OFFSET ?
        """
        async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
            cursor = await db.execute(statement, (self.kingdom, self.limit, self.offset))
            self.results = await cursor.fetchall()

    async def create_embed(self):
        """
        Create the embed showing building blueprint data for the current page.
        """
        current_page = (self.offset // self.limit) + 1
        total_pages = ((await self.get_max_items() - 1) // self.limit) + 1
        self.embed = discord.Embed(
            title=f"{self.kingdom}'s armies",
            description=f"Page {current_page} of {total_pages}"
        )

        for row in self.results:
            (
                kingdom, army_name, consumption_size
            ) = row

            self.embed.add_field(
                name=f"{army_name}",
                value=f"**Consumption Size**: {consumption_size}",
                inline=False
            )

    async def get_max_items(self):
        """
        Return the total number of building blueprints in kb_Buildings_Blueprints.
        """
        if self.max_items is None:
            async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
                cursor = await db.execute("SELECT COUNT(*) FROM KB_Armies where Kingdom = ?", (self.kingdom,))
                count = await cursor.fetchone()
                self.max_items = count[0]
        return self.max_items


class KingdomEventView(discord.ui.View):
    """Base class for shop views with pagination."""

    def __init__(self, user_id: int, guild_id: int, interaction: discord.Interaction,
                 kingdom: str,
                 intent: int):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.guild_id = guild_id
        self.interaction = interaction
        self.kingdom = kingdom
        self.intent = intent
        self.offset = 0
        self.limit = 10
        self.event_list = []
        self.max = None
        self.embed = None
        self.message = None
        self.results = None
        # Initialize buttons

    async def update_buttons(self):
        self.clear_items()
        await self.update_results()
        max_items = await self.get_max_items()
        first_page = self.offset <= 0
        last_page = self.offset + self.limit >= max_items

        first_page_button = discord.ui.Button(label='First Page', style=discord.ButtonStyle.primary, row=1)
        first_page_button.disabled = first_page
        previous_page_button = discord.ui.Button(label='Previous Page', style=discord.ButtonStyle.primary, row=1)
        previous_page_button.disabled = first_page
        change_page_button = discord.ui.Button(label='Change View', style=discord.ButtonStyle.primary, row=1)
        next_page_button = discord.ui.Button(label='Next Page', style=discord.ButtonStyle.primary, row=1)
        next_page_button.disabled = last_page
        last_page_button = discord.ui.Button(label='Last Page', style=discord.ButtonStyle.primary, row=1)
        last_page_button.disabled = last_page

        first_page_button.callback = self.first_page
        previous_page_button.callback = self.previous_page
        change_page_button.callback = self.change_page
        next_page_button.callback = self.next_page
        last_page_button.callback = self.last_page

        self.add_item(first_page_button)
        self.add_item(previous_page_button)
        self.add_item(change_page_button)
        self.add_item(next_page_button)
        self.add_item(last_page_button)

        for idx, event in enumerate(self.event_list):
            button = discord.ui.Button(label=event[0], style=discord.ButtonStyle.primary, row=2 + idx // 5)
            button.callback = self.create_button_callback(event)
            self.add_item(button)

    def create_button_callback(self, event):
        async def button_callback(interaction: discord.Interaction):
            await self.roll_check(interaction, event)

        return button_callback

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Ensure that only the user who initiated the view can interact with the buttons."""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "You cannot interact with this button.",
                ephemeral=True
            )
            return False
        return True

    async def first_page(self, interaction: discord.Interaction):
        """Handle moving to the first page."""
        await interaction.response.defer()
        if self.offset == 0:
            await interaction.response.send_message("You are already on the first page.", ephemeral=True)
            return
        self.offset = 0
        await self.update_buttons()
        await self.create_embed()
        await interaction.edit_original_response(
            embed=self.embed,
            view=self
        )

    async def previous_page(self, interaction: discord.Interaction):
        """Handle moving to the previous page."""
        await interaction.response.defer()
        if self.offset > 0:
            self.offset -= self.limit
            if self.offset < 0:
                self.offset = 0

            await self.update_buttons()
            await self.create_embed()
            await interaction.edit_original_response(
                embed=self.embed,
                view=self
            )
        else:
            await interaction.followup.send("You are on the first page.", ephemeral=True)

    async def change_page(self, interaction: discord.Interaction):
        """Handle changing the view."""
        await interaction.response.defer()
        self.offset = 0
        if self.intent == 1:
            self.intent = 2
        elif self.intent == 2:
            self.intent = 3
        elif self.intent == 3:
            self.intent = 1
        await self.update_buttons()
        await self.create_embed()
        await interaction.edit_original_response(
            embed=self.embed,
            view=self
        )

    async def next_page(self, interaction: discord.Interaction):
        """Handle moving to the next page."""
        await interaction.response.defer()
        max_items = await self.get_max_items()
        if self.offset + self.limit < max_items:
            self.offset += self.limit
            await self.update_buttons()
            await self.create_embed()
            await interaction.edit_original_response(
                embed=self.embed,
                view=self
            )
        else:
            await interaction.followup.send("You are on the last page.", ephemeral=True)

    async def last_page(self, interaction: discord.Interaction):
        """Handle moving to the last page."""
        await interaction.response.defer()
        max_items = await self.get_max_items()
        last_page_offset = (max_items // self.limit) * self.limit
        if self.offset != last_page_offset:
            self.offset = last_page_offset
            await self.update_buttons()
            await self.create_embed()
            await interaction.edit_original_response(
                embed=self.embed,
                view=self
            )
        else:
            await interaction.followup.send("You are on the last page.", ephemeral=True)

    async def send_initial_message(self):
        """Send the initial message with the view."""
        try:
            await self.update_buttons()
            await self.create_embed()
            await self.interaction.followup.send(
                embed=self.embed,
                view=self
            )
            self.message = self.interaction.original_response()
        except (discord.HTTPException, AttributeError) as e:
            logging.error(f"Failed to send message: {e} in guild {self.interaction.guild.id} for {self.user_id}")

    async def on_timeout(self):
        """Disable buttons when the view times out."""
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(embed=self.embed, view=self)
            except discord.HTTPException as e:
                logging.error(f"Failed to edit message on timeout: {e}")

    async def update_results(self):
        """Fetch the results for the current page. To be implemented in subclasses."""
        if self.intent == 1:
            statement = """
                            SELECT ID, Type, Kingdom, Settlement, Hex, Name, Effect, Duration, Check_A, Check_A_Status, Check_B, Check_B_Status
                            FROM KB_Events_Active 
                            WHERE Kingdom = ? AND Type = 'Problematic' 
                            Limit ? Offset ?
                        """
            event_statement = """
                        SELECT ID, Type, Kingdom, Settlement, Hex, Name, Effect, Duration, Check_A, Check_A_Status, Check_B, Check_B_Status
                        FROM KB_Events_Active 
                        WHERE Kingdom = ? AND Type = 'Problematic'  AND (Check_A IS NOT NULL OR Check_B IS NOT NULL)
                        Limit ? Offset ?
                        """
        elif self.intent == 2:
            statement = """
                        SELECT ID, Type, Kingdom, Settlement, Hex, Name, Effect, Duration, Check_A, Check_A_Status, Check_B, Check_B_Status
                        FROM KB_Events_Active 
                        WHERE Kingdom = ? 
                        Limit ? Offset ?
                        """
            event_statement = """
            SELECT ID, Type, Kingdom, Settlement, Hex, Name, Effect, Duration, Check_A, Check_A_Status, Check_B, Check_B_Status
            FROM KB_Events_Active 
            WHERE Kingdom = ?  AND (Check_A IS NOT NULL OR Check_B IS NOT NULL)
            Limit ? Offset ?
            """
        else:
            statement = """
                            SELECT ID, Type, Kingdom, Settlement, Hex, Name, Effect, Duration, Check_A, Check_A_Status, Check_B, Check_B_Status
                            FROM KB_Events_Active 
                            WHERE Kingdom = ? AND Duration > 0 
                            Limit ? Offset ?
                        """
            event_statement = """
                                SELECT Name, Kingdom, Settlement, Check_A, Check_B, Check_A_Status, Check_B_Status
                                FROM KB_Events_Active 
                                WHERE Kingdom = ? AND Duration > 0 AND (Check_A IS NOT NULL OR Check_B IS NOT NULL)
                                Limit ? Offset ?
                        """
        async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute(statement, (self.kingdom, self.limit, self.offset))
            self.results = await cursor.fetchall()
            await cursor.execute(event_statement, (self.kingdom, self.limit, self.offset))
            self.event_list = await cursor.fetchall()

    async def create_embed(self):
        """Create the embed for the current page. To be implemented in subclasses."""
        current_page = (self.offset // self.limit) + 1
        total_pages = ((await self.get_max_items() - 1) // self.limit) + 1
        if self.intent == 1:
            self.embed = discord.Embed(
                title=f"Problematic Events for {self.kingdom}",
                description=f"Page {current_page} of {total_pages}")
        elif self.intent == 2:
            self.embed = discord.Embed(
                title=f"Ongoing Events for {self.kingdom}",
                description=f"Page {current_page} of {total_pages}")
        elif self.intent == 3:
            self.embed = discord.Embed(
                title=f"Temporary Events for {self.kingdom}",
                description=f"Page {current_page} of {total_pages}")
        for item in self.results:
            (id, type, kingdom, settlement, hex, name, effect, duration, check_a, check_a_status, check_b,
             check_b_status) = item
            status_dict = {0: "Not Attempted", 1: "Passed", -1: "Failed"}
            duration = f"{duration} turns" if duration > 0 else "Ongoing"
            field_content = f"**Type**: {type}, Duration: {duration}"
            field_content += f", **Settlement**: {settlement}" if settlement else ""
            field_content += f", **Hex**: {hex}" if hex else ""
            field_content += f"\r\n{effect}"
            field_content += f"\r\n**{check_b}**: {status_dict[check_a_status]}" if check_a else ""
            field_content += f"\r\n**{check_b}**: {status_dict[check_b_status]}" if check_b else ""
            async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
                cursor = await db.execute(
                    "SELECT Name, Severity, Type, Value, Reroll FROM KB_Events_Consequence where Name = ? Order BY Severity asc",
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
                    (name, severity, type, value, reroll) = consequence
                    field_content += f"\r\n**Consequence**: {name}, **Severity**: {consequence_severity_dict[severity]}, **Effects**: {type}, **Value**: {value}, **Reroll**: {consequence_rolltype_dict[reroll]}"
            self.embed.add_field(name=f'**Event**: {name} ID: {id}', value=field_content, inline=False)

    async def get_max_items(self):
        """Get the total number of items. To be implemented in subclasses."""
        if self.intent == 1:
            statement = """
                            SELECT COUNT(*) 
                            FROM KB_Events_Active 
                            WHERE Kingdom = ? AND Type = 'Problematic'
                        """
        elif self.intent == 2:
            statement = """
                            SELECT COUNT(*) 
                            FROM KB_Events_Active 
                            WHERE Kingdom = ?
                        """
        elif self.intent == 3:
            statement = """
                            SELECT COUNT(*) 
                            FROM KB_Events_Active 
                            WHERE Kingdom = ? AND Duration > 0
                        """
        async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
            cursor = await db.execute(statement, (self.kingdom,))
            count = await cursor.fetchone()
            return count[0]

    async def roll_check(self, interaction: discord.Interaction, event: aiosqlite.Row):
        """Prompt the user to roll Check_A and Check_B if available."""
        await interaction.response.defer()
        (event_id, event_name, kingdom, settlement, hex, name, effect, duration, check_a, check_a_status, check_b,
         check_b_status) = event
        check_prompts = []
        if check_a:
            check_prompts.append(f"**Roll for {check_a}**")
        if check_b:
            check_prompts.append(f"**Roll for {check_b}**")

        check_prompt_text = "\n".join(check_prompts) if check_prompts else "No checks required."

        embed = discord.Embed(
            title=f"Event Roll: {event_name} (ID: {event_id})",
            description=check_prompt_text,
            color=discord.Color.blue()
        )
        view = CheckButton(check_a=check_a, check_b=check_b, kingdom=self.kingdom, settlement=None,
                           guild_id=self.guild_id, event_id=event_id)

        await interaction.followup.send(embed=embed, ephemeral=True, view=view)


class CheckButton(discord.ui.View):
    def __init__(self, check_a: str, check_b: str, kingdom: str, settlement: typing.Optional[str], guild_id: int,
                 event_id):
        super().__init__(timeout=9000)
        self.check_a = check_a
        self.check_b = check_b
        self.kingdom = kingdom
        self.guild_id = guild_id
        self.event_id = event_id
        self.settlement = settlement
        if check_a:
            button = discord.ui.Button(label=check_a, style=discord.ButtonStyle.primary, row=1)
            button.callback = self.create_button_callback(check=check_a, version="A")
            self.add_item(button)
        if check_b:
            button = discord.ui.Button(label=check_b, style=discord.ButtonStyle.primary, row=1)
            button.callback = self.create_button_callback(check=check_b, version="B")
            self.add_item(button)

    def create_button_callback(self, check: str, version: str):
        async def button_callback(interaction: discord.Interaction):
            await self.handle_button_check(interaction, check=check, version=version)

        return button_callback

    async def handle_button_check(self, interaction: discord.Interaction, check: str, version: str):
        try:
            async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                if version == "A":
                    await cursor.execute("SELECT Check_A_Status, Name from KB_Events_Active where ID = ?",
                                         (self.event_id,))
                elif version == "B":
                    await cursor.execute("SELECT Check_B_Status, Name from KB_Events_Active where ID = ?",
                                         (self.event_id,))
                check_status = await cursor.fetchone()
                if check_status[0] != 0:
                    await interaction.response.send_message(
                        f"{check} has already been rolled for.", ephemeral=True
                    )
                    return
                if check == "Loyalty":
                    statement = "SELECT Control_DC, Loyalty From KB_Kingdoms where Kingdom = ?"
                elif check == "Stability":
                    statement = "SELECT  Control_DC, Stability From KB_Kingdoms where Kingdom = ?"
                elif check == "Economy":
                    statement = "SELECT  Control_DC, Economy From KB_Kingdoms where Kingdom = ?"
                await cursor.execute(statement, (self.kingdom,))
                result = await cursor.fetchone()
                await cursor.execute("Select Bonus, Penalty FROM KB_Events WHERE Name = ?", (check_status[1],))
                bonus_penalty = await cursor.fetchone()
                check_result = random.randint(1, 20) + result[1]
                if bonus_penalty[0]:
                    check_bonus = kingdom_dict.get(bonus_penalty[0], None)
                    check_bonus = settlement_dict.get(bonus_penalty[0], None) if not check_bonus else check_bonus
                    if check_bonus:
                        await cursor.execute(
                            f"SELECT Sum(Amount) from KB_Buildings Where Kingdom = ? and Settlement = ? AND {check_bonus} > 0",
                            (self.kingdom, self.settlement))
                    else:
                        await cursor.execute(
                            "SELECT Sum(Amount) from KB_Buildings Where Kingdom = ? and Settlement = ? AND Type = ?",
                            (self.kingdom, self.settlement, bonus_penalty[1]))
                    check_bonus = await cursor.fetchone()
                    check_result += check_bonus[0]
                elif bonus_penalty[1]:
                    check_penalty = kingdom_dict.get(bonus_penalty[1], None)
                    check_penalty = settlement_dict.get(bonus_penalty[1],
                                                        None) if not check_penalty else check_penalty
                    if check_penalty:
                        await cursor.execute(
                            f"SELECT Sum(Amount) from KB_Buildings Where Kingdom = ? and Settlement = ? AND {check_penalty} > 0",
                            (self.kingdom, self.settlement))
                    else:
                        await cursor.execute(
                            "SELECT Sum(Amount) from KB_Buildings Where Kingdom = ? and Settlement = ? AND Type = ?",
                            (self.kingdom, self.settlement, bonus_penalty[1]))
                    check_penalty = await cursor.fetchone()
                    check_result -= check_penalty[0]
                final_response = f"Rolling for {check} with a result of {check_result}."
                final_result = 1 if check_result >= result[0] else -1
                final_response += f"\n{check} check {'passed' if final_result == 1 else 'failed'}"
                if version == "A":
                    statement = "UPDATE KB_Events_Active Set Check_A_Status = ? where ID = ?"
                else:
                    statement = "UPDATE KB_Events_Active Set Check_B_Status = ? where ID = ?"
                await cursor.execute(statement, (final_result, self.event_id))
                await db.commit()
                await interaction.response.send_message(content=final_response, ephemeral=True)
                self.view.stop()
        except Exception as e:
            logging.exception(f"Error in Checkbutton callback: {e}")
            await interaction.response.send_message(
                "An error occurred while finalizing your availability.", ephemeral=True
            )


class TradeView(shared_functions.RecipientAcknowledgementView):
    def __init__(
            self,
            allowed_user_id: int,
            requester_name: str,
            requester_id: int,
            character_name: str,
            recipient_name: str,
            requesting_kingdom: str,
            sending_kingdom: str,
            seafood: int,
            husbandry: int,
            grain: int,
            produce: int,
            textiles: int,
            metallurgy: int,
            woodworking: int,
            stoneworking: int,
            magical_consumables: int,
            magical_items: int,
            mundane_exotic: int,
            mundane_complex: int,
            lumber: int,
            stone: int,
            ore: int,
            raw_textiles: int,
            bot: commands.Bot,
            guild_id: int,
            interaction: discord.Interaction
    ):
        super().__init__(allowed_user_id=allowed_user_id, interaction=interaction,
                         content=f"<@{allowed_user_id}>, please accept or request this transaction.")
        self.guild_id = guild_id
        self.requester_name = requester_name
        self.requester_id = requester_id
        self.character_name = character_name
        self.recipient_name = recipient_name  # Name of the recipient
        self.bot = bot
        self.embed = None
        self.requesting_kingdom = requesting_kingdom
        self.sending_kingdom = sending_kingdom
        self.seafood = seafood
        self.husbandry = husbandry
        self.grain = grain
        self.produce = produce
        self.textiles = textiles
        self.metallurgy = metallurgy
        self.woodworking = woodworking
        self.stoneworking = stoneworking
        self.magical_consumables = magical_consumables
        self.magical_items = magical_items
        self.mundane_exotic = mundane_exotic
        self.mundane_complex = mundane_complex
        self.lumber = lumber
        self.stone = stone
        self.ore = ore
        self.raw_textiles = raw_textiles

    async def accepted(self, interaction: discord.Interaction):
        """Handle the approval logic."""
        # Update the database to mark the proposition as accepted
        # Adjust prestige, log the transaction, notify the requester, etc.

        self.embed = discord.Embed(
            title=f"{self.requester_name}'s Kingdom of {self.requesting_kingdom} has opened trade with {self.recipient_name}'s kingdom of {self.sending_kingdom}",
            description=f"The request of trade has been accepted by <@{self.allowed_user_id}>'s {self.sending_kingdom}.",
            color=discord.Color.green()
        )
        # Additional logic such as notifying the requester
        async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as conn:
            cursor = await conn.cursor()
            await cursor.execute("""
            INSERT INTO KB_Trade (
            Source_Kingdom, End_Kingdom, 
            Seafood, Husbandry, Grain, Produce, 
            Wood, Stone, Ore, Raw_Textiles, 
            Textiles, Metallurgy, Woodworking, Stoneworking, 
            Magical_Consumables, Magical_Items, Mundane_Exotic, Mundane_Complex)
            VALUES (
            ?, ?, 
            ?, ?, ?, ?, 
            ?, ?, ?, ?, 
            ?, ?, ?, ?, 
            ?, ?, ?, ?)
            """, (
                self.requesting_kingdom, self.sending_kingdom,
                self.seafood, self.husbandry, self.grain, self.produce,
                self.lumber, self.stone, self.ore, self.raw_textiles,
                self.textiles, self.metallurgy, self.woodworking, self.stoneworking,
                self.magical_consumables, self.magical_items, self.mundane_exotic, self.mundane_complex))
            await conn.commit()

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
        self.embed = discord.Embed(
            title=f"{self.character_name}'s Trade Request",
            description=f"{self.character_name} has requested to trade with {self.recipient_name}.\n"
                        f"Please accept or reject this transaction.",
            color=discord.Color.blurple()
        )
        if any((self.seafood, self.produce, self.grain, self.husbandry)):
            self.embed.add_field(name="Food",
                                 value=f"Seafood: {self.seafood}\nProduce: {self.produce}\nGrain: {self.grain}\nHusbandry: {self.husbandry}")
        if any((self.ore, self.stone, self.lumber, self.raw_textiles)):
            self.embed.add_field(name="Raw Materials",
                                 value=f"Ore: {self.ore}\nStone: {self.stone}\nLumber: {self.lumber}\nRaw Textiles: {self.raw_textiles}")
        if any((self.textiles, self.metallurgy, self.woodworking, self.stoneworking)):
            self.embed.add_field(name="Crafts",
                                 value=f"Textiles: {self.textiles}\nMetallurgy: {self.metallurgy}\nWoodworking: {self.woodworking}\nStoneworking: {self.stoneworking}")
        if any((self.magical_consumables, self.magical_items, self.mundane_exotic, self.mundane_complex)):
            self.embed.add_field(name="Specialty",
                                 value=f"Magical Consumables: {self.magical_consumables}\nMagical Items: {self.magical_items}\nMundane Exotic: {self.mundane_exotic}\nMundane Complex: {self.mundane_complex}")
        self.embed.set_author(name=self.requester_name)
        self.embed.set_footer(text="Please accept or reject this transaction before it expires.")


logging.basicConfig(
    level=logging.INFO,  # Set the minimum logging level
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='application.log',  # Log to a file
    filemode='a'  # Append to the file
)
