import logging
import typing
from datetime import datetime
from typing import Union, Tuple, Any, Coroutine

import aiosqlite
import discord
from discord import Embed

from commands.gamemaster_commands import session_reward_calculation
from core.config import config_cache
from core.kingdom import KingdomInfo, SettlementInfo
from core.kingdom_fetching import fetch_kingdom, fetch_settlement


async def kingdom_embed(
        kingdom: str,
        guild: discord.Guild,
        turn_id: typing.Optional[int] = 0,
        channel: discord.TextChannel = None
        ) -> Union[Tuple[discord.Embed, KingdomInfo], str]:
    try:
        async with aiosqlite.connect(f"pathparser_{guild.id}.sqlite") as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.cursor()
            kingdom_info = await fetch_kingdom(guild_id=guild.id,kingdom=kingdom, turn_id=turn_id)
            if not kingdom_info:
                return f"No Kingdom info for {kingdom}"



            embed = discord.Embed(
                title=kingdom,
                description=F"{kingdom_info.alignment} {kingdom_info.government}",
            )
            if turn_id:
                embed.set_footer(text=f"Turn: {turn_id}")
            if kingdom_info.heraldry:
                embed.set_thumbnail(url=kingdom_info.heraldry)

            embed.add_field(
                name="Primary Stats",
                value=f':anger: **Unrest:**: {kingdom_info.unrest.total}, :heart: **Loyalty**: {kingdom_info.loyalty.total}, :scales: **Stability**: {kingdom_info.stability.total}, :moneybag: **Economy** {kingdom_info.economy.total}',
                inline=False
            )
            embed.add_field(
                name="Resources",
                value=f':hammer: **Build Points**: {kingdom_info.build_points}, :star: **Fame**: {kingdom_info.fame.total} :busts_in_silhouette: **Population**: {kingdom_info.population}, _Hexagon_shape: **Size**: {kingdom_info.size.total} hexes.'
            )
            embed.add_field(
                name="Other",
                value=f':muscle: **Control DC**: {kingdom_info.control_dc.total}, :fork_and_knife: **Consumption**: {kingdom_info.consumption.no_hex_total}, :bread: **Food Production**: {kingdom_info.consumption.hex_value} :coin: **Taxation**: {kingdom_info.taxation.total}',
                inline=False
            )

        # Fetch the bio channel
            if kingdom_info.host_channel:
                kingdom_channel = guild.get_channel(kingdom_info.host_channel)
                if kingdom_channel is None:
                    kingdom_channel = await guild.fetch_channel(kingdom_info.host_channel)
                if kingdom_channel is None:
                    return f"Channel with ID {kingdom_info.host_channel} not found."

            # Fetch and edit the message
                try:
                    host_message = await kingdom_channel.fetch_message(kingdom_info.host_message)
                    await host_message.edit(embed=embed)
                except discord.NotFound:
                    return f"Message with ID {kingdom_info.host_message} not found in channel {kingdom_info.host_channel}."
                except discord.Forbidden:
                    return "Bot lacks permissions to edit the message."
                except discord.HTTPException as e:
                    logging.exception(f"Discord error while editing message: {e}")
                    return "An error occurred while editing the message."
            elif channel:
                kingdom_info.host_channel = channel.id
                host_message = await channel.send(embed=embed)
                kingdom_info.host_message = host_message.id
                kingdom_thread = await host_message.create_thread(name=f"{kingdom_info.kingdom} Log")
                await cursor.execute("Update KB_Kingdoms set Host_Channel = ?, host_message = ?, log_thread = ? where kingdom = ?",(kingdom_info.host_channel,host_message.id, kingdom_thread.id, kingdom_info.kingdom))
                await conn.commit()

            return embed, kingdom_info

    except aiosqlite.Error as e:
        logging.exception(f"Database error: {e}")
        return f"An error occurred with the database."
    except Exception as e:
        logging.exception(f"An unexpected error occurred: {e}")
        return f"An unexpected error occurred while building kingdom embed for '{kingdom_info.kingdom}'."


