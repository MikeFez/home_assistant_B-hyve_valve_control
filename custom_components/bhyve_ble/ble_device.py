"""Low-level BLE communication with a b-hyve hose tap timer."""
from __future__ import annotations

import asyncio
import os
import struct
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from bleak import BleakClient
from bleak_retry_connector import establish_connection

from .const import (
    AES_CHAR_UUID,
    BHYVE_MFR_ID,
    MESSAGE_FLAG,
    MIN_DURATION_SEC,
    NETWORK_CHAR_UUID,
    READ_CHAR_UUID,
    WRITE_CHAR_UUID,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


@dataclass
class DeviceStatus:
    watering: bool = False
    battery_mv: Optional[int] = None
    run_time_remaining_sec: int = 0


def _crc16(data: bytes) -> int:
    crc = 0
    for b in data:
        idx = ((crc >> 8) ^ b) & 0xFF
        tmp = idx << 8
        for _ in range(8):
            tmp = (tmp << 1) ^ 0x1021 if tmp & 0x8000 else tmp << 1
        crc = ((crc << 8) ^ tmp) & 0xFFFF
    return crc


def _varint(v: int) -> bytes:
    buf = []
    while v > 0x7F:
        buf.append((v & 0x7F) | 0x80)
        v >>= 7
    buf.append(v)
    return bytes(buf)


def _pb(field_num: int, wire: int, data: bytes) -> bytes:
    return _varint((field_num << 3) | wire) + (data if wire == 0 else _varint(len(data)) + data)


def _inner_frame(proto: bytes) -> bytes:
    body = b"\xaa\x77\x5a\x0f" + struct.pack("<H", len(proto) + 2) + proto
    return body + struct.pack("<H", _crc16(body))


def _aes_ecb(key: bytes, block: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.backends import default_backend
    c = Cipher(algorithms.AES(key), modes.ECB(), backend=default_backend())
    e = c.encryptor()
    return e.update(block) + e.finalize()


def _aes_ctr(key: bytes, iv: bytes, ctr: int, data: bytes) -> bytes:
    result = bytearray()
    for i in range(0, len(data), 16):
        block = iv + struct.pack("<I", ctr & 0xFFFFFFFF)
        ks = _aes_ecb(key, block)
        chunk = data[i:i + 16]
        result += bytes(a ^ b for a, b in zip(ks, chunk))
        ctr = (ctr + 1) % 0xFFFFFFFF
    return bytes(result)


def _wire_frame(key: bytes, iv: bytes, enc_ctr: int, plaintext: bytes) -> bytes:
    ct = _aes_ctr(key, iv, enc_ctr, plaintext)
    chk = (MESSAGE_FLAG + len(ct) + sum(plaintext)) & 0xFFFF
    return bytes([MESSAGE_FLAG, len(ct)]) + ct + struct.pack("<H", chk)


def _decrypt_frame(key: bytes, iv: bytes, dec_ctr: int, data: bytes) -> tuple[bytes, int]:
    plen = data[1]
    ct = data[2:2 + plen]
    pt = _aes_ctr(key, iv, dec_ctr, ct)
    new_ctr = (dec_ctr + (plen + 15) // 16) % 0xFFFFFFFF
    return pt, new_ctr


def _parse_varint(data: bytes, pos: int) -> tuple[int, int]:
    result, shift = 0, 0
    while pos < len(data):
        b = data[pos]; pos += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            break
        shift += 7
    return result, pos


def _parse_status(proto: bytes) -> DeviceStatus:
    """Extract watering state and battery mV from a deviceStatusInfo proto."""
    status = DeviceStatus()
    pos = 0
    while pos < len(proto):
        try:
            tag, pos = _parse_varint(proto, pos)
        except Exception:
            break
        field_num, wire = tag >> 3, tag & 7
        if wire == 0:
            val, pos = _parse_varint(proto, pos)
            if field_num == 1:
                status.watering = val == 4  # 4 = wateringInProgress
        elif wire == 2:
            length, pos = _parse_varint(proto, pos)
            payload = proto[pos:pos + length]
            pos += length
            if field_num == 14:
                status.battery_mv = _parse_battery_mv(payload)
            elif field_num == 6:
                _parse_watering_status(payload, status)
        else:
            break
    return status


def _parse_battery_mv(data: bytes) -> Optional[int]:
    """Extract mV from sub-message at field 14 of deviceStatusInfo (sub-field 3)."""
    pos = 0
    while pos < len(data):
        try:
            tag, pos = _parse_varint(data, pos)
        except Exception:
            break
        field_num, wire = tag >> 3, tag & 7
        if wire == 0:
            val, pos = _parse_varint(data, pos)
            if field_num == 3:
                return val
        else:
            break
    return None


def _parse_watering_status(data: bytes, status: DeviceStatus) -> None:
    """Extract remaining run time from wateringStatus sub-message (field 5)."""
    pos = 0
    while pos < len(data):
        try:
            tag, pos = _parse_varint(data, pos)
        except Exception:
            break
        field_num, wire = tag >> 3, tag & 7
        if wire == 0:
            val, pos = _parse_varint(data, pos)
            if field_num == 5:
                status.run_time_remaining_sec = val
        elif wire == 2:
            length, pos = _parse_varint(data, pos)
            pos += length
        else:
            break


_msg_id = 0


def _build_message(network_key: bytes, device_id: bytes, payload_pb: bytes) -> bytes:
    global _msg_id
    _msg_id += 1
    proto = (
        _pb(1, 2, device_id) +
        _pb(7, 0, _varint(int(time.time()))) +
        _pb(95, 0, _varint(_msg_id)) +
        payload_pb
    )
    return _inner_frame(proto)


def _manual_water_pb(duration_sec: int) -> bytes:
    station = _pb(1, 0, _varint(0)) + _pb(2, 0, _varint(duration_sec))
    mmp = _pb(3, 2, station)
    tm = _pb(1, 0, _varint(2)) + _pb(2, 2, mmp)
    return _pb(14, 2, tm)


def _stop_pb() -> bytes:
    # timerMode { mode: offMode(0) } — mirrors start but with mode=0 instead of manualMode(2)
    return _pb(14, 2, _pb(1, 0, _varint(0)))


class BhyveBLEDevice:
    def __init__(
        self,
        network_key: bytes,
        device_id: bytes,
        provision_version: int,
        ble_address: str,
        hass: "HomeAssistant | None" = None,
    ) -> None:
        self._key = network_key
        self._device_id = device_id
        self._provision_version = provision_version
        self._address = ble_address
        self._hass = hass
        self._lock = asyncio.Lock()

    def _get_ble_device(self):
        from homeassistant.components import bluetooth
        return bluetooth.async_ble_device_from_address(
            self._hass, self._address, connectable=True
        )

    async def _connect_and_run(self, operation):
        """Connect, provision, AES handshake, run operation, disconnect."""
        async with self._lock:
            device = self._get_ble_device()
            if device is None:
                raise RuntimeError(f"BLE device {self._address} not found")

            client = await establish_connection(BleakClient, device, self._address)
            try:
                return await self._run_with_client(client, operation)
            finally:
                await client.disconnect()

    async def _run_with_client(self, client, operation):
        pending: list[bytes] = []

        def _on_notify(_, data: bytearray):
            pending.append(bytes(data))

        await client.start_notify(READ_CHAR_UUID, _on_notify)
        await client.write_gatt_char(
            NETWORK_CHAR_UUID,
            struct.pack("<H", self._provision_version) + self._key,
            response=True,
        )

        our_write = bytearray(os.urandom(20))
        our_write[11] = 0
        await client.write_gatt_char(AES_CHAR_UUID, bytes(our_write), response=True)
        await asyncio.sleep(0.3)

        rb = bytes(await client.read_gatt_char(AES_CHAR_UUID))
        km = rb[:4] + bytes(our_write)[4:20]
        iv = km[:12]
        enc_ctr = struct.unpack_from("<I", km, 12)[0]
        dec_ctr = struct.unpack_from("<I", km, 16)[0]

        await asyncio.sleep(0.5)

        for frame in pending:
            _, dec_ctr = _decrypt_frame(self._key, iv, dec_ctr, frame)
        pending.clear()

        results: list[DeviceStatus] = []

        def _on_notify_live(_, data: bytearray):
            nonlocal dec_ctr
            pt, dec_ctr = _decrypt_frame(self._key, iv, dec_ctr, bytes(data))
            if pt[:4] == b"\xaa\x77\x5a\x0f":
                lf = struct.unpack_from("<H", pt, 4)[0]
                inner_proto = pt[6:6 + lf - 2]
                status = _parse_status_from_message(inner_proto)
                if status is not None:
                    results.append(status)

        await client.stop_notify(READ_CHAR_UUID)
        await client.start_notify(READ_CHAR_UUID, _on_notify_live)

        result = await operation(client, iv, enc_ctr, results)
        await asyncio.sleep(5)
        return result, results

    async def start_watering(self, duration_sec: int) -> DeviceStatus:
        duration_sec = max(duration_sec, MIN_DURATION_SEC)

        async def op(client, iv, enc_ctr, results):
            plaintext = _build_message(self._key, self._device_id, _manual_water_pb(duration_sec))
            await client.write_gatt_char(
                WRITE_CHAR_UUID,
                _wire_frame(self._key, iv, enc_ctr, plaintext),
                response=True,
            )

        _, results = await self._connect_and_run(op)
        return results[-1] if results else DeviceStatus(watering=True)

    async def stop_watering(self) -> DeviceStatus:
        async def op(client, iv, enc_ctr, results):
            plaintext = _build_message(self._key, self._device_id, _stop_pb())
            await client.write_gatt_char(
                WRITE_CHAR_UUID,
                _wire_frame(self._key, iv, enc_ctr, plaintext),
                response=True,
            )

        _, results = await self._connect_and_run(op)
        return results[-1] if results else DeviceStatus(watering=False)

    async def poll_status(self) -> DeviceStatus:
        """Connect just to receive the spontaneous status push (battery + state)."""
        async def op(client, iv, enc_ctr, results):
            pass  # no write needed — spontaneous push comes during AES

        _, results = await self._connect_and_run(op)
        return results[-1] if results else DeviceStatus()


def _parse_status_from_message(proto: bytes) -> Optional[DeviceStatus]:
    """Find field 16 (deviceStatusInfo) in an OrbitPbApi_Message and parse it."""
    pos = 0
    while pos < len(proto):
        try:
            tag, pos = _parse_varint(proto, pos)
        except Exception:
            break
        field_num, wire = tag >> 3, tag & 7
        if wire == 0:
            _, pos = _parse_varint(proto, pos)
        elif wire == 2:
            length, pos = _parse_varint(proto, pos)
            payload = proto[pos:pos + length]
            pos += length
            if field_num == 16:
                return _parse_status(payload)
        else:
            break
    return None
