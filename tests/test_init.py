"""The integration inside Home Assistant: setup, services, sensors, storage."""

from typing import Any

import pytest

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_capture_events

from custom_components.family_tasks.const import DOMAIN, EVENT_POINTS_CHANGED


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, title="Family Tasks")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _call(hass: HomeAssistant, service: str, **data: Any) -> dict[str, Any]:
    res = await hass.services.async_call(DOMAIN, service, data, blocking=True, return_response=True)
    await hass.async_block_till_done()
    return res


def _sensor(hass: HomeAssistant, person: str):
    for st in hass.states.async_all("sensor"):
        if st.attributes.get("person") == person:
            return st
    return None


async def test_config_flow_adds_one_entry(hass: HomeAssistant):
    res = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert res["type"] is FlowResultType.FORM
    res = await hass.config_entries.flow.async_configure(res["flow_id"], {})
    assert res["type"] is FlowResultType.CREATE_ENTRY
    again = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert again["type"] is FlowResultType.ABORT


async def test_award_creates_a_points_sensor(hass: HomeAssistant):
    await _setup(hass)
    res = await _call(hass, "award", key="todo.lina|a1", person="Lina", points=10, task="Tidy room")
    assert res == {"awarded": True, "balance": 10}
    st = _sensor(hass, "Lina")
    assert st.state == "10"
    assert st.attributes["earned"] == 10
    assert st.attributes["last_booking"] == "Tidy room"
    assert st.attributes["unit_of_measurement"] == "points"


async def test_the_same_task_is_booked_once(hass: HomeAssistant):
    await _setup(hass)
    await _call(hass, "award", key="k", person="Lina", points=10)
    res = await _call(hass, "award", key="k", person="Lina", points=10)  # the wall tablet, too
    assert res == {"awarded": False, "balance": 10}
    assert _sensor(hass, "Lina").state == "10"


async def test_revoke_redeem_adjust(hass: HomeAssistant):
    await _setup(hass)
    await _call(hass, "award", key="a", person="Ben", points=30)
    await _call(hass, "award", key="b", person="Ben", points=10)
    assert await _call(hass, "revoke", key="b") == {"revoked": True}
    assert await _call(hass, "redeem", person="Ben", points=20, reward="Ice cream") == {
        "balance": 10
    }
    assert await _call(hass, "adjust", person="Ben", points=-3, reason="Fought") == {"balance": 7}
    st = _sensor(hass, "Ben")
    assert (st.state, st.attributes["earned"], st.attributes["redeemed"]) == ("7", 27, 20)


async def test_redeem_refuses_too_expensive(hass: HomeAssistant):
    await _setup(hass)
    await _call(hass, "award", key="a", person="Mia", points=5)
    with pytest.raises(ServiceValidationError) as err:
        await _call(hass, "redeem", person="Mia", points=50)
    assert err.value.translation_key == "insufficient_points"
    assert _sensor(hass, "Mia").state == "5"


async def test_fires_an_event_for_automations(hass: HomeAssistant):
    await _setup(hass)
    events = async_capture_events(hass, EVENT_POINTS_CHANGED)
    await _call(hass, "award", key="a", person="Lina", points=10, task="Bins")
    await _call(hass, "award", key="a", person="Lina", points=10, task="Bins")  # duplicate: silent
    assert [e.data for e in events] == [
        {"person": "Lina", "kind": "award", "points": 10, "label": "Bins", "balance": 10}
    ]


async def test_points_survive_a_restart(hass: HomeAssistant, hass_storage):
    entry = await _setup(hass)
    await _call(hass, "award", key="a", person="Lina", points=10)
    await hass.config_entries.async_unload(entry.entry_id)
    assert hass_storage[DOMAIN]["data"]["bookings"][0]["key"] == "a"
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert _sensor(hass, "Lina").state == "10"
    assert (await _call(hass, "award", key="a", person="Lina", points=10))["awarded"] is False


async def test_services_need_the_integration_set_up(hass: HomeAssistant):
    entry = await _setup(hass)
    await hass.config_entries.async_unload(entry.entry_id)
    with pytest.raises(ServiceValidationError):
        await _call(hass, "award", key="a", person="Lina", points=10)


async def test_person_entity_names_the_device(hass: HomeAssistant):
    hass.states.async_set("person.lina", "home", {"friendly_name": "Lina"})
    await _setup(hass)
    await _call(hass, "award", key="a", person="person.lina", points=10)
    assert _sensor(hass, "person.lina").entity_id == "sensor.lina_points"
