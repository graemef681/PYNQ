.. _remote_resource_cleanup:

Remote Resource Cleanup
=======================

PYNQ.remote clients create target-side resources through the long-running
``pynq-remote`` server. Buffers allocate target memory, MMIO objects create
server-side mappings, and GPIO objects create both server handles and Linux
sysfs exports. These resources can outlive the host Python objects that created
them if a client exits unexpectedly or a Jupyter kernel is restarted.

Automatic Cleanup
-----------------

``RemoteDevice`` performs cleanup automatically by default. When
``auto_cleanup=True``, a new ``RemoteDevice`` connection asks the target server
to release stale buffers, MMIO mappings, and GPIO handles before the client
starts using the device. The same best-effort cleanup is also registered for
normal Python interpreter shutdown.

Full ``Overlay.download()`` also performs remote cleanup before programming PL
clocks and downloading the overlay when the overlay is using a remote device
with ``auto_cleanup=True``. Lower-level bitstream and device download paths do
not perform this extra cleanup; callers using those APIs are responsible for
their own resource lifetime.

Manual Cleanup
--------------

Call ``device.cleanup()`` to explicitly release server-side remote resources:

.. code-block:: python

   from pynq.pl_server.remote_device import RemoteDevice

   device = RemoteDevice(ip_addr="192.168.2.99")
   device.cleanup()

Cleanup is global to the target-side ``pynq-remote`` server. It is intended for
single-client workflows, including repeated test runs and host kernel restarts.
For controlled experiments where a new client must not clean resources created
by an existing client, construct the device with ``auto_cleanup=False``:

.. code-block:: python

   device = RemoteDevice(ip_addr="192.168.2.99", auto_cleanup=False)

This opt-out does not provide safe multi-client isolation. Any client can still
call global cleanup, download an overlay, change registers, or release shared
GPIO state.

Per-Object Release
------------------

Remote resources can also be released individually:

* ``RemoteBuffer.freebuffer()`` releases target-side allocated memory.
* ``RemoteMMIO.close()`` releases the server-side MMIO mapping.
* ``MMIO.close()`` releases the backing remote mapping when the ``MMIO`` object
  is using a remote device.
* ``RemoteGPIO.release()`` or ``RemoteGPIO.close()`` releases the remote GPIO
  handle and unexports the GPIO.
* ``RemoteDevice.close()`` performs best-effort cleanup for a remote client with
  ``auto_cleanup=True``.

Explicit release is preferred for long-running programs. Destructors provide a
best-effort fallback, but Python object finalization is not a substitute for
clear ownership in application code.

Stale Handles
-------------

Remote buffer, MMIO, and GPIO handles are opaque strings. After global cleanup,
new handles are allocated in a fresh cleanup epoch so old host objects cannot
accidentally alias resources created later.

Operations on malformed handles return ``INVALID_ARGUMENT`` from gRPC. Handles
from an older cleanup epoch, or handles whose resource has already been
released, return ``NOT_FOUND``. Release-style operations are idempotent for
stale or already released resources.
