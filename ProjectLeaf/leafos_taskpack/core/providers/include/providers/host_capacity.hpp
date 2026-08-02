#pragma once
// Host capacity snapshot for local routing decisions.

#include "providers/types.hpp"

namespace leafos::providers {

// Snapshot available RAM, optional VRAM, and reserved headroom.
// Missing data is represented by zeros or negatives, never infinite.
HostCapacity detect_host_capacity();

} // namespace leafos::providers
