import logging
import math
import random
import typing
from decimal import Decimal
from itertools import chain

import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands

from commands import character_commands
from core.autocomplete import (
    alignment_autocomplete, blueprint_autocomplete, improvement_subtype_autocomplete,
    blueprint_repurpose_autocomplete, blueprint_upgrade_autocomplete,
    government_autocompletion, hex_improvement_autocomplete,
    leadership_autocomplete, kingdom_autocomplete, settlement_autocomplete,
    region_autocomplete, own_character_select_autocompletion,
    character_select_autocompletion
)
from core.character import UpdateCharacterData, CharacterChange, update_character
from core.display import log_embed, character_embed
from core.kingdom import (
    validate_password, encrypt_password, KingdomInfo, goods_remaining_dict,
)
from core.kingdom_actions import (
    create_a_kingdom, edit_a_kingdom, delete_a_kingdom, adjust_bp,
    remove_leader, claim_hex, relinquish_hex,
    add_an_improvement, degrade_improvement, repurpose_an_improvement,
    add_building, remove_building, claim_a_settlement, relinquish_settlement
)
from core.kingdom_fetching import (
    fetch_kingdom, fetch_building, fetch_hex_improvement, fetch_resources
)
from core.kingdom_logging import kingdom_embed, settlement_embed
from core.kingdom_views import (
    LeadershipView, HexView, ImprovementView, BlueprintView,
    SettlementBuildingsView, ArmyView, KingdomEventView, TradeView,
    KingdomView, SettlementView
)
from core.utils import safe_min, safe_sub


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
    @app_commands.autocomplete(region=region_autocomplete)
    async def create(
            self,
            interaction: discord.Interaction,
            kingdom: str,
            password: str,
            region: str,
            government: str,
            alignment: str,
            heraldry: typing.Optional[str],
            channel: discord.TextChannel
    ):
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
                password=password,
                image_link=heraldry
            )
            await interaction.followup.send(content=kingdom_create)
            await kingdom_embed(
                kingdom=kingdom,
                guild=interaction.guild,
                channel=channel
            )
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
            new_alignment: typing.Optional[str],
            new_heraldry: typing.Optional[str]
    ):
        """This is a player command to modify a kingdom THEY OWN."""
        await interaction.response.defer(thinking=True)
        try:
            if new_heraldry is not None:
                new_heraldry = str.replace(str.replace(new_heraldry, ";", ""), ")", "")
                image_link_valid = str.lower(new_heraldry[0:5])
                if len(new_heraldry) > 300:
                    await interaction.followup.send(
                        f"When it blocked out the sun, did you consider if it was possible that your image link is a little too long?")
                    return
                if image_link_valid != 'https':
                    await interaction.followup.send(f"Image link is missing HTTPS:")
                    return
            kingdom_info = await fetch_kingdom(interaction.guild_id, old_kingdom, turn_id=0)
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
                alignment=new_alignment,
                image_link = new_heraldry
            )
            await interaction.followup.send(content=status)
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"Error fetching kingdom: {e}")
            await interaction.followup.send(content="An error occurred while fetching kingdom.")
            return

    @kingdom_group.command(name="build_points", description="Adjust the build points of a kingdom")
    @app_commands.autocomplete(kingdom=kingdom_autocomplete)
    @app_commands.autocomplete(character_name=own_character_select_autocompletion)
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

                    update_character_info = UpdateCharacterData(
                        character_name=character_name,
                        gold_package=(gold_reward[0], gold_reward[1], gold_reward[2])
                    )

                    update_character_log = CharacterChange(
                        author=interaction.user.name,
                        character_name=character_name,
                        transaction_id=gold_reward[4],
                        gold_change=gold_reward[0],
                        gold=gold_reward[1],
                        gold_value=gold_reward[2],
                        gold_value_max=gold_reward[3],
                        source=f"Adjust BP Command selling {bought_points} build points",
                    )
                    await update_character(interaction.guild_id, update_character_info)
                    await log_embed(
                        bot=self.bot,
                        thread=character_info[5],
                        guild=interaction.guild,
                        change=update_character_log)
                    await character_embed(guild=interaction.guild, character_name=character_name)
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
                    update_character_info = UpdateCharacterData(
                        character_name=character_name,
                        gold_package=(gold_used[0], gold_used[1], gold_used[2])
                    )
                    update_character_log = CharacterChange(
                        author=interaction.user.name,
                        character_name=character_name,
                        transaction_id=gold_used[4],
                        gold_change=gold_used[0],
                        gold=gold_used[1],
                        gold_value=gold_used[2],
                        gold_value_max=gold_used[3],
                        source=f"Adjust BP Command buying {bought_points} build points",
                    )
                    await update_character(interaction.guild_id, update_character_info)
                    await log_embed(
                        bot=self.bot,
                        thread=character_info[5],
                        guild=interaction.guild,
                        change=update_character_log)
                    await character_embed(
                        guild=interaction.guild,
                        character_name=character_name)
                    await interaction.followup.send(adjusted_bp_result)
        except (aiosqlite, TypeError, ValueError, character_commands.CalculationAidFunctionError) as e:
            logging.exception(f"Error increasing build points: {e}")
            await interaction.followup.send(content="An error occurred while increasing build points.")

    @edict_group.command(name="set", description="set the severity of your edicts")
    @app_commands.choices(
        holiday=[discord.app_commands.Choice(name='None', value=0),
                discord.app_commands.Choice(name='Minimal', value=1),
                discord.app_commands.Choice(name='Standard', value=2),
                discord.app_commands.Choice(name='Extravagant', value=3),
                discord.app_commands.Choice(name='Lascivious', value=4)
                 ]
    )
    @app_commands.choices(
        promotion=[discord.app_commands.Choice(name='None', value=0),
                 discord.app_commands.Choice(name='Token', value=1),
                 discord.app_commands.Choice(name='Standard', value=2),
                 discord.app_commands.Choice(name='Aggressive', value=3),
                discord.app_commands.Choice(name='Expansionist', value=4)
                 ]
    )
    @app_commands.choices(
        taxation=[discord.app_commands.Choice(name='None', value=0),
                 discord.app_commands.Choice(name='Light', value=1),
                 discord.app_commands.Choice(name='Normal', value=2),
                 discord.app_commands.Choice(name='Heavy', value=3),
                discord.app_commands.Choice(name='Douchebag', value=4)
                 ]
    )
    @app_commands.autocomplete(kingdom=kingdom_autocomplete)
    async def set_edicts(self, interaction: discord.Interaction, kingdom: str, password: str,
                         holiday: typing.Optional[discord.app_commands.Choice[int]],
                         promotion: typing.Optional[discord.app_commands.Choice[int]],
                         taxation: typing.Optional[discord.app_commands.Choice[int]]):
        """This command is used to set the severity of your edicts"""
        await interaction.response.defer(thinking=True)
        try:
            holiday = holiday.value if isinstance(holiday, discord.app_commands.Choice) else holiday
            promotion = promotion.value if isinstance(promotion, discord.app_commands.Choice) else promotion
            taxation = taxation.value if isinstance(taxation, discord.app_commands.Choice) else taxation
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute("SELECT Password, Holiday, Promotion, Taxation FROM kb_Kingdoms WHERE Kingdom = ?", (kingdom,))
                kingdom_results = await cursor.fetchone()
                if not kingdom_results:
                    await interaction.followup.send(content=f"The kingdom of {kingdom} does not exist.")
                    return
                (kingdom_password, old_holiday, old_promotion, old_taxation) = kingdom_results
                valid_password = validate_password(password, kingdom_password)
                if not valid_password:
                    await interaction.followup.send(content="The password provided is incorrect.")
                    return
                embed = discord.Embed(title=f"{kingdom}'s current Edicts:")


                await cursor.execute("Select Holidays, Holidays_Loyalty, Holidays_Consumption from KB_Edicts where Severity = ?", (old_holiday,))
                old_holidays_results = await cursor.fetchone()
                if not old_holidays_results:
                    await interaction.response.send("How the fuck is the old value invalid for Holidays?")
                    return
                (old_holidays_name, old_holidays_loyalty, old_holidays_consumption) = old_holidays_results


                await cursor.execute("Select promotion, Promotion_stability, Promotion_Consumption from kb_edicts where Severity = ?",(old_promotion,))
                old_promotion_results = await cursor.fetchone()
                if not old_promotion_results:
                    await interaction.response.send("How the fuck is the old value invalid for Promotion?")
                    return
                (old_promotion_name, old_promotion_stability, old_promotion_consumption) = old_promotion_results


                await cursor.execute("SELECT Taxation, Taxation_economy, Taxation_Loyalty from kb_edicts where severity = ?", (old_taxation,))
                old_taxation_results = await cursor.fetchone()
                if not old_taxation_results:
                    await interaction.response.send("How the fuck is the old value invalid for Taxation?")
                    return
                (old_taxation_name, old_taxation_economy, old_taxation_loyalty) = old_taxation_results

                if holiday:
                    await cursor.execute("Select Holidays, Holidays_Loyalty, Holidays_Consumption from KB_Edicts where Severity = ?", (holiday,))
                    holidays_results = await cursor.fetchone()
                    if not holidays_results:
                        embed.add_field(name="Holidays",
                                        value="The New Holiday value was Invalid, please choose between 0-4.")
                        holiday = old_holiday
                    else:
                        (holidays_name, holidays_loyalty, holidays_consumption) = holidays_results
                        embed.add_field(name=f"New Taxation Edict: {holidays_name}",
                                        value=f"New Holidays Loyalty: {holidays_loyalty}, Holidays Consumption: {holidays_consumption}\r\n"
                                              f"Old Holidays Loyalty: {old_holidays_loyalty}, Old Holidays Consumption: {old_holidays_consumption}",
                                        inline=False)
                else:
                    holiday = old_holiday
                    embed.add_field(name=f"Holidays Edict: {old_holidays_name}",
                                    value=f"Holidays Loyalty: {old_holidays_loyalty}, Holidays Consumption: {old_holidays_consumption}",
                                    inline=False)

                if promotion:
                    await cursor.execute("Select Promotion, Promotion_stability, Promotion_Consumption from kb_edicts where Severity = ?",(promotion,))
                    promotion_results = await cursor.fetchone()
                    if not promotion_results:
                        embed.add_field(name="Promotion",
                                        value="The Promotion value was Invalid, please choose between 0-4.")
                        promotion = old_promotion
                    else:
                        (promotion_name, promotion_stability, promotion_consumption) = promotion_results
                        embed.add_field(name=f"New Taxation Edict: {promotion_name}",
                                        value=f"New Promotion Stability: {promotion_stability}, New Promotion Consumption: {promotion_consumption}\r\n"
                                              f"Old Promotion Stability: {old_promotion_stability}, Old Promotion Consumption: {old_promotion_consumption}",
                                        inline=False)
                else:
                    promotion = old_promotion
                    embed.add_field(name=f"Promotion Edict: {old_promotion_name}",
                                    value=f"Promotion Stability: {old_promotion_stability}, Promotion Consumption: {old_promotion_consumption}",
                                    inline=False)

                if taxation:
                    await cursor.execute("SELECT Taxation, Taxation_economy, Taxation_Loyalty from kb_edicts where severity = ?", (taxation,))
                    taxation_results = await cursor.fetchone()
                    if not taxation_results:
                        embed.add_field(name="Taxation", value="The Taxation value was Invalid, please choose between 0-4. You're the king? Who voted for you. I swear to god, if you tried to increase the taxation too high, I'll make the citizens American your british ass.")
                        taxation = old_taxation
                    else:
                        (taxation_name, taxation_economy, taxation_loyalty) = taxation_results
                        embed.add_field(name=f"New Taxation Edict: {taxation_name}",
                                        value=f"New Taxation Economy: {taxation_economy}, New Taxation Loyalty: {taxation_loyalty}\r\n"
                                              f"Old Taxation Economy: {old_taxation_economy}, old Taxation Loyalty: {old_taxation_loyalty}", inline=False)
                else:
                    taxation = old_taxation
                    embed.add_field(name=f"Taxation Edict: {old_taxation_name}", value=f"Taxation Economy: {old_taxation_economy} Taxation Loyalty: {old_taxation_loyalty}", inline=False)

                await cursor.execute("Update kb_kingdoms set Holiday = ?, Promotion = ?, Taxation = ? where kingdom = ?",
                                     (holiday, promotion, taxation, kingdom))
                await db.commit()
                await interaction.followup.send(embed=embed)

        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"Error setting edict severity: {e}")
            await interaction.followup.send(content="An error occurred while setting edict severity.")

    @edict_group.command(name="display", description="Display the edict severity of a kingdom")
    async def display_edicts(self, interaction: discord.Interaction, kingdom: typing.Optional[str]):
        await interaction.response.defer(thinking=True)
        try:
            embed = discord.Embed(title="Edict Information", color=0x00ff00, description="information about edicts")
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                if not kingdom:
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
                else:
                    await cursor.execute("select kingdom, holiday, promotion, taxation from kb_kingdoms where kingdom = ?", (kingdom,))
                    kingdom_info = await cursor.fetchone()
                    if not kingdom_info:
                        await interaction.followup.send(f"Kingdom of {kingdom} could not be found.")
                    else:
                        await cursor.execute("SELECT COUNT(*) from kb_hexes where kingdom = ?", (kingdom_info[0],))
                        hex_count = await cursor.fetchone()
                        embed = discord.Embed(title=f"{kingdom}'s edict Information", color=0x00ff00, description="information about edicts")
                        await cursor.execute("Select Holidays, Holidays_Loyalty, Holidays_Consumption from kb_edicts where severity = ?", (kingdom_info[1],) )
                        holiday_info = await cursor.fetchone()
                        if holiday_info:
                            embed.add_field(name=f"Holiday Edict: {holiday_info[0]}", value=f"Loyalty Effect: {holiday_info[1]}, Consumption Effect: {holiday_info[2]}", inline=False)
                        await cursor.execute("Select Promotion, Promotion_stability, Promotion_Consumption from kb_edicts where severity = ?", (kingdom_info[1],))
                        promotion_info = await cursor.fetchone()
                        if promotion_info:
                            embed.add_field(name=f"Promotion Edict: {promotion_info[0]}", value=f"Stability: {promotion_info[1]}, Consumption: {promotion_info[2]}", inline=False)
                        await cursor.execute("SELECT Taxation, Taxation_Economy, Taxation_Loyalty from kb_edicts where severity = ?", (kingdom_info[1],))
                        taxation_info = await cursor.fetchone()
                        if taxation_info:
                            embed.add_field(name=f"Taxation Edict: {taxation_info[0]}", value=f"Economy: {taxation_info[1]}, Loyalty: {taxation_info[2]}", inline=False)

                        await cursor.execute("Select Settlements, Buildings, Improvements, Hexes from KB_Improvements where kingdom = ? and Size < ?  order by size desc limit 1", (kingdom_info[1],hex_count))
                        improvement_edict_info = await cursor.fetchone()
                        if improvement_edict_info:
                            (settlements_per_turn, buildings_per_turn, improvements_per_turn, hexes_per_turn) = improvement_edict_info
                            embed.add_field(name="Improvement Edicts", value=f"Settlements: {settlements_per_turn}, Buildings: {buildings_per_turn}, Improvements:{improvements_per_turn}, Hexes: {hexes_per_turn}", inline=False)
                        await interaction.followup.send(embed=embed)
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"Error displaying edict severity: {e}")
            await interaction.followup.send(content="An error occurred while displaying edict severity.")


    @leadership_group.command(name="modify",
                              description="Modify a leader, by changing their ability score or who is in charge")
    @app_commands.autocomplete(kingdom=kingdom_autocomplete)
    @app_commands.autocomplete(title=leadership_autocomplete)
    @app_commands.autocomplete(character_name=character_select_autocompletion)
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
                kingdom = await fetch_kingdom(guild_id=interaction.guild_id, kingdom=kingdom, turn_id=0)
                if not kingdom:
                    await interaction.followup.send(content=f"The kingdom of {kingdom} does not exist.")
                    return
                valid_password = validate_password(password, kingdom.password)
                if not valid_password:
                    await interaction.followup.send(content="The password provided is incorrect.")
                    return

                status = await add_an_improvement(
                    guild_id=interaction.guild_id,
                    hex_id=hex_id,
                    kingdom=kingdom.kingdom,
                    improvement=improvement,
                    amount=amount,
                    build_points=kingdom.build_points,
                    kingdom_size=kingdom.size.total
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
                               hex_id: int, image_link: str, channel: discord.TextChannel):
        """This command is used to claim a settlement for a kingdom"""
        await interaction.response.defer(thinking=True)
        try:
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
                                                  hex_id, image_link)
                await interaction.followup.send(content=status)
                await settlement_embed(
                    settlement=settlement,
                    guild=interaction.guild,
                    channel=channel
                )
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"Error claiming settlement: {e}")
            await interaction.followup.send(content="An error occurred while claiming a settlement.")

    @settlement_group.command(name="edit", description="Edit a settlement for a kingdom")
    @app_commands.autocomplete(kingdom=kingdom_autocomplete)
    async def edit_settlement(self, interaction: discord.Interaction, kingdom: str, password: str, old_name: str,
                              new_name: str, image_link: typing.Optional[str]):
        """This command is used to Edit a settlement for a kingdom"""
        await interaction.response.defer(thinking=True)
        try:
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
                await cursor.execute("UPDATE kb_settlements SET Settlement = ?, image_link = coalesce(?, image_link) WHERE Settlement = ?",
                                     (new_name, image_link, old_name))
                await cursor.execute("UPDATE KB_Buildings SET Settlement = ? WHERE Settlement = ?",
                                     (new_name, old_name))
                await cursor.execute("UPDATE KB_Buildings_Custom SET Settlement = ? WHERE Settlement = ?",
                                     (new_name, old_name))
                await cursor.execute("UPDATE Rumors SET Settlement = ? WHERE Settlement = ?",
                                     (new_name, old_name))
                await cursor.execute("UPDATE KB_events_active SET Settlement = ? WHERE Settlement = ?",
                                     (new_name, old_name))
                await cursor.execute("UPDATE KB_Turn_Penalty_Settlement SET Settlement = ? WHERE Settlement = ?",
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
                SUM(CASE WHEN KBB.Subtype = 'Housing' THEN KB.Amount * COALESCE(KBB.Quality, 0) ELSE 0 END) AS Housing_Total,
                SUM(CASE WHEN KBB.Subtype != 'Housing' THEN KB.Amount * COALESCE(KBB.Supply, 0) ELSE 0 END) AS Non_Housing_Total
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
                                            settlement=settlement, building_info=building_info, amount=amount)
                await interaction.followup.send(content=status)
                await kingdom_embed(
                    kingdom=kingdom,
                    guild=interaction.guild
                )
                await settlement_embed(
                    settlement=settlement,
                    guild=interaction.guild
                )
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

    @kingdom_group.command(name="event", description="display active events for a kingdom")
    @app_commands.autocomplete(kingdom=kingdom_autocomplete)
    async def kingdom_event(self, interaction: discord.Interaction, kingdom: str):
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
                view = KingdomEventView(user_id=interaction.user.id, guild_id=interaction.guild_id,
                                        kingdom=kingdom, interaction=interaction)
                await view.update_results()
                await view.create_embed()
                await view.send_initial_message()
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"Error displaying kingdom events: {e}")
            await interaction.followup.send(content="An error occurred while displaying kingdom events.")

    @kingdom_group.command(name="check", description="roll a blind kingdom check")
    @app_commands.autocomplete(kingdom=kingdom_autocomplete)
    @app_commands.choices(
        check=[discord.app_commands.Choice(name='Loyalty', value='Loyalty'),
                discord.app_commands.Choice(name='Stability', value='Stability'),
               discord.app_commands.Choice(name='Economy', value='Economy')])
    async def kingdom_check(self, interaction: discord.Interaction, kingdom: str, check: str, turn_id: typing.Optional[int]):
        """this handles events or does a blind kingdom check"""
        await interaction.response.defer(thinking=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                kingdom_info = await fetch_kingdom(interaction.guild_id, kingdom, turn_id)
                check_value = check.value if isinstance(check, discord.app_commands.Choice) else check
                if not kingdom_info:
                    await interaction.followup.send(f"WTF BRO, {kingdom} IS NOT REGISTERED FOR DRIVING LIKE THIS.")
                dc = kingdom_info.control_dc.total
                check_attr = check_value.lower()
                check_metric = getattr(kingdom_info, check_attr)
                result = random.randint(1, 20) + check_metric.total
                await interaction.followup.send(
                    f"{check_value} Check Result: {result} vs DC {dc}"
                )
        except Exception as e:
            logging.exception(f"Error checking kingdom event: {e}")
            await interaction.followup.send(content=f"An error occurred while checking kingdom events. {e}")


    @kingdom_group.command(name="resolve", description="roll against an event ID")
    @app_commands.autocomplete(kingdom=kingdom_autocomplete)
    @app_commands.choices(
        check=[discord.app_commands.Choice(name='Primary_Check', value='Primary_Check'),
                discord.app_commands.Choice(name='Secondary_Check', value='Secondary_Check'),
               discord.app_commands.Choice(name='Both', value='Both')])
    async def resolve_kingdom_check(self, interaction: discord.Interaction, kingdom: str, event_id: int, turn_id: typing.Optional[int], password: str, check: str = 'Both'):
        """this handles events or does a blind kingdom check"""
        await interaction.response.defer(thinking=True)
        try:
            check_value = check.value if isinstance(check, discord.app_commands.Choice) else check
            async with (aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db):
                cursor = await db.cursor()
                kingdom_info = await fetch_kingdom(interaction.guild_id, kingdom, turn_id)
                if not kingdom_info:
                    await interaction.followup.send(f"WTF BRO, {kingdom} IS NOT REGISTERED FOR DRIVING LIKE THIS.")
                valid_password = validate_password(password, kingdom_info.password)
                if not valid_password:
                    await interaction.followup.send(content="The password provided is incorrect. WHY ARE YOU UP IN SOMEONE ELSE'S JAM YOU MARMELADE THIEF. PADDINGTON WOULD BE SO VERY DISAPPOINTED WITH YOU")
                    return
                await cursor.execute("Select kea.Name, Check_A, Check_B from KB_Events_Active KEA left join KB_Events KE on KE.name = KEA.name where KEA.id = ? and keA.kingdom = ?", (event_id,kingdom))
                event_results = await cursor.fetchone()
                if not event_results:
                    await interaction.followup.send(f"No Event by the id: {event_id} exists for {kingdom}.")
                (name, check_a, check_b) = event_results
                check_list = ['Loyalty', 'Stability', 'Economy']
                dc = kingdom_info.control_dc.total
                embed = discord.Embed(title=f"{kingdom} Event Resolution for {name} event id: {event_id}")
                if check_a in check_list and check_value in ('Primary_Check', 'Both'):
                    check_attr = check_a.lower()
                    check_metric = getattr(kingdom_info, check_attr)
                    roll = random.randint(1, 20)
                    result = check_metric.total + roll
                    check_a_status = 1 if result > dc else 0
                    check_a_status_desc = 'Passed' if check_a_status else 'Failed'
                    await cursor.execute("Update KB_Events_active set Check_A_Status=? where ID=?", (check_a_status, event_id))
                    embed.add_field(name="Primary Check:", value=f"Roll {roll} with Modifier {check_metric.total} - Result: {result} vs DC {dc} - {check_a_status_desc}", inline=False)
                elif check_a and check_value in ('Secondary_Check', 'Both'):
                    embed.add_field(name='Secondary Check:', value=f"This check is weird and requires: {check_a}")
                if check_b in check_list and check_value in ('Secondary_Check', 'Both'):
                    check_attr = check_b.lower()
                    check_metric = getattr(kingdom_info, check_attr)
                    roll = random.randint(1, 20)
                    result = check_metric.total + roll
                    check_b_status = 1 if result > dc else 0
                    check_b_status_desc = 'Passed' if check_a_status else 'Failed'
                    await cursor.execute("Update KB_Events_active set Check_B_Status=? where ID=?", (check_b_status, event_id))
                    embed.add_field(name="Secondary Check:", value=f"Roll {roll} with Modiifer {check_metric.total} - Result: {result} vs DC {dc} - {check_b_status_desc}",
                                    inline=False)
                elif check_b and check_value in ('Primary_Check', 'Both'):
                    embed.add_field(name='Secondary Check:', value=f"This check is weird and requires: {check_b}")
                await db.commit()
                await interaction.followup.send(
                    embed=embed
                )
        except Exception as e:
            logging.exception(f"Error checking kingdom event: {e}")
            await interaction.followup.send(content=f"An error occurred while checking kingdom events. {e}")



    trade_group = discord.app_commands.Group(
        name='trade',
        description='Commands related to kingdom management',
        parent=kingdom_group
    )

    @trade_group.command(name="request", description="Request a trade route to another kingdom")
    @app_commands.autocomplete(kingdom=kingdom_autocomplete)
    @app_commands.autocomplete(target_kingdom=kingdom_autocomplete)
    async def request_trade(
            self, interaction: discord.Interaction, kingdom: str, password: str, target_kingdom: str, distance: int,
            seafood: int = 0, husbandry: int = 0, produce: int = 0,
            grain: int = 0,
            ore: int = 0, wood: int = 0, stone: int = 0,
            raw_textiles: int = 0,
            textiles: int = 0, metallurgy: int = 0, woodworking: int = 0,
            stoneworking: int = 0,
            magical_items: int = 0,
            luxury: int = 0

    ):
        """This command is used to request a trade route to another kingdom"""
        await interaction.response.defer(thinking=True)
        try:
            if distance < 0:
                await interaction.followup.send("Hilarious. Real. Real Funny.")
                return
            resources = {
                "seafood": seafood,
                "husbandry": husbandry,
                "produce": produce,
                "grain": grain,
                "ore": ore,
                "wood": wood,
                "stone": stone,
                "raw_textiles": raw_textiles,
                "textiles": textiles,
                "metallurgy": metallurgy,
                "woodworking": woodworking,
                "stoneworking": stoneworking,
                "magical_items": magical_items,
                "luxury": luxury
            }

            if not any(x is not None for x in resources.values()):
                await interaction.followup.send(
                    "I want you to understand just how much freaking work went into this and you, like some asshole went 'teehee, what if I sent NOTHING.' FUCK YOU."
                )
                return

            negative_resource = next(
                ((name, value) for name, value in resources.items()
                 if value is not None and value < 0),
                None
            )

            if negative_resource:
                name, value = negative_resource

                await interaction.followup.send(
                    f"`{name}` cannot be negative. You entered {value}."
                )
                return

            if kingdom == target_kingdom:
                await interaction.followup.send("https://media.tenor.com/PG7TQGmTPoMAAAAe/are-you-serious-spiderman.png")
                return

            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                kingdom_info = await fetch_kingdom(guild_id=interaction.guild_id, kingdom=kingdom, turn_id=None)
                if not kingdom_info:
                    await interaction.followup.send(content=f"The kingdom of {kingdom} does not exist.")
                    return
                valid_password = validate_password(password, kingdom_info.password)
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

                (food_dataclass, raw_materials_dataclass, simple_crafts_dataclass, luxury_crafts_dataclass,
                 available_food, penalty_dict, event) = await fetch_resources(db=db, kingdom=kingdom_info, farm_penalty=0,
                                          consumption=kingdom_info.consumption.total)
                await cursor.execute("""
                              SELECT 
                                  coalesce(sum(husbandry), 0),
                                  coalesce(sum(seafood), 0),
                                  coalesce(sum(produce), 0),
                                  coalesce(sum(grain), 0),
                                  coalesce(sum(ore), 0),
                                  coalesce(sum(wood), 0),
                                  coalesce(sum(stone), 0),
                                  coalesce(sum(raw_textiles), 0),
                                  coalesce(sum(textiles), 0),
                                  coalesce(sum(metallurgy), 0),
                                  coalesce(sum(woodworking), 0),
                                  coalesce(sum(stoneworking), 0),
                                  coalesce(sum(magical_items), 0),
                                  coalesce(sum(luxury), 0)
                              from KB_Trade
                                  Where Source_Kingdom = ?                   
                              """, (kingdom,))
                outgoing_results = await cursor.fetchone()
                if not outgoing_results:
                    pass
                else:
                    (sent_husbandry, sent_seafood, sent_produce, sent_grain,
                     sent_ore, sent_wood, sent_stone, sent_raw_textiles,
                     sent_textiles, sent_metallurgy, sent_woodworking, sent_stoneworking, sent_magical_items,
                     sent_luxury) = outgoing_results
                    food_dataclass.husbandry.remaining = max(0, food_dataclass.husbandry.remaining - sent_husbandry)
                    food_dataclass.seafood.remaining = max(0, food_dataclass.seafood.remaining - sent_seafood)
                    food_dataclass.produce.remaining = max(0, food_dataclass.produce.remaining - sent_produce)
                    food_dataclass.grain.remaining = max(0, food_dataclass.grain.remaining - sent_grain)
                    raw_materials_dataclass.ore.remaining = max(0, raw_materials_dataclass.ore.remaining - sent_ore)
                    raw_materials_dataclass.stone.remaining = max(0, raw_materials_dataclass.stone.remaining - sent_stone)
                    raw_materials_dataclass.raw_textiles.remaining = max(0, raw_materials_dataclass.raw_textiles.remaining - sent_raw_textiles)
                    raw_materials_dataclass.wood.remaining = max(0, raw_materials_dataclass.wood.remaining - sent_wood)
                    simple_crafts_dataclass.textiles.remaining = max(0, simple_crafts_dataclass.textiles.remaining - sent_textiles)
                    simple_crafts_dataclass.stoneworking.remaining = max(0, simple_crafts_dataclass.stoneworking.remaining - sent_stone)
                    simple_crafts_dataclass.woodworking.remaining = max(0, simple_crafts_dataclass.woodworking.remaining - sent_wood)
                    simple_crafts_dataclass.metallurgy.remaining = max(0, simple_crafts_dataclass.metallurgy.remaining - sent_metallurgy)
                    luxury_crafts_dataclass.magical_items.remaining = max(0, luxury_crafts_dataclass.magical_items.remaining - sent_magical_items)
                    luxury_crafts_dataclass.luxury.remaining = max(0, luxury_crafts_dataclass.luxury.remaining - sent_luxury)
                food_dict = goods_remaining_dict(food_dataclass)
                raw_materials_dict = goods_remaining_dict(raw_materials_dataclass)
                simple_crafts_dict = goods_remaining_dict(simple_crafts_dataclass)
                luxury_crafts_dict = goods_remaining_dict(luxury_crafts_dataclass)
                if sum(chain(food_dict.values(), raw_materials_dict.values(), simple_crafts_dict.values(), luxury_crafts_dict.values())) == 0:
                    await interaction.followup.send("Haha. Buddy. You've got nothing left to send. If you tried to send more, you'd be taking a penalty to your fame for **GASP** failing to send your trade!")
                    return
                trade_valid = False
                response = ""
                if sum((grain, seafood, husbandry, produce)) > 0 and sum(food_dict.values()):
                    response += "You have no food to give away! Your people HUNGY."
                else:
                    trade_valid = True
                print('Food Dict is: ', food_dict, 'raw_mats_dict', raw_materials_dict, 'simple_crafts_dict', simple_crafts_dict, 'luxury_crafts_dict', luxury_crafts_dict)
                food_dict['seafood'] = min(food_dict['seafood'], seafood)
                food_dict['husbandry'] = min(food_dict['husbandry'], husbandry)
                food_dict['grain'] = min(food_dict['grain'], grain)
                food_dict['produce'] = min(food_dict['produce'], produce)
                if sum((ore, stone, raw_textiles, wood)) > 0 and sum(raw_materials_dict.values()):
                    response += "You have no materials to give away! Your people must harvest more!."
                else:
                    trade_valid = True
                raw_materials_dict['ore'] = min(raw_materials_dict['ore'], ore)
                raw_materials_dict['stone'] = min(raw_materials_dict['stone'], stone)
                raw_materials_dict['raw_textiles'] = min(raw_materials_dict['raw_textiles'], raw_textiles)
                raw_materials_dict['wood'] = min(raw_materials_dict['wood'], wood)
                if sum((textiles, woodworking, stoneworking, metallurgy)) > 0 and sum(simple_crafts_dict.values()):
                    response += "You have no crafts to offer! Your people must build more!."
                else:
                    trade_valid = True
                simple_crafts_dict['textiles'] = min(simple_crafts_dict['textiles'], textiles)
                simple_crafts_dict['woodworking'] = min(simple_crafts_dict['woodworking'], woodworking)
                simple_crafts_dict['stoneworking'] = min(simple_crafts_dict['stoneworking'], stoneworking)
                simple_crafts_dict['metallurgy'] = min(simple_crafts_dict['metallurgy'], metallurgy)
                if sum((luxury, magical_items)) > 0 and sum(luxury_crafts_dict.values()):
                    response += "You have no luxuries to offer! Your people must build more!."
                else:
                    trade_valid = True
                luxury_crafts_dict['magical_items'] = min(luxury_crafts_dict['magical_items'], magical_items)
                luxury_crafts_dict['luxury'] = min(luxury_crafts_dict['luxury'], luxury)
                if not trade_valid:
                    await interaction.followup.send(response)
                    return
                else:
                    view = TradeView(
                            allowed_user_id=target_ruler_id,
                            requester_name=interaction.user.name,
                            requester_id=interaction.user.id,
                            character_name=source_ruler_name,
                            recipient_name=target_ruler_name,
                            requesting_kingdom=kingdom,
                            sending_kingdom=target_kingdom,
                            distance=distance,
                            bot=self.bot,
                            guild_id=interaction.guild_id,
                            interaction=interaction,
                            food_dict=food_dict,
                            raw_materials_dict=raw_materials_dict,
                            simple_crafts_dict=simple_crafts_dict,
                            luxury_crafts_dict=luxury_crafts_dict
                        )
                    await view.create_embed()
                    await view.send_initial_message()
                    await interaction.followup.send("Request created")
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
                Magical_Items, luxury
                FROM KB_Trade
                WHERE Source_Kingdom = ? AND End_Kingdom = ?"""
                delete_statement = "Delete from KB_Trade where Source_Kingdom = ? and End_Kingdom = ?"
                if intent == 2:
                    await cursor.execute(statement, (target_kingdom, kingdom))
                    await cursor.execute(delete_statement, (target_kingdom, kingdom))
                else:
                    await cursor.execute(statement, (kingdom, target_kingdom))
                    await cursor.execute(delete_statement, (kingdom, target_kingdom))
                trade_results = await cursor.fetchone()
                if not trade_results:
                    await interaction.followup.send(content="No trade route exists between these kingdoms.")
                    return
                (source_kingdom, end_kingdom,
                 husbandry, seafood, grain, produce,
                 ore, stone, wood, raw_textiles,
                 textiles, metallurgy, woodworking, stoneworking,
                 magical_items, luxury) = trade_results
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
                if any((magical_items, luxury)):
                    embed.add_field(name="Items",
                                    value=f"Magical Items: {magical_items}, Luxury: {luxury}")
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
    @app_commands.autocomplete(region=region_autocomplete)
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
    async def display_kingdom(self, interaction: discord.Interaction, kingdom: typing.Optional[str], page: int = 0, turn_id: int = 0):
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
                        interaction=interaction,
                        kingdom=kingdom,
                        turn_id=turn_id
                    )
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
                        interaction=interaction,
                        kingdom=kingdom,
                        turn_id=turn_id)
                await view.update_results()
                await view.create_embed()
                await view.send_initial_message()
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"Error displaying kingdom information: {e}")
            await interaction.followup.send(content=f"An error occurred while displaying kingdom information. {e}")

    @settlement_group.command(name='display', description='Display settlement information')
    @app_commands.autocomplete(kingdom=kingdom_autocomplete)
    @app_commands.autocomplete(settlement=settlement_autocomplete)
    async def display_settlement(self, interaction: discord.Interaction, kingdom: str, settlement: str = None, page: int = 0, turn_id: int = 0):
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
                        interaction=interaction, turn_id=turn_id)
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
                        interaction=interaction,
                        turn_id=turn_id)
                await view.update_results()
                await view.create_embed()
                await view.send_initial_message()
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"Error displaying settlement information: {e}")
            await interaction.followup.send(content=f"An error occurred while displaying settlement information. {e}")

    @hex_group.command(name='display', description='Display hex information')
    @app_commands.autocomplete(kingdom=kingdom_autocomplete)
    @app_commands.autocomplete(region=region_autocomplete)
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
                await cursor.execute("SELECT Count(Full_name) FROM KB_Buildings_Blueprints")
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
    @app_commands.autocomplete(kingdom=kingdom_autocomplete)
    @app_commands.autocomplete(settlement=settlement_autocomplete)
    async def display_constructed_settlement(self, interaction: discord.Interaction, kingdom: str, settlement: str = None, page: int = 0):
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
                    kingdom=kingdom,
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


