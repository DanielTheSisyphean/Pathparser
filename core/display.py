import discord
import logging
from typing import Union, Tuple, Optional
from decimal import Decimal
import aiosqlite
from .config import config_cache
from .utils import get_gold_breakdown, extract_document_id
from .worldanvil import drive_word_document
from .character import CharacterChange


async def character_embed(
        character_name: str,
        guild: discord.Guild) -> Union[Tuple[discord.Embed, str, int], str]:
    try:
        async with aiosqlite.connect(f"pathparser_{guild.id}.sqlite") as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.cursor()
            channel_id = None
            async with config_cache.lock:
                configs = config_cache.cache.get(guild.id)

                if configs:
                    channel_id = configs.get('Accepted_Bio_Channel')

            if not channel_id:
                return f"No channel found with Identifier 'Accepted_Bio_Channel' in Admin table."

            # Fetch character info
            await cursor.execute(
                """
                SELECT player_name, player_id, True_Character_Name, Title, Titles, Description, Oath, Level,
                       Tier, Milestones, Milestones_Required, Trials, Trials_Required, Gold, Gold_Value,
                       Essence, Fame, Prestige, Color, Mythweavers, Image_Link, Tradition_Name,
                       Tradition_Link, Template_Name, Template_Link, Article_Link, Message_ID, Region,
                       heroism, hero_points, hero_points_max
                FROM Player_Characters WHERE Character_Name = ?
                """, (character_name,))
            character_info = await cursor.fetchone()
            if not character_info:
                return f"No character found with Character_Name '{character_name}'."

        # Unpack character_info using column names
        player_name = character_info['player_name']
        player_id = character_info['player_id']
        true_character_name = character_info['True_Character_Name']
        title = character_info['Title']
        titles = character_info['Titles']
        if character_info['Description']:
            description = character_info['Description']
        elif character_info['Oath']:
            description = character_info['Oath']
        else:
            description = " "
        oath = character_info['Oath']
        level = character_info['Level']
        tier = character_info['Tier']
        milestones = character_info['Milestones']
        milestones_required = character_info['Milestones_Required']
        trials = character_info['Trials']
        trials_required = character_info['Trials_Required']
        gold = character_info['Gold']
        gold_value = character_info['Gold_Value']
        essence = character_info['Essence']
        fame = character_info['Fame']
        prestige = character_info['Prestige']
        color = character_info['Color']
        mythweavers = character_info['Mythweavers']
        image_link = character_info['Image_Link']
        tradition_name = character_info['Tradition_Name']
        tradition_link = character_info['Tradition_Link']
        template_name = character_info['Template_Name']
        template_link = character_info['Template_Link']
        article_link = character_info['Article_Link']
        message_id = character_info['Message_ID']
        heroism = character_info['Heroism']
        hero_points = character_info['Hero_points']
        hero_points_max = character_info['Hero_points_max']
        # Convert color to integer
        try:
            int_color = int(color.lstrip('#'), 16)
        except ValueError:
            int_color = 0x000000  # Default color if invalid

        # Build embed description
        description_field = ""
        if titles:
            description_field += f"**Other Names**: {titles}\n"
        if article_link:
            description_field += f"[**Backstory**]({article_link})"
        if character_info['Region']:
            description_field += f"\n**Region**: {character_info['Region']}"

        titled_character_name = true_character_name if not title else f"{title} {true_character_name}"

        embed = discord.Embed(
            title=titled_character_name,
            url=mythweavers,
            description=description_field,
            color=int_color
        )
        embed.set_author(name=player_name)
        embed.set_thumbnail(url=image_link)
        information_value = f'**Level**: {level}, **Mythic Tier**: {tier}\n**Fame**: {fame}, **Prestige**: {prestige}'
        if heroism == 1:
            information_value += f"\n**Hero Points**: {hero_points}\n"
        embed.add_field(
            name="Information",
            value=information_value,
            inline=False
        )
        embed.add_field(
            name="Experience",
            value=f'**Milestones**: {milestones}, **Remaining**: {milestones_required}'
        )
        embed.add_field(
            name="Mythic",
            value=f'**Trials**: {trials}, **Remaining**: {trials_required}'
        )
        gold_string = get_gold_breakdown(gold)
        effective_string = get_gold_breakdown(gold_value)
        embed.add_field(
            name="Current Wealth",
            value=f'**Gold**: {gold_string}, **Effective**: {effective_string}',
            inline=False
        )
        embed.add_field(
            name="Current Essence",
            value=f'**Essence**: {essence}'
        )

        # Additional Info
        linkage = ""
        if tradition_name:
            linkage += f"**Tradition**: [{tradition_name}]({tradition_link})"
        if template_name:
            if tradition_name:
                linkage += " "
            linkage += f"**Template**: [{template_name}]({template_link})"
        if linkage:
            embed.add_field(name='Additional Info', value=linkage, inline=False)

        # Footer with Oath
        oath_icons = {
            'Offerings': 'https://i.imgur.com/dSuLyJd.png',
            'Poverty': 'https://i.imgur.com/4Fr9ZnZ.png',
            'Absolute': 'https://i.imgur.com/ibE5vSY.png'
        }
        icon_url = oath_icons.get(oath)
        print(type(gold))
        embed.set_footer(text=description, icon_url=icon_url)

        message_content = f"<@{player_id}>"

        # Fetch the bio channel
        bio_channel = guild.get_channel(channel_id)
        if bio_channel is None:
            bio_channel = await guild.fetch_channel(channel_id)
        if bio_channel is None:
            return f"Channel with ID {channel_id} not found."

        # Fetch and edit the message
        try:
            bio_message = await bio_channel.fetch_message(message_id)
            await bio_message.edit(content=message_content, embed=embed)
        except discord.NotFound:
            return f"Message with ID {message_id} not found in channel {bio_channel.name}."
        except discord.Forbidden:
            return "Bot lacks permissions to edit the message."
        except discord.HTTPException as e:
            logging.exception(f"Discord error while editing message: {e}")
            return "An error occurred while editing the message."

        return embed, message_content, channel_id

    except aiosqlite.Error as e:
        logging.exception(f"Database error: {e}")
        return f"An error occurred with the database."
    except Exception as e:
        logging.exception(f"An unexpected error occurred: {e}")
        return f"An unexpected error occurred while building character embed for '{character_name}'."




