import discord
import logging
import typing
import aiosqlite
import datetime
from core.config import config_cache

async def silent_close_thread(
    guild: discord.Guild,
    ticketid: int,
    reason: str = None,
    closer_name_tkt: str = None,
    closer_id_tkt: int = None,
    interaction: discord.Interaction = None
):
    """
    Silently closes a thread and logs it to the archive channel.
    """
    try:
        print("entered close_thread")
        async with aiosqlite.connect(f"pathparser_{guild.id}.sqlite") as conn:
            cursor = await conn.cursor()
            await cursor.execute("SELECT tickettype, threadid, channel_id, player_id, player_name, messageid, claimed_by_id, claimed_by_name, closer_id, closer_name FROM tickets_thread where id = ?", (ticketid,))
            ticket_info = await cursor.fetchone()
            await cursor.execute("UPDATE tickets_thread SET active = ?, closed_time = ? WHERE id = ?", (0, datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S"), ticketid))
            if not ticket_info:
                # If no ticket is found, return a failed message
                return_value = f"There is no ticket with the ID of {ticketid}."
                return return_value
            else:
                print("found ticket")
                # If a ticket is found, extract the relevant information
                (tickettype, threadid, channel_id, player_id, player_name, messageid, claimed_by_id, claimed_by_name, closer_id, closer_name) = ticket_info
                closer_name = closer_name_tkt if closer_name_tkt else closer_name
                closer_id = closer_id_tkt if closer_id_tkt else closer_id
                try: 
                    thread = guild.get_thread(threadid)
                    if not thread:
                        thread = await guild.fetch_thread(threadid)
                except discord.HTTPException as e:
                    logging.error(f"Failed to fetch thread {threadid}: {e}")
            async with config_cache.lock:
                print("grabbing configs")
                configs = config_cache.cache.get(guild.id)
                if configs:
                    archive_channel_id = configs.get('Ticket_Archive')
                    if not archive_channel_id:
                        return_value = f"No channel found with Identifier 'Archive_Channel' in Admin table."
                        return return_value
                    archive_channel = guild.get_channel(archive_channel_id)
                    if not archive_channel:
                        archive_channel = await guild.fetch_channel(archive_channel_id)
        # Create the embed
        embed = discord.Embed(
            title="Ticket Closed",
            description=f"Ticket {tickettype}-{player_name}-{ticketid} has been closed.",
            color=discord.Color.red()
        )
        embed.add_field(name="Ticket Type", value=tickettype, inline=True)
        embed.add_field(name="Player", value=player_name, inline=True)
        embed.add_field(name="Claimed By", value=claimed_by_name, inline=True)
        embed.add_field(name="Closer", value=closer_name, inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name="Link", value=thread.jump_url, inline=False)
        embed.add_field(name="Closed At", value=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), inline=True)
        
        # Send to archive channel
        if archive_channel:
            await archive_channel.send(embed=embed)

        # Archive the thread
        await thread.send(f"this thread is now closed by <@{closer_id}>")
        if interaction:
            await interaction.followup.send("This thread will now be closed and locked.")
        await thread.edit(archived=True, locked=True)
        return
    except Exception as e:
        logging.error(f"Failed to silent close thread {thread.id}: {e}")


async def claim_thread(
    thread: discord.Thread,
    claimer_name: str,
    claimer_id: int,
    guild_id: int,
):
    """
    Silently claims a thread and logs it to the archive channel.
    """
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as conn:
            cursor = await conn.cursor()
            await cursor.execute("UPDATE tickets_thread SET claimed_by_id = ?, claimed_by_name = ? WHERE threadid = ?", (claimer_id, claimer_name, thread.id))
            await conn.commit() 

        # Create the embed
        embed = discord.Embed(
            title="Ticket Claimed",
            description=f"Ticket {thread.name} has been claimed.",
            color=discord.Color.green()
        )
        embed.add_field(name="Ticket Name", value=thread.name, inline=True)
        embed.add_field(name="Claimer", value=claimer_name, inline=True)

        # Send to archive channel
        await thread.send(embed=embed)

    except Exception as e:
        logging.error(f"Failed to silent claim thread {thread.id}: {e}")