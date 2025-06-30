import math
import random
import typing
import discord
import numpy as np
import pycountry
import pycountry_convert
import requests
from discord.ext import commands
from discord import app_commands
from typing import List, Optional
import aiosqlite
import pytz
import datetime
from zoneinfo import ZoneInfo, available_timezones
import logging
from dateutil import parser
import os
from matplotlib import pyplot as plt
from pywaclient.api import BoromirApiClient as WaClient
import shared_functions
from commands import gamemaster_commands

# CALL ME MR MONEYBAGS BECAUSE HERE IS MY CASH
timezone_cache = sorted(available_timezones())

# Initialize logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s:%(name)s: %(message)s',
    handlers=[
        logging.FileHandler("pathparser.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Define regions
regions = {
    'Africa', 'America', 'Antarctica', 'Asia', 'Atlantic',
    'Australia', 'Europe', 'Indian', 'Pacific', 'Etc'
}

africa_regions = {
    'Northern Africa': ['Algeria', 'Egypt', 'Libya', 'Morocco', 'Sudan', 'Tunisia', 'Western Sahara'],
    'Western Africa': ['Benin', 'Burkina Faso', 'Cabo Verde', 'Côte d\'Ivoire', 'Gambia', 'Ghana', 'Guinea',
                       'Guinea-Bissau', 'Liberia', 'Mali', 'Mauritania', 'Niger', 'Nigeria', 'Senegal', 'Sierra Leone',
                       'Togo'],
    'Central Africa': ['Angola', 'Cameroon', 'Central African Republic', 'Chad', 'Congo',
                       'Democratic Republic of the Congo',
                       'Equatorial Guinea', 'Gabon', 'São Tomé and Príncipe'],
    'Eastern Africa': ['Burundi', 'Comoros', 'Djibouti', 'Eritrea', 'Ethiopia', 'Kenya', 'Madagascar', 'Malawi',
                       'Mauritius', 'Mozambique', 'Rwanda', 'Seychelles', 'Somalia', 'South Sudan', 'Tanzania',
                       'Uganda', 'Zambia', 'Zimbabwe'],
    'Southern Africa': ['Botswana', 'Eswatini', 'Lesotho', 'Namibia', 'South Africa'],
}

asia_regions = {
    'Western Asia': ['Armenia', 'Azerbaijan', 'Bahrain', 'Cyprus', 'Georgia', 'Iraq', 'Israel', 'Jordan', 'Kuwait',
                     'Lebanon', 'Oman', 'Qatar', 'Saudi Arabia', 'State of Palestine', 'Syria', 'Turkey',
                     'United Arab Emirates', 'Yemen'],
    'Central Asia': ['Kazakhstan', 'Kyrgyzstan', 'Tajikistan', 'Turkmenistan', 'Uzbekistan'],
    'South Asia': ['Afghanistan', 'Bangladesh', 'Bhutan', 'India', 'Iran', 'Maldives', 'Nepal', 'Pakistan',
                   'Sri Lanka'],
    'East Asia': ['China', 'Japan', 'Mongolia', 'North Korea', 'South Korea', 'Taiwan'],
    'Southeast Asia': ['Brunei', 'Cambodia', 'Indonesia', 'Laos', 'Malaysia', 'Myanmar', 'Philippines', 'Singapore',
                       'Thailand', 'Timor-Leste', 'Vietnam'],
}

europe_regions = {
    'Northern Europe': ['Denmark', 'Estonia', 'Finland', 'Iceland', 'Ireland', 'Latvia', 'Lithuania', 'Norway',
                        'Sweden', 'United Kingdom'],
    'Western Europe': ['Austria', 'Belgium', 'France', 'Germany', 'Liechtenstein', 'Luxembourg', 'Monaco',
                       'Netherlands', 'Switzerland'],
    'Eastern Europe': ['Belarus', 'Bulgaria', 'Czech Republic', 'Hungary', 'Moldova', 'Poland', 'Romania',
                       'Russia', 'Slovakia', 'Ukraine'],
    'Southern Europe': ['Albania', 'Andorra', 'Bosnia and Herzegovina', 'Croatia', 'Greece', 'Italy', 'Kosovo',
                        'North Macedonia', 'Malta', 'Montenegro', 'Portugal', 'San Marino', 'Serbia', 'Slovenia',
                        'Spain', 'Vatican City'],
}

north_america_regions = {
    'Northern America': ['Bermuda', 'Canada', 'Greenland', 'Mexico', 'United States'],
    'Central America': ['Belize', 'Costa Rica', 'El Salvador', 'Guatemala', 'Honduras', 'Nicaragua', 'Panama'],
    'Caribbean': ['Antigua and Barbuda', 'Bahamas', 'Barbados', 'Cuba', 'Dominica', 'Dominican Republic',
                  'Grenada', 'Haiti', 'Jamaica', 'Saint Kitts and Nevis', 'Saint Lucia',
                  'Saint Vincent and the Grenadines',
                  'Trinidad and Tobago', 'Puerto Rico']
}

us_regions = {
    'Northeast': ['Connecticut', 'Maine', 'Massachusetts', 'New Hampshire', 'Rhode Island', 'Vermont',
                  'New Jersey', 'New York', 'Pennsylvania'],
    'Midwest': ['Indiana', 'Illinois', 'Michigan', 'Ohio', 'Wisconsin',
                'Iowa', 'Kansas', 'Minnesota', 'Missouri', 'Nebraska', 'North Dakota', 'South Dakota'],
    'South': ['Delaware', 'Florida', 'Georgia', 'Maryland', 'North Carolina', 'South Carolina', 'Virginia',
              'District of Columbia', 'West Virginia', 'Alabama', 'Kentucky', 'Mississippi', 'Tennessee',
              'Arkansas', 'Louisiana', 'Oklahoma', 'Texas'],
    'West': ['Arizona', 'Colorado', 'Idaho', 'Montana', 'Nevada', 'New Mexico', 'Utah', 'Wyoming',
             'Alaska', 'California', 'Hawaii', 'Oregon', 'Washington'],
}
# Mapping of US states to their time zones
us_state_timezones = {
    'Alabama': ['Central Time'],
    'Alaska': ['Alaska Time'],
    'Arizona': ['Mountain Time'],
    'Arkansas': ['Central Time'],
    'California': ['Pacific Time'],
    'Colorado': ['Mountain Time'],
    'Connecticut': ['Eastern Time'],
    'Delaware': ['Eastern Time'],
    'Florida': ['Eastern Time', 'Central Time'],
    'Georgia': ['Eastern Time'],
    'Hawaii': ['Hawaii Time'],
    'Idaho': ['Mountain Time', 'Pacific Time'],
    'Illinois': ['Central Time'],
    'Indiana': ['Eastern Time', 'Central Time'],
    'Iowa': ['Central Time'],
    'Kansas': ['Central Time', 'Mountain Time'],
    'Kentucky': ['Eastern Time', 'Central Time'],
    'Louisiana': ['Central Time'],
    'Maine': ['Eastern Time'],
    'Maryland': ['Eastern Time'],
    'Massachusetts': ['Eastern Time'],
    'Michigan': ['Eastern Time', 'Central Time'],
    'Minnesota': ['Central Time'],
    'Mississippi': ['Central Time'],
    'Missouri': ['Central Time'],
    'Montana': ['Mountain Time'],
    'Nebraska': ['Central Time', 'Mountain Time'],
    'Nevada': ['Pacific Time', 'Mountain Time'],
    'New Hampshire': ['Eastern Time'],
    'New Jersey': ['Eastern Time'],
    'New Mexico': ['Mountain Time'],
    'New York': ['Eastern Time'],
    'North Carolina': ['Eastern Time'],
    'North Dakota': ['Central Time', 'Mountain Time'],
    'Ohio': ['US/Eastern'],
    'Oklahoma': ['Central Time'],
    'Oregon': ['Pacific Time', 'Mountain Time'],
    'Pennsylvania': ['Eastern Time'],
    'Rhode Island': ['Eastern Time'],
    'South Carolina': ['Eastern Time'],
    'South Dakota': ['Central Time', 'Mountain Time'],
    'Tennessee': ['Central Time', 'Eastern Time'],
    'Texas': ['Central Time', 'Mountain Time'],
    'Utah': ['Mountain Time'],
    'Vermont': ['US/Eastern'],
    'Virginia': ['Eastern Time'],
    'Washington': ['Pacific Time'],
    'West Virginia': ['Eastern Time'],
    'Wisconsin': ['Central Time'],
    'Wyoming': ['Mountain Time'],
    'District of Columbia': ['Eastern Time'],
}

# Update the continent_regions mapping
continent_regions = {
    'Africa': africa_regions,
    'Asia': asia_regions,
    'Europe': europe_regions,
    'North America': north_america_regions,  # Add this line
    # Other continents can be added here if needed
}

# Create a mapping of regions to their respective timezones
region_timezones = {region: [tz for tz in timezone_cache if tz.startswith(f"{region}/")] for region in regions}


async def search_timezones(interaction: discord.Interaction, current: str) -> typing.List[app_commands.Choice[str]]:
    # Get all available timezones
    global timezone_cache
    # Check if timezone cache is initialized
    # Filter timezones based on current input
    filtered_timezones = [tz for tz in timezone_cache if current.lower() in tz.lower()]

    # Return list of app_commands.Choice objects (maximum 25 choices for Discord autocomplete)
    return [
        app_commands.Choice(name=tz, value=tz)
        for tz in filtered_timezones[:25]  # Limit to 25 results to comply with Discord's limit
    ]


def time_to_minutes(t):
    if t[:1] == '-':
        hours, minutes = map(int, t[1:].split(':'))
        hours = -abs(hours)
        minutes = -abs(minutes)
    elif t[:1] == '+':
        hours, minutes = map(int, t[1:].split(':'))
    elif len(t) == 5:
        hours, minutes = map(int, t.split(':'))
    else:
        hours = 0
        minutes = 0
    return hours * 60 + minutes


async def fetch_timecard_data_from_db(guild_id, player_name, day, utc_offset):
    time_labels = [
        "00:00", "00:30", "01:00", "01:30", "02:00", "02:30", "03:00", "03:30",
        "04:00", "04:30", "05:00", "05:30", "06:00", "06:30", "07:00", "07:30",
        "08:00", "08:30", "09:00", "09:30", "10:00", "10:30", "11:00", "11:30",
        "12:00", "12:30", "13:00", "13:30", "14:00", "14:30", "15:00", "15:30",
        "16:00", "16:30", "17:00", "17:30", "18:00", "18:30", "19:00", "19:30",
        "20:00", "20:30", "21:00", "21:30", "22:00", "22:30", "23:00", "23:30"
    ]
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()
            # Fetch the player's timezone from the database
            if utc_offset == 0:
                # Fetch the player's timecard data for the specified day, they're in UTC so the UTEasy.
                joined_labels = ', '.join([f'"{label}"' for label in time_labels])
                await cursor.execute(f"SELECT {joined_labels} FROM Player_Timecard WHERE Player_Name = ? AND Day = ?",
                                     (player_name, day))
                row = await cursor.fetchone()
            else:
                # get next instance of day occurring
                start_time = datetime.datetime.now(tz=pytz.utc)
                days_ahead = day - start_time.weekday() if day - start_time.weekday() >= 0 else 7 + day - start_time.weekday()
                start_time = start_time + datetime.timedelta(days=days_ahead)

                # get the start and end of the day
                day_start_start_time = datetime.datetime.combine(start_time.date(), datetime.time.min)
                day_end_start_time = datetime.datetime.combine(start_time.date(), datetime.time.max)

                # adjust the hour and minute of the day start and end to the player's timezone
                day_start_timezone = day_start_start_time.astimezone(pytz.timezone(utc_offset))
                day_end_timezone = day_end_start_time.astimezone(pytz.timezone(utc_offset))
                day_start_timezone = day_start_timezone - datetime.timedelta(
                    minutes=day_start_timezone.utcoffset().total_seconds() / 60)
                day_end_timezone = day_end_timezone - datetime.timedelta(
                    minutes=day_end_timezone.utcoffset().total_seconds() / 60)

                # Because the timecard is stored in UTC, we need to extract the UTC Times based off of the Player's Timezones
                end_time = 1440
                start_time = 0
                day_start_minutes = day_start_timezone.hour * 60 + day_start_timezone.minute
                day_end_minutes = day_end_timezone.hour * 60 + day_end_timezone.minute

                # Select the columns based on the player's timezone
                select_statement = []
                for col in time_labels:
                    col_minutes = time_to_minutes(col)
                    if day_start_minutes <= col_minutes <= end_time:
                        select_statement.append(f'pt1."{col}"')
                for col in time_labels:
                    col_minutes = time_to_minutes(col)
                    if start_time <= col_minutes <= day_end_minutes:
                        select_statement.append(f'pt2."{col}"')
                joined_labels = ', '.join(select_statement)

                # Fetch the player's timecard data for the specified day using a left join statement to combine hte results.
                await cursor.execute(
                    f"SELECT {joined_labels} FROM Player_Timecard PT1 LEFT JOIN Player_Timecard PT2 on PT1.Player_Name = PT2.Player_Name  WHERE PT1.Player_Name = ? AND PT1.Day = ? and Pt2.Day = ?",
                    (player_name, day_start_timezone.weekday(), day_end_timezone.weekday()))
                row = await cursor.fetchone()

            # If the player's data is found, return the row
            return row
    except aiosqlite.Error as e:
        logging.error(f"Error fetching timecard data for {player_name}: {e}")


async def fetch_group_availability_from_db(guild_id, group_id, day, utc_offset):
    time_labels = [
        "00:00", "00:30", "01:00", "01:30", "02:00", "02:30", "03:00", "03:30",
        "04:00", "04:30", "05:00", "05:30", "06:00", "06:30", "07:00", "07:30",
        "08:00", "08:30", "09:00", "09:30", "10:00", "10:30", "11:00", "11:30",
        "12:00", "12:30", "13:00", "13:30", "14:00", "14:30", "15:00", "15:30",
        "16:00", "16:30", "17:00", "17:30", "18:00", "18:30", "19:00", "19:30",
        "20:00", "20:30", "21:00", "21:30", "22:00", "22:30", "23:00", "23:30"
    ]
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute("SELECT Player_Name from Sessions_Group_Presign where Group_id = ?", (group_id,))
            players = await cursor.fetchall()

            player_list = [group_id]
            player_list.extend(player[0] for player in players)

            # Build the list of placeholders for the player names
            select_list = ', '.join('?' for _ in players)  # Ensure the number of '?' matches player_list length
            joined_labels = ['?']
            utc_offset_time = get_utc_offset(utc_offset)
            # Fetch the player's timezone from the database
            if utc_offset_time == 0:
                # Fetch the player's timecard data for the specified day, they're in UTC so the UTEasy.
                joined_labels.extend([f'"SUM({label})"' for label in time_labels])
                joined_labels = ', '.join(joined_labels)
                sql_statement = f"SELECT {joined_labels} FROM Player_Timecard WHERE Player_Name in ({select_list}) AND Day = ?"

                await cursor.execute(sql_statement,
                                     (player_list, day))
                row = await cursor.fetchone()
            else:
                # get next instance of day occurring
                start_time = datetime.datetime.now(tz=pytz.utc)
                days_ahead = day - start_time.weekday() if day - start_time.weekday() >= 0 else 7 + day - start_time.weekday()
                start_time = start_time + datetime.timedelta(days=days_ahead)

                # get the start and end of the day
                day_start_start_time = datetime.datetime.combine(start_time.date(), datetime.time.min)
                day_end_start_time = datetime.datetime.combine(start_time.date(), datetime.time.max)

                # adjust the hour and minute of the day start and end to the player's timezone
                day_start_timezone = day_start_start_time.astimezone(pytz.timezone(utc_offset))
                day_end_timezone = day_end_start_time.astimezone(pytz.timezone(utc_offset))
                day_start_timezone = day_start_timezone - datetime.timedelta(
                    minutes=day_start_timezone.utcoffset().total_seconds() / 60)
                day_end_timezone = day_end_timezone - datetime.timedelta(
                    minutes=day_end_timezone.utcoffset().total_seconds() / 60)

                # Because the timecard is stored in UTC, we need to extract the UTC Times based off of the Player's Timezones
                end_time = 1440
                start_time = 0
                day_start_minutes = day_start_timezone.hour * 60 + day_start_timezone.minute
                day_end_minutes = day_end_timezone.hour * 60 + day_end_timezone.minute

                # Select the columns based on the player's timezone
                select_statement = []
                select_statement.extend('?')
                for col in time_labels:
                    col_minutes = time_to_minutes(col)
                    if day_start_minutes <= col_minutes <= end_time:
                        select_statement.append(f'sum(pt1."{col}")')
                for col in time_labels:
                    col_minutes = time_to_minutes(col)
                    if start_time <= col_minutes <= day_end_minutes:
                        select_statement.append(f'sum(pt2."{col}")')
                joined_labels = ', '.join(select_statement)

                # Append the additional parameters (ensure order matches the placeholders in the SQL statement)
                additional_params = [day_start_timezone.weekday(), day_end_timezone.weekday()]
                params = player_list + additional_params  # Combine player_list with additional params

                # Fetch the player's timecard data for the specified day using a left join statement to combine hte results.
                sql_statement = f"""
                    SELECT {joined_labels} 
                    FROM Player_Timecard PT1 
                    LEFT JOIN Player_Timecard PT2 
                    ON PT1.Player_Name = PT2.Player_Name  
                    WHERE PT1.Player_Name IN ({select_list}) 
                    AND PT1.Day = ? AND PT2.Day = ?
                """

                await cursor.execute(
                    sql_statement, params)
                row = await cursor.fetchone()

            # If the player's data is found, return the row
            return row
    except aiosqlite.Error as e:
        logging.error(f"Error fetching timecard data for {group_id}: {e}")


# Function to plot and save the graph as an image
async def create_timecard_plot(guild_id, player_name, day, utc_offset):
    # Time intervals (x-axis)
    time_labels = [
        "00:00", "00:30", "01:00", "01:30", "02:00", "02:30", "03:00", "03:30",
        "04:00", "04:30", "05:00", "05:30", "06:00", "06:30", "07:00", "07:30",
        "08:00", "08:30", "09:00", "09:30", "10:00", "10:30", "11:00", "11:30",
        "12:00", "12:30", "13:00", "13:30", "14:00", "14:30", "15:00", "15:30",
        "16:00", "16:30", "17:00", "17:30", "18:00", "18:30", "19:00", "19:30",
        "20:00", "20:30", "21:00", "21:30", "22:00", "22:30", "23:00", "23:30"
    ]
    daysdict = {1: 'Monday', 2: 'Tuesday', 3: 'Wednesday', 4: 'Thursday', 5: 'Friday', 6: 'Saturday', 7: 'Sunday'}

    if isinstance(player_name, str):
        row = await fetch_timecard_data_from_db(guild_id, player_name, day, utc_offset)

        if row:
            player_availability = row
        else:
            player_availability = [0] * len(time_labels)  # Default to 0 if no data found
        player_availability = [int(x) if str(x).isdigit() else 0 for x in player_availability]
        # Reshape the 1D array to a 2D array with 1 row and 48 columns
        player_availability = np.array(player_availability).reshape(1, -1)

        # Use the updated colormap call to avoid deprecation warning
        cmap = plt.colormaps.get_cmap('RdYlGn')

        # Create a plot with larger size to fit everything
        plt.figure(figsize=(14, 3))  # Widen the figure

        # Plot the data
        plt.imshow(player_availability, cmap=cmap, aspect='auto')

        midpoints = np.arange(len(time_labels)) - 0.5  # Shift ticks by -0.5 to place grid between labels
        # Rotate the x-axis labels and align them properly
        plt.xticks(np.arange(len(time_labels)), time_labels, rotation=90, ha="center",
                   fontsize=8)  # Adjust rotation and font size

        plt.yticks(np.arange(1), [player_name])

        plt.gca().set_xticks(midpoints, minor=True)  # Set the grid to the midpoints between ticks
        plt.gca().grid(which='minor', color='white', linestyle='-', linewidth=2)  # Minor grid between ticks

        plt.tick_params(axis='x', which='both', length=4, pad=5)
        # Labeling the graph
        cbar = plt.colorbar()
        cbar.set_label('Red = Unavailable, Green = Available', fontsize=10)

        # Add a title with an increased font size
        plt.title(f"{player_name} availability on {daysdict[day]}", fontsize=14)

        # Adjust the layout to fit the x-axis labels and title
        plt.subplots_adjust(bottom=0.3,
                            top=0.85)  # Adjust bottom and top margins to give room for the x-labels and title

        plt.tight_layout()
    elif isinstance(player_name, tuple):  # Correct
        player_list = []  # Initialize an empty list to store player names
        player_availability = []  # Initialize an empty list to store all players' availability data
        group_name = None
        for player in player_name:
            row = fetch_timecard_data_from_db(guild_id, player[2], day, utc_offset)
            group_name = player[0]
            if row:
                player_list.append(player[2])  # Append the player name to the list
                availability = [int(x) if str(x).isdigit() else 0 for x in row]  # Process row data
                player_availability.append(availability)  # Add the player's availability to the list
        # Convert the list of lists into a 2D numpy array for plotting
        player_availability = np.array(player_availability)
        group_availability = np.sum(player_availability, axis=0)  # Summing along the player axis

        # Use the updated colormap call to avoid deprecation warning
        cmap = plt.colormaps.get_cmap('RdYlGn')

        # Create a plot with larger size to fit everything
        min_height = max(3, len(player_name) * 0.5)  # Minimum height of 3 inches
        fig, ax1 = plt.subplots(figsize=(14, min_height))  # ax1 will be used for the player availability heatmap

        # Plot the player availability heatmap
        heatmap1 = ax1.imshow(player_availability, cmap=cmap, aspect='auto')

        # Rotate the x-axis labels and align them properly
        midpoints = np.arange(len(time_labels)) - 0.5  # Shift ticks by -0.5 to place grid between labels
        ax1.set_xticks(np.arange(len(time_labels)))
        ax1.set_xticklabels(time_labels, rotation=90, ha="center", fontsize=8)

        # Set y-axis ticks to show player names
        player_list = [p[2] for p in player_name]  # Extract player names from player_name tuple
        ax1.set_yticks(np.arange(len(player_list)))
        ax1.set_yticklabels(player_list)

        # Add a grid between x-axis labels
        ax1.set_xticks(midpoints, minor=True)
        ax1.grid(which='minor', color='white', linestyle='-', linewidth=2)

        # Add color bar for player availability heatmap
        cbar1 = plt.colorbar(heatmap1, ax=ax1, pad=0.02)
        cbar1.set_label('Red = Unavailable, Green = Available', fontsize=10)

        # Create a second axis (ax2) to plot the group availability heatmap
        ax2 = ax1.twinx()  # Create a twin axis sharing the same x-axis
        ax2.set_yticks([])  # Hide y-axis ticks for ax2, since it's just an overlay

        # Plot the group availability as a secondary plot on ax2
        # You can use a different colormap to distinguish between individual and group heatmaps
        ax2.plot(group_availability, color='blue', linewidth=2, label='Group Availability')

        # Add a legend for group availability
        ax2.legend(loc='upper right')

        # Add a title with an increased font size
        ax1.set_title(f"{group_name} Availability for {daysdict[day]}", fontsize=14)

        # Adjust the layout to fit the x-axis labels and title
        plt.subplots_adjust(bottom=0.3, top=0.85)

        plt.tight_layout(rect=[0, 0, 0.95, 1])  # Adjust the right margin to fit the color bar

    # Save the plot as an image file
    plt.savefig('C:\\pathparser\\plots\\timecard_plot.png')  # Ensure the path is correct for your system
    plt.close()


async def create_timecard_group_plot(guild_id: int, user_id: int, group_name: str, group_info: list, day: int,
                                     utc_offset: str):
    # Time intervals (x-axis)
    time_labels = [f"{hour:02d}:{minute:02d}" for hour in range(24) for minute in (0, 30)]

    daysdict = {1: 'Monday', 2: 'Tuesday', 3: 'Wednesday', 4: 'Thursday', 5: 'Friday', 6: 'Saturday', 7: 'Sunday'}
    player_list = []
    player_availability = []

    # Fetch availability data for each player
    for player in group_info:
        # Assuming 'player' is a string containing the player's name
        row = await fetch_timecard_data_from_db(guild_id, player, day, utc_offset)

        if row:
            player_list.append(player)  # Append the player name to the list
            availability = [int(x) if str(x).isdigit() else 0 for x in row]
            player_availability.append(availability)
        else:
            # Handle case where no data is available for the player
            logging.info(f"No availability data found for {player}.")

    if not player_availability:
        logging.info("No availability data found for any player.")
        return

    # Convert to numpy array
    player_availability = np.array(player_availability)
    group_availability = np.sum(player_availability, axis=0)

    # Set up the plot
    cmap = plt.get_cmap('RdYlGn')
    min_height = max(3, len(player_list) * 0.5)
    fig, ax1 = plt.subplots(figsize=(14, min_height))

    # Plot the player availability heatmap
    heatmap1 = ax1.imshow(player_availability, cmap=cmap, aspect='auto')

    # Configure x-axis
    ax1.set_xticks(np.arange(len(time_labels)))
    ax1.set_xticklabels(time_labels, rotation=90, ha="center", fontsize=8)
    midpoints = np.arange(len(time_labels) + 1) - 0.5
    ax1.set_xticks(midpoints, minor=True)
    ax1.grid(which='minor', color='white', linestyle='-', linewidth=2)

    # Configure y-axis
    ax1.set_yticks(np.arange(len(player_list)))
    ax1.set_yticklabels(player_list)

    # Add color bar
    cbar1 = plt.colorbar(heatmap1, ax=ax1, pad=0.02)
    cbar1.set_label('Red = Unavailable, Green = Available', fontsize=10)

    # Plot group availability
    ax2 = ax1.twinx()
    ax2.set_yticks([])
    ax2.plot(group_availability, color='blue', linewidth=2, label='Group Availability')
    ax2.legend(loc='upper right')

    # Add title
    day_name = daysdict.get(day, "Unknown Day")
    ax1.set_title(f"{group_name} Availability for {day_name}", fontsize=14)

    # Adjust layout
    plt.subplots_adjust(bottom=0.3, top=0.85)
    plt.tight_layout(rect=[0, 0, 0.95, 1])

    # Save the plot
    plot_dir = os.path.join('C:', 'pathparser', 'plots')
    os.makedirs(plot_dir, exist_ok=True)
    plot_path = os.path.join(plot_dir, f'timecard_{user_id}_plot.png')
    plt.savefig(plot_path)
    plt.close()


# Utility functions
def get_next_weekday(weekday: int) -> datetime.date:
    """Return the date of the next specified weekday (0=Monday, 6=Sunday)."""
    today = datetime.datetime.now().date()
    days_ahead = weekday - today.weekday()
    if days_ahead <= 0:
        days_ahead += 7
    return today + datetime.timedelta(days=days_ahead)


def get_utc_offset(tz):
    try:
        tzinfo = ZoneInfo(tz)
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        now_tz = now_utc.astimezone(tzinfo)

        # Get the offset in hours and minutes
        offset_seconds = now_tz.utcoffset().total_seconds()

        # Format the offset as "+HH:MM" or "-HH:MM"
        return offset_seconds
    except Exception as e:
        logging.info(f"Error getting UTC offset for timezone {tz}: {e}")
        return "+00:00"  # Return UTC if the timezone is invalid or there's an error


def parse_time_input(time_str: str) -> Optional[datetime.time]:
    """Parse time input in various formats and return a time object."""
    try:
        dt = parser.parse(time_str, fuzzy=True)
        return dt.time()
    except (parser.ParserError, ValueError):
        return None


# Build mapping from continents to country codes and names
# Build mapping from continents to country codes and names
continent_to_countries = {}

for country in pycountry.countries:
    country_code = country.alpha_2
    country_name = country.name
    try:
        continent_code = pycountry_convert.country_alpha2_to_continent_code(country_code)
        continent_name = pycountry_convert.convert_continent_code_to_continent_name(continent_code)
    except KeyError:
        continue  # Skip countries where mapping is not available

    # Map 'Americas' to 'North America' or 'South America' based on country
    if continent_name == 'Americas':
        # Use country codes to differentiate North and South America
        if country_name in north_america_regions['Northern America'] + \
                north_america_regions['Central America'] + \
                north_america_regions['Caribbean']:
            continent_name = 'North America'
        else:
            continent_name = 'South America'
    # Initialize continent list if not already
    if continent_name not in continent_to_countries:
        continent_to_countries[continent_name] = []

    continent_to_countries[continent_name].append({'code': country_code, 'name': country_name})


# Custom Select Menus

class ContinentSelect(discord.ui.Select):
    def __init__(self):
        # Use the exact continent names from your mappings
        options = [discord.SelectOption(label=continent) for continent in continent_to_countries.keys()]
        options.append(discord.SelectOption(label='Cancel', value='cancel'))
        super().__init__(
            placeholder="Select your continent...",
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        try:
            self.view.continent = self.values[0]

            if self.view.continent == 'cancel':
                self.view.clear_items()
                self.view.stop()
                await interaction.response.send_message("Selection cancelled.", ephemeral=True)
            elif self.view.continent in continent_regions:
                await self.view.update_region_select(interaction)
            else:
                await self.view.update_country_select(interaction)
        except Exception as e:
            logging.exception(f"Error in ContinentSelect callback: {e}")
            await interaction.response.send_message(
                "An error occurred while selecting your continent.", ephemeral=True
            )
            self.view.stop()


class RegionSelect(discord.ui.Select):
    def __init__(self, continent: str, regions: typing.Dict[str, List[str]]):
        self.continent = continent
        self.regions = regions
        options = [discord.SelectOption(label=region) for region in regions.keys()]
        options.append(discord.SelectOption(label='Return', value='return'))
        options.append(discord.SelectOption(label='Cancel', value='cancel'))
        super().__init__(
            placeholder="Select your region...",
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        try:
            self.view.region = self.values[0]
            logging.info(f"Region selected: {self.view.region}")
            if self.view.region == 'return':
                self.view.continent = None
                self.view.clear_items()
                self.view.add_item(ContinentSelect())
                await interaction.response.edit_message(content="Select your continent:", view=self.view)
            elif self.view.region == 'cancel':
                self.view.clear_items()
                self.view.stop()

                await interaction.response.send_message("Selection cancelled.", ephemeral=True)
            else:
                await self.view.update_country_select(interaction)
        except Exception as e:
            logging.exception(f"Error in RegionSelect callback:{e}")
            await interaction.response.send_message(
                "An error occurred while selecting your region.", ephemeral=True
            )
            self.view.stop()


class USRegionSelect(discord.ui.Select):
    def __init__(self, regions: typing.Dict[str, List[str]]):
        self.regions = regions
        options = [discord.SelectOption(label=region) for region in regions.keys()]
        options.append(discord.SelectOption(label='Cancel', value='cancel'))
        options.append(discord.SelectOption(label='Return', value='return'))
        super().__init__(
            placeholder="Select your US region...",
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        try:
            self.view.us_region = self.values[0]
            if self.view.us_region == 'cancel':
                self.view.clear_items()
                self.view.stop()
                await interaction.response.send_message("Selection cancelled.", ephemeral=True)
            elif self.view.us_region == 'return':
                self.view.state = None
                await self.view.update_country_select(interaction)
            else:
                await self.view.update_state_select(interaction)
        except Exception as e:
            logging.exception(f"Error in USRegionSelect callback: {e}")
            await interaction.response.send_message(
                "An error occurred while selecting your US region.", ephemeral=True
            )
            self.view.stop()


class CountrySelect(discord.ui.Select):
    def __init__(self, options: List[discord.SelectOption]):
        super().__init__(
            placeholder="Select your country...",
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        try:
            selected_country_name = self.values[0]
            if selected_country_name == 'other':
                await interaction.response.send_message(
                    "Please enter your country manually using the `/timesheet` command with your country.",
                    ephemeral=True
                )
                self.view.stop()
                return
            elif selected_country_name == 'cancel':
                self.view.clear_items()
                self.view.stop()
                await interaction.response.send_message("Selection cancelled.", ephemeral=True)
                return
            elif selected_country_name == 'return':
                self.view.region = None
                await self.view.update_region_select(interaction)
                return
            # Map country name back to country code
            country = pycountry.countries.get(name=selected_country_name)
            if not country:
                # Try searching by common name
                country = pycountry.countries.search_fuzzy(selected_country_name)[0]
            self.view.country_code = country.alpha_2
            if self.view.country_code == 'US':
                await self.view.update_region_select_us(interaction)
            else:
                await self.view.update_timezone_select(interaction)
        except Exception as e:
            logging.exception(f"Error in CountrySelect callback: {e}")
            await interaction.response.send_message(
                "An error occurred while selecting your country.", ephemeral=True
            )
            self.view.stop()


class TimezoneSelect(discord.ui.Select):
    def __init__(self, options: List[discord.SelectOption], prompt_day_update: bool = False):
        super().__init__(
            placeholder="Select your time zone...",
            options=options
        )
        self.prompt_day_update = prompt_day_update

    async def callback(self, interaction: discord.Interaction):
        try:
            selected_timezone = self.values[0]
            if selected_timezone == "other":
                # Prompt user to enter their timezone manually
                await interaction.response.send_message(
                    "Please enter your timezone manually using the `/timesheet` command with your timezone.",
                    ephemeral=True
                )
                self.view.stop()
                return
            elif selected_timezone == 'cancel':
                self.view.clear_items()
                self.view.stop()
                await interaction.response.send_message("Selection cancelled.", ephemeral=True)
                return
            elif selected_timezone == 'return':
                self.view.country_code = None
                await self.view.update_country_select(interaction)
                return
            await update_player_timezone(timezone=selected_timezone, guild_id=interaction.guild.id,
                                         player_name=interaction.user.name)
            self.view.timezone = selected_timezone
            if not self.prompt_day_update:
                await self.view.update_day_select(interaction)
            else:
                await self.view.optional_day_select(interaction)

        except Exception as e:
            logging.exception(f"Error in TimezoneSelect callback: {e}")
            await interaction.response.send_message(
                "An error occurred while selecting your time zone.", ephemeral=True
            )
            self.view.stop()


class DaySelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label='Monday', value='Monday'),
            discord.SelectOption(label='Tuesday', value='Tuesday'),
            discord.SelectOption(label='Wednesday', value='Wednesday'),
            discord.SelectOption(label='Thursday', value='Thursday'),
            discord.SelectOption(label='Friday', value='Friday'),
            discord.SelectOption(label='Saturday', value='Saturday'),
            discord.SelectOption(label='Sunday', value='Sunday'),
        ]
        super().__init__(
            placeholder='Select a day...',
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        try:
            self.view.day = self.values[0]
            # Check if time_style is already set
            if not self.view.time_style:
                # Present the TimeStyleSelect
                self.view.clear_items()
                self.view.add_item(TimeStyleSelect())
                self.view.add_navigation_buttons()
                await interaction.response.edit_message(content="Select your preferred time format:", view=self.view)
                self.view.current_step = "time_style_select"
            else:
                # Proceed to time selection
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
            discord.SelectOption(label="24-hour", value="24-hour")
        ]
        super().__init__(
            placeholder="Select your preferred time format",
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        try:
            self.view.time_style = self.values[0]
            # Proceed to time selection
            await self.view.update_time_select(interaction, time_type="start")
        except Exception as e:
            logging.exception(f"Error in TimeStyleSelect callback: {e}")
            await interaction.response.send_message(
                "An error occurred while selecting the time format.", ephemeral=True
            )
            self.view.stop()


class HourSelect(discord.ui.Select):
    def __init__(self, time_type: str, time_style: str):
        self.time_type = time_type  # "start" or "end"
        self.time_style = time_style
        if time_style == "12-hour":
            hours = [str(hour) for hour in range(1, 13)]  # 1 to 12
        else:  # "24-hour"
            hours = [f"{hour:02d}" for hour in range(0, 24)]  # 00 to 23
        options = [discord.SelectOption(label=hour, value=hour) for hour in hours]
        super().__init__(
            placeholder="Select the hour...",
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        try:
            selected_hour = int(self.values[0])
            if self.time_type == "start":
                self.view.start_hour = selected_hour
                if self.time_style == "12-hour":
                    await self.view.update_am_pm_select(interaction, self.time_type)
                else:
                    await self.view.update_minute_select(interaction, self.time_type)
            else:
                self.view.end_hour = selected_hour
                if self.time_style == "12-hour":
                    await self.view.update_am_pm_select(interaction, self.time_type)
                else:
                    await self.view.update_minute_select(interaction, self.time_type)
        except Exception as e:
            logging.exception(f"Error in HourSelect callback: {e}")
            await interaction.response.send_message(
                "An error occurred while selecting the hour.", ephemeral=True
            )
            self.view.stop()


class AMPMSelect(discord.ui.Select):
    def __init__(self, time_type: str):
        self.time_type = time_type  # "start" or "end"
        options = [
            discord.SelectOption(label="AM", value="AM"),
            discord.SelectOption(label="PM", value="PM")
        ]
        super().__init__(
            placeholder="Select AM or PM",
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        try:
            am_pm = self.values[0]
            if self.time_type == "start":
                self.view.start_am_pm = am_pm
                await self.view.update_minute_select(interaction, self.time_type)
            else:
                self.view.end_am_pm = am_pm
                await self.view.update_minute_select(interaction, self.time_type)
        except Exception as e:
            logging.exception(f"Error in AMPMSelect callback: {e}")
            await interaction.response.send_message(
                "An error occurred while selecting AM/PM.", ephemeral=True
            )
            self.view.stop()


class MinuteSelect(discord.ui.Select):
    def __init__(self, time_type: str):
        self.time_type = time_type  # "start" or "end"
        options = [
            discord.SelectOption(label=f"{minute:02d}", value=str(minute)) for minute in [0, 30]
        ]
        super().__init__(
            placeholder="Select the minutes...",
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        try:
            selected_minute = int(self.values[0])
            if self.time_type == "start":
                self.view.start_minute = selected_minute
                # Combine hour and minute to form start_time
                self.view.start_time = f"{self.view.start_hour:02d}:{self.view.start_minute:02d}"
                # Proceed to select end time
                await self.view.update_time_select(interaction, "end")
            else:
                self.view.end_minute = selected_minute
                # Combine hour and minute to form end_time
                self.view.end_time = f"{self.view.end_hour:02d}:{self.view.end_minute:02d}"
                # Proceed to process availability
                await self.view.process_availability(interaction)
        except Exception as e:
            logging.exception(f"Error in MinuteSelect callback: {e}")
            await interaction.response.send_message(
                "An error occurred while selecting the minutes.", ephemeral=True
            )
            self.view.stop()


# Custom Buttons for Adding Multiple Time Slots
class AddAnotherSlotButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Add Another Time Slot", style=discord.ButtonStyle.primary)

    async def callback(self, interaction: discord.Interaction):
        try:
            self.view.clear_items()
            # Reset day and time selections but keep time_style
            self.view.day = None
            self.view.start_hour = None
            self.view.start_minute = None
            self.view.end_hour = None
            self.view.end_minute = None
            self.view.start_am_pm = None
            self.view.end_am_pm = None
            self.view.start_time = None
            self.view.end_time = None
            self.view.timezone = None

            # Proceed to day selection
            self.add_item(DaySelect())
            await interaction.response.edit_message(content="Select the day you are available:", view=self.view)
        except Exception as e:
            logging.exception(f"Error in AddAnotherSlotButton callback: {e}")
            await interaction.response.send_message(
                "An error occurred while adding another time slot.", ephemeral=True
            )
            self.view.stop()


class StateSelect(discord.ui.Select):
    def __init__(self, options: List[discord.SelectOption]):
        super().__init__(
            placeholder="Select your state...",
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        try:
            self.view.state = self.values[0]
            if self.view.state == 'return':
                self.view.us_region = None
                await self.view.update_region_select_us(interaction)
            elif self.view.state == 'cancel':
                self.view.clear_items()
                self.view.stop()
                await interaction.response.send_message("Selection cancelled.", ephemeral=True)
            else:
                await self.view.update_timezone_select_us(interaction)
        except Exception as e:
            logging.exception(f"Error in StateSelect callback: {e}")
            await interaction.response.send_message(
                "An error occurred while selecting your state.", ephemeral=True
            )
            self.view.stop()


class FinishButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Finish", style=discord.ButtonStyle.success)

    async def callback(self, interaction: discord.Interaction):
        try:
            await self.view.process_all_availability(interaction)
        except Exception as e:
            logging.exception(f"Error in FinishButton callback: {e}")
            await interaction.response.send_message(
                "An error occurred while finalizing your availability.", ephemeral=True
            )
            self.view.stop()


class BackButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Back")

    async def callback(self, interaction: discord.Interaction):
        await self.view.go_back(interaction)


class CancelButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Cancel", style=discord.ButtonStyle.danger)

    async def callback(self, interaction: discord.Interaction):
        await self.view.cancel(interaction)


class ChangeTimeFormatButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Change Time Format")

    async def callback(self, interaction: discord.Interaction):
        try:
            self.view.clear_items()
            self.view.add_item(TimeStyleSelect())
            await interaction.response.edit_message(content="Select your preferred time format:", view=self.view)
        except Exception as e:
            logging.exception(f"Error in ChangeTimeFormatButton callback: {e}")
            await interaction.response.send_message(
                "An error occurred while changing time format.", ephemeral=True
            )
            self.view.stop()


class TimezoneCompleteButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Finish", style=discord.ButtonStyle.success)

    async def callback(self, interaction: discord.Interaction):
        try:
            self.view.stop()
            await interaction.response.send_message("Timezone has been set successfully.", ephemeral=True)
        except Exception as e:
            logging.exception(f"Error in FinishButton callback: {e}")
            await interaction.response.send_message(
                "An error occurred while finalizing your availability.", ephemeral=True
            )
            self.view.stop()


# Enhanced AvailabilityView with Multiple Time Slots
class AvailabilityView(discord.ui.View):
    def __init__(self, timezone: typing.Optional[str], prompt_day_update: bool = False):
        super().__init__(timeout=600)
        self.start_am_pm = None
        self.end_am_pm = None
        self.region: Optional[str] = None
        self.continent: Optional[str] = None
        self.country_code: Optional[str] = None
        self.us_region: Optional[str] = None
        self.state: Optional[str] = None
        self.timezone = timezone
        self.day: Optional[str] = None
        self.start_time: Optional[str] = None
        self.end_time: Optional[str] = None
        self.guild_id: Optional[int] = None
        self.user_id: Optional[int] = None
        self.time_slots: List[dict] = []
        self.start_hour: Optional[int] = None
        self.start_minute: Optional[int] = None
        self.end_hour: Optional[int] = None
        self.end_minute: Optional[int] = None
        self.time_style: Optional[str] = None  # Will be set to "12-hour" or "24-hour"
        self.prompt_day_update = prompt_day_update
        # Start with continent selection
        if not self.timezone:
            self.add_item(ContinentSelect())
        else:
            self.add_item(DaySelect())

    def add_navigation_buttons(self):
        self.add_item(BackButton())
        self.add_item(CancelButton())

    async def update_country_select(self, interaction: discord.Interaction):
        try:
            self.clear_items()
            continent_name = self.continent
            logging.info(f"Continent: {continent_name}")

            if continent_name in continent_regions:
                # For continents with regions
                logging.info(f"Region: {self.region}")
                regions = continent_regions[continent_name]
                if self.region is None:
                    await interaction.response.send_message(
                        "Please select a region first.", ephemeral=True
                    )
                    return
                countries = regions.get(self.region, [])
            else:
                # For continents without regions
                countries = [country['name'] for country in continent_to_countries[continent_name]]
                logging.info(f"No region selection needed for continent {continent_name}")

            if not countries:
                await interaction.response.send_message(
                    "No countries found for the selected region or continent.", ephemeral=True
                )
                self.stop()
                return

            # Sort countries alphabetically
            countries_sorted = sorted(countries)
            # Create options for the select menu
            options = [
                discord.SelectOption(label=country) for country in countries_sorted[:25]
            ]
            if len(countries_sorted) > 25:
                options.append(discord.SelectOption(label='Other...', value='other'))
            options.append(discord.SelectOption(label='Cancel', value='cancel'))
            options.append(discord.SelectOption(label='Return', value='return'))

            if not options:
                await interaction.response.send_message(
                    "No country options available.", ephemeral=True
                )
                self.stop()
                return

            if len(countries_sorted) > 24:
                options.append(discord.SelectOption(label='Other...', value='other'))

            self.add_item(CountrySelect(options=options))
            await interaction.response.edit_message(content="Select your country:", view=self)
        except Exception as e:
            logging.exception(f"Error in update_country_select: {e}")
            await interaction.response.send_message(
                "An error occurred while updating country selection.", ephemeral=True
            )
            self.stop()

    async def update_region_select(self, interaction: discord.Interaction):
        try:
            self.clear_items()
            regions = continent_regions.get(self.continent)
            if not regions:
                await interaction.response.send_message(
                    "No regions found for the selected continent.", ephemeral=True
                )
                self.stop()
                return
            # Create a RegionSelect with the regions of the continent
            self.add_item(RegionSelect(continent=self.continent, regions=regions))
            await interaction.response.edit_message(content="Select your region:", view=self)
        except Exception as e:
            logging.exception(f"Error in update_region_select{e}")
            await interaction.response.send_message(
                "An error occurred while updating region selection.", ephemeral=True
            )
            self.stop()

    async def update_state_select(self, interaction: discord.Interaction):
        try:
            self.clear_items()
            if self.country_code == 'US':
                # Get states for the selected US region
                states_in_region = us_regions.get(self.us_region, [])
                if not states_in_region:
                    await interaction.response.send_message(
                        "No states found for the selected region.", ephemeral=True
                    )
                    self.stop()
                    return
                # Create options for states in the region
                options = [
                    discord.SelectOption(label=state) for state in sorted(states_in_region)
                ]
                options.append(discord.SelectOption(label='Return', value='return'))
                options.append(discord.SelectOption(label='Cancel', value='cancel'))
                self.add_item(StateSelect(options=options))
                await interaction.response.edit_message(content="Select your state:", view=self)
            else:
                # Handle other countries if necessary
                pass
        except Exception as e:
            logging.exception(f"Error in update_state_select: {e}")
            await interaction.response.send_message(
                "An error occurred while updating state selection.", ephemeral=True
            )
            self.stop()

    async def update_region_select_us(self, interaction: discord.Interaction):
        try:
            self.clear_items()
            # Assuming you have us_regions defined as before
            regions = us_regions  # Make sure us_regions is defined
            # Create a USRegionSelect for US regions
            self.add_item(USRegionSelect(regions=regions))
            await interaction.response.edit_message(content="Select your US region:", view=self)
        except Exception as e:
            logging.exception(f"Error in update_region_select_us: {e}")
            await interaction.response.send_message(
                "An error occurred while updating US region selection.", ephemeral=True
            )
            self.stop()

    async def update_timezone_select_us(self, interaction: discord.Interaction):
        try:
            self.clear_items()
            state_timezones = us_state_timezones.get(self.state)
            if not state_timezones:
                await interaction.response.send_message(
                    "No time zones found for the selected state.", ephemeral=True
                )
                self.stop()
                return
            # Create options for time zones
            options = [
                discord.SelectOption(label=tz, value=tz) for tz in state_timezones
            ]
            options.append(discord.SelectOption(label='Cancel', value='cancel'))
            options.append(discord.SelectOption(label='Return', value='return'))
            self.add_item(TimezoneSelect(options=options, prompt_day_update=self.prompt_day_update))
            await interaction.response.edit_message(content="Select your time zone:", view=self)
        except Exception as e:
            logging.exception(f"Error in update_timezone_select_us: {e}")
            await interaction.response.send_message(
                "An error occurred while updating time zone selection.", ephemeral=True
            )
            self.stop()

    async def update_timezone_select(self, interaction: discord.Interaction):
        try:
            # Remove previous items
            self.clear_items()
            if self.country_code == 'other':
                await interaction.response.send_message(
                    "Please enter your country manually using the `/timesheet` command with your country.",
                    ephemeral=True
                )
                self.stop()
                return
            # Get time zones for the selected country
            timezones = pytz.country_timezones.get(self.country_code)
            if not timezones:
                await interaction.response.send_message("No time zones found for the selected country.", ephemeral=True)
                self.stop()
                return
            # Create options for the select menu
            options = [
                discord.SelectOption(label=tz, value=tz) for tz in timezones[:25]
            ]
            options.append(discord.SelectOption(label='Cancel', value='cancel'))
            options.append(discord.SelectOption(label='Return', value='Return'))
            if len(timezones) > 25:
                options.append(discord.SelectOption(label='Other...', value='other'))
            self.add_item(TimezoneSelect(options=options, prompt_day_update=self.prompt_day_update))
            await interaction.response.edit_message(content="Select your time zone:", view=self)
        except Exception as e:
            logging.exception(f"Error in update_timezone_select: {e}")
            await interaction.response.send_message(
                "An error occurred while updating time zone selection.", ephemeral=True
            )
            self.view.stop()

    async def on_timeout(self):
        """Disable all components when the view times out."""
        for item in self.children:
            item.disabled = True
        # Optionally, edit the message to inform the user

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Ensure only the initiating user can interact with the view."""
        if self.user_id and interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "You cannot interact with this view.", ephemeral=True
            )
            return False
        return True

    async def update_day_select(self, interaction: discord.Interaction):
        try:
            # Remove the timezone select menu
            self.clear_items()
            # Add the day select menu
            self.add_item(DaySelect())
            await interaction.response.edit_message(content="Select the day of the week:", view=self)
        except Exception as e:
            logging.exception(f"Error in update_day_select: {e}")
            await interaction.response.send_message(
                "An error occurred while updating day selection.", ephemeral=True
            )
            self.stop()

    async def optional_day_select(self, interaction: discord.Interaction):
        try:
            # Remove the timezone select menu
            self.clear_items()
            # Add the day select menu
            self.add_item(DaySelect())
            self.add_item(TimezoneCompleteButton())
            await interaction.response.edit_message(content="Select the day of the week:", view=self)
        except Exception as e:
            logging.exception(f"Error in update_day_select: {e}")
            await interaction.response.send_message(
                "An error occurred while updating day selection.", ephemeral=True
            )
            self.stop()

    async def update_am_pm_select(self, interaction: discord.Interaction, time_type: str):
        try:
            self.clear_items()
            self.add_item(AMPMSelect(time_type=time_type))
            self.add_navigation_buttons()
            await interaction.response.edit_message(content=f"Select AM or PM for your {time_type} time:", view=self)
            # Update current_step
            if time_type == "start":
                self.current_step = "am_pm_select_start"
            else:
                self.current_step = "am_pm_select_end"
        except Exception as e:
            logging.exception(f"Error in update_am_pm_select: {e}")
            await interaction.response.send_message(
                "An error occurred while updating AM/PM selection.", ephemeral=True
            )
            self.stop()

    async def update_time_select(self, interaction: discord.Interaction, time_type: str):
        try:
            self.clear_items()
            self.add_item(HourSelect(time_type=time_type, time_style=self.time_style))
            self.add_navigation_buttons()
            await interaction.response.edit_message(content=f"Select your {time_type} time (hour):", view=self)
            # Update current_step
            if time_type == "start":
                self.current_step = "hour_select_start"
            else:
                self.current_step = "hour_select_end"
        except Exception as e:
            logging.exception(f"Error in update_time_select: {e}")
            await interaction.response.send_message(
                "An error occurred while updating time selection.", ephemeral=True
            )
            self.stop()

    async def update_minute_select(self, interaction: discord.Interaction, time_type: str):
        try:
            self.clear_items()
            self.add_item(MinuteSelect(time_type=time_type))
            self.add_navigation_buttons()
            await interaction.response.edit_message(content=f"Select your {time_type} time (minutes):", view=self)
            # Update current_step
            if time_type == "start":
                self.current_step = "minute_select_start"
            else:
                self.current_step = "minute_select_end"
        except Exception as e:
            logging.exception(f"Error in update_minute_select: {e}")
            await interaction.response.send_message(
                "An error occurred while updating minute selection.", ephemeral=True
            )
            self.stop()

    async def process_availability(self, interaction: discord.Interaction):
        try:
            # All selections have been made, process the data
            required_fields = [self.timezone, self.day]
            if self.time_style == "12-hour":
                required_fields.extend([self.start_am_pm, self.end_am_pm])

            if not all(
                    required_fields) and self.start_hour is None and self.start_minute is None and self.end_hour is None and self.end_minute is None:
                await interaction.response.send_message(
                    "Incomplete availability information.", ephemeral=True
                )
                return

            if self.time_style == "12-hour":
                self.start_hour = self.convert_to_24_hour(self.start_hour, self.start_am_pm)
                self.end_hour = self.convert_to_24_hour(self.end_hour, self.end_am_pm)

            # Convert day string to integer
            days = {
                'Monday': 1, 'Tuesday': 2, 'Wednesday': 3,
                'Thursday': 4, 'Friday': 5, 'Saturday': 6,
                'Sunday': 7
            }
            day_value = days.get(self.day)
            if not day_value:
                await interaction.response.send_message(
                    f"Invalid day: {self.day}", ephemeral=True
                )
                return

            start_time_str = f"{self.start_hour:02d}:{self.start_minute:02d}"
            end_time_str = f"{self.end_hour:02d}:{self.end_minute:02d}"

            # Parse times
            start_time_parsed = parse_time_input(start_time_str)
            end_time_parsed = parse_time_input(end_time_str)
            if not start_time_parsed or not end_time_parsed:
                await interaction.response.send_message(
                    "Invalid start or end time format.", ephemeral=True
                )
                return

            # Get the next occurrence of the selected day
            next_date = get_next_weekday(day_value - 1)  # Adjust for Python's weekday (0=Monday)

            # Create datetime objects with timezone
            try:
                tzinfo = ZoneInfo(self.timezone)
            except Exception as e:
                await interaction.response.send_message(
                    "Invalid timezone selected.", ephemeral=True
                )
                logging.info(f"Error in process_availability: {e}")
                return

            start_datetime = datetime.datetime.combine(next_date, start_time_parsed, tzinfo=tzinfo)
            end_datetime = datetime.datetime.combine(next_date, end_time_parsed, tzinfo=tzinfo)

            # Adjust end time if it's before start time
            if end_datetime <= start_datetime:
                end_datetime += datetime.timedelta(days=1)

            # Convert to UTC
            # start_datetime_utc = start_datetime.astimezone(datetime.timezone.utc)
            # end_datetime_utc = end_datetime.astimezone(datetime.timezone.utc)

            # Extract hours and minutes for storage
            # start_hours = start_datetime_utc.hour
            # start_minutes = start_datetime_utc.minute
            # end_hours = end_datetime_utc.hour
            # end_minutes = end_datetime_utc.minute

            # Add the time slot to the list
            self.time_slots.append({
                'day': self.day,
                'start_time': self.start_time,
                'end_time': self.end_time,
                'timezone': self.timezone
            })

            # Reset selections for another entry
            # Reset selections for another entry
            self.day = None
            self.start_hour = None
            self.start_minute = None
            self.end_hour = None
            self.end_minute = None
            self.start_time = None
            self.end_time = None
            self.start_am_pm = None
            self.end_am_pm = None

            # Ask if the user wants to add another time slot
            self.clear_items()
            self.add_item(AddAnotherSlotButton())
            self.add_item(FinishButton())
            await interaction.response.edit_message(
                content="Time slot added! Would you like to add another time slot or finish?",
                view=self
            )
        except Exception as e:
            logging.exception(f"Error in process_availability: {e}")
            await interaction.response.send_message(
                "An unexpected error occurred while processing your availability.", ephemeral=True
            )
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

                    # Parse times
                    start_time_parsed = parse_time_input(slot['start_time'])
                    end_time_parsed = parse_time_input(slot['end_time'])

                    if not start_time_parsed or not end_time_parsed:
                        await interaction.response.send_message(
                            f"Invalid time format for {slot['day']}. Skipping.", ephemeral=True
                        )
                        continue

                    # Get the next occurrence of the selected day
                    next_date = get_next_weekday(day_value - 1)  # Adjust for Python's weekday (0=Monday)

                    # Create datetime objects with timezone
                    try:
                        tzinfo = ZoneInfo(slot['timezone'])
                    except Exception as e:
                        await interaction.response.send_message(
                            f"Invalid timezone {slot['timezone']} for {slot['day']}. Skipping.", ephemeral=True
                        )
                        logging.info(f"Error in process_all_availability: {e}")
                        continue

                    start_datetime = datetime.datetime.combine(next_date, start_time_parsed, tzinfo=tzinfo)
                    end_datetime = datetime.datetime.combine(next_date, end_time_parsed, tzinfo=tzinfo)

                    # Adjust end time if it's before start time
                    # Convert to UTC
                    start_datetime_utc = start_datetime.astimezone(datetime.timezone.utc)
                    end_datetime_utc = end_datetime.astimezone(datetime.timezone.utc)

                    #                    utc_offset = start_datetime.utcoffset().total_seconds()

                    if end_datetime <= start_datetime:
                        end_datetime += datetime.timedelta(days=1)
                    # Extract hours and minutes for storage
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

                    if end_datetime_utc.isoweekday() != start_datetime_utc.isoweekday():
                        end_time = 1440
                        start_time = 0

                        # start day
                        for col in time_columns:
                            minutes = time_to_minutes(col)
                            if start_combined <= minutes <= end_time:
                                columns_to_nullify.append(f'"{col}" = 1')
                        set_clause = ', '.join(columns_to_nullify)
                        sql = f"""
                            UPDATE Player_Timecard
                            SET {set_clause}
                            WHERE Player_Name = ? and Day = ?
                            """

                        await cursor.execute(sql,
                                             (user_name, end_datetime_utc.isoweekday()))
                        await db.commit()
                        # end day
                        for col in time_columns:
                            minutes = time_to_minutes(col)
                            if start_time <= minutes <= end_combined:
                                columns_to_nullify.append(f'"{col}" = 1')
                        set_clause = ', '.join(columns_to_nullify)
                        sql = f"""
                        UPDATE Player_Timecard
                        SET {set_clause}
                        WHERE Player_Name = ? and Day = ?
                        """

                        await cursor.execute(sql,
                                             (user_name, end_datetime_utc.isoweekday()))
                        await db.commit()
                    else:
                        for col in time_columns:
                            minutes = time_to_minutes(col)
                            if start_combined <= minutes <= end_combined:
                                columns_to_nullify.append(f'"{col}" = 1')
                        set_clause = ', '.join(columns_to_nullify)
                        sql = f"""
                        UPDATE Player_Timecard
                        SET {set_clause}
                        WHERE Player_Name = ? and Day = ?
                        """

                        await cursor.execute(sql,
                                             (user_name, start_datetime.isoweekday()))
                        await db.commit()

            # Inform the user
            embed = discord.Embed(
                title="Availability Updated",
                description=f"Your availability has been successfully updated.",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            self.stop()
        except Exception as e:
            logging.exception(f"Error in process_all_availability: {e}")
            await interaction.response.send_message(
                "An unexpected error occurred while finalizing your availability.", ephemeral=True
            )
            self.stop()

    def convert_to_24_hour(self, hour: int, am_pm: str) -> int:
        """Convert 12-hour format to 24-hour format."""
        if am_pm == "AM":
            return hour % 12  # 12 AM is 0 hours
        else:
            return (hour % 12) + 12  # 12 PM is 12 hours

    async def cancel(self, interaction: discord.Interaction):
        try:
            await interaction.response.send_message("Availability setup has been canceled.", ephemeral=True)
            self.stop()
        except Exception as e:
            logging.exception(f"Error in cancel: {e}")
            self.stop()

    async def go_back(self, interaction: discord.Interaction):
        try:
            # Determine the previous step based on current_step
            if self.current_step == "minute_select_end":
                # Go back to end time hour selection
                await self.update_time_select(interaction, time_type="end")
                self.current_step = "hour_select_end"
            elif self.current_step == "hour_select_end":
                # Go back to start time minute selection
                await self.update_minute_select(interaction, time_type="start")
                self.current_step = "minute_select_start"
            elif self.current_step == "minute_select_start":
                # Go back to start time hour selection
                await self.update_time_select(interaction, time_type="start")
                self.current_step = "hour_select_start"
            elif self.current_step == "hour_select_start":
                if self.time_style == "12-hour":
                    # Go back to AM/PM selection if in 12-hour format
                    await self.update_am_pm_select(interaction, time_type="start")
                    self.current_step = "am_pm_select_start"
                else:
                    # Go back to day selection
                    self.clear_items()
                    self.add_item(DaySelect())
                    self.add_navigation_buttons()
                    await interaction.response.edit_message(content="Select the day you are available:", view=self)
                    self.current_step = "day_select"
            elif self.current_step == "am_pm_select_start":
                # Go back to hour selection
                await self.update_time_select(interaction, time_type="start")
                self.current_step = "hour_select_start"
            elif self.current_step == "day_select":
                # Go back to time style selection if it was selected
                if self.time_style:
                    # Already selected, cannot go back further
                    await interaction.response.send_message("You are at the first step and cannot go back further.",
                                                            ephemeral=True)
                else:
                    # Go back to time style selection
                    self.clear_items()
                    self.add_item(TimeStyleSelect())
                    self.add_navigation_buttons()
                    await interaction.response.edit_message(content="Select your preferred time format:", view=self)
                    self.current_step = "time_style_select"
            elif self.current_step == "time_style_select":
                # Cannot go back further
                await interaction.response.send_message("You are at the first step and cannot go back further.",
                                                        ephemeral=True)
            else:
                # Default case
                await interaction.response.send_message("Cannot go back from here.", ephemeral=True)
        except Exception as e:
            logging.exception(f"Error in go_back: {e}")
            await interaction.response.send_message(
                "An error occurred while going back to the previous step.", ephemeral=True
            )
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
        # Start with continent selection
        self.add_item(DaySelect())

    async def update_day_select(self, interaction: discord.Interaction):
        try:
            # Remove the timezone select menu
            self.clear_items()
            # Add the day select menu
            self.add_item(DaySelect())
            await interaction.response.edit_message(content="Select the day of the week:", view=self)
        except Exception as e:
            logging.exception(f"Error in update_day_select: {e}")
            await interaction.response.send_message(
                "An error occurred while updating day selection.", ephemeral=True
            )
            self.stop()

    async def update_time_select(self, interaction: discord.Interaction, time_type: str):
        try:
            # Remove previous items
            self.clear_items()
            # Add HourSelect
            self.add_item(HourSelect(time_type=time_type, time_style="24-hour"))
            await interaction.response.edit_message(content=f"Select your {time_type} time (hour):", view=self)
        except Exception as e:
            logging.exception(f"Error in update_time_select: {e}")
            await interaction.response.send_message(
                "An error occurred while updating time selection.", ephemeral=True
            )
            self.stop()

    async def update_minute_select(self, interaction: discord.Interaction, time_type: str):
        try:
            # Remove previous items
            self.clear_items()
            # Add MinuteSelect
            self.add_item(MinuteSelect(time_type=time_type))
            await interaction.response.edit_message(content=f"Select your {time_type} time (minutes):", view=self)
        except Exception as e:
            logging.exception(f"Error in update_minute_select: {e}")
            await interaction.response.send_message(
                "An error occurred while updating minute selection.", ephemeral=True
            )
            self.stop()

    async def process_availability(self, interaction: discord.Interaction):
        try:
            # All selections have been made, process the data

            if not all([self.timezone,
                        self.day]) and self.start_hour is None and self.start_minute is None and self.end_hour is None and self.end_minute is None:
                await interaction.response.send_message(
                    "Incomplete availability information.", ephemeral=True
                )
                return

            # Convert day string to integer
            days = {
                'Monday': 1, 'Tuesday': 2, 'Wednesday': 3,
                'Thursday': 4, 'Friday': 5, 'Saturday': 6,
                'Sunday': 7
            }
            day_value = days.get(self.day)
            if not day_value:
                await interaction.response.send_message(
                    f"Invalid day: {self.day}", ephemeral=True
                )
                return

            start_time_str = f"{self.start_hour:02d}:{self.start_minute:02d}"
            end_time_str = f"{self.end_hour:02d}:{self.end_minute:02d}"

            # Parse times
            start_time_parsed = parse_time_input(start_time_str)
            end_time_parsed = parse_time_input(end_time_str)
            if not start_time_parsed or not end_time_parsed:
                await interaction.response.send_message(
                    "Invalid start or end time format.", ephemeral=True
                )
                return

            # Get the next occurrence of the selected day
            next_date = get_next_weekday(day_value - 1)  # Adjust for Python's weekday (0=Monday)

            # Create datetime objects with timezone
            try:
                tzinfo = ZoneInfo(self.timezone)
            except Exception as e:
                await interaction.response.send_message(
                    "Invalid timezone selected.", ephemeral=True
                )
                logging.info(f"Invalid timezone selected. {e}")
                return

            start_datetime = datetime.datetime.combine(next_date, start_time_parsed, tzinfo=tzinfo)
            end_datetime = datetime.datetime.combine(next_date, end_time_parsed, tzinfo=tzinfo)

            utc_offset = start_datetime.utcoffset().total_seconds()
            if end_datetime <= start_datetime and utc_offset < 0:
                end_datetime += datetime.timedelta(days=1)
            elif end_datetime <= start_datetime and utc_offset > 0:
                start_datetime -= datetime.timedelta(days=1)

            # Convert to UTC
            # start_datetime_utc = start_datetime.astimezone(datetime.timezone.utc)
            # end_datetime_utc = end_datetime.astimezone(datetime.timezone.utc)

            # Extract hours and minutes for storage
            # start_hours = start_datetime_utc.hour
            # start_minutes = start_datetime_utc.minute
            # end_hours = end_datetime_utc.hour
            # end_minutes = end_datetime_utc.minute

            # Add the time slot to the list
            self.time_slots.append({
                'day': self.day,
                'start_time': self.start_time,
                'end_time': self.end_time,
                'timezone': self.timezone
            })

            # Reset selections for another entry
            # Reset selections for another entry
            self.day = None
            self.start_hour = None
            self.start_minute = None
            self.end_hour = None
            self.end_minute = None
            self.start_time = None
            self.end_time = None

            # Ask if the user wants to add another time slot
            self.clear_items()
            self.add_item(AddAnotherSlotButton())
            self.add_item(FinishButton())
            await interaction.response.edit_message(
                content="Time slot added! Would you like to add another time slot or finish?",
                view=self
            )
        except Exception as e:
            logging.exception(f"Error in process_availability: {e}")
            await interaction.response.send_message(
                "An unexpected error occurred while processing your availability.", ephemeral=True
            )
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

                    # Parse times
                    start_time_parsed = parse_time_input(slot['start_time'])
                    end_time_parsed = parse_time_input(slot['end_time'])
                    if not start_time_parsed or not end_time_parsed:
                        await interaction.response.send_message(
                            f"Invalid time format for {slot['day']}. Skipping.", ephemeral=True
                        )
                        continue

                    # Get the next occurrence of the selected day
                    next_date = get_next_weekday(day_value - 1)  # Adjust for Python's weekday (0=Monday)

                    # Create datetime objects with timezone
                    try:
                        tzinfo = ZoneInfo(slot['timezone'])
                    except Exception as e:
                        await interaction.response.send_message(
                            f"Invalid timezone {slot['timezone']} for {slot['day']}. Skipping.", ephemeral=True
                        )
                        logging.info(f"Error in process_all_availability {e}")
                        continue

                    start_datetime = datetime.datetime.combine(next_date, start_time_parsed, tzinfo=tzinfo)
                    end_datetime = datetime.datetime.combine(next_date, end_time_parsed, tzinfo=tzinfo)

                    # Adjust end time if it's before start time
                    if end_datetime <= start_datetime:
                        end_datetime += datetime.timedelta(days=1)

                    # Convert to UTC
                    start_datetime_utc = start_datetime.astimezone(datetime.timezone.utc)
                    end_datetime_utc = end_datetime.astimezone(datetime.timezone.utc)

                    # Extract hours and minutes for storage
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

                        # start day
                        for col in time_columns:
                            minutes = time_to_minutes(col)
                            if start_combined <= minutes <= end_time:
                                columns_to_nullify.append(f'"{col}" = Null')
                        set_clause = ', '.join(columns_to_nullify)
                        await cursor.execute(f"""
                        UPDATE Player_Timecard
                        SET {set_clause}
                        WHERE Player_Name = ? and Day = ?
                        """,
                                             (user_name, start_datetime.isoweekday()))
                        await db.commit()
                        # end day
                        for col in time_columns:
                            minutes = time_to_minutes(col)
                            if start_time <= minutes <= end_combined:
                                columns_to_nullify.append(f'"{col}" = Null')
                        set_clause = ', '.join(columns_to_nullify)
                        await cursor.execute(f"""
                        UPDATE Player_Timecard
                        SET {set_clause}
                        WHERE Player_Name = ? and Day = ?
                        """,
                                             (user_name, end_datetime.isoweekday()))
                        await db.commit()
                    else:
                        for col in time_columns:
                            minutes = time_to_minutes(col)
                            if start_combined <= minutes <= end_combined:
                                columns_to_nullify.append(f'"{col}" = Null')
                        set_clause = ', '.join(columns_to_nullify)
                        await cursor.execute(f"""
                        UPDATE Player_Timecard
                        SET {set_clause}
                        WHERE Player_Name = ? and Day = ?
                        """,
                                             (user_name, start_datetime.isoweekday()))
                        await db.commit()

            # Inform the user
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


async def player_signup(
        guild: discord.Guild,
        thread_id: int,
        session_name: str,
        session_id: int,
        player_id: int,
        character_name: str,
        warning_duration: typing.Optional[int]) -> bool:
    try:
        async with aiosqlite.connect(f"pathparser_{guild.id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute(
                """Select 
                player_name, True_Character_Name, title, 
                level, tier, 
                gold, gold_value, 
                tradition_name, tradition_link, template_name, template_link, 
                mythweavers, image_link, color, 
                description, titles,
                essence, oath from Player_Characters where Player_ID = ? and Character_Name = ?""",
                (player_id, character_name))
            character_info = await cursor.fetchone()
            if character_info:
                (player_name, character_name, title,
                 level, tier,
                 gold, gold_value,
                 tradition_name, tradition_link, template_name, template_link,
                 mythweavers, image_link, color,
                 description, titles,
                 essence, oath) = character_info
                await cursor.execute("SELECT Character_Name from Sessions_Signups WHERE Character_Name = ? and Session_ID = ?",
                                     (character_name,session_id))
                character_present = await cursor.fetchone()
                if character_present:
                    return False

                await cursor.execute(
                    """INSERT INTO Sessions_Signups (Session_ID, Session_Name, Player_Name, Player_ID, Character_Name, Level, Effective_Wealth, Tier, Notification_Warning) Values (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (session_id, session_name, player_name, player_id, character_name, level, gold_value - gold, tier,
                     warning_duration)
                )
                await db.commit()

                thread = guild.get_thread(thread_id)
                if not thread:
                    thread = await guild.fetch_channel(thread_id)
                if thread:
                    embed = signup_embed(
                        character_name=character_name,
                        title=titles,
                        level=level,
                        tier=tier,
                        gold=gold,
                        gold_value=gold_value,
                        tradition_name=tradition_name,
                        tradition_link=tradition_link,
                        template_name=template_name,
                        template_link=template_link,
                        mythweavers=mythweavers,
                        image_link=image_link,
                        color=color,
                        description=description)
                    await thread.send(embed=embed, content=f"<@{player_id}>",
                                      allowed_mentions=discord.AllowedMentions(users=True))
                    return True
                else:
                    raise ValueError(f"Thread {thread_id} not found in guild {guild.id}")
            else:
                raise ValueError(f"Character {character_name} not found for player {player_id}")
    except (aiosqlite.Error, TypeError) as e:
        logging.exception(f"Failed to sign up player <@{player_id}> for session {session_name} ({session_id}): {e}")


def signup_embed(
        character_name: str,
        title: str,
        level: int,
        tier: int,
        gold: int,
        gold_value: int,
        tradition_name: str,
        tradition_link: str,
        template_name: str,
        template_link: str,
        mythweavers: str,
        image_link: str,
        color: str,
        description: str) -> discord.Embed:
    try:
        if any([tradition_name, tradition_link, template_name, template_link]):
            print("Tradition or template found")
            print(tradition_name, tradition_link, template_name, template_link)
        title_field = f"{character_name} would like to participate" if title is None else f"{title} {character_name} would like to participate"
        embed = discord.Embed(title=title_field, color=int(color[1:], 16), url=mythweavers)
        embed.set_thumbnail(url=image_link)
        gold_string = shared_functions.get_gold_breakdown(gold_value - gold)
        embed.add_field(name="Information", value=f"**Level**: {level}, **Mythic Tier**: {tier}")
        embed.add_field(name="illiquid Wealth", value=f"**Gold**: {gold_string}")
        additional_info = f"**Tradition**: [{tradition_name}]({tradition_link})" if tradition_name else ""
        additional_info += '\r\n' if tradition_name and template_name else ""
        additional_info += f"**Template**: [{template_name}]({template_link})" if template_name else ""
        if tradition_name or template_name:
            embed.add_field(name="Additional Info", value=additional_info, inline=False)
        embed.set_footer(text=description)
        return embed
    except ValueError as e:
        logging.exception(f"Failed to create signup embed for character {character_name}: {e}")


async def player_leave_session(guild: discord.Guild, session_id: int, player_name: str, player: bool = True) -> bool:
    async with aiosqlite.connect(f"pathparser_{guild.id}.sqlite") as db:
        try:
            cursor = await db.cursor()
            await cursor.execute("SELECT Session_Thread FROM Sessions WHERE Session_ID = ?", (session_id,))
            session_info = await cursor.fetchone()
            print(session_info)

            await cursor.execute(
                "DELETE FROM Sessions_Signups WHERE Session_ID = ? AND Player_Name = ?",
                (session_id, player_name)
            )
            await cursor.execute(
                "DELETE FROM Sessions_Participants WHERE Session_ID = ? AND Player_Name = ?",
                (session_id, player_name)
            )
            await db.commit()
            print("Deleted from signups and participants")

            if session_info:
                thread_id = session_info[0]
                thread = guild.get_thread(thread_id)
                if not thread:
                    thread = await guild.fetch_channel(thread_id)
                if thread:
                    if player:
                        await thread.send(f"{player_name} has decided against participating in the session!")
                    else:
                        await thread.send(f"{player_name} has been removed from the session!")
                    return True
                else:
                    raise ValueError(f"Thread {thread_id} not found in guild {guild.id}")
            return True
        except aiosqlite.Error as e:
            logging.exception(f"Failed to remove player {player_name} from session {session_id}: {e}")


async def update_report(guild_id: int, overview: str, world_id: str, article_id: str, character_name: str,
                        author_name: str):
    try:
        if guild_id == 883009758179762208:
            time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            client = WaClient(
                'pathparser',
                'https://github.com/Solfyrism/pathparser',
                'V1.1',
                os.getenv('WORLD_ANVIL_API'),
                os.getenv('WORLD_ANVIL_USER')
            )
            overview = shared_functions.drive_word_document(overview)

            specific_article = client.article.get(article_id, granularity=1)

            new_overview = f'{specific_article["reportNotes"]} [br] [br] {author_name} [br] {character_name} - {time} [br] {overview}' if \
                specific_article["reportNotes"] is not None else f'{character_name} - {time} [br] {overview}'
            client.article.patch(article_id, {
                'reportNotes': f'{new_overview}',
                'world': {'id': world_id}
            })
            return True
    except (ValueError, KeyError) as e:
        logging.exception(f"Failed to update report for {character_name} in guild {guild_id}: {e}")
        return False


async def delete_group(guild: discord.Guild, group_id: int, role_id: int) -> bool:
    try:
        async with aiosqlite.connect(f"pathparser_{guild.id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute("DELETE FROM Sessions_group WHERE Group_ID = ?", (group_id,))
            await db.commit()
            await cursor.execute("DELETE FROM Sessions_Group_Presign WHERE Role_ID = ?", (role_id,))
            await db.commit()
            await guild.get_role(role_id).delete()
            return True
    except aiosqlite.Error as e:
        logging.exception(f"Failed to delete group {group_id} in guild {guild.id}: {e}.")
        return False


async def create_new_group(
        guild: discord.Guild,
        player_name: str,
        player_id: int,
        group_name: str,
        host_character: str,
        description: str) -> typing.Optional[discord.Role]:
    try:
        async with aiosqlite.connect(f"pathparser_{guild.id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute(
                "INSERT INTO Sessions_Group(Player_Name, Group_Name, Host_Character, Description) VALUES (?, ?, ?, ?)",
                (player_name, group_name, host_character, description))
            await db.commit()
            await cursor.execute(
                "SELECT Max(Group_ID) FROM Sessions_Group WHERE Player_Name = ? AND Group_Name = ? AND Host_Character = ?",
                (player_name, group_name, host_character))
            group_id = await cursor.fetchone()
            role = await guild.create_role(name=group_name, mentionable=True)

            await cursor.execute("INSERT INTO Sessions_Group_Presign(Group_ID, Player_Name) VALUES (?, ?)",
                                 (group_id[0], player_name))
            await db.commit()
            await cursor.execute("UPDATE Sessions_Group SET Role_ID = ? WHERE Group_ID = ?", (role.id, group_id[0]))
            await db.commit()
            await guild.get_member(player_id).add_roles(role)

            return role
    except aiosqlite.Error as e:
        logging.exception(f"Failed to delete group {group_id} in guild {guild.id}: {e}.")
        return None


async def join_group(
        guild: discord.Guild,
        player_name: str,
        player_id: int,
        group_id: int,
        group_role_id) -> bool:
    try:
        async with aiosqlite.connect(f"pathparser_{guild.id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute(
                "INSERT INTO Sessions_Group_Presign(Group_ID, Player_Name) VALUES (?, ?)",
                (group_id, player_name))
            await db.commit()
            await guild.get_member(player_id).add_roles(guild.get_role(group_role_id))
            return True
    except aiosqlite.Error as e:
        logging.exception(f"Failed to delete group {group_id} in guild {guild.id}: {e}.")
        return False


def random_name():
    name = ''
    url = 'https://www.mit.edu/~ecprice/wordlist.10000'
    response = requests.get(url)
    words = response.content.splitlines()
    max_length = 32
    while len(name) + 4 < max_length:
        word = random.choice(words)
        if len(name) + len(word) < max_length:
            name += word.decode('utf-8').capitalize()
        else:
            break
    return name


async def leave_group(
        guild: discord.Guild,
        player_name: str,
        player_id: int,
        group_id: int,
        group_role_id: int) -> bool:
    try:
        async with aiosqlite.connect(f"pathparser_{guild.id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute("DELETE FROM Sessions_Group_Presign WHERE Group_ID = ? AND Player_Name = ?",
                                 (group_id, player_name))
            await db.commit()
            player = guild.get_member(player_id)
            if not player:
                raise ValueError(f"Player {player_id} not found in guild {guild.id}")
            role = guild.get_role(group_role_id)
            if not role:
                raise ValueError(f"Role {group_role_id} not found in guild {guild.id}")
            await player.remove_roles(role)
            return True
    except aiosqlite.Error as e:
        logging.exception(f"Failed to delete group {group_id} in guild {guild.id}: {e}.")
        return False


async def build_timesheet(guild_id: int, player_name: str) -> bool:
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()
            day = 1
            while day < 8:
                await cursor.execute("INSERT INTO Player_Timecard (Player_Name, Day) VALUES (?, ?)", (player_name, day))
                await db.commit()
                day += 1
            return True
    except aiosqlite.Error as e:
        logging.exception(f"Failed to build timesheet for {player_name} in guild {guild_id}: {e}.")
        return False


async def clear_timesheet(guild_id: int, player_name: str) -> bool:
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute("DELETE FROM Player_Timecard WHERE Player_Name = ?", (player_name,))
            await db.commit()
            return True
    except aiosqlite.Error as e:
        logging.exception(f"Failed to clear timesheet for {player_name} in guild {guild_id}: {e}.")
        return False


async def update_player_timezone(guild_id: int, player_name: str, timezone: str) -> bool:
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute("UPDATE Player_Timecard SET UTC_Offset = ? WHERE Player_Name = ?",
                                 (timezone, player_name))
            await db.commit()
            return True
    except aiosqlite.Error as e:
        logging.exception(f"Failed to update timezone for {player_name} in guild {guild_id}: {e}.")
        return False


class PlayerCommands(commands.Cog, name='Player'):
    def __init__(self, bot):
        self.bot = bot

    player_group = discord.app_commands.Group(
        name='player',
        description='Commands related to playing'
    )

    sessions_group = discord.app_commands.Group(
        name='sessions',
        description='commands related to participating and playing in sessions..',
        parent=player_group
    )

    group_group = discord.app_commands.Group(
        name='group',
        description='Commands related to grouping up.',
        parent=player_group
    )

    timesheet_group = discord.app_commands.Group(
        name='timesheet',
        description='Commands related to setting your availability',
        parent=player_group
    )


    @player_group.command(name='help', description="Get help with player commands")
    async def help(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        embed = discord.Embed(title="Player Commands Help", color=discord.Color.green())
        embed.add_field(
            name="__**Group**__",
            value="""Commands related to grouping up with your fellow players! \r\n
            **/player group create** - Create a new group for players to join! \n
            **/player group delete** - Delete a group that you have created! \n
            **/player group display** - Display all the groups! \n
            **/player group join** - Join a group that has been created! \n
            **/player group leave** - Leave a group that you have joined! \n
        """, inline=False)
        embed.add_field(
            name="__**Timesheet**__",
            value="""Commands related to setting up your timesheets! \r\n
                **/player timesheet availability** - Display your availability on a day! \n
                **/player timesheet group** - Display the overall availability of a group! \n
                **/player timesheet set** - Set your time and timezone! \n
                **/player timesheet timezone** - Set a specific timezone if you don't want to use the options menu! \n
                """, inline=False)
        embed.add_field(
            name="__**Sessions**__",
            value="""Commands related to participating and playing in sessions! \r\n
            **/player sessions Display** - display sessions! \n
            **/player sessions join** - Join a session! \n
            **/player sessions leave** - Leave a session! \n
            **/player sessions Notify** - Update your notification window! \n
            **/player sessions report** - report on a session and add your notes to a WA article! \n    
            """, inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @sessions_group.command(name='join', description='join a session')
    @app_commands.autocomplete(character_name=shared_functions.own_character_select_autocompletion)
    @app_commands.choices(notification=[
        discord.app_commands.Choice(name='an hour before', value=60),
        discord.app_commands.Choice(name='half an hour before', value=30),
        discord.app_commands.Choice(name='session start', value=0),
        discord.app_commands.Choice(name='no reminder', value=-1)])
    async def join(self, interaction: discord.Interaction, session_id: int, character_name: str,
                   notification: typing.Optional[discord.app_commands.Choice[int]]):
        """Offer your Participation in a session."""
        warning_duration = -1 if notification is None else notification.value
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute(
                    "SELECT Session_Name, Play_location, hammer_time, game_link, Session_Range_ID, Session_Range, Session_Thread, overflow FROM Sessions WHERE Session_ID = ? AND IsActive = 1",
                    (session_id,)
                )
                session_info = await cursor.fetchone()
                if session_info is None:
                    await interaction.followup.send(f"No active session with Session ID: {session_id} can be found!")
                else:
                    (session_name, play_location, hammer_time, game_link, session_range_id, session_range,
                     session_thread,
                     overflow) = session_info

                    await cursor.execute(
                        "SELECT Player_Name from Sessions_Signups WHERE Session_ID = ? AND Player_Name = ?",
                        (session_id, interaction.user.name))
                    signup_present = await cursor.fetchone()
                    await cursor.execute(
                        "SELECT Player_Name from Sessions_Participants WHERE Session_ID = ? AND Player_Name = ?", (session_id, interaction.user.name)
                    )
                    participant_present = await cursor.fetchone()
                    if signup_present or participant_present:
                        await interaction.followup.send(
                            f"Player {interaction.user.name} has already signed up for session {session_name} ({session_id})",
                            ephemeral=True)
                        return
                    else:

                        await cursor.execute(
                            "SELECT Level from Player_Characters WHERE Player_ID = ? AND Character_Name = ?",
                            (interaction.user.id, character_name))
                        character_info = await cursor.fetchone()
                        if not character_info:
                            await interaction.followup.send(
                                f"Character {character_name} not found for player {interaction.user.name}")
                            return
                        else:
                            level = character_info[0]
                            quest_thread = interaction.guild.get_thread(session_thread)
                            if not quest_thread:
                                quest_thread = await interaction.guild.fetch_channel(session_thread)
                            if not quest_thread:
                                raise ValueError(f"Thread {session_thread} not found in guild {interaction.guild_id}")

                            if overflow != 4:
                                secondary_role = await gamemaster_commands.validate_milestone_system_overflow(
                                    guild=interaction.guild,
                                    overflow=overflow,
                                    session_range_id=session_range_id)
                                if not secondary_role:
                                    secondary_role = await gamemaster_commands.validate_region_system_overflow(
                                        guild=interaction.guild,
                                        overflow=overflow,
                                        session_range_id=session_range_id)
                                else:
                                    (secondary_role, min_level, max_level) = secondary_role
                                if overflow == 1 or not secondary_role:
                                    await cursor.execute(
                                        "Select min(level), max(level), Level_Range_ID from Milestone_System WHERE Level_Range_ID = ?",
                                        (session_range_id,))
                                    level_range_info = await cursor.fetchone()
                                    (min_level, max_level, role_name) = level_range_info
                                else:
                                    (role_name, min_level, max_level) = secondary_role
                            else:
                                min_level = 0
                                max_level = 999
                                join_session = await player_signup(
                                    guild=interaction.guild,
                                    thread_id=session_thread,
                                    session_name=session_name,
                                    session_id=session_id,
                                    player_id=interaction.user.id,
                                    character_name=character_name,
                                    warning_duration=warning_duration)
                                if join_session:
                                    await interaction.followup.send(
                                        content="You have submitted your request! Please wait for the GM to accept or deny your request!",
                                        ephemeral=True)
                                else:
                                    await interaction.followup.send(
                                        f"Failed to sign up player {interaction.user.name} for session {session_name} ({session_id})",
                                        ephemeral=True)
                            if not min_level or not max_level:
                                role = interaction.guild.get_role(session_range_id)
                                if not role:
                                    await interaction.followup.send(
                                        f"Role {session_range_id} not found in guild {interaction.guild_id}")
                                    raise ValueError(f"Role {session_range_id} not found in guild {interaction.guild_id}")
                                if role in interaction.user.roles:

                                    join_session = await player_signup(
                                        guild=interaction.guild,
                                        thread_id=session_thread,
                                        session_name=session_name,
                                        session_id=session_id,
                                        player_id=interaction.user.id,
                                        character_name=character_name,
                                        warning_duration=warning_duration)
                                    if join_session:
                                        await interaction.followup.send(
                                            content=f"You have submitted your request! Please wait for the GM to accept or deny your request!",
                                            ephemeral=True)
                                    else:
                                        await interaction.followup.send(
                                            f"Failed to sign up player {interaction.user.name} for session {session_name} ({session_id})",
                                            ephemeral=True)
                                else:
                                    await interaction.followup.send(
                                        f"You do not have the required role to join this session.", ephemeral=True)
                            else:
                                if min_level <= level <= max_level:
                                    join_session = await player_signup(
                                        guild=interaction.guild,
                                        thread_id=session_thread,
                                        session_name=session_name,
                                        session_id=session_id,
                                        player_id=interaction.user.id,
                                        character_name=character_name,
                                        warning_duration=warning_duration)
                                    if join_session:
                                        await interaction.followup.send(
                                            content=f"You have submitted your request! Please wait for the GM to accept or deny your request!",
                                            ephemeral=True)
                                    else:
                                        await interaction.followup.send(
                                            f"Failed to sign up player {interaction.user.name} for session {session_name} ({session_id})",
                                            ephemeral=True)
                                else:
                                    await interaction.followup.send(
                                        f"Character {character_name} is not within the level range of the session.",
                                        ephemeral=True)
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(
                f"Failed to sign up player {interaction.user.name} for session with id: ({session_id}:{e}")

    @sessions_group.command(name='notify', description='Update your notification time for a session')
    @app_commands.choices(notification=[
        discord.app_commands.Choice(name='an hour before', value=60),
        discord.app_commands.Choice(name='half an hour before', value=30),
        discord.app_commands.Choice(name='session start', value=0),
        discord.app_commands.Choice(name='no reminder', value=-1)])
    async def notify_me(
            self, interaction:
            discord.Interaction,
            session_id: int,
            notification: typing.Optional[discord.app_commands.Choice[int]]):
        warning_duration = -1 if notification is None else notification.value
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                update_signups = await cursor.execute(
                    "UPDATE Sessions_Signups SET Notification_Warning = ? WHERE Session_ID = ? AND Player_ID = ?",
                    (warning_duration, session_id, interaction.user.id))
                await db.commit()
                update_participants = await cursor.execute(
                    "UPDATE Sessions_Participants SET Notification_Warning = ? WHERE Session_ID = ? AND Player_ID = ?",
                    (warning_duration, session_id, interaction.user.id))
                await db.commit()
                if update_signups.rowcount > 0 or update_participants.rowcount > 0:
                    await interaction.followup.send(content=f"Notification time updated for {session_id}!",
                                                    ephemeral=True)
        except (aiosqlite.Error, TypeError) as e:
            logging.exception(f"Failed to sign up player {interaction.user.name} for session ({session_id}): {e}")
            await interaction.followup.send(
                f"Failed to sign up player {interaction.user.name} for session ({session_id})", ephemeral=True)

    @sessions_group.command(name='leave', description='Rescind your Participation in a session')
    async def leave_session(self, interaction: discord.Interaction, session_id: int):
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute(
                    "SELECT Session_Name, Play_location, hammer_time, Game_Link FROM Sessions WHERE Session_ID = ?",
                    (session_id,))
                print("i got here")
                session_info = await cursor.fetchone()
                if session_info is None:
                    await interaction.followup.send(f"No active session with {session_id} can be found!")
                if session_info is not None:
                    await cursor.execute(
                        "SELECT Character_Name, Level, Effective_Wealth from Sessions_Signups where Player_Name = ? and session_ID = ?",
                        (interaction.user.name, session_id))
                    character_info = await cursor.fetchone()
                    if character_info is None:
                        await cursor.execute(
                            "SELECT Character_Name, Level, Effective_Wealth from Sessions_Participants where Player_Name = ? and session_ID = ?",
                            (interaction.user.name,session_id))
                        character_info = await cursor.fetchone()
                        if character_info is None:
                            await interaction.followup.send(
                                f"{interaction.user.name} has no active character in this session!")
                        if character_info is not None:
                            true_name = character_info[0]
                            await db.close()
                            await player_leave_session(interaction.guild, session_id, interaction.user.name)
                            await interaction.followup.send(
                                f"{interaction.user.name}'s {true_name} has decided against participating in the session of '{session_info[0]}'!")
                    elif character_info is not None:
                        true_name = character_info[0]
                        await db.close()
                        await player_leave_session(interaction.guild, session_id, interaction.user.name)
                        await interaction.followup.send(
                            f"{interaction.user.name}'s {true_name} has decided against participating in the session of '{session_info[0]}'!")
        except aiosqlite.Error as e:
            logging.exception(f"Failed to remove player {interaction.user.name} from session {session_id} {e}")

    @sessions_group.command(name='display', description='Display all participants and signups for a session!')
    @app_commands.describe(
        group="Displaying All Participants & Signups, Active Participants Only, or Potential Sign-ups Only for a session")
    @app_commands.choices(group=[discord.app_commands.Choice(name='All', value=1),
                                 discord.app_commands.Choice(name='Participants', value=2),
                                 discord.app_commands.Choice(name='Sign-ups', value=3)])
    async def display(self, interaction: discord.Interaction, session_id: int,
                      group: discord.app_commands.Choice[int] = 1, page_number: int = 1):
        """ALL: THIS COMMAND DISPLAYS SESSION INFORMATION"""
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild.id}.sqlite") as conn:
                cursor = await conn.cursor()
                view_type = 0 if group == 1 else group.value - 1
                count = 0
                if view_type == 0 or view_type == 1:
                    await cursor.execute("SELECT COUNT(*) FROM Sessions_Participants WHERE Session_ID = ?",
                                         (session_id,))
                    participants_count = await cursor.fetchone()
                    count += 0 if not participants_count else participants_count[0]
                if view_type == 0 or view_type == 2:
                    cursor = await conn.execute("SELECT COUNT(*) FROM Sessions_Signups WHERE Session_ID = ?",
                                                (session_id,))
                    signups_count = await cursor.fetchone()
                    count += 0 if not signups_count else participants_count[0]
                max_items = count
                if max_items == 0:
                    await interaction.followup.send("No participants or signups found for this session!")
                    return
                else:
                    # Set up pagination variables
                    page_number = min(max(page_number, 1), math.ceil(max_items / 20))
                    items_per_page = 20 if view_type == 1 else 1
                    offset = (page_number - 1) * items_per_page

                    # Create and send the view with the results
                    view = gamemaster_commands.SessionDisplayView(
                        user_id=interaction.user.id,
                        guild_id=interaction.guild.id,
                        limit=items_per_page,
                        offset=offset,
                        view_type=view_type,
                        interaction=interaction,
                        session_id=session_id
                    )
                    await view.send_initial_message()
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"An error occurred whilst displaying session information: {e}")
            await interaction.followup.send(
                "An error occurred whilst displaying session information. Please try again later.")

    @sessions_group.command(name='report', description='Report on a session')
    @app_commands.describe(summary="This will use a Google Drive Link if available")
    @app_commands.autocomplete(session_id=shared_functions.player_session_autocomplete)
    @app_commands.autocomplete(character_name=shared_functions.own_character_select_autocompletion)
    async def report(self, interaction: discord.Interaction, session_id: int, summary: str, character_name: str):
        """Report on a session"""
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute(
                    "SELECT Session_ID, Session_Name, Article_Link, Article_ID, History_ID FROM Sessions WHERE Session_ID = ? AND IsActive = 0",
                    (session_id,))
                session_info = await cursor.fetchone()
                if session_info is None:
                    await interaction.followup.send(f"No completed Session with ID {session_id} could be found!")
                else:
                    (session_id, session_name, article_link, article_id, history_id) = session_info
                    await cursor.execute(
                        "SELECT Character_Name from Sessions_Archive where Session_ID = ? and Player_Name = ?",
                        (session_id, interaction.user.name))
                    character_info = await cursor.fetchone()
                    if character_info is None:
                        await interaction.followup.send(
                            f"Character {character_name} not found for player {interaction.user.name}")
                    else:
                        async with shared_functions.config_cache.lock:
                            configs = shared_functions.config_cache.cache.get(interaction.guild.id)
                            if configs:
                                world_id = configs.get('WA_World_ID')

                        if not world_id:
                            await interaction.followup.send("World ID not found!")
                        else:
                            await update_report(interaction.guild_id, summary, world_id, article_id, character_name,
                                                interaction.user.name)
                            await interaction.followup.send(f"Report has been updated for {session_name}!")
        except aiosqlite.Error as e:
            logging.exception(f"Failed to update report for session {session_id}: {e}")
            await interaction.followup.send(f"Failed to update report for session {session_id}")

    @group_group.command(name='create', description='create your group')
    @app_commands.autocomplete(character_name=shared_functions.own_character_select_autocompletion)
    async def create_group(self, interaction: discord.Interaction, character_name: str, group_name: str,
                           description: str):
        """Open a session Request"""
        await interaction.response.defer(thinking=True, ephemeral=False)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute("Select Group_ID, Role_ID from Sessions_Group where Player_Name = ?",
                                     (interaction.user.name,))
                group = await cursor.fetchone()
                await cursor.execute("Select Group_ID, Role_ID from Sessions_Group where Group_Name = ?",
                                     (group_name,))
                taken = await cursor.fetchone()
                if not group and not taken:
                    new_role = await create_new_group(interaction.guild, interaction.user.name, interaction.user.id,
                                                      group_name,
                                                      character_name, description)
                    await interaction.followup.send(
                        f"Group {group_name} has been created with the role <@&{new_role.id}>!")
                elif taken:
                    generated_name = random_name()
                    random_number = random.randint(0, 1000)
                    await interaction.followup.send(
                        f"Group name is taken :( Why don't you try {generated_name}{random_number}.")
                else:
                    await interaction.followup.send(
                        f"You already have a group request open! Please close it before opening another.")
        except (aiosqlite.Error, TypeError) as e:
            logging.exception(f"Failed to add a session request for {interaction.user.name}: {e}")
            await interaction.followup.send(f"Failed to add a session request for {interaction.user.name}")

    @group_group.command(name='delete', description='delete your group')
    async def delete_group(self, interaction: discord.Interaction):
        """Delete a session Request"""
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute("Select Group_ID, Role_ID from Sessions_Group where Player_Name = ?",
                                     (interaction.user.name,))
                group = await cursor.fetchone()
                if group:
                    await delete_group(interaction.guild, group[0], group[1])
                    await interaction.followup.send(f"Group {group[0]} has been deleted!")
                else:
                    await interaction.followup.send(f"Couldn't find any groups associated with {interaction.user}!")
        except (aiosqlite.Error, TypeError) as e:
            logging.exception(f"Failed to add a session request for {interaction.user.name}: {e}")
            await interaction.followup.send(f"Failed to add a session request for {interaction.user.name}")

    @group_group.command(name='join', description='Join a group')
    @app_commands.autocomplete(group_id=shared_functions.group_id_autocompletion)
    async def group_join(self, interaction: discord.Interaction, group_id: int):
        """Sync your Groups up for a GM to view whose in a session request group."""
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute("""
                Select
                SG.Group_Name, SG.Group_ID, SG.Role_ID, SG.Player_Name,
                PC.Player_ID 
                from Sessions_Group as SG 
                Left Join Player_Characters as PC 
                on SG.Player_Name = PC.Player_Name 
                where SG.Group_ID = ?
                """, (group_id,))
                group = await cursor.fetchone()
                if group:
                    (group_name, group_id, role_id, player_name, owner_id) = group
                    await cursor.execute(
                        "Select Group_ID, player_name from Sessions_Group_Presign where Group_ID = ? and Player_Name = ?",
                        (group_id, interaction.user.name))
                    previous_group = await cursor.fetchone()
                    if previous_group:
                        await interaction.followup.send(f"You have already joined group {group_id}!")
                    else:
                        await cursor.execute("SELECT Player_ID from Player_Characters WHERE Player_Name = ?", (interaction.user.name,))
                        player_id_info = await cursor.fetchone()
                        player_id = player_id_info[0]
                        view = GroupJoinView(
                            allowed_user_id=owner_id,
                            guild_id=interaction.guild.id,
                            group_id=group_id,
                            interaction=interaction,
                            bot=self.bot,
                            content=f"<@{owner_id}>\r\n<@{player_id}> has requested to join group {group_name}! Do you accept?",
                            group_name=group_name,
                            requester_name=interaction.user.name,
                            group_role_id=role_id
                        )
                        await view.send_initial_message()
                        await interaction.followup.send(
                            content=f"Group {group_name} has been requested to join by {interaction.user.name}!",
                            ephemeral=True)

                else:
                    await interaction.followup.send(f"Group {group_id} could not be found!")
        except (aiosqlite.Error, TypeError) as e:
            logging.exception(f"Failed to join a session request for {interaction.user.name}: {e}")
            await interaction.followup.send(
                f"Failed to Join a session request for {interaction.user.name} for group {group_id}")

    @group_group.command(name='leave', description='leave a group')
    @app_commands.autocomplete(group_id=shared_functions.group_id_autocompletion)
    async def group_leave(self, interaction: discord.Interaction, group_id: int):
        """leave a group because you hate everyone inside."""
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute("Select Group_ID, Role_ID from Sessions_Group where Group_ID = ?", (group_id,))
                group = await cursor.fetchone()
                if group:
                    await cursor.execute(
                        "Select Group_ID, player_name from Sessions_Group_Presign where Group_ID = ? and Player_Name = ?",
                        (group_id, interaction.user.name))
                    previous_group = await cursor.fetchone()
                    if previous_group:
                        try_leave = await leave_group(interaction.guild, interaction.user.name, interaction.user.id,
                                                      group_id, group[1])
                        if try_leave:
                            await interaction.followup.send(f"You have left group {group_id}!")
                        else:
                            await interaction.followup.send(f"Failed to leave group {group_id}!")
                    else:
                        await interaction.followup.send(f"You are not in group {group_id}!")
                else:
                    await interaction.followup.send(f"Group {group_id} could not be found!")
        except (aiosqlite.Error, TypeError) as e:
            logging.exception(f"Failed to add a session request for {interaction.user.name}: {e}")
            await interaction.followup.send(f"Failed to add a session request for {interaction.user.name}")

    @group_group.command(name='display', description='Display all participants and signups for a group!')
    @app_commands.autocomplete(group_id=shared_functions.group_id_autocompletion)
    async def display_groups(self, interaction: discord.Interaction, group_id: typing.Optional[int],
                             page_number: int = 1):
        """Display all participants and signups for a group"""
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild.id}.sqlite") as conn:
                cursor = await conn.cursor()
                if group_id is None:
                    await cursor.execute("SELECT COUNT(*) FROM sessions_group")
                    count = await cursor.fetchone()
                    max_items = count
                    if max_items == 0:
                        await interaction.followup.send("No groups found!")
                        return
                    else:
                        # Set up pagination variables
                        items_per_page = 20
                        page_number = min(max(page_number, 1), math.ceil(max_items[0] / 20))
                        offset = (page_number - 1) * items_per_page

                        # Create and send the view with the results
                        view = GroupView(
                            user_id=interaction.user.id,
                            guild_id=interaction.guild.id,
                            limit=items_per_page,
                            offset=offset,
                            interaction=interaction,
                            group_id=group_id
                        )
                        await view.send_initial_message()
                else:
                    await cursor.execute(
                        "SELECT Group_ID, Group_Name, Role_ID, Player_Name, Host_Character, Description FROM sessions_group WHERE Group_ID = ?",
                        (group_id,))
                    group_info = await cursor.fetchone()
                    if group_info is None:
                        await interaction.followup.send("No group found with that ID!")
                        return
                    else:
                        (group_id, group_name, role_id, player_name, host_character, description) = group_info
                        await cursor.execute("SELECT COUNT(*) FROM sessions_group_presign WHERE group_id = ?",
                                             (group_id,))
                        count = await cursor.fetchone()

                        max_items = count[0]
                        if max_items == 0:
                            await interaction.followup.send("No participants or signups found for this session!")
                            return
                        else:
                            # Set up pagination variables
                            items_per_page = 20
                            page_number = min(max(page_number, 1), math.ceil(max_items / 20))
                            offset = (page_number - 1) * items_per_page

                            # Create and send the view with the results
                            view = GroupManyView(
                                user_id=interaction.user.id,
                                guild_id=interaction.guild.id,
                                limit=items_per_page,
                                offset=offset,
                                interaction=interaction,
                                group_id=group_id,
                                group_name=group_name,
                                role_id=role_id,
                                host_player_name=player_name,
                                host_character=host_character,
                                description=description
                            )
                            await view.send_initial_message()
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"An error occurred whilst displaying session information: {e}")
            await interaction.followup.send(
                "An error occurred whilst displaying session information. Please try again later.")

    @timesheet_group.command(name="set", description="Set your availability for a day of the week")
    @app_commands.choices(change=[discord.app_commands.Choice(name='Add Time', value=1),
                                  discord.app_commands.Choice(name='Remove Time', value=2),
                                  discord.app_commands.Choice(name='Update Time-Zone', value=3),
                                  discord.app_commands.Choice(name='Clear All Availability', value=4)])
    async def timesheet_creation(self, interaction: discord.Interaction,
                                 change: typing.Optional[discord.app_commands.Choice[int]]):
        await interaction.response.defer(thinking=True, ephemeral=True)
        change_value = 1 if change is None else change.value
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild.id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute(
                    "SELECT Distinct(UTC_Offset), COUNT(*) FROM Player_Timecard WHERE Player_Name = ? Group by UTC_Offset",
                    (interaction.user.name,))
                timesheet_info = await cursor.fetchone()
                if change_value == 4:
                    # Clear all availability by deleting and remaking all timesheets
                    timesheet_clear = await clear_timesheet(interaction.guild.id, interaction.user.name)
                    if not timesheet_clear:
                        await interaction.followup.send(f"Failed to clear timesheet for {interaction.user.name}!")
                        return
                    timesheet_build = await build_timesheet(interaction.guild.id, interaction.user.name)
                    if not timesheet_build:
                        await interaction.followup.send(f"Failed to build timesheet for {interaction.user.name}!")
                        return
                    await interaction.followup.send(f"Timesheet has been cleared for {interaction.user.name}!")
                else:
                    if not timesheet_info:
                        # If the user has no timesheet, build one
                        await build_timesheet(interaction.guild.id, interaction.user.name)
                    elif timesheet_info[1] != 7:
                        # If the user has a timesheet, but it's somehow incomplete, delete and rebuild it
                        await clear_timesheet(interaction.guild.id, interaction.user.name)
                        await build_timesheet(interaction.guild.id, interaction.user.name)
                    if change_value == 3:
                        # If the user has no timezone set, or is updating their timezone, prompt them to set it
                        view = AvailabilityView(timezone=None, prompt_day_update=True)
                    elif change_value == 1 and not timesheet_info:
                        # If the user has no timezone set, prompt them to set it
                        view = AvailabilityView(timezone=None)
                    elif change_value == 1 and not timesheet_info[0]:
                        # If the user has no timezone set, prompt them to set it
                        view = AvailabilityView(timezone=None)
                    elif change_value == 1 and timesheet_info[0]:
                        # If the user has a timezone set, prompt them to set their availability
                        view = AvailabilityView(timezone=timesheet_info[0])
                    elif change_value == 2 and (not timesheet_info[0] or not timesheet_info):
                        await interaction.followup.send("You have no availability to remove!")
                        return
                    elif change_value == 2 and timesheet_info[0]:
                        view = UnavailabilityView(timezone=timesheet_info[0])

            await interaction.followup.send(content="Start by using the dropdown below!", view=view)
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"An error occurred whilst handling timesheet!: {e}")
            await interaction.followup.send(
                "An error occurred whilst handling timesheet. Please try again later.")

    @timesheet_group.command(name="timezone", description="Set your timezone for availability")
    @app_commands.autocomplete(timezone=search_timezones)
    async def set_timezone(self, interaction: discord.Interaction, timezone: str):
        """Set your timezone for availability"""
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            async with aiosqlite.connect(f"pathparser_{interaction.guild.id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute(
                    "SELECT Distinct(UTC_Offset), COUNT(*) FROM Player_Timecard WHERE Player_Name = ? Group by UTC_Offset",
                    (interaction.user.name,))
                timesheet_info = await cursor.fetchone()
                if not timesheet_info:
                    # If the user has no timesheet, build one
                    await build_timesheet(interaction.guild.id, interaction.user.name)
                elif timesheet_info[1] != 7:
                    # If the user has a timesheet, but it's somehow incomplete, delete and rebuild it
                    await clear_timesheet(interaction.guild.id, interaction.user.name)
                    await build_timesheet(interaction.guild.id, interaction.user.name)
                view = AvailabilityView(timezone=timezone, prompt_day_update=True)
                await interaction.followup.send(
                    content="Timezone has been manually set. Would you like to make any other changes?", view=view)
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"An error occurred whilst handling timesheet!: {e}")
            await interaction.followup.send(
                "An error occurred whilst handling timesheet. Please try again later.")

    @timesheet_group.command(name="availability", description="Display availability for a day of the week")
    @app_commands.choices(
        day=[discord.app_commands.Choice(name='Monday', value=1), discord.app_commands.Choice(name='Tuesday', value=2),
             discord.app_commands.Choice(name='Wednesday', value=3),
             discord.app_commands.Choice(name='Thursday', value=4),
             discord.app_commands.Choice(name='Friday', value=5), discord.app_commands.Choice(name='Saturday', value=6),
             discord.app_commands.Choice(name='Sunday', value=7)])
    async def availability(self, interaction: discord.Interaction, player: discord.Member,
                           day: discord.app_commands.Choice[int]):
        """Display historical Session Requests"""

        guild_id = interaction.guild.id
        day_value = day.value
        await interaction.response.defer(thinking=True, ephemeral=True)
        if day_value < 1 or day_value > 7:
            embed = discord.Embed(title=f"Day Error", description=f'{day} is not a valid day of the week!',
                                  colour=discord.Colour.red())
            await interaction.followup.send(embed=embed)
        else:
            player = interaction.user.name if player is None else player.name
            async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
                cursor = await db.cursor()
                await cursor.execute("Select UTC_Offset from Player_Timecard where Player_Name = ?",
                                     (interaction.user.name,))
                host_utc_offset = await cursor.fetchone()
                await cursor.execute("Select UTC_Offset from Player_Timecard where Player_Name = ?", (player,))
                player_utc_offset = await cursor.fetchone()
                utc_offset = host_utc_offset[0] if host_utc_offset is not None else 'Universal'
                if player_utc_offset is not None:
                    await create_timecard_plot(guild_id, player, day_value, utc_offset)
                    with open('C:\\pathparser\\plots\\timecard_plot.png', 'rb') as f:
                        picture = discord.File(f)
                        await interaction.followup.send(
                            f"Here's the availability chart for {player} on {day.name}:",
                            file=picture)
                else:
                    embed = discord.Embed(title=f"Player Error",
                                          description=f'{player} did not have a valid timecard!!',
                                          colour=discord.Colour.red())
                    await interaction.followup.send(embed=embed)

    @timesheet_group.command(name="group",
                             description="Display availability for a group or groups on a day of the week")
    @app_commands.choices(
        day=[discord.app_commands.Choice(name='Monday', value=1), discord.app_commands.Choice(name='Tuesday', value=2),
             discord.app_commands.Choice(name='Wednesday', value=3),
             discord.app_commands.Choice(name='Thursday', value=4),
             discord.app_commands.Choice(name='Friday', value=5), discord.app_commands.Choice(name='Saturday', value=6),
             discord.app_commands.Choice(name='Sunday', value=7)])
    async def group_availability(self, interaction: discord.Interaction, group_id: typing.Optional[int],
                                 day: discord.app_commands.Choice[int]):
        """Display historical Session Requests"""
        guild_id = interaction.guild.id
        day_value = day.value
        try:
            await interaction.response.defer(thinking=True, ephemeral=True)
            if day_value < 1 or day_value > 7:
                embed = discord.Embed(title=f"Day Error", description=f'{day} is not a valid day of the week!',
                                      colour=discord.Colour.red())
                await interaction.followup.send(embed=embed)
            else:
                async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
                    cursor = await db.cursor()
                    await cursor.execute(
                        "Select UTC_Offset from Player_Timecard where Player_Name = ?",
                        (interaction.user.name,))
                    host_utc_offset = await cursor.fetchone()
                    view = DisplayGroupTimesheet(
                        guild_id=guild_id,
                        group_id=group_id,
                        day=day_value,
                        utc_offset=host_utc_offset[0],
                        interaction=interaction,
                        user_id=interaction.user.id)
                    await view.send_initial_message()
        except (aiosqlite.Error, TypeError, ValueError) as e:
            logging.exception(f"An error occurred whilst handling timesheet!: {e}")
            await interaction.followup.send(
                "An error occurred whilst handling timesheet. Please try again later.")


class GroupManyView(shared_functions.ShopView):
    def __init__(self, user_id: int, guild_id: int, offset: int, limit: int, group_id: typing.Optional[int],
                 group_name: str, host_player_name: str, host_character: str, description: str, role_id: int,
                 interaction: discord.Interaction):
        super().__init__(user_id=user_id, guild_id=guild_id, offset=offset, limit=limit, interaction=interaction,
                         content="")
        self.max_items = None  # Cache total number of items
        self.content = None
        self.group_id = group_id
        self.group_name = group_name
        self.host_player_name = host_player_name
        self.host_character = host_character
        self.description = description
        self.role_id = role_id

    async def update_results(self):
        """Fetch the history of prestige request  for the current page."""

        statement = """
                        SELECT Group_ID, Player_Name
                        FROM Sessions_Group_Presign
                        WHERE Group_ID = ? ORDER BY Player_Name Limit ? Offset ? 
                    """
        async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
            cursor = await db.execute(statement, (self.group_id, self.limit, self.offset))
            self.results = await cursor.fetchall()

    async def create_embed(self):
        """Create the embed for the titles."""
        current_page = (self.offset // self.limit) + 1
        total_pages = ((await self.get_max_items() - 1) // self.limit) + 1
        self.embed = discord.Embed(
            title=f"Group: {self.group_id}: {self.group_name} hosted by {self.host_player_name}'s {self.host_character}",
            description=f"Page {current_page} of {total_pages}")
        self.embed.set_footer(text=f"Group <@{self.role_id}> Description: {self.description}")
        for item in self.results:
            (group_id, player_name) = item
            self.embed.add_field(name=f'**Player**: {player_name}', value=f'**Group**: {group_id}', inline=False)

    async def get_max_items(self):
        """Get the total number of titles."""
        if self.max_items is None:
            async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
                cursor = await db.execute("SELECT COUNT(*) FROM Sessions_Group_Presign WHERE Group_ID = ?",
                                          (self.group_id,))
                count = await cursor.fetchone()
                self.max_items = count[0]
        return self.max_items


class GroupView(shared_functions.ShopView):
    def __init__(self, user_id: int, guild_id: int, offset: int, limit: int, group_id: typing.Optional[int],
                 interaction: discord.Interaction):
        super().__init__(user_id=user_id, guild_id=guild_id, offset=offset, limit=limit, interaction=interaction,
                         content=None)
        self.max_items = None  # Cache total number of items
        self.content = None
        self.group_id = group_id

    async def update_results(self):
        """Fetch the history of prestige request  for the current page."""

        statement = """
                        SELECT Group_ID, Group_Name, Role_ID, Player_Name, Host_Character, Description
                        FROM Sessions_Group Order by Group_ID Limit ? Offset ? 
                    """
        async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
            cursor = await db.execute(statement, (self.group_id, self.limit, self.offset))
            self.results = await cursor.fetchall()

    async def create_embed(self):
        """Create the embed for the titles."""
        current_page = (self.offset // self.limit) + 1
        total_pages = ((await self.get_max_items() - 1) // self.limit) + 1
        self.embed = discord.Embed(
            title=f"Group Requests",
            description=f"Page {current_page} of {total_pages}")
        for item in self.results:
            (group_id, group_name, role_id, host_player_name, host_character, description) = item
            self.embed.add_field(name=f'**Group**: {group_id}: {group_name} Role: <@{role_id}>',
                                 value=f'**Host**: {host_player_name}, **Character**: {host_character}\r\n**Description**: {description}',
                                 inline=False)

    async def get_max_items(self):
        """Get the total number of titles."""
        if self.max_items is None:
            async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
                cursor = await db.execute("SELECT COUNT(*) FROM Sessions_Group",
                                          (self.group_id,))
                count = await cursor.fetchone()
                self.max_items = count[0]
        return self.max_items


class DisplayGroupTimesheet(discord.ui.View):
    """Base class for shop views with pagination."""

    def __init__(
            self,
            user_id: int,
            guild_id: int,
            group_id: typing.Optional[int],
            day: int,
            utc_offset: str,
            interaction: discord.Interaction):
        super().__init__(timeout=180)
        self.range_id = None
        self.user_id = user_id
        self.guild_id = guild_id
        self.group_id = group_id
        self.day = day
        self.view_type = 1
        self.message = None
        self.interaction = interaction
        self.results = []
        self.host_results = []
        self.all_results = []
        self.embed = None
        self.max_range_id = 0
        self.utc_offset = utc_offset
        self.user_id = interaction.user.id

        # Initialize buttons
        self.first_page_button = discord.ui.Button(label='First Page', style=discord.ButtonStyle.primary)
        self.previous_page_button = discord.ui.Button(label='Previous Page', style=discord.ButtonStyle.primary)
        self.change_view_button = discord.ui.Button(label='Change View', style=discord.ButtonStyle.primary)
        self.next_page_button = discord.ui.Button(label='Next Page', style=discord.ButtonStyle.primary)
        self.last_page_button = discord.ui.Button(label='Last Page', style=discord.ButtonStyle.primary)

        self.first_page_button.callback = self.first_page
        self.previous_page_button.callback = self.previous_page
        self.change_view_button.callback = self.change_view
        self.next_page_button.callback = self.next_page
        self.last_page_button.callback = self.last_page

        self.add_item(self.first_page_button)
        self.add_item(self.previous_page_button)
        self.add_item(self.change_view_button)
        self.add_item(self.next_page_button)
        self.add_item(self.last_page_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Ensure that only the user who initiated the view can interact with the buttons."""
        try:
            if interaction.user.id != self.user_id:
                await interaction.response.send_message(
                    "You cannot interact with this button.",
                    ephemeral=True
                )
                return False
            return True
        except Exception as e:
            logging.error(f"Failed to check interaction: {e}")
            raise

    async def first_page(self, interaction: discord.Interaction):
        """Handle moving to the first page."""
        try:
            await interaction.response.defer()
            if self.view_type == 0:
                if self.day == 1:
                    await interaction.followup.send("You are on the first page.", ephemeral=True)
                    return
                else:
                    self.day = 1
            else:
                if self.range_id == 0:
                    await interaction.followup.send("You are on the first page.", ephemeral=True)
                    return
                else:
                    self.range_id = 0
            await self.update_results()
            await self.create_embed()
            await self.update_buttons()
            await interaction.message.edit(
                embed=self.embed,
                view=self
            )
            with open(f'C:\\pathparser\\pathparser\\plots\\timecard_{self.user_id}_plot.png', 'rb') as f:
                picture = discord.File(f)
                await interaction.followup.send(file=picture, ephemeral=True)
        except Exception as e:
            logging.error(f"Failed to move to the first page: {e}")
            raise

    async def previous_page(self, interaction: discord.Interaction):
        """Handle moving to the previous page."""
        try:
            await interaction.response.defer()
            if self.view_type == 0:
                if self.day == 1:
                    await interaction.followup.send("You are on the first page.", ephemeral=True)
                    return
                else:
                    self.day -= 1
            else:
                if self.range_id == 0:
                    await interaction.followup.send("You are on the first page.", ephemeral=True)
                    return
                else:
                    self.range_id -= 1
            await self.update_results()
            await self.create_embed()
            await self.update_buttons()
            await interaction.message.edit(
                embed=self.embed,
                view=self
            )
            with open(f'C:\\pathparser\\pathparser\\plots\\timecard_{self.user_id}_plot.png', 'rb') as f:
                picture = discord.File(f)
                await interaction.followup.send(file=picture, ephemeral=True)
        except Exception as e:
            logging.error(f"Failed to move to the previous page: {e}")
            raise

    async def send_initial_message(self):
        """Send the initial message with the view."""
        try:

            await self.update_results()
            await self.create_embed()
            await self.update_buttons()
            with open(f'C:\\pathparser\\pathparser\\plots\\timecard_{self.user_id}_plot.png', 'rb') as f:
                picture = discord.File(f)
            self.message = await self.interaction.followup.send(
                embed=self.embed,
                view=self, file=picture, ephemeral=True
            )

        except discord.HTTPException as e:
            logging.error(
                f"Failed to send message due to HTTPException: {e} in guild {self.interaction.guild.id} for {self.user_id}")
        except Exception as e:
            logging.error(f"Failed to send message: {e} in guild {self.interaction.guild.id} for {self.user_id}")

    async def on_timeout(self):
        """Disable buttons when the view times out."""
        try:
            os.remove(f'C:\\pathparser\\pathparser\\plots\\timecard_{self.user_id}_plot.png')
            for child in self.children:
                child.disabled = True
            if self.message:
                await self.message.edit(view=self)
        except Exception as e:
            logging.error(f"Failed to disable buttons: {e}")
            raise

    async def change_view(self, interaction: discord.Interaction):
        """Change the view type."""
        await interaction.response.defer()
        try:
            self.view_type = 1 if self.view_type == 0 else 0
            await self.update_results()
            await self.create_embed()
            await self.update_buttons()
            await interaction.message.edit(
                embed=self.embed,
                view=self
            )
        except Exception as e:
            logging.error(f"Failed to change view: {e}")
            raise

    async def next_page(self, interaction: discord.Interaction):
        """Handle moving to the next page."""
        try:
            await interaction.response.defer()
            if self.view_type == 0:
                if self.day == 7:
                    await interaction.followup.send("You are on the last page.", ephemeral=True)
                    return
                else:
                    self.day += 1
            else:
                if self.range_id == self.max_range_id:
                    await interaction.followup.send("You are on the first page.", ephemeral=True)
                    return
                else:
                    self.range_id += 1
            await self.update_results()
            await self.create_embed()
            await self.update_buttons()
            await interaction.message.edit(
                embed=self.embed,
                view=self
            )
            with open(f'C:\\pathparser\\plots\\timecard_{self.user_id}_plot.png', 'rb') as f:
                picture = discord.File(f)
                await interaction.followup.send(file=picture, ephemeral=True)
        except Exception as e:
            logging.error(f"Failed to move to the next page: {e}")
            raise

    async def last_page(self, interaction: discord.Interaction):
        """Handle moving to the last page."""
        try:
            await interaction.response.defer()
            if self.view_type == 0:
                if self.day == 7:
                    await interaction.followup.send("You are on the last page.", ephemeral=True)
                    return
                else:
                    self.day = 7
            else:
                if self.range_id == self.max_range_id:
                    await interaction.followup.send("You are on the first page.", ephemeral=True)
                    return
                else:
                    self.range_id = self.max_range_id
            await self.update_results()
            await self.create_embed()
            await self.update_buttons()
            await interaction.message.edit(
                embed=self.embed,
                view=self
            )
            with open(f'C:\\pathparser\\pathparser\\plots\\timecard_{self.user_id}_plot.png', 'rb') as f:
                picture = discord.File(f)
                await interaction.followup.send(file=picture, ephemeral=True)
        except Exception as e:
            logging.error(f"Failed to move to the last page: {e}")
            raise

    async def update_buttons(self):
        """Update the enabled/disabled state of buttons based on the current page."""
        try:

            await self.get_max_items()

            if self.view_type == 0:
                first_page = 1
                last_page = 7
            else:
                first_page = 0
                last_page = self.max_range_id

            self.first_page_button.disabled = first_page
            self.previous_page_button.disabled = first_page
            self.next_page_button.disabled = last_page
            self.last_page_button.disabled = last_page
        except Exception as e:
            logging.error(f"Failed to update buttons: {e}")
            raise

    async def update_results(self):
        """Fetch the results for the current page."""
        try:
            async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
                cursor = await db.cursor()
                # Fetch all group data
                await cursor.execute(
                    """SELECT Group_ID, Player_Name, Group_Name, Host_Character, Role_ID, Description 
                       FROM Sessions_Group 
                       ORDER BY Group_ID ASC"""
                )
                self.all_results = await cursor.fetchall()

                if self.group_id:
                    # Find the index of the group_id in the all_results list
                    self.range_id = next(
                        (index for index, row in enumerate(self.all_results) if row[0] == self.group_id),
                        None
                    )
                    if self.range_id is None:
                        raise ValueError(f"Group ID {self.group_id} not found in the results.")

                    self.host_results = self.all_results[self.range_id]
                    await cursor.execute(
                        """SELECT Player_Name FROM Sessions_Group_Presign WHERE Group_ID = ?""",
                        (self.group_id,)
                    )
                    self.results = await cursor.fetchall()
                else:
                    # Default to the first group
                    self.range_id = 0
                    self.host_results = self.all_results[self.range_id]
                    await cursor.execute(
                        """SELECT Player_Name FROM Sessions_Group_Presign WHERE Group_ID = ?""",
                        (self.host_results[0],)
                    )
                    self.results = await cursor.fetchall()
        except Exception as e:
            logging.error(f"Failed to update results: {e}")
            raise

    async def create_embed(self):
        """Create the embed for the current page. To be implemented in subclasses."""
        try:

            results_tuple = []
            for result in self.results:
                results_tuple.append(result[0])
            await create_timecard_group_plot(
                guild_id=self.guild_id,
                day=self.day,
                group_info=results_tuple,
                user_id=self.user_id,
                utc_offset=self.utc_offset,
                group_name=self.host_results[2]
            )
            (group_id, player_name, group_name, host_character, role_id, description) = self.host_results
            embed = discord.Embed(
                title=f"Group {group_id}: {group_name}",
                description=f"Hosted by {player_name}'s {host_character}",
                colour=discord.Colour.blurple()
            )
            embed.add_field(name=f"Group Description", value=f"{description}", inline=False)
            embed.set_footer(text=f"group {self.range_id + 1} of {self.max_range_id + 1}")
        except Exception as e:
            logging.error(f"Failed to create embed: {e}")

    async def get_max_items(self):
        """Get the total number of items. To be implemented in subclasses."""

        async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute("SELECT COUNT(*) FROM Sessions_Group""")
            count = await cursor.fetchone()

            self.max_range_id = count[0]
            return self.max_range_id




class GroupJoinView(shared_functions.RecipientAcknowledgementView):
    def __init__(
            self,
            allowed_user_id: int,
            requester_name: str,
            bot: commands.Bot,
            guild_id: int,
            interaction: discord.Interaction,
            group_id: int,
            group_name: str,
            group_role_id: int,
            content: str
    ):
        super().__init__(allowed_user_id=allowed_user_id, interaction=interaction, content=content)
        self.guild_id = guild_id
        self.requester_name = requester_name
        self.allowed_user_id = allowed_user_id
        self.bot = bot
        self.group_id = group_id
        self.group_name = group_name
        self.group_role_id = group_role_id
        self.interaction = interaction


    async def accepted(self, interaction: discord.Interaction):
        """Handle the approval logic."""
        # Update the database to mark the proposition as accepted
        # Adjust prestige, log the transaction, notify the requester, etc.
        self.embed = discord.Embed(
            title="Group Join Accepted!",
            description=f"<@{self.allowed_user_id}> has allowed <@{self.interaction.user.id}> to join their session!.",
            color=discord.Color.green()
        )
        # Additional logic such as notifying the requester
        async with aiosqlite.connect(f"pathparser_{self.guild_id}.sqlite") as conn:
            cursor = await conn.cursor()
            await cursor.execute(
                "INSERT INTO Sessions_Group_Presign (Group_ID, Player_Name) VALUES (?, ?)",
                (self.group_id, self.interaction.user.name)
            )
            await conn.commit()
            group_role = interaction.guild.get_role(self.group_role_id)
            await self.interaction.user.add_roles(group_role)

    async def rejected(self, interaction: discord.Interaction):
        """Handle the rejection logic."""
        # Update the database to mark the proposition as rejected

        self.embed = discord.Embed(
            title="Group Application Rejected",
            description=f"The owner of this group did not desire you in their cohort.",
            color=discord.Color.red()
        )
        # Additional logic such as notifying the requester

    async def create_embed(self):
        """Create the initial embed for the proposition."""
        self.embed = discord.Embed(
            title=f"Group Join Request \r\nGroup Name: {self.group_name}",
            description=(
                f"**Requester:** {self.requester_name}\n"
            ),
            color=discord.Color.blue()
        )