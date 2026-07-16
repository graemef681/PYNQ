# Copyright (C) 2026 Advanced Micro Devices, Inc.
# SPDX-License-Identifier: BSD-3-Clause

"""Manual step 1 after ``test_remote.py``.

Run with ``pytest -s`` so the checkpoints pause for board-log inspection.
This module intentionally stays simple and self-contained.
"""

import gc
import os
from pathlib import Path
import sys

import grpc
import numpy as np
import pytest


os.environ.setdefault("PYNQ_REMOTE_DEVICES", "192.168.2.197")

pytestmark = pytest.mark.remote


def test_remote_cleanup_01_individual_delete():
    if not sys.stdin.isatty():
        pytest.skip("Run this manual test with `pytest -s` so the checkpoints can pause.")

    remote_env = os.environ.get("PYNQ_REMOTE_DEVICES", "")
    if not remote_env:
        pytest.skip("PYNQ_REMOTE_DEVICES environment variable not set")
    remote_ip = remote_env.split(",")[0].strip()

    overlay_path = Path(__file__).with_name("resizer.xsa")
    if not overlay_path.exists():
        pytest.skip(f"Overlay not found: {overlay_path}")

    from pynq import Overlay
    from pynq.pl_server.remote_device import RemoteDevice
    from pynq.remote import buffer_pb2, mmio_pb2

    device = None
    overlay = None
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

        print(f"Created remote MMIO: {mmio_id}")
        print(f"Created remote buffer: {buffer_id}")
        input(
            "Check the board logs for MMIO/buffer creation, then press Enter to "
            "delete the Python objects individually."
        )

        del remote_mmio
        del remote_buffer
        gc.collect()

        input(
            "Check the board logs for individual MMIO/buffer release, then press "
            "Enter to let pytest verify that both remote IDs are gone."
        )

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
    finally:
        if device is not None:
            try:
                device.close()
            except Exception:
                pass
        del overlay

