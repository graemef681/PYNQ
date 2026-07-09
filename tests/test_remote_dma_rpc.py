## Use custom DMA RPCs to invoke DMA transfer instead of MMIO RPCs with RemoteMMIO Hook

import os
import pytest
import numpy as np

os.environ["PYNQ_REMOTE_DEVICES"] = "192.168.2.197"


def _bool_param(params, key, default="0"):
    return bool(int(params.get(key, default)))


def _int_param(params, key, default="0"):
    return int(params.get(key, default))


@pytest.mark.remote
def test_remote_dma_rpc():
    """Exercise the DMA gRPC service using the resizer overlay."""
    if not os.environ.get("PYNQ_REMOTE_DEVICES"):
        pytest.skip("PYNQ_REMOTE_DEVICES environment variable not set")

    test_dir = os.path.dirname(os.path.abspath(__file__))
    overlay_path = os.path.join(test_dir, "resizer.xsa")
    if not os.path.exists(overlay_path):
        pytest.skip(f"Overlay not found: {overlay_path}")

    try:
        import grpc
        from pynq import allocate, Overlay
        from pynq.pl_server.device import Device
        from pynq.pl_server.remote_device import RemoteDevice
        from pynq.remote import dma_pb2, dma_pb2_grpc
    except ImportError as e:
        pytest.skip(f"Required modules not found: {e}")

    devices = Device.devices
    remote_devices = [d for d in devices if isinstance(d, RemoteDevice)]
    if not remote_devices:
        pytest.skip("No remote device discovered")

    design = Overlay(overlay_path)
    dma = design.axi_dma_0
    resizer = design.resize_accel_0
    device = dma.device
    remote_mmio = device.mmap(dma.mmio.base_addr, dma.mmio.length)
    params = dma.description["parameters"]

    dma_stub = dma_pb2_grpc.DmaStub(device.client.channel)
    bind_response = dma_stub.bind_dma(
        dma_pb2.BindDmaRequest(
            mmio_id=remote_mmio.mmio_id,
            axi_dma_config=dma_pb2.AxiDmaConfig(
                has_sts_cntrl_strm=_bool_param(params, "c_sg_include_stscntrl_strm"),
                has_mm2s=_bool_param(params, "c_include_mm2s", "1"),
                has_mm2s_dre=_bool_param(params, "c_include_mm2s_dre"),
                mm2s_data_width=_int_param(params, "c_m_axi_mm2s_data_width", "32"),
                has_s2mm=_bool_param(params, "c_include_s2mm", "1"),
                has_s2mm_dre=_bool_param(params, "c_include_s2mm_dre"),
                s2mm_data_width=_int_param(params, "c_m_axi_s2mm_data_width", "32"),
                has_sg=_bool_param(params, "c_include_sg"),
                mm2s_num_channels=_int_param(params, "c_num_mm2s_channels", "1"),
                s2mm_num_channels=_int_param(params, "c_num_s2mm_channels", "1"),
                mm2s_burst_size=_int_param(params, "c_mm2s_burst_size", "16"),
                s2mm_burst_size=_int_param(params, "c_s2mm_burst_size", "16"),
                micro_dma_mode=_bool_param(params, "c_micro_dma"),
                addr_width=_int_param(params, "c_addr_width", "32"),
                sg_length_width=_int_param(params, "c_sg_length_width", "23"),
            ),
        )
    )
    if getattr(bind_response, "msg", ""):
        raise RuntimeError(bind_response.msg)

    size = 500
    fake_img = np.random.randint(0, 256, (size, size, 3), dtype=np.uint8)

    in_buffer = allocate(shape=(size, size, 3), dtype=np.uint8, cacheable=1)
    out_buffer = allocate(shape=(size, size, 3), dtype=np.uint8, cacheable=1)
    in_buffer[:] = fake_img

    # Push host data into the board-side input buffer before the DMA RPC uses it.
    in_buffer.flush()

    resizer.register_map.src_rows = size
    resizer.register_map.src_cols = size
    resizer.register_map.dst_rows = size
    resizer.register_map.dst_cols = size

    tx_response = dma_stub.transfer(
        dma_pb2.TransferRequest(
            mmio_id=remote_mmio.mmio_id,
            direction=dma_pb2.CHANNEL_DIRECTION_MM2S,
            buffer_id=in_buffer.buffer_id,
            start=0,
            nbytes=in_buffer.nbytes,
            transfer_mode=dma_pb2.TRANSFER_MODE_SIMPLE,
            cyclic=False,
        )
    )
    if getattr(tx_response, "msg", ""):
        raise RuntimeError(tx_response.msg)

    rx_response = dma_stub.transfer(
        dma_pb2.TransferRequest(
            mmio_id=remote_mmio.mmio_id,
            direction=dma_pb2.CHANNEL_DIRECTION_S2MM,
            buffer_id=out_buffer.buffer_id,
            start=0,
            nbytes=out_buffer.nbytes,
            transfer_mode=dma_pb2.TRANSFER_MODE_SIMPLE,
            cyclic=False,
        )
    )
    if getattr(rx_response, "msg", ""):
        raise RuntimeError(rx_response.msg)

    resizer.write(0x00, 0x81)

    tx_wait = dma_stub.wait(
        dma_pb2.WaitRequest(
            transfer_id=tx_response.transfer_id,
            completion_mode=dma_pb2.COMPLETION_MODE_POLL,
            timeout_ms=0,
        )
    )
    if getattr(tx_wait, "msg", ""):
        raise RuntimeError(tx_wait.msg)

    rx_wait = dma_stub.wait(
        dma_pb2.WaitRequest(
            transfer_id=rx_response.transfer_id,
            completion_mode=dma_pb2.COMPLETION_MODE_POLL,
            timeout_ms=0,
        )
    )
    if getattr(rx_wait, "msg", ""):
        raise RuntimeError(rx_wait.msg)

    # Pull the completed output back from the board-side buffer.
    out_buffer.invalidate()

    assert np.array_equal(in_buffer[:], out_buffer[:])


if __name__ == "__main__":
    test_remote_dma_rpc()
