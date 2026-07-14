/*
 * File: dma.cc
 * Description: Board-side helper classes for remote DMA control.
 * Engineer Name: Graeme Fitzpatrick
 * Project: PYNQ.remote
 * Created: 2026-06-16
 *
 * This file implements a service-independent DMA manager that mirrors the
 * high-level operations used by the Python PYNQ DMA driver. Remote DMA
 * requests are handled exclusively through the embeddedsw XAxiDma driver.
 */

#include "dma.h"

#include <chrono>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <thread>

#ifdef USE_XAXIDMA
#include "xaxidma.h"
#endif

namespace
{
constexpr const char *kXaxiDmaRequiredMessage =
    "DMA RPC driver requires the PYNQ.remote image to be built with USE_XAXIDMA enabled.";

const char *direction_to_string(DmaChannelDirection direction)
{
    return (direction == DmaChannelDirection::S2MM) ? "S2MM" : "MM2S";
}

const char *xaxidma_compile_state()
{
#ifdef USE_XAXIDMA
    return "USE_XAXIDMA=ON";
#else
    return "USE_XAXIDMA=OFF";
#endif
}
}

DmaManager::DmaManager(uint64_t base_address, size_t length, std::optional<DmaHardwareConfig> config)
    : owned_mmio_(std::make_unique<MMIO>(base_address, length)),
      mmio_(owned_mmio_.get()),
      hardware_config_(std::move(config))
{
    initialize_backend();
}

DmaManager::DmaManager(MMIO &mmio, std::optional<DmaHardwareConfig> config)
    : owned_mmio_(nullptr),
      mmio_(&mmio),
      hardware_config_(std::move(config))
{
    initialize_backend();
}

DmaManager::~DmaManager() = default;

DmaTransferResult DmaManager::transfer(const DmaTransferRequest &request)
{
    DmaTransferResult result;

    try
    {
        std::string backend_message;
        if (!ensure_backend_ready(backend_message))
        {
            result.message = backend_message;
            return result;
        }

        if (request.buffer == nullptr)
        {
            result.message = "Buffer pointer cannot be null.";
            return result;
        }

        if (request.transfer_mode != DmaTransferMode::Simple)
        {
            result.message = "Only simple DMA mode is currently implemented.";
            return result;
        }

        if (request.cyclic)
        {
            result.message = "Cyclic mode is not implemented in this helper yet.";
            return result;
        }

        if (request.start > request.buffer->size_)
        {
            result.message = "Start offset exceeds buffer size.";
            return result;
        }

        uint64_t nbytes = request.nbytes;
        if (nbytes == 0)
        {
            nbytes = request.buffer->size_ - request.start;
        }
        else
        {
            uint64_t remaining = request.buffer->size_ - request.start;
            if (nbytes > remaining)
            {
                result.message = "Requested transfer exceeds buffer size.";
                return result;
            }
        }

        if (nbytes > std::numeric_limits<uint32_t>::max())
        {
            result.message = "Transfer size exceeds XAxiDma/simple DMA 32-bit length support.";
            return result;
        }

        uint64_t address = request.buffer->physical_address() + request.start;

        if (request.direction == DmaChannelDirection::MM2S)
        {
            request.buffer->flush();
        }

#ifdef USE_XAXIDMA
        std::cout << "[pynq-remote-dma] backend=XAxiDma call=XAxiDma_SimpleTransfer"
                  << " direction=" << direction_to_string(request.direction)
                  << " address=0x" << std::hex << address << std::dec
                  << " nbytes=" << nbytes
                  << std::endl;
        int status = XAxiDma_SimpleTransfer(
            axidma_instance_.get(),
            static_cast<UINTPTR>(address),
            static_cast<u32>(nbytes),
            xaxidma_direction(request.direction));
        if (status != XST_SUCCESS)
        {
            result.message = "XAxiDma_SimpleTransfer failed: " + xaxidma_status_to_string(status);
            return result;
        }
#else
        result.message = kXaxiDmaRequiredMessage;
        return result;
#endif

        ActiveTransfer transfer;
        transfer.direction = request.direction;
        transfer.buffer = request.buffer;
        transfer.start = request.start;
        transfer.nbytes = nbytes;
        transfer.cyclic = request.cyclic;

        result.transfer_id = generate_transfer_id();
        transfers_[result.transfer_id] = transfer;
        result.success = true;
    }
    catch (const std::exception &e)
    {
        result.message = e.what();
    }

    return result;
}

