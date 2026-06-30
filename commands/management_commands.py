import logging
import typing
import discord
import aiosqlite
from discord import app_commands
from discord.ext import commands
from core.autocomplete import response_trigger_autocomplete, response_followup_autocomplete
from core.memes import ensure_response_tables

class ResponseDisplayView(discord.ui.View):
    def __init__(self, user_id, guild_id, triggers, items_per_page=5):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.guild_id = guild_id
        self.triggers = triggers
        self.items_per_page = items_per_page
        self.current_page = 0
        self.update_buttons()

    def update_buttons(self):
        max_page = max(0, (len(self.triggers) - 1) // self.items_per_page)
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                if child.label == "◀️ Previous":
                    child.disabled = (self.current_page == 0)
                elif child.label == "Next ▶️":
                    child.disabled = (self.current_page >= max_page)

    async def get_page_embed(self):
        start = self.current_page * self.items_per_page
        end = start + self.items_per_page
        page_triggers = self.triggers[start:end]
        
        embed = discord.Embed(
            title="Dynamic Meme Responses List",
            description=f"Page {self.current_page + 1} of {max(1, ((len(self.triggers) - 1) // self.items_per_page) + 1)}",
            color=discord.Color.blurple()
        )
        
        async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
            for trigger_id, trigger, match_type, response, enabled, likelihood, cooldown in page_triggers:
                async with db.execute("SELECT UserID FROM Response_Users WHERE TriggerID = ?", (trigger_id,)) as c:
                    users = [row[0] for row in await c.fetchall()]
                async with db.execute("SELECT RoleID FROM Response_Roles WHERE TriggerID = ?", (trigger_id,)) as c:
                    roles = [row[0] for row in await c.fetchall()]
                async with db.execute("SELECT ChannelID FROM Response_Channels WHERE TriggerID = ?", (trigger_id,)) as c:
                    channels = [row[0] for row in await c.fetchall()]
                async with db.execute("SELECT buttonname FROM Response_Followup WHERE TriggerID = ?", (trigger_id,)) as c:
                    followups = [row[0] for row in await c.fetchall()]

                status = "🟢 Enabled" if enabled else "🔴 Disabled"
                details = (
                    f"**Match Type**: `{match_type}`\n"
                    f"**Likelihood**: `{likelihood if likelihood is not None else 100}%` | **Cooldown**: `{cooldown or 0}s`\n"
                    f"**Response**: {response[:200] if len(response) > 200 else response}\n"
                )
                constraints = []
                if users:
                    constraints.append(f"👤 Users: {', '.join(f'<@{u}>' for u in users)}")
                if roles:
                    constraints.append(f"🛡️ Roles: {', '.join(f'<@&{r}>' for r in roles)}")
                if channels:
                    constraints.append(f"💬 Channels: {', '.join(f'<#{c}>' for c in channels)}")
                if followups:
                    constraints.append(f"🔘 Buttons: {', '.join(f'`{f}`' for f in followups)}")
                
                if constraints:
                    details += "**Filters/Followups**:\n" + "\n".join(constraints)
                else:
                    details += "*No filters or followups configured.*"
                
                embed.add_field(
                    name=f"ID: {trigger_id} | Pattern: `{trigger}` ({status})",
                    value=details,
                    inline=False
                )
        return embed

    @discord.ui.button(label="◀️ Previous", style=discord.ButtonStyle.primary)
    async def prev_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("You cannot use these buttons.", ephemeral=True)
            return
        self.current_page -= 1
        self.update_buttons()
        embed = await self.get_page_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Next ▶️", style=discord.ButtonStyle.primary)
    async def next_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("You cannot use these buttons.", ephemeral=True)
            return
        self.current_page += 1
        self.update_buttons()
        embed = await self.get_page_embed()
        await interaction.response.edit_message(embed=embed, view=self)


class ManagementCommands(commands.Cog, name='management'):
    def __init__(self, bot):
        self.bot = bot

    manage_group = discord.app_commands.Group(
        name='manage',
        description='Commands related to server management'
    )

    response_group = discord.app_commands.Group(
        name='response',
        description='Commands to manage dynamic meme responses and filters.',
        parent=manage_group
    )

    # ------------------ Dynamic Response Triggers Commands ------------------

    @response_group.command(name='add_trigger', description='Add a dynamic response trigger')
    @app_commands.describe(
        trigger='The trigger string/regex',
        match_type='How to match the trigger',
        response='The text or image link to respond with',
        likelihood='Percentage chance to trigger (1-100)',
        cooldown='Cooldown in seconds'
    )
    @app_commands.choices(match_type=[
        app_commands.Choice(name='Contains', value='contains'),
        app_commands.Choice(name='Exact', value='exact'),
        app_commands.Choice(name='Regex', value='regex')
    ])
    async def add_trigger(
        self,
        interaction: discord.Interaction,
        trigger: str,
        match_type: app_commands.Choice[str],
        response: str,
        likelihood: typing.Optional[int] = 100,
        cooldown: typing.Optional[int] = 0
    ):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                await ensure_response_tables(db)
                cursor = await db.execute(
                    "INSERT INTO Response_Trigger (Trigger, MatchType, Response, Enabled, Likelihood, Cooldown) "
                    "VALUES (?, ?, ?, 1, ?, ?)",
                    (trigger, match_type.value, response, likelihood, cooldown)
                )
                trigger_id = cursor.lastrowid
                await db.commit()
            
            await interaction.followup.send(
                f"Successfully added response trigger with ID **{trigger_id}**!\n"
                f"- Trigger: `{trigger}`\n"
                f"- Match Type: `{match_type.value}`\n"
                f"- Likelihood: `{likelihood}%`\n"
                f"- Cooldown: `{cooldown}s`",
                ephemeral=True
            )
        except Exception as e:
            logging.exception(f"Error in add_trigger command: {e}")
            await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)

    @response_group.command(name='update_trigger', description='Update an existing dynamic response trigger')
    @app_commands.describe(
        trigger_id='The ID of the trigger to update',
        trigger='New trigger string/regex',
        match_type='New match type',
        response='New text or image response',
        likelihood='New likelihood percentage (1-100)',
        cooldown='New cooldown in seconds',
        enabled='Whether this trigger is active'
    )
    @app_commands.choices(match_type=[
        app_commands.Choice(name='Contains', value='contains'),
        app_commands.Choice(name='Exact', value='exact'),
        app_commands.Choice(name='Regex', value='regex')
    ])
    @app_commands.autocomplete(trigger_id=response_trigger_autocomplete)
    async def update_trigger(
        self,
        interaction: discord.Interaction,
        trigger_id: str,
        trigger: typing.Optional[str] = None,
        match_type: typing.Optional[app_commands.Choice[str]] = None,
        response: typing.Optional[str] = None,
        likelihood: typing.Optional[int] = None,
        cooldown: typing.Optional[int] = None,
        enabled: typing.Optional[bool] = None
    ):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            t_id = int(trigger_id)
        except ValueError:
            await interaction.followup.send("Invalid Trigger ID.", ephemeral=True)
            return

        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                await ensure_response_tables(db)
                # Check if trigger exists
                async with db.execute("SELECT TriggerID FROM Response_Trigger WHERE TriggerID = ?", (t_id,)) as cursor:
                    if not await cursor.fetchone():
                        await interaction.followup.send(f"Trigger with ID **{t_id}** not found.", ephemeral=True)
                        return

                updates = []
                params = []
                if trigger is not None:
                    updates.append("Trigger = ?")
                    params.append(trigger)
                if match_type is not None:
                    updates.append("MatchType = ?")
                    params.append(match_type.value)
                if response is not None:
                    updates.append("Response = ?")
                    params.append(response)
                if likelihood is not None:
                    updates.append("Likelihood = ?")
                    params.append(likelihood)
                if cooldown is not None:
                    updates.append("Cooldown = ?")
                    params.append(cooldown)
                if enabled is not None:
                    updates.append("Enabled = ?")
                    params.append(1 if enabled else 0)

                if not updates:
                    await interaction.followup.send("No updates specified.", ephemeral=True)
                    return

                params.append(t_id)
                query = f"UPDATE Response_Trigger SET {', '.join(updates)} WHERE TriggerID = ?"
                await db.execute(query, tuple(params))
                await db.commit()

            await interaction.followup.send(f"Successfully updated response trigger with ID **{t_id}**!", ephemeral=True)
        except Exception as e:
            logging.exception(f"Error in update_trigger command: {e}")
            await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)

    @response_group.command(name='remove_trigger', description='Remove an existing dynamic response trigger and all its filters')
    @app_commands.describe(trigger_id='The ID of the trigger to remove')
    @app_commands.autocomplete(trigger_id=response_trigger_autocomplete)
    async def remove_trigger(self, interaction: discord.Interaction, trigger_id: str):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            t_id = int(trigger_id)
        except ValueError:
            await interaction.followup.send("Invalid Trigger ID.", ephemeral=True)
            return

        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                await ensure_response_tables(db)
                # Check existence
                async with db.execute("SELECT Trigger FROM Response_Trigger WHERE TriggerID = ?", (t_id,)) as cursor:
                    row = await cursor.fetchone()
                    if not row:
                        await interaction.followup.send(f"Trigger with ID **{t_id}** not found.", ephemeral=True)
                        return
                    trigger_text = row[0]

                # Delete dependent records
                await db.execute("DELETE FROM Response_Users WHERE TriggerID = ?", (t_id,))
                await db.execute("DELETE FROM Response_Roles WHERE TriggerID = ?", (t_id,))
                await db.execute("DELETE FROM Response_Channels WHERE TriggerID = ?", (t_id,))
                await db.execute("DELETE FROM Response_Followup WHERE TriggerID = ?", (t_id,))
                await db.execute("DELETE FROM Response_Trigger WHERE TriggerID = ?", (t_id,))
                await db.commit()

            await interaction.followup.send(
                f"Successfully deleted trigger **{trigger_text}** (ID: {t_id}) and all associated filters/buttons.",
                ephemeral=True
            )
        except Exception as e:
            logging.exception(f"Error in remove_trigger command: {e}")
            await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)

    # ------------------ Constraint Filtering Subcommands ------------------

    @response_group.command(name='add_channel', description='Restrict a trigger to only work in a specific channel')
    @app_commands.describe(trigger_id='The trigger to restrict', channel='The text channel to allow')
    @app_commands.autocomplete(trigger_id=response_trigger_autocomplete)
    async def add_channel(self, interaction: discord.Interaction, trigger_id: str, channel: discord.TextChannel):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            t_id = int(trigger_id)
        except ValueError:
            await interaction.followup.send("Invalid Trigger ID.", ephemeral=True)
            return

        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                await ensure_response_tables(db)
                async with db.execute("SELECT TriggerID FROM Response_Trigger WHERE TriggerID = ?", (t_id,)) as cursor:
                    if not await cursor.fetchone():
                        await interaction.followup.send(f"Trigger with ID **{t_id}** not found.", ephemeral=True)
                        return
                
                # Check duplicate
                async with db.execute("SELECT 1 FROM Response_Channels WHERE TriggerID = ? AND ChannelID = ?", (t_id, channel.id)) as cursor:
                    if await cursor.fetchone():
                        await interaction.followup.send(f"Channel {channel.mention} is already added as a filter for this trigger.", ephemeral=True)
                        return

                await db.execute("INSERT INTO Response_Channels (TriggerID, ChannelID) VALUES (?, ?)", (t_id, channel.id))
                await db.commit()
            
            await interaction.followup.send(f"Successfully added channel filter {channel.mention} to trigger ID **{t_id}**.", ephemeral=True)
        except Exception as e:
            logging.exception(f"Error in add_channel command: {e}")
            await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)

    @response_group.command(name='remove_channel', description='Remove a channel restriction from a trigger')
    @app_commands.describe(trigger_id='The trigger to modify', channel='The text channel to remove restriction for')
    @app_commands.autocomplete(trigger_id=response_trigger_autocomplete)
    async def remove_channel(self, interaction: discord.Interaction, trigger_id: str, channel: discord.TextChannel):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            t_id = int(trigger_id)
        except ValueError:
            await interaction.followup.send("Invalid Trigger ID.", ephemeral=True)
            return

        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                await ensure_response_tables(db)
                # Check existence of restriction
                async with db.execute("SELECT 1 FROM Response_Channels WHERE TriggerID = ? AND ChannelID = ?", (t_id, channel.id)) as cursor:
                    if not await cursor.fetchone():
                        await interaction.followup.send(f"Channel {channel.mention} is not restricted on trigger ID **{t_id}**.", ephemeral=True)
                        return

                await db.execute("DELETE FROM Response_Channels WHERE TriggerID = ? AND ChannelID = ?", (t_id, channel.id))
                await db.commit()
            
            await interaction.followup.send(f"Successfully removed channel filter {channel.mention} from trigger ID **{t_id}**.", ephemeral=True)
        except Exception as e:
            logging.exception(f"Error in remove_channel command: {e}")
            await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)

    @response_group.command(name='add_role', description='Restrict a trigger to users with a specific role')
    @app_commands.describe(trigger_id='The trigger to restrict', role='The role to allow')
    @app_commands.autocomplete(trigger_id=response_trigger_autocomplete)
    async def add_role(self, interaction: discord.Interaction, trigger_id: str, role: discord.Role):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            t_id = int(trigger_id)
        except ValueError:
            await interaction.followup.send("Invalid Trigger ID.", ephemeral=True)
            return

        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                await ensure_response_tables(db)
                async with db.execute("SELECT TriggerID FROM Response_Trigger WHERE TriggerID = ?", (t_id,)) as cursor:
                    if not await cursor.fetchone():
                        await interaction.followup.send(f"Trigger with ID **{t_id}** not found.", ephemeral=True)
                        return
                
                # Check duplicate
                async with db.execute("SELECT 1 FROM Response_Roles WHERE TriggerID = ? AND RoleID = ?", (t_id, role.id)) as cursor:
                    if await cursor.fetchone():
                        await interaction.followup.send(f"Role **{role.name}** is already added as a filter for this trigger.", ephemeral=True)
                        return

                await db.execute("INSERT INTO Response_Roles (TriggerID, RoleID) VALUES (?, ?)", (t_id, role.id))
                await db.commit()
            
            await interaction.followup.send(f"Successfully added role filter **{role.name}** to trigger ID **{t_id}**.", ephemeral=True)
        except Exception as e:
            logging.exception(f"Error in add_role command: {e}")
            await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)

    @response_group.command(name='remove_role', description='Remove a role restriction from a trigger')
    @app_commands.describe(trigger_id='The trigger to modify', role='The role to remove restriction for')
    @app_commands.autocomplete(trigger_id=response_trigger_autocomplete)
    async def remove_role(self, interaction: discord.Interaction, trigger_id: str, role: discord.Role):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            t_id = int(trigger_id)
        except ValueError:
            await interaction.followup.send("Invalid Trigger ID.", ephemeral=True)
            return

        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                await ensure_response_tables(db)
                # Check existence of restriction
                async with db.execute("SELECT 1 FROM Response_Roles WHERE TriggerID = ? AND RoleID = ?", (t_id, role.id)) as cursor:
                    if not await cursor.fetchone():
                        await interaction.followup.send(f"Role **{role.name}** is not restricted on trigger ID **{t_id}**.", ephemeral=True)
                        return

                await db.execute("DELETE FROM Response_Roles WHERE TriggerID = ? AND RoleID = ?", (t_id, role.id))
                await db.commit()
            
            await interaction.followup.send(f"Successfully removed role filter **{role.name}** from trigger ID **{t_id}**.", ephemeral=True)
        except Exception as e:
            logging.exception(f"Error in remove_role command: {e}")
            await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)

    @response_group.command(name='add_user', description='Restrict a trigger to only work for a specific user')
    @app_commands.describe(trigger_id='The trigger to restrict', user='The user to allow')
    @app_commands.autocomplete(trigger_id=response_trigger_autocomplete)
    async def add_user(self, interaction: discord.Interaction, trigger_id: str, user: discord.User):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            t_id = int(trigger_id)
        except ValueError:
            await interaction.followup.send("Invalid Trigger ID.", ephemeral=True)
            return

        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                await ensure_response_tables(db)
                async with db.execute("SELECT TriggerID FROM Response_Trigger WHERE TriggerID = ?", (t_id,)) as cursor:
                    if not await cursor.fetchone():
                        await interaction.followup.send(f"Trigger with ID **{t_id}** not found.", ephemeral=True)
                        return
                
                # Check duplicate
                async with db.execute("SELECT 1 FROM Response_Users WHERE TriggerID = ? AND UserID = ?", (t_id, user.id)) as cursor:
                    if await cursor.fetchone():
                        await interaction.followup.send(f"User **{user.name}** is already added as a filter for this trigger.", ephemeral=True)
                        return

                await db.execute("INSERT INTO Response_Users (TriggerID, UserID) VALUES (?, ?)", (t_id, user.id))
                await db.commit()
            
            await interaction.followup.send(f"Successfully added user filter **{user.name}** to trigger ID **{t_id}**.", ephemeral=True)
        except Exception as e:
            logging.exception(f"Error in add_user command: {e}")
            await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)

    @response_group.command(name='remove_user', description='Remove a user restriction from a trigger')
    @app_commands.describe(trigger_id='The trigger to modify', user='The user to remove restriction for')
    @app_commands.autocomplete(trigger_id=response_trigger_autocomplete)
    async def remove_user(self, interaction: discord.Interaction, trigger_id: str, user: discord.User):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            t_id = int(trigger_id)
        except ValueError:
            await interaction.followup.send("Invalid Trigger ID.", ephemeral=True)
            return

        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                await ensure_response_tables(db)
                # Check existence of restriction
                async with db.execute("SELECT 1 FROM Response_Users WHERE TriggerID = ? AND UserID = ?", (t_id, user.id)) as cursor:
                    if not await cursor.fetchone():
                        await interaction.followup.send(f"User **{user.name}** is not restricted on trigger ID **{t_id}**.", ephemeral=True)
                        return

                await db.execute("DELETE FROM Response_Users WHERE TriggerID = ? AND UserID = ?", (t_id, user.id))
                await db.commit()
            
            await interaction.followup.send(f"Successfully removed user filter **{user.name}** from trigger ID **{t_id}**.", ephemeral=True)
        except Exception as e:
            logging.exception(f"Error in remove_user command: {e}")
            await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)

    # ------------------ Followup Buttons Subcommands ------------------

    @response_group.command(name='add_followup', description='Add an ephemeral button followup message to a trigger')
    @app_commands.describe(
        trigger_id='The trigger to attach this button to',
        button_name='The label shown on the button',
        response='The text/image response sent ephemerally when clicked'
    )
    @app_commands.autocomplete(trigger_id=response_trigger_autocomplete)
    async def add_followup(self, interaction: discord.Interaction, trigger_id: str, button_name: str, response: str):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            t_id = int(trigger_id)
        except ValueError:
            await interaction.followup.send("Invalid Trigger ID.", ephemeral=True)
            return

        if len(button_name) > 80:
            await interaction.followup.send("Button label must be 80 characters or fewer.", ephemeral=True)
            return

        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                await ensure_response_tables(db)
                async with db.execute("SELECT TriggerID FROM Response_Trigger WHERE TriggerID = ?", (t_id,)) as cursor:
                    if not await cursor.fetchone():
                        await interaction.followup.send(f"Trigger with ID **{t_id}** not found.", ephemeral=True)
                        return

                # Check duplicate button label for this trigger
                async with db.execute("SELECT 1 FROM Response_Followup WHERE TriggerID = ? AND buttonname = ?", (t_id, button_name)) as cursor:
                    if await cursor.fetchone():
                        await interaction.followup.send(f"Button named `{button_name}` already exists for this trigger.", ephemeral=True)
                        return

                await db.execute(
                    "INSERT INTO Response_Followup (TriggerID, buttonname, response) VALUES (?, ?, ?)",
                    (t_id, button_name, response)
                )
                await db.commit()
            
            await interaction.followup.send(f"Successfully added followup button `{button_name}` to trigger ID **{t_id}**.", ephemeral=True)
        except Exception as e:
            logging.exception(f"Error in add_followup command: {e}")
            await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)

    @response_group.command(name='remove_followup', description='Remove a followup button from a trigger')
    @app_commands.describe(
        trigger_id='The trigger to modify',
        button_name='The name of the button to remove'
    )
    @app_commands.autocomplete(
        trigger_id=response_trigger_autocomplete,
        button_name=response_followup_autocomplete
    )
    async def remove_followup(self, interaction: discord.Interaction, trigger_id: str, button_name: str):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            t_id = int(trigger_id)
        except ValueError:
            await interaction.followup.send("Invalid Trigger ID.", ephemeral=True)
            return

        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                await ensure_response_tables(db)
                async with db.execute("SELECT 1 FROM Response_Followup WHERE TriggerID = ? AND buttonname = ?", (t_id, button_name)) as cursor:
                    if not await cursor.fetchone():
                        await interaction.followup.send(f"No button named `{button_name}` found for trigger ID **{t_id}**.", ephemeral=True)
                        return

                await db.execute("DELETE FROM Response_Followup WHERE TriggerID = ? AND buttonname = ?", (t_id, button_name))
                await db.commit()
            
            await interaction.followup.send(f"Successfully removed button `{button_name}` from trigger ID **{t_id}**.", ephemeral=True)
        except Exception as e:
            logging.exception(f"Error in remove_followup command: {e}")
            await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)

    # ------------------ List / View Subcommand ------------------

    @response_group.command(name='list', description='List all configured dynamic triggers for this server')
    async def list_triggers(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                await ensure_response_tables(db)
                async with db.execute("SELECT TriggerID, Trigger, MatchType, Response, Enabled, Likelihood, Cooldown FROM Response_Trigger") as cursor:
                    triggers = await cursor.fetchall()
            
            if not triggers:
                await interaction.followup.send("No dynamic triggers configured on this server.", ephemeral=True)
                return
            
            view = ResponseDisplayView(interaction.user.id, interaction.guild_id, triggers)
            embed = await view.get_page_embed()
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        except Exception as e:
            logging.exception(f"Error in list_triggers command: {e}")
            await interaction.followup.send(f"An error occurred: {e}", ephemeral=True)
