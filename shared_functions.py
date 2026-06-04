"""
Refactored shared_functions.py
This file is deprecated. Please import directly from core submodule.
"""

from core.config import ConfigCache, config_cache, timezone_cache
from core.cache import (
    ApprovedChannelCache, HomeChannelCache, AutocompleteCache, AutocompleteWorldAnvilCache,
    approved_channel_cache, autocomplete_cache, autocomplete_worldanvil_cache,
    add_guild_to_cache, clear_autocomplete_cache, invalidate_user_cache,
    clear_worldanvil_autocomplete_cache, invalidate_worldanvil_user_cache, CACHE_EXPIRATION
)
from core.utils import (
    get_gold_breakdown, safe_add, safe_int_complex, name_fix, extract_document_id,
    validate_mythweavers, validate_worldanvil, allocate_food, ordinal, validate_vtt
)
from core.character import CharacterChange, UpdateCharacterData, update_character
from core.autocomplete import (
    stg_character_select_autocompletion, own_character_select_autocompletion,
    character_select_autocompletion, get_plots_autocompletion,
    get_precreated_plots_autocompletion, session_autocompletion,
    group_id_autocompletion, get_plots_autocomplete, player_session_autocomplete,
    fame_autocomplete, title_autocomplete, settings_autocomplete,
    rp_store_autocomplete, rp_inventory_autocomplete, settlement_autocomplete,
    region_autocomplete, search_timezones
)
from core.time_utils import (
    get_next_weekday, parse_time_input, get_utc_offset, time_to_minutes,
    fetch_timecard_data_from_db, create_timecard_plot, convert_to_unix,
    adjust_day, parse_hammer_time_to_iso, parse_hammer_time_to_timestamp,
    validate_hammertime, convert_datetime_to_unix, complex_validate_hammertime
)
from core.memes import meme_handler, last_trigger_time
from core.display import character_embed, log_embed
from core.views import ShopView, RecipientAcknowledgementView, SelfAcknowledgementView, DualView
from core.worldanvil import (
    validate_worldanvil_link, put_wa_article, patch_wa_article,
    put_wa_report, patch_wa_report, drive_word_document
)
