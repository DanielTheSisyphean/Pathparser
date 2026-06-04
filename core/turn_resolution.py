async def resolve_turn(
        guild_id: int,
        kingdom: str) -> str:
    try:
        async with aiosqlite.connect(f"pathparser_{guild_id}.sqlite") as db:
            cursor = await db.cursor()
            await cursor.execute(
                "Select Kingdom, Region, Build_Points, Control_DC, Economy, Loyalty, Stability, Unrest, Consumption, Population FROM KB_Kingdoms WHERE Kingdom = ?",
                (kingdom,))
            kingdom_check = await cursor.fetchone()
            if not kingdom_check:
                return "The kingdom could not be found."
            (kingdom, region, build_points, control_dc, economy, loyalty, stability, unrest, consumption,
             population) = kingdom_check
            (event_economy, event_loyalty, event_stability) = await calculate_event_impacts(db, kingdom)
            await cursor.execute(
                "SELECT id, settlement, hex, Name, duration, check_a_status, check_b_status FROM KB_Events_Active WHERE Kingdom = ? And Active = 1",
                (kingdom,))
            active_events = await cursor.fetchall()

            consumption_modifier = 0
            farm_penalty = 0
            for event in active_events:
                (event_id, settlement, hex_id, name, duration, check_a_status, check_b_status) = event
                severity = 0
                severity += check_a_status if check_a_status > 0 else 0
                severity += check_b_status if check_b_status > 0 else 0
                await handle_severity(
                    db=db,
                    severity=severity,
                    kingdom=kingdom,
                    region=region,
                    settlement=settlement,
                    hex_id=hex_id,
                    event=name,
                    duration=duration,
                    event_id=event_id)
                if name == "Food Shortage" and severity == 0:
                    consumption_modifier += 1
                elif name == "Food Shortage" and severity == 1:
                    consumption_modifier += .5
                elif name == "Food Surplus":
                    consumption_modifier -= .5
                elif name == "Crop Failure" and severity == 0:
                    farm_penalty += 2
                elif name == "Crop Failure" and severity == 1:
                    farm_penalty += 1

            economy += event_economy
            loyalty += event_loyalty
            stability += event_stability
            stability_check = random.randint(1, 20) + stability - control_dc - unrest
            if stability_check < -5:
                unrest += random.randint(1, 4)
            elif stability_check < 0:
                unrest += 1
            else:
                unrest -= 1
            consumption = consumption + (consumption_modifier * consumption)
            await cursor.execute("SELECT SUM(Consumption_Size) FROM KB_Armies WHERE Kingdom = ?", (kingdom,))
            army_consumption = await cursor.fetchone()
            population = consumption + army_consumption[0] if army_consumption else consumption
            await cursor.execute("""
            SELECT 
                SUM(CASE WHEN subtype = 'Grain' THEN amount * quality ELSE 0 END) AS Grain_total,
                SUM(CASE WHEN subtype = 'Produce' THEN amount * quality ELSE 0 END) AS Produce_total
                SUM(CASE WHEN subtype = 'Husbandry' THEN amount * quality ELSE 0 END) AS Husbandry_total
                SUM(CASE WHEN subtype = 'Seafood' THEN amount * quality ELSE 0 END) AS Seafood_total,
                SUM(CASE WHEN type = 'Wood' THEN amount * quality ELSE 0 END) AS Wood_Total,
                SUM(CASE WHEN Type = 'Stone' THEN amount * quality ELSE 0 END) AS Stone_Total,
                SUM(CASE WHEN subtype = 'Raw_Textiles' THEN amount * quality ELSE 0 END) AS raw_textiles_total,
                SUM(CASE WHEN Type = 'Ore' THEN amount * quality ELSE 0 END) AS ore_total
            FROM KB_Hexes_Constructed KHC
            LEFT JOIN KB_Hexes_Improvements KHI on KHC.Full_Name = KHI.Full_Name
            WHERE Kingdom = ?""", (kingdom,))
            food_results = await cursor.fetchone()
            (produced_grain, produced_produce, produced_husbandry, produced_seafood, produced_wood, produced_stone,
             produced_raw_textiles, produced_ore) = food_results
            if farm_penalty == 1:
                produced_grain = produced_grain * .5 if produced_grain else 0
                produced_husbandry = produced_husbandry * .5 if produced_husbandry else 0
                produced_produce = produced_produce * .5 if produced_produce else 0
                produced_raw_textiles = produced_raw_textiles * .5 if produced_raw_textiles else 0
            elif farm_penalty == 2:
                produced_grain = 0
                produced_husbandry = 0
                produced_produce = 0
                produced_raw_textiles = 0

            await cursor.execute("""SELECT 
                SUM(CASE WHEN subtype = 'Woodworking' THEN amount * quality ELSE 0 END) AS Woodworking_Total,
                SUM(CASE WHEN subtype = 'Textile' THEN amount * quality ELSE 0 END) AS Textile_total,
                SUM(CASE WHEN subtype = 'Stoneworking' THEN amount * quality ELSE 0 END) AS Stoneworking_total,
                SUM(CASE WHEN subtype = 'Metallurgy' THEN amount * quality ELSE 0 END) AS Metallurgy_total,
                SUM(CASE WHEN subtype = 'Mundane Exotic' THEN amount * quality ELSE 0 END) AS Mundane_Exotic_total,
                SUM(CASE WHEN subtype = 'Mundane Complex' THEN amount * quality ELSE 0 END) AS Mundane_Complex_total,
                SUM(CASE WHEN subtype = 'Magical Items' THEN amount * quality ELSE 0 END) AS Magical_Items_total,
                SUM(CASE WHEN subtype = 'Magical Consumables' THEN amount * quality ELSE 0 END) AS Magical_Consumables_total
                FROM KB_Buildings kbuild
                LEFT JOIN KB_Buildings_Blueprints kblue on kblue.Full_Name = kbuild.Full_Name 
            WHERE Kingdom = ?""", (kingdom,))
            building_results = await cursor.fetchone()
            (woodworking, textile, stoneworking, metallurgy, mundane_exotic, mundane_complex, magical_consumable,
             magical_items) = building_results
            wood = safe_add(produced_wood, receiving_wood)
            stone = safe_add(produced_stone, receiving_stone)
            ore = safe_add(produced_ore, receiving_ore)
            grain = safe_add(produced_grain, receiving_grain)
            husbandry = safe_add(produced_husbandry, receiving_husbandry)
            produce = safe_add(produced_produce, receiving_produce)
            seafood = safe_add(produced_seafood, receiving_seafood)
            raw_textiles = safe_add(produced_raw_textiles, receiving_raw_textiles)
            produced_woodworking = min(wood, woodworking)
            wood -= produced_woodworking
            produced_stoneworking = min(stone, stoneworking)
            stone -= produced_woodworking
            produced_textiles = min(textile, raw_textiles)
            raw_textiles -= produced_woodworking
            produced_metallurgy = min(metallurgy, ore)
            metallurgy -= produced_woodworking
            source_materials_dict = {
                'Wood': wood,
                'Raw_Textiles': raw_textiles,
                'ore': ore,
                'stone': stone
            }
            target_materials_dict = {
                'mundane_exotic': mundane_exotic,
                'mundane_complex': mundane_complex,
                'magical_consumable': magical_consumable,
                'magical_items': magical_items
            }
            (source_materials_dict, target_materials_dict) = distribute_pain(source_materials_dict,
                                                                             target_materials_dict)
            source_food_dict = {
                'grain': grain,
                'seafood': seafood,
                'husbandry': husbandry,
                'produce': produce
            }
            (reduced_goods, consumption_used, base_target, leftover) = distribute_consumption(source_food_dict,
                                                                                              consumption)

            await cursor.execute(
                "SELECT coalesce(Stored_Grain, 0), coalesce(Stored_Produce, 0), coalesce(Stored_Husbandry, 0), coalesce(Stored_Seafood, 0) FROM KB_Kingdoms WHERE Kingdom = ?",
                (kingdom,))
            stored_food_results = await cursor.fetchone()
            (stored_grain, stored_produce, stored_husbandry, stored_seafood) = stored_food_results
            reduced_goods['grain'] += stored_grain
            reduced_goods['produce'] += stored_produce
            reduced_goods['husbandry'] += stored_husbandry
            reduced_goods['seafood'] += stored_seafood
            if leftover > 0:
                (reduced_goods, consumption_used, base_target, leftover) = distribute_consumption(reduced_goods, leftover)
                if leftover > 0:




    except:
        return "An error occurred while resolving the turn."
