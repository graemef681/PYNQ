# Copyright (C) 2026 Advanced Micro Devices, Inc.
# SPDX-License-Identifier: BSD-3-Clause

import gc

import pytest

from tests._remote_cleanup import (
    assert_remote_gpio_id_invalid,
    assert_remote_gpio_id_valid,
    assert_remote_gpio_invalid,
    assert_remote_gpio_valid,
    cleanup_quietly,
    close_quietly,
    gpio_sysfs_path,
    make_remote_gpio,
    new_remote_device,
    remote_ip,
    remote_server_ready,
    release_gpio,
)

pytestmark = pytest.mark.remote


def test_remote_gpio_release_and_destructor_release_individual_gpios(remote_ip):
    device = None
    released_gpio = None
    survivor_gpio = None
    destructed_gpio = None
    try:
        device = new_remote_device(remote_ip, auto_cleanup=True)

        released_gpio, released_pin = make_remote_gpio(device, user_index=0)
        released_id = released_gpio._gpio_id
        assert_remote_gpio_valid(released_gpio)
        released_gpio.release()
        assert_remote_gpio_id_invalid(device, released_id)
        assert device.exists_file(gpio_sysfs_path(released_pin)).exists is False

        survivor_gpio, survivor_pin = make_remote_gpio(device, user_index=0)
        survivor_id = survivor_gpio._gpio_id
        assert_remote_gpio_valid(survivor_gpio)

        destructed_gpio, destructed_pin = make_remote_gpio(device, user_index=1)
        destructed_id = destructed_gpio._gpio_id
        assert_remote_gpio_valid(destructed_gpio)

        del destructed_gpio
        destructed_gpio = None
        gc.collect()

        assert_remote_gpio_id_invalid(device, destructed_id)
        assert_remote_gpio_id_valid(device, survivor_id)
        assert device.exists_file(gpio_sysfs_path(destructed_pin)).exists is False
        assert device.exists_file(gpio_sysfs_path(survivor_pin)).exists is True
    finally:
        release_gpio(released_gpio)
        release_gpio(survivor_gpio)
        release_gpio(destructed_gpio)
        close_quietly(device)


def test_remote_gpio_global_cleanup_releases_server_handle_and_sysfs_path(remote_ip):
    device = None
    stale_gpio = None
    fresh_gpio = None
    try:
        device = new_remote_device(remote_ip, auto_cleanup=True)

        stale_gpio, pin = make_remote_gpio(device, user_index=0)
        stale_id = stale_gpio._gpio_id
        assert_remote_gpio_valid(stale_gpio)
        assert device.exists_file(gpio_sysfs_path(pin)).exists is True

        response = device.cleanup()
        assert response.status is True

        assert_remote_gpio_invalid(stale_gpio)
        assert_remote_gpio_id_invalid(device, stale_id)
        assert device.exists_file(gpio_sysfs_path(pin)).exists is False

        fresh_gpio, fresh_pin = make_remote_gpio(device, user_index=0)
        assert fresh_pin == pin
        assert fresh_gpio._gpio_id != stale_id
        assert_remote_gpio_valid(fresh_gpio)
    finally:
        cleanup_quietly(device)
        release_gpio(stale_gpio)
        release_gpio(fresh_gpio)
        close_quietly(device)
