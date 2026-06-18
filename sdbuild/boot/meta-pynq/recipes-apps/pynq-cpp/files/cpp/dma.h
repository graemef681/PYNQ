/*
 * File: dma.h
 * Description: Board-side helper classes for remote DMA control.
 * Engineer Name: Graeme Fitzpatrick
 * Additional Contributors: OpenAI Codex
 * Project: PYNQ.remote
 * Created: 2026-06-16
 *
 * This file defines a service-independent DMA manager that mirrors the
 * high-level operations used by the Python PYNQ DMA driver. It is intended
 * to be called from a future gRPC service implementation and from local
 * pynq-cpp code that wants PYNQ-like DMA semantics without gRPC.
 */

#ifndef DMA_H
#define DMA_H

#include <cstdint>
#include <memory>
#include <optional>
#include <string>
#include <unordered_map>

#include "buffer.h"
#include "mmio.h"

enum class DmaChannelDirection
{
    MM2S = 1,
    S2MM = 2
};

enum class DmaCompletionMode
{
    Auto = 0,
    Poll = 1,
    Interrupt = 2
};

enum class DmaTransferMode
{
    Simple = 0,
    ScatterGather = 1
};

struct DmaTransferRequest
{
    DmaChannelDirection direction = DmaChannelDirection::MM2S;
    BufferRemote *buffer = nullptr;
    uint64_t start = 0;
    uint64_t nbytes = 0;
    DmaTransferMode transfer_mode = DmaTransferMode::Simple;
    bool cyclic = false;
};

struct DmaWaitRequest
{
    std::string transfer_id;
    DmaCompletionMode completion_mode = DmaCompletionMode::Auto;
    uint64_t timeout_ms = 0;
};

struct DmaTransferResult
{
    bool success = false;
    std::string message;
    std::string transfer_id;
};

struct DmaWaitResult
{
    bool success = false;
    std::string message;
    uint64_t transferred = 0;
    uint32_t dma_status = 0;
};

struct DmaStatusResult
{
    bool success = false;
    std::string message;
    bool running = false;
    bool idle = false;
    bool halted = false;
    uint32_t dma_status = 0;
    uint64_t transferred = 0;
};

class DMAChannel;

class DmaManager
{
public:
    DmaManager(uint64_t base_address, size_t length = 0x1000);
    explicit DmaManager(MMIO &mmio);

    DmaTransferResult transfer(const DmaTransferRequest &request);
    DmaWaitResult wait(const DmaWaitRequest &request);
    DmaWaitResult stop(const std::string &transfer_id);
    DmaStatusResult status(const std::string &transfer_id);

private:
    struct ActiveTransfer
    {
        DmaChannelDirection direction = DmaChannelDirection::MM2S;
        BufferRemote *buffer = nullptr;
        uint64_t start = 0;
        uint64_t nbytes = 0;
        bool cyclic = false;
        uint64_t transferred = 0;
        uint32_t last_status = 0;
    };

    static constexpr uint64_t kTxOffset = 0x00;
    static constexpr uint64_t kRxOffset = 0x30;
    static constexpr uint64_t kDmacrOffset = 0x00;
    static constexpr uint64_t kDmasrOffset = 0x04;
    static constexpr uint64_t kAddrLowOffset = 0x18;
    static constexpr uint64_t kAddrHighOffset = 0x1C;
    static constexpr uint64_t kLengthOffset = 0x28;
    static constexpr uint32_t kRunStop = 0x0001;
    static constexpr uint32_t kInterruptEnable = 0x1000;

    std::unique_ptr<MMIO> owned_mmio_;
    MMIO *mmio_;
    std::unordered_map<std::string, ActiveTransfer> transfers_;
    uint64_t transfer_counter_ = 0;

    MMIO &mmio() const;
    std::string generate_transfer_id();
    uint64_t channel_offset(DmaChannelDirection direction) const;
    uint32_t read_status(uint64_t channel_offset) const;
    bool is_running(uint32_t status) const;
    bool is_idle(uint32_t status) const;
    bool is_halted(uint32_t status) const;
    std::optional<std::string> decode_error(uint32_t status) const;
};

class DMAChannel
{
public:
    DMAChannel(DmaManager &manager, DmaChannelDirection direction);

    DmaTransferResult transfer(BufferRemote &buffer, uint64_t start = 0, uint64_t nbytes = 0);
    DmaTransferResult transfer(
        BufferRemote &buffer,
        uint64_t start,
        uint64_t nbytes,
        DmaTransferMode transfer_mode,
        bool cyclic = false);
    DmaWaitResult wait(
        DmaCompletionMode completion_mode = DmaCompletionMode::Auto,
        uint64_t timeout_ms = 0);
    DmaWaitResult stop();
    DmaStatusResult status();

    const std::string &active_transfer_id() const;
    bool has_active_transfer() const;

private:
    DmaManager *manager_;
    DmaChannelDirection direction_;
    std::string active_transfer_id_;
};

class DMA
{
public:
    DMA(uint64_t base_address, size_t length = 0x1000);
    explicit DMA(MMIO &mmio);

private:
    DmaManager manager_;

public:
    DMAChannel sendchannel;
    DMAChannel recvchannel;
};

#endif // DMA_H
