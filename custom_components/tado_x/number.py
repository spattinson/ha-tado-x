"""Number platform for Tado X."""
from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DHW_MAX_TEMP, DHW_MIN_TEMP, DOMAIN, FEATURE_ENTITY_MAP
from .coordinator import TadoXDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tado X number entities."""
    coordinator: TadoXDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[NumberEntity] = []

    # Only add flow temperature if the feature is available
    if coordinator.data and coordinator.data.has_flow_temp_control:
        entities.append(TadoXMaxFlowTemperature(coordinator))

    entities.append(TadoXDhwTemperature(coordinator))

    async_add_entities(entities)

    # Update entity enabled/disabled state based on feature flags
    entity_registry = er.async_get(hass)
    for entity_id, entity_entry in list(entity_registry.entities.items()):
        if entity_entry.platform != DOMAIN or entity_entry.domain != "number":
            continue

        if not entity_entry.unique_id:
            continue

        # Check if this entity matches a disabled feature
        should_be_disabled = False
        for feature_flag, entity_keys in FEATURE_ENTITY_MAP.items():
            feature_enabled = getattr(coordinator, feature_flag, False)

            for entity_key in entity_keys:
                if entity_entry.unique_id.endswith(f"_{entity_key}"):
                    if not feature_enabled:
                        should_be_disabled = True
                    break

            if should_be_disabled:
                break

        # Update disabled state
        if should_be_disabled:
            entity_registry.async_update_entity(
                entity_id,
                disabled_by=er.RegistryEntryDisabler.INTEGRATION,
            )
        elif entity_entry.disabled_by == er.RegistryEntryDisabler.INTEGRATION:
            # Make sure it's enabled if the feature is on
            entity_registry.async_update_entity(
                entity_id,
                disabled_by=None,
            )


class TadoXMaxFlowTemperature(CoordinatorEntity[TadoXDataUpdateCoordinator], NumberEntity):
    """Number entity for Tado X max flow temperature."""

    _attr_has_entity_name = True
    _attr_translation_key = "max_flow_temperature"
    _attr_icon = "mdi:thermometer-water"
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: TadoXDataUpdateCoordinator) -> None:
        """Initialize the max flow temperature entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.home_id}_max_flow_temperature"

        # Set min/max from constraints
        data = coordinator.data
        if data:
            self._attr_native_min_value = float(data.flow_temp_min or 20)
            self._attr_native_max_value = float(data.flow_temp_max or 75)
        else:
            self._attr_native_min_value = 20.0
            self._attr_native_max_value = 75.0
        self._attr_native_step = 1.0

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for the home."""
        home_name = self.coordinator.home_name or f"Tado Home {self.coordinator.home_id}"
        return DeviceInfo(
            identifiers={(DOMAIN, str(self.coordinator.home_id))},
            name=home_name,
            manufacturer="Tado",
            model="Tado X Home",
        )

    @property
    def native_value(self) -> float | None:
        """Return the current max flow temperature."""
        data = self.coordinator.data
        if not data or not data.has_flow_temp_control:
            return None
        return float(data.max_flow_temperature) if data.max_flow_temperature else None

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        data = self.coordinator.data
        return data is not None and data.has_flow_temp_control

    async def async_set_native_value(self, value: float) -> None:
        """Set the max flow temperature."""
        try:
            await self.coordinator.api.set_max_flow_temperature(int(value))
            await self.coordinator.async_request_refresh()
            _LOGGER.info("Set max flow temperature to %d°C", int(value))
        except Exception as err:
            _LOGGER.error("Failed to set max flow temperature: %s", err)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        # Update min/max if constraints changed
        data = self.coordinator.data
        if data and data.has_flow_temp_control:
            if data.flow_temp_min is not None:
                self._attr_native_min_value = float(data.flow_temp_min)
            if data.flow_temp_max is not None:
                self._attr_native_max_value = float(data.flow_temp_max)
        self.async_write_ha_state()


class TadoXDhwTemperature(CoordinatorEntity[TadoXDataUpdateCoordinator], NumberEntity):
    """Number entity for Tado X domestic hot water temperature."""

    _attr_has_entity_name = True
    _attr_translation_key = "dhw_temperature"
    _attr_icon = "mdi:water-boiler"
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_mode = NumberMode.SLIDER
    _attr_native_step = 1.0

    def __init__(self, coordinator: TadoXDataUpdateCoordinator) -> None:
        """Initialize the domestic hot water temperature entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.home_id}_dhw_temperature"
        self._update_constraints()

    def _update_constraints(self) -> None:
        """Set min/max from API constraints, falling back to defaults."""
        data = self.coordinator.data
        min_temp = data.dhw_temp_min if data else None
        max_temp = data.dhw_temp_max if data else None
        self._attr_native_min_value = float(min_temp if min_temp is not None else DHW_MIN_TEMP)
        self._attr_native_max_value = float(max_temp if max_temp is not None else DHW_MAX_TEMP)

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for the home."""
        home_name = self.coordinator.home_name or f"Tado Home {self.coordinator.home_id}"
        return DeviceInfo(
            identifiers={(DOMAIN, str(self.coordinator.home_id))},
            name=home_name,
            manufacturer="Tado",
            model="Tado X Home",
        )

    @property
    def native_value(self) -> float | None:
        """Return the current domestic hot water temperature setpoint."""
        data = self.coordinator.data
        if not data:
            return None
        return data.dhw_temperature

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.data is not None and self.coordinator.enable_hot_water

    async def async_set_native_value(self, value: float) -> None:
        """Set the domestic hot water temperature."""
        try:
            await self.coordinator.api.set_domestic_hot_water_temperature(int(value))
            await self.coordinator.async_request_refresh()
            _LOGGER.info("Set domestic hot water temperature to %d°C", int(value))
        except Exception as err:
            _LOGGER.error("Failed to set domestic hot water temperature: %s", err)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._update_constraints()
        self.async_write_ha_state()
