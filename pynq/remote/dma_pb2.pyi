from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ChannelDirection(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    CHANNEL_DIRECTION_UNSPECIFIED: _ClassVar[ChannelDirection]
    CHANNEL_DIRECTION_MM2S: _ClassVar[ChannelDirection]
    CHANNEL_DIRECTION_S2MM: _ClassVar[ChannelDirection]

class CompletionMode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    COMPLETION_MODE_AUTO: _ClassVar[CompletionMode]
    COMPLETION_MODE_POLL: _ClassVar[CompletionMode]
    COMPLETION_MODE_INTERRUPT: _ClassVar[CompletionMode]

class TransferMode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    TRANSFER_MODE_SIMPLE: _ClassVar[TransferMode]
    TRANSFER_MODE_SCATTER_GATHER: _ClassVar[TransferMode]
CHANNEL_DIRECTION_UNSPECIFIED: ChannelDirection
CHANNEL_DIRECTION_MM2S: ChannelDirection
CHANNEL_DIRECTION_S2MM: ChannelDirection
COMPLETION_MODE_AUTO: CompletionMode
COMPLETION_MODE_POLL: CompletionMode
COMPLETION_MODE_INTERRUPT: CompletionMode
TRANSFER_MODE_SIMPLE: TransferMode
TRANSFER_MODE_SCATTER_GATHER: TransferMode

class AxiDmaConfig(_message.Message):
    __slots__ = ("has_sts_cntrl_strm", "has_mm2s", "has_mm2s_dre", "mm2s_data_width", "has_s2mm", "has_s2mm_dre", "s2mm_data_width", "has_sg", "mm2s_num_channels", "s2mm_num_channels", "mm2s_burst_size", "s2mm_burst_size", "micro_dma_mode", "addr_width", "sg_length_width")
    HAS_STS_CNTRL_STRM_FIELD_NUMBER: _ClassVar[int]
    HAS_MM2S_FIELD_NUMBER: _ClassVar[int]
    HAS_MM2S_DRE_FIELD_NUMBER: _ClassVar[int]
    MM2S_DATA_WIDTH_FIELD_NUMBER: _ClassVar[int]
    HAS_S2MM_FIELD_NUMBER: _ClassVar[int]
    HAS_S2MM_DRE_FIELD_NUMBER: _ClassVar[int]
    S2MM_DATA_WIDTH_FIELD_NUMBER: _ClassVar[int]
    HAS_SG_FIELD_NUMBER: _ClassVar[int]
    MM2S_NUM_CHANNELS_FIELD_NUMBER: _ClassVar[int]
    S2MM_NUM_CHANNELS_FIELD_NUMBER: _ClassVar[int]
    MM2S_BURST_SIZE_FIELD_NUMBER: _ClassVar[int]
    S2MM_BURST_SIZE_FIELD_NUMBER: _ClassVar[int]
    MICRO_DMA_MODE_FIELD_NUMBER: _ClassVar[int]
    ADDR_WIDTH_FIELD_NUMBER: _ClassVar[int]
    SG_LENGTH_WIDTH_FIELD_NUMBER: _ClassVar[int]
    has_sts_cntrl_strm: bool
    has_mm2s: bool
    has_mm2s_dre: bool
    mm2s_data_width: int
    has_s2mm: bool
    has_s2mm_dre: bool
    s2mm_data_width: int
    has_sg: bool
    mm2s_num_channels: int
    s2mm_num_channels: int
    mm2s_burst_size: int
    s2mm_burst_size: int
    micro_dma_mode: bool
    addr_width: int
    sg_length_width: int
    def __init__(self, has_sts_cntrl_strm: bool = ..., has_mm2s: bool = ..., has_mm2s_dre: bool = ..., mm2s_data_width: _Optional[int] = ..., has_s2mm: bool = ..., has_s2mm_dre: bool = ..., s2mm_data_width: _Optional[int] = ..., has_sg: bool = ..., mm2s_num_channels: _Optional[int] = ..., s2mm_num_channels: _Optional[int] = ..., mm2s_burst_size: _Optional[int] = ..., s2mm_burst_size: _Optional[int] = ..., micro_dma_mode: bool = ..., addr_width: _Optional[int] = ..., sg_length_width: _Optional[int] = ...) -> None: ...

class BindDmaRequest(_message.Message):
    __slots__ = ("mmio_id", "axi_dma_config")
    MMIO_ID_FIELD_NUMBER: _ClassVar[int]
    AXI_DMA_CONFIG_FIELD_NUMBER: _ClassVar[int]
    mmio_id: str
    axi_dma_config: AxiDmaConfig
    def __init__(self, mmio_id: _Optional[str] = ..., axi_dma_config: _Optional[_Union[AxiDmaConfig, _Mapping]] = ...) -> None: ...

class BindDmaResponse(_message.Message):
    __slots__ = ("status", "msg")
    STATUS_FIELD_NUMBER: _ClassVar[int]
    MSG_FIELD_NUMBER: _ClassVar[int]
    status: bool
    msg: str
    def __init__(self, status: bool = ..., msg: _Optional[str] = ...) -> None: ...

class TransferRequest(_message.Message):
    __slots__ = ("mmio_id", "direction", "buffer_id", "start", "nbytes", "transfer_mode", "cyclic")
    MMIO_ID_FIELD_NUMBER: _ClassVar[int]
    DIRECTION_FIELD_NUMBER: _ClassVar[int]
    BUFFER_ID_FIELD_NUMBER: _ClassVar[int]
    START_FIELD_NUMBER: _ClassVar[int]
    NBYTES_FIELD_NUMBER: _ClassVar[int]
    TRANSFER_MODE_FIELD_NUMBER: _ClassVar[int]
    CYCLIC_FIELD_NUMBER: _ClassVar[int]
    mmio_id: str
    direction: ChannelDirection
    buffer_id: str
    start: int
    nbytes: int
    transfer_mode: TransferMode
    cyclic: bool
    def __init__(self, mmio_id: _Optional[str] = ..., direction: _Optional[_Union[ChannelDirection, str]] = ..., buffer_id: _Optional[str] = ..., start: _Optional[int] = ..., nbytes: _Optional[int] = ..., transfer_mode: _Optional[_Union[TransferMode, str]] = ..., cyclic: bool = ...) -> None: ...

class TransferResponse(_message.Message):
    __slots__ = ("status", "msg", "transfer_id")
    STATUS_FIELD_NUMBER: _ClassVar[int]
    MSG_FIELD_NUMBER: _ClassVar[int]
    TRANSFER_ID_FIELD_NUMBER: _ClassVar[int]
    status: bool
    msg: str
    transfer_id: str
    def __init__(self, status: bool = ..., msg: _Optional[str] = ..., transfer_id: _Optional[str] = ...) -> None: ...

class WaitRequest(_message.Message):
    __slots__ = ("transfer_id", "completion_mode", "timeout_ms")
    TRANSFER_ID_FIELD_NUMBER: _ClassVar[int]
    COMPLETION_MODE_FIELD_NUMBER: _ClassVar[int]
    TIMEOUT_MS_FIELD_NUMBER: _ClassVar[int]
    transfer_id: str
    completion_mode: CompletionMode
    timeout_ms: int
    def __init__(self, transfer_id: _Optional[str] = ..., completion_mode: _Optional[_Union[CompletionMode, str]] = ..., timeout_ms: _Optional[int] = ...) -> None: ...

class WaitResponse(_message.Message):
    __slots__ = ("status", "msg", "transferred", "dma_status")
    STATUS_FIELD_NUMBER: _ClassVar[int]
    MSG_FIELD_NUMBER: _ClassVar[int]
    TRANSFERRED_FIELD_NUMBER: _ClassVar[int]
    DMA_STATUS_FIELD_NUMBER: _ClassVar[int]
    status: bool
    msg: str
    transferred: int
    dma_status: int
    def __init__(self, status: bool = ..., msg: _Optional[str] = ..., transferred: _Optional[int] = ..., dma_status: _Optional[int] = ...) -> None: ...

class StopRequest(_message.Message):
    __slots__ = ("transfer_id",)
    TRANSFER_ID_FIELD_NUMBER: _ClassVar[int]
    transfer_id: str
    def __init__(self, transfer_id: _Optional[str] = ...) -> None: ...

class StopResponse(_message.Message):
    __slots__ = ("status", "msg", "dma_status")
    STATUS_FIELD_NUMBER: _ClassVar[int]
    MSG_FIELD_NUMBER: _ClassVar[int]
    DMA_STATUS_FIELD_NUMBER: _ClassVar[int]
    status: bool
    msg: str
    dma_status: int
    def __init__(self, status: bool = ..., msg: _Optional[str] = ..., dma_status: _Optional[int] = ...) -> None: ...

class StatusRequest(_message.Message):
    __slots__ = ("transfer_id",)
    TRANSFER_ID_FIELD_NUMBER: _ClassVar[int]
    transfer_id: str
    def __init__(self, transfer_id: _Optional[str] = ...) -> None: ...

class StatusResponse(_message.Message):
    __slots__ = ("status", "msg", "running", "idle", "halted", "dma_status", "transferred")
    STATUS_FIELD_NUMBER: _ClassVar[int]
    MSG_FIELD_NUMBER: _ClassVar[int]
    RUNNING_FIELD_NUMBER: _ClassVar[int]
    IDLE_FIELD_NUMBER: _ClassVar[int]
    HALTED_FIELD_NUMBER: _ClassVar[int]
    DMA_STATUS_FIELD_NUMBER: _ClassVar[int]
    TRANSFERRED_FIELD_NUMBER: _ClassVar[int]
    status: bool
    msg: str
    running: bool
    idle: bool
    halted: bool
    dma_status: int
    transferred: int
    def __init__(self, status: bool = ..., msg: _Optional[str] = ..., running: bool = ..., idle: bool = ..., halted: bool = ..., dma_status: _Optional[int] = ..., transferred: _Optional[int] = ...) -> None: ...
