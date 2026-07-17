"""Tests for the exposed-entity allowlist in NativeFunction._execute_service.

The allowlist is the only access-control boundary on the shipped
``execute_service`` tool, so these verify it cannot be bypassed by
list-valued entity_ids or broad area/device/target targeting.
"""
import sys

import pytest

sys.path.insert(0, ".")

# conftest.py stubs all HA modules before this runs
from custom_components.venice_ai.functions.native import NativeFunction
from custom_components.venice_ai.exceptions import EntityNotExposed, EntityNotFound


class _FakeStates:
    def __init__(self, ids):
        self._ids = list(ids)

    def async_entity_ids(self):
        return list(self._ids)


class _FakeServices:
    def __init__(self):
        self.calls = []

    async def async_call(self, domain, service, service_data, blocking=True):
        self.calls.append((domain, service, service_data))


class _FakeHass:
    def __init__(self, known_ids):
        self.states = _FakeStates(known_ids)
        self.services = _FakeServices()


EXPOSED = [{"entity_id": "light.kitchen"}]


async def _run(hass, service_data):
    fn = NativeFunction()
    return await fn._execute_service(
        hass,
        {"domain": "light", "service": "turn_on", "service_data": service_data},
        EXPOSED,
    )


@pytest.mark.asyncio
async def test_exposed_entity_allowed():
    hass = _FakeHass(["light.kitchen"])
    result = await _run(hass, {"entity_id": "light.kitchen"})
    assert result == {"success": True}
    assert len(hass.services.calls) == 1


@pytest.mark.asyncio
async def test_non_exposed_entity_rejected():
    hass = _FakeHass(["light.kitchen", "lock.front"])
    with pytest.raises(EntityNotExposed):
        await _run(hass, {"entity_id": "lock.front"})
    assert hass.services.calls == []


@pytest.mark.asyncio
async def test_unknown_entity_rejected():
    hass = _FakeHass(["light.kitchen"])
    with pytest.raises(EntityNotFound):
        await _run(hass, {"entity_id": "light.ghost"})


@pytest.mark.asyncio
async def test_list_entity_id_validated_per_element():
    hass = _FakeHass(["light.kitchen", "lock.front"])
    # kitchen is exposed but lock.front is not — must reject the whole call.
    with pytest.raises(EntityNotExposed):
        await _run(hass, {"entity_id": ["light.kitchen", "lock.front"]})
    assert hass.services.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("broad", ["area_id", "device_id", "label_id"])
async def test_broad_targeting_rejected(broad):
    hass = _FakeHass(["light.kitchen", "lock.front"])
    result = await _run(hass, {broad: "bedroom"})
    assert "error" in result
    assert hass.services.calls == []


@pytest.mark.asyncio
async def test_broad_targeting_in_target_block_rejected():
    hass = _FakeHass(["light.kitchen"])
    result = await _run(hass, {"target": {"area_id": "bedroom"}})
    assert "error" in result
    assert hass.services.calls == []


@pytest.mark.asyncio
async def test_target_entity_id_validated():
    hass = _FakeHass(["light.kitchen", "lock.front"])
    with pytest.raises(EntityNotExposed):
        await _run(hass, {"target": {"entity_id": "lock.front"}})


@pytest.mark.asyncio
async def test_no_entity_no_broad_key_passes_through():
    # A service with no entity target (e.g. a notify service) is allowed.
    hass = _FakeHass(["light.kitchen"])
    result = await _run(hass, {"message": "hi"})
    assert result == {"success": True}
