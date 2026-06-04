import datetime
import logging
import typing
from dataclasses import dataclass, field, fields
from typing import Optional
import math
import bcrypt
from copy import deepcopy

settlement_dict = {
    "Corruption": "Corruption",
    "Crime": "Crime",
    "Productivity": "Productivity",
    "Law": "Law",
    "Lore": "Lore",
    "Society": "Society",
    "Danger": "Danger",
    "Defence": "Defence",
    "Base Value": "Base_Value",
    "Spellcasting": "Spellcasting",
    "Supply": "Supply",
}
kingdom_dict = {
    "Size": "Size",
    "Population": "Population",
    "Unallocated Population": "Unallocated_Population",
    "Economy": "Economy",
    "Loyalty": "Loyalty",
    "Stability": "Stability",
    "Fame": "Fame",
    "Unrest": "Unrest",
    "Consumption": "Consumption"
}
reroll_dict = {
    0: "Set Result",
    1: "Roll Randomly",
    2: "All Buildings with same trait",
    3: "Explode result on Max",
    4: "A single instance that explodes on the max roll."
}

@dataclass
class UtilizationMetrics:
    base: int
    trade: int
    remaining: int
    depletion: int

    # This turns 'total' into a dynamic property so you don't have to calculate it manually
    @property
    def total(self) -> int:
        return self.base + self.trade


@dataclass
class PopulationMetric:
    current: int =0
    min: int = 0
    max: int = 0


@dataclass
class FoodDataClass:
    husbandry: UtilizationMetrics = field(
        default_factory=lambda: UtilizationMetrics(0, 0, 0, 0)
    )
    seafood: UtilizationMetrics = field(
        default_factory=lambda: UtilizationMetrics(0, 0, 0, 0)
    )
    produce: UtilizationMetrics = field(
        default_factory=lambda: UtilizationMetrics(0, 0, 0, 0)
    )
    grain: UtilizationMetrics = field(
        default_factory=lambda: UtilizationMetrics(0, 0, 0, 0)
    )


@dataclass
class RawMaterialsDataClass:
    raw_textiles: UtilizationMetrics = field(
        default_factory=lambda: UtilizationMetrics(0, 0, 0, 0)
    )
    ore: UtilizationMetrics = field(
        default_factory=lambda: UtilizationMetrics(0, 0, 0, 0)
    )
    stone: UtilizationMetrics = field(
        default_factory=lambda: UtilizationMetrics(0, 0, 0, 0)
    )
    wood: UtilizationMetrics = field(
        default_factory=lambda: UtilizationMetrics(0, 0, 0, 0)
    )

@dataclass
class SimpleCraftDataClass:
    textiles: UtilizationMetrics = field(
        default_factory=lambda: UtilizationMetrics(0, 0, 0, 0)
    )
    metallurgy: UtilizationMetrics = field(
        default_factory=lambda: UtilizationMetrics(0, 0, 0, 0)
    )
    woodworking: UtilizationMetrics = field(
        default_factory=lambda: UtilizationMetrics(0, 0, 0, 0)
    )
    stoneworking: UtilizationMetrics = field(
        default_factory=lambda: UtilizationMetrics(0, 0, 0, 0)
    )


@dataclass
class LuxuryCraftDataClass:
    magical_items: UtilizationMetrics = field(
        default_factory=lambda: UtilizationMetrics(0, 0, 0, 0)
    )
    luxury: UtilizationMetrics = field(
        default_factory=lambda: UtilizationMetrics(0, 0, 0, 0)
    )




@dataclass
class TradeInfo:
    source_kingdom: str = None
    end_kingdom: str = None
    husbandry: int = 0
    seafood: int = 0
    produce: int = 0
    grain: int = 0
    raw_textiles: int = 0
    ore: int = 0
    stone: int = 0
    wood: int = 0
    textiles: int = 0
    metallurgy: int = 0
    woodworking: int = 0
    stoneworking: int = 0
    magical_consumables: int = 0
    magical_items: int = 0
    mundane_exotic: int = 0
    luxury: int = 0


@dataclass
class SettlementStatMetrics:
    base: int = 0
    custom_value: int = 0
    building_value: int = 0
    penalty: int = 0
    other: int = 0

    # This turns 'total' into a dynamic property so you don't have to calculate it manually
    @property
    def total(self) -> int:
        return self.base + self.custom_value + self.building_value + self.penalty +self.other




