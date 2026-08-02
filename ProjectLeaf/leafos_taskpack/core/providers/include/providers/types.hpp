#pragma once
// LeafOS provider routing types

#include <string>
#include <vector>
#include <cstdint>
#include <optional>

namespace leafos::providers {

enum class ProviderKind { LlamaCpp, Ollama, OpenAICompatible, Unknown };
enum class Placement { Local, Remote, Hybrid };

// Runtime placement segment: where a local expert is expected to execute.
// local_any means either CPU or GPU is acceptable; local_cpu/local_gpu force one.
enum class StackSegment { LocalAny, LocalCpu, LocalGpu, Remote };

// Lightweight phase marker for the reasoning/thinking loop.
enum class ThinkingPhase { Idle, Route, Plan, Code, Review, Judge, Recover, Map, Write };

enum class RouteFailure {
	None,
	NoEligibleExpert,
	MemoryUnavailable,
	ContextTooLarge,
	CapabilityDenied,
	BudgetDenied,
	ProviderUnavailable,
	Timeout,
	InvalidResponse
};

struct ExpertDescriptor {
	std::string schema;
	std::string id;
	std::string model_ref;
	std::string source_repo;
	std::string revision;
	uint32_t parameters_b = 0;
	ProviderKind provider = ProviderKind::Unknown;
	Placement placement = Placement::Local;
	StackSegment stack_segment = StackSegment::LocalAny;
	std::string endpoint_ref;
	std::string quantization;
	double estimated_memory_gib = 0.0;
	uint32_t context_tokens = 0;
	std::vector<std::string> capabilities;
	std::vector<std::string> fallback_chain;
	bool enabled = false;
};

struct HostCapacity {
	double available_ram_gib = 0.0;
	double available_vram_gib = -1.0; // -1 means unknown
	double reserved_memory_gib = 2.0;
	uint32_t logical_cpus = 1;
};

struct AllowModelFilter {
	std::vector<std::string> allow_ids;       // if non-empty, expert id must match one
	std::vector<std::string> deny_ids;        // always reject these ids
	std::vector<std::string> require_quantization; // optional hard filter
	std::optional<std::string> require_provider;   // optional "llama.cpp", etc.

	bool empty() const {
		return allow_ids.empty() && deny_ids.empty() &&
			   require_quantization.empty() && !require_provider.has_value();
	}
};

struct RequestFeatures {
	std::string role; // e.g. "coder", "brain", "mapper", "qa"
	std::string slot; // logical slot requested, e.g. "primary"
	std::vector<std::string> required_capabilities;
	uint32_t parameter_floor_b = 0;
	uint32_t context_tokens = 0;
	bool allow_remote = false;
	bool allow_hybrid = false;
	double online_budget_usd = 0.0;
	StackSegment preferred_segment = StackSegment::LocalAny; // CPU/GPU/any preference
	AllowModelFilter filter;
	ThinkingPhase phase = ThinkingPhase::Idle; // reasoning loop phase request
};

struct RouteCandidate {
	std::string expert_id;
	int64_t score = 0;           // fixed-point integer score
	std::vector<std::string> reject_reasons;
};

struct RejectedCandidate {
	std::string expert_id;
	std::string reason;
};

struct RoutePlan {
	std::string schema = "leafos.route.plan.v1";
	std::string selected_expert_id;
	std::string selected_model_ref;
	ProviderKind selected_provider = ProviderKind::Unknown;
	Placement selected_placement = Placement::Local;
	StackSegment selected_stack_segment = StackSegment::LocalAny;
	std::string endpoint_ref;
	std::vector<std::string> capabilities_used;
	std::vector<RejectedCandidate> rejected;
	double estimated_memory_gib = 0.0;
	uint32_t context_ceiling = 0;
	uint32_t timeout_ms = 60000;
	std::string fallback_policy = "none";
	RouteFailure terminal_failure = RouteFailure::None;
	std::string stable_hash;
};

} // namespace leafos::providers
