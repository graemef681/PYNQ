# Copyright (C) 2026 Advanced Micro Devices, Inc.
# SPDX-License-Identifier: BSD-3-Clause

import contextlib
import gc

import pytest

from tests._remote_cleanup import (
    assert_remote_call_fails,
    assert_remote_mmio_id_invalid,
    assert_remote_mmio_id_valid,
    cleanup_quietly,
    close_quietly,
    load_resizer_overlay,
    new_remote_device,
    overlay_path,
    remote_ip,
    remote_server_ready,
)

pytestmark = pytest.mark.remote


def test_remote_mmio_close_and_destructor_release_individual_mmios(
    remote_ip, overlay_path
):
    device = None
    overlay = None
    closed_mmio = None
    survivor_mmio = None
    destructed_mmio = None
    try:
        device = new_remote_device(remote_ip, auto_cleanup=True)
        overlay, base_addr, _ = load_resizer_overlay(device, overlay_path)

        closed_mmio = device.mmap(base_addr, 0x1000)
        closed_id = closed_mmio.mmio_id
        closed_mmio.read(0)
        closed_mmio.close()
        assert_remote_mmio_id_invalid(device, closed_id)

        survivor_mmio = device.mmap(base_addr, 0x1000)
        survivor_id = survivor_mmio.mmio_id
        destructed_mmio = device.mmap(base_addr, 0x1000)
        destructed_id = destructed_mmio.mmio_id
        destructed_mmio.read(0)

        del destructed_mmio
        destructed_mmio = None
        gc.collect()

        assert_remote_mmio_id_invalid(device, destructed_id)
        assert_remote_mmio_id_valid(device, survivor_id)
    finally:
        close_quietly(closed_mmio, survivor_mmio, device)
        del overlay


def test_pynq_mmio_api_without_overlay_object_supports_global_and_local_cleanup(
    remote_ip, overlay_path
):
    """Use normal ``pynq.MMIO(..., device=...)`` syntax with no live overlay."""
    from pynq import MMIO

    device = None
    overlay = None
    mmio = None
    try:
        device = new_remote_device(remote_ip, auto_cleanup=True)
        overlay, base_addr, addr_range = load_resizer_overlay(device, overlay_path)
        overlay = None

        mmio = MMIO(base_addr, min(addr_range, 0x1000), device=device)
        mmio_id = mmio._remote_map.mmio_id
        mmio.read(0)

        response = device.cleanup()
        assert response.status is True
        assert_remote_call_fails(lambda: mmio.read(0))
        assert_remote_mmio_id_invalid(device, mmio_id)

        mmio = MMIO(base_addr, min(addr_range, 0x1000), device=device)
        mmio_id = mmio._remote_map.mmio_id
        mmio.read(0)
        mmio.close()
        assert_remote_mmio_id_invalid(device, mmio_id)

        mmio = MMIO(base_addr, min(addr_range, 0x1000), device=device)
        mmio_id = mmio._remote_map.mmio_id
        mmio.read(0)
        del mmio
        mmio = None
        gc.collect()
        assert_remote_mmio_id_invalid(device, mmio_id)
    finally:
        if mmio is not None:
            with contextlib.suppress(Exception):
                mmio.close()
        close_quietly(device)
