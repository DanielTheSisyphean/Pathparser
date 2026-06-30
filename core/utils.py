from decimal import Decimal
from typing import Union, Tuple, Optional
import logging
from unidecode import unidecode
from urllib.parse import urlparse, parse_qs
import re
import discord

def compare_new(new_info: Union[str, int], old_info: Union[str, int]) -> Union[str, int]:
    value = new_info if new_info else old_info
    value = None if new_info == 'None' else value
    return value

def compare_choice(new_info: Union[discord.app_commands.Choice, str, int], old_info: Union[str, int]) -> Union[str, int]:
    new_info = new_info.value if isinstance(new_info, discord.app_commands.Choice) else new_info
    value = compare_new(new_info, old_info)
    return value

def get_gold_breakdown(number: Union[float, Decimal]) -> str:
    """Break down a number into its gold, silver, and copper components."""
    gold_breakdown = ""
    print(number)
    gold_breakdown += f"{'{:,}'.format(int(number))} GP " if number >= 1 else "0 GP "
    gold_breakdown += f"{int((number - int(number)) * 10)} SP " if ((number - int(number)) * 10) >= 1 else ""
    gold_breakdown += \
        f"{int(((number - int(number)) * 10 - int((number - int(number)) * 10)) * 10)} CP " \
            if (((number - int(number)) * 10 - int(
            (number - int(number)) * 10)) * 10) >= 1 else ""
    return gold_breakdown

def safe_add(a, b):
    """Safely add two values together, treating None as zero and converting to Decimal if necessary."""
    a = a if a is not None else 0
    b = b if b is not None else 0
    if isinstance(a, float) or isinstance(b, float):
        a = float(a)
        b = float(b)
    return a + b

def safe_int_complex(a, b, c, d):
    """Safely add two values together, treating None as zero and converting to Decimal if necessary."""
    a = a if a is not None else 0
    b = b if b is not None else 0
    c = c if c is not None else 0
    d = d if d is not None else 0
    if isinstance(a, int) or isinstance(b, int) or isinstance(c, int):
        a = int(a)
        b = int(b)
        c = int(c)
        d = int(d)
    return a + b + c + d

def name_fix(name) -> Optional[Tuple[str, str]]:
    return_value = [None, None]
    try:
        coded_name = str.replace(
            str.replace(
                str.replace(str.replace(str.replace(str.title(name), ";", ""), "(", ""), ")", ""),
                "[", ""), "]", "")
        unidecoded_name = unidecode(coded_name)
        return_value = coded_name, unidecoded_name
    except (TypeError, ValueError) as e:
        logging.exception(f"An error occurred whilst fixing character name '{name}': {e}")
    return return_value

def extract_document_id(url: str) -> Optional[str]:
    try:
        pattern = r'/document/d/([a-zA-Z0-9-_]+)'
        match = re.search(pattern, url)
        if match:
            return match.group(1)
        else:
            return None
    except Exception as e:
        logging.error(f"Failed to extract document ID from URL '{url}': {e}")
        return None

def validate_mythweavers(url: str) -> Tuple[bool, str, int]:
    try:
        parsed_url = urlparse(url)
        if parsed_url.scheme != 'https':
            return False, "URL must start with 'https://'", 0
        if parsed_url.netloc != 'www.myth-weavers.com':
            return False, "URL must be from 'www.myth-weavers.com'", 1
        if parsed_url.path != '/sheets/' and parsed_url.path != '/sheets//' and parsed_url.path != '/idunn/' and parsed_url.path != '/idunn/sheets/':
            return False, "URL path must be '/sheet.html'", 2
        query_params = parse_qs(parsed_url.query)
        fragment_params = parse_qs(parsed_url.fragment)
        id_param = query_params.get('id') or fragment_params.get('id')
        print(query_params, fragment_params, id_param)
        if not id_param:
            return False, "URL must contain a valid 'id' parameter", 3
        return True, "", -1
    except Exception as e:
        logging.error(f"Error validating Myth-Weavers link '{url}': {e}")
        return False, "An error occurred during validation", -1

