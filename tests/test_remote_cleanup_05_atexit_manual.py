# Copyright (C) 2026 Advanced Micro Devices, Inc.
# SPDX-License-Identifier: BSD-3-Clause

"""Manual final step for checking ``atexit`` cleanup.

Run this module last and with ``pytest -s``. It deliberately leaves one
``RemoteDevice(auto_cleanup=True)`` alive in module globals so that when the
pytest process exits, the device's registered ``atexit`` cleanup hook should
emit a final Cleanup Request on the board.
"""

import os
from pathlib import Path
import sys

import numpy as np
import pytest


os.environ.setdefault("PYNQ_REMOTE_DEVICES", "192.168.2.197")

pytestmark = pytest.mark.remote

ATEXIT_STATE = {}


def test_remote_cleanup_05_atexit_manual():
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

    device = None
    gpio = None
    try:
        device = RemoteDevice(ip_addr=remote_ip, auto_cleanup=True)
        overlay = Overlay(str(overlay_path), device=device)
        base_addr = overlay.ip_dict["resize_accel_0"]["phys_addr"]

        remote_mmio = device.mmap(base_addr, 0x1000)
        remote_mmio.read(0)

        remote_buffer = device.allocate(shape=(16,), dtype=np.uint32, cacheable=1)
        remote_buffer[:] = np.arange(16, dtype=np.uint32)
        remote_buffer.flush()

        gpio_id = None
        gpio_path = None
        base_path = GPIO.get_gpio_base_path(device=device)
        npins = GPIO.get_gpio_npins(device=device)
        if base_path and npins:
            gpio_pin = GPIO.get_gpio_pin(0, device=device)
            gpio_path = f"/sys/class/gpio/gpio{gpio_pin}"
            if not device.exists_file(gpio_path).exists:
                gpio = GPIO(gpio_pin, "in", device=device)
                gpio.read()
                gpio_id = gpio._gpio_id
            else:
                print(f"Skipping GPIO creation because {gpio_path} is already exported.")
        else:
            print("Skipping GPIO creation because Linux sysfs GPIO is not available.")

        ATEXIT_STATE.clear()
        ATEXIT_STATE.update(
            {
                "device": device,
                "mmio": remote_mmio,
                "buffer": remote_buffer,
                "gpio": gpio,
                "overlay": overlay,
                "mmio_id": remote_mmio.mmio_id,
                "buffer_id": remote_buffer.buffer_id,
                "gpio_id": gpio_id,
            }
        )

        print(f"Live remote MMIO for atexit check: {ATEXIT_STATE['mmio_id']}")
        print(f"Live remote buffer for atexit check: {ATEXIT_STATE['buffer_id']}")
        if ATEXIT_STATE["gpio_id"] is not None:
            print(f"Live remote GPIO for atexit check: {ATEXIT_STATE['gpio_id']}")

        input(
            "Check the board logs for the live resources now. After you press "
            "Enter, the test will finish but keep these objects alive in module "
            "globals. When the pytest process exits after this module, watch the "
            "board logs for the final atexit-triggered Cleanup Request."
        )

        assert remote_mmio.read(0) is not None
        assert remote_buffer.physical_address is not None
        if gpio is not None:
            assert gpio.read() in (0, 1)
    except Exception:
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
        ATEXIT_STATE.clear()
        raise
