import asyncio
import datetime
import logging
import os
import random
import re
import shutil
from logging import exception

import aiosqlite
import discord
from discord.ext import commands
from dotenv import load_dotenv
import scheduler_utils
from commands import gamemaster_commands
from commands.RP_Commands import RPCommands
from core.roleplay import handle_rp_message, reinstate_rp_cache
from core.cache import add_guild_to_cache, build_home_cache, approved_channel_cache, clear_autocomplete_cache
from core.config import config_cache
from core.memes import meme_handler
from core.views import TicketView
from commands.admin_commands import AdminCommands
from commands.character_commands import CharacterCommands
from commands.gamemaster_commands import GamemasterCommands
from commands.kingdom_commands import KingdomCommands
from commands.overseer_commands import OverseerCommands
from commands.player_commands import PlayerCommands
from commands.reviewer_commands import ReviewerCommands
from commands.management_commands import ManagementCommands
from scheduler_utils import scheduler, scheduled_jobs, remind_users, start_global_scheduler, shutdown_global_scheduler
from test_functions import TestCommands


# Configure logging at the start
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s [%(filename)s:%(lineno)d] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    filename='pathparser.log',
    filemode='a'
)

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
BASE_PATH = os.getenv("PATHPARSER_DATA", "./data")
try:
    os.chdir(BASE_PATH)
except FileNotFoundError:
    logging.error(f"Could not change directory to {BASE_PATH}. Defaulting to current directory.")

bot = commands.Bot(command_prefix="!", intents=intents)


async def reinstate_cache(discord_bot: commands.Bot) -> None:
    for guild in discord_bot.guilds:
        await add_guild_to_cache(guild.id)


async def reinstate_reminders(server_bot) -> None:
    guilds = server_bot.guilds
    now = datetime.datetime.now(datetime.timezone.utc)
    for guild in guilds:
        try:
            async with aiosqlite.connect(f"pathparser_{guild.id}.sqlite") as db:
                cursor = await db.cursor()
                print(f"Reinstating reminders for guild {guild.id}")
                print(now.timestamp())
                await cursor.execute(
                    "SELECT Session_ID, Session_Thread, Hammer_Time FROM Sessions WHERE IsActive = 1 AND Hammer_Time > ?",
                    (now.timestamp(),)
                )
                reminders = await cursor.fetchall()
                for reminder in reminders:
                    (session_id, thread_id, hammer_time) = reminder
                    scheduler_utils.schedule_session_reminders(
                        session_id=session_id,
                        thread_id=thread_id,
                        hammer_time=hammer_time,
                        guild_id=guild.id,
                        bot=server_bot
                    )
        except aiosqlite.Error as e:
            logging.exception(f"Failed to reinstate reminders for guild {guild.id} with error: {e}")


async def reinstate_session_buttons(server_bot) -> None:
    guilds = server_bot.guilds
    now = datetime.datetime.now(datetime.timezone.utc)

    for guild in guilds:
        try:
            async with aiosqlite.connect(f"pathparser_{guild.id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute(
                    "SELECT Session_ID, Session_Name, Message, Session_Thread, Hammer_Time FROM Sessions WHERE IsActive = 1 AND hammer_time > ?",
                    (now.timestamp(),)
                )
                sessions = await cursor.fetchall()

                await cursor.execute("SELECT Search FROM Admin WHERE Identifier = 'Sessions_Channel'")
                channel_id = await cursor.fetchone()
                logging.info(f"Found sessions channel: {channel_id}")

                # Try to get the channel from cache, or fetch it.
                channel = server_bot.get_channel(channel_id[0])
                if not channel:
                    channel = await guild.fetch_channel(channel_id[0])

                for session in sessions:
                    session_id, session_name, message_id, channel_id, hammer_time_str = session
                    session_start_time = datetime.datetime.fromtimestamp(int(hammer_time_str), datetime.timezone.utc)
                    timeout_seconds = (
                            session_start_time - datetime.datetime.now(datetime.timezone.utc)).total_seconds()
                    # Cap the timeout at 12 hours.
                    timeout_seconds = min(timeout_seconds, 12 * 3600)
                    print(session_id)
                    # Fetch the message to be edited.
                    try:
                        message = await channel.fetch_message(message_id)
                    except discord.HTTPException as http_err:
                        logging.exception(f"Failed to fetch message {message_id} in guild {guild.id}: {http_err}")
                        continue  # Skip to the next session

                    # Create a new view with the updated timeout.
                    view = gamemaster_commands.JoinOrLeaveSessionView(
                        timeout_seconds=int(timeout_seconds),
                        session_id=session_id,
                        guild=guild,
                        session_name=session_name,
                        content=""
                    )

                    # Try to edit the message. If a rate limit occurs, wait and try again.
                    try:
                        await message.edit(view=view)
                    except discord.HTTPException as http_err:
                        logging.warning(f"Rate limit editing message {message_id} in guild {guild.id}: {http_err}")
                        # Optionally sleep for a couple seconds and then try again:
                        await asyncio.sleep(2)
                        try:
                            await message.edit(view=view)
                        except discord.HTTPException as http_err_retry:
                            logging.exception(
                                f"Retry failed for message {message_id} in guild {guild.id}: {http_err_retry}")
                            continue  # Skip this session if it still fails

                    # Add a small delay to prevent hammering the API.
                    await asyncio.sleep(0.5)

        except aiosqlite.Error as e:
            logging.exception(f"Failed to reinstate session buttons for guild {guild.id} with error: {e}")
        except Exception as general_e:
            logging.exception(f"An unexpected error occurred for guild {guild.id}: {general_e}")