DmaWaitResult DmaManager::wait(const DmaWaitRequest &request)
{
    DmaWaitResult result;

    try
    {
        std::string backend_message;
        if (!ensure_backend_ready(backend_message))
        {
            result.message = backend_message;
            return result;
        }

        auto it = transfers_.find(request.transfer_id);
        if (it == transfers_.end())
        {
            result.message = "Transfer ID not found.";
            return result;
        }

        if (request.completion_mode == DmaCompletionMode::Interrupt)
        {
            result.message = "Interrupt completion is not implemented.";
            return result;
        }

#ifdef USE_XAXIDMA
        ActiveTransfer &transfer = it->second;
        auto start_time = std::chrono::steady_clock::now();
        while (XAxiDma_Busy(axidma_instance_.get(), xaxidma_direction(transfer.direction)))
        {
            if (request.timeout_ms > 0)
            {
                auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
                    std::chrono::steady_clock::now() - start_time);
                if (static_cast<uint64_t>(elapsed.count()) > request.timeout_ms)
                {
                    result.message = "DMA wait timed out.";
                    result.dma_status = read_xaxidma_status(transfer.direction);
                    return result;
                }
            }

            std::this_thread::sleep_for(std::chrono::microseconds(50));
        }

        uint32_t status_value = read_xaxidma_status(transfer.direction);
        transfer.last_status = status_value;

        std::cout << "[pynq-remote-dma] backend=XAxiDma call=XAxiDma_Busy"
                  << " transfer_id=" << request.transfer_id
                  << " direction=" << direction_to_string(transfer.direction)
                  << " result=complete"
                  << " status=0x" << std::hex << status_value << std::dec
                  << std::endl;

        auto error = decode_xaxidma_error(status_value);
        if (error.has_value())
        {
            result.message = error.value();
            result.dma_status = status_value;
            return result;
        }

        if (transfer.direction == DmaChannelDirection::S2MM)
        {
            transfer.buffer->invalidate();
        }

        transfer.transferred = read_xaxidma_transferred(transfer.direction);
        result.transferred = transfer.transferred;
        result.dma_status = transfer.last_status;
        result.success = true;
        transfers_.erase(it);
#else
        result.message = kXaxiDmaRequiredMessage;
        return result;
#endif
    }
    catch (const std::exception &e)
    {
        result.message = e.what();
    }

    return result;
}

DmaWaitResult DmaManager::stop(const std::string &transfer_id)
{
    DmaWaitResult result;

    try
    {
        std::string backend_message;
        if (!ensure_backend_ready(backend_message))
        {
            result.message = backend_message;
            return result;
        }

        auto it = transfers_.find(transfer_id);
        if (it == transfers_.end())
        {
            result.message = "Transfer ID not found.";
            return result;
        }

#ifdef USE_XAXIDMA
        ActiveTransfer &transfer = it->second;
        std::cout << "[pynq-remote-dma] backend=XAxiDma call=XAxiDma_Reset"
                  << " transfer_id=" << transfer_id
                  << " direction=" << direction_to_string(transfer.direction)
                  << std::endl;
        XAxiDma_Reset(axidma_instance_.get());
        while (!XAxiDma_ResetIsDone(axidma_instance_.get()))
        {
            std::this_thread::sleep_for(std::chrono::microseconds(50));
        }
        transfer.last_status = read_xaxidma_status(transfer.direction);
        transfer.transferred = read_xaxidma_transferred(transfer.direction);

        result.success = true;
        result.dma_status = transfer.last_status;
        result.transferred = transfer.transferred;
        transfers_.erase(it);
#else
        result.message = kXaxiDmaRequiredMessage;
        return result;
#endif
    }
    catch (const std::exception &e)
    {
        result.message = e.what();
    }

    return result;
}