async def settlement_embed(
        settlement: str,
        guild: discord.Guild,
        turn_id: typing.Optional[int] = 0,
        channel: discord.TextChannel = None
        ) -> str | tuple[list[Embed], SettlementInfo]:
    try:
        async with aiosqlite.connect(f"pathparser_{guild.id}.sqlite") as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.cursor()
            settlement_info = await fetch_settlement(guild_id=guild.id,settlement=settlement, turn_id=turn_id)
            if not settlement_info:
                return f"No Kingdom info for {settlement}"



            embed = discord.Embed(
                title=f"{settlement_info.kingdom}'s settlement of {settlement}",
                description=f"{settlement_info.size.total} lots",
            )
            if turn_id:
                embed.set_footer(text=f"Turn: {turn_id}")
            if settlement_info.image:
                embed.set_thumbnail(url=settlement_info.image)

            embed.add_field(
                name="Primary Stats",
                value=f':see_no_evil: **Corruption:**: {settlement_info.corruption.total}, :supervillain: **Crime**: {settlement_info.crime.total}, :hammer_pick: **Productivity**: {settlement_info.productivity.total},\r\n :scales: **Law** {settlement_info.law.total}, :book: **Lore**: {settlement_info.lore.total}. :speech_balloon: **Society**: {settlement_info.society.total}',
                inline=False
            )
            embed.add_field(
                name="Defences",
                value=f':bell: **Danger**: {settlement_info.danger.total}, :shield:   **Defence**: {settlement_info.defence.total}.'
            )
            embed.add_field(
                name="Market",
                value=f':moneybag: **Gold Cap**: {settlement_info.base_value.total}, :sparkles: **Spellcasting**: {settlement_info.spellcasting.total}',
                inline=False
            )
            embeds = [embed]
            if settlement_info.latitude and settlement_info.longitude:
                await cursor.execute("""select 
                Temp_High, 
                Temp_Low, 
                Wind_Speed, 
                Precipitation_probability, 
                Cloud_cover, 
                humidity, 
                WMO_Code,
                Coalesce(WSet.Result, WAll.result)
                from Weather_History WH
                LEFT JOIN Weather_WMO WSet on WSet.Code = WH.WMO_Code and WH.Settlement = ?
                LEFT JOIN Weather_WMO WAll on WAll.Code = WH.WMO_Code and WH.Settlement = 'All' 
                where WH.Settlement = ? and Date = ?""",
                                     (settlement, settlement, datetime.now().strftime("%Y-%m-%d")))
                weather_info = await cursor.fetchone()
                if weather_info:
                    (temp_high, temp_low, wind_speed, precipitation_probability, cloud_cover, humidity, wmo_code, wmo_result) = weather_info
                    weather_embed = discord.Embed(title="Weather Report", description=f"-# {wmo_result}")
                    weather_conditions = f"""
                    :sun_with_face: High: {temp_high}°f :snowflake: Low: {temp_low}°f
                    :leaves: Wind: {wind_speed} MPH :droplet: {humidity}% humidity 
                    :cloud: Cloud Cover: {cloud_cover}% :cloud_rain: Precipitation Probability: {precipitation_probability}%
                    """
                    weather_embed.add_field(name="Conditions", value=weather_conditions)
                    embeds.append(weather_embed)


            # Fetch the bio channel
            if settlement_info.host_channel:
                print("editing Channel")
                kingdom_channel = guild.get_channel(settlement_info.host_channel)
                if kingdom_channel is None:
                    kingdom_channel = await guild.fetch_channel(settlement_info.host_channel)
                if kingdom_channel is None:
                    return f"Channel with ID {settlement_info.host_channel} not found."

            # Fetch and edit the message
                try:
                    host_message = await kingdom_channel.fetch_message(settlement_info.host_message)
                    await host_message.edit(embeds=embeds)
                except discord.NotFound:
                    return f"Message with ID {settlement_info.host_message} not found in channel {settlement_info.host_channel}."
                except discord.Forbidden:
                    return "Bot lacks permissions to edit the message."
                except discord.HTTPException as e:
                    logging.exception(f"Discord error while editing message: {e}")
                    return "An error occurred while editing the message."
            elif channel:
                settlement_info.host_channel = channel.id
                host_message = await channel.send(embeds=embeds)
                settlement_info.host_message = host_message.id
                await cursor.execute("Update KB_Settlements set Host_Channel = ?, host_message = ? where settlement = ?",(settlement_info.host_channel,host_message.id, settlement_info.settlement))
                await conn.commit()

        return embeds, settlement_info

    except aiosqlite.Error as e:
        logging.exception(f"Database error: {e}")
        return f"An error occurred with the database."
    except Exception as e:
        logging.exception(f"An unexpected error occurred: {e}")
        return f"An unexpected error occurred while building kingdom embed for '{settlement_info.kingdom}'."