async def reinstate_server_buttons(server_bot) -> None:
    guilds = server_bot.guilds
    now = datetime.datetime.now(datetime.timezone.utc)

    for guild in guilds:
        try:
            async with aiosqlite.connect(f"pathparser_{guild.id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute("""
                SELECT t.messageid, channelid, t.jump_url, count(buttonname)
                FROM tickets t 
                left join tickets_buttons tb on t.messageid = tb.messageid 
                GROUP BY t.messageid, channelid
                order by channelid desc""")
                messages = await cursor.fetchall()

                await cursor.execute("SELECT Search FROM Admin WHERE Identifier = 'Admin_Log'")
                log_channel_id = await cursor.fetchone()
                logging.info(f"Found sessions channel: {log_channel_id[0]}")

                old_channel = None
                for message in messages:
                    await asyncio.sleep(2) # Slow down API calls
                    message_id, channel_id, jump_url, button_count = message
                    if button_count > 0:
                        if channel_id != old_channel:
                            old_channel = channel_id
                            channel = server_bot.get_channel(channel_id)
                        try:
                            message = await channel.fetch_message(message_id)
                            if message:
                                view = TicketView(
                                    message_id=message_id,
                                    guild_id=guild.id,
                                )
                                await view.setup_buttons()
                                try:
                                    await message.edit(view=view)
                                except Exception as e:
                                    log_channel = server_bot.get_channel(log_channel_id[0])
                                    await log_channel.send(f"Failed to edit message in guild {guild.id}: {e}\r\nMessage:{message_id}, channel:{channel_id}, jump_url:{jump_url}")
                                except discord.HTTPException as http_err:
                                    logging.warning(f"Rate limit editing message {message_id} in guild {guild.id}: {http_err}")
                                    # Optionally sleep for a couple seconds and then try again:
                                    await asyncio.sleep(2)
                                    await message.edit(view=view)
                        except discord.HTTPException as http_err:
                            logging.exception(f"Failed to fetch message {message_id} in guild {guild.id}: {http_err}")
                            continue  # Skip to the next session
        except aiosqlite.Error as e:
            logging.exception(f"Failed to reinstate session buttons for guild {guild.id} with error: {e}")
        except Exception as general_e:
            logging.exception(f"An unexpected error occurred for guild {guild.id}: {general_e}")

@bot.event
async def on_ready():
    await bot.wait_until_ready()
    await bot.add_cog(TestCommands(bot))
    await bot.add_cog(CharacterCommands(bot))
    await bot.add_cog(AdminCommands(bot))
    await bot.add_cog(GamemasterCommands(bot))
    await bot.add_cog(PlayerCommands(bot))
    await bot.add_cog(ReviewerCommands(bot))
    await bot.add_cog(RPCommands(bot))
    await bot.add_cog(KingdomCommands(bot))
    await bot.add_cog(OverseerCommands(bot))
    await bot.add_cog(ManagementCommands(bot))
    await bot.tree.sync()
    await start_global_scheduler(bot)
    await reinstate_reminders(bot)
    await reinstate_session_buttons(bot)
    await reinstate_server_buttons(bot)
    await reinstate_cache(bot)
    await reinstate_rp_cache(bot)
    await config_cache.initialize_configuration(discord_bot=bot)
    # Move background tasks here
    bot.loop.create_task(config_cache.refresh_cache_periodically(600, bot))
    bot.loop.create_task(clear_autocomplete_cache())
    logging.info(f"Bot is ready and logged in as {bot.user}")


@bot.event
async def on_disconnect():
    print("Bot is disconnecting.")


@bot.event
async def on_connect():
    await start_global_scheduler(bot)



@bot.event
async def on_message(message):
    if message.author.bot:
        return
    guild_id = message.guild.id
    if isinstance(message.channel, discord.channel.TextChannel):
        channel_id = message.channel.id
    elif isinstance(message.channel, discord.channel.Thread):
        async with build_home_cache.lock:
            thread_id = message.channel.id
            if guild_id in build_home_cache.cache:
                build_home = build_home_cache.cache[guild_id]
                if thread_id in build_home:
                    information = build_home.get[thread_id]
                    if information[1] == message.author.id:
                        await message.pin()
                        information[0] -= 1
                        update_message = await message.channel.fetch_message(information[2])
                        await update_message.edit(content=f"**{information[0] // 2} messages remaining!**")
                    if message.author.system:
                        await message.delete()
                        information[0] -= 1
                    if information[0] == 0:
                        build_home.pop(thread_id)
                        update_message = await message.channel.fetch_message(information[2])
                        await update_message.delete()

        channel_id = message.channel.parent_id

    else:
        channel_id = None
    try:
        async with config_cache.lock:
            configs = config_cache.cache.get(message.guild.id, {})
            no_ping_role = configs.get('Do_Not_Ping')
            no_ping_emoji = configs.get('Do_Not_Ping_React')
    except Exception:
        logging.error("Error getting server configs", exc_info=True)
        no_ping_role = None
        no_ping_emoji = None

    # Check if the guild is in the cache
    async with approved_channel_cache.lock:
        if guild_id in approved_channel_cache.cache:
            if channel_id in approved_channel_cache.cache[guild_id]:
                multiplier = approved_channel_cache.cache[guild_id][channel_id]
                await handle_rp_message(message, multiplier)
                if message.mentions and no_ping_role:
                    try:
                        no_ping_role_flake = message.guild.get_role(no_ping_role)
                        for member in message.mentions:
                            if no_ping_role_flake in member.roles:
                                await message.add_reaction(no_ping_emoji)
                                break
                    except Exception:
                        pass
            else:
                logging.debug(f"Channel {channel_id} is not approved. Processing commands.")
                await meme_handler(message)
                await bot.process_commands(message)
        else:
            logging.debug(f"Guild {guild_id} not in cache. Adding.")
            await add_guild_to_cache(guild_id)
            if channel_id in approved_channel_cache.cache[guild_id]:
                logging.debug(f"Channel {channel_id} is approved after cache update.")
                await handle_rp_message(message)
            else:
                logging.debug(f"Channel {channel_id} is still not approved. Processing commands.")
                await meme_handler(message)
                await bot.process_commands(message)


@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    try:
        if payload.message_author_id == bot.user.id:
            return
        elif payload.user_id == bot.user.id:
            return
        else:
            async with config_cache.lock:
                configs = config_cache.cache.get(payload.guild_id, {})
                quote_emote = configs.get('quote_emote')
                quote_channel_id = configs.get('quote_channel')
                if not quote_emote or not quote_channel_id:
                    return
            if payload.channel_id == quote_channel_id:
                return
            channel = await bot.fetch_channel(payload.channel_id)
            message = await channel.fetch_message(payload.message_id)
            reaction_count = discord.utils.get(message.reactions, emoji=quote_emote)
            quote_channel = bot.get_channel(quote_channel_id)
            if quote_channel and reaction_count.count > 5:
                await message.forward(destination=quote_channel)
    except Exception as e:
        logging.error(f"Error getting reaction count {e}", exc_info=True)
        return

@bot.event
async def on_member_join(member: discord.Member):
    try:
        async with aiosqlite.connect(f"pathparser_{member.guild.id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute("select * from rp_players where user_id = ?", (member.id,))
            present = await cursor.fetchone()
            if present:
                await cursor.execute("update rp_players set join_time = ? where user_id = ?", (member.joined_at.timestamp(), member.id))
            else:
                await cursor.execute("insert into rp_players (user_id, user_name, join_time) values (?, ?, ?) ", (member.id, member.name, member.joined_at.timestamp()))
    except Exception as e:
        logging.error(f"Error getting member {member.name} with exception: {e}", exc_info=True)

@bot.event
async def on_guild_join(guild):
    # Using relative paths here, assuming the bot is running in the correct directory (BASE_PATH)
    source = "pathparser.sqlite"
    destination = f"pathparser_{guild.id}.sqlite"
    try:
        shutil.copyfile(source, destination)
        logging.info(f"Copied {source} to {destination} for guild {guild.id}")
    except FileNotFoundError:
        logging.error(f"Could not find source database {source} to copy for new guild {guild.id}")

@bot.event
async def on_channel_delete(channel: discord.TextChannel):
    try:
        async with aiosqlite.connect(f"pathparser_{channel.guild.id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute("delete from rp_approved_channels where channel_id = ?", (channel.id,))
            await db.commit()
    except Exception as e:
        logging.error(f"Error getting channel {channel.name} with exception: {e}", exc_info=True)

bot.run(os.getenv("DISCORD_TOKEN"))
