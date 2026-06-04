from datetime import datetime, timedelta, timezone
import logging
from dateutil import parser
from zoneinfo import ZoneInfo
import re
import aiosqlite
import numpy as np
import pytz
import matplotlib.pyplot as plt
import os
from typing import Union, Tuple, Optional, List

def get_next_weekday(weekday):
    """Return the date of the next specified weekday (0=Monday, 6=Sunday)."""
    today = datetime.now().date()
    days_ahead = weekday - today.weekday()
    if days_ahead <= 0:
        days_ahead += 7
    return today + timedelta(days=days_ahead)


def parse_time_input(time_str):
    """Parse time input in various formats and return a time object."""
    try:
        # Use dateutil.parser to parse the time string
        dt = parser.parse(time_str, fuzzy=True)
        return dt.time()
    except (parser.ParserError, ValueError):
        return None

def get_utc_offset(tz):
    try:
        # Get the current time for the timezone
        tzinfo = ZoneInfo(tz)
        now_utc = datetime.now(timezone.utc)
        now_tz = now_utc.astimezone(tzinfo)
        # Get the offset in hours and minutes
        offset_seconds = now_tz.utcoffset().total_seconds()
        offset_hours = int(offset_seconds // 3600)
        offset_minutes = int((offset_seconds % 3600) // 60)
        # Format the offset as "+HH:MM" or "-HH:MM"
        return f"{offset_hours:+03}:{offset_minutes:02}"
    except Exception as e:
        logging.exception(f"An error occurred whilst getting UTC offset for timezone '{tz}': {e}")
        return "+00:00"  # Return UTC if the timezone is invalid or there's an error


def time_to_minutes(t):
    pattern = r'^(?P<sign>[+-]?)(?P<hours>\d{1,2}):(?P<minutes>\d{2})$'
    match = re.match(pattern, t)
    if not match:
        logging.error(f"Invalid time format: {t}")
        return 0  # Or raise an exception

    sign = -1 if match.group('sign') == '-' else 1
    hours = int(match.group('hours'))
    minutes = int(match.group('minutes'))
    total_minutes = sign * (hours * 60 + minutes)
    return total_minutes


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
            # Fetch the player's timezone from the database. utc_offset arg here is expected to be a string timezone name for complex logic, or 0 if UTC.
            if utc_offset == 0 or utc_offset == "0" or utc_offset == "+00:00":
                 # Fetch the player's timecard data for the specified day, they're in UTC so the UTEasy.
                joined_labels = ', '.join([f'"{label}"' for label in time_labels])
                await cursor.execute(f"SELECT {joined_labels} FROM Player_Timecard WHERE Player_Name = ? AND Day = ?",
                                     (player_name, day))
                row = await cursor.fetchone()
            else:
                # get next instance of day occurring
                start_time = datetime.now(tz=pytz.utc)
                days_ahead = day - start_time.weekday() if day - start_time.weekday() >= 0 else 7 + day - start_time.weekday()
                start_time = start_time + timedelta(days=days_ahead)

                # get the start and end of the day
                day_start_start_time = datetime.combine(start_time.date(), datetime.min.time())
                day_end_start_time = datetime.combine(start_time.date(), datetime.max.time())

                # adjust the hour and minute of the day start and end to the player's timezone
                try:
                    if isinstance(utc_offset, str):
                        target_tz = pytz.timezone(utc_offset)
                    else:
                        # Fallback if it was passed as minutes int (old generic logic), but here we need timezone for astimezone logic
                        # If passed as int minutes, this logic fails. Assuming str based on player_commands source.
                        logging.error(f"fetch_timecard_data_from_db expected timezone string but got {type(utc_offset)}: {utc_offset}")
                        return None
                        
                    day_start_timezone = day_start_start_time.astimezone(target_tz)
                    day_end_timezone = day_end_start_time.astimezone(target_tz)
                    
                    day_start_timezone = day_start_timezone - timedelta(
                        minutes=day_start_timezone.utcoffset().total_seconds() / 60)
                    day_end_timezone = day_end_timezone - timedelta(
                        minutes=day_end_timezone.utcoffset().total_seconds() / 60)
                except Exception as e:
                    logging.error(f"Error calculating timezone offsets: {e}")
                    return None

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
        return None


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
            
            offset_val = 0
            if isinstance(utc_offset_time, str):
                if utc_offset_time == "+00:00" or utc_offset_time == "0":
                    offset_val = 0
                else:
                    offset_val = 1
            
            if offset_val == 0:
                # Fetch the player's timecard data for the specified day, they're in UTC so the UTEasy.
                joined_labels.extend([f'"SUM({label})"' for label in time_labels])
                joined_labels = ', '.join(joined_labels)
                sql_statement = f"SELECT {joined_labels} FROM Player_Timecard WHERE Player_Name in ({select_list}) AND Day = ?"

                await cursor.execute(sql_statement,
                                     (player_list, day))
                row = await cursor.fetchone()
            else:
                # get next instance of day occurring
                start_time = datetime.now(tz=pytz.utc)
                days_ahead = day - start_time.weekday() if day - start_time.weekday() >= 0 else 7 + day - start_time.weekday()
                start_time = start_time + timedelta(days=days_ahead)

                # get the start and end of the day
                day_start_start_time = datetime.combine(start_time.date(), datetime.min.time())
                day_end_start_time = datetime.combine(start_time.date(), datetime.max.time())

                # adjust the hour and minute of the day start and end to the player's timezone
                try:
                     target_tz = pytz.timezone(utc_offset)
                     day_start_timezone = day_start_start_time.astimezone(target_tz)
                     day_end_timezone = day_end_start_time.astimezone(target_tz)
                     day_start_timezone = day_start_timezone - timedelta(
                         minutes=day_start_timezone.utcoffset().total_seconds() / 60)
                     day_end_timezone = day_end_timezone - timedelta(
                         minutes=day_end_timezone.utcoffset().total_seconds() / 60)
                except Exception as e:
                     logging.error(f"Error calculating timezone offsets in group: {e}")
                     return None

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
        return None

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
            row = await fetch_timecard_data_from_db(guild_id, player[2], day, utc_offset)
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

def convert_to_unix(military_time: str, timezone_str: str) -> str:
    # Ensure military_time is in HH:MM format
    if len(military_time) != 5 or ':' not in military_time:
        return "Invalid military time format. Please provide time as HH:MM."

    # Parse the military time into hours and minutes
    hours, minutes = map(int, military_time.split(':'))

    # Get the current date and combine it with the provided time
    current_date = datetime.now().date()
    time_combined = datetime(current_date.year, current_date.month, current_date.day, hours, minutes)

    # Convert to the given timezone
    try:
        timezone_info = pytz.timezone(timezone_str)
        localized_time = timezone_info.localize(time_combined)
        unix_timestamp = int(localized_time.timestamp())
        return f"<t:{unix_timestamp}:t>"
    except Exception as e:
        return f"Error: {e}"


def adjust_day(day, hours, utc_offset):
    logging.debug(f"Adjusting day {day} with hours {hours} and UTC offset {utc_offset}")
    adjusted_day = day + (1 if int(hours) - int(utc_offset) >= 24 else -1 if int(hours) - int(utc_offset) <= 0 else 0)
    return ((adjusted_day - 1) % 7) + 1

def parse_hammer_time_to_iso(hammer_time_str: str) -> datetime:
    return datetime.fromtimestamp(int(hammer_time_str), tz=timezone.utc)

def parse_hammer_time_to_timestamp(hammer_time_str: str) -> datetime:
    return datetime.fromisoformat(hammer_time_str)

def validate_hammertime(timestamp_str):
    try:
        now = int(datetime.now().timestamp())
        if len(timestamp_str) == 16:
            timestamp_str = timestamp_str[3:13]

        # Define acceptable time range (e.g., within the next 5 years)
        five_years_earlier = now - (5 * 365 * 24 * 60 * 60)
        timestamp = int(timestamp_str)
        if five_years_earlier < timestamp < now:
            return False, False, "The time you provided is in the past."
        elif timestamp < five_years_earlier:
            # Handle special cases like "99 years ago"
            return True, False, ("Special Date", None, "Arrival", "Hammer Time")
        else:
            # Time is acceptable
            date = f"<t:{timestamp}:D>"  # Long date
            time_hhmm = f"<t:{timestamp}:t>"  # Long time
            arrival = f"<t:{timestamp}:R>"  # Relative time
            hammer_time_stamp = timestamp_str  # Keep the timestamp string if needed

            return True, True, (date, time_hhmm, arrival, hammer_time_stamp)
    except ValueError:
        return False, False, "Invalid timestamp format. Please provide a valid timestamp."

def convert_datetime_to_unix(time_str, timezone_str):
    # Define possible date formats
    formats = ["%m/%d/%Y %I:%M %p", "%m/%d/%Y %H:%M"]
    for fmt in formats:
        try:
            # Parse the date with the given format
            dt = datetime.strptime(time_str, fmt)
            break
        except ValueError:
            continue
    else:
        raise ValueError("Time format not recognized.")

    # Localize the datetime to the specified timezone
    tz = pytz.timezone(timezone_str)
    dt = tz.localize(dt)

    # Convert to Unix timestamp
    unix_time = int(dt.timestamp())
    return unix_time

async def complex_validate_hammertime(
        guild_id,
        author_name,
        hammertime: Union[str, datetime]) -> Union[
    Tuple[bool, Tuple[bool, bool, Tuple[str, str, str, str]]], Tuple[bool, str]]:
    try:
        # Attempt to retrieve the user's timezone
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute(
                "SELECT UTC_Offset FROM Player_Timecard WHERE Player_Name = ?", (author_name,)
            )
            utc_result = await cursor.fetchone()

        if not utc_result:
            # Player not found, attempt to validate hammertime directly
            return False, "Player not found in the database."

        (utc_offset,) = utc_result
        if utc_offset:
            # If utc_offset is "+00:00" string or similar, we need to handle it.
            # get_utc_offset returns string like "+00:00".
            # Here we might expect something else or we can parse it.
            # Assuming it's a timezone string or we can use gettz.
            # In time_utils, get_utc_offset takes 'tz' (timezone string like 'America/New_York') and returns offset string.
            # The DB likely stores the timezone name (e.g. 'America/New_York') or offset?
            # From shared_functions 1764: user_timezone = tz.gettz(utc_offset) -> uses dateutil.tz
            # So import tz from dateutil
            from dateutil import tz
            user_timezone = tz.gettz(utc_offset)

        # Check if hammertime is a Unix timestamp
        if isinstance(hammertime, str) and hammertime.isdigit():
            timestamp = int(hammertime)
            # Convert timestamp to datetime in user's timezone
            parsed_time = datetime.fromtimestamp(timestamp, tz=user_timezone)
        else:
            # Attempt to parse the input time
            parsed_time = parser.parse(hammertime, fuzzy=True, default=datetime.now(tz=user_timezone))
            # Ensure the parsed time is timezone-aware
            if parsed_time.tzinfo is None:
                parsed_time = parsed_time.replace(tzinfo=user_timezone)

        # If the time has already passed, adjust to the next day
        now = datetime.now(tz=user_timezone)
        if parsed_time < now:
            parsed_time += timedelta(days=1)

        # Convert to Unix timestamp
        create_timestamp = int(parsed_time.timestamp())

        # Validate the hammertime
        hammertime_result = validate_hammertime(str(create_timestamp))

        return True, hammertime_result

    except Exception as e:
        logging.exception(f"Error validating hammertime '{hammertime}': {e}")
        # Attempt to validate hammertime directly
        if isinstance(hammertime, str):
             hammertime_result = validate_hammertime(hammertime)
             return True, hammertime_result
        return False, str(e)


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

