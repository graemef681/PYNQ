# Copyright (C) 2026 Advanced Micro Devices, Inc.
# SPDX-License-Identifier: BSD-3-Clause

"""Manual step 2 after ``test_remote_cleanup_01_individual_delete.py``.

Run with ``pytest -s`` so the checkpoints pause for board-log inspection.
This test uses ``device.cleanup()`` instead of individual object destruction.
"""

import os
from pathlib import Path
import sys

import grpc
import numpy as np
import pytest


os.environ.setdefault("PYNQ_REMOTE_DEVICES", "192.168.2.197")

pytestmark = pytest.mark.remote


def test_remote_cleanup_02_device_cleanup():
    if not sys.stdin.isatty():
        pytest.skip("Run this manual test with `pytest -s` so the checkpoints can pause.")

    remote_env = os.environ.get("PYNQ_REMOTE_DEVICES", "")
    if not remote_env:
        pytest.skip("PYNQ_REMOTE_DEVICES environment variable not set")
    remote_ip = remote_env.split(",")[0].strip()

    overlay_path = Path(__file__).with_name("resizer.xsa")
    if not overlay_path.exists():
        pytest.skip(f"Overlay not found: {overlay_path}")

    from pynq import GPIO, Overlay
    from pynq.pl_server.remote_device import RemoteDevice
    from pynq.remote import buffer_pb2, gpio_pb2, mmio_pb2

    device = None
    overlay = None
    gpio = None
    gpio_id = None
    gpio_path = None
    try:
        device = RemoteDevice(ip_addr=remote_ip, auto_cleanup=True)
        overlay = Overlay(str(overlay_path), device=device)
        base_addr = overlay.ip_dict["resize_accel_0"]["phys_addr"]

        remote_mmio = device.mmap(base_addr, 0x1000)
        mmio_id = remote_mmio.mmio_id
        remote_mmio.read(0)

        remote_buffer = device.allocate(shape=(16,), dtype=np.uint32, cacheable=1)
        buffer_id = remote_buffer.buffer_id
        remote_buffer[:] = np.arange(16, dtype=np.uint32)
        remote_buffer.flush()

        base_path = GPIO.get_gpio_base_path(device=device)
        npins = GPIO.get_gpio_npins(device=device)
        if base_path and npins:
            gpio_pin = GPIO.get_gpio_pin(0, device=device)
            gpio_path = f"/sys/class/gpio/gpio{gpio_pin}"
            if not device.exists_file(gpio_path).exists:
                gpio = GPIO(gpio_pin, "in", device=device)
                gpio_id = gpio._gpio_id
                gpio.read()
            else:
                print(f"Skipping GPIO creation because {gpio_path} is already exported.")
        else:
            print("Skipping GPIO creation because Linux sysfs GPIO is not available.")

        print(f"Created remote MMIO: {mmio_id}")
        print(f"Created remote buffer: {buffer_id}")
        if gpio_id is not None:
            print(f"Created remote GPIO: {gpio_id} at {gpio_path}")
        input(
            "Check the board logs for resource creation, then press Enter to call "
            "device.cleanup()."
        )

        response = device.cleanup()
        assert response.status is True

        input(
            "Check the board logs for the Cleanup Request, then press Enter to let "
            "pytest verify that the stale objects and IDs are all invalid."
        )

        with pytest.raises((grpc.RpcError, RuntimeError)):
            remote_mmio.read(0)
        with pytest.raises((grpc.RpcError, RuntimeError)):
            remote_buffer.physical_address

        with pytest.raises((grpc.RpcError, RuntimeError)):
            device._stub["mmio"].read(
                mmio_pb2.ReadRequest(
                    mmio_id=mmio_id,
                    offset=0,
                    length=4,
                    word_order="little",
                )
            )
        with pytest.raises((grpc.RpcError, RuntimeError)):
            device._stub["buffer"].physical_address(
                buffer_pb2.AddressRequest(buffer_id=buffer_id)
            )

        if gpio is not None:
            with pytest.raises((grpc.RpcError, RuntimeError)):
                gpio.read()
            with pytest.raises((grpc.RpcError, RuntimeError)):
                device._stub["gpio"].read(gpio_pb2.GpioReadRequest(gpio_id=gpio_id))
            assert device.exists_file(gpio_path).exists is False
    finally:
        if gpio is not None:
            try:
                gpio.release()
            except Exception:
                pass
        if device is not None:
            try:
                device.close()
            except Exception:
                pass
        del overlay

