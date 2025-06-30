import logging
import shutil
import typing
from math import ceil
from typing import Union
import discord
import unbelievaboat
from discord.app_commands import checks
from discord.ext import commands
from discord import app_commands
import datetime
import os
from pywaclient.api import BoromirApiClient as WaClient
import aiosqlite
import shared_functions
from decimal import Decimal

from commands import gamemaster_commands, RP_Commands
from shared_functions import name_fix, character_select_autocompletion
import commands.character_commands as character_commands

# *** GLOBAL VARIABLES *** #
os.chdir("C:\\pathparser")


async def update_region_level_range(interaction: discord.Interaction, database_conn: aiosqlite.Connection,
                                    level_range_info, region: str, min_level: int, max_level: int, role: discord.Role):
    cursor = await database_conn.cursor()
    for level_range in level_range_info:
        (name, min_stored_level, max_stored_level, old_role_id) = level_range
        print("PT2", level_range)
        if min_level < min_stored_level < max_stored_level < max_level:
            await interaction.followup.send(
                f"The level range you are trying to add overlaps with an existing level range of {name} and cannot split it into two entries either rename it, or set the min level to be below or equal to {min_stored_level} or the max level to be above or equal to {max_stored_level}.",
                ephemeral=True)
            return None
        elif min_level <= min_stored_level < max_stored_level <= max_level:
            await cursor.execute("DELETE FROM Regions_Level_Range WHERE Name = ? and Min_Level = ? and Max_Level = ?",
                                 (name, min_stored_level, max_stored_level))
            content = f"The level range of {min_stored_level}-{max_stored_level} has been removed as it was entirely within the new level range.\r\n"
            catch_range_higher = max_stored_level
            catch_range_lower = min_stored_level
        elif min_stored_level < min_level < max_stored_level < max_level:
            await cursor.execute(
                "UPDATE Regions_Level_Range SET Max_Level = ? WHERE Name = ? AND Min_level = ? and Max_Level = ?",
                (min_level - 1, name, min_stored_level, max_stored_level))
            content = f"The level range of {min_stored_level}-{max_stored_level} has been reduced to to {min_stored_level}-{max_level - 1}.\r\n"
            catch_range_higher = min_level
            catch_range_lower = max_stored_level
        elif min_level < min_stored_level < max_level < max_stored_level:
            await cursor.execute(
                "UPDATE Regions_Level_Range SET Min_Level = ? WHERE Name = ? AND Min_level = ? and Max_Level = ?",
                (max_level + 1, name, min_stored_level, max_stored_level))
            content = f"The level range of {min_stored_level}-{max_stored_level} has been reduced to to {min_level + 1}-{max_stored_level}.\r\n"
            catch_range_higher = max_level
            catch_range_lower = min_stored_level
        else:
            catch_range_higher = 0
            catch_range_lower = 0
            content = ""
        await cursor.execute("select player_id from Player_Characters where region = ? and level >= ? and level <= ?",
                             (region, catch_range_lower, catch_range_higher))
        players = await cursor.fetchall()
        for player in players:
            old_role = interaction.guild.get_role(old_role_id)
            await interaction.guild.get_member(player[0]).remove_roles(old_role)
        return content


async def transactions_reverse(guild_id: int, transaction_id: int, author_id: int, author_name: str,
                               reason: str) -> (
        Union[tuple[int, int, str, int, float, float, float, float], str]):
    """Reverse a transaction by undoing the transaction and updating the player's gold information."""
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as conn:
            cursor = await conn.cursor()
            # Retrieve the original Transaction information to be undone
            await cursor.execute(
                "Select Character_Name, Gold_value, Effective_Gold_Value, Effective_gold_value_max, source_command, Related_Transaction_ID FROM A_Audit_Gold WHERE transaction_id = ?",
                (transaction_id,))
            gold_info = await cursor.fetchone()
            if not gold_info:
                # If no transaction is found, return a failed message
                return_value = f"There is no transaction with the ID of {transaction_id}."
                return return_value
            else:
                # If a transaction is found, extract the relevant information
                (character_name, gold, effective_gold, max_effective_gold, source_command,
                 related_transaction_id) = gold_info
                # Retrieve the player information used in the transaction
                await cursor.execute(
                    "select gold, gold_value, gold_value_max, Thread_ID from Player_Characters where Character_Name = ?",
                    (character_name,))
                player_info = await cursor.fetchone()
                if not player_info:
                    # Command to undo the transaction failed due to the player not being found!
                    return_value = f"There is no character with the name or nickname of {character_name}! Cannot undo transaction!"
                    return return_value
                else:
                    (gold_total, gold_value_total, gold_value_max_total, thread_id) = player_info
                    # Update the player's gold information to reflect the undoing of the transaction
                    await cursor.execute(
                        "UPDATE Player_Characters SET Gold = ?, Gold_Value = ?, Gold_Value_Max = ? WHERE Character_Name = ?",
                        (
                            gold_total - gold, gold_value_total - effective_gold,
                            gold_value_max_total - max_effective_gold,
                            character_name))
                    await conn.commit()
                    # Insert the undo transaction into the audit table for auditing logs
                    await cursor.execute(
                        "INSERT into A_Audit_Gold (Character_Name, Author_Name, Author_ID, gold_value, Effective_Gold_Value, Effective_Gold_value_max, Related_Transaction_ID, Reason, Source_Command) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            character_name, author_name, author_id, -gold, -effective_gold, -max_effective_gold,
                            transaction_id,
                            reason, 'undo transaction'))
                    await conn.commit()
                    await cursor.execute("Select MAX(Transaction_ID) FROM A_Audit_Gold")
                    new_transaction_id = await cursor.fetchone()
                    # Return the new transaction ID for the undo transaction
                    new_transaction_id = new_transaction_id[0]
                    new_gold_total = gold_total - gold
                    new_effective_gold_total = gold_value_total - effective_gold
                    new_max_effective_gold_total = gold_value_max_total - max_effective_gold
                    return_value = (
                        new_transaction_id, related_transaction_id, character_name, thread_id, gold, new_gold_total,
                        new_effective_gold_total, new_max_effective_gold_total)
                    return return_value
    except (aiosqlite.Error, TypeError, ValueError) as e:
        logging.exception(
            f"an error occurred for {author_name} whilst undoing transaction with id {transaction_id}': {e}")
        return_value = f"an error occurred for {author_name} whilst undoing transaction with id {transaction_id} Error: {e}."
        return return_value


def safe_add(a, b):
    """Safely add two values together, treating None as zero and converting to Decimal if necessary."""
    # Treat None as zero
    a = a if a is not None else 0
    b = b if b is not None else 0

    # If either value is a Decimal, convert both to Decimal
    if isinstance(a, float) or isinstance(b, float):
        a = float(a)
        b = float(b)

    return a + b


def create_progress_bar(current, total, bar_length=20):
    """Create a progress bar for a given current and total value."""
    progress = int(bar_length * (current / total))
    return f"[{'█' * progress}{'-' * (bar_length - progress)}] {current}/{total}"


async def add_item_to_store(guild_id, item_name, price, description, stock, inventory, usable, sellable, image,
                            custom_message):
    """Add an item to the roleplay store."""
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as conn:
            cursor = await conn.cursor()
            await cursor.execute(
                "SELECT name FROM RP_Store_Items WHERE name = ?",
                (item_name,))
            exists = await cursor.fetchone()
            if exists:
                return "Item already exists in the store. Please choose a different item name."
            await cursor.execute(
                "INSERT INTO RP_Store_Items (name, price, description, stock_remaining, inventory, usable, sellable, matching_requirements, image_link, custom_message) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (item_name, price, description, stock, inventory, usable, sellable, 1, image, custom_message))
            await conn.commit()
            return True
    except (aiosqlite.Error, TypeError, ValueError) as e:
        logging.exception(
            f"an error occurred whilst adding an item to the store': {e}")
        return f"An error occurred whilst adding an item to the store. Error: {e}."


async def edit_item_in_store(guild_id, old_item_name, new_item_name, price, description, stock, inventory, usable,
                             sellable, image, custom_message):
    """Edit an item in the roleplay store."""
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as conn:
            cursor = await conn.cursor()
            if new_item_name:
                await cursor.execute("SELECT name FROM RP_Store_Items WHERE name = ?", (new_item_name,))
                exists = await cursor.fetchone()
                if exists:
                    return f"Item '{new_item_name}' already exists in the store. Please choose a different item name."
            await cursor.execute(
                "SELECT price, description, stock_remaining, inventory, usable, sellable, image_link, Custom_message FROM RP_Store_Items WHERE name = ?",
                (old_item_name,))
            item_info = await cursor.fetchone()
            if not item_info:
                raise ValueError(f"Item '{old_item_name}' not found in the store.")
            (old_price, old_description, old_stock, old_inventory, old_usable, old_sellable, old_image,
             old_custom_message) = item_info

            # If a value is None, keep the old value
            new_price = price if price is not None else old_price
            new_description = description if description else old_description
            new_stock = stock if stock is not None else old_stock
            new_inventory = inventory if inventory else old_inventory
            new_usable = usable if usable else old_usable
            new_sellable = sellable if sellable else old_sellable
            new_image = image if image else old_image
            new_item_name = new_item_name if new_item_name else old_item_name
            new_custom_message = custom_message if custom_message else old_custom_message

            # Update the item in the store
            await cursor.execute(
                "UPDATE RP_Store_Items SET name = ?, price = ?, description = ?, stock_remaining = ?, inventory = ?, usable = ?, sellable = ?, image_link = ?, Custom_Message = ?, WHERE name = ?",
                (new_item_name, new_price, new_description, new_stock, new_inventory, new_usable, new_sellable,
                 new_image, new_custom_message, old_item_name))
            await conn.commit()
            await cursor.execute(
                "UPDATE RP_Players_Items SET item_name = ? WHERE item_name = ?",
                (new_item_name, old_item_name))
            return True
    except (aiosqlite.Error, TypeError, ValueError) as e:
        logging.exception(
            f"an error occurred whilst adding an item to the store': {e}")
        return f"An error occurred whilst adding an item to the store. Error: {e}."


async def session_log_player(cursor: aiosqlite.Cursor,
                             interaction: discord.Interaction,
                             bot,
                             session_id: int,
                             player_id: int,
                             character_name: str,
                             thread_id: int,
                             source: str,
                             packaged_session_info: tuple,
                             return_level: tuple,
                             return_trial: tuple,
                             return_gold: tuple,
                             return_essence: tuple):
    """Log a player's session rewards and update their character information."""
    try:
        character_changes = shared_functions.CharacterChange(
            character_name=character_name,
            author=interaction.user.name,
            source=source)

        if isinstance(return_level, tuple):
            # If the return is a tuple, unpack the values, the command succeeded.
            (new_level, total_milestones, min_milestones, milestones_to_level, milestones_required,
             awarded_total_milestones) = return_level
            character_changes.level = new_level
            character_changes.milestones_total = total_milestones
            character_changes.milestones_remaining = min_milestones
            character_changes.milestone_change = awarded_total_milestones
        else:
            # If the return is not a tuple, set the milestone change to zero, the command failed in processing the level tuple.
            awarded_total_milestones = 0

        if isinstance(return_trial, tuple):
            # If the return is a tuple, unpack the values, the command succeeded.
            (new_tier, total_trials, trials_required, trial_change) = return_trial
            character_changes.tier = new_tier
            character_changes.trials = total_trials
            character_changes.trials_remaining = trials_required
            character_changes.trial_change = trial_change
        elif isinstance(return_trial, int):
            # If the return is an integer, set the trial change to zero, the command failed in processing the trial tuple.
            trial_change = 0
        else:
            # If the return is not a tuple or an integer, set the trial change to zero, there was no trial tuple TO process.
            trial_change = 0

        if isinstance(return_gold, tuple):
            # If the return is a tuple, unpack the values, the command succeeded.
            (calculated_difference, gold_total, gold_value_total, gold_value_max_total, transaction_id) = return_gold
            character_changes.gold = gold_total
            character_changes.gold_change = calculated_difference
            character_changes.effective_gold = gold_value_total
            character_changes.effective_gold_max = gold_value_max_total
            character_changes.transaction_id = transaction_id
        else:
            # If the return is not a tuple, set the gold change to zero, the command failed in processing the gold tuple.
            calculated_difference = 0
            transaction_id = 0

        if isinstance(return_essence, tuple):
            # If the return is a tuple, unpack the values, the command succeeded.
            (essence_total, essence_change) = return_essence
            character_changes.essence = essence_total
            character_changes.essence_change = essence_change

        else:
            # If the return is not a tuple, set the essence change to zero, the command failed in processing the essence tuple.
            essence_change = 0

        # Unpack the session information and insert it into the log.
        (player_name, player_id, original_level, original_tier, original_effective_gold) = packaged_session_info
        await cursor.execute("INSERT INTO Session_Log (Session_ID, Player_ID, Character_Name, Level, "
                             "Tier, Effective_Gold, Received_Milestones, Received_Trials, Received_Gold, "
                             "Received_Fame, Received_Prestige, Received_Essence, Gold_Transaction_ID) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                             (
                                 session_id, player_id, character_name, original_level, original_tier,
                                 original_effective_gold,
                                 awarded_total_milestones, trial_change, calculated_difference, 0, 0, essence_change,
                                 transaction_id))

        # Update the character information in the database and log it appropriately.
        await shared_functions.character_embed(character_name=character_name,
                                               guild=interaction.guild)

        await shared_functions.log_embed(change=character_changes, guild=interaction.guild,
                                         thread=thread_id, bot=bot)

        return f"<@{player_id}>'s {character_name} has been successfully updated!"

    except (aiosqlite.Error, TypeError, ValueError) as e:
        logging.exception(
            f"an error occurred for {interaction.user.name} whilst updating bio & log with ID {session_id} for character {character_name}': {e}")
        return f"<@{player_id}>'s {character_name} encountered an error whilst being updated! Error: {e}."


