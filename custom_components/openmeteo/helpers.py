from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN


async def maybe_update_device_name(hass: HomeAssistant, config_entry: ConfigEntry, new_name: str | None) -> None:
    """Ustaw nazwę urządzenia na `new_name`, jeśli użytkownik nie zmienił jej ręcznie.

    - Szukamy urządzenia po identifiers {(DOMAIN, entry_id)}.
    - Jeśli user ustawił własną nazwę (name_by_user) — nie ruszamy.
    - Aktualizujemy tylko, gdy device.name różni się od new_name.
    """
    if not new_name:
        return

    dev_reg = dr.async_get(hass)
    device = dev_reg.async_get_device(identifiers={(DOMAIN, config_entry.entry_id)})
    if not device:
        return

    # Szanujemy ręczną zmianę użytkownika
    if device.name_by_user:
        return

    if device.name != new_name:
        dev_reg.async_update_device(device_id=device.id, name=new_name)
