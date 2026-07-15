# Copyright (C) 2026 Advanced Micro Devices, Inc.
# SPDX-License-Identifier: BSD-3-Clause

import gc

import numpy as np
import pytest

from tests._remote_cleanup import (
    assert_remote_buffer_id_invalid,
    assert_remote_buffer_id_valid,
    close_quietly,
    free_buffer,
    load_resizer_overlay,
    new_remote_device,
    overlay_path,
    remote_ip,
    remote_server_ready,
)

pytestmark = pytest.mark.remote


def test_remote_buffer_freebuffer_and_destructor_release_individual_buffers(
    remote_ip, overlay_path
):
    device = None
    overlay = None
    freed_buffer = None
    survivor_buffer = None
    destructed_buffer = None
    try:
        device = new_remote_device(remote_ip, auto_cleanup=True)
        overlay, _, _ = load_resizer_overlay(device, overlay_path)

        freed_buffer = device.allocate(shape=(16,), dtype=np.uint32, cacheable=1)
        freed_id = freed_buffer.buffer_id
        freed_buffer[:] = np.arange(16, dtype=np.uint32)
        freed_buffer.flush()
        freed_buffer.freebuffer()
        assert_remote_buffer_id_invalid(device, freed_id)

        survivor_buffer = device.allocate(shape=(16,), dtype=np.uint32, cacheable=1)
        survivor_id = survivor_buffer.buffer_id
        survivor_buffer[:] = np.arange(16, dtype=np.uint32)
        survivor_buffer.flush()

        destructed_buffer = device.allocate(shape=(16,), dtype=np.uint32, cacheable=1)
        destructed_id = destructed_buffer.buffer_id
        destructed_buffer[:] = np.arange(16, dtype=np.uint32)
        destructed_buffer.flush()

        del destructed_buffer
        destructed_buffer = None
        gc.collect()

        assert_remote_buffer_id_invalid(device, destructed_id)
        assert_remote_buffer_id_valid(device, survivor_id)
    finally:
        free_buffer(freed_buffer)
        free_buffer(survivor_buffer)
        free_buffer(destructed_buffer)
        close_quietly(device)
        del overlay