async def log_embed(bot, guild: discord.Guild, old_kingdom_info: KingdomInfo,
                    new_kingdom_info: typing.Optional[KingdomInfo] = None,
                    settlement_changes: typing.Optional[
                        dict[str, tuple[SettlementInfo, SettlementInfo]]
                    ] = None,
                    extra_embeds: typing.Optional[discord.Embed] = None
                    ) -> list[Any] | None:
    try:
        embeds = []
        if new_kingdom_info:
            if new_kingdom_info.alignment != old_kingdom_info.alignment:
                description = f"Kingdom has changed alignment from {old_kingdom_info.alignment} to {new_kingdom_info.alignment}"
            else:
                description = f"{new_kingdom_info.alignment}"
            if new_kingdom_info.government != old_kingdom_info.government:
                description += f" Kingdom has changed government from {old_kingdom_info.alignment} to {new_kingdom_info.government}"
            else:
                description += f" {new_kingdom_info.government}"
            if new_kingdom_info.password != old_kingdom_info.password:
                description += "\r\npassword changed"

            if new_kingdom_info.kingdom != old_kingdom_info.kingdom:
                embed_kingdom = discord.Embed(title=f"{old_kingdom_info.kingdom}'s name has been changed to {new_kingdom_info.kingdom}", description=description)
            else:
                embed_kingdom = discord.Embed(title=f"{new_kingdom_info.kingdom}", description=description)

            if (old_kingdom_info.unrest.total != new_kingdom_info.unrest.total
                    or old_kingdom_info.loyalty.total != new_kingdom_info.loyalty.total
                    or old_kingdom_info.stability.total != new_kingdom_info.stability.total
                    or old_kingdom_info.economy.total != new_kingdom_info.economy.total):
                unrest_change = new_kingdom_info.unrest.total - old_kingdom_info.unrest.total
                loyalty_change = new_kingdom_info.loyalty.total - old_kingdom_info.loyalty.total
                stability_change = new_kingdom_info.stability.total - old_kingdom_info.stability.total
                economy_change = new_kingdom_info.economy.total - old_kingdom_info.economy.total


                primary_stat_change_desc = ""
                primary_stat_change_desc += f":anger: Current Unrest: {new_kingdom_info.unrest.total} Change: {unrest_change}\r\n" if unrest_change else ""
                primary_stat_change_desc += f"heart: Current Loyalty: {new_kingdom_info.loyalty.total} Change: {loyalty_change}\r\n" if loyalty_change else ""
                primary_stat_change_desc += f":scales: Current Stability: {new_kingdom_info.stability.total} Change: {stability_change}\r\n" if stability_change else ""
                primary_stat_change_desc += f":moneybag: Current Economy: {new_kingdom_info.economy.total} Change: {economy_change}\r\n" if economy_change else ""
                embed_kingdom.add_field(name=f"Primary Stat Changes",value=primary_stat_change_desc, inline=False)


            if (old_kingdom_info.build_points != new_kingdom_info.build_points
                    or old_kingdom_info.fame.total != new_kingdom_info.fame.total
                    or old_kingdom_info.population != new_kingdom_info.population
                    or old_kingdom_info.size != new_kingdom_info.size):
                build_points_changes = new_kingdom_info.build_points - old_kingdom_info.build_points
                fame_change = new_kingdom_info.fame.total - old_kingdom_info.fame.total
                population_change = new_kingdom_info.population - old_kingdom_info.population
                size_change = new_kingdom_info.size.total - old_kingdom_info.size.total

                resource_stat_changes = ""
                resource_stat_changes += f":hammer: Current Build Points: {new_kingdom_info.build_points}, Change: {build_points_changes}\r\n" if new_kingdom_info.build_points else ""
                resource_stat_changes += f":star: Current Fame: {new_kingdom_info.fame.total}, Change: {fame_change}\r\n" if fame_change else ""
                resource_stat_changes += f":busts_in_silhouette: Current Population: {new_kingdom_info.population}, Change: {population_change}\r\n" if population_change else ""
                resource_stat_changes += f":diamond_shape_with_a_dot_inside: Current Size: {new_kingdom_info.size} hexes, Change: {size_change}\r\n" if size_change else ""
                embed_kingdom.add_field(name=f"Resource Changes",value=resource_stat_changes, inline=False)

            if (old_kingdom_info.control_dc.total != new_kingdom_info.control_dc.total
                    or old_kingdom_info.consumption.no_hex_total != new_kingdom_info.consumption.no_hex_total
                    or old_kingdom_info.consumption.hex_value != new_kingdom_info.consumption.hex_value
                    or old_kingdom_info.taxation.total != new_kingdom_info.taxation.total):
                control_dc_change = (old_kingdom_info.control_dc.total - new_kingdom_info.control_dc.total)
                consumption_change = (old_kingdom_info.consumption.no_hex_total- new_kingdom_info.consumption.no_hex_total)
                food_production_change = (old_kingdom_info.consumption.hex_value- new_kingdom_info.consumption.hex_value)
                taxation_change = (old_kingdom_info.taxation.total- new_kingdom_info.taxation.total)
                kingdom_stat_changes = ""
                kingdom_stat_changes += (
                    f":muscle: Current Control DC: {new_kingdom_info.control_dc.total}, Change: {control_dc_change}\r\n"
                    if control_dc_change else ""
                )
                kingdom_stat_changes += (
                    f":fork_and_knife: Current Consumption: {new_kingdom_info.consumption.no_hex_total}, Change: {consumption_change}\r\n"
                    if consumption_change else ""
                )

                kingdom_stat_changes += (
                    f":bread: Current Food Production: {new_kingdom_info.consumption.hex_value}, Change: {food_production_change}\r\n"
                    if food_production_change else ""
                )

                kingdom_stat_changes += (
                    f":coin: Current Taxation: {new_kingdom_info.taxation.total}, Change: {taxation_change}\r\n"
                    if taxation_change else ""
                )

                embed_kingdom.add_field(
                    name="Other Changes",
                    value=kingdom_stat_changes,
                    inline=False
                )
            if new_kingdom_info.turn:
                embed_kingdom.set_footer(text=new_kingdom_info.turn)

        if settlement_changes:
            settlement_names = list(settlement_changes.keys())

            for idx, settlement_name in enumerate(settlement_names, start=1):
                if idx > 5:
                    remaining_names = settlement_names[idx - 1:]
                    additional_settlement_names = ", ".join(remaining_names)

                    embed = discord.Embed(
                        title=f"{len(remaining_names)} Additional Settlements Affected",
                        description=additional_settlement_names
                    )
                    embeds.append(embed)
                    break

                # Process first 5 settlements here
                old_settlement_info, new_settlement_info = settlement_changes[settlement_name]
                size_change = new_settlement_info.size.total - old_settlement_info.size.total
                description = f"Settlement size: {new_settlement_info.size}"
                description += f" Size Change: {size_change:+}" if size_change else ""

                if old_settlement_info.settlement != new_settlement_info.settlement:
                    embed_settlement = discord.Embed(title=f"{new_settlement_info.kingdom}'s {old_settlement_info.settlement} has been renamed to {old_settlement_info.settlement}", description=description)
                else:
                    embed_settlement = discord.Embed(
                        title=f"{new_settlement_info.kingdom}'s {new_settlement_info.settlement}",
                        description=description)
                if (
                        old_settlement_info.corruption.total != new_settlement_info.corruption.total
                        or old_settlement_info.crime.total != new_settlement_info.crime.total
                        or old_settlement_info.productivity.total != new_settlement_info.productivity.total
                        or old_settlement_info.law.total != new_settlement_info.law.total
                        or old_settlement_info.lore.total != new_settlement_info.lore.total
                        or old_settlement_info.society.total != new_settlement_info.society.total
                ):
                    corruption_change = new_settlement_info.corruption.total - old_settlement_info.corruption.total
                    crime_change = new_settlement_info.crime.total - old_settlement_info.crime.total
                    productivity_change = new_settlement_info.productivity.total - old_settlement_info.productivity.total
                    law_change = new_settlement_info.law.total - old_settlement_info.law.total
                    lore_change = new_settlement_info.lore.total - old_settlement_info.lore.total
                    society_change = new_settlement_info.society.total - old_settlement_info.society.total

                    primary_stat_change_desc = ""
                    primary_stat_change_desc += (
                        f":see_no_evil: Current Corruption: {new_settlement_info.corruption.total} "
                        f"Change: {corruption_change:+}\n"
                        if corruption_change else ""
                    )
                    primary_stat_change_desc += (
                        f":supervillain: Current Crime: {new_settlement_info.crime.total} "
                        f"Change: {crime_change:+}\n"
                        if crime_change else ""
                    )
                    primary_stat_change_desc += (
                        f":hammer_pick: Current Productivity: {new_settlement_info.productivity.total} "
                        f"Change: {productivity_change:+}\n"
                        if productivity_change else ""
                    )
                    primary_stat_change_desc += (
                        f":scales: Current Law: {new_settlement_info.law.total} "
                        f"Change: {law_change:+}\n"
                        if law_change else ""
                    )
                    primary_stat_change_desc += (
                        f":book: Current Lore: {new_settlement_info.lore.total} "
                        f"Change: {lore_change:+}\n"
                        if lore_change else ""
                    )
                    primary_stat_change_desc += (
                        f":speech_balloon: Current Society: {new_settlement_info.society.total} "
                        f"Change: {society_change:+}\n"
                        if society_change else ""
                    )

                    embed_settlement.add_field(
                        name="Primary Stat Changes",
                        value=primary_stat_change_desc,
                        inline=False
                    )

                if (
                        old_settlement_info.danger.total != new_settlement_info.danger.total
                        or old_settlement_info.defence.total != new_settlement_info.defence.total
                ):
                    danger_change = new_settlement_info.danger.total - old_settlement_info.danger.total
                    defence_change = new_settlement_info.defence.total - old_settlement_info.defence.total

                    defence_change_desc = ""
                    defence_change_desc += (
                        f":bell: Current Danger: {new_settlement_info.danger.total} "
                        f"Change: {danger_change:+}\n"
                        if danger_change else ""
                    )
                    defence_change_desc += (
                        f":shield: Current Defence: {new_settlement_info.defence.total} "
                        f"Change: {defence_change:+}\n"
                        if defence_change else ""
                    )

                    embed_settlement.add_field(
                        name="Defence Changes",
                        value=defence_change_desc,
                        inline=False
                    )

                if (
                        old_settlement_info.base_value.total != new_settlement_info.base_value.total
                        or old_settlement_info.spellcasting.total != new_settlement_info.spellcasting.total
                ):
                    base_value_change = (
                            new_settlement_info.base_value.total
                            - old_settlement_info.base_value.total
                    )
                    spellcasting_change = (
                            new_settlement_info.spellcasting.total
                            - old_settlement_info.spellcasting.total
                    )

                    market_change_desc = ""
                    market_change_desc += (
                        f":moneybag: Current Gold Cap: {new_settlement_info.base_value.total} "
                        f"Change: {base_value_change:+}\n"
                        if base_value_change else ""
                    )
                    market_change_desc += (
                        f":sparkles: Current Spellcasting: {new_settlement_info.spellcasting.total} "
                        f"Change: {spellcasting_change:+}\n"
                        if spellcasting_change else ""
                    )

                    embed_settlement.add_field(
                        name="Market Changes",
                        value=market_change_desc,
                        inline=False
                    )
                embeds.append(embed_settlement)


        if embeds:
            embeds.append(extra_embeds)
        # Set Footer

        logging_thread = guild.get_thread(old_kingdom_info.log_thread)
        if logging_thread is None:
            logging_thread = await bot.fetch_channel(old_kingdom_info.log_thread)
            if logging_thread.archived:
                try:
                    # Remove the thread from Archive
                    await logging_thread.edit(archived=False, locked=False)
                except discord.Forbidden:
                    logging.exception(f"Bot lacks permissions to update thread from archived {logging_thread.id}")
        await logging_thread.send(embeds=embeds)
        return embeds
    except (TypeError, ValueError) as e:
        logging.exception(f"An error occurred whilst building logging embed for '{old_kingdom_info.kingdom}': {e}")