@dataclass
class KingdomStatMetrics5type:
    base: int = 0
    custom_value: int = 0
    building_value: int = 0
    hex_value: int = 0
    leadership: int = 0

    # This turns 'total' into a dynamic property so you don't have to calculate it manually
    @property
    def total(self) -> int:
        print('base = ', self.base, 'custom_value = ', self.custom_value, 'building_value = ', self.building_value,
              'hex_value = ', self.hex_value, 'leadership = ', self.leadership)
        return self.base + self.custom_value + self.building_value + self.hex_value +self.leadership


@dataclass
class KingdomStatMetrics6type:
    base: int = 0
    custom_value: int = 0
    building_value: int = 0
    hex_value: int = 0
    leadership: int = 0
    edict: int = 0

    # This turns 'total' into a dynamic property so you don't have to calculate it manually
    @property
    def total(self) -> int:
        print('base = ', self.base, 'custom_value = ', self.custom_value, 'building_value = ', self.building_value, 'hex_value = ', self.hex_value, 'leadership = ', self.leadership, 'edict = ', self.edict)
        return self.base + self.custom_value + self.building_value + self.hex_value +self.leadership + self.edict

@dataclass
class KingdomStatMetrics7type:
    base: int = 0
    custom_value: int = 0
    building_value: int = 0
    hex_value: int = 0
    leadership: int = 0
    edict: int = 0
    turn_penalty: int = 0

    # This turns 'total' into a dynamic property so you don't have to calculate it manually
    @property
    def total(self) -> int:
#        print('base = ', self.base, 'custom_value = ', self.custom_value, 'building_value = ', self.building_value,
#              'hex_value = ', self.hex_value, 'leadership = ', self.leadership, 'edict = ', self.edict, 'turn_penalty = ', self.turn_penalty)
        return self.base + self.custom_value + self.building_value + self.hex_value +self.leadership + self.edict + self.turn_penalty



@dataclass
class KingdomStatMetricsConsumption:
    base: int = 0
    custom_value: int = 0
    building_value: int = 0
    hex_value: int = 0
    edict: int = 0
    army: int = 0

    # This turns 'total' into a dynamic property so you don't have to calculate it manually
    @property
    def total(self) -> int:
#        print('base = ', self.base, 'custom_value = ', self.custom_value, 'building_value = ', self.building_value,
#              'hex_value = ', self.hex_value, 'edict = ', self.edict, 'army = ', self.army)
        return self.base + self.custom_value + self.building_value + self.hex_value + self.edict + self.army
    @property
    def no_hex_total(self) -> int:
        return self.base + self.custom_value + self.building_value + self.edict + self.army




@dataclass
class KingdomInfo:
    kingdom: str
    region: str = None
    password: Optional[str] = None
    government: Optional[str] = None
    alignment: Optional[str] = None
    build_points: Optional[int] = None
    population: Optional[int] = None
    turn: Optional[int] = 0
    heraldry: Optional[str] = None
    host_channel: Optional[int] = None
    host_message: Optional[int]= None
    log_thread: Optional[int] = None
    control_dc: KingdomStatMetrics5type = field(
        default_factory=lambda: KingdomStatMetrics5type(0, 0, 0, 0, 0)
    )
    size: KingdomStatMetrics5type = field(
        default_factory=lambda: KingdomStatMetrics5type(0, 0, 0, 0, 0)
    )
    economy: KingdomStatMetrics7type = field(
        default_factory=lambda: KingdomStatMetrics7type(0, 0, 0, 0, 0, 0, 0)
    )
    loyalty: KingdomStatMetrics7type = field(
        default_factory=lambda: KingdomStatMetrics7type(0, 0, 0, 0, 0, 0, 0)
    )
    stability: KingdomStatMetrics7type = field(
        default_factory=lambda: KingdomStatMetrics7type(0, 0, 0, 0, 0, 0, 0)
    )
    fame: KingdomStatMetrics5type = field(
        default_factory=lambda: KingdomStatMetrics5type(0, 0, 0, 0, 0)
    )
    unrest: KingdomStatMetrics5type = field(
        default_factory=lambda: KingdomStatMetrics5type(0, 0, 0, 0, 0)
    )
    consumption: KingdomStatMetricsConsumption = field(
        default_factory=lambda: KingdomStatMetricsConsumption(0, 0, 0, 0, 0, 0)
    )
    taxation: KingdomStatMetrics5type = field(
        default_factory=lambda: KingdomStatMetrics5type(0, 0, 0, 0, 0)
    )
    suppy: Optional[int] = None



