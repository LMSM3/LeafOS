#pragma once
// LeafOS stack table: the bridge between the reasoning/thinking loop,
// CPU/GPU stack segments, and the currently active modelExpert per segment.

#include "providers/types.hpp"

#include <map>
#include <optional>
#include <string>
#include <vector>

namespace leafos::providers {

// One row in the stack table. A row tells the reasoning loop which expert is
// currently assigned to a segment and what phase it is serving.
struct StackRow {
	std::string segment_name;          // "local_gpu", "local_cpu", "remote"
	std::string active_expert_id;
	std::string active_slot;
	ThinkingPhase phase = ThinkingPhase::Idle;
	bool loaded = false;
	double memory_gib = 0.0;
};

// Provides the three-component wiring:
//   1. reasoning/thinking loop phase
//   2. CPU/GPU stack segment assignment
//   3. selected expert activation and serialization
class StackTable {
public:
	StackTable() = default;
	explicit StackTable(const HostCapacity& host);

	// Set or query phase. The phase drives which segment is preferred.
	void set_phase(ThinkingPhase phase) { current_phase_ = phase; }
	ThinkingPhase phase() const { return current_phase_; }

	// Assign an expert to a segment row.
	void assign(StackSegment segment, const std::string& expert_id,
				const std::string& slot, double memory_gib);

	// Clear a segment row.
	void clear(StackSegment segment);

	// Return row if one exists.
	std::optional<StackRow> row(StackSegment segment) const;

	// Preferred segment for a phase. GPU is preferred for code/review when
	// available, CPU is preferred for judge-bedrock/recovery, any otherwise.
	StackSegment preferred_segment_for_phase(ThinkingPhase phase,
										 const HostCapacity& host) const;

	// Active rows as JSON for telemetry/session plans.
	std::string to_json() const;

	const std::map<StackSegment, StackRow>& rows() const { return rows_; }

private:
	std::map<StackSegment, StackRow> rows_;
	ThinkingPhase current_phase_ = ThinkingPhase::Idle;
	HostCapacity host_;
};

} // namespace leafos::providers
