# Copyright (C) 2026 Advanced Micro Devices, Inc.
# SPDX-License-Identifier: BSD-3-Clause

"""Manual step 4 after ``test_remote_cleanup_03_prepare_autocleanup.py``.

Run these two modules in the same ``pytest -s`` process and in filename order.
This module constructs a fresh ``RemoteDevice(auto_cleanup=True)`` and checks
that constructor-time cleanup invalidates the still-live Python objects from the
previous module.
"""

import os
import sys

import grpc
import pytest

import tests.test_remote_cleanup_03_prepare_autocleanup as prepared_state


os.environ.setdefault("PYNQ_REMOTE_DEVICES", "192.168.2.197")

pytestmark = pytest.mark.remote


def test_remote_cleanup_04_autocleanup_on_new_device():
    if not sys.stdin.isatty():
        pytest.skip("Run this manual test with `pytest -s` so the checkpoints can pause.")

    if not prepared_state.STATE:
        pytest.skip(
            "No prepared stale state found. Run "
            "`test_remote_cleanup_03_prepare_autocleanup.py` first in the same pytest process."
        )

    remote_env = os.environ.get("PYNQ_REMOTE_DEVICES", "")
    if not remote_env:
        pytest.skip("PYNQ_REMOTE_DEVICES environment variable not set")
    remote_ip = remote_env.split(",")[0].strip()

    from pynq.remote import buffer_pb2, gpio_pb2, mmio_pb2
    from pynq.pl_server.remote_device import RemoteDevice

    cleanup_device = None
    try:
        cleanup_device = RemoteDevice(ip_addr=remote_ip, auto_cleanup=True)

        input(
            "Constructor auto-cleanup has already run on the new device. Check the "
            "board logs now, then press Enter to let pytest verify that the stale "
            "objects and IDs from the previous module are gone."
        )

        with pytest.raises((grpc.RpcError, RuntimeError)):
            prepared_state.STATE["mmio"].read(0)
        with pytest.raises((grpc.RpcError, RuntimeError)):
            prepared_state.STATE["buffer"].physical_address

        with pytest.raises((grpc.RpcError, RuntimeError)):
            cleanup_device._stub["mmio"].read(
                mmio_pb2.ReadRequest(
                    mmio_id=prepared_state.STATE["mmio_id"],
                    offset=0,
                    length=4,
                    word_order="little",
                )
            )
        with pytest.raises((grpc.RpcError, RuntimeError)):
            cleanup_device._stub["buffer"].physical_address(
                buffer_pb2.AddressRequest(buffer_id=prepared_state.STATE["buffer_id"])
            )

        if prepared_state.STATE["gpio"] is not None:
            with pytest.raises((grpc.RpcError, RuntimeError)):
                prepared_state.STATE["gpio"].read()
            with pytest.raises((grpc.RpcError, RuntimeError)):
                cleanup_device._stub["gpio"].read(
                    gpio_pb2.GpioReadRequest(gpio_id=prepared_state.STATE["gpio_id"])
                )
            assert (
                cleanup_device.exists_file(prepared_state.STATE["gpio_path"]).exists is False
            )
    finally:
        if cleanup_device is not None:
            try:
                cleanup_device.close()
            except Exception:
                pass

        for key in ["gpio", "mmio", "buffer", "device"]:
            obj = prepared_state.STATE.get(key)
            if obj is None:
                continue
            try:
                if key == "gpio":
                    obj.release()
                elif key == "buffer":
                    obj.freebuffer()
                else:
                    obj.close()
            except Exception:
                pass
        prepared_state.STATE.clear()

