import logging
import typing
from dataclasses import dataclass, field
from math import ceil
from typing import Dict

import discord
from discord import app_commands
from discord.ext import commands
import aiosqlite
import asyncio
import json
import difflib
from datetime import datetime

from unidecode import unidecode

import shared_functions


@dataclass
class RoleplaySettings:
    min_post_length: int
    similarity_threshold: float
    min_rewards: int
    max_rewards: int
    reward_multiplier: float
    reward_name: str = "coins"
    reward_emoji: str = "<:RPCash:884166313260503060>"


@dataclass
class RoleplayInfoCache:
    cache: Dict[int, RoleplaySettings] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


roleplay_info_cache = RoleplayInfoCache()


async def use_item(interaction: discord.Interaction, item_name: typing.Optional[str], item_id: typing.Optional[int] = None):
    guild_id = interaction.guild.id
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.execute(
                "SELECT actions_1_type, actions_1_subtype, actions_1_behavior, actions_2_type, actions_2_subtype, actions_2_behavior, actions_3_type, actions_3_subtype, actions_3_behavior FROM RP_Store_Items WHERE name = ? or item_id = ?",
                (item_name, item_id))
            item_info = await cursor.fetchone()
            if item_info:
                actions_1_type, actions_1_subtype, actions_1_behavior, actions_2_type, actions_2_subtype, actions_2_behavior, actions_3_type, actions_3_subtype, actions_3_behavior = item_info
                if actions_1_type and actions_1_subtype and actions_1_behavior:
                    actions_1 = await handle_action(interaction, actions_1_type, actions_1_subtype, actions_1_behavior)
                else:
                    actions_1 = 0
                if actions_2_type and actions_2_subtype and actions_2_behavior:
                    actions_2 = await handle_action(interaction, actions_2_type, actions_2_subtype, actions_2_behavior)
                else:
                    actions_2 = 0
                if actions_3_type and actions_3_subtype and actions_3_behavior:
                    actions_3 = await handle_action(interaction, actions_3_type, actions_3_subtype, actions_3_behavior)
                else:
                    actions_3 = 0
                return actions_1, actions_2, actions_3
            else:
                raise ValueError("Item not found.")
    except (aiosqlite.Error, TypeError, ValueError) as e:
        logging.exception(f"An error occurred while using item: {e}")
        return -1, -1, -1


async def handle_action(interaction: discord.Interaction, actions_type: str, actions_subtype: str,
                        actions_behavior: str):
    try:
        if int(actions_type) == 1:
            role = interaction.guild.get_role(int(actions_behavior))
            if int(actions_subtype) == 1 and role not in interaction.user.roles:
                await interaction.user.add_roles(role)
                return f"role of  {role.name} has been added!"
            elif int(actions_subtype) == 2 and role in interaction.user.roles:
                await interaction.user.remove_roles(role)
                return f"role of  {role.name} has been removed!"
            else:
                if int(actions_subtype) == 1:
                    return "User already has role and does not need another..."
                else:
                    return "User does not have role and does not need it removed."
        else:
            async with aiosqlite.connect(f"pathparser_{interaction.guild.id}.sqlite") as db:
                cursor = await db.cursor()
                if int(actions_type) == 2:
                    if int(actions_subtype) == 1:
                        await cursor.execute("UPDATE RP_Players SET balance = balance + ? WHERE user_id = ?",
                                             (actions_behavior, interaction.user.id))
                    else:
                        await cursor.execute("UPDATE RP_Players SET balance = balance - ? WHERE user_id = ?",
                                             (actions_behavior, interaction.user.id))
                    await db.commit()
                else:
                    await cursor.execute(
                        "Select Item_Quantity from RP_PLayers_Items WHERE player_id = ? and item_name = ?",
                        (interaction.user.id, actions_behavior))
                    item_quantity_info = await cursor.fetchone()
                    item_quantity = int(item_quantity_info[0]) if item_quantity_info else None
                    if int(actions_subtype) == 1:
                        if item_quantity is None:
                            await cursor.execute(
                                "INSERT INTO RP_Players_Items (player_id, item_name, item_quantity) VALUES (?, ?, 1)",
                                (interaction.user.id, actions_behavior))
                        else:
                            await cursor.execute(
                                "UPDATE RP_Players_Items SET Item_Quantity = Item_Quantity + 1 WHERE user_id = ? and Item_Name = ?",
                                (interaction.user.id, actions_behavior))
                        await db.commit()
                    elif int(actions_subtype) == 2 and item_quantity:
                        if item_quantity == 1:
                            await cursor.execute("DELETE FROM RP_Players_Items WHERE user_id = ? and item_name = ?",
                                                 (interaction.user.id, actions_behavior))
                        else:
                            await cursor.execute(
                                "UPDATE RP_Players_Items SET item_quantity = item_quantity - ? WHERE user_id = ? AND Item_Name = ?",
                                (interaction.user.id, actions_behavior))
                        await db.commit()
        return 1
    except (aiosqlite.Error, TypeError, ValueError) as e:
        logging.exception(f"An error occurred while handling action: {e}")
        return -1


async def handle_requirements(requirements_type, requirements_pair, interaction, user_id, balance):
    try:
        async with aiosqlite.connect(f"pathparser_{interaction.guild.id}.sqlite") as db:
            cursor = await db.cursor()

            if requirements_type == 1:
                role = interaction.guild.get_role(int(requirements_pair))
                user_roles = interaction.user.roles

                if role not in user_roles:
                    validation = False
                else:
                    validation = True
            elif requirements_type == 2:
                if balance > requirements_pair:
                    validation = True
                else:
                    validation = False
            else:
                await cursor.execute("SELECT Item_Quantity FROM RP_Players_Items WHERE player_id = ? and item_name = ?",
                                     (user_id, requirements_pair))
                item_quantity = await cursor.fetchone()
                if item_quantity is None:
                    validation = False
                else:
                    validation = True
        return validation
    except (aiosqlite.Error, TypeError, ValueError) as e:
        logging.exception(f"An error occurred while handling requirements: {e}")
        return False