async def log_embed(change: CharacterChange, guild: discord.Guild, thread: int, bot) -> discord.Embed:
    try:
        embed = discord.Embed(
            title=change.character_name,
            description="Character Change",
            color=discord.Color.blurple()
        )
        embed.set_author(name=change.author)
        if change.titles is not None:
            embed.add_field(
                name="titles",
                value=f"new titles: {change.titles}"
            )

        if change.image is not None:
            embed.set_thumbnail(url=change.image)
        if change.mythweavers is not None:
            embed.add_field(
                name="Mythweavers",
                value=f"[Character Sheet]({change.mythweavers})"
            )

        if change.titles is not None:
            embed.add_field(
                name="titles",
                value=f"new titles: {change.titles}"
            )

        if change.oath is not None:
            embed.add_field(
                name="Oath",
                value=change.oath
            )

        if change.backstory is not None:
            embed.add_field(
                name="Backstory",
                value=change.backstory
            )

        if change.description is not None:
            embed.add_field(
                name="Description",
                value=change.description
            )
        # Milestone Change
        if change.milestone_change is not None:
            embed.add_field(
                name="Milestone Change",
                value=(
                    f"**Level**: {change.level}\n"
                    f"**Milestone Change**: {change.milestone_change}\n"
                    f"**Total Milestones**: {change.milestones_total}\n"
                    f"**Milestones Remaining**: {change.milestones_remaining}"
                )
            )

        # Trial Change
        if change.trial_change is not None:
            embed.add_field(
                name="Trial Change",
                value=(
                    f"**Mythic Tier**: {change.tier}\n"
                    f"**Trial Change**: {change.trial_change}\n"
                    f"**Total Trials**: {change.trials}\n"
                    f"**Trials Remaining**: {change.trials_remaining}"
                )
            )

        # Wealth Changes
        if change.gold_change is not None:
            gold = round(change.gold, 2) if change.gold is not None else "N/A"
            gold_change = round(change.gold_change, 2) if change.gold_change else "N/A"
            gold_value = round(change.gold_value, 2) if change.gold_value else "N/A"
            gold_string = get_gold_breakdown(gold)
            if change.gold_value:
                gold_value_string = get_gold_breakdown(gold_value)
            else:
                gold_value_string = "N/A"
            if change.gold_change:
                gold_change_string = get_gold_breakdown(gold_change)
            else:
                gold_change_string = "N/A"
            embed.add_field(
                name="Wealth Changes",
                value=(
                    f"**Gold**: {gold_string}\n"
                    f"**Gold Change**: {gold_change_string}\n"
                    f"**Effective Gold**: {gold_value_string}\n"
                    f"**Transaction ID**: {change.transaction_id}"
                )
            )

        # Essence Change
        if change.essence_change is not None:
            embed.add_field(
                name="Essence Change",
                value=(
                    f"**Essence**: {change.essence}\n"
                    f"**Essence Change**: {change.essence_change}"
                )
            )

        # Tradition Change
        if change.tradition_name and change.tradition_link:
            embed.add_field(
                name="Tradition Change",
                value=f"**Tradition**: [{change.tradition_name}]({change.tradition_link})"
            )

        # Template Change
        if change.template_name and change.template_link:
            embed.add_field(
                name="Template Change",
                value=f"**Template**: [{change.template_name}]({change.template_link})"
            )

        # Alternate Reward
        if change.alternate_reward is not None:
            embed.add_field(
                name="Other Rewards",
                value=change.alternate_reward
            )

        # Fame and Prestige
        if change.fame_change is not None or change.prestige_change is not None:
            fame = change.fame if change.fame else "Not Changed"
            prestige = change.prestige if change.prestige else "Not Changed"
            fame_change = change.fame_change if change.fame_change else "Not Changed"
            prestige_change = change.prestige_change if change.prestige_change else "Not Changed"

            embed.add_field(
                name="Fame and Prestige",
                value=(
                    f"**Total Fame**: {fame}\n"
                    f"**Received Fame**: {fame_change}\n"
                    f"**Total Prestige**: {prestige}\n"
                    f"**Received Prestige**: {prestige_change}"
                )
            )
        if change.region is not None:
            embed.add_field(
                name="Region",
                value=change.region
            )

        if change.hero_point_change is not None:
            embed.add_field(
                name=f"Hero Point Change",value=change.hero_point_change
            )

        # Set Footer
        if change.source is not None:
            embed.set_footer(text=change.source)
        logging_thread = guild.get_thread(thread)
        if logging_thread is None:
            logging_thread = await bot.fetch_channel(thread)
            if logging_thread.archived:
                try:
                    # Remove the thread from Archive
                    await logging_thread.edit(archived=False, locked=False)
                except discord.Forbidden:
                    logging.exception(f"Bot lacks permissions to update thread from archived {logging_thread.id}")
        await logging_thread.send(embed=embed)
        return embed
    except (TypeError, ValueError) as e:
        logging.exception(f"An error occurred whilst building character embed for '{change.character_name}': {e}")