@dataclass
class SettlementInfo:
    kingdom: str
    settlement: str
    image: Optional[str] = None
    host_channel: Optional[int] = None
    host_message: Optional[int] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    size: SettlementStatMetrics = field(
        default_factory=lambda: SettlementStatMetrics(0, 0, 0, 0, 0)
    )
    corruption: SettlementStatMetrics = field(
        default_factory=lambda: SettlementStatMetrics(0, 0, 0, 0, 0)
    )
    crime: SettlementStatMetrics = field(
        default_factory=lambda: SettlementStatMetrics(0, 0, 0, 0, 0)
    )
    productivity: SettlementStatMetrics = field(
        default_factory=lambda: SettlementStatMetrics(0, 0, 0, 0, 0)
    )
    law: SettlementStatMetrics = field(
        default_factory=lambda: SettlementStatMetrics(0, 0, 0, 0, 0)
    )
    lore: SettlementStatMetrics = field(
        default_factory=lambda: SettlementStatMetrics(0, 0, 0, 0, 0)
    )
    society: SettlementStatMetrics = field(
        default_factory=lambda: SettlementStatMetrics(0, 0, 0, 0, 0)
    )
    danger: SettlementStatMetrics = field(
        default_factory=lambda: SettlementStatMetrics(0, 0, 0, 0, 0)
    )
    defence: SettlementStatMetrics = field(
        default_factory=lambda: SettlementStatMetrics(0, 0, 0, 0, 0)
    )
    base_value: SettlementStatMetrics = field(
        default_factory=lambda: SettlementStatMetrics(0, 0, 0, 0, 0)
    )
    spellcasting: SettlementStatMetrics = field(
        default_factory=lambda: SettlementStatMetrics(0, 0, 0, 0, 0)
    )
    supply: SettlementStatMetrics = field(
        default_factory=lambda: SettlementStatMetrics(0, 0, 0, 0, 0)
    )
    decay: SettlementStatMetrics = field(
        default_factory=lambda: SettlementStatMetrics(0, 0, 0, 0, 0)
    )


@dataclass
class BaseSettlementInfo:
    kingdom: str
    settlement: str
    size: Optional[int] = None
    population: Optional[int] = None
    corruption: Optional[int] = None
    crime: Optional[int] = None
    productivity: Optional[int] = None
    law: Optional[int] = None
    lore: Optional[int] = None
    society: Optional[int] = None
    danger: Optional[int] = None
    defence: Optional[int] = None
    base_value: Optional[int] = None
    spellcasting: Optional[int] = None
    supply: Optional[int] = None
    decay: Optional[int] = None


@dataclass
class BuildingInfo:
    full_name: str
    type: str
    subtype: str
    quality: int
    build_points: int
    lots: int
    economy: int
    loyalty: int
    stability: int
    fame: int
    unrest: int
    corruption: int
    crime: int
    productivity: int
    law: int
    lore: int
    society: int
    danger: int
    defence: int
    base_value: int
    spellcasting: int
    supply: int
    settlement_limit: int
    district_limit: int
    description: str
    upgrade: str
    discount: str
    tier: int


@dataclass
class HexImprovementInfo:
    full_name: str
    name: str
    subtype: str
    quality: int
    build_points: int
    economy: int
    loyalty: int
    stability: int
    unrest: int
    consumption: int
    defence: int
    taxation: int
    cavernous: int
    coastline: int
    desert: int
    forest: int
    hills: int
    jungle: int
    marsh: int
    mountains: int
    plains: int
    water: int
    source: int
    size: int


def clamp_remaining_to_zero(dataclass_instance):
    for field in fields(dataclass_instance):
        metric = getattr(dataclass_instance, field.name)
        metric.remaining = max(0, metric.remaining)

def fix_remaining_to_zero(food: FoodDataClass):
    for f in fields(food):
        metric = getattr(food, f.name)
        metric.remaining = 0

def goods_remaining_dict(good: typing.Union[FoodDataClass, SimpleCraftDataClass, RawMaterialsDataClass, LuxuryCraftDataClass]) -> typing.Dict[str, int]:
    return {
        f.name: getattr(good, f.name).remaining
        for f in fields(good)
    }

def remaining_is_total(dataclass_instance):
    for field in fields(dataclass_instance):
        metric = getattr(dataclass_instance, field.name)
        metric.remaining = metric.base + metric.trade


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


def encrypt_password(plain_password: str):
    # Generate a salt and hash the password
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(plain_password.encode(), salt)
    return hashed_password


def validate_password(plain_password, stored_hashed_password):
    return bcrypt.checkpw(plain_password.encode('utf-8'), stored_hashed_password)

