import discord
from discord.ext import commands
import re
import aiosqlite
import logging

from proto.marshal.compat import message

from core.views import TicketView

class CreateRootModal(discord.ui.Modal, title="Create Root Ticket Message"):

    title_input = discord.ui.TextInput(
        label="Embed Title",
        style=discord.TextStyle.short,
        max_length=500,
        required=True
    )

    content_input = discord.ui.TextInput(
        label="Embed Content",
        style=discord.TextStyle.paragraph,
        max_length=2000,
        required=True
    )

    response_title_input = discord.ui.TextInput(
        label="Response Embed Title",
        style=discord.TextStyle.short,
        max_length=500,
        required=True
    )

    response_content_input = discord.ui.TextInput(
        label="Response Embed Content",
        style=discord.TextStyle.paragraph,
        max_length=2000,
        required=True
    )


    def __init__(self, channel, button_label, style, color, response_color, emoji):
        super().__init__()
        self.channel = channel
        self.button_label = button_label
        self.style = style
        self.color = color
        self.response_color = response_color
        self.emoji = emoji


    async def on_submit(self, interaction: discord.Interaction):
        message = None

        regex = r'^#(?:[0-9a-fA-F]{3}){1,2}$'

        # Validate main color
        if not re.search(regex, self.color):
            await interaction.response.send_message(
                f"Color key of {self.color} not valid",
                ephemeral=True
            )
            return

        # Validate response color
        if not re.search(regex, self.response_color):
            await interaction.response.send_message(
                f"Color key of {self.response_color} not valid",
                ephemeral=True
            )
            return

        int_color = int(self.color.lstrip('#'), 16)
        response_int_color = int(self.response_color.lstrip('#'), 16)

        try:
            embed = discord.Embed(
                title=self.title_input.value,
                description=self.content_input.value,
                color=int_color
            )

            message = await self.channel.send(embed=embed)

            async with aiosqlite.connect(
                f"pathparser_{interaction.guild_id}.sqlite"
            ) as db:
                cursor = await db.cursor()

                await cursor.execute(
                    "INSERT INTO TICKETS(messageid, title, content, color, channelid, jump_url) VALUES(?,?,?,?,?, ?)",
                    (
                        message.id,
                        self.title_input.value,
                        self.content_input.value,
                        int_color,
                        self.channel.id,
                        message.jump_url
                    )
                )

                await cursor.execute(
                    """INSERT INTO Tickets_Buttons
                       (messageid, buttonname, buttonstyle,
                        response_title, response_content,
                        color, response_color, emoji)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        message.id,
                        self.button_label,
                        self.style.value,
                        self.response_title_input.value,
                        self.response_content_input.value,
                        self.color,
                        response_int_color,
                        self.emoji
                    )
                )

                await db.commit()

            view = TicketView(
                message_id=message.id,
                guild_id=message.guild.id
            )
            await view.setup_buttons()
            await message.edit(view=view)

            await interaction.response.send_message(
                f"Root message created in {self.channel.mention}.",
                ephemeral=True
            )
        except Exception as e:
            logging.exception(f"Error adding button: {e}")
            error_message = f"Error adding button: {e}"
            if message:
                error_message += f"\nMessage ID: {message.id}"
            await interaction.response.send_message(
                error_message,
                ephemeral=True
            )



class EditRootModal(discord.ui.Modal):

    def __init__(self, channel, message_id: int, current_title: str,
                 current_content: str, current_color: int):

        super().__init__(title="Edit Root Ticket Message")

        self.channel = channel
        self.message_id = message_id
        self.current_color = current_color

        # Convert stored int color back to hex
        hex_color = f"#{current_color:06X}"

        self.title_input = discord.ui.TextInput(
            label="Embed Title",
            style=discord.TextStyle.short,
            max_length=500,
            default=current_title,
            required=True
        )

        self.content_input = discord.ui.TextInput(
            label="Embed Content",
            style=discord.TextStyle.paragraph,
            max_length=2000,
            default=current_content,
            required=True
        )

        self.color_input = discord.ui.TextInput(
            label="Embed Color (Hex)",
            style=discord.TextStyle.short,
            default=hex_color,
            required=True
        )

        self.add_item(self.title_input)
        self.add_item(self.content_input)
        self.add_item(self.color_input)

    async def on_submit(self, interaction: discord.Interaction):
        message = None
        regex = r'^#(?:[0-9a-fA-F]{3}){1,2}$'
        color_value = self.color_input.value

        if not re.search(regex, color_value):
            await interaction.response.send_message(
                f"Color key of {color_value} not valid.",
                ephemeral=True
            )
            return

        int_color = int(color_value.lstrip('#'), 16)

        try:
            embed = discord.Embed(
                title=self.title_input.value,
                description=self.content_input.value,
                color=int_color
            )

            message = await self.channel.fetch_message(self.message_id)
            await message.edit(embed=embed)

            async with aiosqlite.connect(
                f"pathparser_{interaction.guild_id}.sqlite"
            ) as db:
                await db.execute(
                    "UPDATE TICKETS SET title = ?, content = ?, color = ? WHERE messageid = ?",
                    (
                        self.title_input.value,
                        self.content_input.value,
                        int_color,
                        self.message_id
                    )
                )
                await db.commit()

            await interaction.response.send_message(
                f"Message {self.message_id} updated.",
                ephemeral=True
            )

        except discord.NotFound:
            await interaction.response.send_message(
                "Message not found.",
                ephemeral=True
            )
        except Exception as e:
            logging.exception(f"Error adding button: {e}")
            error_message = f"Error adding button: {e}"
            if message:
                error_message += f"\nMessage ID: {message.id}"
            await interaction.response.send_message(
                error_message,
                ephemeral=True
            )

class AddButtonModal(discord.ui.Modal):

    def __init__(self, channel: discord.TextChannel,
                 message_id: int,
                 style: discord.app_commands.Choice[int],
                 emoji: str):

        super().__init__(title="Add Button To Ticket")

        self.channel = channel
        self.message_id = message_id
        self.style = style
        self.emoji = emoji

        self.label_input = discord.ui.TextInput(
            label="Button Label",
            max_length=20,
            required=True
        )

        self.response_title_input = discord.ui.TextInput(
            label="Response Embed Title",
            max_length=500,
            required=True
        )

        self.response_content_input = discord.ui.TextInput(
            label="Response Embed Content",
            style=discord.TextStyle.paragraph,
            max_length=2000,
            required=True
        )

        self.response_color_input = discord.ui.TextInput(
            label="Response Embed Color (Hex)",
            default="#FFFFFF",
            required=True
        )

        self.add_item(self.label_input)
        self.add_item(self.response_title_input)
        self.add_item(self.response_content_input)
        self.add_item(self.response_color_input)

    async def on_submit(self, interaction: discord.Interaction):
        message = None
        regex = r'^#(?:[0-9a-fA-F]{3}){1,2}$'
        color_value = self.response_color_input.value

        if not re.search(regex, color_value):
            await interaction.response.send_message(
                "Invalid hex color.",
                ephemeral=True
            )
            return

        response_int_color = int(color_value.lstrip('#'), 16)

        try:
            async with aiosqlite.connect(
                f"pathparser_{interaction.guild_id}.sqlite"
            ) as db:

                cursor = await db.cursor()

                # Validate root exists
                await cursor.execute(
                    "SELECT messageid FROM TICKETS WHERE messageid = ?",
                    (self.message_id,)
                )
                if not await cursor.fetchone():
                    await interaction.response.send_message(
                        "Root ticket message not found.",
                        ephemeral=True
                    )
                    return

                # Enforce max buttons
                await cursor.execute(
                    "SELECT COUNT(*) FROM Tickets_Buttons WHERE messageid = ?",
                    (self.message_id,)
                )
                count = (await cursor.fetchone())[0]

                if count >= 5:
                    await interaction.response.send_message(
                        f"Max {5} buttons allowed per root message.",
                        ephemeral=True
                    )
                    return

                # Generate stable custom_id
                custom_id = f"ticket:{self.message_id}:{count+1}"

                # Insert
                await db.execute(
                    """INSERT INTO Tickets_Buttons
                       (messageid, buttonname, buttonstyle,
                        response_title, response_content,
                        color, response_color,
                        emoji)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        self.message_id,
                        self.label_input.value,
                        self.style.value,
                        self.response_title_input.value,
                        self.response_content_input.value,
                        None,
                        response_int_color,
                        self.emoji or None
                    )
                )

                await db.commit()

            # Rebuild view
            message = await self.channel.fetch_message(self.message_id)

            view = TicketView(
                message_id=self.message_id,
                guild_id=interaction.guild_id
            )
            await view.setup_buttons()

            await message.edit(view=view)

            await interaction.response.send_message(
                "Button added successfully.",
                ephemeral=True
            )

        except Exception as e:
            logging.exception(f"Error adding button: {e}")
            error_message = f"Error adding button: {e}"
            if message:
                error_message += f"\nMessage ID: {message.id}"
            await interaction.response.send_message(
                error_message,
                ephemeral=True
            )


