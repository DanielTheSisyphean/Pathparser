import asyncio
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Any

import aiosqlite

@dataclass
class ApprovedChannelCache:
    cache: Dict[int, list[Dict[int, float]]] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

@dataclass
class HomeChannelCache:
    cache: Dict[int, dict] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

@dataclass
class AutocompleteCache:
    cache: Dict[Tuple[int, str], List[Tuple[str, str]]] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

@dataclass
class AutocompleteWorldAnvilCache:
    cache: Dict[int, Tuple[List[Tuple[str, dict]], float]] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

approved_channel_cache = ApprovedChannelCache()
build_home_cache = HomeChannelCache()
autocomplete_cache = AutocompleteCache()
autocomplete_worldanvil_cache = AutocompleteWorldAnvilCache()

CACHE_EXPIRATION = 600  # 10 minutes

async def add_guild_to_cache(guild_id: int) -> None:
    try:
        async with approved_channel_cache.lock:
            async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
                print(f"Adding guild {guild_id} to cache.")
                cursor = await db.cursor()
                await cursor.execute("SELECT Channel_ID, coalesce(Multiplier, 1) FROM rp_approved_Channels")
                approved_channels = await cursor.fetchall()
                # approved_channels is a list of tuples, extract the channel IDs
                channel_ids = [{int(channel_id[0]): float(channel_id[1])} for channel_id in approved_channels]
                approved_channel_cache.cache[guild_id] = channel_ids
    except aiosqlite.Error as e:
        logging.exception(f"Failed to add guild {guild_id} to cache with error: {e}")

async def clear_autocomplete_cache():
    while True:
        await asyncio.sleep(300)  # Wait for 5 minutes
        async with autocomplete_cache.lock:
            autocomplete_cache.cache.clear()

async def invalidate_user_cache(user_id: int):
    async with autocomplete_cache.lock:
        keys_to_delete = [key for key in autocomplete_cache.cache if key[0] == user_id]
        for key in keys_to_delete:
            del autocomplete_cache.cache[key]

async def clear_worldanvil_autocomplete_cache():
    while True:
        await asyncio.sleep(300)  # Wait for 5 minutes
        async with autocomplete_cache.lock:
            autocomplete_cache.cache.clear()

async def invalidate_worldanvil_user_cache(user_id: int):
    async with autocomplete_cache.lock:
        keys_to_delete = [key for key in autocomplete_cache.cache if key[0] == user_id]
        for key in keys_to_delete:
            del autocomplete_cache.cache[key]