def resource_dict_balancing(goods_dict: dict, crafted_dict: dict) -> (dict, dict):
    total_crafted_materials_dict = {
        'woodworking': min(goods_dict['wood'], crafted_dict['woodworking']),
        'textile': min(goods_dict['textile'], crafted_dict['raw_textiles']),
        'stoneworking': min(goods_dict['stone'], crafted_dict['stoneworking']),
        'metallurgy': min(goods_dict['metallurgy'], crafted_dict['ore']),
    }
    source_materials_dict = {
        'Wood': goods_dict['wood'] - total_crafted_materials_dict['woodworking'],
        'Raw_Textiles': crafted_dict['raw_textiles'] - total_crafted_materials_dict['textile'],
        'ore': crafted_dict['ore'] - total_crafted_materials_dict['metallurgy'],
        'stone': goods_dict['stone'] - total_crafted_materials_dict['stoneworking']
    }
    return total_crafted_materials_dict, source_materials_dict




def distribute_consumption(goods, utilization):
    goods = deepcopy(goods)

    metrics = [
        getattr(goods, f.name)
        for f in fields(goods)
    ]

    max_value = max(metric.remaining for metric in metrics)

    for target in range(max_value, -1, -1):

        total_used = sum(
            max(0, metric.remaining - target)
            for metric in metrics
        )

        if total_used <= utilization:
            base_target = target
            break
    else:
        raise ValueError("Not enough resources to equalize.")

    total_used = 0

    for metric in metrics:
        reduction = max(
            0,
            metric.remaining - base_target
        )

        metric.remaining -= reduction
        total_used += reduction

    leftover = utilization - total_used

    while leftover > 0:

        candidates = [
            metric
            for metric in metrics
            if metric.remaining > 0
        ]

        if not candidates:
            break

        candidates.sort(
            key=lambda m: m.remaining,
            reverse=True
        )

        for metric in candidates:
            metric.remaining -= 1
            leftover -= 1

            if leftover == 0:
                break

    return goods, base_target, leftover


def allocate_food(required: int, available: dict[str, int]) -> dict[str, int]:
    """
    Attempts to:
    - Give every food type at least 15% contribution if possible
    - Prevent any one type from exceeding 50%
    - Evenly spread remaining consumption
    """

    if required <= 0 or not available:
        return {k: 0 for k in available}

    allocation = {k: 0 for k in available}

    cap = math.floor(required * 0.5)
    min_contribution = math.floor(required * 0.15)

    # STEP 1:
    # Try to give each food type minimum contribution
    remaining_required = required

    for resource, amount in available.items():
        contribution = min(amount, min_contribution)

        allocation[resource] += contribution
        remaining_required -= contribution

    if remaining_required <= 0:
        return allocation

    # STEP 2:
    # Distribute remaining food evenly while respecting caps
    while remaining_required > 0:
        progress = False

        for resource in available:
            available_left = available[resource] - allocation[resource]

            if available_left <= 0:
                continue

            if allocation[resource] >= cap:
                continue

            allocation[resource] += 1
            remaining_required -= 1
            progress = True

            if remaining_required <= 0:
                break

        # No more valid allocations possible
        if not progress:
            break

    return allocation



def distribute_pain(sources, targets):
    conversion_rate = 2

    sources = deepcopy(sources)
    targets = deepcopy(targets)

    source_metrics = [
        getattr(sources, f.name)
        for f in fields(sources)
    ]

    target_metrics = [
        getattr(targets, f.name)
        for f in fields(targets)
    ]

    total_raw = sum(
        metric.remaining
        for metric in source_metrics
    )

    total_possible_production = total_raw // conversion_rate

    desired_production = sum(
        metric.base
        for metric in target_metrics
    )

    overdraft = desired_production - total_possible_production
    # Enough resources
    if desired_production <= total_possible_production:
        actual_production = desired_production

    # Not enough resources
    else:
        actual_production = total_possible_production

        excess = desired_production - actual_production

        while excess > 0:

            active = [
                metric
                for metric in target_metrics
                if metric.base > 0
            ]

            if not active:
                break

            share = max(1, excess // len(active))

            reduced_this_pass = 0

            for metric in active:

                if excess <= 0:
                    break

                reduction = min(
                    share,
                    metric.base,
                    excess
                )

                metric.base -= reduction

                excess -= reduction
                reduced_this_pass += reduction

            if reduced_this_pass == 0:
                break

    # Consume raw materials
    raw_to_consume = actual_production * conversion_rate

    while raw_to_consume > 0:

        active = [
            metric
            for metric in source_metrics
            if metric.remaining > 0
        ]

        if not active:
            break

        share = max(1, raw_to_consume // len(active))

        consumed_this_pass = 0

        for metric in active:

            if raw_to_consume <= 0:
                break

            consume = min(
                share,
                metric.remaining,
                raw_to_consume
            )

            metric.remaining -= consume

            raw_to_consume -= consume
            consumed_this_pass += consume

        if consumed_this_pass == 0:
            break

    return sources, targets, overdraft