class EditButtonModal(discord.ui.Modal):

    def __init__(
        self,
        channel: discord.TextChannel,
        message_id: int,
        original_label: str,
        row_data: dict,
        emoji: str
    ):
        super().__init__(title="Edit Ticket Button")

        self.channel = channel
        self.message_id = message_id
        self.original_label = original_label
        self.original_style = row_data["buttonstyle"]
        self.emoji = emoji
        hex_color = f"#{row_data['response_color']:06X}"

        self.label_input = discord.ui.TextInput(
            label="Button Label",
            default=row_data["buttonname"],
            max_length=20,
            required=True
        )

        self.response_title_input = discord.ui.TextInput(
            label="Response Embed Title",
            default=row_data["response_title"],
            max_length=500,
            required=True
        )

        self.response_content_input = discord.ui.TextInput(
            label="Response Embed Content",
            default=row_data["response_content"],
            style=discord.TextStyle.paragraph,
            max_length=2000,
            required=True
        )

        self.response_color_input = discord.ui.TextInput(
            label="Response Embed Color (Hex)",
            default=hex_color,
            required=True
        )

        self.add_item(self.label_input)
        self.add_item(self.response_title_input)
        self.add_item(self.response_content_input)
        self.add_item(self.response_color_input)

    async def on_submit(self, interaction: discord.Interaction):
        message = None
        regex = r'^#(?:[0-9a-fA-F]{3}){1,2}$'
        color_value = self.response_color_input.value

        if not re.search(regex, color_value):
            await interaction.response.send_message(
                "Invalid hex color.",
                ephemeral=True
            )
            return

        response_int_color = int(color_value.lstrip('#'), 16)

        try:
            async with aiosqlite.connect(
                f"pathparser_{interaction.guild_id}.sqlite"
            ) as db:

                await db.execute(
                    """UPDATE Tickets_Buttons
                       SET buttonname = ?,
                           response_title = ?,
                           response_content = ?,
                           response_color = ?,
                           emoji = ?
                       WHERE messageid = ? AND buttonname = ?""",
                    (
                        self.label_input.value,
                        self.response_title_input.value,
                        self.response_content_input.value,
                        response_int_color,
                        self.emoji or None,
                        self.message_id,
                        self.original_label
                    )
                )

                await db.commit()

            # Rebuild persistent view
            message = await self.channel.fetch_message(self.message_id)

            view = TicketView(
                message_id=self.message_id,
                guild_id=interaction.guild_id
            )
            await view.setup_buttons()

            await message.edit(view=view)

            await interaction.response.send_message(
                f"Button updated successfully.",
                ephemeral=True
            )

        except discord.NotFound:
            await interaction.response.send_message(
                "Message not found.",
                ephemeral=True
            )
        except Exception as e:
            logging.exception(f"Error adding button: {e}")
            error_message = f"Error adding button: {e}"
            if message:
                error_message += f"\nMessage ID: {message.id}"
            await interaction.response.send_message(
                error_message,
                ephemeral=True
            )


