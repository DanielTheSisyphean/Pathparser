import discord
from discord.ext import commands
from discord import app_commands
import typing
from typing import List, Optional, Union
import logging
from zoneinfo import ZoneInfo
import datetime
from datetime import timedelta
import pytz
import aiosqlite

from core.regions import (
    regions, africa_regions, asia_regions, europe_regions, north_america_regions,
    us_regions, us_state_timezones, continent_regions, region_timezones, continent_to_countries,
    timezone_cache
)
from core.time_utils import update_player_timezone, parse_time_input, get_next_weekday, time_to_minutes
from core.autocomplete import search_timezones

class ContinentSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=continent, description=f"Select {continent}")
            for continent in sorted(regions)
        ]
        super().__init__(placeholder="Select your continent...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        try:
            selected_continent = self.values[0]
            self.view.continent = selected_continent
            await self.view.update_region_select(interaction)
        except Exception as e:
            logging.exception(f"Error in ContinentSelect callback: {e}")
            await interaction.response.send_message(
                "An error occurred while selecting the continent.", ephemeral=True
            )
            self.view.stop()


class RegionSelect(discord.ui.Select):
    def __init__(self, continent: str):
        self.continent = continent
        regions_list = continent_regions.get(continent, {})
        if isinstance(regions_list, dict):
            options = [
                discord.SelectOption(label=region, description=f"Select {region}")
                for region in sorted(regions_list.keys())
            ]
        else:
            options = []

        super().__init__(placeholder=f"Select region in {continent}...", min_values=1, max_values=1,
                         options=options)

    async def callback(self, interaction: discord.Interaction):
        try:
            selected_region = self.values[0]
            self.view.region = selected_region
            await self.view.update_country_select(interaction)
        except Exception as e:
            logging.exception(f"Error in RegionSelect callback: {e}")
            await interaction.response.send_message(
                "An error occurred while selecting the region.", ephemeral=True
            )
            self.view.stop()


class USRegionSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=region, description=f"Select {region} states")
            for region in sorted(us_regions.keys())
        ]
        super().__init__(placeholder="Select US Region...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        try:
            selected_us_region = self.values[0]
            self.view.us_region = selected_us_region
            await self.view.update_state_select(interaction)
        except Exception as e:
            logging.exception(f"Error in USRegionSelect callback: {e}")
            await interaction.response.send_message(
                "An error occurred while selecting the US region.", ephemeral=True
            )
            self.view.stop()


class CountrySelect(discord.ui.Select):
    def __init__(self, continent: str, region: str):
        self.continent = continent
        self.region = region
        countries = continent_regions.get(continent, {}).get(region, [])
        unique_countries = sorted(list(set(countries)))

        if len(unique_countries) > 25:
            unique_countries = unique_countries[:25]

        options = [
            discord.SelectOption(label=country, description=f"Select {country}")
            for country in unique_countries
        ]
        super().__init__(placeholder=f"Select country in {region}...", min_values=1, max_values=1,
                         options=options)

    async def callback(self, interaction: discord.Interaction):
        try:
            selected_country = self.values[0]
            self.view.country = selected_country
            if selected_country == "United States":
                await self.view.update_us_region_select(interaction)
            else:
                await self.view.update_timezone_select(interaction)
        except Exception as e:
            logging.exception(f"Error in CountrySelect callback: {e}")
            await interaction.response.send_message(
                "An error occurred while selecting the country.", ephemeral=True
            )
            self.view.stop()


class TimezoneSelect(discord.ui.Select):
    def __init__(self, country: str):
        self.country = country
        timezones = []
        try:
            country_code = None
            for code, name in pytz.country_names.items():
                if name == country:
                    country_code = code
                    break
            
            if country_code:
                timezones = pytz.country_timezones.get(country_code, [])

            if not timezones:
                 # Logic for when pytz doesn't have it or checks regions
                 pass
            
            unique_timezones = sorted(list(set(timezones)))
            if len(unique_timezones) > 25:
                unique_timezones = unique_timezones[:25]
            
            if not unique_timezones:
                options = [discord.SelectOption(label="UTC", description="Coordinated Universal Time")]
            else:
                options = [
                    discord.SelectOption(label=tz, description=tz)
                    for tz in unique_timezones
                ]

        except Exception as e:
            logging.warning(f"Failed to fetch timezones for {country}: {e}")
            options = [discord.SelectOption(label="UTC", description="Defaulting to UTC")]

        super().__init__(placeholder=f"Select timezone for {country}...", min_values=1, max_values=1,
                         options=options)

    async def callback(self, interaction: discord.Interaction):
        try:
            selected_timezone = self.values[0]
            self.view.timezone = selected_timezone
            await update_player_timezone(
                timezone=selected_timezone,
                guild_id=interaction.guild.id,
                player_name=interaction.user.name
            )
            
            if hasattr(self.view, 'day'):
                await self.view.update_day_select(interaction)
            else:
                 if isinstance(self.view, UnavailabilityView):
                     await self.view.update_day_select(interaction)
                 else:
                    embed = discord.Embed(
                        title="Timezone Set",
                        description=f"Your timezone has been set to **{selected_timezone}**.",
                        color=discord.Color.green()
                    )
                    await interaction.response.edit_message(content=None, embed=embed, view=None)
                    self.view.stop()
        except Exception as e:
            logging.exception(f"Error in TimezoneSelect callback: {e}")
            await interaction.response.send_message(
                "An error occurred while selecting the timezone.", ephemeral=True
            )
            self.view.stop()


class DaySelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Monday", value="Monday"),
            discord.SelectOption(label="Tuesday", value="Tuesday"),
            discord.SelectOption(label="Wednesday", value="Wednesday"),
            discord.SelectOption(label="Thursday", value="Thursday"),
            discord.SelectOption(label="Friday", value="Friday"),
            discord.SelectOption(label="Saturday", value="Saturday"),
            discord.SelectOption(label="Sunday", value="Sunday"),
        ]
        super().__init__(placeholder="Select available day...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        try:
            selected_day = self.values[0]
            self.view.day = selected_day
            if hasattr(self.view, 'update_time_style_select'):
                await self.view.update_time_style_select(interaction)
            else:
                # UnavailabilityView
                await self.view.update_time_select(interaction, time_type="start")

        except Exception as e:
            logging.exception(f"Error in DaySelect callback: {e}")
            await interaction.response.send_message(
                "An error occurred while selecting the day.", ephemeral=True
            )
            self.view.stop()


class TimeStyleSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="12-hour (AM/PM)", value="12-hour"),
            discord.SelectOption(label="24-hour", value="24-hour"),
        ]
        super().__init__(placeholder="Select time format...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        try:
            selected_style = self.values[0]
            self.view.time_style = selected_style
            if selected_style == "12-hour":
                await self.view.update_am_pm_select(interaction, time_type="start")
            else:
                await self.view.update_time_select(interaction, time_type="start")
        except Exception as e:
            logging.exception(f"Error in TimeStyleSelect callback: {e}")
            await interaction.response.send_message(
                "An error occurred while selecting the time format.", ephemeral=True
            )
            self.view.stop()


class HourSelect(discord.ui.Select):
    def __init__(self, time_type: str, time_style: str):
        self.time_type = time_type
        self.time_style = time_style

        if time_style == "12-hour":
            hours = [12] + list(range(1, 12))
        else:
            hours = list(range(0, 24))

        options = [
            discord.SelectOption(label=f"{hour:02d}", value=str(hour))
            for hour in hours
        ]
        placeholder = f"Select {time_type} hour..."
        super().__init__(placeholder=placeholder, min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        try:
            selected_hour = int(self.values[0])
            if self.time_type == "start":
                self.view.start_hour = selected_hour
                await self.view.update_minute_select(interaction, time_type="start")
            else:
                self.view.end_hour = selected_hour
                await self.view.update_minute_select(interaction, time_type="end")
        except Exception as e:
            logging.exception(f"Error in HourSelect callback: {e}")
            await interaction.response.send_message(
                "An error occurred while selecting the hour.", ephemeral=True
            )
            self.view.stop()


class AMPMSelect(discord.ui.Select):
    def __init__(self, time_type: str):
        self.time_type = time_type
        options = [
            discord.SelectOption(label="AM", value="AM"),
            discord.SelectOption(label="PM", value="PM"),
        ]
        placeholder = f"Select AM/PM for {time_type} time..."
        super().__init__(placeholder=placeholder, min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        try:
            selected_am_pm = self.values[0]
            if self.time_type == "start":
                self.view.start_am_pm = selected_am_pm
                await self.view.update_time_select(interaction, time_type="start")
            else:
                self.view.end_am_pm = selected_am_pm
                await self.view.update_time_select(interaction, time_type="end")
        except Exception as e:
            logging.exception(f"Error in AMPMSelect callback: {e}")
            await interaction.response.send_message(
                "An error occurred during AM/PM selection.", ephemeral=True
            )
            self.view.stop()


class MinuteSelect(discord.ui.Select):
    def __init__(self, time_type: str):
        self.time_type = time_type
        minutes = [0, 30]
        options = [
            discord.SelectOption(label=f"{minute:02d}", value=str(minute))
            for minute in minutes
        ]
        placeholder = f"Select {time_type} minute..."
        super().__init__(placeholder=placeholder, min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        try:
            selected_minute = int(self.values[0])
            if self.time_type == "start":
                self.view.start_minute = selected_minute
                if self.view.time_style == "12-hour":
                    hour_24 = self.view.convert_to_24_hour(self.view.start_hour, self.view.start_am_pm)
                    self.view.start_hour = hour_24
                
                if hasattr(self.view, 'update_am_pm_select') and self.view.time_style == "12-hour":
                     await self.view.update_am_pm_select(interaction, time_type="end")
                else:
                     await self.view.update_time_select(interaction, time_type="end")
            else:
                self.view.end_minute = selected_minute
                if hasattr(self.view, 'time_style') and self.view.time_style == "12-hour":
                    hour_24 = self.view.convert_to_24_hour(self.view.end_hour, self.view.end_am_pm)
                    self.view.end_hour = hour_24
                    
                await self.view.process_availability(interaction)
        except Exception as e:
            logging.exception(f"Error in MinuteSelect callback: {e}")
            await interaction.response.send_message(
                "An error occurred while selecting the minute.", ephemeral=True
            )
            self.view.stop()


class AddAnotherSlotButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Add Another Time Slot", style=discord.ButtonStyle.primary)

    async def callback(self, interaction: discord.Interaction):
        try:
            await self.view.update_day_select(interaction)
        except Exception as e:
            logging.exception(f"Error in AddAnotherSlotButton callback: {e}")
            await interaction.response.send_message(
                "An error occurred.", ephemeral=True
            )
            self.view.stop()


class StateSelect(discord.ui.Select):
    def __init__(self, region: str):
        self.region = region
        states = us_regions.get(region, [])
        options = [
            discord.SelectOption(label=state, description=f"Select {state}")
            for state in sorted(states)
        ]
        super().__init__(placeholder=f"Select state in {region}...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        try:
            selected_state = self.values[0]
            self.view.state = selected_state
            timezone = us_state_timezones.get(selected_state)
            if timezone:
                self.view.timezone = timezone
                await update_player_timezone(
                    timezone=timezone,
                    guild_id=interaction.guild.id,
                    player_name=interaction.user.name
                )
                await self.view.update_day_select(interaction)
            else:
                await self.view.update_timezone_select(interaction)

        except Exception as e:
            logging.exception(f"Error in StateSelect callback: {e}")
            await interaction.response.send_message(
                "An error occurred while selecting the state.", ephemeral=True
            )
            self.view.stop()


class FinishButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Finish & Save", style=discord.ButtonStyle.success)

    async def callback(self, interaction: discord.Interaction):
        try:
            await self.view.process_all_availability(interaction)
        except Exception as e:
            logging.exception(f"Error in FinishButton callback: {e}")
            await interaction.response.send_message(
                "An error occurred while saving.", ephemeral=True
            )
            self.view.stop()


class BackButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Back", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction):
        await self.view.go_back(interaction)


class CancelButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Cancel", style=discord.ButtonStyle.danger)

    async def callback(self, interaction: discord.Interaction):
        await self.view.cancel(interaction)


class ChangeTimeFormatButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Change Time Format", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction):
        try:
            await self.view.update_time_style_select(interaction)
        except Exception as e:
            logging.exception(f"Error in ChangeTimeFormatButton callback: {e}")
            self.view.stop()


class TimezoneCompleteButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="My Timezone is Correct", style=discord.ButtonStyle.success)

    async def callback(self, interaction: discord.Interaction):
         try:
            await self.view.update_day_select(interaction)
         except Exception as e:
            logging.exception(f"Error in TimezoneCompleteButton callback: {e}")
            self.view.stop()


class AvailabilityView(discord.ui.View):
    def __init__(self, timezone: Optional[str] = None):
        super().__init__(timeout=600)
        self.continent: Optional[str] = None
        self.region: Optional[str] = None
        self.country: Optional[str] = None
        self.us_region: Optional[str] = None
        self.state: Optional[str] = None
        self.timezone: Optional[str] = timezone
        self.day: Optional[str] = None
        self.time_style: Optional[str] = None
        self.start_am_pm: Optional[str] = None
        self.end_am_pm: Optional[str] = None
        self.start_hour: Optional[int] = None
        self.start_minute: Optional[int] = None
        self.end_hour: Optional[int] = None
        self.end_minute: Optional[int] = None
        self.start_time: Optional[str] = None
        self.end_time: Optional[str] = None
        self.time_slots: List[dict] = []
        self.current_step: str = "init"

        if self.timezone:
            self.add_item(TimezoneCompleteButton())
            change_btn = discord.ui.Button(label="Update Timezone", style=discord.ButtonStyle.secondary)
            
            async def change_tz_callback(interaction: discord.Interaction):
                await self.update_continent_select(interaction)
            
            change_btn.callback = change_tz_callback
            self.add_item(change_btn)
        else:
             self.add_item(ContinentSelect())

    async def update_continent_select(self, interaction: discord.Interaction):
        self.clear_items()
        self.add_item(ContinentSelect())
        await interaction.response.edit_message(content="Select your continent:", view=self)

    async def update_region_select(self, interaction: discord.Interaction):
        self.clear_items()
        self.add_item(RegionSelect(self.continent))
        self.add_navigation_buttons()
        await interaction.response.edit_message(content=f"Select region in {self.continent}:", view=self)
        self.current_step = "region_select"

    async def update_country_select(self, interaction: discord.Interaction):
        self.clear_items()
        self.add_item(CountrySelect(self.continent, self.region))
        self.add_navigation_buttons()
        await interaction.response.edit_message(content=f"Select country in {self.region}:", view=self)
        self.current_step = "country_select"

    async def update_us_region_select(self, interaction: discord.Interaction):
        self.clear_items()
        self.add_item(USRegionSelect())
        self.add_navigation_buttons()
        await interaction.response.edit_message(content="Select US Region:", view=self)
        self.current_step = "us_region_select"

    async def update_state_select(self, interaction: discord.Interaction):
        self.clear_items()
        self.add_item(StateSelect(self.us_region))
        self.add_navigation_buttons()
        await interaction.response.edit_message(content=f"Select state in {self.us_region}:", view=self)
        self.current_step = "state_select"

    async def update_timezone_select(self, interaction: discord.Interaction):
        self.clear_items()
        self.add_item(TimezoneSelect(self.country))
        self.add_navigation_buttons()
        await interaction.response.edit_message(content=f"Select timezone for {self.country}:", view=self)
        self.current_step = "timezone_select"

    async def update_day_select(self, interaction: discord.Interaction):
        self.clear_items()
        self.add_item(DaySelect())
        self.add_navigation_buttons()
        await interaction.response.edit_message(content="Select the day you are available:", view=self)
        self.current_step = "day_select"

    async def update_time_style_select(self, interaction: discord.Interaction):
        self.clear_items()
        self.add_item(TimeStyleSelect())
        self.add_navigation_buttons()
        await interaction.response.edit_message(content="Select your preferred time format:", view=self)
        self.current_step = "time_style_select"

    async def update_am_pm_select(self, interaction: discord.Interaction, time_type: str):
        self.clear_items()
        self.add_item(AMPMSelect(time_type=time_type))
        self.add_navigation_buttons()
        await interaction.response.edit_message(content=f"Select AM/PM for {time_type} time:", view=self)
        if time_type == "start":
            self.current_step = "am_pm_select_start"
        else:
             self.current_step = "am_pm_select_end"

    async def update_time_select(self, interaction: discord.Interaction, time_type: str):
        self.clear_items()
        self.add_item(HourSelect(time_type=time_type, time_style=self.time_style))
        self.add_navigation_buttons()
        await interaction.response.edit_message(content=f"Select your {time_type} time (hour):", view=self)
        if time_type == "start":
            self.current_step = "hour_select_start"
        else:
             self.current_step = "hour_select_end"

    async def update_minute_select(self, interaction: discord.Interaction, time_type: str):
        self.clear_items()
        self.add_item(MinuteSelect(time_type=time_type))
        self.add_navigation_buttons()
        await interaction.response.edit_message(content=f"Select your {time_type} time (minutes):", view=self)
        if time_type == "start":
             self.current_step = "minute_select_start"
        else:
             self.current_step = "minute_select_end"

    def add_navigation_buttons(self):
        self.add_item(BackButton())
        self.add_item(CancelButton())
    
    def clear_items(self):
        super().clear_items()

    async def process_availability(self, interaction: discord.Interaction):
        try:
             if not all([self.timezone, self.day]) and \
                self.start_hour is None and self.start_minute is None and \
                self.end_hour is None and self.end_minute is None:
                 await interaction.response.send_message("Incomplete availability information.", ephemeral=True)
                 return
             
             days = {
                'Monday': 1, 'Tuesday': 2, 'Wednesday': 3,
                'Thursday': 4, 'Friday': 5, 'Saturday': 6,
                'Sunday': 7
             }
             day_value = days.get(self.day)
             if not day_value:
                  await interaction.response.send_message(f"Invalid day: {self.day}", ephemeral=True)
                  return

             start_time_str = f"{self.start_hour:02d}:{self.start_minute:02d}"
             end_time_str = f"{self.end_hour:02d}:{self.end_minute:02d}"
             
             start_time_parsed = parse_time_input(start_time_str)
             end_time_parsed = parse_time_input(end_time_str)
             if not start_time_parsed or not end_time_parsed:
                  await interaction.response.send_message("Invalid start or end time format.", ephemeral=True)
                  return

             next_date = get_next_weekday(day_value - 1)
             
             try:
                 tzinfo = ZoneInfo(self.timezone)
             except Exception as e:
                 await interaction.response.send_message("Invalid timezone selected.", ephemeral=True)
                 logging.info(f"Invalid timezone selected. {e}")
                 return

             start_datetime = datetime.datetime.combine(next_date, start_time_parsed, tzinfo=tzinfo)
             end_datetime = datetime.datetime.combine(next_date, end_time_parsed, tzinfo=tzinfo)
             
             utc_offset = start_datetime.utcoffset().total_seconds()
             if end_datetime <= start_datetime and utc_offset < 0:
                 end_datetime += datetime.timedelta(days=1)
             elif end_datetime <= start_datetime and utc_offset > 0:
                 start_datetime -= datetime.timedelta(days=1)
             
             self.time_slots.append({
                'day': self.day,
                'start_time': start_time_str,
                'end_time': end_time_str,
                'timezone': self.timezone
             })
             
             self.day = None
             self.start_hour = None
             self.start_minute = None
             self.end_hour = None
             self.end_minute = None
             self.start_time = None
             self.end_time = None
             
             self.clear_items()
             self.add_item(AddAnotherSlotButton())
             self.add_item(FinishButton())
             await interaction.response.edit_message(
                 content="Time slot added! Would you like to add another time slot or finish?",
                 view=self
             )
        except Exception as e:
            logging.exception(f"Error in process_availability: {e}")
            await interaction.response.send_message("An unexpected error occurred while processing your availability.", ephemeral=True)
            self.stop()

    async def process_all_availability(self, interaction: discord.Interaction):
        try:
            if not self.time_slots:
                await interaction.response.send_message(
                    "No availability entries to save.", ephemeral=True
                )
                return

            async with aiosqlite.connect(f"pathparser_{interaction.guild.id}.sqlite") as db:
                cursor = await db.cursor()
                for slot in self.time_slots:
                    user_name = interaction.user.name
                    day_value = {
                        'Monday': 1, 'Tuesday': 2, 'Wednesday': 3,
                        'Thursday': 4, 'Friday': 5, 'Saturday': 6,
                        'Sunday': 7
                    }.get(slot['day'])

                    start_time_parsed = parse_time_input(slot['start_time'])
                    end_time_parsed = parse_time_input(slot['end_time'])
                    
                    if not start_time_parsed or not end_time_parsed:
                         await interaction.response.send_message(f"Invalid time format for {slot['day']}. Skipping.", ephemeral=True)
                         continue
                         
                    next_date = get_next_weekday(day_value - 1)
                    
                    try:
                        tzinfo = ZoneInfo(slot['timezone'])
                    except Exception as e:
                        await interaction.response.send_message(f"Invalid timezone {slot['timezone']} for {slot['day']}. Skipping.", ephemeral=True)
                        logging.info(f"Error in process_all_availability {e}")
                        continue
                    
                    start_datetime = datetime.datetime.combine(next_date, start_time_parsed, tzinfo=tzinfo)
                    end_datetime = datetime.datetime.combine(next_date, end_time_parsed, tzinfo=tzinfo)
                    
                    if end_datetime <= start_datetime:
                         end_datetime += datetime.timedelta(days=1)
                    
                    start_datetime_utc = start_datetime.astimezone(datetime.timezone.utc)
                    end_datetime_utc = end_datetime.astimezone(datetime.timezone.utc)
                    
                    start_hours = start_datetime_utc.hour
                    start_minutes = start_datetime_utc.minute
                    end_hours = end_datetime_utc.hour
                    end_minutes = end_datetime_utc.minute
                    
                    time_columns = [
                        "00:00", "00:30", "01:00", "01:30", "02:00", "02:30", "03:00", "03:30",
                        "04:00", "04:30", "05:00", "05:30", "06:00", "06:30", "07:00", "07:30",
                        "08:00", "08:30", "09:00", "09:30", "10:00", "10:30", "11:00", "11:30",
                        "12:00", "12:30", "13:00", "13:30", "14:00", "14:30", "15:00", "15:30",
                        "16:00", "16:30", "17:00", "17:30", "18:00", "18:30", "19:00", "19:30",
                        "20:00", "20:30", "21:00", "21:30", "22:00", "22:30", "23:00", "23:30"
                    ]
                    columns_to_nullify = []
                    start_combined = start_hours * 60 + start_minutes
                    end_combined = end_hours * 60 + end_minutes
                    
                    if end_datetime.isoweekday() != start_datetime.isoweekday():
                        end_time = 1440
                        start_time = 0
                        
                        columns_to_nullify = []
                        for col in time_columns:
                            minutes = time_to_minutes(col)
                            if start_combined <= minutes <= end_time:
                                columns_to_nullify.append(f'"{col}" = Null')
                        set_clause = ', '.join(columns_to_nullify)
                        await cursor.execute(f"UPDATE Player_Timecard SET {set_clause} WHERE Player_Name = ? and Day = ?", (user_name, start_datetime.isoweekday()))
                        await db.commit()
                        
                        columns_to_nullify = []
                        for col in time_columns:
                            minutes = time_to_minutes(col)
                            if start_time <= minutes <= end_combined:
                                columns_to_nullify.append(f'"{col}" = Null')
                        set_clause = ', '.join(columns_to_nullify)
                        await cursor.execute(f"UPDATE Player_Timecard SET {set_clause} WHERE Player_Name = ? and Day = ?", (user_name, end_datetime.isoweekday()))
                        await db.commit()
                    else:
                        columns_to_nullify = []
                        for col in time_columns:
                            minutes = time_to_minutes(col)
                            if start_combined <= minutes <= end_combined:
                                columns_to_nullify.append(f'"{col}" = Null')
                        set_clause = ', '.join(columns_to_nullify)
                        await cursor.execute(f"UPDATE Player_Timecard SET {set_clause} WHERE Player_Name = ? and Day = ?", (user_name, start_datetime.isoweekday()))
                        await db.commit()

            embed = discord.Embed(
                title="Availability Updated",
                description=f"Your availability has been successfully updated.",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            self.stop()
        except Exception as e:
            logging.exception(f"Error in process_all_availability {e}")
            await interaction.response.send_message(
                "An unexpected error occurred while finalizing your availability.", ephemeral=True
            )
            self.stop()

    def convert_to_24_hour(self, hour: int, am_pm: str) -> int:
        if am_pm == "AM":
            return hour % 12
        else:
            return (hour % 12) + 12

    async def cancel(self, interaction: discord.Interaction):
        try:
            await interaction.response.send_message("Availability setup has been canceled.", ephemeral=True)
            self.stop()
        except Exception as e:
            logging.exception(f"Error in cancel: {e}")
            self.stop()

    async def go_back(self, interaction: discord.Interaction):
         try:
            if self.current_step == "minute_select_end":
                await self.update_time_select(interaction, time_type="end")
                self.current_step = "hour_select_end"
            elif self.current_step == "hour_select_end":
                await self.update_minute_select(interaction, time_type="start")
                self.current_step = "minute_select_start"
            elif self.current_step == "minute_select_start":
                await self.update_time_select(interaction, time_type="start")
                self.current_step = "hour_select_start"
            elif self.current_step == "hour_select_start":
                if self.time_style == "12-hour":
                    await self.update_am_pm_select(interaction, time_type="start")
                    self.current_step = "am_pm_select_start"
                else:
                     self.clear_items()
                     self.add_item(DaySelect())
                     self.add_navigation_buttons()
                     await interaction.response.edit_message(content="Select the day you are available:", view=self)
                     self.current_step = "day_select"
            elif self.current_step == "am_pm_select_start":
                await self.update_time_select(interaction, time_type="start")
                self.current_step = "hour_select_start"
            elif self.current_step == "day_select":
                if self.time_style:
                     await interaction.response.send_message("You are at the first step and cannot go back further.", ephemeral=True)
                else:
                     self.clear_items()
                     self.add_item(TimeStyleSelect())
                     self.add_navigation_buttons()
                     await interaction.response.edit_message(content="Select your preferred time format:", view=self)
                     self.current_step = "time_style_select"
            elif self.current_step == "time_style_select":
                 await interaction.response.send_message("You are at the first step and cannot go back further.", ephemeral=True)
            else:
                 await interaction.response.send_message("Cannot go back from here.", ephemeral=True)
         except Exception as e:
            logging.exception(f"Error in go_back: {e}")
            await interaction.response.send_message("An error occurred while going back.", ephemeral=True)
            self.stop()

class UnavailabilityView(discord.ui.View):
    def __init__(self, timezone: str):
        super().__init__(timeout=600)
        self.day: Optional[str] = None
        self.timezone = timezone
        self.start_time: Optional[str] = None
        self.end_time: Optional[str] = None
        self.guild_id: Optional[int] = None
        self.user_id: Optional[int] = None
        self.time_slots: List[dict] = []
        self.start_hour: Optional[int] = None
        self.start_minute: Optional[int] = None
        self.end_hour: Optional[int] = None
        self.end_minute: Optional[int] = None
        self.add_item(DaySelect())

    async def update_day_select(self, interaction: discord.Interaction):
        self.clear_items()
        self.add_item(DaySelect())
        await interaction.response.edit_message(content="Select the day of the week:", view=self)

    async def update_time_select(self, interaction: discord.Interaction, time_type: str):
        self.clear_items()
        self.add_item(HourSelect(time_type=time_type, time_style="24-hour"))
        await interaction.response.edit_message(content=f"Select your {time_type} time (hour):", view=self)

    async def update_minute_select(self, interaction: discord.Interaction, time_type: str):
        self.clear_items()
        self.add_item(MinuteSelect(time_type=time_type))
        await interaction.response.edit_message(content=f"Select your {time_type} time (minutes):", view=self)

    async def process_availability(self, interaction: discord.Interaction):
        try:
             # Similar to AvailabilityView but sets up for unavailability
             if not all([self.timezone, self.day]) and \
                self.start_hour is None and self.start_minute is None and \
                self.end_hour is None and self.end_minute is None:
                 await interaction.response.send_message("Incomplete availability information.", ephemeral=True)
                 return
             
             days = {
                'Monday': 1, 'Tuesday': 2, 'Wednesday': 3,
                'Thursday': 4, 'Friday': 5, 'Saturday': 6,
                'Sunday': 7
             }
             day_value = days.get(self.day)
             if not day_value:
                  await interaction.response.send_message(f"Invalid day: {self.day}", ephemeral=True)
                  return

             start_time_str = f"{self.start_hour:02d}:{self.start_minute:02d}"
             end_time_str = f"{self.end_hour:02d}:{self.end_minute:02d}"
             
             start_time_parsed = parse_time_input(start_time_str)
             end_time_parsed = parse_time_input(end_time_str)
             if not start_time_parsed or not end_time_parsed:
                  await interaction.response.send_message("Invalid start or end time format.", ephemeral=True)
                  return

             next_date = get_next_weekday(day_value - 1)
             
             try:
                 tzinfo = ZoneInfo(self.timezone)
             except Exception as e:
                 await interaction.response.send_message("Invalid timezone selected.", ephemeral=True)
                 return

             start_datetime = datetime.datetime.combine(next_date, start_time_parsed, tzinfo=tzinfo)
             end_datetime = datetime.datetime.combine(next_date, end_time_parsed, tzinfo=tzinfo)
             
             utc_offset = start_datetime.utcoffset().total_seconds()
             if end_datetime <= start_datetime and utc_offset < 0:
                 end_datetime += datetime.timedelta(days=1)
             elif end_datetime <= start_datetime and utc_offset > 0:
                 start_datetime -= datetime.timedelta(days=1)
             
             self.time_slots.append({
                'day': self.day,
                'start_time': start_time_str,
                'end_time': end_time_str,
                'timezone': self.timezone
             })
             
             self.day = None
             self.start_hour = None
             self.start_minute = None
             self.end_hour = None
             self.end_minute = None
             self.start_time = None
             self.end_time = None
             
             self.clear_items()
             self.add_item(AddAnotherSlotButton())
             self.add_item(FinishButton())
             await interaction.response.edit_message(
                 content="Time slot added! Would you like to add another time slot or finish?",
                 view=self
             )

        except Exception as e:
             logging.exception(f"Error in UnavailabilityView process: {e}")
             self.stop()

    async def process_all_availability(self, interaction: discord.Interaction):
         try:
            if not self.time_slots:
                await interaction.response.send_message("No availability entries to save.", ephemeral=True)
                return

            async with aiosqlite.connect(f"pathparser_{interaction.guild.id}.sqlite") as db:
                cursor = await db.cursor()
                for slot in self.time_slots:
                    user_name = interaction.user.name
                    day_value = {
                        'Monday': 1, 'Tuesday': 2, 'Wednesday': 3,
                        'Thursday': 4, 'Friday': 5, 'Saturday': 6,
                        'Sunday': 7
                    }.get(slot['day'])

                    start_time_parsed = parse_time_input(slot['start_time'])
                    end_time_parsed = parse_time_input(slot['end_time'])
                    
                    next_date = get_next_weekday(day_value - 1)
                    tzinfo = ZoneInfo(slot['timezone'])
                    
                    start_datetime = datetime.datetime.combine(next_date, start_time_parsed, tzinfo=tzinfo)
                    end_datetime = datetime.datetime.combine(next_date, end_time_parsed, tzinfo=tzinfo)
                    
                    if end_datetime <= start_datetime:
                        end_datetime += datetime.timedelta(days=1)
                    
                    start_datetime_utc = start_datetime.astimezone(datetime.timezone.utc)
                    end_datetime_utc = end_datetime.astimezone(datetime.timezone.utc)
                    
                    start_hours = start_datetime_utc.hour
                    start_minutes = start_datetime_utc.minute
                    end_hours = end_datetime_utc.hour
                    end_minutes = end_datetime_utc.minute
                    
                    time_columns = [
                        "00:00", "00:30", "01:00", "01:30", "02:00", "02:30", "03:00", "03:30",
                        "04:00", "04:30", "05:00", "05:30", "06:00", "06:30", "07:00", "07:30",
                        "08:00", "08:30", "09:00", "09:30", "10:00", "10:30", "11:00", "11:30",
                        "12:00", "12:30", "13:00", "13:30", "14:00", "14:30", "15:00", "15:30",
                        "16:00", "16:30", "17:00", "17:30", "18:00", "18:30", "19:00", "19:30",
                        "20:00", "20:30", "21:00", "21:30", "22:00", "22:30", "23:00", "23:30"
                    ]
                    
                    start_combined = start_hours * 60 + start_minutes
                    end_combined = end_hours * 60 + end_minutes
                    
                    if end_datetime.isoweekday() != start_datetime.isoweekday():
                        end_time = 1440
                        start_time = 0
                        
                        columns_to_nullify = []
                        for col in time_columns:
                            minutes = time_to_minutes(col)
                            if start_combined <= minutes <= end_time:
                                columns_to_nullify.append(f'"{col}" = 1')
                        if columns_to_nullify:
                            set_clause = ', '.join(columns_to_nullify)
                            await cursor.execute(f"UPDATE Player_Timecard SET {set_clause} WHERE Player_Name = ? and Day = ?", (user_name, start_datetime.isoweekday()))
                        
                        columns_to_nullify = []
                        for col in time_columns:
                            minutes = time_to_minutes(col)
                            if start_time <= minutes <= end_combined:
                                columns_to_nullify.append(f'"{col}" = 1')
                        if columns_to_nullify:
                            set_clause = ', '.join(columns_to_nullify)
                            await cursor.execute(f"UPDATE Player_Timecard SET {set_clause} WHERE Player_Name = ? and Day = ?", (user_name, end_datetime.isoweekday()))

                    else:
                        columns_to_nullify = []
                        for col in time_columns:
                            minutes = time_to_minutes(col)
                            if start_combined <= minutes <= end_combined:
                                columns_to_nullify.append(f'"{col}" = 1')
                        if columns_to_nullify:
                            set_clause = ', '.join(columns_to_nullify)
                            await cursor.execute(f"UPDATE Player_Timecard SET {set_clause} WHERE Player_Name = ? and Day = ?", (user_name, start_datetime.isoweekday()))
                    
                    await db.commit()
            
            embed = discord.Embed(title="Availability Updated", description="Your availability has been successfully updated.", color=discord.Color.green())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            self.stop()
         except Exception as e:
            logging.exception(f"Error: {e}")
            await interaction.response.send_message(
                 "An unexpected error occurred while finalizing your availability.", ephemeral=True
            )
            self.stop()
