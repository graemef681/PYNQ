![pynq_logo](https://github.com/Xilinx/PYNQ/raw/master/logo.png)

![python](https://github.com/Xilinx/PYNQ/workflows/Python/badge.svg)

PYNQ is an open-source project from Xilinx that makes it easy to design embedded systems with Zynq All Programmable Systems on Chips (APSoCs). Using the Python language and libraries, designers can exploit the benefits of programmable logic and microprocessors in Zynq to build more capable and exciting embedded systems.
PYNQ users can now create high performance embedded applications with
-	parallel hardware execution
-	high frame-rate video processing
-	hardware accelerated algorithms
-	real-time signal processing
-	high bandwidth IO
-	low latency control

See the <a href="http://www.pynq.io/" target="_blank">PYNQ webpage</a> for an overview of the project, and find <a href="http://pynq.readthedocs.io" target="_blank">documentation on ReadTheDocs</a> to get started.

## Precompiled Image

The project currently supports <a href="https://www.pynq.io/boards.html" target="_blank">multiple boards</a>.

You can download a precompiled image, write the image to a micro SD card, and boot the board from the micro SD card.

## Quick Start

See the <a href="http://pynq.readthedocs.io/en/latest/getting_started.html" target="_blank">Quickstart guide</a> for details on writing the image to an SD card, and getting started with a PYNQ-enabled board.

## Python Source Code

All Python code for the `pynq` package can be found in the `/pynq` folder. This folder can be found on the board after the board boots with the precompiled image.

To update your PYNQ SD card to the latest `pynq` package, you can run the following command from a terminal connected to your board:

```console
sudo pip3 install --upgrade --upgrade-strategy only-if-needed pynq
```

The `--upgrade-strategy only-if-needed` option will upgrade dependencies only in case they do not satisfy the requirements, which will speed-up the installation process and also avoid possible upgrade errors.

SDK software projects and Python-C source codes are also stored along with the Python source code. After installing the `pynq` package, the compiled target files will be saved automatically into the `pynq` package.

## Board Files and Overlays

All board related files including Vivado projects, bitstreams, and example notebooks, can be found in the `/boards` folder.

In Linux, you can rebuild the overlay by running *make* in the corresponding overlay folder (e.g. `/boards/Pynq-Z1/base`). In Windows, you need to source the appropriate tcl files in the corresponding overlay folder.

## Remote Cleanup PR Story

This PR came out of work on improving DMA performance in PYNQ.remote. While
running repeated benchmark and overlay flows, the `pynq-remote` logs made it
clear that some target-side resources were surviving much longer than the host
Python objects that created them.

That matters because a `pynq.remote` image normally runs `pynq-remote` as a
systemd service for the whole time the board is powered. The server can remain
alive while Jupyter kernels restart, tests run repeatedly, overlays are loaded
and reloaded, and different client processes connect to the same gRPC endpoint.
So any server-side state that is not explicitly released can accumulate across
normal user workflows.

The first issue was MMIO lifetime. Remote MMIO objects did not have an on-board
release path, so the server-side `mmios_` map could grow for the lifetime of the
board. This is not the same as leaking contiguous memory, but it is still
unbounded server state, and it leaves stale handles around that future host
objects might accidentally interact with.

Buffers had a related but more concrete failure mode. A well-behaved client
could manually free a remote buffer, but if the host kernel restarted or
disconnected without proper cleanup, the target allocation could remain live
with no remaining host object that knew it existed. That leaves contiguous
memory reserved but effectively unusable from the new client.

GPIO needed to be brought into the same model as well, because it has both a
remote server handle and Linux sysfs state. Cleaning up only one side is not
enough to make stale GPIO objects behave predictably.

This PR therefore makes cleanup a first-class part of PYNQ.remote operation
across MMIO, buffers, and GPIO. It adds explicit manual cleanup capability for
all of those resource classes, adds global cleanup for single-client workflows,
and gives stale handles clear failure behavior rather than allowing resources
from old kernels or overlays to silently persist inside a long-running server.

## Remote Cleanup PR Notes

This branch adds single-client PYNQ.remote resource cleanup. Notes to include in
the PR write-up:

- Remote cleanup is deliberately global for single-client use. A new
  `RemoteDevice` construction cleans stale target-side buffers, MMIOs, and GPIOs
  left by previous host kernels.
- Full overlay downloads clean stale remote resources before overlay clock
  programming creates fresh clock/register MMIOs. Raw `Bitstream.download()` /
  `RemoteDevice.download()` do not auto-clean, matching the lower-level embedded
  PYNQ behavior where callers own any required cleanup and clock setup.
- Cleanup has slightly different meaning for each remote resource type. Buffers
  own target-side allocated memory, so cleanup must free that memory and make
  the old buffer handle fail. MMIO objects own server-side mapping handles, not
  unique physical address ranges, so cleanup releases the mapping handle and
  prevents stale host objects from accidentally using a later mapping. GPIO has
  both a server handle and a Linux sysfs export, so cleanup must invalidate the
  old `gpio_id` and unexport `/sys/class/gpio/gpioN`.
- This PR also gives a client explicit cleanup capability for all remote
  resource classes. Previously a client could manually free remote buffers, but
  not the server-side MMIO mappings or GPIO exports/handles; those could remain
  live until the long-running server process was restarted.
- GPIO staleness is checked by the remote `gpio_id`, not only by the sysfs path.
  Immediately after cleanup the old GPIO path should be gone, but creating a
  fresh GPIO for the same pin is allowed to re-export the same
  `/sys/class/gpio/gpioN` path. In that case the old `gpio_id` must still return
  `NOT_FOUND`; the reused sysfs path belongs to the new GPIO handle.
- Remote cleanup clears server-side buffer, MMIO, and GPIO handle tables. If it
  actually frees any resource, all three handle services advance their cleanup
  epoch together. New handles are allocated as numbered opaque strings like
  `epoch:number`, so stale handles from earlier epochs stay invalid even though
  numbering restarts after cleanup.
- This also acts as a practical guard rail between separate host client
  instances talking to the same long-lived `pynq-remote` server. In single-client
  mode, a new Python kernel should not be able to accidentally inherit,
  operate through, or release stale handles created by a previous kernel. The
  connection is therefore treated as an ownership boundary for remote resource
  handles. This matters in practice because a `pynq.remote` image normally keeps
  the systemd-managed `pynq-remote` service running for as long as the board is
  powered, while host clients may restart kernels, run many tests, and load many
  overlays against that same server process. This branch does not implement full
  multi-client isolation or authorization.
- A simple cooperative multi-client experiment can opt out of constructor
  cleanup with `auto_cleanup=False`, allowing multiple clients to connect to the
  same gRPC server and hold independent handle IDs at the same time. That is not
  safe multi-client support: any client can still call global `device.cleanup()`,
  load a full overlay, change shared registers, release shared GPIO sysfs state,
  or otherwise invalidate another client's assumptions. Real multi-client
  support would need session/resource ownership, scoped cleanup, overlay
  locking, and explicit access-control or lease semantics.
- The `pynq-remote` server now uses the same `epoch:number` handle scheme for
  buffers, MMIOs, and GPIOs, and returns `RESOURCE_EXHAUSTED` if the 64-bit
  epoch/counter space is ever exhausted rather than silently wrapping or
  reusing old handles.
- Remote handle errors are now operation-specific without exposing other live
  server resources. Malformed IDs return `INVALID_ARGUMENT` with messages such
  as `Invalid MMIO ID while handling read()...`; old cleanup-epoch handles
  return `NOT_FOUND` with `Object stale`; well-formed current IDs with no
  backing resource return `Object not found`. Release-style calls
  (`release_mmio()`, `freebuffer()`, and GPIO `unexport()`) are idempotent for
  stale/already-gone handles, while active operations like `read()`,
  `write()`, `flush()`, and `physical_address()` fail clearly.
- Individual object release frees the server-side resource but does not recycle
  that handle number. Handles are intentionally opaque and non-reused. If a
  per-epoch counter ever reaches its 64-bit limit, the server automatically
  advances to the next epoch and continues from `next_epoch:0`; only exhausting
  the full epoch/counter space causes `RESOURCE_EXHAUSTED`.
- `Register(addr)` now retains its backing `MMIO` while the `Register` exists.
  Without this, `MMIO.__del__()` could release a `RemoteMMIO` too early for
  temporary register operations. This was found while adding `RemoteMMIO`
  cleanup.
- Remote MMIO cleanup is not about freeing scarce contiguous memory like buffer
  cleanup. It prevents unbounded growth of the server-side MMIO handle table,
  releases target-side mapping objects, keeps debug logs/IDs meaningful during
  long-running sessions, and makes stale host MMIO objects fail instead of
  accidentally operating through an obsolete server handle.
- Remote AXI-width setup now passes `device=self` explicitly into
  `Register(...)`, avoiding accidental use of the wrong active device.
- Remote device close now drops the cached `Clocks` instance only when it
  belongs to that exact `RemoteDevice`. This lets the clock MMIO destructors
  release their own server handles before final global cleanup, without
  disturbing another device in a future multi-board session.
- We intentionally did not implement host-side invalidation of every stale
  Python `RemoteMMIO` / `RemoteBuffer` / `RemoteGPIO` object on global cleanup
  in this branch. That can be added later with per-endpoint weak tracking for
  single-client mode, but it should be designed separately from the future
  multi-client story and does not replace server-side stale-handle protection.
- The shared bitstream handler now treats a file as XSA only when the requested
  path itself has a `.xsa` suffix. This fixes the same-stem sibling case where
  loading `foo.bit` could be misclassified if `foo.xsa` existed beside it.

Example stale-handle bug avoided by epoch-prefixed numbered handles:

```python
from pynq.pl_server.remote_device import RemoteDevice

dev = RemoteDevice(ip_addr="192.168.2.197", auto_cleanup=False)

old_mmio = dev.mmap(0xA0000000, 0x1000)   # server handle "0:0"
old_mmio.read(0)

dev.cleanup()                             # clears server MMIOs, advances epoch

new_mmio = dev.mmap(0xB0000000, 0x1000)   # should now be handle "1:0"

# If cleanup only reset a plain numbered counter, old_mmio could alias new_mmio.
old_mmio.read(0)                          # should fail, not read new_mmio
old_mmio.close()                          # should not release new_mmio
new_mmio.read(0)                          # should still work
```

## Contribute

Contributions to this repository are welcomed. Please refer to <a href="https://github.com/Xilinx/PYNQ/blob/master/CONTRIBUTING.md" target="_blank">CONTRIBUTING.md</a>
for how to improve PYNQ.

## Support

Please ask questions on the <a href="https://discuss.pynq.io" target="_blank">PYNQ support forum</a>.

## Citing PYNQ

If you use PYNQ in your research, please cite this GitHub repository by using the metadata given in <a href="https://github.com/Xilinx/PYNQ/blob/master/CITATION.cff" target="_blank">CITATION.cff</a>.

## Licenses

**PYNQ** License: [BSD 3-Clause License](https://github.com/Xilinx/PYNQ/blob/master/LICENSE)

**Xilinx Embedded SW** License: [Multiple License File](https://github.com/Xilinx/embeddedsw/blob/master/license.txt)

**Digilent IP** License: [MIT License](https://github.com/Xilinx/PYNQ/blob/master/THIRD_PARTY_LIC)

## SDBuild Open Source Components

**License and Copyrights Info** [TAR/GZIP](https://www.xilinx.com/bin/public/openDownload?filename=pynq-v3.0-license.tar.gz)

**Open Components Source Code** [TAR/GZIP](https://www.xilinx.com/bin/public/openDownload?filename=pynq-v3.0-open_components.tar.gz)
