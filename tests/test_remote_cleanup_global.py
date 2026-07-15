# Copyright (C) 2026 Advanced Micro Devices, Inc.
# SPDX-License-Identifier: BSD-3-Clause

import inspect

import pytest

from tests._remote_cleanup import (
    assert_remote_buffer_id_invalid,
    assert_remote_buffer_invalid,
    assert_remote_buffer_valid,
    assert_remote_mmio_id_invalid,
    assert_remote_mmio_invalid,
    cleanup_quietly,
    close_quietly,
    free_buffer,
    load_resizer_overlay,
    make_remote_resources,
    new_remote_device,
    overlay_path,
    remote_ip,
    remote_server_ready,
    run_resizer_loopback,
)

pytestmark = pytest.mark.remote


def test_auto_cleanup_default_and_false_mode(remote_ip, overlay_path):
    """``auto_cleanup`` defaults on, and ``False`` disables implicit cleanup."""
    from pynq.pl_server.remote_device import RemoteDevice

    assert inspect.signature(RemoteDevice).parameters["auto_cleanup"].default is True

    setup_device = None
    no_cleanup_device = None
    overlay = None
    stale_mmio = None
    stale_buffer = None
    try:
        setup_device = new_remote_device(remote_ip, auto_cleanup=True)
        overlay, base_addr, _ = load_resizer_overlay(setup_device, overlay_path)
        stale_mmio, stale_buffer = make_remote_resources(setup_device, base_addr)

        no_cleanup_device = new_remote_device(remote_ip, auto_cleanup=False)
        assert no_cleanup_device.auto_cleanup is False

        stale_mmio.read(0)
        assert_remote_buffer_valid(stale_buffer)

        no_cleanup_device.close()
        stale_mmio.read(0)
        assert_remote_buffer_valid(stale_buffer)

        response = no_cleanup_device.cleanup()
        assert response.status is True
        assert_remote_mmio_invalid(stale_mmio)
        assert_remote_buffer_invalid(stale_buffer)
    finally:
        free_buffer(stale_buffer)
        close_quietly(no_cleanup_device, setup_device)
        del overlay


def test_remote_device_constructor_triggers_global_cleanup(remote_ip, overlay_path):
    setup_device = None
    cleanup_device = None
    overlay = None
    stale_mmio = None
    stale_buffer = None
    try:
        setup_device = new_remote_device(remote_ip, auto_cleanup=True)
        overlay, base_addr, _ = load_resizer_overlay(setup_device, overlay_path)
        stale_mmio, stale_buffer = make_remote_resources(setup_device, base_addr)
        stale_mmio_id = stale_mmio.mmio_id
        stale_buffer_id = stale_buffer.buffer_id

        cleanup_device = new_remote_device(remote_ip, auto_cleanup=True)

        assert_remote_mmio_invalid(stale_mmio)
        assert_remote_buffer_invalid(stale_buffer)
        assert_remote_mmio_id_invalid(cleanup_device, stale_mmio_id)
        assert_remote_buffer_id_invalid(cleanup_device, stale_buffer_id)
    finally:
        free_buffer(stale_buffer)
        close_quietly(cleanup_device, setup_device)
        del overlay


def test_explicit_global_cleanup_releases_mmio_and_buffers_and_design_still_runs(
    remote_ip, overlay_path
):
    device = None
    overlay = None
    stale_mmio = None
    stale_buffer = None
    fresh_mmio = None
    fresh_buffer = None
    try:
        device = new_remote_device(remote_ip, auto_cleanup=True)
        overlay, base_addr, _ = load_resizer_overlay(device, overlay_path)
        stale_mmio, stale_buffer = make_remote_resources(device, base_addr)
        stale_mmio_id = stale_mmio.mmio_id
        stale_buffer_id = stale_buffer.buffer_id

        response = device.cleanup()
        assert response.status is True

        assert_remote_mmio_invalid(stale_mmio)
        assert_remote_buffer_invalid(stale_buffer)
        assert_remote_mmio_id_invalid(device, stale_mmio_id)
        assert_remote_buffer_id_invalid(device, stale_buffer_id)

        fresh_mmio, fresh_buffer = make_remote_resources(device, base_addr)
        assert fresh_mmio.mmio_id != stale_mmio_id
        assert fresh_buffer.buffer_id != stale_buffer_id
        run_resizer_loopback(overlay)
    finally:
        close_quietly(fresh_mmio)
        free_buffer(stale_buffer)
        free_buffer(fresh_buffer)
        close_quietly(device)
        del overlay


def test_full_overlay_download_triggers_cleanup_and_design_still_runs(
    remote_ip, overlay_path
):
    device = None
    first_overlay = None
    reloaded_overlay = None
    stale_mmio = None
    stale_buffer = None
    try:
        device = new_remote_device(remote_ip, auto_cleanup=True)
        first_overlay, base_addr, _ = load_resizer_overlay(device, overlay_path)
        stale_mmio, stale_buffer = make_remote_resources(device, base_addr)
        stale_mmio_id = stale_mmio.mmio_id
        stale_buffer_id = stale_buffer.buffer_id

        reloaded_overlay, _, _ = load_resizer_overlay(device, overlay_path)

        assert_remote_mmio_invalid(stale_mmio)
        assert_remote_buffer_invalid(stale_buffer)
        assert_remote_mmio_id_invalid(device, stale_mmio_id)
        assert_remote_buffer_id_invalid(device, stale_buffer_id)
        run_resizer_loopback(reloaded_overlay)
    finally:
        cleanup_quietly(device)
        free_buffer(stale_buffer)
        close_quietly(device)
        del first_overlay
        del reloaded_overlay
