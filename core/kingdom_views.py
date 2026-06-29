import discord
import logging
import typing
import asyncio
import aiosqlite
import random
from discord.ext import commands
from core.views import ShopView, RecipientAcknowledgementView, DualView, NewDualView
from core.kingdom_actions import update_leader
from core.kingdom import kingdom_dict, settlement_dict
from core.kingdom_fetching import (
    fetch_kingdom,
    fetch_kingdom_event_list, fetch_consequence_list, fetch_kingdom_army_state,
    fetch_kingdom_trade, fetch_kingdom_hex_output, fetch_kingdom_building_output,
    fetch_kingdom_requirements, fetch_settlement_base, fetch_settlement_building_state,
    fetch_settlement_event_list, fetch_resources, fetch_settlement
)
from core.utils import safe_add, get_gold_breakdown

class AttributeSelect(discord.ui.Select):
    def __init__(self, options):
        super().__init__(
            placeholder='Select an Attribute...',
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        try:
            await interaction.response.defer()
            if view:
                view.attribute = self.values[0]
                # Remove the attribute select from the view
                view.clear_items()
                # Proceed to modifier selection
                await view.proceed_to_modifier_selection()

        except Exception as e:
            logging.exception(f"Error in AttributeSelect callback: {e}")
            await interaction.followup.send(
                "An error occurred while selecting the attribute.", ephemeral=True
            )
            if view:
                view.stop()


class LeadershipModifier(discord.ui.Select):
    def __init__(self, options):
        super().__init__(
            placeholder='Select a kingdom stat to modify...',
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        try:
            await interaction.response.defer()
            if view:
                selected_modifier = self.values[0]
                modifier_value = getattr(view, selected_modifier.lower())
                # Update the modified value
                setattr(view, f'{selected_modifier.lower()}_modified', modifier_value)
                view.modifier_selection_count += 1
                # Remove previous modifier select
                view.clear_items()
                # Proceed to the next modifier selection
                await view.proceed_to_modifier_selection()
        except Exception as e:
            logging.exception(f"Error in  LeadershipModifier callback: {e}")
            await interaction.followup.send(
                "An error occurred while selecting the modifier.", ephemeral=True
            )
            if view:
                view.stop()


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
        # Attribute Selection
        if options is None or len(options) == 0:
            self.stop()
        elif len(options) == 1:
            asyncio.create_task(self.send_initial_message())
            self.attribute = options[0].value
            # Proceed to modifier selection
            asyncio.create_task(self.proceed_to_modifier_selection())
        else:
            asyncio.create_task(self.send_initial_message())
            # Multiple attributes, show selection
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
        if self.modifier_selection_count < len(self.modifier_fields) and self.additional > 0:
            # Create options for modifiers
            options = [
                discord.SelectOption(label=field, value=field)
                for field in self.modifier_fields
                if getattr(self, f'{field.lower()}_modified') == 0  # Skip already selected
            ]
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

class HexView(ShopView):
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
                hex_id, kingdom, settlement, hex_terrain,
                farm, ore, stone, wood, fish, is_town
            ) = row
            if is_town:
                desc = f"Settlement: {settlement}\r\n\n"
            else:
                desc = ""
                async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
                    cursor = await db.cursor()
                    await cursor.execute(
                        "SELECT KHC.Full_Name, Type, Subtype, Amount FROM KB_Hexes_Constructed KHC Left Join KB_hexes_Improvements KHI on KHI.full_name = KHC.Full_Name WHERE ID = ?", (hex_id,))
                    hex_built = await cursor.fetchall()
                    if hex_built:
                        desc += f"Built: {', '.join([f'{amount} {name}(s) type: {type}, produces: {subtype} ' for name, type, subtype, amount in hex_built])}\n"
                    else:
                        desc += "Built: None\n"
                desc += (
                    f"Max Farms: {farm}, Max Ore: {ore}, Max Stone: {stone}, Max Wood: {wood},  Max Fish: {fish}\n"
                )
            self.embed.add_field(name=f"kingdom: {kingdom} ID: {hex_id}", value=desc, inline=False)

    async def get_max_items(self):
        """
        Return the total number of hexes for the given kingdom.
        """
        if self.max_items is None:
            async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
                if self.kingdom:
                    cursor = await db.execute(
                        "SELECT COUNT(*) FROM kb_hexes WHERE region = ? and (Kingdom = ? or Kingdom = Null)",
                        (self.region, self.kingdom)
                    )
                else:
                    cursor = await db.execute(
                        "SELECT COUNT(*) FROM kb_hexes WHERE region = ?",
                        (self.region,)
                    )
                count = await cursor.fetchone()
                self.max_items = count[0]
        return self.max_items


class ImprovementView(ShopView):
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
                Cavernous, Coastline, Desert, Forest, Hills, Jungle, Marsh, Mountains, 
                Plains, Water, Size
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
                plains,  water, size
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


class BlueprintView(ShopView):
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
                    KBB.Full_Name, Type, Subtype, Quality, Build_Points, 
                    Economy, Loyalty, Stability, Corruption, Crime, Productivity, Law, Lore, Society, 
                    Fame, Unrest, Danger, Defence,
                    Base_Value, Spellcasting, Supply,
                    Settlement_Limit, District_Limit, Description,
                    upgrade, discount, tier
                FROM KB_Buildings_Permits KBP
                LEFT JOIN kb_Buildings_Blueprints KBB ON KBB.Full_Name = KBP.Full_Name
                WHERE KBP.Kingdom = ?
            """
        else:
            statement = """
                SELECT 
                    Full_Name, Type, Subtype, Quality, Build_Points, 
                    Economy, Loyalty, Stability, Corruption, Crime, Productivity, Law, Lore, Society, 
                    Fame, Unrest, Danger, Defence,
                    Base_Value, Spellcasting, Supply,
                    Settlement_Limit, District_Limit, Description,
                    upgrade, discount, tier
                FROM kb_Buildings_Blueprints KBB
            """
        if self.order_by == 'Default':
            statement += "Order by KBB.Full_Name Limit ? Offset ?"
        else:
            statement += "Order by Subtype desc, Full_Name LIMIT ? OFFSET ?"
        async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
            print(statement)
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


class SettlementBuildingsView(ShopView):
    """
    A paginated view for displaying building blueprint data (kb_Buildings_Blueprints).
    """

    def __init__(
            self,
            user_id: int,
            guild_id: int,
            kingdom: str,
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
        self.kingdom = kingdom

    async def update_results(self):
        """
        Fetch building blueprint rows for the current page.
        NOTE: We unify the table references to 'kb_Buildings_Blueprints'.
        """
        async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:

            if self.settlement:
                statement = """
                    SELECT 
                        Settlement, KB.Full_Name, KBB.Type, KBB.Subtype, KB.Amount, KB.Discounted,
                        KBB.Quality, KBB.Build_Points, 
                        KBB.Economy, KBB.Loyalty, KBB.Stability, KBB.Corruption, KBB.Crime, KBB.Productivity, KBB.Law, KBB.Lore, KBB.Society, 
                        KBB.Fame, KBB.Unrest, KBB.Danger, KBB.Defence,
                        KBB.Base_Value, KBB.Spellcasting, KBB.Supply,
                        KBB.Settlement_Limit, KBB.District_Limit, KBB.Description,
                        KBB.Upgrade, KBB.Discount, KBB.Tier
                    FROM KB_Buildings KB
                    LEFT JOIN kb_Buildings_Blueprints KBB ON KB.Full_Name = KBB.Full_Name 
                    WHERE KB.Kingdom = ? and Kingdom = ? 
                    Order by kb.Full_name
                    LIMIT ? OFFSET ?
                """
                cursor = await db.execute(statement, (self.kingdom, self.settlement, self.limit, self.offset))
            else:
                statement = f"""
                    SELECT 
                        Settlement, KB.Full_Name, KBB.Type, KBB.Subtype, KB.Amount, KB.Discounted,
                        KBB.Quality, KBB.Build_Points, 
                        KBB.Economy, KBB.Loyalty, KBB.Stability, KBB.Corruption, KBB.Crime, KBB.Productivity, KBB.Law, KBB.Lore, KBB.Society, 
                        KBB.Fame, KBB.Unrest, KBB.Danger, KBB.Defence,
                        KBB.Base_Value, KBB.Spellcasting, KBB.Supply,
                        KBB.Settlement_Limit, KBB.District_Limit, KBB.Description,
                        upgrade, discount, tier
                    FROM KB_Buildings KB
                    LEFT JOIN kb_Buildings_Blueprints KBB ON KB.Full_Name = KBB.Full_Name 
                    WHERE KB.Kingdom = ?
                    Order by Subtype desc, kb.Full_Name
                    LIMIT ? OFFSET ?
                """
                cursor = await db.execute(statement, (self.kingdom, self.limit, self.offset))

            self.results = await cursor.fetchall()

    async def create_embed(self):
        """
        Create the embed showing building blueprint data for the current page.
        """
        current_page = (self.offset // self.limit) + 1
        total_pages = ((await self.get_max_items() - 1) // self.limit) + 1
        if self.settlement:
            self.embed = discord.Embed(
                title=f"{self.kingdom}'s Buildings in {self.settlement}",
                description=f"Page {current_page} of {total_pages}"
            )
        else:
            self.embed = discord.Embed(
                title=f"{self.kingdom}'s Buildings Constructed",
                description=f"Page {current_page} of {total_pages}"
            )

        for row in self.results:
            (
                settlement, full_name, building_type, subtype, amount, discounted,
                quality, build_points,
                economy, loyalty, stability, corruption, crime, productivity, law, lore, society,
                fame, unrest, danger, defence,
                base_value, spellcasting, supply,
                settlement_limit, district_limit, description,
                upgrade, discount, tier
            ) = row

            desc = (
                f"""**Type**: {building_type}, **Subtype**: {subtype}, **Quality**: {quality}, **Tier**: {tier}\n"""
                f"**Economy**: {economy}, **Loyalty**: {loyalty}, **Stability**: {stability}, **Fame**: {fame}\n"
                f"**Unrest**: {unrest}, **Corruption**: {corruption}, **Crime**: {crime}, **Productivity**: {productivity}\n"
                f"**Law**: {law}, **Lore**: {lore}, **Society**: {society}, **Danger**: {danger}\n"
                f"**Defence**: {defence}, **Base Value**: {base_value}, **Spellcasting**: {spellcasting}, **Supply**: {supply}\n"
                f"**Settlement Limit**: {settlement_limit}, **District Limit**: {district_limit}\n"
            )
            desc += f"Upgrades to: {upgrade}\n" if upgrade else ""
            desc += f"Discounts: {discount}\n, discounted: {discounted} buildings" if discount else ""

            desc += f"\n**Description**: {description}"
            self.embed.add_field(
                name=f"{settlement}: {amount} {full_name}",
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


class ArmyView(ShopView):
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
                 kingdom: str):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.guild_id = guild_id
        self.interaction = interaction
        self.kingdom = kingdom
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
        next_page_button = discord.ui.Button(label='Next Page', style=discord.ButtonStyle.primary, row=1)
        next_page_button.disabled = last_page
        last_page_button = discord.ui.Button(label='Last Page', style=discord.ButtonStyle.primary, row=1)
        last_page_button.disabled = last_page

        first_page_button.callback = self.first_page
        previous_page_button.callback = self.previous_page
        next_page_button.callback = self.next_page
        last_page_button.callback = self.last_page

        self.add_item(first_page_button)
        self.add_item(previous_page_button)
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
            self.message = await self.interaction.original_response()
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
        statement = """
                        SELECT ke.type, kea.ID, Settlement, kea.Hex, kea.Name, ke.effect, ke.special, kea.Duration, check_a, coalesce(Check_A_Status, 0), check_b, coalesce(Check_B_Status, 0), coalesce(success_requirement, 0)
                        FROM KB_Events_Active KEA 
                        left join KB_Events KE on KE.Name = KEA.Name 
                        WHERE Kingdom = ?
                        Order by ke.type desc, kea.name desc
                        Limit ? Offset ?
                    """
        consequence_statement = "SELECT Type, Value, Reroll from KB_Events_Consequence where Name = ? and Severity = ?"
        async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute(statement, (self.kingdom, self.limit, self.offset))
            event_results = await cursor.fetchall()
            self.results = []
            for event in event_results:
                severity = event[9] + event[11]
                print('eventinfo', event[4], severity)

                await cursor.execute(consequence_statement, (event[4], severity))
                consequence_results = await cursor.fetchall()
                print('this is consequence results', consequence_results)
                self.results.append([event, consequence_results])

    async def create_embed(self):
        """Create the embed for the current page. To be implemented in subclasses."""
        consequence_roll_dict = {0: "Set", 1: "Randomized", 2: "Per building sharing this trait",
                                 3: "Percentile Effect", 4: "Randomized with 'exploding' reroll on max",
                                 5: "Singular Effect that explodes on Max"}
        consequence_severity_dict = {0: "No Action required", 1: "pass 1 check",
                                     2: "pass 2 checks"}
        success_state_dict = {0: "Unsuccessful", 1: "Successful"}
        current_page = (self.offset // self.limit) + 1
        total_pages = ((await self.get_max_items() - 1) // self.limit) + 1
        self.embed = discord.Embed(
            title=f"Events for {self.kingdom}",
            description=f"Page {current_page} of {total_pages}")
        for item in self.results:
            (event, unforeseen_consequences) = item
            (event_type, event_id, settlement, hex_id, event_name, event_effect, event_special, duration, check_a, event_status_a, check_b, event_status_b, success_requirement) = event

            duration = f"{duration} turns" if duration > 0 else "Ongoing"
            field_content = f"**Type**: {event_type}, **Duration**: {duration}\r\n"
            field_content += f"**Settlement**: {settlement}" if settlement else ""
            field_content += f", **Hex**: {hex_id}" if hex_id else ""
            field_content += f"\r\n{event_effect}" if event_effect else ""
            field_content += f"\r\n{event_special}" if event_special else ""
            field_content += f"\r\nSuccess Requirement: {consequence_severity_dict[success_requirement]}" if success_requirement else ""
            field_content += f"\r\n**{check_a}**: Status - {success_state_dict[event_status_a]}" if check_a else ""
            field_content += f"\r\n**{check_b}**: Status - {success_state_dict[event_status_b]}" if check_b else ""
            print(unforeseen_consequences)
            if unforeseen_consequences:
                for prepare in unforeseen_consequences:
                    (consequence_type, consequence_value, consequence_reroll) = prepare
                    field_content += f"\r\n**Impacts**: {consequence_type} with a **value** of: {consequence_value}, **Reroll**: {consequence_roll_dict[consequence_reroll]}"
            self.embed.add_field(name=f'**Event**: {event_name} ID: {event_id}', value=field_content, inline=False)

    async def get_max_items(self):
        """Get the total number of items. To be implemented in subclasses."""
        statement = """
                        SELECT COUNT(*) 
                        FROM KB_Events_Active 
                        WHERE Kingdom = ? 
                    """
        async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
            cursor = await db.execute(statement, (self.kingdom,))
            count = await cursor.fetchone()
            return count[0]



class TradeView(RecipientAcknowledgementView):
    def __init__(
            self,
            allowed_user_id: int,
            requester_name: str,
            requester_id: int,
            character_name: str,
            recipient_name: str,
            requesting_kingdom: str,
            sending_kingdom: str,
            food_dict: dict,
            raw_materials_dict: dict,
            simple_crafts_dict: dict,
            luxury_crafts_dict: dict,
            bot: commands.Bot,
            guild_id: int,
            distance: int,
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
        self.distance = distance
        self.requesting_kingdom = requesting_kingdom
        self.sending_kingdom = sending_kingdom
        self.food_dict=food_dict
        self.raw_materials_dict=raw_materials_dict
        self.simple_crafts_dict=simple_crafts_dict
        self.luxury_crafts_dict=luxury_crafts_dict

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
            Magical_Items, luxury, distance)
            VALUES (
            ?, ?, 
            ?, ?, ?, ?, 
            ?, ?, ?, ?, 
            ?, ?, ?, ?, 
            ?, ?, ?)
            """, (
                self.requesting_kingdom, self.sending_kingdom,
                self.food_dict['seafood'], self.food_dict['husbandry'], self.food_dict['grain'], self.food_dict['produce'],
                self.raw_materials_dict['wood'], self.raw_materials_dict['stone'], self.raw_materials_dict['ore'], self.raw_materials_dict['raw_textiles'],
                self.simple_crafts_dict['textiles'], self.simple_crafts_dict['metallurgy'], self.simple_crafts_dict['woodworking'], self.simple_crafts_dict['stoneworking'],
                self.luxury_crafts_dict['magical_items'], self.luxury_crafts_dict['luxury'], self.distance))
            await conn.commit()

    async def rejected(self, interaction: discord.Interaction):
        """Handle the rejection logic."""
        # Update the database to mark the proposition as rejected
        self.embed = discord.Embed(
            title=f"{self.character_name}'s Transaction Rejected",
            description=f"The request \r\n has been rejected by <@{self.allowed_user_id}>'s {self.recipient_name}.",
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
        if sum(self.food_dict.values()) > 0:
            self.embed.add_field(name="Food",
                                 value=f"Seafood: {self.food_dict['seafood']}\nProduce: {self.food_dict['produce']}\nGrain: {self.food_dict['grain']}\nHusbandry: {self.food_dict['husbandry']}")
        if sum(self.raw_materials_dict.values()) > 0:
            self.embed.add_field(name="Raw Materials",
                                 value=f"Ore: {self.raw_materials_dict['ore']}\nStone: {self.raw_materials_dict['stone']}\nLumber: {self.raw_materials_dict['wood']}\nRaw Textiles: {self.raw_materials_dict['raw_textiles']}")
        if sum(self.simple_crafts_dict.values()) > 0:
            self.embed.add_field(name="Crafts",
                                 value=f"Textiles: {self.simple_crafts_dict['textiles']}\nMetallurgy: {self.simple_crafts_dict['metallurgy']}\nWoodworking: {self.simple_crafts_dict['woodworking']}\nStoneworking: {self.simple_crafts_dict['stoneworking']}")
        if sum(self.luxury_crafts_dict.values()) > 0:
            self.embed.add_field(name="Specialty",
                                 value=f"Magical Items: {self.luxury_crafts_dict['magical_items']}\nLuxury: {self.luxury_crafts_dict['luxury']}")
        self.embed.set_author(name=self.requester_name)
        self.embed.set_footer(text="Please accept or reject this transaction before it expires.")


class KingdomView(NewDualView):
    def __init__(
            self,
            user_id: int,
            guild_id: int,
            offset: int,
            limit: int,
            player_name: str,
            kingdom: str,
            view_type: int,
            turn_id: int,
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
        self.turn_id = turn_id

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
        if not self.max_items:
            await self.get_max_items()
        async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
            cursor = await db.cursor()
            if self.view_type == 1:
                for kingdom in self.results:
                    await cursor.execute("""
                    Select count(*), Coalesce(sum(case when type = 'Beneficial' then 1 else 0 end), 0) as beneficial, Coalesce(sum(case when type = 'Beneficial' then 0 else 1 end), 0) as problematic
                    FROM KB_Events_Active KEA 
                    LEFT JOIN KB_Events KE on ke.name = kea.name
                    where kingdom = ?
                    """, (kingdom[0],))
                    event_totals = await cursor.fetchone()
                     
                    self.kingdom = kingdom[0]
                    kingdom_info = await fetch_kingdom(guild_id=self.guild_id, kingdom=self.kingdom, turn_id=self.turn_id)
                    outgoing_trade = await fetch_kingdom_trade(db=db, source_kingdom=self.kingdom)
                    (food_dataclass, raw_materials_dataclass, simple_crafts_dataclass, luxury_crafts_dataclass,
                     available_food, penalty_dict, event) = await fetch_resources(db=db, kingdom=kingdom_info,
                                                                                  farm_penalty=0,
                                                                                  consumption=kingdom_info.consumption.total)

                    kingdom_embed = discord.Embed(title=f"Kingdom Information for {self.kingdom}", description=f"**Turn**: {self.turn_id} **Fame**: {kingdom_info.fame.total} \r\nActive Events: {event_totals[0]}, Good Events {event_totals[1]}, Bad Events {event_totals[2]}")
                    kingdom_embed.add_field(name="Base Stats", value=f"**Size**: {kingdom_info.size.total}, **Control DC**: {kingdom_info.control_dc.total}, **Unrest :anger:**: {kingdom_info.unrest.total} **Consumption**: {kingdom_info.consumption.total}", inline=False)
                    kingdom_embed.add_field(name="Control Stats", value=f"**Economy** :coin:: {kingdom_info.economy.total} **Loyalty** :heart: : {kingdom_info.loyalty.total} **Stability** :scales:: {kingdom_info.stability.total} **Taxation** :purse:: {kingdom_info.taxation.total}", inline=False)

                    building_embed = discord.Embed(title=f"Building Modifiers for {self.kingdom}")
                    building_embed.add_field(name="Base Stat", value=f"Unrest :anger:: {kingdom_info.unrest.building_value}")
                    building_embed.add_field(name="Control Stats", value=f"**Economy** :coin:: {kingdom_info.economy.building_value} **Loyalty** :heart: : {kingdom_info.loyalty.building_value} **Stability** :scales:: {kingdom_info.stability.building_value} **Taxation** :purse:: {kingdom_info.taxation.building_value}", inline=False)

                    hex_embed = discord.Embed(title=f"Hex Modifiers for {self.kingdom}")
                    hex_embed.add_field(name="Base Stat", value=f"Unrest :anger:: {kingdom_info.unrest.hex_value}, **Consumption**: {kingdom_info.consumption.total}")
                    hex_embed.add_field(name="Control Stats", value=f"**Economy** :coin:: {kingdom_info.economy.hex_value} **Loyalty** :heart: : {kingdom_info.loyalty.hex_value} **Stability** :scales:: {kingdom_info.stability.hex_value} **Taxation** :purse:: {kingdom_info.taxation.hex_value}", inline=False)


                    food_value = f""":leafy_green: Produce - Produced: {food_dataclass.produce.base} Incoming: {food_dataclass.produce.trade}, Leftover: {food_dataclass.produce.remaining}, Outgoing: {outgoing_trade.produce}
                        :bread: Grain Produced: {food_dataclass.grain.base}, Incoming: {food_dataclass.grain.trade}, Leftover: {food_dataclass.grain.remaining}, Outgoing: {outgoing_trade.grain}
                        :fish: Seafood - Produced: {food_dataclass.seafood.base}, Incoming: {food_dataclass.seafood.trade}, Leftover: {food_dataclass.seafood.remaining}, Outgoing: {outgoing_trade.seafood}
                        :cow: Husbandry - Produced: {food_dataclass.husbandry.base}, Incoming: {food_dataclass.husbandry.trade}, Leftover: {food_dataclass.husbandry.remaining}, Outgoing: {outgoing_trade.husbandry}
                    """
                    if event:
                        food_value += f":warning: **Your kingdom is {event}!**\n" if event == 'Starving' else f":meat_on_bone: **Your kingdom is {event}!**\n"


                    raw_materials_value = f""":rock: Stone Produced: {raw_materials_dataclass.stone.base}, Incoming: {raw_materials_dataclass.stone.trade}, Leftover: {raw_materials_dataclass.stone.remaining}, Outgoing: {outgoing_trade.stone}
                    :pick: Ore Produced: {raw_materials_dataclass.ore.base}, Incoming: {raw_materials_dataclass.ore.trade}, Leftover: {raw_materials_dataclass.ore.remaining}, Outgoing: {outgoing_trade.ore}
                    :wood: Wood Produced: {raw_materials_dataclass.wood.base}, Incoming: {raw_materials_dataclass.wood.trade}, Leftover: {raw_materials_dataclass.wood.remaining}, Outgoing: {outgoing_trade.wood}
                    :herb: Raw Textiles Produced: {raw_materials_dataclass.raw_textiles.base}, Incoming: {raw_materials_dataclass.raw_textiles.trade}, Leftover: {raw_materials_dataclass.raw_textiles.remaining}, Outgoing: {outgoing_trade.raw_textiles}
                    """
                    if penalty_dict['overdraft'] > 0 or raw_materials_dataclass.stone.depletion > 0 or raw_materials_dataclass.ore.depletion > 0 or raw_materials_dataclass.wood.depletion or raw_materials_dataclass.raw_textiles.depletion:
                        raw_materials_value += f"\r\n:warning: Raw Materials are overtaxed: :rock: Stone: {raw_materials_dataclass.stone.depletion}, :pick: Ore: {raw_materials_dataclass.ore.depletion}, :wood: Wood: {raw_materials_dataclass.wood.depletion}, :herb: Raw Textiles: {raw_materials_dataclass.raw_textiles.depletion}, General: {penalty_dict['overdraft']}"

                    goods_value = f""":moyai: Stoneworking Produced: {simple_crafts_dataclass.stoneworking.base}, Incoming: {simple_crafts_dataclass.stoneworking.trade}, Leftover: {simple_crafts_dataclass.stoneworking.remaining}, Outgoing: {outgoing_trade.stoneworking}
                    :crossed_swords: Metallurgy Produced: {simple_crafts_dataclass.metallurgy.base}, Incoming: {simple_crafts_dataclass.metallurgy.trade}, Leftover: {simple_crafts_dataclass.metallurgy.remaining}, Outgoing: {outgoing_trade.metallurgy}
                    :chair: Woodworking Produced: {simple_crafts_dataclass.woodworking.base}, Incoming: {simple_crafts_dataclass.woodworking.trade}, Leftover: {simple_crafts_dataclass.woodworking.remaining}, Outgoing: {outgoing_trade.woodworking}
                    :shirt: Textiles Produced: {simple_crafts_dataclass.textiles.base}, Incoming: {simple_crafts_dataclass.textiles.trade}, Leftover: {simple_crafts_dataclass.textiles.remaining}, Outgoing: {outgoing_trade.textiles}
                    """
                    if simple_crafts_dataclass.stoneworking.depletion > 0 or simple_crafts_dataclass.woodworking.depletion > 0 or simple_crafts_dataclass.metallurgy.depletion > 0 or simple_crafts_dataclass.textiles.depletion > 0:
                        goods_value += (f"\r\n:warning: Crafted Goods are overdrafted: :moyai: Stoneworking: {simple_crafts_dataclass.stoneworking.depletion}, :crossed_swords: Metallurgy: {simple_crafts_dataclass.metallurgy.depletion} "
                                        f":chair: Woodworking: {simple_crafts_dataclass.woodworking.depletion}, :shirt: Textiles: {simple_crafts_dataclass.textiles.depletion} ")

                    complex_goods_value = f""":harp: Luxury Items Produced: {luxury_crafts_dataclass.luxury.base}, Incoming: {luxury_crafts_dataclass.luxury.trade}, Leftover: {luxury_crafts_dataclass.luxury.remaining}, Outgoing: {outgoing_trade.luxury}
                    :sparkles: Magical Items Produced: {luxury_crafts_dataclass.magical_items.base}, Incoming: {luxury_crafts_dataclass.magical_items.trade}, Leftover: {luxury_crafts_dataclass.magical_items.remaining}, Outgoing: {outgoing_trade.magical_items}
                    """
                    if penalty_dict['loyalty']:
                        complex_goods_value += f'\r\n:warning: Overdraft - :harp: Luxury Items: {luxury_crafts_dataclass.luxury.depletion}, :sparkles: Magical Items: {luxury_crafts_dataclass.magical_items.depletion}' if luxury_crafts_dataclass.magical_items.depletion > 0 or luxury_crafts_dataclass.luxury.depletion > 0 else f"\r\nGeneral Depletion: {penalty_dict['loyalty']}"

                    resource_embed = discord.Embed(title=f"Resource breakdown for {self.kingdom}")
                    resource_embed.add_field(name="**Food**",value=food_value, inline=False)
                    resource_embed.add_field(name="Raw Materials", value=raw_materials_value, inline=False)
                    resource_embed.add_field(name="Simple Goods", value=goods_value, inline=False)
                    resource_embed.add_field(name="Complex Goods", value=complex_goods_value, inline=False)
                    
                    self.embeds = [kingdom_embed, building_embed, hex_embed, resource_embed]
            else:
                embed = discord.Embed(
                    title=f"Kingdom Information",
                    description=f"Page {self.offset // self.limit + 1} of {self.max_items // self.limit + 1}"
                )
                for kingdom in self.results:
                    self.kingdom = kingdom[0]
                    kingdom_info = await fetch_kingdom(guild_id=self.guild_id, kingdom=self.kingdom, turn_id=self.turn_id)


                    kingdom_info_content = f"""
                                    **Size**: {kingdom_info.size.total}, **Control DC**: {kingdom_info.control_dc.total}, **Unrest**: {kingdom_info.unrest.total} \r\n
                                    **Economy**: {kingdom_info.economy.total} **Loyalty**: {kingdom_info.loyalty.total} **Stability**: {kingdom_info.stability.total}\r\n
                                    **Fame**: {kingdom_info.fame.total} **Consumption**: {kingdom_info.consumption.total}, **Taxation**: {kingdom_info.taxation.total}\r\n
                                    """
                    embed.add_field(name=f"Kingdom of {self.kingdom}", value=kingdom_info_content, inline=False)
                self.embeds = [embed]

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


class SettlementView(NewDualView):
    def __init__(
            self,
            user_id: int,
            guild_id: int,
            offset: int,
            limit: int,
            player_name: str,
            kingdom: str,
            view_type: int,
            turn_id: int,
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
        self.turn_id = turn_id

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
            if not self.max_items:
                self.max_items = await self.get_max_items()
            self.embeds = []
            for settlement in self.results:
                settlement = settlement[0]
                settlement_info = await fetch_settlement(guild_id=self.guild_id, settlement=settlement, turn_id=self.turn_id)
                population = settlement_info.size.total * 75
                description = f"Approximate Population: {population}, Size: {settlement_info.size.total}, Districts: {max(settlement_info.size.total // 36, 1)}"
                settlement_embed = discord.Embed(title=f"{settlement_info.kingdom} - {settlement_info.settlement}", description=description)
                settlement_embed.add_field(name= "Settlement Stats:", value= f"""
                :see_no_evil: **Corruption**: {settlement_info.corruption.total}, :supervillain: **Crime**: {settlement_info.crime.total}, :hammer_pick: **Productivity**: {settlement_info.productivity.total} 
                :scales: **Law**: {settlement_info.law.total}, :book: **Lore**: {settlement_info.lore.total} :people_hugging: **Society**: {settlement_info.society.total} 
                :rotating_light: **Danger**: {settlement_info.danger.total}, :shield: **Defence**: {settlement_info.defence.total} 
                :bank: **Market**: {settlement_info.base_value.total} :sparkles: **Spellcasting**: {settlement_info.spellcasting.total}, :homes: **Available Supply**: {settlement_info.supply.total}\r\n\r\n
                """, inline=False)
                settlement_embed.add_field(name="Building Stats:", value=f"""
                    :see_no_evil: **Corruption**: {settlement_info.corruption.building_value}, :supervillain: **Crime**: {settlement_info.crime.building_value}, :hammer_pick: **Productivity**: {settlement_info.productivity.building_value} 
                    :scales: **Law**: {settlement_info.law.building_value}, :book: **Lore**: {settlement_info.lore.building_value} :people_hugging: **Society**: {settlement_info.society.building_value} 
                    :rotating_light: **Danger**: {settlement_info.danger.building_value}, :shield: **Defence**: {settlement_info.defence.building_value} 
                    :bank: **Market**: {settlement_info.base_value.building_value} :sparkles: **Spellcasting**: {settlement_info.spellcasting.building_value}, :homes: **Available Supply**: {settlement_info.supply.building_value}\r\n
                    """, inline=False)
                self.embeds.append(settlement_embed)

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


class EventDisplayView(DualView):
    def __init__(self, user_id: int, guild_id: int, offset: int, limit: int, view_type: int,
                 interaction: discord.Interaction):
        super().__init__(user_id=user_id, guild_id=guild_id, offset=offset, limit=limit, view_type=view_type,
                         interaction=interaction, content="")
        self.max_items = None  # Cache total number of items
        self.view_type = view_type  # 0: All, 1: Problematic, 2: Beneficial

    async def update_results(self):
        """Update the results based on the current offset."""
        if self.view_type == 0:
            statement = """
            SELECT Scale, Likelihood, Region, Type, Name, Effect, Special, 
            Check_A, Check_B, Hex, Success_Requirements, 
            Duration, Bonus, Penalty, Hex 
            from KB_Events ORDER BY Name LIMIT ? OFFSET ?
            """
        elif self.view_type == 1:
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
        current_page = (self.offset // self.limit) + 1
        total_pages = ((await self.get_max_items() - 1) // self.limit) + 1
        
        type_title = "Events"
        if self.view_type == 1:
            type_title = "Problematic Events"
        elif self.view_type == 2:
            type_title = "Beneficial Events"

        self.embed = discord.Embed(title=f"{type_title} Summary",
                                   description=f"Page {current_page} of {total_pages}")
        
        for result in self.results:
            (scale, likelihood, region, type, name, effect, special,
             check_a, check_b, hex, success_requirements,
             duration, bonus, penalty, hex) = result
            duration = f"{duration} turns" if duration > 0 else "Ongoing"
            check_dict = {1: "Loyalty", 2: "Stability", 3: "Economy", 4: "Demand Building", 5: "Demand Improvement"}
            check_a_str = check_dict.get(check_a, str(check_a)) if check_a else "None"
            check_b_str = check_dict.get(check_b, str(check_b)) if check_b else "None"
            
            type_str = type
            
            hex_dict = {0: "Does not affect hexes", 1: "Affects a hex"}
            hex_str = hex_dict.get(hex, str(hex))
            
            requirements_dict = {0: "No requirements", 1: "Succeed at one check", 2: "Succeed at both checks"}
            req_str = requirements_dict.get(success_requirements, str(success_requirements))

            field_content = f"""**Likelihood**: {likelihood} **Type**: {type_str} 
            \r\n**Scale**: {scale}, **Region**: {region}, **Hex**: {hex_str}, **Duration**: {duration}
            \r\n**Effect**: {effect}
            \r\n**Special**: {special}, 
            \r\n**Check A**: {check_a_str}, **Check B**: {check_b_str}, **Success Requirements**: {req_str}
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
                
                consequence_severity_dict = {0: "No Action or failed rolls"}
                if type == "Problematic": 
                     consequence_severity_dict.update({1: "Passed 1 Check", 2: "passed 2 checks"})
                
                for consequence in unforeseen_consequences:
                    (id, c_name, severity, c_type, value, reroll) = consequence
                    severity_str = consequence_severity_dict.get(severity, str(severity))
                    reroll_str = consequence_rolltype_dict.get(reroll, str(reroll))
                    field_content += f"\r\n**ID**: {id} **Consequence**: {c_name}, **Severity**: {severity_str}, **Effects**: {c_type}, **Value**: {value}, **Reroll**: {reroll_str}"
                
                if field_content:
                    self.embed.add_field(name=f'**{name} consequences**', value=field_content, inline=False)

    async def get_max_items(self):
        """Get the total number of titles."""
        if self.max_items is None:
            async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
                if self.view_type == 0:
                    cursor = await db.execute("SELECT COUNT(*) from KB_Events")
                elif self.view_type == 1:
                    cursor = await db.execute("SELECT COUNT(*) from KB_Events where Type = 'Problematic'")
                else:
                    cursor = await db.execute("SELECT COUNT(*) from KB_Events where Type = 'Beneficial'")
                count = await cursor.fetchone()
                self.max_items = count[0]
        return self.max_items

    async def on_view_change(self):
        # Cycle through view types: 0 -> 1 -> 2 -> 0
        if self.view_type == 0:
            self.view_type = 1
        elif self.view_type == 1:
            self.view_type = 2
        else:
            self.view_type = 0
