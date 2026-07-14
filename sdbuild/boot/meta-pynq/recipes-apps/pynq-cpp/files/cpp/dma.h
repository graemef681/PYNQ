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

#ifdef USE_XAXIDMA
struct XAxiDma;
#endif

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

struct DmaHardwareConfig
{
    bool has_sts_cntrl_strm = false;
    bool has_mm2s = true;
    bool has_mm2s_dre = false;
    uint32_t mm2s_data_width = 32;
    bool has_s2mm = true;
    bool has_s2mm_dre = false;
    uint32_t s2mm_data_width = 32;
    bool has_sg = false;
    uint32_t mm2s_num_channels = 1;
    uint32_t s2mm_num_channels = 1;
    uint32_t mm2s_burst_size = 16;
    uint32_t s2mm_burst_size = 16;
    bool micro_dma_mode = false;
    uint32_t addr_width = 32;
    uint32_t sg_length_width = 23;
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
    DmaManager(uint64_t base_address, size_t length = 0x1000, std::optional<DmaHardwareConfig> config = std::nullopt);
    explicit DmaManager(MMIO &mmio, std::optional<DmaHardwareConfig> config = std::nullopt);
    ~DmaManager();

    DmaTransferResult transfer(const DmaTransferRequest &request);
    DmaWaitResult wait(const DmaWaitRequest &request);
    DmaWaitResult stop(const std::string &transfer_id);
    DmaStatusResult status(const std::string &transfer_id);
    bool backend_ready() const;
    const std::string &backend_error() const;
    bool using_xaxidma() const;

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

    std::unique_ptr<MMIO> owned_mmio_;
    MMIO *mmio_;
    std::unordered_map<std::string, ActiveTransfer> transfers_;
    uint64_t transfer_counter_ = 0;
    std::optional<DmaHardwareConfig> hardware_config_;
    bool use_xaxidma_ = false;
    std::string backend_error_;

#ifdef USE_XAXIDMA
    std::unique_ptr<XAxiDma> axidma_instance_;
#endif

    MMIO &mmio() const;
    std::string generate_transfer_id();
    void initialize_backend();
    bool ensure_backend_ready(std::string &message) const;

#ifdef USE_XAXIDMA
    std::optional<std::string> initialize_xaxidma(const DmaHardwareConfig &config);
    std::string xaxidma_status_to_string(int status) const;
    int xaxidma_direction(DmaChannelDirection direction) const;
    uint32_t read_xaxidma_status(DmaChannelDirection direction) const;
    uint32_t read_xaxidma_transferred(DmaChannelDirection direction) const;
    bool xaxidma_is_running(uint32_t status) const;
    bool xaxidma_is_idle(uint32_t status) const;
    bool xaxidma_is_halted(uint32_t status) const;
    std::optional<std::string> decode_xaxidma_error(uint32_t status) const;
#endif
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
    DMA(uint64_t base_address, size_t length = 0x1000, std::optional<DmaHardwareConfig> config = std::nullopt);
    explicit DMA(MMIO &mmio, std::optional<DmaHardwareConfig> config = std::nullopt);

private:
    DmaManager manager_;

public:
    DMAChannel sendchannel;
    DMAChannel recvchannel;
    bool backend_ready() const { return manager_.backend_ready(); }
    const std::string &backend_error() const { return manager_.backend_error(); }
    bool using_xaxidma() const { return manager_.using_xaxidma(); }
};

#endif // DMA_H
