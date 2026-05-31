"""Config flow — fetches credentials from Orbit API."""
from __future__ import annotations

import base64
import json
import logging
from typing import Any
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_DEFAULT_DURATION,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_NETWORK_KEY,
    CONF_POLL_INTERVAL,
    CONF_PROVISION_VER,
    DEFAULT_DURATION_SEC,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    ORBIT_API_BASE,
)

_LOGGER = logging.getLogger(__name__)


def _api_request(method: str, url: str, body: dict | None = None, token: str | None = None) -> dict:
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["orbit-session-token"] = token
    req = Request(url, data=data, headers=headers, method=method)
    with urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def _fetch_device_credentials(email: str, password: str) -> list[dict]:
    """Return list of {name, device_id_hex, network_key_b64, provision_version} for all b-hyve devices."""
    session = _api_request("POST", f"{ORBIT_API_BASE}/session", {"session": {"email": email, "password": password}})
    token = session["orbit_session_token"]
    user_id = session["user_id"]

    devices = _api_request("GET", f"{ORBIT_API_BASE}/devices?user_id={user_id}", token=token)

    results = []
    for dev in devices:
        mac = dev.get("reference") or dev.get("mac_address", "")
        topo_id = dev.get("network_topology_id")
        if not topo_id:
            continue
        topo = _api_request("GET", f"{ORBIT_API_BASE}/network_topologies/{topo_id}", token=token)

        network_key_b64 = topo.get("network_key", "")
        network_device_id_hex = ""
        for d in topo.get("devices", []):
            if d.get("device_id") == dev["id"]:
                network_device_id_hex = d.get("network_device_id", "")

        if not network_key_b64:
            continue

        provision_version = 1
        if network_device_id_hex:
            try:
                provision_version = int(network_device_id_hex, 16) & 0xFFFF
            except ValueError:
                pass

        results.append({
            "name": dev.get("name", mac),
            "device_id": mac.replace(":", "").lower(),
            "network_key": network_key_b64,
            "provision_version": provision_version,
        })

    return results


class BhyveBLEConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._candidates: list[dict] = []

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                candidates = await self.hass.async_add_executor_job(
                    _fetch_device_credentials,
                    user_input[CONF_EMAIL],
                    user_input[CONF_PASSWORD],
                )
            except HTTPError as err:
                errors["base"] = "invalid_auth" if err.code in (401, 403) else "cannot_connect"
            except (URLError, OSError):
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error fetching credentials")
                errors["base"] = "unknown"
            else:
                if not candidates:
                    errors["base"] = "no_devices"
                elif len(candidates) == 1:
                    return self._create_entry(candidates[0])
                else:
                    self._candidates = candidates
                    return await self.async_step_pick_device()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_EMAIL): str,
                vol.Required(CONF_PASSWORD): str,
            }),
            errors=errors,
        )

    async def async_step_pick_device(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            name = user_input["device"]
            candidate = next(c for c in self._candidates if c["name"] == name)
            return self._create_entry(candidate)

        return self.async_show_form(
            step_id="pick_device",
            data_schema=vol.Schema({
                vol.Required("device"): vol.In([c["name"] for c in self._candidates]),
            }),
        )

    def _create_entry(self, candidate: dict) -> FlowResult:
        return self.async_create_entry(
            title=candidate["name"],
            data={
                CONF_DEVICE_NAME:   candidate["name"],
                CONF_DEVICE_ID:     candidate["device_id"],
                CONF_NETWORK_KEY:   candidate["network_key"],
                CONF_PROVISION_VER: candidate["provision_version"],
            },
        )

    @staticmethod
    def async_get_options_flow(entry: config_entries.ConfigEntry) -> BhyveBLEOptionsFlow:
        return BhyveBLEOptionsFlow(entry)


class BhyveBLEOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            if user_input.pop("refresh_credentials", False):
                return await self.async_step_refresh_credentials()
            return self.async_create_entry(title="", data=user_input)

        opts = self._entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(
                    CONF_DEFAULT_DURATION,
                    default=opts.get(CONF_DEFAULT_DURATION, DEFAULT_DURATION_SEC),
                ): vol.All(int, vol.Range(min=15, max=14400)),
                vol.Required(
                    CONF_POLL_INTERVAL,
                    default=opts.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
                ): vol.All(int, vol.Range(min=60, max=86400)),
                vol.Optional("refresh_credentials", default=False): bool,
            }),
        )

    async def async_step_refresh_credentials(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                candidates = await self.hass.async_add_executor_job(
                    _fetch_device_credentials,
                    user_input[CONF_EMAIL],
                    user_input[CONF_PASSWORD],
                )
            except HTTPError as err:
                errors["base"] = "invalid_auth" if err.code in (401, 403) else "cannot_connect"
            except (URLError, OSError):
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error refreshing credentials")
                errors["base"] = "unknown"
            else:
                current_device_id = self._entry.data.get(CONF_DEVICE_ID, "")
                match = next(
                    (c for c in candidates if c["device_id"] == current_device_id),
                    candidates[0] if candidates else None,
                )
                if match is None:
                    errors["base"] = "no_devices"
                else:
                    self.hass.config_entries.async_update_entry(
                        self._entry,
                        data={
                            **self._entry.data,
                            CONF_NETWORK_KEY:   match["network_key"],
                            CONF_PROVISION_VER: match["provision_version"],
                            CONF_DEVICE_NAME:   match["name"],
                        },
                    )
                    return self.async_create_entry(title="", data=self._entry.options)

        return self.async_show_form(
            step_id="refresh_credentials",
            data_schema=vol.Schema({
                vol.Required(CONF_EMAIL): str,
                vol.Required(CONF_PASSWORD): str,
            }),
            errors=errors,
            description_placeholders={
                "device_name": self._entry.data.get(CONF_DEVICE_NAME, "your device"),
            },
        )
