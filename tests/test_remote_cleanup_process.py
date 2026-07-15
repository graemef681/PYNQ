# Copyright (C) 2026 Advanced Micro Devices, Inc.
# SPDX-License-Identifier: BSD-3-Clause

import subprocess
import sys

import pytest

from tests._remote_cleanup import (
    RESULT_PREFIX,
    assert_remote_buffer_id_invalid,
    assert_remote_buffer_id_valid,
    assert_remote_gpio_id_invalid,
    assert_remote_gpio_id_valid,
    assert_remote_mmio_id_invalid,
    assert_remote_mmio_id_valid,
    close_quietly,
    get_remote_gpio_pin,
    gpio_sysfs_path,
    load_resizer_overlay,
    new_remote_device,
    overlay_path,
    parse_child_ids,
    remote_ip,
    remote_server_ready,
    subprocess_env,
)

pytestmark = pytest.mark.remote


def test_graceful_process_exit_runs_atexit_cleanup(remote_ip, overlay_path):
    device = None
    overlay = None
    probe_device = None
    try:
        device = new_remote_device(remote_ip, auto_cleanup=True)
        overlay, base_addr, _ = load_resizer_overlay(device, overlay_path)
        gpio_pin = get_remote_gpio_pin(device, user_index=0)
        if device.exists_file(gpio_sysfs_path(gpio_pin)).exists:
            pytest.skip("Remote GPIO sysfs path is already exported before the test")

        child_script = r"""
import json
import sys

import numpy as np

from pynq import GPIO
from pynq.pl_server.remote_device import RemoteDevice

ip_addr = sys.argv[1]
base_addr = int(sys.argv[2], 0)
gpio_pin = int(sys.argv[3], 0)

device = RemoteDevice(ip_addr=ip_addr, auto_cleanup=True)
remote_mmio = device.mmap(base_addr, 0x1000)
remote_mmio.read(0)

remote_buffer = device.allocate(shape=(16,), dtype=np.uint32, cacheable=1)
remote_buffer[:] = np.arange(16, dtype=np.uint32)
remote_buffer.flush()

remote_gpio = GPIO(gpio_pin, "in", device=device)
remote_gpio.read()

print(
    "REMOTE_CLEANUP_IDS "
    + json.dumps(
        {
            "mmio_id": remote_mmio.mmio_id,
            "buffer_id": remote_buffer.buffer_id,
            "gpio_id": remote_gpio._gpio_id,
            "gpio_pin": gpio_pin,
        }
    ),
    flush=True,
)
"""

        result = subprocess.run(
            [
                sys.executable,
                "-c",
                child_script,
                remote_ip,
                hex(base_addr),
                str(gpio_pin),
            ],
            check=True,
            capture_output=True,
            text=True,
            env=subprocess_env(),
        )
        ids = parse_child_ids(result.stdout)
        assert ids is not None, result.stdout

        probe_device = new_remote_device(remote_ip, auto_cleanup=False)
        assert_remote_mmio_id_invalid(probe_device, ids["mmio_id"])
        assert_remote_buffer_id_invalid(probe_device, ids["buffer_id"])
        assert_remote_gpio_id_invalid(probe_device, ids["gpio_id"])
        assert probe_device.exists_file(gpio_sysfs_path(ids["gpio_pin"])).exists is False
    finally:
        close_quietly(probe_device, device)
        del overlay


def test_hard_host_restart_orphans_resources_until_next_constructor_cleanup(
    remote_ip, overlay_path
):
    device = None
    overlay = None
    probe_device = None
    cleanup_device = None
    try:
        device = new_remote_device(remote_ip, auto_cleanup=True)
        overlay, base_addr, _ = load_resizer_overlay(device, overlay_path)
        gpio_pin = get_remote_gpio_pin(device, user_index=0)
        if device.exists_file(gpio_sysfs_path(gpio_pin)).exists:
            pytest.skip("Remote GPIO sysfs path is already exported before the test")

        child_script = r"""
import json
import os
import sys

import numpy as np

from pynq import GPIO
from pynq.pl_server.remote_device import RemoteDevice

ip_addr = sys.argv[1]
base_addr = int(sys.argv[2], 0)
gpio_pin = int(sys.argv[3], 0)

device = RemoteDevice(ip_addr=ip_addr, auto_cleanup=False)
remote_mmio = device.mmap(base_addr, 0x1000)
remote_mmio.read(0)

remote_buffer = device.allocate(shape=(16,), dtype=np.uint32, cacheable=1)
remote_buffer[:] = np.arange(16, dtype=np.uint32)
remote_buffer.flush()

remote_gpio = GPIO(gpio_pin, "in", device=device)
remote_gpio.read()

print(
    "REMOTE_CLEANUP_IDS "
    + json.dumps(
        {
            "mmio_id": remote_mmio.mmio_id,
            "buffer_id": remote_buffer.buffer_id,
            "gpio_id": remote_gpio._gpio_id,
            "gpio_pin": gpio_pin,
        }
    ),
    flush=True,
)

# Intentionally bypass Python destructors and atexit handlers, like a hard
# host-kernel death.
os._exit(0)
"""

        result = subprocess.run(
            [
                sys.executable,
                "-c",
                child_script,
                remote_ip,
                hex(base_addr),
                str(gpio_pin),
            ],
            check=True,
            capture_output=True,
            text=True,
            env=subprocess_env(),
        )
        ids = parse_child_ids(result.stdout)
        assert ids is not None, result.stdout

        probe_device = new_remote_device(remote_ip, auto_cleanup=False)
        assert_remote_mmio_id_valid(probe_device, ids["mmio_id"])
        assert_remote_buffer_id_valid(probe_device, ids["buffer_id"])
        assert_remote_gpio_id_valid(probe_device, ids["gpio_id"])
        assert probe_device.exists_file(gpio_sysfs_path(ids["gpio_pin"])).exists is True

        cleanup_device = new_remote_device(remote_ip, auto_cleanup=True)
        assert_remote_mmio_id_invalid(cleanup_device, ids["mmio_id"])
        assert_remote_buffer_id_invalid(cleanup_device, ids["buffer_id"])
        assert_remote_gpio_id_invalid(cleanup_device, ids["gpio_id"])
        assert cleanup_device.exists_file(gpio_sysfs_path(ids["gpio_pin"])).exists is False
    finally:
        close_quietly(probe_device, cleanup_device, device)
        del overlay