async def add_guild_to_rp_cache(guild_id: int) -> None:
    try:
        async with roleplay_info_cache.lock:
            async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute("""
                    SELECT Minimum_Post_Length_In_Characters, Similarity_Threshold,
                           Minimum_Reward, Maximum_Reward, Reward_Multiplier,
                           reward_name, reward_emoji
                    FROM rp_guild_info
                """)
                settings_row = await cursor.fetchone()
                if settings_row:
                    settings = RoleplaySettings(
                        min_post_length=settings_row[0],
                        similarity_threshold=settings_row[1],
                        min_rewards=settings_row[2],
                        max_rewards=settings_row[3],
                        reward_multiplier=settings_row[4],
                        reward_name=settings_row[5],
                        reward_emoji=settings_row[6]
                    )
                    roleplay_info_cache.cache[guild_id] = settings
    except (aiosqlite.Error, TypeError, ValueError) as e:
        logging.exception(f"Failed to add guild {guild_id} to cache with error: {e}")


async def reinstate_rp_cache(bot: commands.Bot) -> None:
    guilds = bot.guilds
    for guild in guilds:
        await add_guild_to_rp_cache(guild.id)


MAX_SIMILARITY_LENGTH = 1000  # Maximum characters to consider in similarity checks
MAX_COMPARISONS = 2  # Number of recent posts to compare against
SIMILARITY_TIMEOUT = 0.05  # Maximum time in seconds for similarity checks


# Handler for RP messages

async def handle_rp_message(message):
    try:
        logging.debug(f"Received message from {message.author} in guild {message.guild.id}: {message.content}")

        # Ignore messages wrapped in parentheses (OOC)
        guild_id = message.guild.id
        content = message.content.strip()
        if content.startswith('(') and content.endswith(')'):
            logging.debug("Message is OOC (wrapped in parentheses); ignoring.")
            return

        # Ensure the guild's settings are in the cache
        async with roleplay_info_cache.lock:
            if guild_id not in roleplay_info_cache.cache:
                logging.debug(f"Guild {guild_id} not in roleplay_info_cache. Adding to cache.")
                await add_guild_to_rp_cache(guild_id)
            settings = roleplay_info_cache.cache[guild_id]
            logging.debug(f"Retrieved settings for guild {guild_id}: {settings}")

        # Extract settings with defaults
        min_content_length = settings.min_post_length or 50
        similarity_threshold = settings.similarity_threshold / 100 or 0.8
        minimum_reward = settings.min_rewards or 1
        maximum_reward = settings.max_rewards or 100
        reward_multiplier = settings.reward_multiplier or 1
        reward_name = settings.reward_name or "coins"
        reward_emoji = settings.reward_emoji or "<:RPCash:884166313260503060>"
        logging.debug(
            f"Settings for guild {guild_id}: min_content_length={min_content_length}, "
            f"similarity_threshold={similarity_threshold}, minimum_reward={minimum_reward}, "
            f"maximum_reward={maximum_reward}, reward_multiplier={reward_multiplier}, "
            f"reward_name='{reward_name}', reward_emoji='{reward_emoji}'"
        )

        user_id = message.author.id
        user_name = message.author.name
        now = datetime.utcnow()
        logging.debug(f"Processing message at {now.isoformat()} from user {user_id} ({user_name})")

        async with aiosqlite.connect(f"pathparser_{message.guild.id}.sqlite") as db:
            # Fetch user data
            cursor = await db.execute(
                "SELECT balance, last_post_time, recent_posts FROM RP_Players WHERE user_id = ?",
                (user_id,)
            )
            user_data = await cursor.fetchone()

            if user_data:
                balance, last_post_time_str, recent_posts_str = user_data
                logging.debug(
                    f"Retrieved user data for {user_id}: balance={balance}, last_post_time={last_post_time_str}"
                )
                if last_post_time_str:
                    last_post_time = datetime.fromisoformat(last_post_time_str)
                else:
                    last_post_time = None
                recent_posts = json.loads(recent_posts_str)
            else:
                # Create a new user record
                balance = 0
                last_post_time = None
                recent_posts = []
                await db.execute(
                    "INSERT INTO RP_Players (user_id, user_name, balance, last_post_time, recent_posts) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (user_id, user_name, balance, None, json.dumps(recent_posts))
                )
                await db.commit()
                logging.debug(f"Created new user record for {user_id}")

            # Content Quality Check
            if len(content) < min_content_length:
                logging.debug(
                    f"Message is too short ({len(content)} characters); minimum is {min_content_length}"
                )

                return

            # Content Similarity Check
            is_similar = False
            truncated_content = truncate_text(content)
            logging.debug(f"Truncated content for similarity check: {truncated_content}")

            for past_content in recent_posts[-MAX_COMPARISONS:]:
                truncated_past_content = truncate_text(past_content)
                logging.debug(f"Comparing to past content: {truncated_past_content}")

                # Time the similarity calculation
                start_time = asyncio.get_event_loop().time()

                similarity_ratio = difflib.SequenceMatcher(
                    None, truncated_content, truncated_past_content
                ).ratio()

                elapsed_time = asyncio.get_event_loop().time() - start_time

                logging.debug(
                    f"Similarity ratio: {similarity_ratio}, elapsed time: {elapsed_time}s"
                )

                if elapsed_time > SIMILARITY_TIMEOUT:
                    # Skip this check if it takes too long
                    logging.warning(
                        f"Similarity check took too long ({elapsed_time}s); skipping this comparison"
                    )
                    continue

                if similarity_ratio > similarity_threshold:
                    logging.debug(
                        f"Message is too similar to recent post (similarity_ratio={similarity_ratio})"
                    )
                    is_similar = True
                    break


            # Time since last post
            if last_post_time:
                time_since_last_post = (now - last_post_time).total_seconds()
                logging.debug(f"Time since last post: {time_since_last_post} seconds")
            else:
                time_since_last_post = None  # First recorded post
                logging.debug("This is the user's first recorded post")

            # Update user's last post time
            last_post_time_str = now.isoformat()

            # Append current post to recent posts
            recent_posts.append(content)
            # Keep only the last 5 posts
            recent_posts = recent_posts[-MAX_COMPARISONS:]
            recent_posts_str = json.dumps(recent_posts)

            # Calculate Reward
            content_length = len(content)
            reward = calculate_reward(
                content_length, time_since_last_post, reward_multiplier, minimum_reward, maximum_reward
            )
            logging.debug(f"Calculated reward: {reward}")

            # Update user's balance and other data in the database
            balance += reward
            logging.debug(f"Updated balance for user {user_id}: {balance}")

            await db.execute(
                "UPDATE RP_Players SET balance = ?, last_post_time = ?, recent_posts = ? WHERE user_id = ?",
                (balance, last_post_time_str, recent_posts_str, user_id)
            )
            await db.commit()
            logging.debug(f"User {user_id}'s data updated in database")

        # Provide feedback to the user

        logging.debug(f"Sent reward message to user {user_id}")

    except Exception as e:
        logging.exception(f"Error in handle_rp_message: {e}")
        # Optionally, send a message to the channel or notify an admin