class EditModalResponseModal(discord.ui.Modal):

    def __init__(
        self,
        channel: discord.TextChannel,
        message_id: int,
        original_label: str,
        fieldone=None,
        fieldonetitle=None,
        fieldonedefault=None,
        fieldtwo=None,
        fieldtwotitle=None,
        fieldtwodefault=None,
        fieldthree=None,
        fieldthreetitle=None,
        fieldthreedefault=None,
        fieldfour=None,
        fieldfourtitle=None,
        fieldfourdefault=None,
        fieldfive=None,
        fieldfivetitle = None,
        fieldfivedefault = None
    ):

        super().__init__(title="Configure Modal Fields")

        self.channel = channel
        self.message_id = message_id
        self.original_label = original_label



        # Store mapping for database saving
        self.field_types = {
            1: fieldone.value if fieldone else None,
            2: fieldtwo.value if fieldtwo else None,
            3: fieldthree.value if fieldthree else None,
            4: fieldfour.value if fieldfour else None,
            5: fieldfive.value if fieldfive else None
        }
        self.title_types = {
            1: fieldonetitle if fieldonetitle else None,
            2: fieldtwotitle if fieldtwotitle else None,
            3: fieldthreetitle if fieldthreetitle else None,
            4: fieldfourtitle if fieldfourtitle else None,
            5: fieldfivetitle if fieldfivetitle else None
        }
        self.default_types = {
            1: fieldonedefault if fieldonedefault else None,
            2: fieldtwodefault if fieldtwodefault else None,
            3: fieldthreedefault if fieldthreedefault else None,
            4: fieldfourdefault if fieldfourdefault else None,
            5: fieldfivedefault if fieldfivedefault else None
        }

        # Keep references to created inputs
        self.inputs = {}

        for index, field_type in self.field_types.items():

            if field_type in (1, 2):  # Short or Long

                style = (
                    discord.TextStyle.short
                    if field_type == 1
                    else discord.TextStyle.paragraph
                )

                existing_title = self.title_types[index]
                existing_default = self.default_types[index]

                input_box = discord.ui.TextInput(
                    label=f"Field {index} Description",
                    default=existing_default,
                    required=True,
                    style=style
                )

                self.inputs[index] = input_box
                self.add_item(input_box)

    async def on_submit(self, interaction: discord.Interaction):
        try:

            async with aiosqlite.connect(
                f"pathparser_{interaction.guild_id}.sqlite"
            ) as db:

                cursor = await db.cursor()
                update_values = []
                for i in range(1, 6):

                    field_type = self.field_types.get(i)
                    if field_type == 3:  # Remove
                        update_values.extend([None, None, None])

                    elif field_type in (1, 2):
                        title_value = self.title_types[i]
                        default_value = self.inputs[i].value
                        update_values.extend([field_type, title_value, default_value])

                    else:
                        # Leave unchanged
                        update_values.extend([self.field_types.get(i), self.title_types.get(i), self.default_types.get(i)])

                await cursor.execute(
                    """
                    UPDATE Tickets_Buttons
                    SET
                        modaltypeone=?,
                        modaltitleone=?,
                        modaldefaultone=?,
                        modaltypetwo=?,
                        modaltitletwo=?,
                        modaldefaulttwo=?,
                        modaltypethree=?,
                        modaltitlethree=?,
                        modaldefaultthree=?,
                        modaltypefour=?,
                        modaltitlefour=?,
                        modaldefaultfour=?,
                        modaltypefive=?,
                        modaltitlefive=?,
                        modaldefaultfive=?
                    WHERE messageid=? AND buttonname=?
                    """,
                    (*update_values, self.message_id, self.original_label)
                )

                await db.commit()

            await interaction.response.send_message(
                "Modal fields updated successfully.",
                ephemeral=True
            )

        except Exception as e:
            await interaction.response.send_message(
                f"Error saving modal fields: {e}",
                ephemeral=True
            )