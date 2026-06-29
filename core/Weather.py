from collections import defaultdict

import aiohttp
import aiosqlite
from pycountry import db

async def get_weather(latitude: float, longitude: float):
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={latitude}"
        f"&longitude={longitude}"
        "&daily="
        "temperature_2m_max,"
        "temperature_2m_min,"
        "wind_speed_10m_mean,"
        "precipitation_probability_max,"
        "weather_code,"
        "cloud_cover_mean"
        "&hourly=relative_humidity_2m"
        "&forecast_days=7"
        "&temperature_unit=fahrenheit"
        "&wind_speed_unit=mph"
        "&timezone=auto"
    )

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            response.raise_for_status()
            data = await response.json()

    daily = data["daily"]

    # Calculate daily average humidity
    humidity_by_day = defaultdict(list)

    for timestamp, humidity in zip(
        data["hourly"]["time"],
        data["hourly"]["relative_humidity_2m"]
    ):
        date = timestamp.split("T")[0]
        humidity_by_day[date].append(humidity)

    average_humidity = [
        round(
            sum(humidity_by_day[date]) / len(humidity_by_day[date]),
            1
        )
        for date in daily["time"]
    ]

    return {
        "dates": daily["time"],
        "temp_high": daily["temperature_2m_max"],
        "temp_low": daily["temperature_2m_min"],
        "wind_speed": daily["wind_speed_10m_mean"],
        "precip_probability": daily["precipitation_probability_max"],
        "wmo_code": daily["weather_code"],
        "cloud_cover": daily["cloud_cover_mean"],
        "humidity": average_humidity,
    }

async def regenerate_weather(
    db: aiosqlite.Connection,
    settlement: str,
    latitude: float,
    longitude: float
) -> str:

    cursor = await db.cursor()

    weather = await get_weather(latitude, longitude)

    for i in range(7):

        await cursor.execute("""
            INSERT INTO Weather_History (
                Settlement,
                Date,
                Temp_high,
                Temp_low,
                Wind_speed,
                Precipitation_probability,
                Cloud_Cover,
                humidity,
                WMO_Code
            )
            VALUES (?, DATE(?, '-1 day'), ?, ?, ?, ?, ?, ?, ?)
        """, (
            settlement,
            weather["dates"][i],
            round(weather["temp_high"][i], 2),
            round(weather["temp_low"][i], 2),
            round(weather["wind_speed"][i], 2),
            round(weather["precip_probability"][i], 2),
            round(weather["cloud_cover"][i], 2),
            round(weather["humidity"][i], 2),
            weather["wmo_code"][i]
        ))

    await db.commit()

    return f"Weather generated for {settlement}"

async def generate_weather(
    db: aiosqlite.Connection,
    settlement: str,
    latitude: float,
    longitude: float
) -> str:

    cursor = await db.cursor()

    weather = await get_weather(latitude, longitude)
    if len(weather["dates"]) < 7:
        raise ValueError("Forecast did not return 7 days.")

    index = 6

    await cursor.execute("""
        INSERT OR Replace INTO Weather_History (
            Settlement,
            Date,
            Temp_high,
            Temp_low,
            Wind_speed,
            Precipitation_probability,
            Cloud_Cover,
            humidity,
            WMO_Code
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        settlement,
        weather["dates"][index],
        round(weather["temp_high"][index], 2),
        round(weather["temp_low"][index], 2),
        round(weather["wind_speed"][index], 2),
        round(weather["precip_probability"][index], 2),
        round(weather["cloud_cover"][index], 2),
        round(weather["humidity"][index], 2),
        weather["wmo_code"][index]
    ))

    await db.commit()

    return f"Weather generated for {settlement}"