def truncate_text(text):
    """Truncate text to the maximum similarity length."""
    return text[:MAX_SIMILARITY_LENGTH]

def calculate_reward(content_length, time_since_last_post, multiplier, minimum_reward, maximum_reward):
    """
    Calculate the reward based on content length and time since last post.
    Rewards increase with longer intervals between posts, up to a maximum cap.
    """
    # Base reward: 1 coin per 10 characters
    base_reward = content_length // 10 * multiplier

    # Time bonus: Additional coins based on time since last post
    if time_since_last_post is not None:
        MAX_TIME = 6 * 60 * 60  # 6 hours in seconds
        time_bonus_seconds = min(time_since_last_post, MAX_TIME)
        time_bonus = int(time_bonus_seconds // (30 * 60))  # 1 coin per 30 minutes
    else:
        time_bonus = 0  # No time bonus for first post

    # Total reward calculation
    total_reward = base_reward + time_bonus

    # Enforce minimum and maximum rewards
    total_reward = max(minimum_reward, min(total_reward, maximum_reward))

    return total_reward


async def rp_inventory_autocomplete(
        interaction: discord.Interaction,
        current: str) -> list[app_commands.Choice[str]]:
    data = []
    guild_id = interaction.guild.id
    current = unidecode(current.lower())
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            # Correct parameterized query
            cursor = await db.execute(
                "SELECT Item_Name FROM rp_players_items WHERE player_id = ? and item_name LIKE ? LIMIT 20",
                (interaction.user.id, f"%{current}%",))
            items_list = await cursor.fetchall()

            # Populate choices
            for item in items_list:
                if current in item[0].lower():
                    data.append(app_commands.Choice(name=item[0], value=item[0]))

    except (aiosqlite.Error, TypeError, ValueError) as e:
        logging.exception(f"An error occurred while fetching settings: {e}")
    return data


# Helper Functions
async def fetch_user_balance(db, user_id):
    cursor = await db.execute("SELECT balance FROM RP_Players WHERE user_id = ?", (user_id,))
    return await cursor.fetchone()


async def fetch_item_data(db, item_name):
    cursor = await db.execute(
        """SELECT item_id, price, description, stock_remaining, inventory, usable, sellable, custom_message,
           matching_requirements, requirements_1_type, requirements_1_pair, requirements_2_type,
           requirements_2_pair, requirements_3_type, requirements_3_pair, actions_1_type,
           actions_1_subtype, actions_1_behavior, actions_2_type, actions_2_subtype,
           actions_2_behavior, actions_3_type, actions_3_subtype, actions_3_behavior
           FROM RP_Store_Items WHERE name = ?""",
        (item_name,)
    )
    return await cursor.fetchone()


def validate_stock(stock_remaining, amount):
    if stock_remaining is not None:
        if stock_remaining == 0:
            return 0, "This item is out of stock."
        elif 0 < stock_remaining < amount:
            # Adjust amount to available stock
            return stock_remaining, f"Only {stock_remaining} of this item is available. Adjusting your purchase."
        elif stock_remaining == -1:
            # Infinite stock, no adjustment needed
            return amount, None
    return amount, None


async def validate_requirements(requirements, matching_requirements, interaction, user_id, old_balance):
    type_dict = {1: "Role", 2: "Balance", 3: "Item"}
    validation_results = []
    for req_type, req_pair in zip(requirements[::2], requirements[1::2]):
        if req_type and req_pair:
            valid = await handle_requirements(req_type, req_pair, interaction, user_id, old_balance)
            validation_results.append((valid, req_type, req_pair))

    if matching_requirements == 1 and not all(v[0] for v in validation_results):
        unmet = [f"{type_dict[t]}: {p}" for v, t, p in validation_results if not v]
        return False, f"Requirements not met: {', '.join(unmet)}"
    elif matching_requirements == 2 and not any(v[0] for v in validation_results):
        unmet = [f"{type_dict[t]}: {p}" for v, t, p in validation_results if not v]
        return False, f"At least one of the following requirements must be met: {', '.join(unmet)}"
    return True, None


async def update_balance_and_stock(db, user_id, new_balance, item_name, stock_remaining, amount):
    await db.execute("UPDATE RP_Players SET balance = ? WHERE user_id = ?", (new_balance, user_id))
    if stock_remaining is not None and stock_remaining != -1:
        new_stock = stock_remaining - amount if stock_remaining > 0 else 0
        await db.execute("UPDATE RP_Store_Items SET stock_remaining = ? WHERE name = ?", (new_stock, item_name))
    await db.commit()


async def handle_inventory_or_use(db, interaction, user_id, item_id, item_name, amount, inventory, custom_message):
    if inventory == 0:  # Item is consumed immediately
        for _ in range(amount):
            try:
                await use_item(interaction, item_name)
            except discord.errors.Forbidden:
                return "An error occurred while using the item! Bot lacks permission to modify roles."
            except Exception as e:
                logging.exception(f"Error using item: {e}")
                return "An error occurred while using the item."
        return f"You used {amount} {item_name}. \r\n {custom_message}"
    else:  # Add item to inventory
        cursor = await db.execute(
            "SELECT Item_Quantity FROM RP_Players_Items WHERE player_id = ? AND item_name = ?",
            (user_id, item_name)
        )
        item_quantity = await cursor.fetchone()
        if item_quantity is None:
            await db.execute(
                "INSERT INTO RP_Players_Items (player_id, item_id, item_name, item_quantity) VALUES (?, ?, ?, ?)",
                (user_id, item_id, item_name, amount)
            )
        else:
            await db.execute(
                "UPDATE RP_Players_Items SET Item_Quantity = Item_Quantity + ? WHERE player_id = ? AND item_name = ?",
                (amount, user_id, item_name)
            )
        await db.commit()
        return f"You bought {amount} {item_name} and added them to your inventory."


async def handle_use(db, interaction: discord.Interaction, user_id: int, item_name: typing.Optional[str] = None, item_id: typing.Optional[int] = None, amount: int = 1):
    cursor = await db.cursor()
    if item_id is None and item_name is None:
        # neither value provided.
        raise ValueError("No item provided.")
    await cursor.execute(
        "SELECT Item_Quantity FROM RP_Players_Items WHERE Player_ID = ? and (Item_Name = ? OR Item_ID = ?)",
        (user_id, item_name, item_id))
    item_quantity = await cursor.fetchone()
    await cursor.execute(
        "SELECT Custom_message from RP_Store_Items WHERE name = ? or item_id = ?", (item_name, item_id))
    custom_message = await cursor.fetchone()
    if not item_quantity:
        return f"You don't have any {item_name} in your inventory."
    amount = min(amount, item_quantity[0])
    response = f"You have used {amount}: {item_name}."
    response += custom_message[0] if custom_message[0] else ""
    for _ in range(amount):
        item_used = await use_item(interaction=interaction, item_id=item_id, item_name=item_name)
        (actions_1, actions_2, actions_3) = item_used
        if actions_1 == -1 or actions_2 == -1 or actions_3 == -1:
            return "An error occurred while using the item."
    update_quantity = item_quantity[0] - amount
    if update_quantity > 0:
        await cursor.execute(
            "UPDATE RP_Players_Items SET Item_Quantity = ? WHERE player_id = ? and (item_name = ? or item_id = ?)",
            (update_quantity, user_id, item_name, item_id))
    else:
        await cursor.execute(
            "DELETE FROM RP_Players_Items WHERE player_id = ? and (item_name = ? or item_id = ?)",
            (user_id, item_name, item_id))
    await db.commit()
    return response


class RPCommands(commands.Cog, name='RP'):
    def __init__(self, bot):
        self.bot = bot

    roleplay_group = discord.app_commands.Group(
        name='roleplay',
        description='roleplay Roots commands.'
    )

    @roleplay_group.command(name="help", description="Get help with roleplay commands.")
    async def roleplay_help(self, interaction: discord.Interaction):
        """Help commands for the associated tree"""
        await interaction.response.defer(thinking=True, ephemeral=True)
        embed = discord.Embed(
            title=f"Roleplay Commands Help",
            description=f'This is a list of GM administrative commands',
            colour=discord.Colour.blurple())

        embed.add_field(
            name=f'__**Roleplay Commands**__',
            value="""
            Commands for handling your roleplay currency and items! \r\n
            **/roleplay balance** - Check your roleplay balance! \n
            **/roleplay buy** - Buy an item from the store! \n
            **/roleplay inventory** - View your roleplay inventory! \n
            **/roleplay item** - Display information about an item! \n
            **/roleplay leaderboard** - View the roleplay leaderboard! \n
            **/roleplay sell** - Sell an item from your inventory! \n
            **/roleplay send** - Send RP to another user! \n
            **/roleplay store** - Display the store! \n
            **/roleplay use** - Use an item from your inventory! \n
            """, inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)

    @roleplay_group.command(name="balance", description="Check your roleplay balance")
    async def roleplay_balance(self, interaction: discord.Interaction, user: typing.Optional[discord.User] = None):
        await interaction.response.defer(thinking=True)

        async with roleplay_info_cache.lock:
            if interaction.guild.id not in roleplay_info_cache.cache:
                await add_guild_to_rp_cache(interaction.guild.id)
            settings = roleplay_info_cache.cache[interaction.guild.id]

            reward_name = settings.reward_name if settings.reward_name else "coins"
            reward_emoji = settings.reward_emoji if settings.reward_emoji else "<:RPCash:884166313260503060>"
        if user is None:
            user_id = interaction.user.id
        else:
            user_id = user.id
        async with aiosqlite.connect(f"pathparser_{interaction.guild.id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute("SELECT balance FROM RP_Players WHERE user_id = ?", (user_id,))
            user_data = await cursor.fetchone()
            await cursor.execute(
                """
                SELECT rank
                FROM (SELECT user_id, 
                balance, 
                RANK() OVER (ORDER BY balance DESC) AS rank
                FROM rp_players
                ) ranked
                WHERE user_id = ?;""", (user_id,))
            user_rank = await cursor.fetchone()
            if user_data:
                balance = user_data[0]
                formatted_balance = "{:,}".format(balance)
                ordinal_position = shared_functions.ordinal(user_rank[0])
                embed = discord.Embed(title=interaction.user.name, description=f"Leaderboard Rank: {ordinal_position}")
                try:
                    embed.set_thumbnail(url=interaction.user.avatar.url)
                except AttributeError:
                    pass
                embed.add_field(name="Balance", value=f"{formatted_balance} {reward_name} {reward_emoji}")
                await interaction.followup.send(embed=embed)
            else:
                await interaction.followup.send("You don't have a balance yet.")

    @roleplay_group.command(name="buy", description="buy an item from the store")
    @app_commands.autocomplete(item_name=shared_functions.rp_store_autocomplete)
    async def roleplay_buy(self, interaction: discord.Interaction, item_name: str, amount: int = 1):
        await interaction.response.defer(thinking=True)
        user_id = interaction.user.id

        if amount < 1:
            await interaction.followup.send("You can't buy less than 1 item.")
            return

        async with aiosqlite.connect(f"pathparser_{interaction.guild.id}.sqlite") as db:
            # Fetch user balance
            user_data = await fetch_user_balance(db, user_id)
            if not user_data:
                await interaction.followup.send("You don't have a balance yet.")
                return

            old_balance = user_data[0]

            # Fetch item data
            item_data = await fetch_item_data(db, item_name)
            if not item_data:
                await interaction.followup.send("This item does not exist.")
                return

            # Unpack item data
            (
                item_id, item_cost, item_description, stock_remaining, inventory, usable, sellable, custom_message,
                matching_requirements, *requirements_and_actions
            ) = item_data

            # Validate stock
            amount, stock_check_message = validate_stock(stock_remaining, amount)
            if stock_check_message:
                await interaction.followup.send(stock_check_message)
                return

            # Get server customized coins name and emoji
            async with roleplay_info_cache.lock:
                if interaction.guild.id not in roleplay_info_cache.cache:
                    await add_guild_to_rp_cache(interaction.guild.id)
                settings = roleplay_info_cache.cache[interaction.guild.id]
                reward_name = settings.reward_name if settings.reward_name else "coins"
                reward_emoji = settings.reward_emoji if settings.reward_emoji else "<:RPCash:884166313260503060>"

            # Check if user can afford the item
            total_cost = item_cost * amount
            if total_cost > old_balance:
                await interaction.followup.send(
                    f"You don't have enough {reward_name} {reward_emoji} to buy this item. You need {total_cost} {reward_name} but only have {old_balance}."
                )
                return

            # Validate requirements
            requirements_valid = await validate_requirements(
                requirements_and_actions[:6], matching_requirements, interaction, user_id, old_balance
            )
            if not requirements_valid[0]:
                await interaction.followup.send(requirements_valid[1])
                return

            # Update user balance and item stock
            new_balance = old_balance - total_cost
            await update_balance_and_stock(db, user_id, new_balance, item_name, stock_remaining, amount)

            # Handle inventory or immediate use
            purchase_response = await handle_inventory_or_use(
                db, interaction, user_id, item_id, item_name, amount, inventory, custom_message
            )

            # Final response
            await interaction.followup.send(purchase_response)

    @roleplay_group.command(name="sell", description="sell an item from your inventory")
    @app_commands.autocomplete(item_name=shared_functions.rp_inventory_autocomplete)
    async def roleplay_sell(self, interaction: discord.Interaction, item_name: str, amount: int = 1):
        await interaction.response.defer(thinking=True)
        try:
            if amount < 1:
                await interaction.followup.send(
                    "You can't sell less than 1 item, did you mean to buy something instead?")
                return
            user_id = interaction.user.id
            # Get server customized coins name and emoji
            async with roleplay_info_cache.lock:
                if interaction.guild.id not in roleplay_info_cache.cache:
                    await add_guild_to_rp_cache(interaction.guild.id)
                settings = roleplay_info_cache.cache[interaction.guild.id]
                reward_name = settings.reward_name if settings.reward_name else "coins"
                reward_emoji = settings.reward_emoji if settings.reward_emoji else "<:RPCash:884166313260503060>"
            async with aiosqlite.connect(f"pathparser_{interaction.guild.id}.sqlite") as db:
                cursor = await db.execute("SELECT Item_Quantity FROM RP_Players_Items WHERE Player_ID = ?", (user_id,))
                user_item_data = await cursor.fetchone()
                cursor = await db.execute("SELECT balance FROM RP_Players WHERE user_id = ?", (user_id,))
                user_data = await cursor.fetchone()
                if user_data and user_item_data:
                    item_quantity = user_item_data[0]
                    balance = user_data[0]
                    await cursor.execute("SELECT Price, Sellable FROM RP_Store_Items WHERE name = ?", (item_name,))
                    sellable_data = await cursor.fetchone()
                    if sellable_data:
                        (item_value, sellable) = sellable_data
                        sold_value = min(item_quantity, amount) * item_value
                        balance += sold_value
                        await db.execute("UPDATE RP_Players SET balance = ? WHERE user_id = ?", (balance, user_id))
                        await db.commit()
                        if item_quantity - amount > 0:
                            await db.execute(
                                "UPDATE RP_Players_Items SET Item_Quantity = Item_Quantity - ? WHERE player_id = ? and item_name = ?",
                                (amount, user_id, item_name))
                            await db.commit()
                        else:
                            await db.execute("DELETE FROM RP_Players_Items WHERE player_id = ? and item_name = ?",
                                             (user_id, item_name))
                            await db.commit()
                        await interaction.followup.send(
                            f"You have sold {item_name} for {item_value} {reward_name} {reward_emoji} and have a new balance of {balance} {reward_name}.")
                    else:
                        await interaction.followup.send(f"{item_name} could not be found!")
                else:
                    await interaction.followup.send("You don't have a balance yet or item could not be found!")
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"An error occurred while selling an item: {e}")
            await interaction.followup.send("An error occurred while selling an item.")

    @roleplay_group.command(name="use", description="use an item from your inventory")
    @app_commands.autocomplete(item_name=rp_inventory_autocomplete)
    async def roleplay_use(self, interaction: discord.Interaction, item_name: str, amount: int = 1):
        await interaction.response.defer(thinking=True)
        user_id = interaction.user.id
        async with aiosqlite.connect(f"pathparser_{interaction.guild.id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute("SELECT Custom_message, usable from RP_Store_Items WHERE name = ?", (item_name,))
            item_data = await cursor.fetchone()
            if not item_data:
                await interaction.followup.send("This item does not exist in the store! Please reach out to your admin to correct this if this is a mistake.")
                return
            (custom_message, usable) = item_data
            if not usable:
                await interaction.followup.send("This item is not usable.")
                return
            await cursor.execute(
                "SELECT Item_Quantity FROM RP_Players_Items WHERE Player_ID = ? and Item_Name = ?",
                (user_id, item_name))
            item_quantity = await cursor.fetchone()
            if not item_quantity:
                await interaction.followup.send(f"You don't have any {item_name} in your inventory.")
            else:

                response = f"You have used {amount}: {item_name}."

                for x in range(amount):
                    actions = await use_item(interaction=interaction, item_name=item_name)
                    response += "\r\n" + item_data[0] if item_data[0] else ""
                    if actions[0] == -1 or actions[1] == -1 or actions[2] == -1:
                        await interaction.followup.send("An error occurred while using the item.")
                        return
                    if x == 1:
                        response += "\n" + actions[0] if isinstance(actions[0], str) else ""
                        response += "\n" + actions[1] if isinstance(actions[1], str) else ""
                        response += "\n" + actions[2] if isinstance(actions[2], str) else ""
                if item_quantity[0] - amount > 0:
                    await db.execute(
                        "UPDATE RP_Players_Items SET Item_Quantity = Item_Quantity - ? WHERE player_id = ? and item_name = ?",
                        (amount, user_id, item_name))
                    await db.commit()
                else:
                    await db.execute("DELETE FROM RP_Players_Items WHERE player_id = ? and item_name = ?",
                                     (user_id, item_name))
                    await db.commit()
                await interaction.followup.send(response)

    @roleplay_group.command(name="send", description="send RP to another user")
    async def roleplay_send(self, interaction: discord.Interaction, amount: int, recipient: discord.User):
        await interaction.response.defer(thinking=True)
        try:
            sender_id = interaction.user.id
            recipient_id = recipient.id
            async with roleplay_info_cache.lock:
                if interaction.guild.id not in roleplay_info_cache.cache:
                    await add_guild_to_rp_cache(interaction.guild.id)
                settings = roleplay_info_cache.cache[interaction.guild.id]
                reward_name = settings.reward_name if settings.reward_name else "coins"
                reward_emoji = settings.reward_emoji if settings.reward_emoji else "<:RPCash:884166313260503060>"
            async with aiosqlite.connect(f"pathparser_{interaction.guild.id}.sqlite") as db:
                cursor = await db.execute("SELECT balance FROM RP_Players WHERE user_id = ?", (sender_id,))
                sender_data = await cursor.fetchone()
                if sender_data:
                    sender_balance = sender_data[0]
                    if sender_balance >= amount:
                        cursor = await db.execute("SELECT balance FROM RP_Players WHERE user_id = ?", (recipient_id,))
                        recipient_data = await cursor.fetchone()
                        if recipient_data:
                            recipient_balance = recipient_data[0]
                            sender_balance -= amount
                            recipient_balance += amount
                            await db.execute("UPDATE RP_Players SET balance = ? WHERE user_id = ?",
                                             (sender_balance, sender_id))
                            await db.execute("UPDATE RP_Players SET balance = ? WHERE user_id = ?",
                                             (recipient_balance, recipient_id))
                            await db.commit()
                            await interaction.followup.send(
                                f"You have sent {amount} {reward_name} {reward_emoji} to {recipient.mention}.")
                        else:
                            await db.execute("INSERT INTO RP_Players (user_id, balance) VALUES (?, ?)",
                                             (recipient_id, amount))
                            await db.commit()
                            await db.execute("UPDATE RP_Players SET balance = ? WHERE user_id = ?",
                                             (sender_balance - amount, sender_id))
                            await db.commit()
                            await interaction.followup.send(f"You have sent {amount} coins to {recipient.mention}.")
                    else:
                        await interaction.followup.send(f"You don't have enough {reward_name} to send.")
                else:
                    await interaction.followup.send("You don't have a balance yet.")
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"An error occurred while sending {reward_name}: {e}")
            await interaction.followup.send(f"An error occurred while sending {reward_name}.")

    @roleplay_group.command(name="leaderboard", description="View the roleplay leaderboard")
    async def leaderboard(self, interaction: discord.Interaction, page_number: int = 1):
        try:
            await interaction.response.defer(thinking=True)
            user_id = interaction.user.id
            guild_id = interaction.guild.id
            limit = 10
            offset = max((page_number - 1) * limit, 1)
            print(offset)
            leaderboard_view = LeaderboardView(user_id=user_id, guild_id=guild_id, offset=offset, limit=limit,
                                               interaction=interaction)
            await leaderboard_view.update_results()
            await leaderboard_view.create_embed()
            await interaction.followup.send(embed=leaderboard_view.embed, view=leaderboard_view)
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"An error occurred while fetching leaderboard: {e}")
            await interaction.followup.send("An error occurred while fetching leaderboard.")

    @roleplay_group.command(name="inventory", description="View your roleplay inventory")
    async def inventory(self, interaction: discord.Interaction, page_number: int = 1,
                        member: typing.Optional[discord.Member] = None):
        try:
            await interaction.response.defer(thinking=True)
            user_id = interaction.user.id
            guild_id = interaction.guild.id
            limit = 10
            offset = (page_number - 1) * limit
            member = member if member else interaction.user
            inventory_view = InventoryView(user_id=user_id, guild_id=guild_id, offset=offset, limit=limit,
                                           player_id=user_id, interaction=interaction, member=member)
            await inventory_view.update_results()
            await inventory_view.create_embed()
            await interaction.followup.send(embed=inventory_view.embed)
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"An error occurred while fetching inventory: {e}")
            await interaction.followup.send("An error occurred while fetching inventory.")

    @roleplay_group.command(name='store', description='List all items in the store and their behavior')
    async def list_rp_store(self, interaction: discord.Interaction, page_number: int = 1):
        await interaction.response.defer(thinking=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild.id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute("SELECT COUNT(name) FROM rp_store_items")
                item_count = await cursor.fetchone()
                (item_count,) = item_count
                page_number = min(max(page_number, 1), ceil(item_count / 10))
                offset = (page_number - 1) * 10
                view = RPStoreView(user_id=interaction.user.id, guild_id=interaction.guild.id, offset=offset, limit=10,
                                   interaction=interaction)
                await view.update_results()
                await view.create_embed()
                await interaction.followup.send(embed=view.embed, view=view)
        except (aiosqlite.Error, ValueError) as e:
            logging.exception(f"an issue occurred in the list_rp_store_items command: {e}")
            await interaction.followup.send(
                f"An error occurred whilst responding. Please try again later.")

    @roleplay_group.command(name='item', description='Get information about a specific item in the store')
    @app_commands.autocomplete(name=shared_functions.rp_store_autocomplete)
    async def get_item_info(self, interaction: discord.Interaction, name: str):
        await interaction.response.defer(thinking=True)
        try:
            async with roleplay_info_cache.lock:
                if interaction.guild.id not in roleplay_info_cache.cache:
                    await add_guild_to_rp_cache(interaction.guild.id)
                settings = roleplay_info_cache.cache[interaction.guild.id]
                reward_name = settings.reward_name if settings.reward_name else "coins"
                reward_emoji = settings.reward_emoji if settings.reward_emoji else "<:RPCash:884166313260503060>"
            async with aiosqlite.connect(f"pathparser_{interaction.guild.id}.sqlite") as db:
                cursor = await db.cursor()
                print(name)
                statement = """
                    SELECT Item_ID, name, price, description, stock_remaining, inventory, usable, sellable, custom_message,
                    matching_requirements, Requirements_1_type, Requirements_1_pair, Requirements_2_type, Requirements_2_pair, Requirements_3_type, Requirements_3_pair,
                    actions_1_type, actions_1_subtype, actions_1_behavior, actions_2_type, actions_2_subtype, actions_2_behavior, actions_3_type, actions_3_subtype, actions_3_behavior,
                    image_link
                    FROM RP_Store_Items
                    WHERE name = ?
                """
                cursor = await cursor.execute(statement, (name,))
                result = await cursor.fetchone()
                print(result)
                embed = discord.Embed(title=name,
                                      description=f"Information about the item {name}", )
                (
                    item_ID, name, price, description, stock_remaining, inventory, usable, sellable, custom_message,
                    matching_requirements,
                    requirements_1_type, requirements_1_pair,
                    requirements_2_type, requirements_2_pair,
                    requirements_3_type, requirements_3_pair,
                    actions_1_type, actions_1_subtype, actions_1_behavior,
                    actions_2_type, actions_2_subtype, actions_2_behavior,
                    actions_3_type, actions_3_subtype, actions_3_behavior,
                    image_link) = result
                stock_remaining = '∞' if stock_remaining == -1 else stock_remaining
                inventory = "can be stored" if inventory == 1 else "consumed immediately"
                usable = "Yes" if usable == 1 else "No"
                sellable = "Yes" if sellable == 1 else "No"
                embed.set_thumbnail(url=image_link)
                formatted_price = "{:,}".format(price)
                content = f'**Price**: {formatted_price} {reward_name} {reward_emoji}, **Stock Remaining**: {stock_remaining}, \r\n**Inventory**: {inventory}\r\n' \
                          f'**Usable**: {usable}, **Sellable**: {sellable}\r\n'

                embed.add_field(name=f'**Item Name**: {name}: **ID**: {item_ID}',
                                value=content, inline=False)
                embed.add_field(name="Use Message", value=custom_message, inline=False)
                embed.add_field(name="Description", value=description, inline=False)
                requirements_group = (
                    requirements_1_type, requirements_2_type, requirements_3_type, requirements_1_pair,
                    requirements_2_pair,
                    requirements_3_pair)
                actions_group = (
                    actions_1_type, actions_2_type, actions_3_type, actions_1_subtype, actions_2_subtype,
                    actions_3_subtype,
                    actions_1_behavior, actions_2_behavior, actions_3_behavior)
                additional_content = ""
                requirement_dict = {'1': "Role", '2': "Balance", '3': "Item"}
                matching_dict = {'1': "All", '2': "Any", '3': "None"}
                if any(requirements_group):
                    additional_content += f"**Requirements**: {matching_dict.get(matching_requirements, 'Unknown')}\r\n"
                    additional_content += f'**Requirement 1**: {requirement_dict.get(requirements_1_type, "Unknown")}, {requirements_1_pair}\r\n' if requirements_1_type else ""
                    additional_content += f'**Requirement 2**: {requirement_dict.get(requirements_2_type, "Unknown")}, {requirements_2_pair}\r\n' if requirements_2_type else ""
                    additional_content += f'**Requirement 3**: {requirement_dict.get(requirements_3_type, "Unknown")}, {requirements_3_pair}\r\n' if requirements_3_type else ""
                if any(actions_group):
                    actions_1_behavior = f"<@&{actions_1_behavior}>" if actions_1_behavior and actions_1_type == '1' else actions_1_behavior
                    actions_2_behavior = f"<@&{actions_2_behavior}>" if actions_2_behavior and actions_2_type == '1' else actions_2_behavior
                    actions_3_behavior = f"<@&{actions_3_behavior}>" if actions_3_behavior and actions_3_type == '1' else actions_3_behavior
                    behavior_dict = {'1': "Add", '2': "Remove"}
                    additional_content += f'**Action 1**: {requirement_dict.get(actions_1_type, "Unknown")}, {behavior_dict.get(actions_1_subtype, "unknown")}, {actions_1_behavior}\r\n' if actions_1_type else ""
                    additional_content += f'**Action 2**: {requirement_dict.get(actions_2_type, "Unknown")}, {behavior_dict.get(actions_2_subtype, "unknown")}, {actions_2_behavior}\r\n' if actions_2_type else ""
                    additional_content += f'**Action 3**: {requirement_dict.get(actions_3_type, "Unknown")}, {behavior_dict.get(actions_3_subtype, "unknown")}, {actions_3_behavior}\r\n' if actions_3_type else ""
                embed.add_field(name=f'**Additional Info**',
                                value=additional_content, inline=False)
                await interaction.followup.send(embed=embed)
        except (aiosqlite.Error, ValueError) as e:
            logging.exception(f"an issue occurred in the get_item_info command: {e}")
            await interaction.followup.send(
                f"An error occurred whilst responding. Please try again later.")


class LeaderboardView(shared_functions.ShopView):
    def __init__(self, user_id: int, guild_id: int, offset: int, limit: int,
                 interaction: discord.Interaction):
        super().__init__(user_id=user_id, guild_id=guild_id, offset=offset, limit=limit, interaction=interaction,
                         content="")
        self.max_items = None  # Cache total number of items
        self.content = None

    async def update_results(self):
        """Fetch the history of prestige request  for the current page."""

        statement = """
                        SELECT user_name, balance
                        FROM RP_Players
                        ORDER BY Balance Desc  Limit ? Offset ?
                    """
        async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
            cursor = await db.execute(statement, (self.limit, self.offset - 1))
            self.results = await cursor.fetchall()

    async def create_embed(self):
        """Create the embed for the titles."""
        current_page = (self.offset // self.limit) + 1
        total_pages = ((await self.get_max_items() - 1) // self.limit) + 1
        embed_list = []
        x = 1
        async with roleplay_info_cache.lock:
            if self.guild_id not in roleplay_info_cache.cache:
                await add_guild_to_rp_cache(self.guild_id)
            settings = roleplay_info_cache.cache[self.guild_id]
            reward_emoji = settings.reward_emoji if settings.reward_emoji else "<:RPCash:884166313260503060>"

        for item in self.results:
            (user_name, balance) = item
            formatted_balance = "{:,}".format(balance)
            embed_list.append(f'**{self.offset - 1 + x}**. {user_name} • {reward_emoji}{formatted_balance}')
            x += 1
        embed_list = "\n".join(embed_list)
        self.embed = discord.Embed(
            title=f"Leaderboard",
            description=embed_list)
        self.embed.set_footer(text=f"Page {current_page} of {total_pages}")

    async def get_max_items(self):
        """Get the total number of titles."""
        if self.max_items is None:
            async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
                cursor = await db.execute("SELECT COUNT(*) FROM RP_Players")
                count = await cursor.fetchone()
                self.max_items = count[0]
        return self.max_items


class InventoryView(shared_functions.ShopView):
    def __init__(self, user_id: int, guild_id: int, offset: int, limit: int, player_id: int, member: discord.Member,
                 interaction: discord.Interaction):
        super().__init__(user_id=user_id, guild_id=guild_id, offset=offset, limit=limit, interaction=interaction,
                         content="")
        self.max_items = None  # Cache total number of items
        self.content = None
        self.player_id = player_id
        self.member = member
        self.interaction = interaction

    async def update_results(self):
        """Fetch the history of prestige request  for the current page."""

        statement = """
                        SELECT RPI.Item_Name, RPI.Item_Quantity, RPS.Description, RPS.Image_Link
                        FROM RP_Players_Items RPI left join RP_Store_Items RPS on RPI.Item_Name = RPS.Name
                        WHERE RPI.Player_ID = ? ORDER BY item_Name Limit ? Offset ?
                    """
        async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
            cursor = await db.execute(statement, (self.member.id, self.limit, self.offset))
            self.results = await cursor.fetchall()

    async def create_embed(self):
        """Create the embed for the titles."""
        current_page = (self.offset // self.limit) + 1
        total_pages = ((await self.get_max_items() - 1) // self.limit) + 1
        self.embed = discord.Embed(
            title=self.member.name,
            description=f"Use an item with /roleplay use <item_name> <amount>.")
        self.embed.set_author(name=self.member)
        self.embed.set_thumbnail(url=self.member.avatar)
        self.embed.set_footer(text=f"Page {current_page} of {total_pages}")
        for item in self.results:
            (item_name, item_number, item_description, image) = item
            self.embed.add_field(name=f"{item_name}",
                                 value=f"**Quantity**: {item_number} \r\n **Description**: {item_description}",
                                 inline=False)

    async def get_max_items(self):
        """Get the total number of titles."""
        if self.max_items is None:
            async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
                cursor = await db.execute("SELECT COUNT(*) FROM RP_Players_Items WHERE Player_ID = ?",
                                          (self.member.id,))
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
        async with roleplay_info_cache.lock:
            if self.guild_id not in roleplay_info_cache.cache:
                await add_guild_to_rp_cache(self.guild_id)
            settings = roleplay_info_cache.cache[self.guild_id]
            reward_name = settings.reward_name if settings.reward_name else "coins"
            reward_emoji = settings.reward_emoji if settings.reward_emoji else "<:RPCash:884166313260503060>"
        current_page = max(1, (self.offset // self.limit))
        total_pages = ((await self.get_max_items() - 1) // self.limit) + 1
        requirement_dict = {'1': "Role", '2': "Balance", '3': "Item"}
        matching_dict = {'1': "All", '2': "Any", '3': "None"}
        behavior_dict = {'1': "Add", '2': "Remove"}

        self.embed = discord.Embed(
            title=f"items in store",
            description=f"Page {current_page} of {total_pages}")

        for item in self.results:
            (item_id, name, price, description, stock_remaining, inventory, usable, sellable, custom_message,
             matching_requirements, requirements_1_type, requirements_1_pair, requirements_2_type, requirements_2_pair,
             requirements_3_type, requirements_3_pair,
             actions_1_type, actions_1_subtype, actions_1_behavior, actions_2_type, actions_2_subtype,
             actions_2_behavior, actions_3_type, actions_3_subtype, actions_3_behavior,
             image_link) = item
            stock_remaining = '∞' if stock_remaining == -1 else stock_remaining
            inventory = "can be stored" if inventory == "1" else "consumed immediately"
            usable = "Yes" if usable == "1" else "No"
            sellable = "Yes" if sellable == "1" else "No"
            content = f'**Price**: {price} {reward_name} {reward_emoji}, **Stock Remaining**: {stock_remaining}, **Inventory**: {inventory}\r\n' \
                      f'**Usable**: {usable}, **Sellable**: {sellable}\r\n'
            content += f'\r\n{description}'
            print(description)
            self.embed.add_field(name=f'**Item Name**: {name}: **ID**: {item_id}',
                                 value=content, inline=False)
            requirements_group = (
                requirements_1_type, requirements_2_type, requirements_3_type,
                requirements_1_pair, requirements_2_pair, requirements_3_pair)
            actions_group = (
                actions_1_type, actions_2_type, actions_3_type,
                actions_1_subtype, actions_2_subtype, actions_3_subtype,
                actions_1_behavior, actions_2_behavior, actions_3_behavior)
            additional_content = ""
            if custom_message:
                additional_content += f"**Custom Message on use**: {custom_message}\r\n"
            if any(requirements_group):
                additional_content += f"**Requirements**: {matching_dict.get(matching_requirements, 'Unknown')}\r\n"
                additional_content += f'**Requirement 1**: {requirement_dict.get(requirements_1_type, "Unknown")}, {requirements_1_pair}\r\n' if requirements_1_type else ""
                additional_content += f'**Requirement 2**: {requirement_dict.get(requirements_2_type, "Unknown")}, {requirements_2_pair}\r\n' if requirements_2_type else ""
                additional_content += f'**Requirement 3**: {requirement_dict.get(requirements_3_type, "Unknown")}, {requirements_3_pair}\r\n' if requirements_3_type else ""

            if any(actions_group):
                additional_content += f'**Action 1**: {requirement_dict.get(actions_1_type, "Unknown")}, {behavior_dict.get(actions_1_subtype, "Unknown")}, {actions_1_behavior}\r\n' if actions_1_type else ""
                additional_content += f'**Action 2**: {requirement_dict.get(actions_2_type, "Unknown")}, {behavior_dict.get(actions_2_subtype, "Unknown")}, {actions_2_behavior}\r\n' if actions_2_type else ""
                additional_content += f'**Action 3**: {requirement_dict.get(actions_3_type, "Unknown")}, {behavior_dict.get(actions_3_subtype, "Unknown")}, {actions_3_behavior}\r\n' if actions_3_type else ""

            if any([requirements_group, actions_group, custom_message]):
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


logging.basicConfig(
    level=logging.DEBUG,  # Set the minimum logging level
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='application.log',  # Log to a file
    filemode='a'  # Append to the file
)
