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
        "&forecast_days=7"
        "&timezone=auto"
    )

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            response.raise_for_status()
            data = await response.json()

    daily = data["daily"]

    return {
        "dates": daily["time"],
        "temp_high": daily["temperature_2m_max"],
        "temp_low": daily["temperature_2m_min"],
        "wind_speed": daily["wind_speed_10m_mean"],
        "precip_probability": daily["precipitation_probability_max"],
        "wmo_code": daily["weather_code"],
        "cloud_cover": daily["cloud_cover_mean"],
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
                WMO_Code
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            settlement,
            weather["dates"][i],
            round(weather["temp_high"][i]),
            round(weather["temp_low"][i]),
            round(weather["wind_speed"][i]),
            round(weather["precip_probability"][i]),
            round(weather["cloud_cover"][i]),
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
            WMO_Code
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        settlement,
        weather["dates"][index],
        round(weather["temp_high"][index]),
        round(weather["temp_low"][index]),
        round(weather["wind_speed"][index]),
        round(weather["precip_probability"][index]),
        round(weather["cloud_cover"][index]),
        weather["wmo_code"][index]
    ))

    await db.commit()

    return f"Weather generated for {settlement}"