def create_progress_bar(current, total, bar_length=20):
    """Create a progress bar for a given current and total value."""
    if total == 0:
        return f"[{'-' * bar_length}] {current}/{total}"
    progress = int(bar_length * (current / total))
    return f"[{'█' * progress}{'-' * (bar_length - progress)}] {current}/{total}"


async def stg_character_embed(
        character_name: str, guild: discord.Guild
    ) -> Union[Tuple[discord.Embed, str], str]:
    try:
        async with aiosqlite.connect(f"pathparser_{guild.id}.sqlite") as conn:
            cursor = await conn.cursor()
            await cursor.execute(
                "SELECT player_name, player_id, True_Character_Name, Titles, Description, Oath, Level, "
                "Tier, Milestones, Milestones_Required, Trials, Trials_Required, Color, Mythweavers, "
                "Image_Link, Backstory"
                " FROM A_STG_Player_Characters WHERE Character_Name = ?", (character_name,))
            character_info = await cursor.fetchone()
            (player_name, player_id, character_name, titles, description, oath, level, tier, milestones,
             milestones_required,
             trials, trials_required, color, mythweavers, image_link, backstory) = character_info
            int_color = int(color[1:], 16)
            description_field = f" "
            if titles is not None:
                description_field += f"**Other Names**: {titles} \r\n"  # Titles
            if description is not None:  # Description
                description_field += f"**Description**: {description}"
            titled_character_name = character_name
            embed = discord.Embed(title=f"{titled_character_name}", url=f'{mythweavers}',
                                  description=f"{description_field}",  # Character Name, Mythweavers, Description
                                  color=int_color)
            embed.set_author(name=f'{player_name}')  # Player Name
            embed.set_thumbnail(url=f'{image_link}')  # Image Link
            embed.add_field(name="Information",
                            value=f'**Level**: {level}, '
                                  f'**Mythic Tier**: {tier}, ',
                            # Level, Tier, Fame, Prestige
                            inline=False)
            embed.add_field(name="Experience",
                            value=f'**Milestones**: {milestones}, '
                                  f'**Remaining**: {milestones_required}')  # Milestones, Remaining Milestones
            embed.add_field(name="Mythic",
                            value=f'**Trials**: {trials}, '
                                  f'**Remaining**: {trials_required}')  # Trials, Remaining Trials
            message = f"<@{player_id}>"
            check_backstory = drive_word_document(backstory)
            if backstory:
                if backstory.startswith("http"):
                    document_id = extract_document_id(backstory)
                    if document_id is None:
                        if oath == 'Offerings':
                            embed.set_footer(text=f'{oath}, Could not parse Document Link!',
                                             icon_url=f'https://i.imgur.com/dSuLyJd.png')
                        elif oath == 'Poverty':
                            embed.set_footer(text=f'{oath}, Could not parse Document Link!',
                                             icon_url=f'https://i.imgur.com/4Fr9ZnZ.png')
                        elif oath == 'Absolute':
                            embed.set_footer(text=f'{oath}, Could not parse Document Link!',
                                             icon_url=f'https://i.imgur.com/ibE5vSY.png')
                        else:
                            embed.set_footer(text=f'Could not parse Document Link!')
                    else:
                        embed.add_field(name="Backstory", value=f"{backstory}", inline=False)
                        if oath == 'Offerings':
                            embed.set_footer(text=f'{oath}', icon_url=f'https://i.imgur.com/dSuLyJd.png')
                        elif oath == 'Poverty':
                            embed.set_footer(text=f'{oath}', icon_url=f'https://i.imgur.com/4Fr9ZnZ.png')
                        elif oath == 'Absolute':
                            embed.set_footer(text=f'{oath} Poverty', icon_url=f'https://i.imgur.com/ibE5vSY.png')
                else:
                    if oath == 'Offerings':
                        embed.set_footer(text=f'{backstory}', icon_url=f'https://i.imgur.com/dSuLyJd.png')
                    elif oath == 'Poverty':
                        embed.set_footer(text=f'{backstory}', icon_url=f'https://i.imgur.com/4Fr9ZnZ.png')
                    elif oath == 'Absolute':
                        embed.set_footer(text=f'{backstory} Poverty', icon_url=f'https://i.imgur.com/ibE5vSY.png')
                    else:
                        embed.set_footer(text=f'{backstory}')
            else:
                if oath == 'Offerings':
                    embed.set_footer(text=f'{oath}', icon_url=f'https://i.imgur.com/dSuLyJd.png')
                elif oath == 'Poverty':
                    embed.set_footer(text=f'{oath}', icon_url=f'https://i.imgur.com/4Fr9ZnZ.png')
                elif oath == 'Absolute':
                    embed.set_footer(text=f'{oath}', icon_url=f'https://i.imgur.com/ibE5vSY.png')

            return_message = embed, message

    except (aiosqlite.Error, TypeError, ValueError) as e:
        logging.exception(f"An error occurred whilst building character embed for '{character_name}': {e}")
        return_message = f"An error occurred whilst building character embed for '{character_name}'."
    return return_message
