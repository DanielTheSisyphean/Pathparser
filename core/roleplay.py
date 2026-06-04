import logging
import typing
from dataclasses import dataclass, field
from typing import Dict
from math import ceil, floor
import discord
from discord import app_commands
import aiosqlite
import asyncio
import json
import difflib
from datetime import datetime
from unidecode import unidecode

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


async def reinstate_rp_cache(bot) -> None:
    guilds = bot.guilds
    for guild in guilds:
        await add_guild_to_rp_cache(guild.id)


MAX_SIMILARITY_LENGTH = 1000  # Maximum characters to consider in similarity checks
MAX_COMPARISONS = 2  # Number of recent posts to compare against
SIMILARITY_TIMEOUT = 0.05  # Maximum time in seconds for similarity checks

def truncate_text(text):
    """Truncate text to the maximum similarity length."""
    return text[:MAX_SIMILARITY_LENGTH]

def calculate_reward(content_length, time_since_last_post, multiplier, minimum_reward, maximum_reward, channel_multiplier):
    """
    Calculate the reward based on content length and time since last post.
    Rewards increase with longer intervals between posts, up to a maximum cap.
    """
    # Base reward: 1 coin per 10 characters
    base_reward = content_length // 10 * multiplier * channel_multiplier

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
    total_reward = floor(max(minimum_reward, min(total_reward, maximum_reward)))

    return total_reward

async def handle_rp_message(message, channel_multiplier = 1):
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
                content_length, time_since_last_post, reward_multiplier, minimum_reward, maximum_reward, channel_multiplier
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
    except (aiosqlite.Error, TypeError, ValueError, discord.errors.Forbidden) as e:
        logging.exception(f"An error occurred while using item: {e}")
        return -1, -1, -1



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