DmaStatusResult DmaManager::status(const std::string &transfer_id)
{
    DmaStatusResult result;

    try
    {
        std::string backend_message;
        if (!ensure_backend_ready(backend_message))
        {
            result.message = backend_message;
            return result;
        }

        auto it = transfers_.find(transfer_id);
        if (it == transfers_.end())
        {
            result.message = "Transfer ID not found.";
            return result;
        }

#ifdef USE_XAXIDMA
        ActiveTransfer &transfer = it->second;
        const bool busy = XAxiDma_Busy(axidma_instance_.get(), xaxidma_direction(transfer.direction));
        uint32_t status_value = read_xaxidma_status(transfer.direction);

        transfer.last_status = status_value;
        transfer.transferred = read_xaxidma_transferred(transfer.direction);

        std::cout << "[pynq-remote-dma] backend=XAxiDma call=XAxiDma_Busy"
                  << " transfer_id=" << transfer_id
                  << " direction=" << direction_to_string(transfer.direction)
                  << " result=" << (busy ? "busy" : "idle")
                  << " status=0x" << std::hex << status_value << std::dec
                  << std::endl;

        result.success = true;
        result.running = xaxidma_is_running(status_value);
        result.idle = xaxidma_is_idle(status_value);
        result.halted = xaxidma_is_halted(status_value);
        result.dma_status = status_value;
        result.transferred = transfer.transferred;
#else
        result.message = kXaxiDmaRequiredMessage;
        return result;
#endif
    }
    catch (const std::exception &e)
    {
        result.message = e.what();
    }

    return result;
}

bool DmaManager::backend_ready() const
{
    return backend_error_.empty();
}

const std::string &DmaManager::backend_error() const
{
    return backend_error_;
}

bool DmaManager::using_xaxidma() const
{
    return use_xaxidma_;
}

MMIO &DmaManager::mmio() const
{
    if (mmio_ == nullptr)
    {
        throw std::runtime_error("DMA manager does not have a valid MMIO instance.");
    }

    return *mmio_;
}

std::string DmaManager::generate_transfer_id()
{
    std::ostringstream stream;
    stream << "dma-transfer-" << transfer_counter_++;
    return stream.str();
}

void DmaManager::initialize_backend()
{
    backend_error_.clear();
    use_xaxidma_ = false;

    std::cout << "[pynq-remote-dma] backend=XAxiDma-only"
              << " compile_state=" << xaxidma_compile_state()
              << " config_present=" << (hardware_config_.has_value() ? "true" : "false")
              << std::endl;

    if (!hardware_config_.has_value())
    {
        backend_error_ = std::string(kXaxiDmaRequiredMessage) +
                         " AXI DMA hardware metadata is also required to initialize the XAxiDma driver.";
        std::cout << "[pynq-remote-dma] backend=unavailable"
                  << " reason=\"" << backend_error_ << "\""
                  << std::endl;
        return;
    }

#ifndef USE_XAXIDMA
    backend_error_ = std::string(kXaxiDmaRequiredMessage) +
                     " This pynq-remote binary was compiled with USE_XAXIDMA disabled.";
    std::cout << "[pynq-remote-dma] backend=unavailable"
              << " reason=\"" << backend_error_ << "\""
              << std::endl;
    return;
#endif

    use_xaxidma_ = true;
    if (auto error = initialize_xaxidma(hardware_config_.value()); error.has_value())
    {
        backend_error_ = error.value() + " " + kXaxiDmaRequiredMessage;
        use_xaxidma_ = false;
        std::cout << "[pynq-remote-dma] backend=unavailable"
                  << " reason=\"" << backend_error_ << "\""
                  << std::endl;
        return;
    }

    std::cout << "[pynq-remote-dma] backend=XAxiDma"
              << " state=ready"
              << std::endl;
}

bool DmaManager::ensure_backend_ready(std::string &message) const
{
    if (!backend_error_.empty())
    {
        message = backend_error_;
        return false;
    }
    return true;
}

