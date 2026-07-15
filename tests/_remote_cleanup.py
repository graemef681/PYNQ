# Copyright (C) 2026 Advanced Micro Devices, Inc.
# SPDX-License-Identifier: BSD-3-Clause

"""Shared helpers for PYNQ.remote single-client cleanup tests.

Manual setup that cannot be done safely inside pytest:

- Build and boot a target image containing the matching ``pynq-remote`` server
  from this branch. Older target servers will not have the cleanup and MMIO
  release RPCs needed by these tests.
- Run the host tests from the same PYNQ branch so the generated Python gRPC
  stubs match the target server.
- Set ``PYNQ_REMOTE_DEVICES`` to the target IP address, for example
  ``PYNQ_REMOTE_DEVICES=192.168.2.197 pytest -m remote tests/test_remote_cleanup_*.py``.
- If you want to cross-check behavior manually over SSH, watch the target-side
  ``pynq-remote`` logs while running these tests. The constructor, explicit
  cleanup, and full overlay download tests should emit cleanup RPCs.
- The GPIO coverage here is intentionally limited to the Linux sysfs GPIO path
  used by ``RemoteGPIO``. The resizer XSA is useful for MMIO and buffer flows
  but it is not a broad PL GPIO test design.
- Raw full-bitstream downloads are not used here to infer cleanup policy. Full
  reconfiguration can change MMIO behavior independently of explicit server
  cleanup, so the more stable cleanup entry points are constructor cleanup,
  explicit ``device.cleanup()``, and full ``Overlay.download()``.
"""

import contextlib
import json
import os
from pathlib import Path
import subprocess
import sys

import grpc
import numpy as np
import pytest


pytestmark = pytest.mark.remote

# Keep the convenience line from tests/test_remote.py, but still allow callers
# to override it from the shell.
os.environ.setdefault("PYNQ_REMOTE_DEVICES", "192.168.2.197")

REMOTE_ENV = "PYNQ_REMOTE_DEVICES"
RESIZER_IP = "resize_accel_0"
RESULT_PREFIX = "REMOTE_CLEANUP_IDS "


@pytest.fixture(scope="module")
def remote_ip():
    ip_env = os.environ.get(REMOTE_ENV)
    if not ip_env:
        pytest.skip(f"{REMOTE_ENV} environment variable not set")
    return ip_env.split(",")[0].strip()


@pytest.fixture(scope="module")
def overlay_path():
    path = Path(__file__).with_name("resizer.xsa")
    if not path.exists():
        pytest.skip(f"Overlay not found: {path}")
    return path


@pytest.fixture(scope="module", autouse=True)
def remote_server_ready(remote_ip):
    try:
        device = new_remote_device(remote_ip, auto_cleanup=False)
    except Exception as exc:
        pytest.skip(f"Remote device is not reachable at {remote_ip}: {exc}")
    else:
        close_quietly(device)


def new_remote_device(remote_ip, *, auto_cleanup=True):
    from pynq.pl_server.remote_device import RemoteDevice

    return RemoteDevice(ip_addr=remote_ip, auto_cleanup=auto_cleanup)


def load_resizer_overlay(device, overlay_path, *, download=True):
    from pynq import Overlay

    overlay = Overlay(str(overlay_path), device=device, download=download)
    ip_desc = overlay.ip_dict[RESIZER_IP]
    return overlay, ip_desc["phys_addr"], ip_desc["addr_range"]


def assert_remote_call_fails(callable_):
    with pytest.raises((grpc.RpcError, RuntimeError)):
        callable_()


def assert_remote_mmio_invalid(remote_mmio):
    assert_remote_call_fails(lambda: remote_mmio.read(0))


def assert_remote_mmio_id_valid(device, mmio_id):
    from pynq.remote import mmio_pb2

    response = device._stub["mmio"].read(
        mmio_pb2.ReadRequest(
            mmio_id=mmio_id,
            offset=0,
            length=4,
            word_order="little",
        )
    )
    assert response is not None


def assert_remote_mmio_id_invalid(device, mmio_id):
    from pynq.remote import mmio_pb2

    assert_remote_call_fails(
        lambda: device._stub["mmio"].read(
            mmio_pb2.ReadRequest(
                mmio_id=mmio_id,
                offset=0,
                length=4,
                word_order="little",
            )
        )
    )


def assert_remote_buffer_valid(remote_buffer):
    assert remote_buffer.physical_address is not None
    remote_buffer.flush()


def assert_remote_buffer_invalid(remote_buffer):
    assert_remote_call_fails(lambda: remote_buffer.physical_address)


