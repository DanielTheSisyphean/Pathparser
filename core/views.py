import datetime

import discord
import logging
import typing
import aiosqlite
from core.threads import silent_close_thread, claim_thread
from .config import config_cache
from decimal import Decimal
import random
from core.character import CharacterChange, UpdateCharacterData, update_character, gold_calculation
from core.display import character_embed, log_embed
from core.utils import get_gold_breakdown


class ShopView(discord.ui.View):
    """Base class for shop views with pagination."""

    def __init__(self, user_id: int, guild_id: int, offset: int, limit: int, interaction: discord.Interaction,
                 content: typing.Optional[str]):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.content = content
        self.message = None
        self.interaction = interaction
        self.guild_id = guild_id
        self.offset = offset
        self.limit = limit
        self.results = []
        self.embed = None

        self.message = None
        # Initialize buttons
        self.first_page_button = discord.ui.Button(label='First Page', style=discord.ButtonStyle.primary)
        self.previous_page_button = discord.ui.Button(label='Previous Page', style=discord.ButtonStyle.primary)
        self.next_page_button = discord.ui.Button(label='Next Page', style=discord.ButtonStyle.primary)
        self.last_page_button = discord.ui.Button(label='Last Page', style=discord.ButtonStyle.primary)

        self.first_page_button.callback = self.first_page
        self.previous_page_button.callback = self.previous_page
        self.next_page_button.callback = self.next_page
        self.last_page_button.callback = self.last_page

        self.add_item(self.first_page_button)
        self.add_item(self.previous_page_button)
        self.add_item(self.next_page_button)
        self.add_item(self.last_page_button)

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
        if self.offset == 1:
            await interaction.response.send_message("You are already on the first page.", ephemeral=True)
            return
        self.offset = 1
        await self.update_results()
        await self.create_embed()
        await self.update_buttons()
        await interaction.edit_original_response(
            embed=self.embed,
            view=self
        )

    async def previous_page(self, interaction: discord.Interaction):
        """Handle moving to the previous page."""
        await interaction.response.defer()
        if self.offset > 1:
            self.offset -= self.limit
            if self.offset < 1:
                self.offset = 1
            await self.update_results()
            await self.create_embed()
            await self.update_buttons()
            await interaction.edit_original_response(
                embed=self.embed,
                view=self
            )
        else:
            await interaction.followup.send("You are on the first page.", ephemeral=True)

    async def next_page(self, interaction: discord.Interaction):
        """Handle moving to the next page."""
        await interaction.response.defer()
        max_items = await self.get_max_items()
        if self.offset + self.limit - 1 < max_items:
            self.offset += self.limit
            await self.update_results()
            await self.create_embed()
            await self.update_buttons()
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
        last_page_offset = ((max_items - 1) // self.limit) * self.limit + 1
        if self.offset != last_page_offset:
            self.offset = last_page_offset
            await self.update_results()
            await self.create_embed()
            await self.update_buttons()
            await interaction.edit_original_response(
                embed=self.embed,
                view=self
            )
        else:
            await interaction.followup.send("You are on the last page.", ephemeral=True)

    async def update_buttons(self):
        """Update the enabled/disabled state of buttons based on the current page."""
        max_items = await self.get_max_items()
        first_page = self.offset == 1
        last_page = self.offset + self.limit - 1 >= max_items

        self.first_page_button.disabled = first_page
        self.previous_page_button.disabled = first_page
        self.next_page_button.disabled = last_page
        self.last_page_button.disabled = last_page

    async def send_initial_message(self):
        """Send the initial message with the view."""
        try:
            await self.update_results()
            await self.create_embed()
            await self.update_buttons()
            await self.interaction.followup.send(
                content=self.content,
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
                await self.message.edit(content=self.content, embed=self.embed, view=self)
            except discord.HTTPException as e:
                logging.error(f"Failed to edit message on timeout: {e}")

    async def update_results(self):
        """Fetch the results for the current page. To be implemented in subclasses."""
        raise NotImplementedError

    async def create_embed(self):
        """Create the embed for the current page. To be implemented in subclasses."""
        raise NotImplementedError

    async def get_max_items(self):
        """Get the total number of items. To be implemented in subclasses."""
        raise NotImplementedError


class RecipientAcknowledgementView(discord.ui.View):
    """Base class for views requiring acknowledgment."""

    def __init__(self, allowed_user_id: int, content: typing.Optional, interaction: discord.Interaction):
        super().__init__(timeout=7200)
        self.allowed_user_id = allowed_user_id
        self.embed = None
        self.content = content
        self.message = None
        self.interaction = interaction
        # Initialize buttons
        self.accept_button = discord.ui.Button(label='Accept', style=discord.ButtonStyle.primary)
        self.reject_button = discord.ui.Button(label='Reject', style=discord.ButtonStyle.danger)

        self.accept_button.callback = self.accept
        self.reject_button.callback = self.reject

        self.add_item(self.accept_button)
        self.add_item(self.reject_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Ensure that only the allowed user can interact with the buttons."""
        if interaction.user.id != self.allowed_user_id:
            await interaction.response.send_message(
                "You cannot interact with this button.",
                ephemeral=True
            )
            return False
        return True

    async def accept(self, interaction: discord.Interaction):
        """Handle the accept action."""
        await interaction.response.defer(thinking=True)
        await self.accepted(interaction)
        await interaction.edit_original_response(
            embed=self.embed,
            view=None
        )

    async def reject(self, interaction: discord.Interaction):
        """Handle the reject action."""
        await interaction.response.defer(thinking=True)
        await self.rejected(interaction)
        await interaction.edit_original_response(
            embed=self.embed,
            view=None
        )

    async def send_initial_message(self):
        """Send the initial message with the view."""
        await self.create_embed()
        try:
            async with config_cache.lock:
                configs = config_cache.cache.get(self.interaction.guild_id)
                if configs:
                    channel_id = configs.get('Character_Transaction_Channel')

                    if channel_id is None:
                        await self.interaction.followup.send(
                            "Character Transaction Channel not found in the database.",
                            ephemeral=True
                        )
                        return
                    channel = self.interaction.guild.get_channel(int(channel_id))
                    if not channel:
                        channel = await self.interaction.guild.fetch_channel(int(channel_id))
                    if channel:
                        self.message = await channel.send(
                            content=self.content,
                            embed=self.embed,
                            view=self
                        )
                        await self.interaction.followup.send(
                            f"Message sent to the Character Transaction Channel. {self.message.jump_url}",
                            ephemeral=True
                        )
                    else:
                        await self.interaction.followup.send(
                            content=self.content,
                            embed=self.embed,
                            view=self
                        )
        except (discord.HTTPException, AttributeError, aiosqlite.Error) as e:
            logging.error(f"Failed to send message: {e} in guild {self.interaction.guild.id}")
            await self.interaction.followup.send(
                "An error occurred while trying to send the message. Please try again later.",
                ephemeral=True
            )

    async def on_timeout(self):
        """Disable buttons when the view times out."""
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException as e:
                logging.error(f"Failed to edit message on timeout: {e}")

    async def accepted(self, interaction: discord.Interaction):
        """To be implemented in subclasses."""
        raise NotImplementedError

    async def rejected(self, interaction: discord.Interaction):
        """To be implemented in subclasses."""
        raise NotImplementedError

    async def create_embed(self):
        """To be implemented in subclasses."""
        raise NotImplementedError


class SelfAcknowledgementView(discord.ui.View):
    """Base class for views requiring self acknowledgment."""

    def __init__(self, content: typing.Optional, interaction: discord.Interaction):
        super().__init__(timeout=180)
        self.embed = None
        self.message = None
        self.content = content
        self.message = None
        self.interaction = interaction
        self.user_id = interaction.user.id

        # Initialize buttons
        self.accept_button = discord.ui.Button(label='Accept', style=discord.ButtonStyle.primary)
        self.reject_button = discord.ui.Button(label='Reject', style=discord.ButtonStyle.danger)

        self.accept_button.callback = self.accept
        self.reject_button.callback = self.reject

        self.add_item(self.accept_button)
        self.add_item(self.reject_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Ensure that only the user who initiated the view can interact with the buttons."""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "You cannot interact with this button.",
                ephemeral=True
            )
            return False
        return True

    async def send_initial_message(self):
        """Send the initial message with the view."""
        await self.create_embed()
        try:
            self.message = await self.interaction.followup.send(
                content=self.content,
                embed=self.embed,
                view=self
            )
        except (discord.HTTPException, AttributeError) as e:
            logging.error(f"Failed to send message: {e} in guild {self.interaction.guild.id} for {self.user_id}")

    async def on_timeout(self):
        """Disable buttons when the view times out."""
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(content=self.content, embed=self.embed, view=self)
            except (discord.HTTPException, AttributeError) as e:
                logging.error(
                    f"Failed to edit message on timeout for user {self.user_id} in guild {self.interaction.guild.id}: {e}")

    async def accept(self, interaction: discord.Interaction):
        """Handle the accept action."""
        await interaction.response.defer()
        await self.accepted(interaction)
        await interaction.edit_original_response(
            embed=self.embed,
            view=None
        )

    async def reject(self, interaction: discord.Interaction):
        """Handle the reject action."""
        await interaction.response.defer()
        await self.rejected(interaction)
        await interaction.edit_original_response(
            embed=self.embed,
            view=None
        )

    async def accepted(self, interaction: discord.Interaction):
        """To be implemented in subclasses."""
        raise NotImplementedError

    async def rejected(self, interaction: discord.Interaction):
        """To be implemented in subclasses."""
        raise NotImplementedError

    async def create_embed(self):
        """To be implemented in subclasses."""
        raise NotImplementedError


class DualView(discord.ui.View):
    """Base class for dual views (list/detail) with pagination."""

    def __init__(self, user_id, guild_id, offset, limit, view_type, content: typing.Optional,
                 interaction: discord.Interaction):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.guild_id = guild_id
        self.offset = offset
        self.limit = limit
        self.content = content
        self.message = None
        self.interaction = interaction
        self.results = []
        self.embed = None
        self.view_type = view_type

        # Initialize buttons
        self.first_page_button = discord.ui.Button(label='First Page', style=discord.ButtonStyle.primary)
        self.previous_page_button = discord.ui.Button(label='Previous Page', style=discord.ButtonStyle.primary)
        self.change_view_button = discord.ui.Button(label='Change View', style=discord.ButtonStyle.primary)
        self.next_page_button = discord.ui.Button(label='Next Page', style=discord.ButtonStyle.primary)
        self.last_page_button = discord.ui.Button(label='Last Page', style=discord.ButtonStyle.primary)

        self.first_page_button.callback = self.first_page
        self.previous_page_button.callback = self.previous_page
        self.change_view_button.callback = self.change_view
        self.next_page_button.callback = self.next_page
        self.last_page_button.callback = self.last_page

        self.add_item(self.first_page_button)
        self.add_item(self.previous_page_button)
        self.add_item(self.change_view_button)
        self.add_item(self.next_page_button)
        self.add_item(self.last_page_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Ensure that only the user who initiated the view can interact with the buttons."""
        try:
            if interaction.user.id != self.user_id:
                await interaction.response.send_message(
                    "You cannot interact with this button.",
                    ephemeral=True
                )
                return False
            return True
        except Exception as e:
            logging.error(f"Failed to check interaction: {e}")
            raise

    async def first_page(self, interaction: discord.Interaction):
        """Handle moving to the first page."""
        try:
            await interaction.response.defer()
            if self.offset == 1:
                await interaction.response.send_message("You are already on the first page.", ephemeral=True)
                return
            self.offset = 1
            await self.update_results()
            await self.create_embed()
            await self.update_buttons()
            await interaction.edit_original_response(
                embed=self.embed,
                view=self
            )
        except Exception as e:
            logging.error(f"Failed to move to the first page: {e}")
            raise

    async def previous_page(self, interaction: discord.Interaction):
        """Handle moving to the previous page."""
        try:
            await interaction.response.defer()
            if self.offset > 1:
                self.offset -= self.limit
                if self.offset < 1:
                    self.offset = 1
                await self.update_results()
                await self.create_embed()
                await self.update_buttons()
                await interaction.edit_original_response(
                    embed=self.embed,
                    view=self
                )
            else:
                await interaction.followup.send("You are on the first page.", ephemeral=True)
        except Exception as e:
            logging.error(f"Failed to move to the previous page: {e}")
            raise

    async def send_initial_message(self):
        """Send the initial message with the view."""
        try:

            await self.update_results()
            await self.create_embed()
            await self.update_buttons()

            self.message = await self.interaction.followup.send(
                content=self.content,
                embed=self.embed,
                view=self
            )
        except discord.HTTPException as e:
            logging.error(
                f"Failed to send message due to HTTPException: {e} in guild {self.interaction.guild.id} for {self.user_id}")
        except Exception as e:
            logging.error(f"Failed to send message: {e} in guild {self.interaction.guild.id} for {self.user_id}")

    async def on_timeout(self):
        """Disable buttons when the view times out."""
        try:
            for child in self.children:
                child.disabled = True
            if self.message:
                try:
                    await self.message.edit(content=self.content, embed=self.embed, view=self)
                except discord.HTTPException as e:
                    logging.error(f"Failed to edit message on timeout: {e}")

        except Exception as e:
            logging.error(f"Failed to disable buttons: {e}")
            raise

    async def change_view(self, interaction: discord.Interaction):
        """Change the view type."""
        await interaction.response.defer()
        try:
            await self.on_view_change()
            await self.update_results()
            await self.create_embed()
            await self.update_buttons()
            await interaction.edit_original_response(
                embed=self.embed,
                view=self
            )
        except Exception as e:
            logging.error(f"Failed to change view: {e}")
            raise

    async def next_page(self, interaction: discord.Interaction):
        """Handle moving to the next page."""
        try:
            await interaction.response.defer()
            max_items = await self.get_max_items()
            if self.offset + self.limit - 1 < max_items:
                self.offset += self.limit
                await self.update_results()
                await self.create_embed()
                await self.update_buttons()
                await interaction.edit_original_response(
                    embed=self.embed,
                    view=self
                )
            else:
                await interaction.response.send_message("You are on the last page.", ephemeral=True)
        except Exception as e:
            logging.error(f"Failed to move to the next page: {e}")
            raise

    async def last_page(self, interaction: discord.Interaction):
        """Handle moving to the last page."""
        try:
            await interaction.response.defer()
            max_items = await self.get_max_items()
            last_page_offset = ((max_items - 1) // self.limit) * self.limit + 1
            if self.offset != last_page_offset:
                self.offset = last_page_offset
                await self.update_results()
                await self.create_embed()
                await self.update_buttons()
                await interaction.edit_original_response(
                    embed=self.embed,
                    view=self
                )
            else:
                await interaction.response.send_message("You are on the last page.", ephemeral=True)
        except Exception as e:
            logging.error(f"Failed to move to the last page: {e}")
            raise

    async def update_buttons(self):
        """Update the enabled/disabled state of buttons based on the current page."""
        try:

            max_items = await self.get_max_items()

            first_page = self.offset == 1
            last_page = self.offset + self.limit - 1 >= max_items

            self.first_page_button.disabled = first_page
            self.previous_page_button.disabled = first_page
            self.next_page_button.disabled = last_page
            self.last_page_button.disabled = last_page
        except Exception as e:
            logging.error(f"Failed to update buttons: {e}")
            raise

    async def on_view_change(self):
        """Change the view type."""
        raise NotImplementedError

    async def update_results(self):
        """Fetch the results for the current page. To be implemented in subclasses."""
        raise NotImplementedError

    async def create_embed(self):
        """Create the embed for the current page. To be implemented in subclasses."""
        raise NotImplementedError

    async def get_max_items(self):
        """Get the total number of items. To be implemented in subclasses."""
        raise NotImplementedError


class NewDualView(discord.ui.View):
    """Base class for dual views (list/detail) with pagination."""

    def __init__(self, user_id, guild_id, offset, limit, view_type, content: typing.Optional,
                 interaction: discord.Interaction):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.guild_id = guild_id
        self.offset = offset
        self.limit = limit
        self.content = content
        self.message = None
        self.interaction = interaction
        self.results = []
        self.embeds = []
        self.view_type = view_type

        # Initialize buttons
        self.first_page_button = discord.ui.Button(label='First Page', style=discord.ButtonStyle.primary)
        self.previous_page_button = discord.ui.Button(label='Previous Page', style=discord.ButtonStyle.primary)
        self.change_view_button = discord.ui.Button(label='Change View', style=discord.ButtonStyle.primary)
        self.next_page_button = discord.ui.Button(label='Next Page', style=discord.ButtonStyle.primary)
        self.last_page_button = discord.ui.Button(label='Last Page', style=discord.ButtonStyle.primary)

        self.first_page_button.callback = self.first_page
        self.previous_page_button.callback = self.previous_page
        self.change_view_button.callback = self.change_view
        self.next_page_button.callback = self.next_page
        self.last_page_button.callback = self.last_page

        self.add_item(self.first_page_button)
        self.add_item(self.previous_page_button)
        self.add_item(self.change_view_button)
        self.add_item(self.next_page_button)
        self.add_item(self.last_page_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Ensure that only the user who initiated the view can interact with the buttons."""
        try:
            if interaction.user.id != self.user_id:
                await interaction.response.send_message(
                    "You cannot interact with this button.",
                    ephemeral=True
                )
                return False
            return True
        except Exception as e:
            logging.error(f"Failed to check interaction: {e}")
            raise

    async def first_page(self, interaction: discord.Interaction):
        """Handle moving to the first page."""
        try:
            await interaction.response.defer()
            if self.offset == 1:
                await interaction.response.send_message("You are already on the first page.", ephemeral=True)
                return
            self.offset = 1
            await self.update_results()
            await self.create_embed()
            await self.update_buttons()
            await interaction.edit_original_response(
                embeds=self.embeds,
                view=self
            )
        except Exception as e:
            logging.error(f"Failed to move to the first page: {e}")
            raise

    async def previous_page(self, interaction: discord.Interaction):
        """Handle moving to the previous page."""
        try:
            await interaction.response.defer()
            if self.offset > 1:
                self.offset -= self.limit
                if self.offset < 1:
                    self.offset = 1
                await self.update_results()
                await self.create_embed()
                await self.update_buttons()
                await interaction.edit_original_response(
                    embeds=self.embeds,
                    view=self
                )
            else:
                await interaction.followup.send("You are on the first page.", ephemeral=True)
        except Exception as e:
            logging.error(f"Failed to move to the previous page: {e}")
            raise

    async def send_initial_message(self):
        """Send the initial message with the view."""
        try:

            await self.update_results()
            await self.create_embed()
            await self.update_buttons()

            self.message = await self.interaction.followup.send(
                content=self.content,
                embeds=self.embeds,
                view=self
            )
        except discord.HTTPException as e:
            logging.error(
                f"Failed to send message due to HTTPException: {e} in guild {self.interaction.guild.id} for {self.user_id}")
        except Exception as e:
            logging.error(f"Failed to send message: {e} in guild {self.interaction.guild.id} for {self.user_id}")

    async def on_timeout(self):
        """Disable buttons when the view times out."""
        try:
            for child in self.children:
                child.disabled = True
            if self.message:
                try:
                    await self.message.edit(content=self.content, embeds=self.embeds, view=self)
                except discord.HTTPException as e:
                    logging.error(f"Failed to edit message on timeout: {e}")

        except Exception as e:
            logging.error(f"Failed to disable buttons: {e}")
            raise

    async def change_view(self, interaction: discord.Interaction):
        """Change the view type."""
        await interaction.response.defer()
        try:
            await self.on_view_change()
            await self.update_results()
            await self.create_embed()
            await self.update_buttons()
            await interaction.edit_original_response(
                embeds=self.embeds,
                view=self
            )
        except Exception as e:
            logging.error(f"Failed to change view: {e}")
            raise

    async def next_page(self, interaction: discord.Interaction):
        """Handle moving to the next page."""
        try:
            await interaction.response.defer()
            max_items = await self.get_max_items()
            if self.offset + self.limit - 1 < max_items:
                self.offset += self.limit
                await self.update_results()
                await self.create_embed()
                await self.update_buttons()
                await interaction.edit_original_response(
                    embed=self.embed,
                    view=self
                )
            else:
                await interaction.response.send_message("You are on the last page.", ephemeral=True)
        except Exception as e:
            logging.error(f"Failed to move to the next page: {e}")
            raise

    async def last_page(self, interaction: discord.Interaction):
        """Handle moving to the last page."""
        try:
            await interaction.response.defer()
            max_items = await self.get_max_items()
            last_page_offset = ((max_items - 1) // self.limit) * self.limit + 1
            if self.offset != last_page_offset:
                self.offset = last_page_offset
                await self.update_results()
                await self.create_embed()
                await self.update_buttons()
                await interaction.edit_original_response(
                    embeds=self.embeds,
                    view=self
                )
            else:
                await interaction.response.send_message("You are on the last page.", ephemeral=True)
        except Exception as e:
            logging.error(f"Failed to move to the last page: {e}")
            raise

    async def update_buttons(self):
        """Update the enabled/disabled state of buttons based on the current page."""
        try:

            max_items = await self.get_max_items()

            first_page = self.offset == 1
            last_page = self.offset + self.limit - 1 >= max_items

            self.first_page_button.disabled = first_page
            self.previous_page_button.disabled = first_page
            self.next_page_button.disabled = last_page
            self.last_page_button.disabled = last_page
        except Exception as e:
            logging.error(f"Failed to update buttons: {e}")
            raise

    async def on_view_change(self):
        """Change the view type."""
        raise NotImplementedError

    async def update_results(self):
        """Fetch the results for the current page. To be implemented in subclasses."""
        raise NotImplementedError

    async def create_embed(self):
        """Create the embed for the current page. To be implemented in subclasses."""
        raise NotImplementedError

    async def get_max_items(self):
        """Get the total number of items. To be implemented in subclasses."""
        raise NotImplementedError


# Modified RetirementView with character deletion
class RetirementView(SelfAcknowledgementView):
    """A view that allows a user to confirm or cancel the retirement of their character."""

    def __init__(self, character_name: str, user_id: int, guild_id: int, interaction: discord.Interaction,
                 content: str):
        super().__init__(content=content, interaction=interaction)
        self.character_name = character_name
        self.user_id = user_id
        self.guild_id = guild_id
        self.message = None  # Will be set when the view is sent

    async def accepted(self, interaction: discord.Interaction):
        """Handle the confirmation of character retirement."""
        async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as conn:
            cursor = await conn.cursor()
            try:
                # Optional: Check if character exists before deletion
                sql_check = """
                    SELECT Thread_ID, Message_ID FROM Player_Characters
                    WHERE Player_ID = ? AND (Character_Name = ? OR Nickname = ?)
                """
                await cursor.execute(sql_check, (interaction.user.id, self.character_name, self.character_name))
                row = await cursor.fetchone()
                if not row:
                    await self.message.edit(
                        content="Character not found or already retired.",
                        view=None
                    )
                    return

                (thread_id, message_id) = row
                logging_thread = interaction.guild.get_channel(thread_id)
                if not logging_thread:
                    logging_thread = await interaction.guild.fetch_channel(thread_id)
                await logging_thread.edit(name=f"{self.character_name} - Retired")

                # Fetch channel ID
                async with config_cache.lock:
                    configs = config_cache.cache.get(interaction.guild_id)
                    if configs:
                        channel_id_row = configs.get('Accepted_Bio_Channel')
                if not channel_id_row:
                    return f"No channel found with Identifier 'Accepted_Bio_Channel' in Admin table."
                channel_id = channel_id_row

                # Fetch the bio channel
                bio_channel = interaction.guild.get_channel(channel_id)
                if bio_channel is None:
                    bio_channel = await interaction.guild.fetch_channel(channel_id)
                if bio_channel is None:
                    return f"Channel with ID {channel_id} not found."

                # Fetch and edit the message
                try:
                    bio_message = await bio_channel.fetch_message(message_id)
                    await bio_message.delete()
                except discord.NotFound:
                    logging.exception("Bio message not found and could not be deleted.")

                sql_archive_statement = """INSERT INTO Archive_Player_Characters(Player_Name, Player_ID, True_Character_Name,
                Title, Titles, Description, Oath, Level, Tier, Milestones, Trials, Gold, Gold_Value, Gold_Value_Max, Essence,
                Fame, Prestige, Mythweavers, Image_Link, Tradition_Name, Tradition_Link, Template_Name, Template_Link,
                Article_Link) 
                SELECT Player_Name, Player_ID, True_Character_Name, Title, Titles, Description, Oath, Level, Tier, Milestones,
                Trials, Gold, Gold_Value, Gold_Value_Max, Essence, Fame, Prestige, Mythweavers, Image_Link, Tradition_Name,
                Tradition_Link, Template_Name, Template_Link, Article_Link FROM Player_Characters WHERE Player_ID = ? AND
                (Character_Name = ? OR Nickname = ?)"""
                await cursor.execute(sql_archive_statement,
                                     (interaction.user.id, self.character_name, self.character_name))
                await conn.commit()

                # Proceed with deletion
                sql_delete = """
                    DELETE FROM Player_Characters 
                    WHERE Character_Name = ?
                """
                await cursor.execute(sql_delete, (self.character_name,))
                await conn.commit()
                self.embed = discord.Embed(
                    title="Character Retirement",
                    description=f"Character '{self.character_name}' has been successfully retired and deleted from the database."
                )
                await interaction.edit_original_response(
                    content="Character successfully retired and deleted from the database.",
                    embed=self.embed,
                    view=None
                )
            except Exception as e:
                logging.exception(f"Failed to delete character '{self.character_name}': {e}")
                await interaction.followup.send(
                    "An unexpected error occurred while trying to retire your character. Please try again later or contact support.",
                    ephemeral=True
                )

    async def rejected(self, interaction: discord.Interaction):
        """Handle the cancellation of character retirement."""
        self.embed = discord.Embed(
            title="Character Retirement",
            description=f"You have chosen against retiring '{self.character_name}'."
        )
        await self.message.edit(
            content="Character retirement cancelled.",

            view=None
        )

    async def create_embed(self):
        """Create the embed for the retirement confirmation."""
        self.embed = discord.Embed(
            title="Character Retirement",
            description=f"Are you sure you want to retire the character '{self.character_name}'?"
        )


# Modified ShopView with additional logic
class TitleShopView(ShopView):
    def __init__(self, user_id: int, guild_id: int, offset: int, limit: int, interaction: discord.Interaction):
        super().__init__(user_id=user_id, guild_id=guild_id, offset=offset, limit=limit, interaction=interaction,
                         content="")
        self.max_items = None  # Cache total number of items

    async def update_results(self):
        """Fetch the title results for the current page."""
        statement = """
            SELECT ID, Effect, Fame, Masculine_Name, Feminine_Name
            FROM Store_Title ORDER BY Fame Asc
            LIMIT ? OFFSET ?
        """
        async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
            cursor = await db.execute(statement, (self.limit, self.offset - 1))
            self.results = await cursor.fetchall()

    async def create_embed(self):
        """Create the embed for the titles."""

        current_page = (self.offset // self.limit) + 1

        total_pages = ((await self.get_max_items() - 1) // self.limit) + 1
        self.embed = discord.Embed(title="Titles", description=f"Page {current_page} of {total_pages}")
        for title in self.results:
            self.embed.add_field(
                name=f"ID: {title[0]} - {title[3]} / {title[4]}",
                value=f"Effect: {title[1]}, Fame: {title[2]}",
                inline=False
            )

    async def get_max_items(self):
        """Get the total number of titles."""
        if self.max_items is None:
            async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
                cursor = await db.execute("SELECT COUNT(*) FROM Store_Title")
                count = await cursor.fetchone()
                self.max_items = count[0]
        return self.max_items


class PrestigeShopView(ShopView):
    def __init__(self, user_id, guild_id: int, offset: int, limit: int, interaction: discord.Interaction):
        super().__init__(user_id=user_id, guild_id=guild_id, offset=offset, limit=limit, interaction=interaction,
                         content="")
        self.max_items = None  # Cache total number of items

    async def update_results(self):
        """Fetch the title results for the current page."""
        statement = """
            SELECT fame_Required, Prestige_Cost, Name, Effect, Use_Limit
            FROM Store_Fame 
            LIMIT ? OFFSET ?
        """
        async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
            cursor = await db.execute(statement, (self.limit, self.offset - 1))
            self.results = await cursor.fetchall()

    async def create_embed(self):
        """Create the embed for the titles."""
        current_page = ((self.offset) // self.limit) + 1
        total_pages = ((await self.get_max_items() - 1) // self.limit) + 1
        self.embed = discord.Embed(title="Fame Store", description=f"Page {current_page} of {total_pages}")
        for fame in self.results:
            (fame_required, prestige_cost, name, effect, limit) = fame
            self.embed.add_field(name=f'**Name**: {name}',
                                 value=f'**Fame Required**: {fame_required} **Prestige Cost**: {prestige_cost}, **Limit**: {limit} '
                                       f'\r\n **Effect**: {effect}',
                                 inline=False)

    async def get_max_items(self):
        """Get the total number of titles."""
        if self.max_items is None:
            async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
                cursor = await db.execute("SELECT COUNT(*) FROM Store_Title")
                count = await cursor.fetchone()
                self.max_items = count[0]
        return self.max_items



class RumorShopView(ShopView):
    def __init__(self, user_id, guild_id: int, offset: int, limit: int, interaction: discord.Interaction, kingdom: str, settlement: str):
        super().__init__(user_id=user_id, guild_id=guild_id, offset=offset, limit=limit, interaction=interaction,
                         content="")
        self.max_items = None  # Cache total number of items
        self.kingdom = kingdom
        self.settlement = settlement

    async def update_results(self):
        """Fetch the title results for the current page."""
        kingdom = self.kingdom
        settlement = self.settlement

        async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
            cursor = await db.execute()
            if kingdom and settlement:
                await cursor.execute("Select RumorID, Kingdom, Settlement, DC, Rumor, Weight from Rumors where Kingdom = ? and Settlement = ? LIMIT ? OFFSET ?", (kingdom, settlement,self.limit, self.offset))
            elif kingdom:
                await cursor.execute("Select RumorID, Kingdom, Settlement, DC, Rumor, Weight from Rumors where Kingdom = ? LIMIT ? OFFSET ?", (kingdom,self.limit, self.offset))
            elif settlement:
                await cursor.execute(
                    "Select RumorID, Kingdom, Settlement, DC, Rumor, Weight from Rumors where Settlement = ? LIMIT ? OFFSET ?", (settlement,self.limit, self.offset))
            else:
                await cursor.execute(
                    "Select RumorID, Kingdom, Settlement, DC, Rumor, Weight from Rumors LIMIT ? OFFSET ?",
                    (self.limit, self.offset))
            self.results = await cursor.fetchall()

    async def create_embed(self):
        """Create the embed for the titles."""
        current_page = ((self.offset) // self.limit) + 1
        total_pages = ((await self.get_max_items() - 1) // self.limit) + 1
        self.embed = discord.Embed(title="Rumor List", description=f"Page {current_page} of {total_pages}")
        for fame in self.results:
            (rumor_id, kingdom, settlement, dc, rumor, weight) = fame
            self.embed.add_field(name=f'**Rumor ID:**: {rumor_id}',
                                 value=f"""
                                 **Kingdom**: {kingdom} **Settlement**: {settlement}, 
                                 **DC**: {dc}, Likelihood {weight} 
                                 {rumor}""",
                                 inline=False)

    async def get_max_items(self):
        """Get the total number of titles."""
        if self.max_items is None:
            kingdom = self.kingdom
            settlement = self.settlement
            async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
                cursor = await db.execute()
                if kingdom and settlement:
                    await cursor.execute("Select Count(*) from Rumors where kingdom = ? and Settlement = ?",
                                         (kingdom, settlement))
                elif kingdom:
                    await cursor.execute("Select Count(*) from Rumors where kingdom = ?", (kingdom,))
                elif settlement:
                    await cursor.execute("Select Count(*) from Rumors where settlement = ?", (settlement,))
                else:
                    await cursor.exexcute("Select Count(*) from rumors")
                rumor_info = await cursor.fetchone()
                self.max_items = rumor_info[0]
        return self.max_items


class PrestigeHistoryView(ShopView):
    def __init__(self, user_id: int, guild_id: int, offset: int, limit: int, character_name: str, item_name: str,
                 interaction: discord.Interaction):
        super().__init__(user_id=user_id, guild_id=guild_id, offset=offset, limit=limit, interaction=interaction,
                         content="")
        self.max_items = None  # Cache total number of items
        self.character_name = character_name
        self.item_name = item_name

    async def update_results(self):
        """Fetch the history of prestige request  for the current page."""
        if self.item_name is None:
            statement = """
                SELECT Item_Name, Prestige_Cost, Transaction_ID, Time, IsAllowed
                FROM A_Audit_Prestige WHERE Character_Name = ? 
                ORDER BY Transaction_ID DESC LIMIT ? OFFSET ? 
            """
            async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
                cursor = await db.execute(statement, (self.character_name, self.limit, self.offset - 1))
                self.results = await cursor.fetchall()

        else:
            statement = """
                            SELECT Item_Name, Prestige_Cost, Transaction_ID, Time, IsAllowed
                            FROM A_Audit_Prestige WHERE Character_Name = ? AND Item_Name = ?
                            ORDER BY Transaction_ID DESC LIMIT ? OFFSET ? 
                        """
            async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
                cursor = await db.execute(statement, (self.character_name, self.item_name, self.limit, self.offset - 1))
                self.results = await cursor.fetchall()

    async def create_embed(self):
        """Create the embed for the titles."""
        current_page = ((self.offset) // self.limit) + 1
        total_pages = ((await self.get_max_items() - 1) // self.limit) + 1
        self.embed = discord.Embed(title=f"Prestige History for {self.character_name}",
                                   description=f"Page {current_page} of {total_pages}")
        for fame in self.results:
            (item_name, prestige_cost, transaction_id, time, allowed) = fame
            allowed = "Approved" if allowed == 1 else "Rejected"
            self.embed.add_field(name=f'**Item Name**: {item_name}',
                                 value=f'**Prestige Cost**: {prestige_cost} **Transaction ID**: {transaction_id}, **Allowed**: {allowed} '
                                       f'\r\n **Time**: {time}',
                                 inline=False)

    async def get_max_items(self):
        """Get the total number of titles."""
        if self.max_items is None:
            async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
                if not self.character_name:
                    cursor = await db.execute("SELECT COUNT(*) FROM Player_Characters")
                else:
                    cursor = await db.execute("SELECT COUNT(*) FROM Player_Characters WHERE Player_Name = ?",
                                              (self.character_name,))
                count = await cursor.fetchone()
                self.max_items = count[0]
        return self.max_items


class GoldHistoryView(ShopView):
    def __init__(self, user_id: int, guild_id: int, offset: int, limit: int, character_name: str,
                 interaction: discord.Interaction):
        super().__init__(user_id=user_id, guild_id=guild_id, offset=offset, limit=limit, interaction=interaction,
                         content="")
        self.max_items = None  # Cache total number of items
        self.character_name = character_name

    async def update_results(self):
        """Fetch the history of Gold Actions  for the current page."""

        statement = """
                        SELECT Transaction_ID, Author_Name, Author_ID, Character_Name, 
                        gold_value, Effective_Gold_Value, Effective_Gold_Value_Max, 
                        Reason, Source_Command, Time, Related_Transaction_ID
                        FROM A_Audit_Gold WHERE Character_Name = ?
                        ORDER BY Transaction_ID DESC LIMIT ? OFFSET ? 
                    """
        async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
            cursor = await db.execute(statement, (self.character_name, self.limit, self.offset - 1))
            self.results = await cursor.fetchall()

    async def create_embed(self):
        """Create the embed for the titles."""
        current_page = (self.offset // self.limit) + 1
        total_pages = ((await self.get_max_items() - 1) // self.limit) + 1
        self.embed = discord.Embed(title=f"Gold History for {self.character_name}",
                                   description=f"Page {current_page} of {total_pages}")
        for item in self.results:
            (transaction_id, author_name, author_id, character_name,
             gold_value, effective_gold_value, effective_gold_value_max,
             reason, source_command, time, related_transaction_id) = item
            transaction_id_field = f"**Transaction ID**: {transaction_id}"
            transaction_id_field += f" **Related Transaction ID**: {related_transaction_id}" if related_transaction_id else ""
            self.embed.add_field(name=transaction_id_field,
                                 value=f'**Author**: {author_name} Source: {source_command}\r\n ***Gold Changes***: **Gold Value**: {gold_value}, **Effective Gold Value**: {effective_gold_value}, **Effective Gold Value Max**: {effective_gold_value_max}\r\n{reason}',
                                 inline=False)

    async def get_max_items(self):
        """Get the total number of titles."""
        if self.max_items is None:
            async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
                cursor = await db.execute("SELECT COUNT(*) FROM A_AUDIT_GOLD WHERE Character_Name = ?",
                                          (self.character_name,))
                count = await cursor.fetchone()
                self.max_items = count[0]
        return self.max_items


# Dual View Type Views
class CharacterDisplayView(DualView):
    def __init__(self, user_id: int, guild_id: int, offset: int, limit: int, player_name: str, character_name: str,
                 view_type: int, interaction: discord.Interaction):
        super().__init__(user_id=user_id, guild_id=guild_id, offset=offset, limit=limit, view_type=view_type,
                         interaction=interaction, content="")
        self.max_items = None  # Cache total number of items
        self.character_name = character_name
        self.view_type = view_type
        self.player_name = player_name

    async def update_results(self):
        """Fetch the history of prestige request  for the current page."""
        if not self.player_name:

            statement = """SELECT player_name, player_id, True_Character_Name, Title, Titles, Description, Oath, Level, 
                            Tier, Milestones, Milestones_Required, Trials, Trials_Required, Gold, Gold_Value, 
                            Essence, Fame, Prestige, Color, Mythweavers, Image_Link, Tradition_Name, 
                            Tradition_Link, Template_Name, Template_Link, Article_Link
                            FROM Player_Characters ORDER BY True_Character_Name ASC LIMIT ? OFFSET ?"""
            val = (self.limit, self.offset - 1)

        else:

            statement = """SELECT player_name, True_Character_Name, Title, Titles, Description, Oath, Level, 
                            Tier, Milestones, Milestones_Required, Trials, Trials_Required, Gold, Gold_Value, 
                            Essence, Fame, Prestige, Color, Mythweavers, Image_Link, Tradition_Name, 
                            Tradition_Link, Template_Name, Template_Link, Article_Link
                            FROM Player_Characters WHERE Player_Name = ? ORDER BY True_Character_Name ASC LIMIT ? OFFSET ? """
            val = (self.player_name, self.limit, self.offset - 1)
        async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
            cursor = await db.execute(statement, val)
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
                gold_string = get_gold_breakdown(gold)
                self.embed.add_field(name=f'Character Name', value=f'**Name**:[{true_character_name}](<{mythweavers}>)')
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
                (player_name, true_character_name, title, titles, description, oath, level, tier, milestones,
                 milestones_required, trials, trials_required, gold, gold_value, essence, fame, prestige, color,
                 mythweavers, image_link, tradition_name, tradition_link, template_name, template_link,
                 article_link) = result
                gold_string = get_gold_breakdown(gold)
                illiquid_gold_string = get_gold_breakdown(gold_value - gold)
                self.embed = discord.Embed(title=f"Detailed view for {true_character_name}",
                                           description=f"Page {current_page} of {total_pages}",
                                           color=int(color[1:], 16))
                self.embed.set_author(name=f'{player_name}')
                self.embed.set_thumbnail(url=f'{image_link}')
                self.embed.add_field(name=f'Character Name', value=f'**Name**:[{true_character_name}](<{mythweavers}>)')
                self.embed.add_field(name=f'Information',
                                     value=f'**Level**: {level}, **Mythic Tier**: {tier}')
                self.embed.add_field(name=f'Total Experience',
                                     value=f'**Milestones**: {milestones}, **Trials**: {trials}',
                                     inline=False)
                self.embed.add_field(name=f'Current Wealth',
                                     value=f'**Gold**: {gold_string}, **Illiquid Gold**: {illiquid_gold_string} **Essence**: {essence}',
                                     inline=False)
                self.embed.add_field(name=f'Fame and Prestige', value=f'**Fame**: {fame}, **Prestige**: {prestige}',
                                     inline=False)
                linkage = ""
                linkage += f"**Tradition**: [{tradition_name}]({tradition_link})" if tradition_name else ""
                linkage += f" " if tradition_name and template_name else ""
                linkage += f"**Template**: [{template_name}]({template_link})" if template_name else ""
                if tradition_name or template_name:
                    self.embed.add_field(name=f'Additional Info', value=linkage, inline=False)

    async def get_max_items(self):
        """Get the total number of titles."""
        if self.max_items is None:
            async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
                if not self.player_name:
                    cursor = await db.execute("SELECT COUNT(*) FROM Player_Characters")
                else:
                    cursor = await db.execute("SELECT COUNT(*) FROM Player_Characters WHERE Player_Name = ?",
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


class LevelRangeDisplayView(DualView):
    def __init__(self, user_id: int, guild_id: int, offset: int, limit: int, level_range_min: int, level_range_max: int,
                 view_type: int, interaction: discord.Interaction):
        super().__init__(user_id=user_id, guild_id=guild_id, offset=offset, limit=limit, view_type=view_type,
                         interaction=interaction, content="")
        self.max_items = None  # Cache total number of items
        self.view_type = view_type
        self.level_range_max = level_range_max
        self.level_range_min = level_range_min

    async def update_results(self):
        """Fetch the history of prestige request  for the current page."""
        statement = """SELECT player_name, player_id, True_Character_Name, Title, Titles, Description, Oath, Level, 
                        Tier, Milestones, Milestones_Required, Trials, Trials_Required, Gold, Gold_Value, 
                        Essence, Fame, Prestige, Color, Mythweavers, Image_Link, Tradition_Name, 
                        Tradition_Link, Template_Name, Template_Link, Article_Link
                        FROM Player_Characters WHERE level BETWEEN ? AND ? ORDER BY True_Character_Name ASC LIMIT ? OFFSET ? """
        val = (self.level_range_min, self.level_range_max, self.limit, self.offset - 1)
        async with (aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db):
            cursor = await db.cursor()
            await cursor.execute(statement, val)
            self.results = await cursor.fetchall()

    async def create_embed(self):
        """Create the embed for the titles."""
        if self.view_type == 1:
            current_page = (self.offset // self.limit) + 1
            total_pages = ((await self.get_max_items() - 1) // self.limit) + 1
            self.embed = discord.Embed(title=f"Character Summary",
                                       description=f"Page {current_page} of {total_pages}")
            for result in self.results:

                (player_name, player_id, true_character_name, title, titles, description, oath, level, tier, milestones,
                 milestones_required, trials, trials_required, gold, gold_value, essence, fame, prestige, color,
                 mythweavers, image_link, tradition_name, tradition_link, template_name, template_link,
                 article_link) = result
                gold_string = get_gold_breakdown(gold)
                self.embed.add_field(name=f'Character Name', value=f'**Name**:{true_character_name}', inline=False)
                self.embed.add_field(name=f'Information',
                                     value=f'**Level**: {level}, **Mythic Tier**: {tier}')
                self.embed.add_field(name=f'Total Experience',
                                     value=f'**Milestones**: {milestones},  **Trials**: {trials}')
                self.embed.add_field(name=f'Current Wealth', value=f'**Gold**: {gold_string}, **Essence**: {essence}',
                                     inline=False)
                linkage = ""
                linkage += f"**Tradition**: [{tradition_name}]({tradition_link})" if tradition_name else ""
                linkage += f" " if tradition_name and template_name else ""
                linkage += f"**Template**: [{template_name}]({template_link})" if template_name else ""
                if not tradition_name or not template_name:
                    self.embed.add_field(name=f'Additional Info', value=linkage, inline=False)
        else:
            current_page = (self.offset // self.limit) + 1
            total_pages = ((await self.get_max_items() - 1) // self.limit) + 1
            for result in self.results:
                (player_name, player_id, true_character_name, title, titles, description, oath, level, tier, milestones,
                 milestones_required, trials, trials_required, gold, gold_value, essence, fame, prestige, color,
                 mythweavers, image_link, tradition_name, tradition_link, template_name, template_link,
                 article_link) = result
                gold_string = get_gold_breakdown(gold)
                illiquid_gold_string = get_gold_breakdown(gold_value - gold)
                self.embed = discord.Embed(title=f"Detailed view for {true_character_name}",
                                           description=f"Page {current_page} of {total_pages}",
                                           color=int(color[1:], 16))
                self.embed.set_author(name=f'{player_name}')
                self.embed.set_thumbnail(url=f'{image_link}')
                self.embed.add_field(name=f'Character Name', value=f'**Name**:{true_character_name}', inline=False)
                self.embed.add_field(name=f'Information',
                                     value=f'**Level**: {level}, **Mythic Tier**: {tier}', inline=False)
                self.embed.add_field(name=f'Total Experience',
                                     value=f'**Milestones**: {milestones}, **Trials**: {trials},')
                self.embed.add_field(name=f'Current Wealth',
                                     value=f'**gold**: {gold_string}, **Illiquid Gold**: {illiquid_gold_string} **Essence**: {essence}')
                self.embed.add_field(name=f'Fame and Prestige', value=f'**Fame**: {fame}, **Prestige**: {prestige}',
                                     inline=False)
                linkage = ""
                linkage += f"**Tradition**: [{tradition_name}]({tradition_link})" if tradition_name else ""
                linkage += f" " if tradition_name and template_name else ""
                linkage += f"**Template**: [{template_name}]({template_link})" if template_name else ""
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
                cursor = await db.cursor()
                await cursor.execute(
                    "SELECT COUNT(*) FROM Player_Characters WHERE Level BETWEEN ? AND ?",
                    (self.level_range_min, self.level_range_max))
                count = await cursor.fetchone()
                self.max_items = count[0]
                return self.max_items
        else:
            return self.max_items

    async def on_view_change(self):
        self.view_type = 1 if self.view_type == 2 else 2
        if self.view_type == 1:
            self.limit = 5  # Change the limit to 5 for the summary view
        else:
            self.limit = 1  # Change the limit to 1 for the detailed view


# Modified RecipientAcknowledgementView with additional logic
class PropositionViewRecipient(RecipientAcknowledgementView):
    def __init__(
            self,
            allowed_user_id: int,
            requester_name: str,
            character_name: str,
            item_name: str,
            prestige_cost: int,
            proposition_id: int,
            bot,
            guild_id: int,
            prestige: int,
            logging_thread: int,
            interaction: discord.Interaction,
            content: str
    ):
        super().__init__(allowed_user_id=allowed_user_id, interaction=interaction, content=content)
        self.guild_id = guild_id
        self.requester_name = requester_name
        self.character_name = character_name
        self.item_name = item_name
        self.prestige_cost = prestige_cost
        self.proposition_id = proposition_id
        self.bot = bot
        self.prestige = prestige
        self.logging_thread = logging_thread
        self.embed = None

    async def accepted(self, interaction: discord.Interaction):
        """Handle the approval logic."""
        # Update the database to mark the proposition as accepted
        # Adjust prestige, log the transaction, notify the requester, etc.
        self.embed = discord.Embed(
            title="Proposition Accepted",
            description=f"The proposition {self.proposition_id} has been accepted.",
            color=discord.Color.green()
        )
        # Additional logic such as notifying the requester
        async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as conn:
            await conn.execute(
                "UPDATE A_Audit_Prestige SET IsAllowed = ? WHERE Transaction_ID = ?",
                (1, self.proposition_id)
            )
            await conn.commit()
            await conn.execute(
                "UPDATE Player_Characters SET Prestige = Prestige - ? WHERE Character_Name = ?",
                (self.prestige_cost, self.character_name)
            )
            await conn.commit()
            await character_embed(character_name=self.character_name, guild=interaction.guild)
            character_changes = CharacterChange(
                character_name=self.character_name,
                author=self.requester_name,
                source=f'Prestige Request',
                prestige_change=-abs(self.prestige_cost),
                prestige=self.prestige - self.prestige_cost)
            await log_embed(
                change=character_changes,
                guild=interaction.guild,
                thread=self.logging_thread,
                bot=self.bot)

    async def rejected(self, interaction: discord.Interaction):
        """Handle the rejection logic."""
        # Update the database to mark the proposition as rejected

        self.embed = discord.Embed(
            title="Proposition Rejected",
            description=f"The proposition {self.proposition_id} has been rejected.",
            color=discord.Color.red()
        )
        # Additional logic such as notifying the requester

    async def create_embed(self):
        """Create the initial embed for the proposition."""
        self.embed = discord.Embed(
            title="Proposition Request",
            description=(
                f"**Requester:** {self.requester_name}\n"
                f"**Character:** {self.character_name}\n"
                f"**Item:** {self.item_name}\n"
                f"**Prestige Cost:** {self.prestige_cost}\n"
                f"**Proposition ID:** {self.proposition_id}"
            ),
            color=discord.Color.blue()
        )


class GoldSendView(RecipientAcknowledgementView):
    def __init__(
            self,
            allowed_user_id: int,
            requester_name: str,
            requester_id: int,
            character_name: str,
            recipient_name: str,
            source_level: int,
            source_oath: str,
            source_gold: Decimal,
            source_gold_value: Decimal,
            source_gold_value_max: Decimal,
            target_level: int,
            target_oath: str,
            recipient_gold: Decimal,
            recipient_gold_value: Decimal,
            recipient_gold_value_max: Decimal,
            gold_change: Decimal,
            market_value: Decimal,
            bot,
            guild_id: int,
            source_logging_thread: int,
            recipient_logging_thread: int,
            reason: str,
            interaction: discord.Interaction
    ):
        super().__init__(allowed_user_id=allowed_user_id, interaction=interaction,
                         content=f"<@{allowed_user_id}>, please accept or request this transaction.")
        self.guild_id = guild_id
        self.requester_name = requester_name
        self.requester_id = requester_id
        self.character_name = character_name
        self.recipient_name = recipient_name  # Name of the recipient
        self.source_level = source_level  # Level of the source character
        self.source_oath = source_oath
        self.source_gold = source_gold
        self.source_gold_value = source_gold_value
        self.source_gold_value_max = source_gold_value_max
        self.target_level = target_level  # Level of the recipient character
        self.target_oath = target_oath
        self.recipient_gold = recipient_gold
        self.recipient_gold_value = recipient_gold_value
        self.recipient_gold_value_max = recipient_gold_value_max
        self.gold_change = gold_change  # Amount of gold to be sent
        self.market_value = market_value  # Market value of the item
        self.bot = bot
        self.source_logging_thread = source_logging_thread
        self.recipient_logging_thread = recipient_logging_thread
        self.reason = reason
        self.embed = None

    async def accepted(self, interaction: discord.Interaction):
        """Handle the approval logic."""
        # Update the database to mark the proposition as accepted
        # Adjust prestige, log the transaction, notify the requester, etc.

        self.embed = discord.Embed(
            title=f"{self.character_name} Transaction Accepted",
            description=f"The request of \r\n{self.reason}\r\n has been accepted by <@{self.allowed_user_id}>'s {self.recipient_name}.",
            color=discord.Color.green()
        )
        # Additional logic such as notifying the requester
        async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as conn:
            cursor = await conn.cursor()
            print("Source Gold Info is", self.source_gold, self.source_gold_value, self.source_gold_value_max)
            source_gold_calculation = await gold_calculation(
                guild_id=self.guild_id,
                character_name=self.character_name,
                level=self.source_level,
                oath=self.source_oath,
                gold=Decimal(self.source_gold),
                gold_value=Decimal(self.source_gold_value),
                gold_value_max=Decimal(self.source_gold_value_max),
                gold_change=Decimal(-abs(self.gold_change)),
                gold_value_change=Decimal(abs(self.market_value)) + Decimal(-abs(self.gold_change)),
                gold_value_max_change=None,
                source=f"Gold Send",
                reason=self.reason,
                author_id=interaction.user.id,
                author_name=interaction.user.name)
            if isinstance(source_gold_calculation, tuple):
                recipient_gold_calculation = await gold_calculation(
                    guild_id=self.guild_id,
                    character_name=self.recipient_name,
                    level=self.target_level,
                    oath=self.target_oath,
                    gold=Decimal(self.recipient_gold),
                    gold_value=Decimal(self.recipient_gold_value),
                    gold_value_max=Decimal(self.recipient_gold_value_max),
                    gold_change=Decimal(abs(self.gold_change)),
                    gold_value_change=None,
                    gold_value_max_change=None,
                    source=f"Gold Send",
                    reason=self.reason,
                    related_transaction=source_gold_calculation[4],
                    author_name=self.requester_name,
                    author_id=interaction.user.id,
                    ignore_limitations=True)
                if isinstance(recipient_gold_calculation, str):
                    await interaction.message.edit(
                        content=f"An error occurred in the gold send command: {recipient_gold_calculation}")
                    return
            else:
                await interaction.message.edit(
                    content=f"An error occurred in the gold send command: {source_gold_calculation}")
            if isinstance(source_gold_calculation, tuple) and isinstance(recipient_gold_calculation, tuple):
                (source_calc_difference, source_calc_gold_total, source_calc_gold_value_total,
                 source_calc_gold_max_total, source_calc_transaction_id) = source_gold_calculation
                (recipient_calc_difference, recipient_calc_gold_total, recipient_calc_gold_value_total,
                 recipient_calc_gold_max_total, recipient_calc_transaction_id) = recipient_gold_calculation
                print("Source Gold Info is", source_calc_gold_total, source_calc_gold_value_total,
                      source_calc_gold_max_total)
                await cursor.execute(
                    "UPDATE Player_Characters SET Gold = ?, Gold_Value = ?, Gold_Value_max = ? WHERE Character_Name = ?",
                    (str(source_calc_gold_total), str(source_calc_gold_value_total), str(source_calc_gold_value_total),
                     self.character_name)
                )
                await conn.commit()
                await character_embed(character_name=self.character_name, guild=interaction.guild)
                character_changes = CharacterChange(
                    character_name=self.character_name,
                    author=self.requester_name,
                    source=f'Gold Send',
                    gold_change=-abs(Decimal(source_calc_difference)),
                    gold=Decimal(source_calc_gold_total),
                    gold_value=Decimal(source_calc_gold_value_total),
                    transaction_id=source_calc_transaction_id
                )
                await log_embed(character_changes, guild=interaction.guild,
                                                 thread=self.source_logging_thread, bot=self.bot)
                await conn.execute(
                    "UPDATE Player_Characters SET Gold = ?, Gold_Value = ?, Gold_Value_max = ? WHERE Character_Name = ?",
                    (str(recipient_calc_gold_total), str(recipient_calc_gold_value_total),
                     str(recipient_calc_gold_max_total),
                     self.recipient_name)
                )
                await conn.commit()
                await cursor.execute("UPDATE A_Audit_Gold SET Related_Transaction_ID = ? WHERE Transaction_ID = ?",
                                     (recipient_calc_transaction_id, source_calc_transaction_id))
                await conn.commit()
                await character_embed(character_name=self.recipient_name, guild=interaction.guild)
                character_changes = CharacterChange(
                    character_name=self.recipient_name,
                    author=self.requester_name,
                    source=f'Gold Send',
                    gold_change=abs(Decimal(recipient_calc_difference)),
                    gold=Decimal(recipient_calc_gold_total),
                    gold_value=Decimal(recipient_calc_gold_value_total),
                    transaction_id=recipient_calc_transaction_id
                )
                await log_embed(character_changes, guild=interaction.guild,
                                                 thread=self.recipient_logging_thread, bot=self.bot)
                await character_embed(character_name=self.recipient_name, guild=interaction.guild)
                await character_embed(character_name=self.character_name, guild=interaction.guild)
                gold_string = get_gold_breakdown(self.gold_change)
                embed = discord.Embed(
                    title=f"Gold Transaction Completed",
                    description=f"{self.character_name} has sent {gold_string} to {self.recipient_name}.\r\n {self.reason}",
                    color=discord.Color.green()
                )
                embed.set_footer(
                    text=f"Transaction ID: {source_calc_transaction_id}>, Recipient Transaction ID: {recipient_calc_transaction_id}")
                await interaction.message.edit(content=None, embed=embed, view=None)
            else:
                await interaction.message.edit(
                    content=f"An error occurred in the gold send command: {recipient_gold_calculation}")

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
        gold_string = get_gold_breakdown(self.gold_change)
        self.embed = discord.Embed(
            title=f"{self.character_name} is sending {gold_string}to {self.recipient_name}",
            description=self.reason,
            color=discord.Color.blue()
        )
        self.embed.set_author(name=self.requester_name)
        self.embed.set_footer(text="Please accept or reject this transaction before it expires.")


# Mythweavers Views
class AttributesView(discord.ui.View):
    def __init__(self, user_id: int, guild_id: int, modifiers: dict):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.guild_id = guild_id
        self.modifiers = modifiers  # Dictionary of attribute names and their modifiers

        # Dynamically create buttons and add callbacks
        for attribute in self.modifiers.keys():
            button = discord.ui.Button(
                label=attribute.capitalize(),
                style=discord.ButtonStyle.primary
            )
            button.callback = self.create_roll_callback(attribute)  # Assign callback
            self.add_item(button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Ensure that only the user who initiated the view can interact with the buttons."""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "You cannot interact with this button.",
                ephemeral=True
            )
            return False
        return True

    def create_roll_callback(self, attribute: str):
        """Generate a callback function for rolling the given attribute."""

        async def callback(interaction: discord.Interaction):
            roll = random.randint(1, 20)
            content = f"**Rolling :game_die: {attribute.capitalize()}** base: {roll}: total: {roll + self.modifiers[attribute]}"
            content += ":broken_heart: **Critical Failure**" if roll == 1 else ""
            content += ":sparkles: **Critical Success**" if roll == 20 else ""
            await interaction.response.send_message(content=content)

        return callback

# Ticket Views
class TicketView(discord.ui.View):
    def __init__(self, message_id: int, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.message_id = message_id


    async def setup_buttons(self):
        # Dynamically create buttons and add callbacks
        async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
            cursor = await db.cursor()
            self.clear_items()
            await cursor.execute("SELECT buttonname, buttonstyle, color, emoji FROM Tickets_Buttons WHERE messageid = ?", (self.message_id,))
            ticket_buttons = await cursor.fetchall()
            for ticket_tuple in ticket_buttons:
                (button_label, style, color, emoji) = ticket_tuple
                style_dict = {
                1: discord.ButtonStyle.primary,
                2: discord.ButtonStyle.secondary,
                3: discord.ButtonStyle.success,
                4: discord.ButtonStyle.danger
                }

                button_style = style_dict.get(style, discord.ButtonStyle.primary)

                button = discord.ui.Button(
                    label=button_label,
                    style=button_style,
                    custom_id=str(self.message_id) + "_" + button_label,
                )
                if emoji:
                    button.emoji = emoji
                button.callback = self.create_thread_callback(button_label)  # Assign callback
                self.add_item(button)


    def create_thread_callback(self, name: str):
        """Generate a callback function for rolling the given attribute."""
        async def callback(interaction: discord.Interaction):

            async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as conn:
                cursor = await conn.cursor()
                await cursor.execute("Select Count(*) from tickets_Thread where player_id = ? and active = 1",(interaction.user.id,))
                count = await cursor.fetchone()
                message_id = self.message_id

                if count[0] >= 5:
                    await interaction.response.send_message(f"You are a fiend for these tickets, huh? You currently have {count[0]} open tickets! Close a few first!", ephemeral=True)
                    return


                await cursor.execute("select coalesce(max(id), 0) + 1 from tickets_thread")
                max_id = await cursor.fetchone()

                await cursor.execute("Select response_content, response_title, color, response_color, modaltypeone, modaltitleone, modaldefaultone, modaltypetwo, modaltitletwo, modaldefaulttwo, modaltypethree, modaltitlethree, modaldefaultthree, modaltypefour, modaltitlefour, modaldefaultfour, modaltypefive, modaltitlefive, modaldefaultfive from tickets_buttons where buttonname = ? and messageid = ?", (name,self.message_id))
                response = await cursor.fetchone()


                if response is None:
                    await interaction.response.send_message("Could not find response for this ticket.", ephemeral=True)
                (response_content, response_title, color, response_color, modaltypeone, modaltitleone, modaldefaultone, modaltypetwo, modaltitletwo, modaldefaulttwo, modaltypethree, modaltitlethree, modaldefaultthree, modaltypefour, modaltitlefour, modaldefaultfour, modaltypefive, modaltitlefive, modaldefaultfive) = response
                await cursor.execute("Select '<@&' || notification_roles || '>' from tickets_notify where ticketname = ? and messageid = ?", (name,self.message_id))
                roles = await cursor.fetchall()

                if roles:
                    ping_group = ", ".join(role[0] for role in roles)
                    ping_group = f"<@{interaction.user.id}>, {ping_group}"
                else:
                    ping_group = f"<@{interaction.user.id}>"

                if any([modaltypeone, modaltypetwo, modaltypethree, modaltypefour, modaltypefive]):

                    modal_fields = [
                        (modaltypeone, modaltitleone, modaldefaultone),
                        (modaltypetwo, modaltitletwo, modaldefaulttwo),
                        (modaltypethree, modaltitlethree, modaldefaultthree),
                        (modaltypefour, modaltitlefour, modaldefaultfour),
                        (modaltypefive, modaltitlefive, modaldefaultfive),
                    ]

                    # Filter out empty ones
                    modal_fields = [(mtype, mtitle, mdefault) for mtype, mtitle, mdefault in modal_fields if mtype]

                    class TicketModal(discord.ui.Modal, title=response_title or "Submit Ticket"):
                        def __init__(self):
                            super().__init__()

                            self.inputs = []

                            for mtype, mtitle, mdefault in modal_fields:
                                style = (
                                    discord.TextStyle.short
                                    if mtype == 1 else discord.TextStyle.long
                                )

                                input_field = discord.ui.TextInput(
                                    label=mtitle,
                                    style=style,
                                    placeholder=mdefault,
                                    required=True,
                                    max_length=1000
                                )

                                self.inputs.append(input_field)
                                self.add_item(input_field)

                        async def on_submit(self, modal_interaction: discord.Interaction):
                            # Collect responses
                            thread = await modal_interaction.channel.create_thread(
                                name=f"{name}-{modal_interaction.user.name}-{max_id[0]}",
                                auto_archive_duration=10080
                            )

                            embed = discord.Embed(
                                title=response_title,
                                description=f"{response_content}",
                                color=response_color
                            )
                            for field in self.inputs:
                                embed.add_field(name=field.label, value=field.value, inline=False)

                            view = threadview(
                                thread.id,
                                modal_interaction.guild_id,
                                message_id,
                                name,
                                max_id[0],
                                modal_interaction.user.id
                            )

                            await thread.send(
                                content=ping_group,
                                embed=embed,
                                allowed_mentions=discord.AllowedMentions(users=True, roles=True),
                                view=view
                            )
                            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as conn:
                                cursor = await conn.cursor()
                                await cursor.execute(
                                    "insert into tickets_thread(tickettype, threadid, channel_id, player_Id, player_name, active, messageid, jump_url, created_time) values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                    (
                                        name,
                                        thread.id,
                                        modal_interaction.channel_id,
                                        modal_interaction.user.id,
                                        modal_interaction.user.name,
                                        1,
                                        message_id,
                                        thread.jump_url,
                                        datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                                    )
                                )
                                await conn.commit()

                            await modal_interaction.response.send_message(
                                "Thread created successfully.",
                                ephemeral=True
                            )

                    await interaction.response.send_modal(TicketModal())
                else:
                    thread = await interaction.channel.create_thread(name=f"{name}-{interaction.user.name}-{max_id[0]}",auto_archive_duration=10080)
                    embed = discord.Embed(title=response_title, description=response_content, color=response_color)
                    view = threadview(thread.id, interaction.guild_id, self.message_id, name, max_id[0], interaction.user.id)
                    await thread.send(content=f"{ping_group}", embed=embed, allowed_mentions=discord.AllowedMentions(users=True, roles=True), view=view)
                    await cursor.execute("insert into tickets_thread(tickettype, threadid, channel_id, player_Id, player_name, active, messageid, jump_url, created_time) values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                         (name, thread.id, interaction.channel_id, interaction.user.id, interaction.user.name, 1, self.message_id, thread.jump_url, datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")))
                    await conn.commit()
                    await interaction.response.send_message("Thread created successfully.", ephemeral=True)
        return callback


class threadview(discord.ui.View):
    def __init__(self, thread_id: int, guild_id: int, message_id: int, ticket_name: str, ticket_id: int, source_id: int):
        super().__init__(timeout=None)
        self.thread_id = thread_id
        self.guild_id = guild_id
        self.message_id = message_id
        self.ticket_name = ticket_name
        self.ticket_id = ticket_id
        self.source_id = source_id

        # Initialize buttons
        self.close_button = discord.ui.Button(label='Close', style=discord.ButtonStyle.primary)
        self.claim_button = discord.ui.Button(label='Claim', style=discord.ButtonStyle.secondary)

        self.close_button.callback = self.close_callback
        self.claim_button.callback = self.claim_callback

        self.add_item(self.close_button)
        self.add_item(self.claim_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Ensure that only the user who initiated the view can interact with the buttons."""


    async def close_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as conn:
            cursor = await conn.cursor()
            await cursor.execute("Select notification_roles from tickets_notify where messageid = ? and ticketname = ?",
                                 (self.message_id, self.ticket_name))
            notification_roles = await cursor.fetchall()
            if not notification_roles:
                pass
            elif any(role[0] in interaction.user.roles for role in notification_roles):
                pass
            elif interaction.user.guild_permissions.administrator:
                pass
            elif interaction.user.id == self.source_id:
                pass
            else:
                await interaction.followup.send("You don't have permission to claim this thread.")
                return
        await silent_close_thread(
            guild=interaction.guild,
            ticketid=self.ticket_id,
            closer_name_tkt=interaction.user.name,
            closer_id_tkt=interaction.user.id,
            interaction=interaction
        )

    async def claim_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as conn:
            cursor = await conn.cursor()
            await cursor.execute("Select notification_roles from tickets_notify where messageid = ? and ticketname = ?",
                                 (self.message_id, self.ticket_name))
            notification_roles = await cursor.fetchall()
            if interaction.user.id == self.source_id:
                await interaction.followup.send("Narcissus loves a man who loves himself. Why are you claiming your own ticket?")
            elif not notification_roles:
                pass
            elif any(role[0] in interaction.user.roles for role in notification_roles):
                pass
            elif interaction.user.guild_permissions.administrator:
                pass
            else:
                await interaction.followup.send("You don't have permission to claim this thread.")


            await claim_thread(
                interaction.channel,
                claimer_name=interaction.user.name,
                claimer_id=interaction.user.id,
                guild_id=self.guild_id
            )
            await interaction.followup.send("Thread claimed.", ephemeral=True)


# Modified ShopView with additional logic
class buttonlist(ShopView):
    def __init__(self, user_id: int, guild_id: int, offset: int, limit: int, interaction: discord.Interaction):
        super().__init__(user_id=user_id, guild_id=guild_id, offset=offset, limit=limit, interaction=interaction,
                         content="")
        self.max_items = None  # Cache total number of items

    async def update_results(self):
        """Fetch the title results for the current page."""
        statement = """
            SELECT t.messageid, tb.buttonname, tb.buttonstyle, tb.color, response_color, response_title, response_content, channelid, jump_url, 
                modaltypeone, modaltitleone, modaltypetwo, modaltitletwo, modaltypethree, modaltitlethree, modaltypefour, modaltitlefour, modaltypefive, modaltitlefive 
            FROM Tickets_Buttons tb 
            left join tickets t on tb.messageid = t.messageid
            ORDER BY t.messageid ASC
            LIMIT ? OFFSET ?
        """
        async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
            cursor = await db.execute(statement, (self.limit, self.offset - 1))
            self.results = await cursor.fetchall()

    async def create_embed(self):
        """Create the embed for the titles."""

        current_page = (self.offset // self.limit) + 1

        total_pages = ((await self.get_max_items() - 1) // self.limit) + 1
        self.embed = discord.Embed(title="Buttons", description=f"Page {current_page} of {total_pages}")
        for title in self.results:
            self.embed.add_field(
                name=f"Message ID: [{title[0]}]({title[8]}) - Button Name: {title[1]}",
                value=f"Button Style: {title[2]}, Color: {title[3]}, Response Color: {title[4]}",
                inline=False
            )
            response_content = f"Response Content: {title[6]}"
            response_content += f"\r\n Modal Title: {title[10]} Type: {title[9]}"  if title[9] else ""
            response_content += f"\r\n Modal Title: {title[12]} Type: {title[11]}"  if title[11] else ""
            response_content += f"\r\n Modal Title: {title[14]} Type: {title[13]}" if title[13] else ""
            response_content += f"\r\n Modal Title: {title[16]} Type: {title[15]}" if title[15] else ""
            response_content += f"\r\n Modal Title: {title[18]} Type: {title[17]}" if title[17] else ""

            self.embed.add_field(
                name=f"Response Title: {title[5]}",
                value=response_content,
                inline=False
            )

    async def get_max_items(self):
        """Get the total number of titles."""
        if self.max_items is None:
            async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
                cursor = await db.execute("SELECT COUNT(*) FROM Tickets_Buttons")
                count = await cursor.fetchone()
                self.max_items = count[0]
        return self.max_items

    # Modified ShopView with additional logic
class ThreadListView(ShopView):
    def __init__(self, user_id: int, guild_id: int, offset: int, limit: int, interaction: discord.Interaction):
        super().__init__(user_id=user_id, guild_id=guild_id, offset=offset, limit=limit, interaction=interaction,
                         content="")
        self.max_items = None  # Cache total number of items

    async def update_results(self):
        """Fetch the title results for the current page."""
        statement = """
            SELECT id, tickettype, threadid, channel_id, player_id, player_name, messageid, claimed_by_id, claimed_by_name, jump_url, created_time
            from tickets_thread tt 
            where active = 1
            ORDER BY id desc
            LIMIT ? OFFSET ?
        """
        async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
            cursor = await db.execute(statement, (self.limit, self.offset - 1))
            self.results = await cursor.fetchall()

    async def create_embed(self):
        """Create the embed for the titles."""

        current_page = (self.offset // self.limit) + 1

        total_pages = ((await self.get_max_items() - 1) // self.limit) + 1
        self.embed = discord.Embed(title="Tickets", description=f"Page {current_page} of {total_pages}")
        for title in self.results:
            (ticket_id, tickettype, threadid, channel_id, player_id, player_name, messageid, claimed_by_id, claimed_by_name, jump_url, created_time) = title
            value = f"Created at: {created_time}"
            value = value if not jump_url else f"jump_url: {jump_url}\r\n" + value
            value = value if not claimed_by_name else value + f"\r\nclaimed by: {claimed_by_name}"
            self.embed.add_field(
                name=f"Ticket: {tickettype}-{player_name}-{ticket_id}",
                value=value,
                inline=False,

            )


    async def get_max_items(self):
        """Get the total number of titles."""
        if self.max_items is None:
            async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
                cursor = await db.execute("SELECT COUNT(*) FROM Tickets_Buttons")
                count = await cursor.fetchone()
                self.max_items = count[0]
        return self.max_items

class EventDisplayView(DualView):
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
                self.embed.add_field(name=f'Current Wealth',
                                     value=f'**Gold**: {gold_string}, **Essence**: {essence}',
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
                check_dict = {1: "Loyalty", 2: "Stability", 3: "Economy", 4: "Demand Building",
                              5: "Demand Improvement"}
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
                                                 3: "Percentile Effect",
                                                 4: "Randomized with 'exploding' reroll on max",
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
