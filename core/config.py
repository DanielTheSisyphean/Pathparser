import asyncio
import logging
import os
from dataclasses import dataclass, field
from typing import Dict, Any, Union
from zoneinfo import available_timezones

import aiosqlite
import discord
from dotenv import load_dotenv

load_dotenv()

timezone_cache = sorted(available_timezones())

@dataclass
class ConfigCache:
    cache: Dict[int, Dict[str, Any]] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def initialize_configuration(self, discord_bot: discord.Client):
        for guild in discord_bot.guilds:
            await self.load_configurations(guild.id)

    async def load_configurations(self, guild_id: int):
        """Load configurations for all guilds from the database into the cache."""
        try:
            async with self.lock:
                async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
                    cursor = await db.execute("SELECT Identifier, search FROM Admin")
                    rows = await cursor.fetchall()
                    self.cache = {}
                    for key, value in rows:
                        guild_id = int(guild_id)
                        if guild_id not in self.cache:
                            self.cache[guild_id] = {}
                        self.cache[guild_id][key] = self._parse_value(value)
        except aiosqlite.Error as e:
            logging.exception(f"Failed to load configurations for guild {guild_id} with error: {e}")

    def get(self, guild_id: int, key: str, default: Any = None) -> Any:
        """Retrieve a configuration value for a guild from the cache."""
        return self.cache.get(guild_id, {}).get(key, default)

    async def update_setting(self, guild_id: int, key: str, value: Any):
        """Update a configuration setting for a guild in the database and cache."""
        async with self.lock:
            async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
                await db.execute("REPLACE INTO configuration_table (Search, Identifier) VALUES (?, ?)",
                                 (guild_id, key, str(value))
                                 )
                await db.commit()
            # Update the cache
            if guild_id not in self.cache:
                self.cache[guild_id] = {}
            self.cache[guild_id][key] = value

    def _parse_value(self, value: str) -> Any:
        """Parse the value from the database into the appropriate type."""
        # Handle booleans
        try:
            return int(value)
        except ValueError:
            pass
        try:
            return float(value)
        except ValueError:
            pass
        if value.lower() in ('true', 'false'):
            return value.lower() == 'true'
        # Return as string if parsing fails
        return value

    async def refresh_cache_periodically(self, interval_seconds: int, bot: discord.Client):
        while True:
            await asyncio.sleep(interval_seconds)
            await self.initialize_configuration(discord_bot=bot)
            print("Configuration cache refreshed.")


config_cache = ConfigCache()