#ifdef USE_XAXIDMA
std::optional<std::string> DmaManager::initialize_xaxidma(const DmaHardwareConfig &config)
{
    uintptr_t virtual_base = mmio().virtual_address();
    if (virtual_base == 0)
    {
        return std::string("MMIO region is not mapped; cannot initialize XAxiDma.");
    }

    XAxiDma_Config native_config{};
#ifndef SDT
    native_config.DeviceId = 0;
#else
    native_config.Name = nullptr;
#endif
    native_config.BaseAddr = static_cast<UINTPTR>(virtual_base);
    native_config.HasStsCntrlStrm = config.has_sts_cntrl_strm ? 1 : 0;
    native_config.HasMm2S = config.has_mm2s ? 1 : 0;
    native_config.HasMm2SDRE = config.has_mm2s_dre ? 1 : 0;
    native_config.Mm2SDataWidth = static_cast<int>(config.mm2s_data_width);
    native_config.HasS2Mm = config.has_s2mm ? 1 : 0;
    native_config.HasS2MmDRE = config.has_s2mm_dre ? 1 : 0;
    native_config.S2MmDataWidth = static_cast<int>(config.s2mm_data_width);
    native_config.HasSg = config.has_sg ? 1 : 0;
    native_config.Mm2sNumChannels = static_cast<int>(config.mm2s_num_channels);
    native_config.S2MmNumChannels = static_cast<int>(config.s2mm_num_channels);
    native_config.Mm2SBurstSize = static_cast<int>(config.mm2s_burst_size);
    native_config.S2MmBurstSize = static_cast<int>(config.s2mm_burst_size);
    native_config.MicroDmaMode = config.micro_dma_mode ? 1 : 0;
    native_config.AddrWidth = static_cast<int>(config.addr_width);
    native_config.SgLengthWidth = static_cast<int>(config.sg_length_width);

    auto instance = std::make_unique<XAxiDma>();
    int status = XAxiDma_CfgInitialize(instance.get(), &native_config);
    if (status != XST_SUCCESS)
    {
        return std::string("XAxiDma_CfgInitialize failed: ") + xaxidma_status_to_string(status);
    }

    std::cout << "[pynq-remote-dma] backend=XAxiDma call=XAxiDma_CfgInitialize"
              << " base=0x" << std::hex << native_config.BaseAddr << std::dec
              << " has_mm2s=" << native_config.HasMm2S
              << " has_s2mm=" << native_config.HasS2Mm
              << " has_sg=" << native_config.HasSg
              << " addr_width=" << native_config.AddrWidth
              << " sg_length_width=" << native_config.SgLengthWidth
              << std::endl;

    if (native_config.HasMm2S)
    {
        std::cout << "[pynq-remote-dma] backend=XAxiDma call=XAxiDma_IntrDisable direction=MM2S"
                  << std::endl;
        XAxiDma_IntrDisable(instance.get(), XAXIDMA_IRQ_ALL_MASK, XAXIDMA_DMA_TO_DEVICE);
    }
    if (native_config.HasS2Mm)
    {
        std::cout << "[pynq-remote-dma] backend=XAxiDma call=XAxiDma_IntrDisable direction=S2MM"
                  << std::endl;
        XAxiDma_IntrDisable(instance.get(), XAXIDMA_IRQ_ALL_MASK, XAXIDMA_DEVICE_TO_DMA);
    }

    axidma_instance_ = std::move(instance);
    return std::nullopt;
}

std::string DmaManager::xaxidma_status_to_string(int status) const
{
    switch (status)
    {
    case XST_SUCCESS:
        return "XST_SUCCESS";
    case XST_FAILURE:
        return "XST_FAILURE";
    case XST_INVALID_PARAM:
        return "XST_INVALID_PARAM";
    case XST_DMA_ERROR:
        return "XST_DMA_ERROR";
    case XST_NOT_SGDMA:
        return "XST_NOT_SGDMA";
    default:
        return "status code " + std::to_string(status);
    }
}

int DmaManager::xaxidma_direction(DmaChannelDirection direction) const
{
    return (direction == DmaChannelDirection::S2MM) ? XAXIDMA_DEVICE_TO_DMA : XAXIDMA_DMA_TO_DEVICE;
}

uint32_t DmaManager::read_xaxidma_status(DmaChannelDirection direction) const
{
    return XAxiDma_ReadReg(
        axidma_instance_->RegBase + (XAXIDMA_RX_OFFSET * xaxidma_direction(direction)),
        XAXIDMA_SR_OFFSET);
}

uint32_t DmaManager::read_xaxidma_transferred(DmaChannelDirection direction) const
{
    return XAxiDma_ReadReg(
        axidma_instance_->RegBase + (XAXIDMA_RX_OFFSET * xaxidma_direction(direction)),
        XAXIDMA_BUFFLEN_OFFSET);
}

bool DmaManager::xaxidma_is_running(uint32_t status) const
{
    return (status & XAXIDMA_HALTED_MASK) == 0u;
}