def validate_worldanvil(url: str) -> Tuple[bool, str, int]:
    try:
        parsed_url = urlparse(url)
        if parsed_url.scheme != 'https':
            return False, "URL must start with 'https://'.", 0
        if parsed_url.netloc not in ('www.worldanvil.com', 'worldanvil.com'):
            return False, "URL must be from 'www.worldanvil.com' or 'worldanvil.com'.", 1
        if not parsed_url.path.startswith('/hero/'):
            return False, "URL path must start with '/hero/'.", 2
        path_parts = parsed_url.path.strip('/').split('/')
        if len(path_parts) < 2 or path_parts[0] != 'hero':
            return False, "URL must contain a valid character ID after '/hero/'.", 3
        return True, "", -1
    except Exception as e:
        logging.error(f"Error validating World Anvil link '{url}': {e}")
        return False, "An error occurred during validation.", -1



def ordinal(n):
    if 11 <= (n % 100) <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"

def validate_vtt(url: str) -> Tuple[bool, str, int]:
    """
    Validates a Virtual Tabletop (VTT) game link URL for platforms like Roll20 and Forge.
    """
    try:
        parsed_url = urlparse(url)
        scheme = parsed_url.scheme.lower()
        domain = parsed_url.hostname.lower() if parsed_url.hostname else ''
        path = parsed_url.path.lower()
        step = 0

        if scheme != 'https':
            return False, "URL must start with 'https://'.", step
        step += 1

        valid_domains = ('roll20.net', 'forge-vtt.com')
        if not any(domain.endswith(valid_domain) for valid_domain in valid_domains):
            return False, "URL must be from Roll20 or Forge.", step
        step += 1

        if domain.endswith('roll20.net'):
            if not path.startswith('/join/'):
                return False, "Roll20 game links should start with '/join/'.", step

        if domain.endswith('forge-vtt.com'):
            if not path.startswith('/invite/') and not path.startswith('/game/'):
                return False, "Forge game links should start with '/invite/' or  '/game/'.", step

        return True, "", -1

    except ValueError as e:
        logging.error(f"Error parsing game link '{url}': {e}")
        return False, "Invalid URL format.", -1


def safe_int(value, default=0):
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def safe_int_atk(value, default=0):
    try:
        try:
            value = int(value)
        except ValueError:
            start_index = value.find('+')
            end_index_slash = value.find('/') if '/' in value else 0
            end_index_space = value.find(' ') if ' ' in value else 0
            end_index = min(end_index_slash, end_index_space) if end_index_slash and end_index_space else max(
                end_index_slash, end_index_space) if end_index_slash or end_index_space else None
            if start_index != -1 and end_index:
                value = int(value[start_index + 1:end_index])
            else:
                value = 0
        return int(value)
    except (ValueError, TypeError):
        return default



def safe_min(a, b):
    """Safely add two values together, treating None as zero and converting to Decimal if necessary."""
    # Treat None as zero
    a = a if a is not None else 0
    b = b if b is not None else 0

    # If either value is a Decimal, convert both to Decimal
    if isinstance(a, int) or isinstance(b, int):
        a = int(a)
        b = int(b)

    return max(min(a, b), 0)


def safe_sub(a, b):
    """Safely add two values together, treating None as zero and converting to Decimal if necessary."""
    # Treat None as zero
    a = a if a is not None else 0
    b = b if b is not None else 0

    # If either value is a Decimal, convert both to Decimal
    if isinstance(a, int) or isinstance(b, int):
        a = int(a)
        b = int(b)

    return a - b


def parse_emoji(emoji_str: str | None) -> tuple[int, str] | None:
    if not emoji_str:
        return None

    emoji_value = emoji_str.strip() if emoji_str else None

    if emoji_value:
        try:
            # Try parsing as custom emoji first
            parsed = discord.PartialEmoji.from_str(emoji_value)
            if not parsed:
                raise ValueError

        except Exception as e:
            # Step 2 — Fallback to Unicode validation
            print(e)
            # Basic Unicode emoji detection (covers 🇦, 1️⃣, 👍🏽, etc.)
            emoji_pattern = re.compile(
                r'^(?:'
                r'[\U0001F1E6-\U0001F1FF]{1,2}'  # Regional indicators (🇦)
                r'|[\u0030-\u0039]\uFE0F?\u20E3'  # Keycaps (1️⃣)
                r'|[\U0001F300-\U0001FAFF]'  # Most emoji symbols
                r'|[\u2600-\u26FF]'  # Misc symbols
                r'|[\u2700-\u27BF]'  # Dingbats
                r')+$'
            )

            if not emoji_pattern.match(emoji_value):
                return (0, "Invalid emoji. Please use a standard emoji or a custom emoji from a server I can access.")

            return 1, emoji_value
        except Exception:
            return 0, "Invalid or unusable emoji. Use a standard emoji or a custom emoji from a server I can access."