class AdminCommands(commands.Cog, name='admin'):
    def __init__(self, bot):
        self.bot = bot

    admin_group = discord.app_commands.Group(
        name='admin',
        description='Commands related to administration'
    )

    @admin_group.command(name='help', description='Help commands for the character tree')
    async def help(self, interaction: discord.Interaction):
        """Display the help command for the admin commands."""
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            embed = discord.Embed(title=f"Admin Help", description=f'This is a list of Admin help commands',
                                  colour=discord.Colour.blurple())
            embed.add_field(name='__**Archive Commands**__',
                            value="""
                            **/admin archive display** - Display the server archive\n
                            **/admin archive inactive** - Archive inactive players and delete their bio.\n
                            """)

            embed.add_field(name=f'__**Character Commands**__',
                            value="""
                            **/admin character essence** - Adjust the essence of a character\n
                            **/admin character milestones** - Adjust the milestones of a character\n
                            **/admin character trials** - Adjust the trials of a character\n
                            """,
                            inline=False)

            embed.add_field(name=f'__**Gold Commands**__',
                            value="""
                            **/admin gold adjust** - Adjust the gold of a character\n
                            **/admin gold undo_transaction** - Undo a gold transaction\n
                            """,
                            inline=False)

            embed.add_field(name=f'__**Level Commands**__',
                            value="""
                            **/admin level level_range** - Adjust the level range roles for the server\n
                            **/admin level cap** - Adjust the level cap for the server\n
                            **/admin level display** - Display information about levels in the server.\n
                            **/admin level jobs** - adjust the milestone rewards for jobs in the server\n
                            **/admin level milestones** - adjust the milestone floor for levels in the server\n
                            **/admin level wpl** - adjust the associated wealth per level for levels in the server. this affects the payout reward of gold pouches.\n
                            """,
                            inline=False)

            embed.add_field(name=f'__**Mythic Commands**__',
                            value="""
                            **/admin mythic cap** - Adjust the mythic cap for the server\n
                            **/admin mythic define** - Define the mythic tiers and their trials for the server\n
                            **/admin mythic display** - Display information about mythic tiers in the server.\n
                            """,
                            inline=False)

            embed.add_field(name=f'__**Roleplay Commands**__',
                            value="""
                            **/admin roleplay add_channel** - Add a roleplay channel to the server in which players can generate RP. Threads inside the channel count as part of the channel.\n
                            **/admin roleplay remove_channel** - Remove a roleplay channel from the server\n
                            **/admin roleplay list** - List all roleplay settings in the server\n
                            **/admin roleplay list_channel** - List all roleplay channels in the server\n
                            **/admin roleplay adjust_rp** - Adjust the roleplay balance of a user.\n
                            **/admin roleplay adjust_role** - Adjust the roleplay balance of a role.\n
                            **/admin roleplay update** - Adjust a roleplay setting.\n
                            """,
                            inline=False)
            embed.add_field(name=f'__**RP Store Commands**__',
                            value="""
                            **/admin RP_Store Add** - Add a roleplay channel to the server in which players can generate RP. Threads inside the channel count as part of the channel.\n
                            **/admin RP_Store Behavior** - Remove a roleplay channel from the server\n
                            **/admin RP_Store Cancel_Behavior** - List all roleplay settings in the server\n
                            **/admin RP_Store Cancel_Requirement** - List all roleplay channels in the server\n
                            **/admin RP_Store Edit** - Adjust the roleplay balance of a user.\n
                            **/Admin RP_Store Give** - Adjust the number of items a user has** \n
                            """, inline=False)
            embed.add_field(name=f'__**More RP Store Commands**__',
                            value="""
                            **/Admin RP_Store Take** - Take Items from the inventory of a player \n
                            **/admin RP_Store List** - Adjust the roleplay balance of a role.\n
                            **/admin RP_Store Matching** - Adjust a roleplay setting.\n
                            **/admin RP_Store Requirements** - Adjust a roleplay setting.\n
                            **/admin RP_Store List** - Adjust a roleplay setting.\n
                            """, inline=False)
            embed.add_field(name=f'__**Session Commands**__',
                            value="""
                            **/admin session management** - Manage a session\n
                            """,
                            inline=False)
            embed.add_field(name="__**Setting Commands**__",
                            value="""
                            **/admin settings display** - Display the server settings\n
                            **/admin settings update** - Update the server settings\n
                            **/admin settings titles** - Update the server titles store\n
                            **/admin settings fame** - Update the server fame store\n
                            **/admin settings ubb_inventory** - display a player's raw ubb inventory data.\n
                            **/admin settings reset** - Reset the server settings\n
                            """,
                            inline=False)
            embed.add_field(name="__**Test commands**__",
                            value="""
                            **/Admin Test Worldanvil** - Test the worldanvil API\n""",
                            inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)
        except discord.errors.HTTPException:
            logging.exception(f"Error in help command")
        finally:
            return

    @admin_group.command(name='announce', description='Announce a message to a channel')
    async def announce(self, interaction: discord.Interaction, role: discord.Role, message: str):
        """Announce a message to a channel."""
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            if role.mentionable:

                await interaction.channel.send(f"Announcing to {role.mention}:\n{message}")
            else:

                try:
                    await role.edit(mentionable=True)
                    await interaction.channel.send(f"Announcing to {role.mention}:\n{message}")
                    await role.edit(mentionable=False)
                except discord.errors.Forbidden:
                    await interaction.channel.send(f"Announcing to {role.name}:\n{message}")

            await interaction.followup.send('announcement sent')
        except discord.errors.HTTPException:
            logging.exception(f"Error in announce command")
        finally:
            return


    character_group = discord.app_commands.Group(
        name='character',
        description='Event settings commands',
        parent=admin_group
    )

    @character_group.command(name="essence",
                             description="commands for adding or removing essence from a character")
    @app_commands.autocomplete(character_name=character_select_autocompletion)
    async def essence(self, interaction: discord.Interaction, character_name: str, amount: int, reason: str):
        """Adjust the essence a PC has"""
        _, unidecode_name = name_fix(character_name)
        guild_id = interaction.guild_id
        guild = interaction.guild
        await interaction.response.defer(thinking=True, ephemeral=True)
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as conn:
            cursor = await conn.cursor()
            try:
                await cursor.execute(
                    "Select True_Character_Name, Character_Name, Essence, Thread_ID FROM Player_Characters where Character_Name = ? OR Nickname = ?",
                    (unidecode_name, unidecode_name))
                player_info = await cursor.fetchone()
                if amount == 0:
                    await interaction.followup.send(f"No changes to essence total required.")
                else:
                    if not player_info:
                        await interaction.followup.send(
                            f"there is no {character_name} registered.", ephemeral=True)
                    else:
                        # Unpack discovered player information
                        (true_character_name, character_name, essence, thread_id) = player_info
                        essence_adjustment = character_commands.calculate_essence(
                            character_name=character_name,
                            essence=essence,
                            essence_change=amount,
                            accepted_date=None
                        )

                        (new_essence, essence_change) = essence_adjustment
                        character_updates = shared_functions.UpdateCharacterData(
                            character_name=character_name,
                            essence=new_essence)

                        # Update the character's essence in the database
                        updated_character = await shared_functions.update_character(
                            guild_id=guild.id,
                            change=character_updates)
                        if not isinstance(updated_character, tuple):
                            await interaction.followup.send(
                                f"An error occurred whilst updating the character's essence for '{character_name}'!.",
                                ephemeral=True)
                            return
                        if isinstance(updated_character, tuple):
                            success = updated_character[0]
                            if not success:
                                # If the update failed, respond with the error message explaining why. Stop further steps.
                                await interaction.followup.send(
                                    f"An error occurred whilst updating the character's essence for '{character_name}'!. \r\n {updated_character[1]}",
                                    ephemeral=True)
                                return

                        # Log the character's essence change
                        character_changes = shared_functions.CharacterChange(
                            character_name=character_name,
                            author=interaction.user.name,
                            essence=new_essence,
                            essence_change=essence_change,
                            source=f"admin adjusted essence by {amount} for {character_name}\r\nReason: {reason}",
                            )
                        character_log = await shared_functions.log_embed(change=character_changes, guild=guild,
                                                                         thread=thread_id, bot=self.bot)

                        # Update the character's Bio embed
                        await shared_functions.character_embed(
                            character_name=character_name,
                            guild=guild)

                        # respond successfully with logged changes
                        await interaction.followup.send(embed=character_log,
                                                        content=f"Essence changes for {character_name} have been made: {essence_change}.",
                                                        ephemeral=True)
            except (aiosqlite.Error, TypeError, ValueError, character_commands.CalculationAidFunctionError) as e:
                logging.exception(
                    f"an error occurred for {interaction.user.name} whilst adjusting essence for {character_name}': {e}")
                await interaction.followup.send(
                    f"An error occurred whilst adjusting essence for '{character_name}' Error: {e}.", ephemeral=True)

    gold_group = discord.app_commands.Group(
        name='gold',
        description='gold commands',
        parent=admin_group
    )

    @gold_group.command(name="adjust",
                        description="commands for adding or removing gold from a character")
    @app_commands.autocomplete(character_name=shared_functions.character_select_autocompletion)
    async def gold_adjust(
            self,
            interaction: discord.Interaction,
            character_name: str,
            reason: str,
            effective_gold: typing.Optional[float],
            lifetime_gold: typing.Optional[float],
            amount: float = 0.0
    ):
        """Adjust the gold a PC has"""
        _, unidecode_name = name_fix(character_name)
        guild_id = interaction.guild_id
        guild = interaction.guild
        await interaction.response.defer(thinking=True, ephemeral=True)

        # Convert input values to Decimal
        amount = Decimal(str(amount))
        effective_gold = Decimal(str(effective_gold)) if isinstance(effective_gold, float) else effective_gold
        lifetime_gold = Decimal(str(lifetime_gold)) if isinstance(lifetime_gold, float) else lifetime_gold

        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as conn:
            cursor = await conn.cursor()
            try:
                if amount == 0 and effective_gold == 0 and lifetime_gold == 0:
                    await interaction.followup.send(
                        "If you don't intend to change anything, why initiate the command?",
                        ephemeral=True
                    )
                    return

                # Fetch the player's information
                await cursor.execute(
                    """
                    SELECT True_Character_Name, Character_Name, Level, Oath,
                           Gold, Gold_Value, Gold_Value_max, Thread_ID
                    FROM Player_Characters
                    WHERE Character_Name = ? OR Nickname = ?
                    """,
                    (unidecode_name, unidecode_name)
                )
                player_info = await cursor.fetchone()

                if not player_info:
                    await interaction.followup.send(
                        f"No character found with the name or nickname '{character_name}'.",
                        ephemeral=True
                    )
                    return

                (true_character_name, character_name, character_level, oath,
                 gold, gold_value, gold_value_max, thread_id) = player_info

                # Convert fetched values to Decimal
                gold = Decimal(str(gold))
                gold_value = Decimal(str(gold_value))
                gold_value_max = Decimal(str(gold_value_max))

                # Calculate the new gold values
                gold_result = await character_commands.gold_calculation(
                    guild_id=guild_id,
                    author_id=interaction.user.id,
                    author_name=interaction.user.name,
                    character_name=character_name,
                    level=character_level,
                    oath=oath,
                    gold=gold,
                    gold_value=gold_value,
                    gold_value_max=gold_value_max,
                    gold_change=amount,
                    gold_value_change=effective_gold,
                    gold_value_max_change=lifetime_gold,
                    source='Admin Gold Adjust',
                    reason=reason
                )

                (adjusted_gold_change, gold_total, new_effective_gold,
                 gold_value_max_total, transaction_id) = gold_result

                gold_package = (gold_total, new_effective_gold, gold_value_max_total)

                # Update the character's gold information
                character_updates = shared_functions.UpdateCharacterData(
                    character_name=character_name,
                    gold_package=gold_package
                )
                await shared_functions.update_character(
                    guild_id=guild_id,
                    change=character_updates
                )

                # Log the character's gold change
                character_changes = shared_functions.CharacterChange(
                    character_name=character_name,
                    author=interaction.user.name,
                    gold=gold_total,
                    gold_change=adjusted_gold_change,
                    gold_value=new_effective_gold,
                    transaction_id=transaction_id,
                    source=f"Admin adjusted gold by {amount} for {character_name} for {reason}"
                )

                character_log = await shared_functions.log_embed(
                    change=character_changes,
                    guild=guild,
                    thread=thread_id,
                    bot=self.bot
                )
                await shared_functions.character_embed(
                    character_name=character_name,
                    guild=guild
                )
                await interaction.followup.send(
                    embed=character_log,
                    content=f"Gold changes for {character_name} have been made.",
                    ephemeral=True
                )
            except Exception as e:
                logging.exception(
                    f"An error occurred for {interaction.user.name} while adjusting gold for {character_name}: {e}"
                )
                await interaction.followup.send(
                    f"An error occurred while adjusting gold for '{character_name}'. Error: {e}.",
                    ephemeral=True
                )

    @gold_group.command(name="undo_transaction",
                        description="commands for undoing a transaction")
    async def undo_transaction(self, interaction: discord.Interaction, reason: str,
                               transaction_id: int):
        guild_id = interaction.guild_id
        guild = interaction.guild

        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            transactions_undo = await transactions_reverse(
                guild_id=guild_id, transaction_id=transaction_id,
                author_id=interaction.user.id, author_name=interaction.user.name, reason=reason)
            if isinstance(transactions_undo, str):
                await interaction.followup.send(transactions_undo, ephemeral=True)
            else:
                (new_transaction_id, related_transaction_id, character_name, thread_id, amount, gold_total,
                 gold_value_total,
                 gold_value_max_total) = transactions_undo
                # Log the character's gold change
                character_changes = shared_functions.CharacterChange(
                    character_name=character_name,
                    author=interaction.user.name,
                    gold=Decimal(gold_total),
                    gold_change=Decimal(amount),
                    source=f"admin undid the transaction of transaction ID: {transaction_id} reducing gold by {amount} for {character_name} for {reason} \r\n New Transaction ID of {new_transaction_id}")
                character_log = await shared_functions.log_embed(
                    change=character_changes,
                    guild=guild,
                    thread=thread_id,
                    bot=self.bot)
                await shared_functions.character_embed(
                    character_name=character_name,
                    guild=guild)
                content = f"undid transaction {transaction_id} for {character_name} with a new transaction id of {new_transaction_id}."
                if related_transaction_id:
                    # If there are related transactions, undo them as well, one was discovering whilst undoing the previous one.
                    related_transactions_undo = await transactions_reverse(
                        guild_id=interaction.guild.id, transaction_id=transaction_id,
                        author_id=interaction.user.id, author_name=interaction.user.name, reason=reason)
                    if isinstance(related_transactions_undo, str):
                        content += f"\r\n {related_transactions_undo}"
                    else:
                        # Log the character's gold change
                        (new_transaction_id, _, character_name, thread_id, amount, gold_total, gold_value_total,
                         gold_value_max_total) = related_transactions_undo
                        character_changes = shared_functions.CharacterChange(
                            character_name=character_name,
                            author=interaction.user.name,
                            gold=Decimal(gold_total),
                            gold_change=Decimal(amount),
                            source=f"admin undid the transaction of transaction ID: {transaction_id} reducing gold by {amount} for {character_name} for {reason} \r\n New Transaction ID of {new_transaction_id}")
                        character_log = await shared_functions.log_embed(
                            change=character_changes,
                            guild=guild,
                            thread=thread_id,
                            bot=self.bot)
                        await shared_functions.character_embed(
                            character_name=character_name,
                            guild=guild)
                        content += f"\r\n undid related transaction {transaction_id} for {character_name} with a new transaction id of {new_transaction_id}."
                await interaction.followup.send(embed=character_log, content=content, ephemeral=True)
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(
                f"an error occurred for {interaction.user.name} whilst undoing a gold transaction with ID: {transaction_id}': {e}")
            await interaction.followup.send(
                f"An error occurred whilst undoing a gold transaction with ID: '{transaction_id}' Error: {e}.",
                ephemeral=True)

    session_group = discord.app_commands.Group(
        name='session',
        description='session commands',
        parent=admin_group
    )

    @session_group.command(name="management", description="command for managing sessions")
    async def management(
            self, interaction: discord.Interaction, session_id: int, gold: typing.Optional[int],
            easy: typing.Optional[int], medium: typing.Optional[int], hard: typing.Optional[int],
            deadly: typing.Optional[int], essence: typing.Optional[int],
            trials: typing.Optional[int],
            reward_all: typing.Optional[str], party_reward: typing.Optional[str],
            fame: typing.Optional[int], prestige: typing.Optional[int]):
        """Update Session Information and alter the rewards received by the players"""
        guild_id = interaction.guild_id
        guild = interaction.guild

        await interaction.response.defer(thinking=True, ephemeral=True)

        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as conn:
            cursor = await conn.cursor()

            try:
                await cursor.execute(
                    "SELECT GM_Name, Session_Name, Hammer_Time, Session_Range, Gold, Essence, Easy, Medium, Hard, Deadly, Trials, Alt_Reward_All, Alt_Reward_Party, Session_Thread, Message, Rewards_Message, Rewards_Thread, Fame, Prestige FROM Sessions WHERE Session_ID = ? and IsActive = 0 LIMIT 1",
                    (session_id,))
                session_info = await cursor.fetchone()

                if not session_info:
                    await interaction.followup.send(f'invalid session ID of {session_id}', ephemeral=True)

                else:
                    (gm_name, session_name, play_time, session_range, session_gold, session_essence, session_easy,
                     session_medium, session_hard, session_deadly, session_trials, session_alt_reward_all,
                     session_alt_reward_party, session_session_thread, session_message, session_rewards_message,
                     session_rewards_thread, session_fame, session_prestige) = session_info

                    rewarded_gold = session_gold if not gold else gold
                    rewarded_essence = session_essence if not essence else essence
                    rewarded_easy = session_easy if easy is None else easy
                    rewarded_medium = session_medium if medium is None else medium
                    rewarded_hard = session_hard if hard is None else hard
                    rewarded_deadly = session_deadly if deadly is None else deadly
                    rewarded_trials = session_trials if trials is None else trials
                    rewarded_reward_all = session_alt_reward_all if reward_all is None else reward_all
                    rewarded_reward_party = session_alt_reward_party if party_reward is None else party_reward
                    rewarded_fame = session_fame if fame is None else fame
                    rewarded_prestige = session_prestige if prestige is None else prestige

                    await cursor.execute(
                        "update Sessions set IsActive = 0, "
                        "gold = ?, essence = ?, easy = ?, medium = ?, hard = ?, deadly = ?, trials = ?, "
                        "fame = ?, prestige = ?, alt_reward_party = ?, alt_reward_all = ? where Session_ID = ?",
                        (rewarded_gold, rewarded_essence, rewarded_easy, rewarded_medium, rewarded_hard,
                         rewarded_deadly, rewarded_trials, rewarded_fame, rewarded_prestige,
                         rewarded_reward_party, rewarded_reward_all, session_id))
                    await conn.commit()

                    base_session_info = gamemaster_commands.RewardSessionBaseInfo(
                        session_name=session_name,
                        rewarded_gold=rewarded_gold,
                        rewarded_essence=rewarded_essence,
                        rewarded_easy=rewarded_easy,
                        rewarded_medium=rewarded_medium,
                        rewarded_hard=rewarded_hard,
                        rewarded_deadly=rewarded_deadly,
                        rewarded_trials=rewarded_trials,
                        rewarded_alt_reward_all=rewarded_reward_all,
                        rewarded_alt_reward_party=rewarded_reward_party,
                        rewarded_fame=rewarded_fame,
                        rewarded_prestige=rewarded_prestige,
                        rewarded_session_thread=session_rewards_thread,
                        rewarded_message=session_rewards_message,
                        gm_name=gm_name)

                    if rewarded_gold < 0 or rewarded_easy < 0 or rewarded_medium < 0 or rewarded_hard < 0 or rewarded_deadly < 0 or rewarded_essence < 0 or rewarded_trials < 0:
                        await interaction.followup.send(
                            f"Minimum Session Rewards may only be 0, if a player receives a lesser reward, have them claim the transaction.",
                            ephemeral=True)

                    else:
                        await cursor.execute(
                            "Select Player_ID, Player_Name, Character_Name, Level, Tier, Effective_Gold, Received_Milestones, Received_Trials, Received_Gold, Received_Fame, Received_Prestige, Received_Essence, Gold_Transaction_ID FROM Sessions_Archive WHERE Session_ID = ?",
                            (session_id,))
                        session_complex = await cursor.fetchall()

                        if not session_complex:
                            await interaction.followup.send(
                                f"there are no players registered for this session.",
                                ephemeral=True)

                        else:
                            embed = discord.Embed(title="Session Adjustment Report",
                                                  description=f"a report of the session: {session_name}",
                                                  color=discord.Color.blue())

                            for idx, player in enumerate(session_complex):
                                (player_id, player_name, character_name, level, tier, effective_gold,
                                 received_milestones,
                                 received_trials, received_gold, received_fame, received_prestige, received_essence,
                                 gold_transaction_id) = player
                                response_field = f"{player_name}'s {character_name}: \r\n"

                                await cursor.execute(
                                    "SELECT True_Character_Name, milestones, trials, Fame, Prestige, Thread_ID from Player_Characters WHERE Character_Name = ? OR Nickname = ?",
                                    (character_name, character_name))
                                player_info = await cursor.fetchone()

                                if not player_info:
                                    response_field += f"Character {character_name} not found. \r\n"

                                else:
                                    (true_character_name, milestones, trials, fame, prestige, thread_id) = player_info

                                    remove_rewards = await gamemaster_commands.session_reward_reversal(
                                        interaction=interaction,
                                        session_id=session_id,
                                        character_name=character_name,
                                        author_name=gm_name,
                                        session_info=player,
                                        session_gold=rewarded_gold,
                                        source="Session Reward")

                                    if isinstance(remove_rewards, str):
                                        response_field += "failed to remove rewards, skipping adjustment. \r\n "

                                    else:
                                        (reversal_dataclass, reversal_thread_id) = remove_rewards

                                        add_rewards = await gamemaster_commands.session_reward_calculation(
                                            interaction=interaction,
                                            session_id=session_id,
                                            character_name=character_name,
                                            author_name=gm_name,
                                            pre_session_level=level,
                                            pre_session_tier=tier,
                                            pre_session_gold=effective_gold,
                                            source="Session Adjustment",
                                            session_base_info=base_session_info
                                        )

                                        if isinstance(add_rewards, str):
                                            response_field += "failed to calculate rewards, skipping adjustment. \r\n "

                                        else:
                                            (add_rewards_dataclass, add_thread_id) = add_rewards
                                            numeric_fields = ['milestone_change', 'milestones_total',
                                                              'milestones_remaining',
                                                              'trial_change', 'trials', 'trials_remaining',
                                                              'gold_change',
                                                              'essence_change', 'fame_change', 'prestige_change']

                                            for field in numeric_fields:
                                                a_value = getattr(add_rewards_dataclass, field)
                                                r_value = getattr(reversal_dataclass, field)
                                                new_value = safe_add(a_value, r_value)
                                                setattr(add_rewards_dataclass, field, new_value)

                                            await shared_functions.log_embed(
                                                change=add_rewards_dataclass,
                                                guild=guild,
                                                thread=thread_id,
                                                bot=self.bot)

                                            await shared_functions.character_embed(
                                                character_name=character_name,
                                                guild=guild)

                                            response_field += f"Rewards adjusted for {character_name}. \r\n"

                                if idx < 20:
                                    embed.add_field(
                                        name=f"{player_name}'s {character_name}",
                                        value=response_field, inline=False)

                                elif idx == 21:
                                    embed.add_field(
                                        name=f"Additional Players",
                                        value="Additional players have been adjusted, please check the session log for more information.",
                                        inline=False)

                            await interaction.followup.send(embed=embed, ephemeral=True)

            except (aiosqlite.Error, TypeError, ValueError) as e:
                logging.exception(
                    f"an error occurred for {interaction.user.name} whilst adjusting session with ID {session_id}': {e}")

                await interaction.followup.send(
                    f"An error occurred whilst adjusting session with ID '{session_id}' Error: {e}.", ephemeral=True)

    settings_group = discord.app_commands.Group(
        name='settings',
        description='Database Settings commands',
        parent=admin_group
    )

    @settings_group.command(name="ubb_inventory", description="Display a unbelievaboat player's inventory")
    async def ubb_inventory(self, interaction: discord.Interaction, player: discord.Member):
        """Display a player's inventory to identify their owned items and set the serverside items for pouches, milestones, and other"""
        guild_id = interaction.guild_id
        client = unbelievaboat.Client(os.getenv('UBB_TOKEN'))
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            shop = await client.get_inventory_items_all(guild_id, player.id)
            if shop is not None:
                embed = discord.Embed(title=f"UBB Inventory", description=f'UBB inventory',
                                      colour=discord.Colour.blurple())

                for idx, item in enumerate(shop.items):
                    if idx <= 20:
                        embed.add_field(name=f'**new item**', value=f'{item}', inline=False)
                    if idx == 21:
                        embed.add_field(name=f'**Additional Items**',
                                        value=f'Additional items exist, please narrow down the inventory for more information. Yes I could paginate this. No. I will not. Use a Dummy player with less items',
                                        inline=False)
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(f"This player does not have any items in their inventory.")
        except unbelievaboat.errors.HTTPError as e:
            logging.exception(f"An error occurred whilst trying to get the inventory for {player.name}: {e}")
            await interaction.followup.send(
                f"An error occurred whilst trying to get the inventory for {player.name}: {e}", ephemeral=True)

    @settings_group.command(name='display',
                            description='Display server settings')
    @app_commands.autocomplete(setting=shared_functions.settings_autocomplete)
    async def display(self, interaction: discord.Interaction, setting: typing.Optional[str],
                      page_number: int = 1):
        """Display server setting information. This is used to know to where key server settings are pointing to."""
        guild_id = interaction.guild_id
        await interaction.response.defer(thinking=True, ephemeral=True)

        try:
            async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as conn:
                cursor = await conn.cursor()

                # Decide which query to execute based on whether 'name' is provided
                await cursor.execute("SELECT COUNT(Search) FROM Admin")
                item_count = await cursor.fetchone()
                (item_count,) = item_count
                if setting:
                    view_type = 2
                    await cursor.execute("SELECT Identifier from Admin where Identifier = ?",
                                         (setting,))
                    setting = await cursor.fetchone()
                    if not setting:
                        await interaction.followup.send(
                            f"Character '{setting}' not found.",
                            ephemeral=True
                        )
                        return
                    else:
                        await cursor.execute(
                            "SELECT Identifier from Admin ORDER BY Identifier asc")
                        results = await cursor.fetchall()
                        offset = results.index(setting) + 1
                else:
                    view_type = 1

                # Set up pagination variables
                page_number = min(max(page_number, 1), ceil(item_count / 20))
                items_per_page = 20 if view_type == 1 else 1
                offset = (page_number - 1) * items_per_page if view_type == 1 else offset

                # Create and send the view with the results
                view = SettingDisplayView(
                    user_id=interaction.user.id,
                    guild_id=guild_id,
                    limit=items_per_page,
                    offset=offset,
                    view_type=view_type,
                    interaction=interaction
                )
                await view.send_initial_message()
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(
                f"An error occurred whilst fetching data! input values of setting: {setting}, page_number: {page_number}': {e}"
            )
            await interaction.followup.send(
                f"An error occurred whilst fetching data. Please try again later.",
                ephemeral=True
            )

    @settings_group.command(name='update',
                            description='update server settings')
    @app_commands.autocomplete(setting=shared_functions.settings_autocomplete)
    async def update_setting(self, interaction: discord.Interaction, setting: str, revision: str):
        """This allows the admin to adjust a serverside setting"""
        guild_id = interaction.guild_id
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as conn:
            cursor = await conn.cursor()

            try:
                await interaction.response.defer(thinking=True, ephemeral=True)

                if not setting:
                    await interaction.followup.send(f"cannot replace a search key with None", ephemeral=True)

                elif not revision:
                    await interaction.followup.send(f"Yeah... that would break shit, no", ephemeral=True)

                else:
                    await cursor.execute(
                        "Select Search, Type, Identifier, Description FROM Admin where Identifier = ?", (setting,))
                    information = await cursor.fetchone()

                    if information:
                        if information[1] == 'Channel':
                            # The admin setting is meant to be a discord.Channel so verify if the bot can find it. Don't make this a thread.
                            revision = int(revision)
                            channel = interaction.guild.get_channel(revision)

                            if not channel:
                                channel = await interaction.guild.fetch_channel(revision)

                            if not channel:
                                await interaction.followup.send("Error: Could not find the requested channel.",
                                                                ephemeral=True)
                                return

                        elif information[1] == 'Level':
                            # The admin setting is meant to be a level so verify if the bot can find it in the system.
                            await cursor.execute("SELECT Max(Level), Min(Level) from Milestone_System")
                            max_level = await cursor.fetchone()

                            if int(revision) > max_level[0]:
                                await interaction.followup.send(
                                    f"Your server does not have a milestone system for above level {max_level[0]}",
                                    ephemeral=True)
                                return

                            elif int(revision) < max_level[1]:
                                await interaction.followup.send(
                                    f"Your server does not have a milestone system for below level {max_level[1]}",
                                    ephemeral=True)
                                return

                        elif information[2] == 'Tier':
                            # The admin setting is meant to be a tier so verify if the bot can find it in the system.
                            await cursor.execute("SELECT Max(Tier) from AA_Trials")
                            max_tier = await cursor.fetchone()

                            if int(revision) > max_tier[0]:
                                await interaction.followup.send(
                                    f"Your server does not have a milestone system for above tier {max_tier[0]}",
                                    ephemeral=True)
                                return

                        elif information[1] == 'item':
                            # This is an item type setting, which means we either need to verify it exists in the server store (if true) or UBB
                            async with shared_functions.config_cache.lock:
                                configs = shared_functions.config_cache.cache.get(guild_id)
                                if configs:
                                    custom_store = configs.get('Use_Custom_Store')

                                if not custom_store:
                                    client = unbelievaboat.Client(os.getenv('UBB_TOKEN'))
                                    try:
                                        item = await client.get_store_item(guild_id, int(revision))

                                        if not item:
                                            await interaction.followup.send("Error: Could not find the requested item.",
                                                                            ephemeral=True)
                                            return
                                    except unbelievaboat.HTTPError as e:
                                        await interaction.followup.send(
                                            f"Error: Could not find the requested item. {e}",
                                            ephemeral=True)
                                        logging.error(f"Error: Could not find the requested item. {e}")
                                        return

                                else:
                                    await cursor.execute("Select name from rp_store_items where item_id = ?",
                                                         (revision,))
                                    item = await cursor.fetchone()
                                    if not item:
                                        await interaction.followup.send("Error: Could not find the requested item.",
                                                                        ephemeral=True)
                                        return

                        await cursor.execute("Update Admin set Search = ? WHERE identifier = ?", (revision, setting))
                        await conn.commit()
                        await shared_functions.config_cache.load_configurations(guild_id=guild_id)
                        await interaction.followup.send(f"Updated {setting} to {revision}", ephemeral=True)

                    else:
                        await interaction.followup.send(
                            'The identifier you have supplied is incorrect.',
                            ephemeral=True)

            except (aiosqlite.Error, TypeError, ValueError) as e:
                logging.exception(
                    f"An error occurred whilst updating data! input values of setting: {setting}, revision: {revision}': {e}"
                )
                await interaction.followup.send(
                    f"An error occurred whilst updating data. Please try again later.",
                    ephemeral=True
                )

    @settings_group.command()
    @app_commands.describe(certainty="is life short?")
    @app_commands.choices(
        certainty=[discord.app_commands.Choice(name='YOLO', value=1), discord.app_commands.Choice(name='No', value=2)])
    async def reset(self, interaction: discord.Interaction, certainty: discord.app_commands.Choice[int]):
        """Perform a database reset, remember to reassign role ranges and server settings!"""
        certainty_value = certainty.value
        interaction.response.defer(thinking=True)
        if certainty_value == 1:
            # Create and send the PropositionView
            content = "You gotta be like so sure about this. Super Sure. Super Duper Sure."
            view = ResetDatabaseView(content=content, interaction=interaction)
            await view.create_embed()
            await interaction.followup.send(
                content=content,
                embed=view.embed,
                view=view,
                ephemeral=True
            )

        else:
            await interaction.followup.send(f"I'M FIRING MY LAS--- What?", ephemeral=True)

    @settings_group.command(name='fame', description='Administrative commands for the fame store.')
    @app_commands.describe(modify="add, remove, or edit something in the store.")
    @app_commands.autocomplete(name=shared_functions.fame_autocomplete)
    @app_commands.choices(
        modify=[discord.app_commands.Choice(name='Add/Edit', value=1),
                discord.app_commands.Choice(name='Remove', value=2)])
    async def store_fame(self, interaction: discord.Interaction, name: str, fame_required: typing.Optional[int],
                         prestige_cost: typing.Optional[int], effect: typing.Optional[str], limit: typing.Optional[int],
                         modify: discord.app_commands.Choice[int]):
        """Add, edit, or remove items from the fame store."""
        guild_id = interaction.guild_id
        await interaction.response.defer(thinking=True, ephemeral=True)
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as conn:
            cursor = await conn.cursor()
            try:
                # Check if the item exists in the fame store
                await cursor.execute(
                    "Select Name, Fame_Required, Prestige_Cost, Use_limit, effect from Store_Fame where Name = ?",
                    (name,))
                fame_item = await cursor.fetchone()

                if modify.value == 1 and not fame_item:
                    # Add a new item to the fame store
                    if not fame_required or not prestige_cost or not effect or not limit:
                        await interaction.followup.send(
                            f"Please provide all required information for adding a new item to the fame store. \r\n "
                            f"You provided: Name: {name}, Fame required: {fame_required}, Prestige Cost: {prestige_cost}, Limit: {limit} \r\n"
                            f"EFFECT: {effect}.",
                            ephemeral=True)
                        return

                    else:
                        await cursor.execute(
                            "Insert into Store_Fame (Name, Fame_Required, Prestige_Cost, Effect, Use_Limit) VALUES (?, ?, ?, ?, ?)",
                            (name, fame_required, prestige_cost, effect, limit))
                        await conn.commit()
                        embed = discord.Embed(title="Fame Store Adjustment",
                                              description=f"adding new fame option",
                                              color=discord.Color.blue())
                        embed.add_field(name=name,
                                        value=f"Fame Required: {fame_required}, Prestige Cost: {prestige_cost}, Limit: {limit} \r\n"
                                              f"Effect: {effect}")
                        await interaction.followup.send(embed=embed, ephemeral=True)

                elif modify.value == 1 and fame_item:
                    (info_name, info_fame_required, info_prestige_cost, info_limit, info_effect) = fame_item
                    # Use default values if the user didn't provide them to edit the item
                    updated_fame_requirement = fame_required if fame_required else info_fame_required
                    updated_prestige_cost = prestige_cost if prestige_cost else info_prestige_cost
                    updated_limit = limit if limit else info_limit
                    updated_effect = effect if effect else info_effect
                    # Update the item in the fame store
                    await cursor.execute(
                        "Update Store_Fame set Name = ?, Fame_Required = ?, Prestige_Cost = ?, Effect = ?, Use_Limit = ? WHERE Name = ?",
                        (name, updated_fame_requirement, updated_prestige_cost, updated_effect, updated_limit, name))
                    embed = discord.Embed(title="Fame Store Adjustment",
                                          description=f"changing fame option",
                                          color=discord.Color.blue())
                    embed.add_field(name=name,
                                    value=f"Fame Required: {fame_required}, Prestige Cost: {prestige_cost}, Limit: {limit} \r\n"
                                          f"Effect: {effect}")
                    await interaction.followup.send(embed=embed, ephemeral=True)

                elif modify.value == 2 and fame_item:
                    # Remove the item from the fame store
                    await cursor.execute("DELETE FROM Store_Fame WHERE Name = ?",
                                         (name,))
                    await conn.commit()
                    await interaction.followup.send(f"Removed {name} from the fame store.", ephemeral=True)

                else:
                    await interaction.followup.send(
                        f"An error occurred whilst adjusting the fame store. Please ensure that the item exists and that all required fields are filled out",
                        ephemeral=True)

            except (aiosqlite.Error, TypeError, ValueError) as e:
                logging.exception(
                    f"an error occurred for {interaction.user.name} whilst adjusting fame store': {e}")
                await interaction.followup.send(
                    f"An error occurred whilst adjusting fame store. Error: {e}.", ephemeral=True)

    @settings_group.command(name='titles', description='Administrative commands for the title store.')
    @app_commands.describe(modify="add, remove, or edit something in the store.")
    @app_commands.describe(
        item_id="The item ID of the item in the store. If your system uses UBB the item needs to be in your inventory.")
    @app_commands.choices(
        modify=[discord.app_commands.Choice(name='Add/Edit', value=1),
                discord.app_commands.Choice(name='Remove', value=2)])
    async def title_store(self, interaction: discord.Interaction, masculine_name: typing.Optional[str],
                          feminine_name: typing.Optional[str],
                          fame: typing.Optional[int], effect: typing.Optional[str], item_id: typing.Optional[str],
                          modify: discord.app_commands.Choice[int] = 1):
        """Add, edit, or remove items from the fame store."""
        guild_id = interaction.guild_id
        await interaction.response.defer(thinking=True, ephemeral=True)
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as conn:
            cursor = await conn.cursor()

            try:
                await cursor.execute(
                    "Select ID, Masculine_Name, Feminine_Name, Fame, Effect from Store_Title where Masculine_Name = ? or Feminine_Name = ?",
                    (masculine_name, feminine_name))
                fame_item = await cursor.fetchone()
                modify_value = modify if isinstance(modify, int) else modify.value
                if modify_value == 1 and not fame_item:
                    # Add a new item to the fame store if it doesn't exist.
                    if not fame or not item_id or not effect or not masculine_name or not feminine_name:
                        await interaction.followup.send(
                            f"Please provide all required information for adding a new item to the fame store. \r\n "
                            f"You provided: Name: {masculine_name}/{feminine_name}, Fame bestowed: {fame}, Item_ID: {item_id}"
                            f"EFFECT: {effect}.", ephemeral=True)
                        return

                    else:
                        # Verify if the server uses the UBB inventory or the custom store
                        async with shared_functions.config_cache.lock:
                            configs = shared_functions.config_cache.cache.get(guild_id)
                            if configs:
                                custom_store = configs.get('Use_Custom_Store')
                            if not custom_store:
                                item_evaluation = await character_commands.ubb_inventory_check(
                                    guild_id=guild_id,
                                    item_id=item_id,
                                    author_id=interaction.user.id,
                                    amount=1
                                )
                            else:

                                await cursor.execute("Select name from rp_store_items where item_id = ?", (item_id,))
                                item = await cursor.fetchone()

                                item_evaluation = 0 if not item else 1

                            if item_evaluation > 0:
                                await cursor.execute(
                                    "Insert into Store_Title (ID, Masculine_Name, Feminine_Name, fame, Effect) VALUES (?, ?, ?, ?, ?)",
                                    (item_id, masculine_name, feminine_name, fame, effect))
                                await conn.commit()
                                embed = discord.Embed(title="Title Store Adjustment",
                                                      description=f"Title Store Adjustment",
                                                      color=discord.Color.blue())
                                embed.add_field(name="Titles:", value=f"Updated Name: {masculine_name}/{feminine_name}")
                                embed.add_field(name="Fame:", value=f"Fame bestowed: {fame}")
                                embed.add_field(name="Item_ID:", value=f"Item_ID: {item_id}")
                                await interaction.followup.send(embed=embed, ephemeral=True)

                            else:
                                await interaction.followup.send(
                                    f"Item_ID: {item_id} not found in the inventory.",
                                    ephemeral=True)

                elif modify_value == 1 and fame_item:
                    # Fame item was found, so update it instead of adding a new one.
                    (info_id, info_masculine_name, info_feminine_name, info_fame, info_effect) = fame_item
                    updated_fame = fame if fame else info_fame
                    updated_ubb_id = item_id if item_id else info_id
                    updated_effect = effect if effect else info_effect
                    updated_masculine_name = masculine_name if masculine_name else info_masculine_name
                    updated_feminine_name = feminine_name if feminine_name else info_feminine_name

                    # Verify if the server uses the UBB inventory or the custom store
                    async with shared_functions.config_cache.lock:
                        configs = shared_functions.config_cache.cache.get(guild_id)
                        if configs:
                            custom_store = configs.get('Use_Custom_Store')

                        if not custom_store:
                            item_evaluation = await character_commands.ubb_inventory_check(
                                guild_id=guild_id,
                                item_id=item_id,
                                author_id=interaction.user.id,
                                amount=1
                            )

                        else:
                            await cursor.execute("Select name from rp_store_items where item_id = ?", (item_id,))
                            item = await cursor.fetchone()
                            item_evaluation = 0 if not item else 1

                    if item_evaluation > 0:
                        await cursor.execute(
                            "Update Store_Title set ID = ?, Masculine_Name = ?, Feminine_Name = ?, Fame = ?, Effect = ? WHERE ID = ?",
                            (
                                updated_ubb_id, updated_masculine_name, updated_feminine_name, updated_fame,
                                updated_effect,
                                info_id))
                        await conn.commit()

                        if masculine_name:
                            await cursor.execute("SELECT Character_Name FROM Player_Characters WHERE title = ?",
                                                 (info_masculine_name,))
                            masculine_characters = await cursor.fetchall()

                            await cursor.execute("Update Player_Characters SET title = ? WHERE title = ?",
                                                 (masculine_name, info_masculine_name))
                            await conn.commit()

                            for character in masculine_characters:
                                (character_name,) = character
                                await shared_functions.character_embed(
                                    character_name=character_name,
                                    guild=interaction.guild)

                        if feminine_name:
                            await cursor.execute("SELECT Character_Name FROM Player_Characters WHERE title = ?",
                                                 (info_feminine_name,))
                            feminine_characters = await cursor.fetchall()

                            await cursor.execute("Update Player_Characters SET title = ? WHERE title = ?",
                                                 (feminine_name, info_feminine_name))
                            await conn.commit()

                            for character in feminine_characters:
                                (character_name,) = character
                                await shared_functions.character_embed(
                                    character_name=character_name,
                                    guild=interaction.guild)

                        embed = discord.Embed(
                            title="Title Store Adjustment",
                            description=f"Title Store Adjustment",
                            color=discord.Color.blue())
                        embed.add_field(name="Titles:",
                                        value=f"Updated Name: {updated_masculine_name}/{updated_feminine_name}")
                        embed.add_field(name="Fame:", value=f"Fame bestowed: {updated_fame}")
                        embed.add_field(name="Item_ID:", value=f"Item_ID: {updated_ubb_id}")
                        await interaction.followup.send(embed=embed, ephemeral=True)

                    else:
                        await interaction.followup.send(
                            f"Item_ID: {item_id} not found in inventory.",
                            ephemeral=True)

                elif modify_value == 2 and fame_item:
                    # CAST THE ITEM INTO THE FIRES OF MOUNT DOOM
                    (info_id, info_masculine_name, info_feminine_name, info_fame, info_effect) = fame_item
                    await cursor.execute("DELETE FROM Store_Title WHERE Masculine_Name = ?",
                                         (info_masculine_name,))
                    await conn.commit()
                    await interaction.followup.send(
                        f"Removed {info_masculine_name}/{info_feminine_name} from the fame store.")

                else:
                    await interaction.followup.send(
                        f"An error occurred whilst adjusting the title store. Please ensure that the item exists and that all required fields are filled out",
                        ephemeral=True)

            except (aiosqlite.Error, TypeError, ValueError) as e:
                logging.exception(
                    f"an error occurred for {interaction.user.name} whilst adjusting title store': {e}")
                await interaction.followup.send(
                    f"An error occurred whilst adjusting title store. Error: {e}.", ephemeral=True)

    level_group = discord.app_commands.Group(
        name='level',
        description='Update the level, WPL, and other information in the milestone system',
        parent=admin_group
    )

    @character_group.command(name="milestones",
                             description="commands for adding or removing milestones from a character")
    @app_commands.autocomplete(character_name=shared_functions.character_select_autocompletion)
    @app_commands.describe(job='What kind of job you are adding')
    @app_commands.choices(
        job=[discord.app_commands.Choice(name='Easy', value=1), discord.app_commands.Choice(name='Medium', value=2),
             discord.app_commands.Choice(name='Hard', value=3), discord.app_commands.Choice(name='Deadly', value=4),
             discord.app_commands.Choice(name='None', value=5)])
    @app_commands.describe(level="The character level for the adjustment: Default at 0 to use current level.")
    async def adjust_milestones(self, interaction: discord.Interaction, character_name: str, amount: int,
                                job: discord.app_commands.Choice[int], level: typing.Optional[int],
                                misc_milestones: int = 0):
        """Adjusts the milestone number a PC has."""
        _, unidecode_name = name_fix(character_name)
        guild_id = interaction.guild_id
        guild = interaction.guild
        await interaction.response.defer(thinking=True, ephemeral=True)
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as conn:
            cursor = await conn.cursor()
            try:

                if amount == 0 and misc_milestones == 0:
                    await interaction.followup.send("No Change in Milestones!", ephemeral=True)

                elif job == 'None' and misc_milestones == 0:
                    await interaction.followup.send("No Change in Milestones!", ephemeral=True)

                else:
                    await cursor.execute(
                        "Select True_Character_Name, Character_Name, Thread_ID, Level, Milestones, Tier, Trials, Personal_Cap, Region FROM Player_Characters where Character_Name = ? OR Nickname = ?",
                        (unidecode_name, unidecode_name))
                    player_info = await cursor.fetchone()
                    if not player_info:
                        await interaction.followup.send(f"There is no player character with this name or nickname.",
                                                        ephemeral=True)
                    if player_info:
                        (true_character_name, character_name, thread_id, character_level, milestones, tier, trials,
                         personal_cap, region) = player_info
                        # Determine the level to use for the calculation, default to the character's current level and default jobs to None
                        character_level = level if level is not None else character_level
                        easy = amount if job.name == 'Easy' else 0
                        medium = amount if job.name == 'Medium' else 0
                        hard = amount if job.name == 'Hard' else 0
                        deadly = amount if job.name == 'Deadly' else 0

                        # Calculate the new level and milestones
                        level_adjustment = await character_commands.level_calculation(
                            character_name=character_name,
                            level=character_level,
                            guild=guild,
                            guild_id=guild_id,
                            personal_cap=personal_cap,
                            base=milestones,
                            easy=easy,
                            medium=medium,
                            hard=hard,
                            deadly=deadly,
                            misc=misc_milestones,
                            region=region)
                        print(level_adjustment)
                        (new_level,
                         total_milestones,
                         min_milestones,
                         milestones_to_level,
                         milestones_required,
                         awarded_total_milestones) = level_adjustment

                        # Calculate the new tier, as a level can change breakpoints.
                        mythic_adjustment = await character_commands.mythic_calculation(
                            guild_id=guild_id,
                            character_name=character_name,
                            level=new_level,
                            trials=trials,
                            trial_change=0,
                            tier=tier)
                        (new_tier, total_trials, trials_required, trial_change) = mythic_adjustment

                        # Create the dataclasses for the changes and log it.
                        character_changes = shared_functions.CharacterChange(
                            character_name=character_name,
                            author=interaction.user.name,
                            level=new_level,
                            milestones_total=total_milestones,
                            milestone_change=awarded_total_milestones,
                            milestones_remaining=min_milestones,
                            source=f"admin adjusted milestones by {amount} for {character_name}")
                        character_updates = shared_functions.UpdateCharacterData(
                            character_name=character_name,
                            level_package=(new_level, total_milestones, milestones_to_level),
                        )
                        if new_tier != tier:
                            character_updates.trial_package = (new_tier, total_trials, trials_required)
                            character_changes.tier = new_tier
                            character_changes.trials = total_trials
                            character_changes.trials_remaining = trials_required
                            character_changes.trial_change = 0

                        # Update the character and log the changes
                        await shared_functions.update_character(guild_id=guild_id, change=character_updates)

                        character_log = await shared_functions.log_embed(
                            change=character_changes,
                            guild=guild,
                            thread=thread_id,
                            bot=self.bot)
                        await shared_functions.character_embed(
                            character_name=character_name,
                            guild=guild)
                        await interaction.followup.send(
                            embed=character_log,
                            content=f"milestone changes for {character_name} have been made.",
                            ephemeral=True)
            except (aiosqlite.Error, TypeError, ValueError, character_commands.CalculationAidFunctionError) as e:
                logging.exception(
                    f"an error occurred for {interaction.user.name} whilst adjusting milestones for {character_name}': {e}")
                await interaction.followup.send(
                    f"An error occurred whilst adjusting milestones for '{character_name}' Error: {e}.",
                    ephemeral=True)

    @level_group.command(name='cap', description='command for adjusting the level cap of the server')
    async def level_cap(self, interaction: discord.Interaction, new_level: int):
        """This allows the admin to adjust the server wide level cap"""
        guild_id = interaction.guild_id
        guild = interaction.guild
        await interaction.response.defer(thinking=True, ephemeral=True)
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as conn:
            cursor = await conn.cursor()
            try:
                await cursor.execute("SELECT MIN(level), MAX(level) from Milestone_System")
                level_minmax = await cursor.fetchone()
                if new_level < level_minmax[0]:
                    await interaction.followup.send(
                        f"Your server does not have a milestone system for below level {level_minmax[0]}",
                        ephemeral=True)
                elif new_level > level_minmax[1]:
                    await interaction.followup.send(
                        f"Your server does not have a milestone system for above level {level_minmax[1]}",
                        ephemeral=True)
                else:
                    await cursor.execute("Select minimum_milestones FROM Milestone_System where Level = ?",
                                         (new_level,))
                    new_level_info = await cursor.fetchone()
                    if new_level_info:
                        minimum_milestones = new_level_info[0]
                        # Update the level cap in the database
                        await cursor.execute("Update Admin set Search = ? WHERe Identifier = 'Level_Cap'", (new_level,))
                        await conn.commit()
                        # Reset the cache to apply the new level cap.
                        await shared_functions.config_cache.load_configurations(guild_id=guild_id)
                        await cursor.execute(
                            "SELECT True_Character_Name, Character_Name, Level, Milestones, Tier, Trials, personal_cap, Thread_ID, region, Player_ID FROM Player_Characters WHERE Milestones >= ?",
                            (minimum_milestones,))
                        characters_to_adjust = await cursor.fetchall()
                        if characters_to_adjust:
                            cap_embed = discord.Embed(title=f"Level Cap Adjustment",
                                                      description=f'{interaction.user.name} Adjusting the level cap to {new_level}')
                            for idx, character in enumerate(characters_to_adjust):
                                # Calculate the new level and tier for each character that had their level cap increased.
                                try:
                                    (true_character_name, character_name, character_level, milestones, tier, trials,
                                     personal_cap, thread_id, region, player_id) = character
                                    level_adjustment = await character_commands.level_calculation(
                                        character_name=character_name,
                                        level=character_level,
                                        guild=guild,
                                        guild_id=guild_id,
                                        personal_cap=personal_cap,
                                        base=milestones,
                                        easy=0,
                                        medium=0,
                                        hard=0,
                                        deadly=0,
                                        misc=0,
                                        region=region,
                                        author_id=player_id)
                                    (new_level,
                                     total_milestones,
                                     min_milestones,
                                     milestones_to_level,
                                     milestones_required,
                                     awarded_total_milestones) = level_adjustment

                                    mythic_adjustment = await character_commands.mythic_calculation(
                                        guild_id=guild_id,
                                        character_name=character_name,
                                        level=new_level,
                                        trials=trials,
                                        trial_change=0,
                                        tier=tier)
                                    (new_tier, total_trials, trials_required, trial_change) = mythic_adjustment

                                    # Create the dataclasses for the changes and log it.
                                    character_updates = shared_functions.UpdateCharacterData(
                                        character_name=character_name,
                                        level_package=(new_level, total_milestones, milestones_to_level),
                                    )

                                    character_changes = shared_functions.CharacterChange(
                                        character_name=character_name,
                                        author=interaction.user.name,
                                        level=new_level,
                                        milestones_total=total_milestones,
                                        milestone_change=awarded_total_milestones,
                                        milestones_remaining=min_milestones,
                                        source=f"admin adjusted level cap to {new_level}")

                                    if new_tier != tier:
                                        character_updates.trial_package = (new_tier, total_trials, trials_required)
                                        character_changes.tier = new_tier
                                        character_changes.trials = total_trials
                                        character_changes.trials_remaining = trials_required
                                        character_changes.trial_change = 0

                                    await shared_functions.update_character(
                                        guild_id=guild_id,
                                        change=character_updates
                                    )

                                    await shared_functions.log_embed(
                                        change=character_changes,
                                        guild=guild,
                                        thread=thread_id, bot=self.bot)

                                    await shared_functions.character_embed(
                                        character_name=character_name,
                                        guild=guild)

                                    if idx <= 20:
                                        # Add the character to the embed if there are less than 20 characters adjusted.
                                        cap_embed.add_field(
                                            name=f"{true_character_name}",
                                            value=f"{true_character_name} has been leveled up to {new_level}.",
                                            inline=False)

                                    elif idx == 21:
                                        # Add a field for additional characters if there are more than 20 characters adjusted. There is a limit of 25 otherwise.
                                        additional_characters = true_character_name

                                    else:
                                        additional_characters += f", {true_character_name}"

                                except (aiosqlite.Error, TypeError, ValueError) as e:
                                    logging.exception(
                                        f"An error occurred whilst looping level cap! input values of: {new_level}, {true_character_name} in server {interaction.guild.id} by {interaction.user.name}: {e}"
                                    )

                            if idx >= 21:
                                # Add the additional characters to the embed if there are more than 20 characters adjusted.
                                cap_embed.add_field(name=f"Additional Characters",
                                                    value=f"{idx} additional characters have been adjusted.\r\n{additional_characters}",
                                                    inline=False)
                            await interaction.followup.send(embed=cap_embed, ephemeral=True)
                            logging.info(
                                f"{interaction.user.name} has adjusted the tier cap to {new_level} for {guild.name} with {idx} characters adjusted.")

                        else:
                            await interaction.followup.send(
                                f"You have increased your cap to {new_level}! However your server does not have any characters that meet the minimum milestone requirement it!",
                                ephemeral=True)

                    else:
                        await interaction.followup.send(
                            f"Your server does not have a milestone system for level {new_level}", ephemeral=True)

            except (aiosqlite.Error, TypeError, ValueError) as e:
                logging.exception(
                    f"An error occurred whilst updating level cap! input values of: {new_level} in server {interaction.guild.id} by {interaction.user.name}': {e}"
                )

                await interaction.followup.send(
                    f"An error occurred whilst fetching data. Please try again later.",
                    ephemeral=True
                )

    @level_group.command(name='milestones',
                         description='command for adjusting the milestone floor of a level among other things.')
    @app_commands.describe(
        level="The level you wish to adjust the milestone floor for or to add a new level into the range.")
    @app_commands.describe(
        minimum_milestones="The minimum number of milestones required to reach the level. Set as -1 to delete the level.")
    async def define_milestone(self, interaction: discord.Interaction, level: int, minimum_milestones: int):
        """This allows the admin to adjust the milestone floor of a level among other things."""
        guild_id = interaction.guild_id
        await interaction.response.defer(thinking=True, ephemeral=True)
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as conn:
            cursor = await conn.cursor()
            try:
                await cursor.execute("SELECT MIN(LEVEL), MAX(LEVEL) from Milestone_System")
                level_minmax = await cursor.fetchone()

                if level < level_minmax[0] - 1:
                    await interaction.followup.send(
                        f"Your minimum server level was {level_minmax[0]} You cannot add levels which break the sequence!",
                        ephemeral=True)
                    return

                elif level > level_minmax[1] + 1:
                    await interaction.followup.send(
                        f"Your maximum server level was {level_minmax[1]}! You cannot add numbers which break the sequence!",
                        ephemeral=True)
                    return

                await cursor.execute(
                    "SELECT level, minimum_milestones, wpl, wpl_heroic FROM Milestone_System WHERE Level = ?",
                    (level - 1,))
                lower_level_info = await cursor.fetchone()

                await cursor.execute("SELECT level, minimum_milestones FROM Milestone_System WHERE Level = ?", (level,))
                center_level_info = await cursor.fetchone()

                await cursor.execute(
                    "SELECT level, minimum_milestones, wpl, wpl_heroic FROM Milestone_System WHERE Level = ?",
                    (level + 1,))
                higher_level_info = await cursor.fetchone()

                if lower_level_info:

                    # found lower level, need to adjust it to account for potential removal of the upper level, or catch other changes.
                    if minimum_milestones == -1:
                        lower_milestones_required = 999999 if not higher_level_info else higher_level_info[1] - \
                                                                                         lower_level_info[1]
                    else:
                        (lower_level, lower_milestones, wpl, wpl_heroic) = lower_level_info
                        lower_milestones_required = minimum_milestones - lower_milestones

                        if lower_milestones_required < 0:
                            await interaction.followup.send(
                                f"Your input of level: {level} minimum_milestones: {minimum_milestones} cannot be less than level: {lower_level} minimum_milestones: {lower_milestones}.",
                                ephemeral=True)
                            return
                    await cursor.execute("UPDATE Milestone_System SET milestones_to_level = ? WHERE Level = ?",
                                         (lower_milestones_required, lower_level_info[0]))
                    await conn.commit()

                if higher_level_info:
                    # found higher level, need to adjust it to account for potential removal of the lower level, or catch other changes.
                    (higher_level, higher_milestones, wpl, wpl_heroic) = higher_level_info

                    if minimum_milestones > higher_milestones:
                        await interaction.followup.send(
                            f"Your input of level: {level} minimum_milestones: {minimum_milestones} cannot be more than level: {higher_level} minimum_milestones: {higher_milestones}.",
                            ephemeral=True)
                        return
                    center_milestones_required = higher_milestones - minimum_milestones

                else:
                    # no higher level available, make this crazy high.
                    center_milestones_required = 999999

                if center_level_info:
                    if minimum_milestones == -1:
                        await cursor.execute("DELETE FROM Milestone_System WHERE Level = ?", (level,))
                        await conn.commit()

                        if level > 0:
                            await cursor.execute("UPDATE Milestones_System SET level = level - 1 where level > ?",
                                                 (level,))
                        else:
                            await cursor.execute("UPDATE Milestones_System SET level = level + 1 where level < ?",
                                                 (level,))
                        await conn.commit()

                        await interaction.followup.send(f"Level of {level} removed from milestone system.",
                                                        ephemeral=True)
                    else:
                        await cursor.execute("UPDATE Milestone_System SET milestones_to_level = ? WHERE Level = ?",
                                             (center_milestones_required, level))
                        await interaction.followup.send(f"Level of {level} updated in milestone system.",
                                                        ephemeral=True)
                else:
                    wpl = higher_level_info[2] - 1 if not lower_level_info else lower_level_info[2] + 1
                    wpl_heroic = higher_level_info[3] - 1 if not lower_level_info else lower_level_info[3] + 1
                    await cursor.execute(
                        "INSERT INTO Milestone_System (Level, Minimum_Milestones, milestones_to_level, WPL, WPL_Heroic) VALUES (?, ?, ?, ?, ?)",
                        (level, minimum_milestones, center_milestones_required, wpl, wpl_heroic))
                    await interaction.followup.send(
                        f"Level of {level} added to milestone system. PLEASE REMEMBER TO UPDATE WPL VALUES.",
                        ephemeral=True)

                await conn.commit()
                center_milestones_range = minimum_milestones if minimum_milestones != -1 else center_level_info[1]
                upper_milestone_range = 999999 if not higher_level_info else higher_level_info[1]

                # Update all characters that are affected by the milestone change.
                await cursor.execute(
                    "Select character_name, level, milestones, trials, personal_cap, Tier, Thread_ID, Region FROM Player_Characters WHERE milestones BETWEEN ? AND ?",
                    (center_milestones_range, upper_milestone_range))
                characters_to_adjust = await cursor.fetchall()

                for character in characters_to_adjust:
                    (character_name, level, milestones, trials, personal_cap, tier, thread_id, region) = character
                    level_adjustment = await character_commands.level_calculation(
                        character_name=character_name,
                        level=level,
                        guild=interaction.guild,
                        guild_id=guild_id,
                        personal_cap=personal_cap,
                        base=milestones,
                        easy=0,
                        medium=0,
                        hard=0,
                        deadly=0,
                        misc=0,
                        region=region)
                    (new_level,
                     total_milestones,
                     min_milestones,
                     milestones_to_level,
                     milestones_required,
                     awarded_total_milestones) = level_adjustment
                    mythic_adjustment = await character_commands.mythic_calculation(
                        guild_id=guild_id,
                        character_name=character_name,
                        level=new_level,
                        trials=trials,
                        trial_change=0,
                        tier=tier)
                    (new_tier, total_trials, trials_required, trial_change) = mythic_adjustment

                    # Create the dataclasses for the changes and log it.
                    character_updates = shared_functions.UpdateCharacterData(
                        character_name=character_name,
                        level_package=(new_level, total_milestones, milestones_to_level),
                    )
                    character_changes = shared_functions.CharacterChange(
                        character_name=character_name,
                        author=interaction.user.name,
                        level=new_level,
                        milestones_total=total_milestones,
                        milestone_change=awarded_total_milestones,
                        milestones_remaining=min_milestones,
                        source=f"admin adjusted level cap to {new_level}")

                    if new_tier != tier:
                        character_updates.trial_package = (new_tier, total_trials, trials_required)
                        character_changes.tier = new_tier
                        character_changes.trials = total_trials
                        character_changes.trials_remaining = trials_required
                        character_changes.trial_change = 0

                    await shared_functions.update_character(
                        guild_id=guild_id,
                        change=character_updates
                    )

                    await shared_functions.log_embed(
                        change=character_changes,
                        guild=interaction.guild,
                        thread=thread_id, bot=self.bot)

                    await shared_functions.character_embed(
                        character_name=character_name,
                        guild=interaction.guild)

            except (aiosqlite.Error, TypeError, ValueError) as e:
                logging.exception(
                    f"An error occurred whilst milestones! input values of: level: {level}, minimum_milestones {minimum_milestones} in server {interaction.guild.id} by {interaction.user.name}': {e}"
                )
                await interaction.followup.send(
                    f"An error occurred whilst fetching data. Please try again later.",
                    ephemeral=True
                )

    @level_group.command(name='wpl',
                         description='command for adjusting the wealth per level and heroic WPL of a level.')
    async def define_wpl(self, interaction: discord.Interaction, level: int, wpl: int, wpl_heroic: int):
        """This allows the admin to adjust the milestone floor of a level among other things."""
        guild_id = interaction.guild_id
        await interaction.response.defer(thinking=True, ephemeral=True)
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as conn:
            cursor = await conn.cursor()
            try:
                await cursor.execute("SELECT Level, WPL, WPL_Heroic FROM Milestone_System WHERE Level = ?", (level,))
                center_level_info = await cursor.fetchone()

                if center_level_info:
                    # found center level, so we update it.
                    await cursor.execute("SELECT Level, WPL, WPL_Heroic FROM Milestone_System WHERE Level = ?",
                                         (level - 1,))
                    lower_level_info = await cursor.fetchone()
                    await cursor.execute("SELECT Level, WPL, WPL_Heroic FROM Milestone_System WHERE Level = ?",
                                         (level + 1,))
                    higher_level_info = await cursor.fetchone()

                    if lower_level_info:
                        (lower_level, lower_wpl, lower_wpl_heroic) = lower_level_info
                        if wpl < lower_wpl or wpl_heroic < lower_wpl_heroic:
                            await interaction.followup.send(
                                f"Your input of level: {level} WPL: {wpl} wpl_heroic: {wpl_heroic} cannot be less than level: {lower_level} WPL: {lower_wpl} Heroic WPL: {lower_wpl_heroic}.",
                                ephemeral=True)
                            return

                    if higher_level_info:
                        # Found higher level, we cannot have a lower level with a higher WPL as that can fuck with things.
                        (higher_level, higher_wpl, higher_wpl_heroic) = higher_level_info
                        if wpl > higher_wpl or wpl_heroic < higher_wpl_heroic:
                            await interaction.followup.send(
                                f"Your input of level: {level} WPL: {wpl} wpl_heroic: {wpl_heroic} cannot be less than level: {higher_level} WPL: {higher_wpl} Heroic WPL: {higher_wpl_heroic}.",
                                ephemeral=True)
                            return

                    await cursor.execute("UPDATE Milestone_System SET WPL = ?, WPL_Heroic = ? WHERE Level = ?",
                                         (wpl, wpl_heroic, level))
                    await conn.commit()

                    await interaction.followup.send(
                        f"Level of {level} updated in milestone system. WPL: {wpl} Heroic WPL: {wpl_heroic}",
                        ephemeral=True)

                else:
                    await interaction.followup.send(
                        f"Your server does not have a milestone system for level {level}", ephemeral=True)

            except (aiosqlite.Error, TypeError, ValueError) as e:
                logging.exception(
                    f"An error occurred whilst milestones! input values of: level: {level}, WPL: {wpl}, WPL_Heroic {wpl_heroic} in server {interaction.guild.id} by {interaction.user.name}': {e}"
                )
                await interaction.followup.send(
                    f"An error occurred whilst fetching data. Please try again later.",
                    ephemeral=True
                )

    @level_group.command(name='jobs', description='command for adjusting the job rewards for a session.')
    async def define_jobs(self, interaction: discord.Interaction, level: int, easy: typing.Optional[int],
                          medium: typing.Optional[int], hard: typing.Optional[int], deadly: typing.Optional[int]):
        """This allows the admin to adjust the milestone floor of a level among other things."""
        guild_id = interaction.guild_id
        await interaction.response.defer(thinking=True, ephemeral=True)
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as conn:
            cursor = await conn.cursor()

            try:
                await cursor.execute("SELECT easy, medium, hard, deadly FROM Milestone_System WHERE Level = ?",
                                     (level,))
                level_info = await cursor.fetchone()

                if level_info:
                    # found level, so we update it.
                    (info_easy, info_medium, info_hard, info_deadly) = level_info
                    new_easy = easy if easy is not None else info_easy
                    new_medium = medium if medium is not None else info_medium
                    new_hard = hard if hard is not None else info_hard
                    new_deadly = deadly if deadly is not None else info_deadly

                    if new_easy < 0 or new_medium < 0 or new_hard < 0 or new_deadly < 0:
                        await interaction.followup.send(
                            "Why do you hate your players so fucking much that you want to have them get a negative reward on a job?!",
                            ephemeral=True)

                    elif new_easy > new_medium or new_medium > new_hard or new_hard > new_deadly:
                        await interaction.followup.send(
                            f"Please give your players higher rewards on more punishing jobs. the punishment is the job. \r\n Easy: {new_easy}, Medium: {new_medium}, Hard: {new_hard}, Deadly: {new_deadly}",
                            ephemeral=True)

                    else:
                        await cursor.execute(
                            "Update Milestone_System SET Easy = ?, Medium = ?, Hard = ?, Deadly = ? where level = ?",
                            (new_easy, new_medium, new_hard, new_deadly, level))
                        await conn.commit()
                        await interaction.followup.send(
                            f"Successfully updated level: {level} to have the following rewards \r\n Easy: {new_easy}, Medium: {new_medium}, Hard: {new_hard}, Deadly: {new_deadly}",
                            ephemeral=True)

                else:
                    await interaction.followup.send(f"Your server does not have a milestone system for level {level}",
                                                    ephemeral=True)

            except (aiosqlite.Error, TypeError, ValueError) as e:
                logging.exception(
                    f"An error occurred whilst milestones! input values of: level: {level}, easy: {easy}, medium: {medium}, hard: {hard}, deadly: {deadly} in server {interaction.guild.id} by {interaction.user.name}': {e}"
                )
                await interaction.followup.send(
                    f"An error occurred whilst fetching data. Please try again later.",
                    ephemeral=True
                )

    @level_group.command(
        name='level_range',
        description='Adjust the stored level ranges of levels in the server.'
    )
    #    @checks.has_permissions(administrator=True)
    async def level_range(
            self,
            interaction: discord.Interaction,
            min_level: int,
            max_level: int,
            role: discord.Role
    ):
        """Allows the admin to adjust the associated levels with a role."""
        await interaction.response.defer(thinking=True, ephemeral=True)

        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as conn:
                cursor = await conn.cursor()
                await cursor.execute("SELECT MIN(level), MAX(level) FROM Milestone_System")
                level_minmax = await cursor.fetchone()

                if min_level < level_minmax[0] or max_level > level_minmax[1]:
                    await interaction.followup.send(
                        f"Your server does not support levels below {level_minmax[0]} or above {level_minmax[1]}.",
                        ephemeral=True
                    )
                    return

                # Fetch existing level ranges that overlap with the new range
                await cursor.execute(
                    "SELECT DISTINCT Level_Range_ID FROM Milestone_System WHERE Level BETWEEN ? AND ?",
                    (min_level, max_level)
                )
                level_ranges = await cursor.fetchall()

                # Prepare progress message
                progress_message = await interaction.followup.send(
                    "Processing level range adjustments...",
                    ephemeral=True
                )

                # Remove roles from players who no longer qualify
                if level_ranges:
                    for level_range in level_ranges:
                        level_range_id = level_range[0]
                        await cursor.execute(
                            "SELECT MIN(Level), MAX(Level) FROM Milestone_System WHERE Level_Range_ID = ?",
                            (level_range_id,)
                        )
                        range_level = await cursor.fetchone()
                        evaluate_range_lower = range_level[0] < min_level if range_level[0] else False
                        evaluate_range_upper = range_level[1] > max_level if range_level[1] else False
                        if evaluate_range_lower or evaluate_range_upper:
                            # Fetch players to remove the role from
                            await cursor.execute(
                                """
                                SELECT DISTINCT Player_ID
                                FROM player_characters
                                WHERE Level BETWEEN ? AND ?
                                AND Level NOT BETWEEN ? AND ?
                                """,
                                (range_level[0], range_level[1], min_level, max_level)
                            )
                            players_to_remove = await cursor.fetchall()
                            players_to_remove_list = [player[0] for player in players_to_remove]

                            total_players = len(players_to_remove_list)
                            processed_count = 0

                            for player_id in players_to_remove_list:
                                remove_role = interaction.guild.get_role(level_range_id)
                                if not remove_role:
                                    logging.warning(
                                        f"Role with ID {level_range_id} not found in guild {interaction.guild.id}")
                                    continue

                                member = interaction.guild.get_member(player_id)
                                if not member:
                                    logging.warning(
                                        f"Member with ID {player_id} not found in guild {interaction.guild.id}")
                                    continue

                                try:
                                    await member.remove_roles(remove_role)
                                except discord.DiscordException as e:
                                    logging.error(f"Failed to remove role {remove_role.name} from {member.name}: {e}")

                                processed_count += 1
                                if processed_count % 10 == 0 or processed_count == total_players:
                                    progress_bar = create_progress_bar(processed_count, total_players)
                                    await progress_message.edit(content=f"Removing roles...\n{progress_bar}")

                # Update the Milestone_System table with the new range
                await cursor.execute(
                    "UPDATE Milestone_System SET Level_Range_Name = ?, Level_Range_ID = ? WHERE Level BETWEEN ? AND ?",
                    (role.name, role.id, min_level, max_level)
                )

                await conn.commit()

                # Assign the role to players who now meet the new requirements
                await cursor.execute(
                    "SELECT DISTINCT Player_ID FROM player_characters WHERE Level BETWEEN ? AND ?",
                    (min_level, max_level)
                )
                players = await cursor.fetchall()
                players_to_add_list = [player[0] for player in players]

                total_players = len(players_to_add_list)
                processed_count = 0

                for player_id in players_to_add_list:
                    member = interaction.guild.get_member(player_id)
                    if not member:
                        logging.warning(f"Member with ID {player_id} not found in guild {interaction.guild.id}")
                        continue

                    try:
                        await member.add_roles(role)
                    except discord.DiscordException as e:
                        logging.error(f"Failed to add role {role.name} to {member.name}: {e}")

                    processed_count += 1
                    if processed_count % 10 == 0 or processed_count == total_players:
                        progress_bar = create_progress_bar(processed_count, total_players)
                        await progress_message.edit(content=f"Assigning roles...\n{progress_bar}")

                # Final update
                await progress_message.edit(content="Level range adjustments complete.")


        except Exception as e:
            logging.exception(
                f"An error occurred while adjusting level ranges: {e}"
            )
            await interaction.followup.send(
                "An error occurred while adjusting level ranges. Please try again later.",
                ephemeral=True
            )

    @level_range.error
    async def level_range_error(self, interaction: discord.Interaction, error):
        if isinstance(error, checks.MissingPermissions):
            await interaction.response.send_message(
                "You do not have permission to use this command.",
                ephemeral=True
            )
        else:
            logging.exception(f"An error occurred in level_range command: {error}")
            await interaction.response.send_message(
                "An unexpected error occurred. Please contact the administrator.",
                ephemeral=True
            )

    @level_group.command(name='display',
                         description='Display milestone settings')
    async def display_milestones(self, interaction: discord.Interaction, page_number: int = 1):
        """Display Milestone Information and further context about levels."""
        guild_id = interaction.guild_id
        await interaction.response.defer(thinking=True, ephemeral=True)

        try:
            async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as conn:
                cursor = await conn.cursor()

                # Decide which query to execute based on whether 'name' is provided
                await cursor.execute("SELECT COUNT(level) FROM Milestone_System")
                item_count = await cursor.fetchone()
                item_count = item_count[0]

                # Set up pagination variables
                page_number = min(max(page_number, 1), ceil(item_count / 20))
                items_per_page = 20
                offset = (page_number - 1) * items_per_page

                # Create and send the view with the results
                view = MilestoneDisplayView(
                    user_id=interaction.user.id,
                    guild_id=guild_id,
                    limit=items_per_page,
                    offset=offset,
                    interaction=interaction
                )
                await view.update_results()
                await view.create_embed()
                await interaction.followup.send(embed=view.embed, view=view, ephemeral=True)

        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(
                f"an error occurred displaying milestones: {e}"
            )
            await interaction.followup.send(
                f"An error occurred whilst fetching data. Please try again later.",
                ephemeral=True
            )

    mythic_group = discord.app_commands.Group(
        name='mythic',
        description='Update the Mythic Trials required and other information in the mythic system',
        parent=admin_group
    )

    @character_group.command(name="trials",
                             description="commands for adding or removing mythic trials from a character")
    @app_commands.autocomplete(character_name=shared_functions.character_select_autocompletion)
    async def trial_adjustment(self, interaction: discord.Interaction, character_name: str, amount: int):
        """Adjust the number of Mythic Trials a character possesses"""
        _, unidecode_name = name_fix(character_name)
        guild_id = interaction.guild_id
        guild = interaction.guild
        await interaction.response.defer(thinking=True, ephemeral=True)
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as conn:
            cursor = await conn.cursor()

            try:

                await cursor.execute(
                    "Select True_Character_Name, Character_Name, Level, Tier, Trials, Thread_ID  FROM Player_Characters where Character_Name = ? OR Nickname = ?",
                    (character_name, character_name))
                player_info = await cursor.fetchone()

                if amount == 0:
                    await interaction.followup.send(f"No changes to trial total required.", ephemeral=True)

                else:
                    if not player_info:
                        await interaction.followup.send(
                            f"there is no {character_name} registered.", ephemeral=True)

                    else:
                        (true_character_name, character_name, character_level, tier, trials, thread_id) = player_info

                        mythic_adjustment = await character_commands.mythic_calculation(
                            character_name=character_name,
                            level=character_level,
                            trials=trials,
                            trial_change=amount,
                            guild_id=guild_id,
                            tier=tier
                        )
                        (new_tier, total_trials, trials_required, trial_change) = mythic_adjustment
                        character_update = shared_functions.UpdateCharacterData(
                            character_name=character_name,
                            mythic_package=(new_tier, total_trials, trials_required)
                        )
                        await shared_functions.update_character(
                            guild_id=guild_id,
                            change=character_update
                        )

                        character_changes = shared_functions.CharacterChange(
                            character_name=character_name,
                            author=interaction.user.name,
                            tier=new_tier,
                            trials=total_trials,
                            trials_remaining=trials_required,
                            trial_change=amount,
                            source=f"admin adjusted trials by {amount} for {character_name}")
                        character_log = await shared_functions.log_embed(
                            change=character_changes,
                            guild=guild,
                            thread=thread_id,
                            bot=self.bot)
                        await shared_functions.character_embed(
                            character_name=character_name,
                            guild=guild)

                        await interaction.followup.send(
                            embed=character_log,
                            content=f"Trial changes for {character_name} have been made.",
                            ephemeral=True)

            except (aiosqlite.Error, TypeError, ValueError, character_commands.CalculationAidFunctionError) as e:
                logging.exception(
                    f"an error occurred for {interaction.user.name} whilst adjusting trials for {character_name}': {e}")
                await interaction.followup.send(
                    f"An error occurred whilst adjusting trials for '{character_name}' Error: {e}.", ephemeral=True)

    @mythic_group.command(name='cap', description='command for adjusting the tier cap of the server')
    async def tier_cap(self, interaction: discord.Interaction, new_tier: int):
        guild_id = interaction.guild_id
        guild = interaction.guild
        await interaction.response.defer(thinking=True, ephemeral=True)
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as conn:
            cursor = await conn.cursor()

            try:
                await cursor.execute("SELECT MIN(tier), MAX(tier) from AA_Trials")
                tier_minmax = await cursor.fetchone()

                if new_tier < tier_minmax[0]:
                    await interaction.followup.send(
                        f"Your server does not have a trial system for below tier {tier_minmax[0]}", ephemeral=True)

                elif new_tier > tier_minmax[1]:
                    await interaction.followup.send(
                        f"Your server does not have a trial system for above tier {tier_minmax[1]}", ephemeral=True)

                else:
                    await cursor.execute("Select Trials FROM AA_Trials where Tier = ?", (new_tier,))
                    new_tier_info = await cursor.fetchone()

                    if new_tier_info:
                        minimum_milestones = new_tier_info[0]
                        await cursor.execute("Update Admin set Search = ? WHERe Identifier = 'Tier_Cap'", (new_tier,))
                        await conn.commit()
                        await shared_functions.config_cache.load_configurations(guild_id=guild_id)
                        await cursor.execute(
                            "SELECT True_Character_Name, Character_Name, Level, Tier, Trials, Thread_ID FROM Player_Characters WHERE Trials >= ?",
                            (minimum_milestones,))
                        characters_to_adjust = await cursor.fetchall()

                        if characters_to_adjust:
                            cap_embed = discord.Embed(
                                title=f"Tier Cap Adjustment",
                                description=f'{interaction.user.name} Adjusting the tier cap to {new_tier}')

                            for idx, character in enumerate(characters_to_adjust):
                                (true_character_name, character_name, character_level, tier, trials,
                                 thread_id) = character

                                mythic_adjustment = await character_commands.mythic_calculation(
                                    guild_id=guild_id,
                                    character_name=character_name,
                                    level=character_level,
                                    trials=trials,
                                    trial_change=0,
                                    tier=tier)
                                (new_tier_adjusted, total_trials, trials_required, trial_change) = mythic_adjustment

                                character_updates = shared_functions.UpdateCharacterData(
                                    character_name=character_name,
                                    mythic_package=(new_tier_adjusted, total_trials, trials_required)
                                )

                                character_changes = shared_functions.CharacterChange(
                                    character_name=character_name,
                                    author=interaction.user.name,
                                    tier=new_tier_adjusted,
                                    trials=total_trials,
                                    trials_remaining=trials_required,
                                    trial_change=0,
                                    source=f"admin adjusted the server tier cap to {new_tier}")

                                await shared_functions.update_character(
                                    guild_id=guild_id,
                                    change=character_updates
                                )

                                await shared_functions.log_embed(
                                    change=character_changes,
                                    guild=guild,
                                    thread=thread_id,
                                    bot=self.bot)

                                await shared_functions.character_embed(
                                    character_name=character_name,
                                    guild=guild)

                                if idx <= 20:
                                    cap_embed.add_field(
                                        name=f"{true_character_name}",
                                        value=f"{true_character_name} has been leveled up to {new_tier}.",
                                        inline=False)

                                elif idx == 21:
                                    additional_characters = true_character_name

                                else:
                                    additional_characters += f", {true_character_name}"

                            if idx >= 21:
                                cap_embed.add_field(
                                    name=f"Additional Characters",
                                    value=f"{idx} additional characters have been adjusted.\r\n{additional_characters}",
                                    inline=False)

                            await interaction.followup.send(embed=cap_embed, ephemeral=True)

                            logging.info(
                                f"{interaction.user.name} has adjusted the tier cap to {new_tier} for {guild.name} with {idx} characters adjusted.")

                        else:
                            await interaction.followup.send(
                                f"The Tier cap is now {new_tier} however your server does not have any characters that meet the minimum trial to be adjusted",
                                ephemeral=True)

                    else:
                        await interaction.followup.send(
                            f"Your server does not have a milestone system for tier {new_tier}", ephemeral=True)

            except (aiosqlite.Error, TypeError, ValueError) as e:
                logging.exception(
                    f"An error occurred whilst updating tier cap! input values of: {new_tier} in server {interaction.guild.id} by {interaction.user.name}': {e}"
                )
                await interaction.followup.send(
                    f"An error occurred whilst fetching data. Please try again later.",
                    ephemeral=True)

    @mythic_group.command(name='define', description='command for defining the trials required for a tier')
    async def define_tier(self, interaction: discord.Interaction, tier: int, trials: int):
        guild_id = interaction.guild_id
        await interaction.response.defer(thinking=True, ephemeral=True)

        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as conn:
            cursor = await conn.cursor()

            try:
                await cursor.execute("SELECT MIN(Tier), MAX(Tier) from AA_Trials")
                tier_minmax = await cursor.fetchone()

                if tier < tier_minmax[0] - 1:
                    await interaction.followup.send(
                        f"Your server does not have a trial system for below tier {tier_minmax[0]}", ephemeral=True)
                    return

                elif tier > tier_minmax[1] + 1:
                    await interaction.followup.send(
                        f"Your server does not have a trial system for above tier {tier_minmax[1]}", ephemeral=True)
                    return

                await cursor.execute("SELECT Trials FROM AA_Trials WHERE Tier = ?", (tier - 1,))
                low_tier_info = await cursor.fetchone()

                await cursor.execute("SELECT Trials FROM AA_Trials WHERE Tier = ?", (tier,))
                center_tier_info = await cursor.fetchone()

                await cursor.execute("SELECT Trials FROM AA_Trials WHERE Tier = ?", (tier + 1,))
                high_tier_info = await cursor.fetchone()

                center_trials_required = 999 if not high_tier_info else high_tier_info[0] - trials

                if low_tier_info:
                    if trials == -1:
                        low_trials_required = 999 if not high_tier_info else high_tier_info[0] - low_tier_info[0]

                    else:

                        low_trials_required = trials - low_tier_info[0]

                        if low_trials_required < 0:
                            await interaction.followup.send(
                                f"Your input of tier: {tier} trials: {trials} cannot be less than tier: {tier - 1} trials: {low_tier_info[0]}.",
                                ephemeral=True)
                            return

                    await cursor.execute(
                        "UPDATE AA_Trials SET Trials_Required = ? WHERE Tier = ?",
                        (low_trials_required, tier - 1))
                    await conn.commit()

                if high_tier_info:
                    if trials > high_tier_info[0]:
                        await interaction.followup.send(
                            f"Your input of tier: {tier} trials: {trials} cannot be more than tier: {tier + 1} trials: {high_tier_info[0]}.",
                            ephemeral=True)
                        return

                    else:
                        await cursor.execute(
                            "SELECT Character_Name, level, Trials, thread_id FROM Player_Characters WHERE Trials BETWEEN ? AND ?",
                            (trials, high_tier_info[0]))
                        characters_to_adjust = await cursor.fetchall()

                        for character in characters_to_adjust:
                            (character_name, character_level, trials, thread_id) = character
                            mythic_adjustment = await character_commands.mythic_calculation(
                                character_name=character_name,
                                level=character_level,
                                trials=trials,
                                trial_change=0,
                                guild_id=guild_id,
                                tier=tier)
                            (new_tier, total_trials, trials_required, trial_change) = mythic_adjustment

                            character_updates = shared_functions.UpdateCharacterData(
                                character_name=character_name,
                                mythic_package=(new_tier, total_trials, trials_required)
                            )

                            character_changes = shared_functions.CharacterChange(
                                character_name=character_name,
                                author=interaction.user.name,
                                tier=new_tier,
                                trials=total_trials,
                                trials_remaining=trials_required,
                                trial_change=0,
                                source=f"admin added new Tier of {tier}")

                            await shared_functions.update_character(
                                guild_id=guild_id,
                                change=character_updates)

                            await shared_functions.log_embed(
                                change=character_changes,
                                guild=interaction.guild,
                                thread=thread_id,
                                bot=self.bot)

                            await shared_functions.character_embed(
                                character_name=character_name,
                                guild=interaction.guild)

                if center_tier_info:
                    if trials == -1:
                        await cursor.execute("DELETE FROM AA_Trials WHERE Tier = ?", (tier,))
                        await conn.commit()

                        if tier > 0:
                            await cursor.execute("UPDATE AA_Trials SET Tier = Tier - 1 where Tier > ?", (tier,))

                        else:
                            await cursor.execute("UPDATE AA_Trials SET Tier = Tier + 1 where Tier < ?",
                                                 (tier,))

                        await interaction.followup.send(f"Tier of {tier} removed from trial system.", ephemeral=True)

                    else:
                        await cursor.execute(
                            "UPDATE AA_Trials SET Trials = ?, Trials_Required = ? WHERE Tier = ?",
                            (trials, center_trials_required, tier))

                        await interaction.followup.send(
                            f"Tier of {tier} updated in trial system. Now requires {trials} trials.", ephemeral=True)

                else:
                    await cursor.execute("INSERT INTO AA_Trials (Tier, Trials, Trials_Required) VALUES (?, ?, ?)",
                                         (tier, trials, center_trials_required))

                    await interaction.followup.send(
                        f"Tier of {tier} added to trial system. It requires {trials} trials.", ephemeral=True)
                await conn.commit()

            except (aiosqlite.Error, TypeError, ValueError) as e:
                logging.exception(
                    f"An error occurred whilst updating tier cap! input values of: {tier}, {trials} in server {interaction.guild.id} by {interaction.user.name}': {e}"
                )

                await interaction.followup.send(
                    f"An error occurred whilst fetching data. Please try again later.",
                    ephemeral=True)

    @mythic_group.command(name='display', description='Display the mythic system')
    async def display_mythic(self, interaction: discord.Interaction, page_number: int = 1):
        """Display Mythic Information and further context about levels."""
        guild_id = interaction.guild_id
        await interaction.response.defer(thinking=True, ephemeral=True)

        try:
            async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as conn:
                cursor = await conn.cursor()

                # Decide which query to execute based on whether 'name' is provided
                await cursor.execute("SELECT COUNT(Tier) FROM AA_Trials")
                item_count = await cursor.fetchone()
                item_count = item_count[0]

                # Set up pagination variables
                page_number = min(max(page_number, 1), ceil(item_count / 20))
                items_per_page = 20
                offset = (page_number - 1) * items_per_page

                # Create and send the view with the results
                view = MythicDisplayView(
                    user_id=interaction.user.id,
                    guild_id=guild_id,
                    limit=items_per_page,
                    offset=offset,
                    interaction=interaction
                )
                await view.update_results()
                await view.create_embed()
                await interaction.followup.send(embed=view.embed, view=view, ephemeral=True)

        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(
                f"an error occurred displaying mythic system: {e}"
            )
            await interaction.followup.send(
                f"An error occurred whilst fetching data. Please try again later.",
                ephemeral=True
            )

    test_group = discord.app_commands.Group(
        name='test',
        description='Test commands for the bot for testing certain features.',
        parent=admin_group
    )

    @test_group.command(name='worldanvil', description='Test command for the worldanvil API')
    async def worldanvil(self, interaction: discord.Interaction):
        """This is a test command for the wa command."""
        await interaction.response.defer(thinking=True, ephemeral=True)
        client = WaClient(
            'pathparser',
            'https://github.com/Solfyrism/pathparser',
            'V1.1',
            os.getenv('WORLD_ANVIL_API'),  # This is the token for the bot
            os.getenv(f'WORLD_ANVIL_{interaction.guild_id}')  # This is the token for the guild
        )

        try:
            try:
                timeline = client.timeline.get('906c8c14-2283-47e0-96e2-0fcd9f71d0d0', granularity=str(1))
                print(timeline)
            except Exception as e:
                print(e)
            try:
                history = client.history.get('76c474c1-c1db-4587-ab62-471e3a29f55f', granularity=str(2))
                print(history)
            except Exception as e:
                print(e)
            try:
                category = client.category.get('a9eee0b7-6121-4680-aa43-f128b8c19506', granularity=str(1))
                print(category)
            except Exception as e:
                print(e)
            try:
                authenticated_user = client.user.identity()
                print(f"I am the authenticated user of {authenticated_user}")
            except Exception as e:
                print(e)
            try:
                worlds = [world for world in client.user.worlds(authenticated_user['id'])]
                print(f"This is my World: {worlds}")
            except Exception as e:
                print(e)
            try:
                categories = [category for category in client.world.categories('f7a60480-ea15-4867-ae03-e9e0c676060a')]
                print(f"this category contains the following categories {categories}")
            except Exception as e:
                print(e)
            try:
                articles = [article for article in client.world.articles('f7a60480-ea15-4867-ae03-e9e0c676060a',
                                                                         'b71f939a-f72d-413b-b4d7-4ebff1e162ca')]
                print(articles)
            except Exception as e:
                print(e)
            try:
                specific_article = client.article.get('3e958a12-25f5-40cc-a421-b1121a357ba7', granularity=str(1))
                print(f"THIS IS {specific_article}")
            except Exception as e:
                print(e)
                print(f"Content for  {specific_article['content']}")
            #    world_id = 'f7a60480-ea15-4867-ae03-e9e0c676060a'

            await interaction.followup.send(
                f"Authenticated User Connection Successful: \r\nWorlds: {worlds}", ephemeral=True)

        except Exception as e:
            # If the user is not authenticated, the bot will raise an exception. I don't know the intended exceptions. but this is to tell the user it failed
            await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)
            logging.exception("An error occurred whilst testing the WorldAnvil API")

    archive = discord.app_commands.Group(
        name='archive',
        description='display players from the archive, and archive inactive players',
        parent=admin_group
    )

    @archive.command(name='display', description='Display players from the archive')
    async def display_archive(self, interaction: discord.Interaction, player_name: typing.Optional[discord.Member],
                              character_name: typing.Optional[str],
                              page_number: int = 1):
        """Display character information.
                Display A specific view when a specific character is provided,
                refine the list of characters when a specific player is provided."""
        guild_id = interaction.guild_id
        await interaction.response.defer(thinking=True, ephemeral=True)

        try:
            async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as conn:
                cursor = await conn.cursor()

                # Decide which query to execute based on whether 'name' is provided
                if not player_name:
                    await cursor.execute("SELECT COUNT(Character_Name) FROM Archive_Player_Characters")

                else:
                    await cursor.execute(
                        "SELECT COUNT(Character_Name) FROM Archive_Player_Characters WHERE Player_Name = ?",
                        (player_name.name,))

                character_count = await cursor.fetchone()
                (character_count,) = character_count

                if character_name:
                    view_type = 2
                    await cursor.execute(
                        "SELECT character_name from Archive_Player_Characters where Character_Name = ?",
                        (character_name,))
                    character = await cursor.fetchone()

                    if not character:
                        await interaction.followup.send(
                            f"Character '{character_name}' not found.",
                            ephemeral=True
                        )
                        return

                    else:
                        if player_name:
                            await cursor.execute(
                                "SELECT character_name from Archive_Player_Characters WHERE Player_Name = ? ORDER BY True_Character_Name asc",
                                (player_name.name,))

                        else:
                            await cursor.execute(
                                "SELECT character_name from Archive_Player_Characters ORDER BY True_Character_Name asc")

                        results = await cursor.fetchall()
                        offset = results.index(character[0]) + 1

                else:
                    view_type = 1

                # Set up pagination variables
                page_number = min(max(page_number, 1), ceil(character_count / 20))
                items_per_page = 5 if view_type == 1 else 1
                offset = (page_number - 1) * items_per_page if view_type == 1 else offset

                # Create and send the view with the results
                view = ArchiveDisplayView(
                    user_id=interaction.user.id,
                    guild_id=guild_id,
                    player_name=player_name.name,
                    character_name=character_name,
                    limit=items_per_page,
                    offset=offset,
                    view_type=view_type,
                    interaction=interaction
                )
                await view.update_results()
                await view.create_embed()
                await interaction.followup.send(embed=view.embed, view=view, ephemeral=True)

        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(
                f"An error occurred whilst fetching data and creating views! {e}")

            await interaction.followup.send(
                f"An error occurred whilst fetching data. Please try again later.",
                ephemeral=True)

    @archive.command(name='inactive', description='Archive inactive players')
    @app_commands.describe(confirmation="if yes, remove all inactive players!")
    @app_commands.choices(
        confirmation=[discord.app_commands.Choice(name='No!', value=1),
                      discord.app_commands.Choice(name='Yes!', value=2)])
    async def archive_inactive(self, interaction: discord.Interaction, player_name: typing.Optional[str],
                               character_name: typing.Optional[str],
                               confirmation: discord.app_commands.Choice[int]):
        """Archive inactive players."""
        guild_id = interaction.guild_id
        guild = interaction.guild
        await interaction.response.defer(thinking=True, ephemeral=True)
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as conn:
            cursor = await conn.cursor()
            try:
                if confirmation == 1:
                    await interaction.followup.send(
                        f"Archive Inactive Players has been cancelled.",
                        ephemeral=True
                    )
                    return

                else:
                    if character_name:
                        await cursor.execute(
                            "SELECT player_id, player_name, character_name FROM Player_Characters WHERE Character_Name = ?",
                            (character_name,))

                        player_info = await cursor.fetchone()
                        retirement_type = 2

                        if not player_info:
                            await interaction.followup.send("No character found with that name to archive.",
                                                            ephemeral=True)
                            return

                    elif player_name:
                        await cursor.execute(
                            "SELECT player_id, player_name, character_name FROM Player_Characters WHERE Player_Name = ?",
                            (player_name,))
                        player_info = await cursor.fetchone()
                        retirement_type = 1

                        if not player_info:
                            await interaction.followup.send("No player found with that name to archive.",
                                                            ephemeral=True)
                            return

                    else:
                        retirement_type = 3

                    async with shared_functions.config_cache.lock:
                        configs = shared_functions.config_cache.cache[interaction.guild.id]
                        accepted_bio_channel = configs.get('Accepted_Bio_Channel')

                    if not accepted_bio_channel:
                        await interaction.followup.send(
                            "No accepted bio channel found. Please set an accepted bio channel to continue.",
                            ephemeral=True)
                        return

                    content = "These player characters will be moved to an Archived table and their Character Bios cleared from the server."
                    view = ArchiveCharactersView(
                        retirement_type=retirement_type, player_name=player_name,
                        character_name=character_name, guild=guild,
                        accepted_bio_channel=accepted_bio_channel,
                        content=content, interaction=interaction)
                    await view.send_initial_message()

            except (aiosqlite.Error, TypeError, ValueError) as e:
                logging.exception(
                    f"An error occurred whilst archiving inactive players! input values of player_name: {player_name}, character_name: {character_name}': {e}"
                )

                await interaction.followup.send(
                    f"An error occurred whilst archiving inactive players. Please try again later.",
                    ephemeral=True)

    roleplay_group = discord.app_commands.Group(
        name='roleplay',
        description='Roleplay commands for the bot',
        parent=admin_group
    )

    @roleplay_group.command(name='add_channel', description='Add a channel to the RP channels')
    async def add_rp_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild.id}.sqlite") as db:
                cursor = await db.execute("SELECT 1 FROM rp_Approved_Channels WHERE channel_id = ?", (channel.id,))
                existing_channel = await cursor.fetchone()

                if existing_channel:
                    await interaction.followup.send(f"{channel.mention} is already an RP channel.", ephemeral=True)
                    return

                await db.execute("INSERT INTO rp_Approved_Channels (channel_id) VALUES (?)", (channel.id,))
                await db.commit()

                await shared_functions.add_guild_to_cache(interaction.guild.id)
                await interaction.followup.send(f"{channel.mention} has been added to the RP channels.",
                                                ephemeral=True)

        except (aiosqlite.Error, ValueError) as e:
            print(e)
            logging.exception(
                f"An error occurred whilst listing RP channels: {e}"
            )
            await interaction.followup.send(
                f"An error occurred whilst fetching data. Please try again later.",
                ephemeral=True
            )

    @roleplay_group.command(name='remove_channel', description='Remove a channel from the RP channels')
    async def remove_rp_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild.id}.sqlite") as db:
                cursor = await db.execute("SELECT 1 FROM rp_Approved_Channels WHERE channel_id = ?", (channel.id,))
                rp_channel = await cursor.fetchone()

                if rp_channel:
                    await db.execute("DELETE FROM rp_Approved_Channels WHERE channel_id = ?", (channel.id,))
                    await db.commit()
                    async with shared_functions.config_cache.lock:
                        await shared_functions.config_cache.pop(interaction.guild.id, None)
                    await shared_functions.add_guild_to_cache(interaction.guild.id)
                    await interaction.followup.send(
                        f"{channel.mention} has been removed from the RP channels.",
                        ephemeral=True)

                else:
                    await interaction.followup.send(f"{channel.mention} is not an RP channel.", ephemeral=True)

        except (aiosqlite.Error, ValueError) as e:
            logging.exception(
                f"An error occurred whilst listing RP channels: {e}"
            )
            await interaction.followup.send(
                f"An error occurred whilst fetching data. Please try again later.",
                ephemeral=True)

    @roleplay_group.command(name='add_category', description='Add all channels in a category to the RP channels')
    async def add_rp_category(self, interaction: discord.Interaction, category: discord.CategoryChannel, except_channel_1: typing.Optional[discord.TextChannel], except_channel_2: typing.Optional[discord.TextChannel], except_channel_3: typing.Optional[discord.TextChannel], except_channel_4: typing.Optional[discord.TextChannel]):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            response = f"In this category there were the following channels:"
            for channel in category.text_channels:
                if channel == except_channel_1 or channel == except_channel_2 or channel == except_channel_3 or channel == except_channel_4:
                    response += f"\n{channel.mention} was skipped."
                    continue
                else:
                    async with aiosqlite.connect(f"pathparser_{interaction.guild.id}.sqlite") as db:
                        cursor = await db.execute("SELECT 1 FROM rp_Approved_Channels WHERE channel_id = ?", (channel.id,))
                        existing_channel = await cursor.fetchone()

                        if existing_channel:
                            response += f"\n {channel.mention} is already an RP channel."
                            continue
                        else:

                            await db.execute("INSERT INTO rp_Approved_Channels (channel_id) VALUES (?)", (channel.id,))
                            await db.commit()
                            response += f"\n{channel.mention} has been added to the RP channels."
            await shared_functions.add_guild_to_cache(interaction.guild.id)
            await interaction.followup.send(response, ephemeral=True)
        except (aiosqlite.Error, ValueError) as e:
            print(e)
            logging.exception(
                f"An error occurred whilst listing RP channels: {e}"
            )
            await interaction.followup.send(
                f"An error occurred whilst fetching data. Please try again later.",
                ephemeral=True
            )

    @roleplay_group.command(name='remove_category', description='Remove all channels in a category from the RP channels')
    async def remove_rp_channel(
            self,
            interaction: discord.Interaction,
            category: discord.CategoryChannel,
            except_channel_1: typing.Optional[discord.TextChannel],
            except_channel_2: typing.Optional[discord.TextChannel],
            except_channel_3: typing.Optional[discord.TextChannel],
            except_channel_4: typing.Optional[discord.TextChannel]):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            response = f"In this category there were the following channels:"
            async with aiosqlite.connect(f"pathparser_{interaction.guild.id}.sqlite") as db:
                for channel in category.text_channels:
                    if channel == except_channel_1 or channel == except_channel_2 or channel == except_channel_3 or channel == except_channel_4:
                        response += f"\n{channel.mention} was skipped."
                        continue
                    else:
                        cursor = await db.execute("SELECT 1 FROM rp_Approved_Channels WHERE channel_id = ?", (channel.id,))
                        rp_channel = await cursor.fetchone()

                        if rp_channel:
                            await db.execute("DELETE FROM rp_Approved_Channels WHERE channel_id = ?", (channel.id,))
                            await db.commit()

                            response += f"\n{channel.mention} has been removed from the RP channels."
                        else:
                            response += f"\n{channel.mention} is not an RP channel."
                async with shared_functions.config_cache.lock:
                    await shared_functions.add_guild_to_cache(interaction.guild.id)
                await interaction.followup.send(response,ephemeral=True)
        except (aiosqlite.Error, ValueError) as e:
            logging.exception(
                f"An error occurred whilst listing RP channels: {e}"
            )
            await interaction.followup.send(
                f"An error occurred whilst fetching data. Please try again later.",
                ephemeral=True)



    @roleplay_group.command(name='list_channels', description='List the RP channels')
    async def list_rp_channels(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild.id}.sqlite") as db:
                cursor = await db.execute("SELECT channel_id FROM rp_Approved_Channels")
                rp_channels = await cursor.fetchall()

                if rp_channels:
                    channels = [f"<#{channel_id}>" for (channel_id,) in rp_channels]
                    channels_list = "\n".join(channels)
                    await interaction.followup.send(f"Current RP channels:\n{channels_list}", ephemeral=True)

                else:
                    await interaction.followup.send("There are no RP channels set.", ephemeral=True)

        except (aiosqlite.Error, ValueError) as e:
            logging.exception(
                f"An error occurred whilst listing RP channels: {e}")

            await interaction.followup.send(
                f"An error occurred whilst fetching data. Please try again later.",
                ephemeral=True)

    @roleplay_group.command(name='adjust_rp', description='Adjust the RP amount for a player')
    async def adjust_rp(self, interaction: discord.Interaction, player: typing.Optional[discord.Member], role: typing.Optional[discord.Role], amount: int):
        """Adjust the RP amount for a player."""
        await interaction.response.defer(thinking=True, ephemeral=False)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild.id}.sqlite") as db:
                cursor = await db.cursor()
                if player:
                    if player.bot:
                        await interaction.followup.send("Very funny. You cannot adjust the RP of a bot.", ephemeral=True)
                        return
                    await cursor.execute("SELECT balance from RP_Players WHERE user_id = ?", (player.id,))
                    rp_balance = await cursor.fetchone()

                    if not rp_balance:
                        await db.execute(
                            "INSERT INTO RP_Players (user_id, user_name, balance) "
                            "VALUES (?, ?, ?)",
                            (player.id, player.name, amount))
                    else:
                        await cursor.execute("UPDATE RP_Players SET balance = balance + ? WHERE user_id = ?",
                                             (amount, player.id))
                    await db.commit()
                    await interaction.followup.send(
                        f"RP balance for {player.mention} has been adjusted by {amount} they now have {rp_balance[0] + amount}.",
                        ephemeral=True)
                if role:
                    for player in role.members:
                        await cursor.execute("SELECT balance from RP_Players WHERE user_id = ?", (player.id,))
                        rp_balance = await cursor.fetchone()
                        if not rp_balance:
                            await db.execute(
                                "INSERT INTO RP_Players (user_id, user_name, balance) "
                                "VALUES (?, ?, ?)",
                                (player.id, player.name, amount))
                        else:
                            await cursor.execute("UPDATE RP_Players SET balance = balance + ? WHERE user_id = ?",
                                             (amount, player.id))
                        await db.commit()
                    await interaction.followup.send(
                        f"RP balance for all members of {role.name} has been adjusted by {amount}.", ephemeral=True)

        except (aiosqlite.Error, ValueError) as e:
            logging.exception(
                f"An error occurred whilst listing RP channels: {e}")
            await interaction.followup.send(
                f"An error occurred whilst fetching data. Please try again later.",
                ephemeral=True)

    @roleplay_group.command(name='adjust_role', description='Adjust the RP amount for a player')
    async def adjust_role_rp(self, interaction: discord.Interaction, group: discord.Role, amount: int):
        """Adjust the RP amount for a player."""
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild.id}.sqlite") as db:
                cursor = await db.cursor()
                for player in group.members:
                    try:
                        await cursor.execute(
                            "UPDATE RP_Balance SET balance = balance + ? WHERE user_id = ?",
                            (amount, player.id))
                        await db.commit()

                    except aiosqlite.Error:
                        pass

                await interaction.followup.send(
                    f"RP balance for all members of {group.name} has been adjusted by {amount}.", ephemeral=True)

        except (aiosqlite.Error, ValueError) as e:
            logging.exception(
                f"An error occurred whilst listing RP channels: {e}")

            await interaction.followup.send(
                f"An error occurred whilst fetching data. Please try again later.",
                ephemeral=True)

    @roleplay_group.command(name="update", description="Update the server RP generation settings")
    @app_commands.describe(similarity_threshold="The similarity threshold for RP generation 90 is 90% 10 is 10%")
    @app_commands.describe(reward_multiplier="The reward multiplier for RP generation, 1 generates 1 coin per 10 words")
    async def update_rp(self, interaction: discord.Interaction, minimum_length: typing.Optional[int],
                        similarity_threshold: typing.Optional[int],
                        minimum_reward: typing.Optional[int], maximum_reward: typing.Optional[int],
                        reward_multiplier: typing.Optional[int], reward_name: typing.Optional[str],
                        reward_emoji: typing.Optional[str]):
        """Update the RP generation settings for the server."""
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild.id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute(
                    "Select Minimum_Post_Length_In_Characters, Similarity_Threshold, Minimum_Reward, Maximum_Reward, Reward_Multiplier, Reward_Name, Reward_Emoji FROM RP_Guild_Info")
                rp_settings = await cursor.fetchone()
                (old_minimum_length, old_similarity_threshold, old_minimum_reward, old_maximum_reward,
                 old_reward_multiplier, old_reward_name, old_reward_emoji) = rp_settings

                minimum_length = minimum_length if minimum_length is not None else old_minimum_length
                similarity_threshold = similarity_threshold if similarity_threshold is not None else old_similarity_threshold
                minimum_reward = minimum_reward if minimum_reward is not None else old_minimum_reward
                maximum_reward = maximum_reward if maximum_reward is not None else old_maximum_reward
                reward_multiplier = reward_multiplier if reward_multiplier is not None else old_reward_multiplier
                reward_name = reward_name if reward_name is not None else old_reward_name
                reward_emoji = reward_emoji if reward_emoji is not None else old_reward_emoji

                await cursor.execute(
                    "UPDATE RP_Guild_Info SET Minimum_Post_Length_In_Characters = ?, Similarity_Threshold = ?, Minimum_Reward = ?, maximum_reward = ?, Reward_Multiplier = ?, Reward_Name = ?, Reward_Emoji = ?",
                    (minimum_length, similarity_threshold, minimum_reward, maximum_reward, reward_multiplier,
                     reward_name, reward_emoji))
                await db.commit()

                async with RP_Commands.roleplay_info_cache.lock:
                    RP_Commands.roleplay_info_cache.cache.pop(interaction.guild.id, None)
                    await RP_Commands.add_guild_to_rp_cache(interaction.guild.id)

                await interaction.followup.send("RP settings have been updated.", ephemeral=True)

        except (aiosqlite.Error, ValueError) as e:
            logging.exception(
                f"An error occurred whilst updating RP settings: {e}")

            await interaction.followup.send(
                f"An error occurred whilst updating RP settings. Please try again later.",
                ephemeral=True)

    @roleplay_group.command(name="list", description="List all RP settings for the server")
    async def list_rp(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild.id}.sqlite") as db:
                cursor = await db.cursor()

                await cursor.execute(
                    "Select Minimum_Post_Length_In_Characters, Similarity_Threshold, Minimum_Reward, Maximum_Reward, Reward_Multiplier FROM RP_Guild_Info")
                rp_settings = await cursor.fetchone()

                if rp_settings:
                    (minimum_length, similarity_threshold, minimum_reward, maximum_reward,
                     reward_multiplier) = rp_settings
                    await interaction.followup.send(
                        f"RP Settings:\n"
                        f"Minimum Post Length: {minimum_length}\n"
                        f"Similarity Threshold: {similarity_threshold}%\n"
                        "Minimum Reward: {minimum_reward}\n"
                        f"Maximum Reward: {maximum_reward}\n"
                        f"Reward Multiplier: {reward_multiplier}", ephemeral=True)

                else:
                    await interaction.followup.send("There are no RP settings set.", ephemeral=True)

        except (aiosqlite.Error, ValueError) as e:
            logging.exception(
                f"An error occurred whilst listing RP settings: {e}")

            await interaction.followup.send(
                f"An error occurred whilst fetching data. Please try again later.",
                ephemeral=True)

    rp_store_group = discord.app_commands.Group(
        name='rp_store',
        description='Roleplay commands for the bot',
        parent=admin_group
    )

    @rp_store_group.command(name='add', description='add an item to the store')
    @app_commands.describe(stock="The amount of stock available for the item, x<0 for infinite")
    @app_commands.describe(response="The response to be sent when the item is used")
    @app_commands.describe(storable="Whether the item can be stored or is immediately used on purchase.")
    @app_commands.describe(sellable="Whether the item can be sold back to the store or not.")
    @app_commands.choices(
        storable=[discord.app_commands.Choice(name='storable', value=1),
                  discord.app_commands.Choice(name='consumed', value=2)])
    @app_commands.choices(
        sellable=[discord.app_commands.Choice(name='sellable', value=1),
                  discord.app_commands.Choice(name='unsellable', value=2)])
    @app_commands.choices(
        usable=[discord.app_commands.Choice(name='usable', value=1),
                discord.app_commands.Choice(name='unusable', value=2)])
    async def add_rp_store(
            self,
            interaction: discord.Interaction,
            name: str,
            description: str,
            price: int,
            stock: typing.Optional[int] = -1,
            image: typing.Optional[str] = None,
            response: typing.Optional[str] = None,
            storable: discord.app_commands.Choice[int] = 1,
            sellable: discord.app_commands.Choice[int] = 1,
            usable: discord.app_commands.Choice[int] = 1,
    ):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            sellable_value = sellable if isinstance(sellable, int) else sellable.value
            storable_value = storable if isinstance(storable, int) else storable.value
            usable_value = usable if isinstance(usable, int) else usable.value

            result = await add_item_to_store(
                guild_id=interaction.guild.id,
                item_name=name,
                description=description,
                price=price,
                stock=stock,
                image=image,
                custom_message=response,
                inventory=storable_value,
                sellable=sellable_value,
                usable=usable_value
            )

            if isinstance(result, str):
                await interaction.followup.send(result, ephemeral=True)
                return

            else:
                await interaction.followup.send(f"{name} has been added to the store.", ephemeral=True)

        except (aiosqlite.Error, ValueError) as e:
            logging.exception(f"an issue occurred in the add_rp_store command {e}")

            await interaction.followup.send(
                f"An error occurred whilst responding. Please try again later.", ephemeral=True)

    @rp_store_group.command(name='edit', description='edit the store by adding or editing an item')
    @app_commands.describe(stock="The amount of stock available for the item, x<0 for infinite")
    @app_commands.describe(response="The response to be sent when the item is used")
    @app_commands.describe(storable="Whether the item can be stored or is immediately used on purchase.")
    @app_commands.describe(sellable="Whether the item can be sold back to the store or not.")
    @app_commands.choices(
        storable=[discord.app_commands.Choice(name='storable', value=1),
                  discord.app_commands.Choice(name='consumed', value=0)])
    @app_commands.choices(
        sellable=[discord.app_commands.Choice(name='sellable', value=1),
                  discord.app_commands.Choice(name='unsellable', value=0)])
    @app_commands.choices(
        usable=[discord.app_commands.Choice(name='usable', value=1),
                discord.app_commands.Choice(name='unusable', value=0)])
    @app_commands.autocomplete(name=shared_functions.rp_store_autocomplete)
    async def edit_rp_store(
            self,
            interaction: discord.Interaction,
            name: str,
            new_name: typing.Optional[str],
            description: typing.Optional[str],
            price: typing.Optional[int],
            stock: typing.Optional[int],
            image: typing.Optional[str],
            response: typing.Optional[str],
            storable: typing.Optional[discord.app_commands.Choice[int]],
            sellable: typing.Optional[discord.app_commands.Choice[int]],
            usable: discord.app_commands.Choice[int]):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            sellable_value = sellable.value if sellable else None
            storable_value = storable.value if storable else None
            usable_value = usable.value
            result = await edit_item_in_store(
                guild_id=interaction.guild.id,
                old_item_name=name,
                new_item_name=new_name,
                description=description,
                price=price,
                stock=stock,
                image=image,
                custom_message=response,
                inventory=storable_value,
                sellable=sellable_value,
                usable=usable_value
            )

            if isinstance(result, str):
                await interaction.followup.send(result, ephemeral=True)
                return

            else:
                await interaction.followup.send(f"{name} has been updated in the store!", ephemeral=True)

        except (aiosqlite.Error, ValueError) as e:
            logging.exception(f"an issue occurred in the edit_rp_store command: {e}")

            await interaction.followup.send(
                f"An error occurred whilst responding. Please try again later.", ephemeral=True)

    @rp_store_group.command(name='give', description='give an item to a user')
    @app_commands.autocomplete(item_name=shared_functions.rp_store_autocomplete)
    async def give_item_to_player(self, interaction: discord.Interaction, item_name: str, quantity: int,
                                  player: discord.Member):
        await interaction.response.defer(thinking=True)
        try:
            if quantity < 1:
                await interaction.followup.send(f"Quantity must be a positive integer.")
                return

            async with aiosqlite.connect(f"pathparser_{interaction.guild.id}.sqlite") as db:
                cursor = await db.cursor()

                await cursor.execute(
                    "SELECT item_id, stock_remaining, Inventory, custom_message FROM rp_store_items WHERE name = ?",
                    (item_name,))
                item = await cursor.fetchone()

                if not item:
                    await interaction.followup.send(f"{item_name} is not in the store.", ephemeral=True)
                    return

                (item_id, stock, storable, custom_message) = item
                if stock < quantity and stock != -1:
                    await interaction.followup.send(f"Insufficient stock for {item_name}.", ephemeral=True)
                    return

                if stock > 0:
                    await cursor.execute(
                        f"Update rp_store_items SET stock_remaining = stock_remaining - ? WHERE name = ?",
                        (quantity, item_name))
                    await db.commit()

                await RP_Commands.handle_inventory_or_use(
                    db=db,
                    user_id=player.id,
                    amount=quantity,
                    item_name=item_name,
                    item_id=item_id,
                    custom_message=custom_message,
                    inventory=storable,
                    interaction=interaction
                )
                content = f"{quantity} {item_name} has been given to {player.mention}."
                content += f"\r\n {custom_message}" if storable == 0 and custom_message else ""
                content += f"\r\n {quantity} {item_name} has been removed from the store." if stock > 0 else ""

                await interaction.followup.send(content=content)

        except (aiosqlite.Error, ValueError) as e:
            logging.exception(f"an issue occurred in the give_item_to_player command: {e}")

            await interaction.followup.send(
                f"An error occurred whilst responding. Please try again later.", ephemeral=True)

    @rp_store_group.command(name='take', description='take an item from a user')
    @app_commands.autocomplete(item_name=shared_functions.rp_store_autocomplete)
    async def take_item_from_player(self, interaction: discord.Interaction, item_name: str, quantity: int,
                                    player: discord.Member):
        await interaction.response.defer(thinking=True)
        try:
            if quantity < 1:
                await interaction.followup.send(f"Quantity must be a positive integer.", ephemeral=True)
                return

            async with aiosqlite.connect(f"pathparser_{interaction.guild.id}.sqlite") as db:
                cursor = await db.cursor()

                await cursor.execute(
                    "SELECT item_name, item_quantity FROM RP_Players_items WHERE player_id = ? and item_name = ?",
                    (player.id, item_name))
                item = await cursor.fetchone()

                if not item:
                    await interaction.followup.send(f"{item_name} is not in the player's inventory.", ephemeral=True)
                    return

                (item_name, stored) = item
                quantity = min(quantity, stored)
                stored -= quantity

                if stored == 0:
                    await cursor.execute("DELETE FROM RP_Players_items WHERE player_id = ? and item_name = ?",
                                         (player.id, item_name))
                else:
                    await cursor.execute(
                        "UPDATE RP_Players_items SET item_quantity = ? WHERE player_id = ? and item_name = ?",
                        (stored, player.id, item_name))
                await db.commit()

                content = f"{quantity} {item_name} has been taken from {player.mention}, they have {stored} remaining."
                await interaction.followup.send(content=content, ephemeral=True)

        except (aiosqlite.Error, ValueError) as e:
            logging.exception(f"an issue occurred in the take_item_from_player command: {e}")

            await interaction.followup.send(
                f"An error occurred whilst responding. Please try again later.", ephemeral=True)

    @rp_store_group.command(name='remove', description='remove an item from the store')
    @app_commands.autocomplete(item_name=shared_functions.rp_store_autocomplete)
    async def remove_rp_store(self, interaction: discord.Interaction, item_name: str):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild.id}.sqlite") as db:
                cursor = await db.cursor()

                await cursor.execute("SELECT 1 FROM rp_store_items WHERE name = ?", (item_name,))
                item = await cursor.fetchone()

                if not item:
                    await interaction.followup.send(f"{item_name} is not in the store.", ephemeral=True)
                    return

                await cursor.execute("DELETE FROM rp_store_items WHERE name = ?", (item_name,))
                await db.commit()

                await interaction.followup.send(f"{item_name} has been removed from the store.", ephemeral=True)

        except (aiosqlite.Error, ValueError) as e:
            logging.exception(f"an issue occurred in trying to remove an item from the store: {e}")

            await interaction.followup.send(
                f"An error occurred whilst responding. Please try again later.", ephemeral=True)

    @rp_store_group.command(name='requirements', description='adjust the requirements of an item in the store')
    @app_commands.autocomplete(item_name=shared_functions.rp_store_autocomplete)
    @app_commands.choices(requirement=[discord.app_commands.Choice(name='slot 1', value=1),
                                       discord.app_commands.Choice(name='slot 2', value=2),
                                       discord.app_commands.Choice(name='slot 3', value=3)])
    @app_commands.choices(requirement_type=[discord.app_commands.Choice(name='role', value=1),
                                            discord.app_commands.Choice(name='balance', value=2),
                                            discord.app_commands.Choice(name='item', value=3)])
    async def requirements_rp_store(self, interaction: discord.Interaction, item_name: str,
                                    requirement_type: discord.app_commands.Choice[int],
                                    requirement: discord.app_commands.Choice[int], value: str):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild.id}.sqlite") as db:
                cursor = await db.cursor()

                await cursor.execute("SELECT 1 FROM rp_store_items WHERE name = ?", (item_name,))
                item = await cursor.fetchone()

                if not item:
                    await interaction.followup.send(f"{item_name} is not in the store.", ephemeral=True)
                    return

                try:
                    value = int(value)

                except ValueError:
                    await interaction.followup.send(f"Value must be an integer.", ephemeral=True)
                    return

                if requirement_type.value == 1:
                    get_role = interaction.guild.get_role(value)

                    if not get_role:
                        await interaction.followup.send(f"Role not found.", ephemeral=True)
                        return

                elif requirement_type.value == 3:
                    await cursor.execute("Select 1 from rp_store_items WHERE name = ?", (value,))
                    item = await cursor.fetchone()

                    if not item:
                        await interaction.followup.send(f"Item not found.", ephemeral=True)
                        return

                else:
                    if value < 0:
                        await interaction.followup.send(f"Value must be a positive integer.", ephemeral=True)
                        return

                requirement_value = requirement if isinstance(requirement, int) else requirement.value
                requirement_type_value = requirement_type if isinstance(requirement_type,
                                                                        int) else requirement_type.value

                if requirement_value == 1:
                    await cursor.execute(
                        "UPDATE rp_store_items SET Requirements_1_type = ?, Requirements_1_pair = ? WHERE name = ?",
                        (requirement_type_value, value, item_name))
                    await db.commit()

                elif requirement_value == 2:
                    await cursor.execute(
                        "UPDATE rp_store_items SET Requirements_2_type = ?, Requirements_2_pair = ? WHERE name = ?",
                        (requirement_type_value, value, item_name))
                    await db.commit()

                else:
                    await cursor.execute(
                        "UPDATE rp_store_items SET Requirements_3_type = ?, Requirements_3_pair = ? WHERE name = ?",
                        (requirement_type_value, value, item_name))
                    await db.commit()

                await interaction.followup.send(f"Requirements for {item_name} have been updated.", ephemeral=True)

        except (aiosqlite.Error, ValueError) as e:
            logging.exception(f"an issue occurred in the requirements_rp_store_items command: {e}")

            await interaction.followup.send(
                f"An error occurred whilst responding. Please try again later.", ephemeral=True)

    @rp_store_group.command(name='matching', description='Specify the matching requirements of an item in the store')
    @app_commands.autocomplete(item_name=shared_functions.rp_store_autocomplete)
    @app_commands.choices(matching=[discord.app_commands.Choice(name='All Match', value=1),
                                    discord.app_commands.Choice(name='Any Match', value=2),
                                    discord.app_commands.Choice(name='Not Match', value=3)])
    async def matching_rp_store(self, interaction: discord.Interaction, item_name: str,
                                matching: discord.app_commands.Choice[int]):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild.id}.sqlite") as db:
                cursor = await db.cursor()

                await cursor.execute("SELECT 1 FROM rp_store_items WHERE name = ?", (item_name,))
                item = await cursor.fetchone()

                if not item:
                    await interaction.followup.send(f"{item_name} is not in the store.", ephemeral=True)
                    return

                matching_value = matching if isinstance(matching, int) else matching.value

                await cursor.execute("UPDATE rp_store_items SET Matching_Requirements = ? WHERE name = ?",
                                     (matching_value, item_name))
                await db.commit()

                await interaction.followup.send(f"Matching requirements for {item_name} have been updated.",
                                                ephemeral=True)

        except (aiosqlite.Error, ValueError) as e:
            logging.exception(f"an issue occurred in the matching_rp_store_items command: {e}")

            await interaction.followup.send(
                f"An error occurred whilst responding. Please try again later.", ephemeral=True)

    @rp_store_group.command(name='behavior', description='Specify the behavior of an item in the store')
    @app_commands.autocomplete(item_name=shared_functions.rp_store_autocomplete)
    @app_commands.choices(slot=[discord.app_commands.Choice(name='slot 1', value=1),
                                discord.app_commands.Choice(name='slot 2', value=2),
                                discord.app_commands.Choice(name='slot 3', value=3)])
    @app_commands.choices(behavior=[discord.app_commands.Choice(name='Edit_Roles', value=1),
                                    discord.app_commands.Choice(name='Edit_Balance', value=2),
                                    discord.app_commands.Choice(name='Edit_Items', value=3)])
    @app_commands.choices(change=[discord.app_commands.Choice(name='Add', value=1),
                                  discord.app_commands.Choice(name='Remove', value=2)])
    async def behavior_rp_store(self, interaction: discord.Interaction, item_name: str,
                                slot: discord.app_commands.Choice[int], behavior: discord.app_commands.Choice[int],
                                change: discord.app_commands.Choice[int], value: str):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild.id}.sqlite") as db:
                cursor = await db.cursor()

                await cursor.execute("SELECT 1 FROM rp_store_items WHERE name = ?", (item_name,))
                item = await cursor.fetchone()

                if not item:
                    await interaction.followup.send(f"{item_name} is not in the store.", ephemeral=True)
                    return

                behavior_value = behavior if isinstance(behavior, int) else behavior.value
                change_value = change if isinstance(change, int) else change.value
                slot_value = slot if isinstance(slot, int) else slot.value

                if behavior_value == 1:
                    get_role = interaction.guild.get_role(int(value))
                    if not get_role:
                        await interaction.followup.send(f"Role not found.", ephemeral=True)
                        return

                elif behavior_value == 3:
                    await cursor.execute("Select 1 from rp_store_items WHERE name = ?", (value,))
                    item = await cursor.fetchone()

                    if not item:
                        await interaction.followup.send(f"Item not found.", ephemeral=True)
                        return

                if slot_value == 1:
                    await cursor.execute(
                        "UPDATE rp_store_items SET Actions_1_Type = ?, Actions_1_Subtype = ?, actions_1_behavior = ? WHERE name = ?",
                        (behavior_value, change_value, value, item_name))

                elif slot_value == 2:
                    await cursor.execute(
                        "UPDATE rp_store_items SET Actions_2_Type = ?, Actions_2_Subtype = ?, actions_2_behavior = ? WHERE name = ?",
                        (behavior_value, change_value, value, item_name))

                else:
                    await cursor.execute(
                        "UPDATE rp_store_items SET Actions_3_Type = ?, Actions_3_Subtype = ?, actions_3_behavior = ? WHERE name = ?",
                        (behavior_value, change_value, value, item_name))
                await db.commit()

                await interaction.followup.send(f"Behavior for {item_name} has been updated.", ephemeral=True)

        except (aiosqlite.Error, ValueError) as e:
            logging.exception(f"an issue occurred in the behavior_rp_store_items command: {e}")
            await interaction.followup.send(
                f"An error occurred whilst responding. Please try again later.", ephemeral=True)

    @rp_store_group.command(name='cancel_requirement', description='cancel a requirement for a shop item')
    @app_commands.autocomplete(item_name=shared_functions.rp_store_autocomplete)
    @app_commands.choices(requirement=[discord.app_commands.Choice(name='slot 1', value=1),
                                       discord.app_commands.Choice(name='slot 2', value=2),
                                       discord.app_commands.Choice(name='slot 3', value=3)])
    async def cancel_requirement_rp_store(self, interaction: discord.Interaction, item_name: str,
                                          requirement: discord.app_commands.Choice[int]):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild.id}.sqlite") as db:
                cursor = await db.cursor()

                await cursor.execute("SELECT 1 FROM rp_store_items WHERE name = ?", (item_name,))
                item = await cursor.fetchone()

                if not item:
                    await interaction.followup.send(f"{item_name} is not in the store.", ephemeral=True)
                    return

                requirement_value = requirement if isinstance(requirement, int) else requirement.value

                if requirement_value == 1:
                    await cursor.execute(
                        "UPDATE rp_store_items SET Requirements_1_type = NULL, Requirements_1_pair = NULL WHERE name = ?",
                        (item_name,))

                elif requirement_value == 2:
                    await cursor.execute(
                        "UPDATE rp_store_items SET Requirements_2_type = NULL, Requirements_2_pair = NULL WHERE name = ?",
                        (item_name,))

                else:
                    await cursor.execute(
                        "UPDATE rp_store_items SET Requirements_3_type = NULL, Requirements_3_pair = NULL WHERE name = ?",
                        (item_name,))
                await db.commit()

                await interaction.followup.send(f"Requirement for {item_name} has been cancelled.", ephemeral=True)

        except (aiosqlite.Error, ValueError) as e:
            logging.exception(f"an issue occurred in the cancel_requirement_rp_store_items command: {e}")

            await interaction.followup.send(
                f"An error occurred whilst responding. Please try again later.", ephemeral=True)

    @rp_store_group.command(name='cancel_behavior', description='cancel a matching requirement for a shop item')
    @app_commands.autocomplete(item_name=shared_functions.rp_store_autocomplete)
    @app_commands.choices(requirement=[discord.app_commands.Choice(name='slot 1', value=1),
                                       discord.app_commands.Choice(name='slot 2', value=2),
                                       discord.app_commands.Choice(name='slot 3', value=3)])
    async def cancel_behavior_rp_store(self, interaction: discord.Interaction, item_name: str,
                                       requirement: discord.app_commands.Choice[int]):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild.id}.sqlite") as db:
                cursor = await db.cursor()

                await cursor.execute("SELECT 1 FROM rp_store_items WHERE name = ?", (item_name,))
                item = await cursor.fetchone()

                if not item:
                    await interaction.followup.send(f"{item_name} is not in the store.", ephemeral=True)
                    return

                requirement_value = requirement if isinstance(requirement, int) else requirement.value

                if requirement_value == 1:
                    await cursor.execute(
                        "UPDATE rp_store_items SET Actions_1_Type = NULL, Actions_1_Subtype = NULL, actions_1_behavior = NULL WHERE name = ?",
                        (item_name,))

                elif requirement_value == 2:
                    await cursor.execute(
                        "UPDATE rp_store_items SET Actions_2_Type = NULL, Actions_2_Subtype = NULL, actions_2_behavior = NULL WHERE name = ?",
                        (item_name,))

                else:
                    await cursor.execute(
                        "UPDATE rp_store_items SET Actions_3_Type = NULL, Actions_3_Subtype = NULL, actions_3_behavior = NULL WHERE name = ?",
                        (item_name,))

                await db.commit()
                await interaction.followup.send(f"Behavior for {item_name} has been cancelled.", ephemeral=True)

        except (aiosqlite.Error, ValueError) as e:
            logging.exception(f"an issue occurred in the cancel_behavior_rp_store_items command: {e}")

            await interaction.followup.send(
                f"An error occurred whilst responding. Please try again later.", ephemeral=True)

    @rp_store_group.command(name='list', description='List all items in the store and their behavior')
    async def list_rp_store(self, interaction: discord.Interaction, page_number: int = 1):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild.id}.sqlite") as db:
                cursor = await db.cursor()

                await cursor.execute("SELECT COUNT(name) FROM rp_store_items")
                item_count = await cursor.fetchone()

                (item_count,) = item_count
                page_number = min(max(page_number, 1), ceil(item_count / 10))
                offset = (page_number - 1) * 5
                view = RPStoreView(
                    user_id=interaction.user.id,
                    guild_id=interaction.guild.id,
                    offset=offset,
                    limit=10,
                    interaction=interaction)

                await view.update_results()
                await view.create_embed()
                await interaction.followup.send(embed=view.embed, view=view, ephemeral=True)

        except (aiosqlite.Error, ValueError) as e:
            logging.exception(f"an issue occurred in the list_rp_store_items command: {e}")

            await interaction.followup.send(
                f"An error occurred whilst responding. Please try again later.")

    region_group = discord.app_commands.Group(
        name='region',
        description='region group commands',
        parent=admin_group
    )

    @region_group.command(name='add', description='Add a region to the server')
    async def add_region(
            self, interaction: discord.Interaction,
            name: str,
            role: discord.Role,
            channel: discord.TextChannel,
            kingdom_building: bool = False):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild.id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute("INSERT INTO Regions (Name, Role_ID, Channel_ID, kingdom_building) VALUES (?, ?, ?, ?)",
                                     (name, role.id, channel.id, kingdom_building))
                await db.commit()

                await interaction.followup.send(f"{name} has been added as a region.", ephemeral=True)

        except (aiosqlite.Error, ValueError) as e:
            logging.exception(f"an issue occurred in the add_region command: {e}")

            await interaction.followup.send(
                f"An error occurred whilst responding. Please try again later.", ephemeral=True)

    @region_group.command(name='remove', description='Remove a region from the server')
    @app_commands.autocomplete(name=shared_functions.region_autocomplete)
    async def remove_region(
            self,
            interaction: discord.Interaction,
            name: str):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild.id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute("DELETE FROM Regions WHERE Name = ?", (name,))
                await cursor.execute("DELETE FROM Regions_Level_Range WHERE Name = ?", (name,))
                await db.commit()

                await interaction.followup.send(f"{name} has been removed as a region.", ephemeral=True)

        except (aiosqlite.Error, ValueError) as e:
            logging.exception(f"an issue occurred in the remove_region command: {e}")

            await interaction.followup.send(
                f"An error occurred whilst responding. Please try again later.", ephemeral=True)

    @region_group.command(name='edit', description='Edit a region on the server')
    @app_commands.autocomplete(old_name=shared_functions.region_autocomplete)
    async def edit_region(
            self,
            interaction: discord.Interaction,
            old_name: str,
            new_name: typing.Optional[str],
            role: typing.Optional[discord.Role],
            channel: typing.Optional[discord.TextChannel],
            kingdom_building: typing.Optional[bool]):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild.id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute("SELECT Role_ID, Channel_ID, Kingdom_Building FROM Regions WHERE Name = ?", (old_name,))
                region = await cursor.fetchone()
                if not region:
                    await interaction.followup.send(f"{old_name} is not a region.", ephemeral=True)
                    return
                else:
                    (role_id, channel_id, old_kingdom_building) = region
                    role = role.id if role is not None else role_id
                    channel = channel.id if channel is not None else channel_id
                    kingdom_building = kingdom_building if kingdom_building is not None else old_kingdom_building
                    if new_name:
                        await cursor.execute("Update Regions_Level_Range set Name = ? WHERE Name = ?",
                                             (new_name, old_name))
                        content = f"{old_name} has been edited as a region to be {new_name}."
                    else:
                        content = f"{old_name} has been edited as a region."
                    new_name = new_name if new_name is not None else old_name
                    await cursor.execute("UPDATE Regions SET Name = ?, Role_ID = ?, Channel_ID = ?, Kingdom_Building = ? WHERE Name = ?",
                                         (new_name, role, channel, kingdom_building, old_name))
                    await db.commit()
                await interaction.followup.send(content, ephemeral=True)

        except (aiosqlite.Error, ValueError) as e:
            logging.exception(f"an issue occurred in the edit_region command: {e}")

            await interaction.followup.send(
                f"An error occurred whilst responding. Please try again later {e}.", ephemeral=True)

    @region_group.command(name='level_range', description='Add a level range to a region')
    @app_commands.autocomplete(region=shared_functions.region_autocomplete)
    async def add_level_range(
            self, interaction: discord.Interaction,
            region: str,
            min_level: int,
            max_level: int,
            role: discord.Role):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild.id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute("SELECT 1 FROM Regions WHERE Name = ?", (region,))
                region_validation = await cursor.fetchone()
                if not region_validation:
                    await interaction.followup.send(f"{region} is not a region.", ephemeral=True)
                    return
                if min_level > max_level:
                    await interaction.followup.send(f"Minimum level must be less than maximum level.", ephemeral=True)
                    return
                await cursor.execute(
                    "SELECT MIN(Level), MAX(Level) from Milestone_System WHERE LEVEL >= ? AND LEVEL <= ?",
                    (min_level, max_level))
                levels = await cursor.fetchone()
                content = ""
                (min_stored_level, max_stored_level) = levels
                if min_level != min_stored_level or max_level != max_stored_level:
                    await interaction.followup.send(
                        f"Levels {min_level} to {max_level} are not valid levels as compared to the minimum {min_stored_level} and maximum {min_stored_level} stored levels in the milestone system.",
                        ephemeral=True)
                    return
                await cursor.execute(
                    "Select name, min_level, max_level, Role_ID from regions_level_range where name = ? and max_level between ? and ?",
                    (region, min_level, max_level))
                below_ranges = await cursor.fetchall()
                print(below_ranges)
                content = ""
                if below_ranges:
                    below_result = await update_region_level_range(interaction=interaction, region=region,
                                                               min_level=min_level, max_level=max_level, role=role,
                                                               level_range_info=below_ranges, database_conn=db)
                    if isinstance(below_result, str):
                        content += below_result
                    else:
                        return
                await cursor.execute("Select name, min_level, max_level, Role_ID from regions_level_range where name = ? and min_level between ? AND ?",
                        (region, min_level, max_level))

                above_ranges = await cursor.fetchall()
                if above_ranges:
                    above_result = await update_region_level_range(interaction=interaction, region=region,
                                                                   min_level=min_level, max_level=max_level, role=role,
                                                                   level_range_info=above_ranges, database_conn=db)
                    if isinstance(above_result, str):
                        content = below_result
                        content += f"{above_result}"
                    else:
                        return
                await cursor.execute(
                    "INSERT INTO Regions_Level_Range (Name, Min_Level, Max_Level, Role_ID) VALUES (?, ?, ?, ?)",
                    (region, min_level, max_level, role.id))
                await cursor.execute("SELECT Player_ID from Player_Characters where region = ? and level >= ? and level <= ?",
                                     (region, min_level, max_level))
                await db.commit()
                players = await cursor.fetchall()
                for player in players:
                    await interaction.guild.get_member(player[0]).add_roles(role)
                content += f"{region} has been granted the ranges of {min_level}-{max_level} with the role {role}."
                await interaction.followup.send(content, ephemeral=True)
        except (aiosqlite.Error, ValueError) as e:
            logging.exception(f"an issue occurred in the add_region command: {e}")

            await interaction.followup.send(
                f"An error occurred whilst responding. Please try again later. {e}", ephemeral=True)

    @admin_group.command(name='reset_roles', description='Reset all assigned in the server')
    async def reset_roles(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild.id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute("SELECT Name, Role_ID FROM Regions where name not in ('Illu', 'Kotima', 'Heim', 'Bayt')")
                roles = await cursor.fetchall()
                for role in roles:
                    (role_name, role_id) = role
                    print("the region is", role_name)
                    guild = interaction.guild
                    role_snowflake = guild.get_role(role_id)
                    members_in_role = role_snowflake.members
                    for member in members_in_role:
                        await member.remove_roles(role_snowflake)
                    print("THIS ROLE SNOWFLAKE HAS THE FOLLOWINGS MEMBERS", role_snowflake.members)
                    await cursor.execute("Select Role_ID, Min_Level, Max_level from Regions_Level_Range where name = ?", (role_name,))
                    region_role_ids = await cursor.fetchall()
                    for region_role_id in region_role_ids:
                        (role_id, min_level, max_level) = region_role_id

                        range_role_snowflake = guild.get_role(role_id)
                        range_members_in_role = range_role_snowflake.members
                        for member in range_members_in_role:
                            await member.remove_roles(range_role_snowflake)
                        print(range_role_snowflake.members)
                        await cursor.execute("Select player_name, player_id from Player_Characters where region = ? and level between ? and ? group by player_name",
                                             (role_name, min_level, max_level))
                        players = await cursor.fetchall()
                        print(f"region range for {role_name} is min level: {min_level} and max level: {max_level}")
                        print(players)
                        for player in players:
                            (player_name, player_id) = player
                            print(player_id)
                            player_snowflake = guild.get_member(player_id)
                            if not player_snowflake:
                                logging.info("PLAYER OF ID {} NOT FOUND".format(player_id))
                            else:
                                await player_snowflake.add_roles(range_role_snowflake, role_snowflake)

                await interaction.followup.send(f"All roles have been reset.", ephemeral=True)
        except (aiosqlite.Error, ValueError) as e:
            logging.exception(f"an issue occurred in the reset_roles command: {e}")

            await interaction.followup.send(
                f"An error occurred whilst responding. Please try again later. {e}", ephemeral=True)

class MilestoneDisplayView(shared_functions.ShopView):
    def __init__(self, user_id: int, guild_id: int, offset: int, limit: int, interaction: discord.Interaction):
        super().__init__(user_id, guild_id, offset, limit, content="", interaction=interaction)
        self.max_items = None  # Cache total number of items

    async def update_results(self):
        """fetch the level information."""
        statement = """
            SELECT Level, Minimum_Milestones, Milestones_to_level, easy, medium, hard, deadly, WPL, WPL_Heroic, Level_range_name, Level_Range_ID
            FROM Milestone_System   
            ORDER BY LEVEL ASC LIMIT ? OFFSET ? 
        """
        async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
            cursor = await db.execute(statement, (self.limit, self.offset - 1))
            self.results = await cursor.fetchall()

    async def create_embed(self):
        """Create the embed for the levels."""
        current_page = (self.offset // self.limit) + 1
        total_pages = ((await self.get_max_items() - 1) // self.limit) + 1
        self.embed = discord.Embed(title=f"Milestone System",
                                   description=f"Page {current_page} of {total_pages}")
        for level in self.results:
            (level, minimum_milestones, milestones_to_level, easy, medium, hard, deadly, wpl, wpl_heroic,
             level_range_name,
             level_range_id) = level
            self.embed.add_field(name=f'**Level**: {level}',
                                 value=f'**Milestone Info**: Minimum Milestones: {minimum_milestones}, Milestones to level: {milestones_to_level}\r\n'
                                       f'**Difficulty Rewards**: Easy: {easy}, Medium: {medium}, Hard: {hard}, Deadly: {deadly}\r\n'
                                       f'**Base Wealth**: WPL: {wpl}, WPL Heroic: {wpl_heroic}\r\n'
                                       f'**Level Range**: {level_range_name} <@{level_range_id}>',
                                 inline=False)

    async def get_max_items(self):
        """Get the total number of levels."""
        if self.max_items is None:
            async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
                cursor = await db.execute("SELECT COUNT(*) FROM Milestone_System")
                count = await cursor.fetchone()
                self.max_items = count[0]
        return self.max_items


class MythicDisplayView(shared_functions.ShopView):
    def __init__(self, user_id: int, guild_id: int, offset: int, limit: int, interaction: discord.Interaction):
        super().__init__(user_id=user_id, guild_id=guild_id, offset=offset, limit=limit, content="",
                         interaction=interaction)
        self.max_items = None  # Cache total number of items

    async def update_results(self):
        """fetch the level information."""
        statement = """
            SELECT Tier, Trials, Trials_Required
            FROM AA_Trials   
            ORDER BY Tier ASC LIMIT ? OFFSET ? 
        """
        async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
            cursor = await db.execute(statement, (self.limit, self.offset - 1))
            self.results = await cursor.fetchall()

    async def create_embed(self):
        """Create the embed for the levels."""
        current_page = (self.offset // self.limit) + 1
        total_pages = ((await self.get_max_items() - 1) // self.limit) + 1
        self.embed = discord.Embed(title=f"Mythic System",
                                   description=f"Page {current_page} of {total_pages}")
        for tier in self.results:
            (tier, trials, trials_required) = tier
            self.embed.add_field(name=f'**Mythic Tier**: {tier}',
                                 value=f'**Minimum Trials:**: {trials}, Milestones to increase tier: {trials_required}',
                                 inline=False)

    async def get_max_items(self):
        """Get the total number of levels."""
        if self.max_items is None:
            async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
                cursor = await db.execute("SELECT COUNT(*) FROM AA_Trials")
                count = await cursor.fetchone()
                self.max_items = count[0]
        return self.max_items


class RPStoreView(shared_functions.ShopView):
    def __init__(self, user_id: int, guild_id: int, offset: int, limit: int, interaction: discord.Interaction):
        super().__init__(user_id=user_id, guild_id=guild_id, offset=offset, limit=limit, content="",
                         interaction=interaction)
        self.max_items = None  # Cache total number of items

    async def update_results(self):
        """fetch the level information."""
        statement = """
            SELECT Item_ID, name, price, description, stock_remaining, inventory, usable, sellable, custom_message,
            matching_requirements, Requirements_1_type, Requirements_1_pair, Requirements_2_type, Requirements_2_pair, Requirements_3_type, Requirements_3_pair,
            actions_1_type, actions_1_subtype, actions_1_behavior, actions_2_type, actions_2_subtype, actions_2_behavior, actions_3_type, actions_3_subtype, actions_3_behavior,
            image_link
            FROM RP_Store_Items
            ORDER BY Item_ID ASC LIMIT ? OFFSET ?
        """
        async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
            cursor = await db.execute(statement, (self.limit, self.offset - 1))
            self.results = await cursor.fetchall()

    async def create_embed(self):
        """Create the embed for the levels."""

        current_page = (self.offset // self.limit) + 1
        total_pages = ((await self.get_max_items() - 1) // self.limit) + 1
        self.embed = discord.Embed(title=f"Item List System",
                                   description=f"Page {current_page} of {total_pages}")
        for item in self.results:
            (item_ID, name, price, description, stock_remaining, inventory, usable, sellable, custom_message,
             matching_requirements, requirements_1_type, requirements_1_pair, requirements_2_type, requirements_2_pair,
             requirements_3_type, requirements_3_pair,
             actions_1_type, actions_1_subtype, actions_1_behavior, actions_2_type, actions_2_subtype,
             actions_2_behavior, actions_3_type, actions_3_subtype, actions_3_behavior,
             image_link) = item
            content = f'**Price**: {price}, **Stock Remaining**: {stock_remaining}, **Inventory**: {inventory}\r\n' \
                      f'**Usable**: {usable}, **Sellable**: {sellable}\r\n'
            content += f'**Custom Message On Use**: {custom_message}\r\n'
            self.embed.add_field(name=f'**Item Name**: {name}: **ID**: {item_ID}',
                                 value=content, inline=False)
            requirements_group = (
                requirements_1_type, requirements_2_type, requirements_3_type, requirements_1_pair, requirements_2_pair,
                requirements_3_pair)
            actions_group = (
                actions_1_type, actions_2_type, actions_3_type, actions_1_subtype, actions_2_subtype, actions_3_subtype,
                actions_1_behavior, actions_2_behavior, actions_3_behavior)
            additional_content = ""
            if any(requirements_group):
                additional_content += "**Requirements**: {matching_requirements}\r\n"
                additional_content += f'**Requirement 1**: {requirements_1_type}, {requirements_1_pair}\r\n' if requirements_1_type else ""
                additional_content += f'**Requirement 2**: {requirements_2_type}, {requirements_2_pair}\r\n' if requirements_2_type else ""
                additional_content += f'**Requirement 3**: {requirements_3_type}, {requirements_3_pair}\r\n' if requirements_3_type else ""
            if any(actions_group):
                additional_content += f'**Action 1**: {actions_1_type}, {actions_1_subtype}, {actions_1_behavior}\r\n' if actions_1_type else ""
                additional_content += f'**Action 2**: {actions_2_type}, {actions_2_subtype}, {actions_2_behavior}\r\n' if actions_2_type else ""
                additional_content += f'**Action 3**: {actions_3_type}, {actions_3_subtype}, {actions_3_behavior}\r\n' if actions_3_type else ""
            self.embed.add_field(name=f'**Additional Info**',
                                 value=additional_content, inline=False)

    async def get_max_items(self):
        """Get the total number of levels."""
        if self.max_items is None:
            async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
                cursor = await db.execute("SELECT COUNT(*) FROM RP_Store_Items")
                count = await cursor.fetchone()
                self.max_items = count[0]
        return self.max_items


# *** DUAL VIEWS ***
class ArchiveDisplayView(shared_functions.DualView):
    def __init__(self, user_id: int, guild_id: int, offset: int, limit: int, player_name: str, character_name: str,
                 view_type: int, interaction: discord.Interaction):
        super().__init__(user_id=user_id, guild_id=guild_id, offset=offset, limit=limit, view_type=view_type,
                         content="", interaction=interaction)
        self.max_items = None  # Cache total number of items
        self.character_name = character_name
        self.view_type = view_type
        self.player_name = player_name

    async def update_results(self):
        """Fetch the history of prestige request  for the current page."""
        try:
            if not self.player_name:
                statement = """SELECT player_name, player_id, True_Character_Name, Title, Titles, Description, Oath, Level, 
                                Milestones, Tier, Trials, Gold, Gold_Value, Gold_Value_Max,
                                Essence, Fame, Prestige, Mythweavers, Image_Link, Tradition_Name, 
                                Tradition_Link, Template_Name, Template_Link, Article_Link
                                FROM Archive_Player_Characters ORDER BY True_Character_Name ASC LIMIT ? OFFSET ?"""
                val = (self.limit, self.offset - 1)

            else:
                statement = """SELECT player_name, player_id, True_Character_Name, Title, Titles, Description, Oath, Level, 
                                Milestones, Tier, Trials, Gold, Gold_Value, Gold_Value_Max,
                                Essence, Fame, Prestige, Mythweavers, Image_Link, Tradition_Name, 
                                Tradition_Link, Template_Name, Template_Link, Article_Link
                                FROM Archive_Player_Characters WHERE Player_Name = ? ORDER BY True_Character_Name ASC LIMIT ? OFFSET ? """
                val = (self.player_name, self.limit, self.offset - 1)
            async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
                cursor = await db.execute(statement, val)
                self.results = await cursor.fetchall()
        except aiosqlite.Error as e:
            logging.exception(
                f"An error occurred whilst fetching data for the archive! input values of player_name: {self.player_name}, character_name: {self.character_name}': {e}"
            )

    async def create_embed(self):
        """Create the embed for the titles."""
        if self.view_type == 1:
            if not self.player_name:
                current_page = (self.offset // self.limit) + 1
                total_pages = ((await self.get_max_items() - 1) // self.limit) + 1
                self.embed = discord.Embed(title=f"Character Summary",
                                           description=f"Page {current_page} of {total_pages}")
            else:
                current_page = (self.offset // self.limit) + 1
                total_pages = ((await self.get_max_items() - 1) // self.limit) + 1
                self.embed = discord.Embed(title=f"Character Summary for {self.player_name}",
                                           description=f"Page {current_page} of {total_pages}")
            for result in self.results:
                (player_name, player_id, true_character_name, title, titles, description, oath, level,
                 milestones, tier, trials, gold, gold_value, gold_value_max,
                 essence, fame, prestige, mythweavers, image_link, tradition_name,
                 tradition_link, template_name, template_link, article_link) = result
                self.embed.add_field(name=f'Character Name', value=f'**Name**:{true_character_name}')
                self.embed.add_field(name=f'Information',
                                     value=f'**Level**: {level}, **Mythic Tier**: {tier}')
                self.embed.add_field(name=f'Total Experience',
                                     value=f'**Milestones**: {milestones}, **Trials**: {trials}')
                self.embed.add_field(name=f'Current Wealth', value=f'**GP**: {gold}, **Essence**: {essence}')
                linkage = None
                if not tradition_name:
                    linkage += f"**Tradition**: [{tradition_name}]({tradition_link})"
                if not template_link:
                    if not tradition_name:
                        linkage += f" "
                    linkage += f"**Template**: [{template_name}]({template_link})"
                if not tradition_name or not template_name:
                    self.embed.add_field(name=f'Additional Info', value=linkage, inline=False)
        else:
            current_page = (self.offset // self.limit) + 1
            total_pages = ((await self.get_max_items() - 1) // self.limit) + 1
            for result in self.results:
                (player_name, player_id, true_character_name, title, titles, description, oath, level,
                 milestones, tier, trials, gold, gold_value, gold_value_max,
                 essence, fame, prestige, mythweavers, image_link, tradition_name,
                 tradition_link, template_name, template_link, article_link) = result
                self.embed = discord.Embed(title=f"Detailed view for {true_character_name}",
                                           description=f"Page {current_page} of {total_pages}")
                self.embed.set_author(name=f'{player_name}')
                self.embed.set_thumbnail(url=f'{image_link}')
                self.embed.add_field(name=f'Character Name', value=f'**Name**:{true_character_name}')
                self.embed.add_field(name=f'Information',
                                     value=f'**Level**: {level}, **Mythic Tier**: {tier}')
                self.embed.add_field(name=f'Total Experience',
                                     value=f'**Milestones**: {milestones}, **Trials**: {trials},')
                self.embed.add_field(name=f'Current Wealth',
                                     value=f'**GP**: {gold}, **Illiquid GP**: {gold_value - gold} **Essence**: {essence}')
                self.embed.add_field(name=f'Fame and Prestige', value=f'**Fame**: {fame}, **Prestige**: {prestige}')
                linkage = None
                if not tradition_name:
                    linkage += f"**Tradition**: [{tradition_name}]({tradition_link})"
                if not template_link:
                    if not tradition_name:
                        linkage += f" "
                    linkage += f"**Template**: [{template_name}]({template_link})"
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
                if not self.player_name:
                    cursor = await db.execute("SELECT COUNT(*) FROM Archive_Player_Characters")
                else:
                    cursor = await db.execute("SELECT COUNT(*) FROM Archive_Player_Characters WHERE Player_Name = ?",
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


class SettingDisplayView(shared_functions.DualView):
    def __init__(self, user_id: int, guild_id: int, offset: int, limit: int, view_type: int,
                 interaction: discord.Interaction):
        super().__init__(user_id=user_id, guild_id=guild_id, offset=offset, limit=limit, view_type=view_type,
                         content="", interaction=interaction)
        self.max_items = None  # Cache total number of items
        self.view_type = view_type

    async def update_results(self):
        """Fetch the history of prestige request  for the current page."""
        try:
            statement = """SELECT Search, Type, Identifier, Description FROM Admin Limit ? OFFSET ?"""
            val = (self.limit, self.offset - 1)

            async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
                cursor = await db.execute(statement, val)
                self.results = await cursor.fetchall()
        except Exception as e:
            logging.exception(
                f"An error occurred whilst fetching data and creating views! {e}"
            )

    async def create_embed(self):
        """Create the embed for the titles."""
        try:
            if self.view_type == 1:

                current_page = (self.offset // self.limit) + 1
                total_pages = ((await self.get_max_items() - 1) // self.limit) + 1
                self.embed = discord.Embed(title=f"Settings Summary",
                                           description=f"Page {current_page} of {total_pages}")
                for result in self.results:
                    (search, data_type, identifier, description) = result
                    self.embed.add_field(name=f'{data_type}: {identifier}',
                                         value=f'current setting: {search}\r\n{description}',
                                         inline=False)
            else:
                current_page = (self.offset // self.limit) + 1
                total_pages = ((await self.get_max_items() - 1) // self.limit) + 1
                for result in self.results:
                    (search, data_type, identifier, description) = result
                    self.embed = discord.Embed(title=f"Setting Details",
                                               description=f"Page {current_page} of {total_pages}")
                    self.embed.add_field(name=f'{data_type}: {identifier}',
                                         value=f'current setting: {search}\r\n{description}',
                                         inline=False)
        except Exception as e:
            logging.exception(
                f"An error occurred whilst fetching data and creating views! {e}"
            )

    async def get_max_items(self):
        """Get the total number of titles."""
        try:
            if self.max_items is None:
                async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
                    cursor = await db.execute("SELECT COUNT(*) FROM Admin")
                    count = await cursor.fetchone()
                    self.max_items = count[0]
            return self.max_items
        except Exception as e:
            logging.exception(
                f"An error occurred whilst fetching data and creating views! {e}"
            )

    async def on_view_change(self):
        try:
            self.view_type = 1 if self.view_type == 2 else 2
            if self.view_type == 1:
                self.limit = 20  # Change the limit to 20 for the summary view
            else:
                self.limit = 1  # Change the limit to 1 for the detailed view
        except Exception as e:
            logging.exception(
                f"An error occurred whilst fetching data and creating views! {e}"
            )

        # *** ACKNOWLEDGEMENT VIEWS ***


class ResetDatabaseView(shared_functions.SelfAcknowledgementView):
    def __init__(self, content: str, interaction: discord.Interaction):
        super().__init__(content=content, interaction=interaction)
        self.embed = None

    async def accepted(self, interaction: discord.Interaction):
        """Handle the approval logic."""
        # Update the database to mark the proposition as accepted
        # Adjust prestige, log the transaction, notify the requester, etc.
        self.embed = discord.Embed(
            title="Database Reset Successful",
            description=f"{interaction.user.name} actually wanted me gone. :'(",
            color=discord.Color.green()
        )
        time = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        shutil.copyfile(f"C:/pathparser/pathparser_{interaction.guild.id}.sqlite",
                        f"C:/pathparser/pathparser_{interaction.guild.id}_{time}.sqlite")
        shutil.copyfile(f"C:/pathparser/pathparser.sqlite",
                        f"C:/pathparser/pathparser_{interaction.guild.id}.sqlite")

        # Additional logic such as notifying the requester

    async def rejected(self, interaction: discord.Interaction):
        """Handle the rejection logic."""
        # Update the database to mark the proposition as rejected
        self.embed = discord.Embed(
            title="Database Reset Rejected",
            description=f"{interaction.user.name} has decided to keep me around. :)",
            color=discord.Color.red()
        )
        # Additional logic such as notifying the requester

    async def create_embed(self):
        """Create the initial embed for the proposition."""
        self.embed = discord.Embed(
            title="Database Reset",
            description="Are you sure you want to reset the database? This action is inconvenient to reverse and may result in data inconsistency.",
            color=discord.Color.blue()
        )


class ArchiveCharactersView(shared_functions.SelfAcknowledgementView):
    def __init__(self, retirement_type, player_name: typing.Optional[str], character_name: typing.Optional[str],
                 guild: discord.Guild, accepted_bio_channel: int, content: str, interaction: discord.Interaction):
        super().__init__(content=content, interaction=interaction)
        self.embed = None
        self.retirement_type = retirement_type
        self.player_name = player_name
        self.character_name = character_name
        self.guild = guild
        self.accepted_bio_channel = accepted_bio_channel
        self.items_to_be_archived = []
        self.items_to_be_deleted = []
        self.results = None

    async def accepted(self, interaction: discord.Interaction):
        """Handle the approval logic."""
        # Update the database to mark the proposition as accepted
        # Adjust prestige, log the transaction, notify the requester, etc.
        self.embed = discord.Embed(
            title="Archive Attempt",
            description=f"{interaction.user.name} has successfully archived the following characters.",
            color=discord.Color.green()
        )
        self.embed.add_field(name=f'Characters Archived', value=f'{self.items_to_be_archived}')
        async with aiosqlite.connect(f"pathparser_{self.guild.id}.sqlite") as conn:
            cursor = await conn.cursor()
            placeholders = ', '.join(
                '?' for _ in self.items_to_be_archived)  # Create the correct number of placeholders
            query = (f"""INSERT INTO Archive_Player_Characters (Player_ID, Player_Name, True_Character_Name, Title, Titles, Description, Oath, Level, Milestones, Tier, Trials, Gold, Gold_Value, Gold_Value_Max, Essence, Fame, Prestige, Mythweavers, Image_Link, Tradition_Name, Tradition_Link, Template_Name, Template_Link, Article_Link)
                        SELECT Player_ID, Player_Name, True_Character_Name, Title, Titles, Description, Oath, Level, Milestones, Tier, Trials, Gold, Gold_Value, Gold_Value_Max, Essence, Fame, Prestige, Mythweavers, Image_Link, Tradition_Name, Tradition_Link, Template_Name, Template_Link, Article_Link
                        FROM Player_Characters WHERE Character_Name IN ({placeholders})""")
            await cursor.execute(query, self.items_to_be_archived)
            await conn.commit()
            bio_channel = self.guild.get_channel(self.accepted_bio_channel)
            if not bio_channel:
                bio_channel = await self.guild.fetch_channel(self.accepted_bio_channel)
            for item in self.items_to_be_deleted:
                message = await bio_channel.fetch_message(item[0])
                await message.delete()
                logging_thread = self.guild.get_channel(item[1])
                if not logging_thread:
                    logging_thread = await self.guild.fetch_channel(item[1])
                await logging_thread.send("Character has been archived.")
        # Additional logic such as notifying the requester

    async def rejected(self, interaction: discord.Interaction):
        """Handle the rejection logic."""
        # Update the database to mark the proposition as rejected
        self.embed = discord.Embed(
            title="Database Reset Rejected",
            description=f"{interaction.user.name} has decided to keep me around. :)",
            color=discord.Color.red()
        )
        # Additional logic such as notifying the requester

    async def create_embed(self):
        """Create the initial embed for the proposition."""
        self.embed = discord.Embed(
            title="Character Archive",
            description="Are you sure you want to Archive the following characters?",
            color=discord.Color.blue()
        )
        async with aiosqlite.connect(f"pathparser_{self.guild.id}.sqlite") as conn:
            cursor = await conn.cursor()
            try:
                if self.retirement_type == 1:
                    await cursor.execute(
                        "SELECT True_Character_Name, Message_ID, Thread_ID  FROM Player_Characters WHERE Player_Name = ?",
                        (self.player_name,))
                    results = await cursor.fetchall()
                    for result in results:
                        self.items_to_be_archived.append(result[0])
                        self.items_to_be_deleted.append((result[1], result[2]))
                        self.embed.add_field(name=f'{result[0]}', value=f'**Player**: {self.player_name}')
                elif self.retirement_type == 2:
                    await cursor.execute(
                        "SELECT True_Character_Name, Message_ID, Thread_ID  FROM Player_Characters WHERE Character_Name = ?",
                        (self.character_name,))
                    results = await cursor.fetchone()
                    self.items_to_be_archived.append(results[0])
                    self.items_to_be_deleted.append((results[1], results[2]))
                    self.embed.add_field(name=f'{results[0]}', value=f'**Player**: {self.player_name}')
                else:
                    await cursor.execute("SELECT DISTINCT(Player_ID)  FROM Player_Characters")
                    player_ids = await cursor.fetchall()
                    for player_id in player_ids:
                        find_player = await self.guild.fetch_member(player_id[0])
                        if not find_player:
                            character_list = ''
                            await cursor.execute(
                                "SELECT True_Character_Name, Message_ID, Thread_ID  FROM Player_Characters WHERE Player_ID = ?",
                                (player_id[0],))
                            results = await cursor.fetchall()
                            for result in results:
                                self.items_to_be_archived.append(result[0])
                                self.items_to_be_deleted.append((result[1], result[2]))
                                character_list += f'{result[0]}\r\n'
                            self.embed.add_field(name=f'**Player**: {find_player.name}', value=character_list)
            except (aiosqlite.Error, TypeError, ValueError, NameError) as e:
                logging.exception(
                    f"An error occurred whilst archiving characters! ViewType: {self.retirement_type} input values of player_name: {self.player_name}, character_name: {self.character_name}': {e}"
                )
                self.embed = discord.Embed(
                    title='Error',
                    description=f"An error occurred whilst archiving characters. Please try again later.",
                )


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s [%(filename)s:%(lineno)d] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    filename='pathparser.log',  # Specify the log file name
    filemode='a'  # Append mode
)
