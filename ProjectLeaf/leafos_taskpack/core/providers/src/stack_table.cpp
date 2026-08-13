#include "providers/stack_table.hpp"
#include "providers/provider.hpp"

#include <iomanip>
#include <sstream>

namespace leafos::providers {

StackTable::StackTable(const HostCapacity& host) : host_(host) {}

void StackTable::assign(StackSegment segment, const std::string& expert_id,
						const std::string& slot, double memory_gib) {
	StackRow r;
	r.segment_name = stack_segment_to_string(segment);
	r.active_expert_id = expert_id;
	r.active_slot = slot;
	r.phase = current_phase_;
	r.loaded = true;
	r.memory_gib = memory_gib;
	rows_[segment] = r;
}

void StackTable::clear(StackSegment segment) {
	rows_.erase(segment);
}

std::optional<StackRow> StackTable::row(StackSegment segment) const {
	auto it = rows_.find(segment);
	if (it == rows_.end()) return std::nullopt;
	return it->second;
}

StackSegment StackTable::preferred_segment_for_phase(ThinkingPhase phase,
												 const HostCapacity& host) const {
	bool gpu_known = host.available_vram_gib >= 0.0;
	bool gpu_available = gpu_known && host.available_vram_gib > 8.0;

	switch (phase) {
		case ThinkingPhase::Code:
		case ThinkingPhase::Review:
			return gpu_available ? StackSegment::LocalGpu : StackSegment::LocalCpu;
		case ThinkingPhase::Judge:
		case ThinkingPhase::Recover:
			// Heavy judge/recovery may overflow GPU; prefer CPU segment if declared.
			return StackSegment::LocalCpu;
		case ThinkingPhase::Route:
		case ThinkingPhase::Map:
		case ThinkingPhase::Write:
		case ThinkingPhase::Plan:
		default:
			return StackSegment::LocalAny;
	}
}

std::string StackTable::to_json() const {
	std::ostringstream oss;
	oss << "[\n";
	size_t i = 0;
	for (const auto& kv : rows_) {
		const auto& r = kv.second;
		oss << "  {\"segment\": \"" << json_escape_string(r.segment_name) << "\",";
		oss << " \"expert_id\": \"" << json_escape_string(r.active_expert_id) << "\",";
		oss << " \"slot\": \"" << json_escape_string(r.active_slot) << "\",";
		oss << " \"phase\": \"" << thinking_phase_to_string(r.phase) << "\",";
		oss << " \"loaded\": " << (r.loaded ? "true" : "false") << ",";
		oss << " \"memory_gib\": " << std::fixed << std::setprecision(2) << r.memory_gib << "}";
		if (++i < rows_.size()) oss << ",";
		oss << "\n";
	}
	oss << "]";
	return oss.str();
}

} // namespace leafos::providers