bool DmaManager::xaxidma_is_idle(uint32_t status) const
{
    return (status & XAXIDMA_IDLE_MASK) == XAXIDMA_IDLE_MASK;
}

bool DmaManager::xaxidma_is_halted(uint32_t status) const
{
    return (status & XAXIDMA_HALTED_MASK) == XAXIDMA_HALTED_MASK;
}

std::optional<std::string> DmaManager::decode_xaxidma_error(uint32_t status) const
{
    if (status & XAXIDMA_ERR_INTERNAL_MASK)
    {
        return std::string("DMA Internal Error (transfer length 0?)");
    }
    if (status & XAXIDMA_ERR_SLAVE_MASK)
    {
        return std::string("DMA Slave Error (cannot access memory map interface)");
    }
    if (status & XAXIDMA_ERR_DECODE_MASK)
    {
        return std::string("DMA Decode Error (invalid address)");
    }
    if (status & XAXIDMA_ERR_SG_INT_MASK)
    {
        return std::string("DMA Scatter-Gather Internal Error");
    }
    if (status & XAXIDMA_ERR_SG_SLV_MASK)
    {
        return std::string("DMA Scatter-Gather Slave Error");
    }
    if (status & XAXIDMA_ERR_SG_DEC_MASK)
    {
        return std::string("DMA Scatter-Gather Decode Error");
    }
    return std::nullopt;
}
#endif

DMA::DMA(uint64_t base_address, size_t length, std::optional<DmaHardwareConfig> config)
    : manager_(base_address, length, std::move(config)),
      sendchannel(manager_, DmaChannelDirection::MM2S),
      recvchannel(manager_, DmaChannelDirection::S2MM)
{
}

DMA::DMA(MMIO &mmio, std::optional<DmaHardwareConfig> config)
    : manager_(mmio, std::move(config)),
      sendchannel(manager_, DmaChannelDirection::MM2S),
      recvchannel(manager_, DmaChannelDirection::S2MM)
{
}

DMAChannel::DMAChannel(DmaManager &manager, DmaChannelDirection direction)
    : manager_(&manager),
      direction_(direction)
{
}

DmaTransferResult DMAChannel::transfer(BufferRemote &buffer, uint64_t start, uint64_t nbytes)
{
    return transfer(buffer, start, nbytes, DmaTransferMode::Simple, false);
}

DmaTransferResult DMAChannel::transfer(
    BufferRemote &buffer,
    uint64_t start,
    uint64_t nbytes,
    DmaTransferMode transfer_mode,
    bool cyclic)
{
    DmaTransferRequest request;
    request.direction = direction_;
    request.buffer = &buffer;
    request.start = start;
    request.nbytes = nbytes;
    request.transfer_mode = transfer_mode;
    request.cyclic = cyclic;

    DmaTransferResult result = manager_->transfer(request);
    if (result.success)
    {
        active_transfer_id_ = result.transfer_id;
    }
    return result;
}

DmaWaitResult DMAChannel::wait(DmaCompletionMode completion_mode, uint64_t timeout_ms)
{
    DmaWaitResult result;
    if (active_transfer_id_.empty())
    {
        result.message = "No active transfer on this DMA channel.";
        return result;
    }

    DmaWaitRequest request;
    request.transfer_id = active_transfer_id_;
    request.completion_mode = completion_mode;
    request.timeout_ms = timeout_ms;

    result = manager_->wait(request);
    if (result.success)
    {
        active_transfer_id_.clear();
    }
    return result;
}

DmaWaitResult DMAChannel::stop()
{
    DmaWaitResult result;
    if (active_transfer_id_.empty())
    {
        result.message = "No active transfer on this DMA channel.";
        return result;
    }

    result = manager_->stop(active_transfer_id_);
    if (result.success)
    {
        active_transfer_id_.clear();
    }
    return result;
}

DmaStatusResult DMAChannel::status()
{
    DmaStatusResult result;
    if (active_transfer_id_.empty())
    {
        result.message = "No active transfer on this DMA channel.";
        return result;
    }
    return manager_->status(active_transfer_id_);
}

const std::string &DMAChannel::active_transfer_id() const
{
    return active_transfer_id_;
}

bool DMAChannel::has_active_transfer() const
{
    return !active_transfer_id_.empty();
}