def assert_remote_buffer_id_valid(device, buffer_id):
    from pynq.remote import buffer_pb2

    response = device._stub["buffer"].physical_address(
        buffer_pb2.AddressRequest(buffer_id=buffer_id)
    )
    assert response.address is not None


def assert_remote_buffer_id_invalid(device, buffer_id):
    from pynq.remote import buffer_pb2

    assert_remote_call_fails(
        lambda: device._stub["buffer"].physical_address(
            buffer_pb2.AddressRequest(buffer_id=buffer_id)
        )
    )


def assert_remote_gpio_valid(remote_gpio):
    assert remote_gpio.is_exported() is True
    assert remote_gpio.read() in (0, 1)


def assert_remote_gpio_invalid(remote_gpio):
    assert_remote_call_fails(lambda: remote_gpio.read())


def assert_remote_gpio_id_valid(device, gpio_id):
    from pynq.remote import gpio_pb2

    response = device._stub["gpio"].read(
        gpio_pb2.GpioReadRequest(gpio_id=gpio_id)
    )
    assert response.value in (0, 1)


def assert_remote_gpio_id_invalid(device, gpio_id):
    from pynq.remote import gpio_pb2

    assert_remote_call_fails(
        lambda: device._stub["gpio"].read(
            gpio_pb2.GpioReadRequest(gpio_id=gpio_id)
        )
    )


def make_remote_resources(device, base_addr):
    remote_mmio = device.mmap(base_addr, 0x1000)
    remote_mmio.read(0)

    remote_buffer = device.allocate(shape=(16,), dtype=np.uint32, cacheable=1)
    remote_buffer[:] = np.arange(16, dtype=np.uint32)
    remote_buffer.flush()

    return remote_mmio, remote_buffer


def get_remote_gpio_pin(device, user_index=0):
    from pynq import GPIO

    base_path = GPIO.get_gpio_base_path(device=device)
    npins = GPIO.get_gpio_npins(device=device)
    if not base_path or npins == 0:
        pytest.skip("Remote Linux sysfs GPIO is not available on the target")
    return GPIO.get_gpio_pin(user_index, device=device)


def gpio_sysfs_path(pin):
    return f"/sys/class/gpio/gpio{pin}"


def make_remote_gpio(device, *, direction="in", user_index=0):
    from pynq import GPIO

    pin = get_remote_gpio_pin(device, user_index=user_index)
    path = gpio_sysfs_path(pin)
    if device.exists_file(path).exists:
        pytest.skip(
            f"Remote GPIO sysfs path is already exported before the test: {path}"
        )
    gpio = GPIO(pin, direction, device=device)
    assert device.exists_file(path).exists
    return gpio, pin


def free_buffer(buffer):
    if buffer is None:
        return
    with contextlib.suppress(Exception):
        buffer.freebuffer()


def release_gpio(gpio):
    if gpio is None:
        return
    with contextlib.suppress(Exception):
        gpio.release()


def close_quietly(*objects):
    for obj in objects:
        if obj is None:
            continue
        with contextlib.suppress(Exception):
            obj.close()


def cleanup_quietly(device):
    if device is None:
        return
    with contextlib.suppress(Exception):
        device.cleanup()


def run_resizer_loopback(overlay, size=500):
    """Exercise the resizer overlay using the same flow as ``test_remote.py``."""
    device = overlay.device
    dma = overlay.axi_dma_0
    resizer = overlay.resize_accel_0

    fake_img = np.random.randint(0, 256, (size, size, 3), dtype=np.uint8)
    in_buffer = device.allocate(shape=(size, size, 3), dtype=np.uint8, cacheable=1)
    out_buffer = device.allocate(shape=(size, size, 3), dtype=np.uint8, cacheable=1)
    try:
        in_buffer[:] = fake_img

        resizer.register_map.src_rows = size
        resizer.register_map.src_cols = size
        resizer.register_map.dst_rows = size
        resizer.register_map.dst_cols = size

        dma.sendchannel.transfer(in_buffer)
        dma.recvchannel.transfer(out_buffer)
        resizer.write(0x00, 0x81)
        dma.sendchannel.wait()
        dma.recvchannel.wait()

        assert np.array_equal(in_buffer[:], out_buffer[:])
    finally:
        free_buffer(in_buffer)
        free_buffer(out_buffer)


def subprocess_env():
    env = os.environ.copy()
    repo_root = Path(__file__).resolve().parents[1]
    env["PYTHONPATH"] = os.pathsep.join(
        part for part in [str(repo_root), env.get("PYTHONPATH", "")] if part
    )
    return env


def parse_child_ids(stdout):
    for line in stdout.splitlines():
        if line.startswith(RESULT_PREFIX):
            return json.loads(line[len(RESULT_PREFIX):])
    raise AssertionError(stdout)

