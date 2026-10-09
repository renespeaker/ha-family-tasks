"""Family Tasks: a persistent points ledger for the Family Task Card.

The card reports checked-off tasks with `family_tasks.award` (and takes them
back with `revoke`); rewards are paid with `redeem`, parents can give a bonus
or deduction with `adjust`. Every person gets a points sensor.
"""

from __future__ import annotations

from dataclasses import dataclass

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_KEY,
    ATTR_PERSON,
    ATTR_POINTS,
    ATTR_REASON,
    ATTR_REWARD,
    ATTR_TASK,
    DOMAIN,
    EVENT_POINTS_CHANGED,
    SERVICE_ADJUST,
    SERVICE_AWARD,
    SERVICE_REDEEM,
    SERVICE_REVOKE,
    SIGNAL_UPDATED,
    STORAGE_KEY,
    STORAGE_VERSION,
)
from .ledger import InsufficientPoints, Ledger

PLATFORMS = [Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PERSON = vol.All(cv.string, vol.Length(min=1))

AWARD_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_KEY): vol.All(cv.string, vol.Length(min=1)),
        vol.Required(ATTR_PERSON): PERSON,
        vol.Required(ATTR_POINTS): vol.All(vol.Coerce(int), vol.Range(min=0)),
        vol.Optional(ATTR_TASK, default=""): cv.string,
    }
)
REVOKE_SCHEMA = vol.Schema({vol.Required(ATTR_KEY): vol.All(cv.string, vol.Length(min=1))})
REDEEM_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_PERSON): PERSON,
        vol.Required(ATTR_POINTS): vol.All(vol.Coerce(int), vol.Range(min=1)),
        vol.Optional(ATTR_REWARD, default=""): cv.string,
    }
)
ADJUST_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_PERSON): PERSON,
        vol.Required(ATTR_POINTS): vol.All(vol.Coerce(int), vol.NotIn([0])),
        vol.Optional(ATTR_REASON, default=""): cv.string,
    }
)


@dataclass
class FamilyTasksData:
    """What a loaded entry keeps: the ledger and where it is stored."""

    ledger: Ledger
    store: Store


type FamilyTasksConfigEntry = ConfigEntry[FamilyTasksData]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the services (they look up the loaded entry when called)."""

    def _data() -> FamilyTasksData:
        entries = hass.config_entries.async_loaded_entries(DOMAIN)
        if not entries:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="not_loaded")
        return entries[0].runtime_data

    @callback
    def _changed(data: FamilyTasksData, person: str, kind: str, points: int, label: str) -> None:
        data.store.async_delay_save(data.ledger.as_dict, 1)
        async_dispatcher_send(hass, SIGNAL_UPDATED, person)
        hass.bus.async_fire(
            EVENT_POINTS_CHANGED,
            {
                "person": person,
                "kind": kind,
                "points": points,
                "label": label,
                "balance": data.ledger.totals(person).balance,
            },
        )

    async def award(call: ServiceCall) -> ServiceResponse:
        data = _data()
        person, points, task = call.data[ATTR_PERSON], call.data[ATTR_POINTS], call.data[ATTR_TASK]
        booked = data.ledger.award(call.data[ATTR_KEY], person, points, task, _now())
        if booked:
            _changed(data, person, "award", points, task)
        return {"awarded": booked, "balance": data.ledger.totals(person).balance}

    async def revoke(call: ServiceCall) -> ServiceResponse:
        data = _data()
        gone = data.ledger.revoke(call.data[ATTR_KEY])
        if gone:
            _changed(data, gone.person, "revoke", -gone.points, gone.label)
        return {"revoked": gone is not None}

    async def redeem(call: ServiceCall) -> ServiceResponse:
        data = _data()
        person, points, reward = (
            call.data[ATTR_PERSON],
            call.data[ATTR_POINTS],
            call.data[ATTR_REWARD],
        )
        try:
            data.ledger.redeem(person, points, reward, _now())
        except InsufficientPoints as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="insufficient_points",
                translation_placeholders={
                    "person": person,
                    "balance": str(err.balance),
                    "points": str(points),
                },
            ) from err
        _changed(data, person, "redeem", -points, reward)
        return {"balance": data.ledger.totals(person).balance}

    async def adjust(call: ServiceCall) -> ServiceResponse:
        data = _data()
        person, points, reason = (
            call.data[ATTR_PERSON],
            call.data[ATTR_POINTS],
            call.data[ATTR_REASON],
        )
        data.ledger.adjust(person, points, reason, _now())
        _changed(data, person, "adjust", points, reason)
        return {"balance": data.ledger.totals(person).balance}

    for name, handler, schema in (
        (SERVICE_AWARD, award, AWARD_SCHEMA),
        (SERVICE_REVOKE, revoke, REVOKE_SCHEMA),
        (SERVICE_REDEEM, redeem, REDEEM_SCHEMA),
        (SERVICE_ADJUST, adjust, ADJUST_SCHEMA),
    ):
        hass.services.async_register(
            DOMAIN, name, handler, schema=schema, supports_response=SupportsResponse.OPTIONAL
        )
    return True


def _now() -> str:
    return dt_util.utcnow().isoformat()


async def async_setup_entry(hass: HomeAssistant, entry: FamilyTasksConfigEntry) -> bool:
    """Load the ledger and the sensors."""
    store: Store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
    entry.runtime_data = FamilyTasksData(Ledger.from_dict(await store.async_load()), store)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: FamilyTasksConfigEntry) -> bool:
    """Write pending bookings before unloading."""
    data = entry.runtime_data
    await data.store.async_save(data.ledger.as_dict())
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
