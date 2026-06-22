/*
 * File: dma.cc
 * Description: Board-side helper classes for remote DMA control.
 * Engineer Name: Graeme Fitzpatrick
 * Project: PYNQ.remote
 * Created: 2026-06-16
 *
 * This file implements a service-independent DMA manager that mirrors the
 * high-level operations used by the Python PYNQ DMA driver. It is intended
 * to be called from a future gRPC service implementation.
 */

#include "dma.h"

#include <chrono>
#include <sstream>
#include <stdexcept>
#include <thread>

DmaManager::DmaManager(uint64_t base_address, size_t length)
    : owned_mmio_(std::make_unique<MMIO>(base_address, length)),
      mmio_(owned_mmio_.get())
{
}

DmaManager::DmaManager(MMIO &mmio)
    : owned_mmio_(nullptr),
      mmio_(&mmio)
{
}

DmaTransferResult DmaManager::transfer(const DmaTransferRequest &request)
{
    DmaTransferResult result;

    try
    {
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

        uint64_t offset = channel_offset(request.direction);

        if (request.direction == DmaChannelDirection::MM2S)
        {
            request.buffer->flush();
        }

        uint64_t address = request.buffer->physical_address() + request.start;
        uint64_t nbytes = request.nbytes;
        if (nbytes == 0)
        {
            if (request.start > request.buffer->size_)
            {
                result.message = "Start offset exceeds buffer size.";
                return result;
            }
            nbytes = request.buffer->size_ - request.start;
        }

        mmio().write(kRunStop, offset + kDmacrOffset);
        mmio().write(static_cast<uint32_t>(address & 0xFFFFFFFFu), offset + kAddrLowOffset);
        mmio().write(static_cast<uint32_t>((address >> 32) & 0xFFFFFFFFu), offset + kAddrHighOffset);
        mmio().write(static_cast<uint32_t>(nbytes), offset + kLengthOffset);

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

        ActiveTransfer &transfer = it->second;
        uint64_t offset = channel_offset(transfer.direction);

        auto start_time = std::chrono::steady_clock::now();
        while (true)
        {
            uint32_t status_value = read_status(offset);
            transfer.last_status = status_value;

            auto error = decode_error(status_value);
            if (error.has_value())
            {
                result.message = error.value();
                result.dma_status = status_value;
                return result;
            }

            if (is_idle(status_value))
            {
                break;
            }

            if (request.timeout_ms > 0)
            {
                auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
                    std::chrono::steady_clock::now() - start_time);
                if (static_cast<uint64_t>(elapsed.count()) > request.timeout_ms)
                {
                    result.message = "DMA wait timed out.";
                    result.dma_status = status_value;
                    return result;
                }
            }

            std::this_thread::sleep_for(std::chrono::microseconds(50));
        }

        if (transfer.direction == DmaChannelDirection::S2MM)
        {
            transfer.buffer->invalidate();
        }

        transfer.transferred = mmio().read(offset + kLengthOffset);
        result.transferred = transfer.transferred;
        result.dma_status = transfer.last_status;
        result.success = true;
        transfers_.erase(it);
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
        auto it = transfers_.find(transfer_id);
        if (it == transfers_.end())
        {
            result.message = "Transfer ID not found.";
            return result;
        }

        ActiveTransfer &transfer = it->second;
        uint64_t offset = channel_offset(transfer.direction);

        mmio().write(0x0000, offset + kDmacrOffset);
        transfer.last_status = read_status(offset);

        result.success = true;
        result.dma_status = transfer.last_status;
        result.transferred = transfer.transferred;
        transfers_.erase(it);
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
        auto it = transfers_.find(transfer_id);
        if (it == transfers_.end())
        {
            result.message = "Transfer ID not found.";
            return result;
        }

        ActiveTransfer &transfer = it->second;
        uint64_t offset = channel_offset(transfer.direction);
        uint32_t status_value = read_status(offset);

        transfer.last_status = status_value;
        transfer.transferred = mmio().read(offset + kLengthOffset);

        result.success = true;
        result.running = is_running(status_value);
        result.idle = is_idle(status_value);
        result.halted = is_halted(status_value);
        result.dma_status = status_value;
        result.transferred = transfer.transferred;
    }
    catch (const std::exception &e)
    {
        result.message = e.what();
    }

    return result;
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

uint64_t DmaManager::channel_offset(DmaChannelDirection direction) const
{
    return (direction == DmaChannelDirection::S2MM) ? kRxOffset : kTxOffset;
}

uint32_t DmaManager::read_status(uint64_t channel_offset) const
{
    return mmio().read(channel_offset + kDmasrOffset);
}

bool DmaManager::is_running(uint32_t status) const
{
    return (status & 0x01u) == 0x00u;
}

bool DmaManager::is_idle(uint32_t status) const
{
    return (status & 0x02u) == 0x02u;
}

bool DmaManager::is_halted(uint32_t status) const
{
    return (status & 0x01u) == 0x01u;
}

std::optional<std::string> DmaManager::decode_error(uint32_t status) const
{
    if (status & 0x10u)
    {
        return std::string("DMA Internal Error (transfer length 0?)");
    }
    if (status & 0x20u)
    {
        return std::string("DMA Slave Error (cannot access memory map interface)");
    }
    if (status & 0x40u)
    {
        return std::string("DMA Decode Error (invalid address)");
    }
    return std::nullopt;
}

DMA::DMA(uint64_t base_address, size_t length)
    : manager_(base_address, length),
      sendchannel(manager_, DmaChannelDirection::MM2S),
      recvchannel(manager_, DmaChannelDirection::S2MM)
{
}

DMA::DMA(MMIO &mmio)
    : manager_(mmio),
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
