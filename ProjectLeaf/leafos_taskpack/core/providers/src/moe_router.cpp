#include "providers/moe_router.hpp"
#include "providers/minijson.hpp"
#include "providers/provider.hpp"

#include <algorithm>
#include <iomanip>
#include <sstream>

namespace leafos::providers {

namespace {

bool has_capability(const ExpertDescriptor& e, const std::string& cap) {
	for (const auto& c : e.capabilities) {
		if (c == cap) return true;
	}
	return false;
}

int64_t count_matches(const ExpertDescriptor& e, const std::vector<std::string>& caps) {
	int64_t n = 0;
	for (const auto& c : caps) {
		if (has_capability(e, c)) ++n;
	}
	return n;
}

std::string join_strings(const std::vector<std::string>& v) {
	std::string out;
	for (size_t i = 0; i < v.size(); ++i) {
		if (i) out += ",";
		out += v[i];
	}
	return out;
}

} // namespace

MoeRouter::MoeRouter(const ExpertRegistry& registry, RouterConfig config)
	: registry_(registry), config_(std::move(config)) {}

RoutePlan MoeRouter::plan(const RequestFeatures& req_in,
						  const HostCapacity& host,
						  RouterTelemetry* telemetry) const {
	RoutePlan plan;
	plan.timeout_ms = config_.default_timeout_ms;
	plan.stable_hash = stable_hash_inputs(req_in, host, config_);

	RequestFeatures req = req_in;
	if (req.required_capabilities.empty()) {
		if (req.role == "coder") req.required_capabilities = {"proposal.patch"};
		else if (req.role == "brain") req.required_capabilities = {"proposal.review"};
		else if (req.role == "mapper") req.required_capabilities = {"context.map"};
		else if (req.role == "qa") req.required_capabilities = {"qa"};
	}

	auto candidates = registry_.enabled_experts();
	if (telemetry) telemetry->notes.push_back("enabled experts: " + std::to_string(candidates.size()));

	std::vector<RouteCandidate> eligible;
	for (const auto& e : candidates) {
		std::vector<std::string> reasons;
		if (is_eligible(e, req, host, reasons)) {
			RouteCandidate cand;
			cand.expert_id = e.id;
			cand.score = score_eligible(e, req, host);
			eligible.push_back(cand);
		} else {
			RejectedCandidate rc;
			rc.expert_id = e.id;
			rc.reason = reasons.empty() ? "ineligible" : join_strings(reasons);
			plan.rejected.push_back(rc);
		}
	}

	if (eligible.empty()) {
		plan.terminal_failure = RouteFailure::NoEligibleExpert;
		plan.fallback_policy = "none";
		return plan;
	}

	std::stable_sort(eligible.begin(), eligible.end(), [](const auto& a, const auto& b) {
		if (a.score != b.score) return a.score > b.score;
		return a.expert_id < b.expert_id; // stable tie-break
	});

	const auto& selected = registry_.get(eligible.front().expert_id);
	if (!selected) {
		plan.terminal_failure = RouteFailure::NoEligibleExpert;
		return plan;
	}

	plan.selected_expert_id = selected->id;
	plan.selected_model_ref = selected->model_ref;
	plan.selected_provider = selected->provider;
	plan.selected_placement = selected->placement;
	plan.selected_stack_segment = selected->stack_segment;
	plan.endpoint_ref = selected->endpoint_ref;
	plan.capabilities_used = selected->capabilities;
	plan.estimated_memory_gib = selected->estimated_memory_gib;
	plan.context_ceiling = std::min(selected->context_tokens, req.context_tokens == 0 ? selected->context_tokens : req.context_tokens);
	plan.fallback_policy = "profile_declared";

	if (telemetry) {
		telemetry->notes.push_back("selected score: " + std::to_string(eligible.front().score));
	}
	return plan;
}

bool MoeRouter::check_eligible(const ExpertDescriptor& e,
							   const RequestFeatures& req,
							   const HostCapacity& host,
							   std::vector<std::string>& reasons) const {
	return is_eligible(e, req, host, reasons);
}

bool MoeRouter::is_eligible(const ExpertDescriptor& e,
							const RequestFeatures& req,
							const HostCapacity& host,
							std::vector<std::string>& reasons) const {
	bool ok = true;
	if (!e.enabled) { reasons.push_back("disabled"); ok = false; }
	if (e.placement == Placement::Remote && !req.allow_remote) {
		reasons.push_back("remote_denied"); ok = false;
	}
	if (e.placement == Placement::Hybrid && !req.allow_hybrid && !req.allow_remote) {
		reasons.push_back("hybrid_denied"); ok = false;
	}
	if (e.parameters_b < req.parameter_floor_b) {
		reasons.push_back("parameter_floor"); ok = false;
	}
	if (e.parameters_b < config_.parameter_floor_b) {
		reasons.push_back("garden_floor"); ok = false;
	}
	if (!req.required_capabilities.empty() && count_matches(e, req.required_capabilities) == 0) {
		reasons.push_back("capability_denied"); ok = false;
	}
	if (req.context_tokens > 0 && e.context_tokens < req.context_tokens) {
		reasons.push_back("context_too_large"); ok = false;
	}
	if (e.placement == Placement::Local) {
		double available = host.available_ram_gib - host.reserved_memory_gib;
		if (available > 0 && e.estimated_memory_gib > available) {
			reasons.push_back("memory_unavailable"); ok = false;
		}
		// unknown VRAM is treated as unknown, not a rejection
		if (host.available_vram_gib >= 0.0 && e.estimated_memory_gib > host.available_vram_gib && e.estimated_memory_gib <= available) {
			// Could still load into system RAM; just note it in telemetry. Not rejected.
		}
	}

	// Stack segment constraint. If the request prefers a specific CPU/GPU
	// segment, reject experts that cannot run there.
	if (req.preferred_segment != StackSegment::LocalAny &&
		req.preferred_segment != StackSegment::Remote) {
		if (e.placement == Placement::Remote) {
			reasons.push_back("segment_remote"); ok = false;
		} else if (e.stack_segment != StackSegment::LocalAny &&
				   e.stack_segment != req.preferred_segment) {
			reasons.push_back("segment_mismatch"); ok = false;
		}
	}

	// Per-assignment allow-model filters. Checked after capability/role eligibility
	// so denials are explicit and auditable.
	const auto& f = req.filter;
	if (!f.deny_ids.empty()) {
		for (const auto& id : f.deny_ids) {
			if (e.id == id) { reasons.push_back("deny_list"); ok = false; break; }
		}
	}
	if (!f.allow_ids.empty()) {
		bool matched = false;
		for (const auto& id : f.allow_ids) {
			if (e.id == id) { matched = true; break; }
		}
		if (!matched) { reasons.push_back("allow_list"); ok = false; }
	}
	if (!f.require_quantization.empty()) {
		bool matched = false;
		for (const auto& q : f.require_quantization) {
			if (e.quantization == q) { matched = true; break; }
		}
		if (!matched) { reasons.push_back("quantization_mismatch"); ok = false; }
	}
	if (f.require_provider.has_value()) {
		std::string kind;
		switch (e.provider) {
			case ProviderKind::LlamaCpp: kind = "llama.cpp"; break;
			case ProviderKind::Ollama: kind = "ollama"; break;
			case ProviderKind::OpenAICompatible: kind = "openai_compatible"; break;
			default: kind = "unknown"; break;
		}
		if (kind != *f.require_provider) { reasons.push_back("provider_mismatch"); ok = false; }
	}
	return ok;
}

int64_t MoeRouter::score_eligible(const ExpertDescriptor& e,
								  const RequestFeatures& req,
								  const HostCapacity& host) const {
	const auto& w = config_.weights;
	int64_t score = 0;

	// Role affinity heuristic
	int64_t role_score = 0;
	if (req.role == "coder") role_score = (has_capability(e, "proposal.patch") ? 20 : 0);
	else if (req.role == "brain") role_score = (has_capability(e, "proposal.review") ? 20 : 0);
	else if (req.role == "mapper") role_score = (has_capability(e, "context.map") ? 20 : 0);
	else if (req.role == "qa") role_score = (has_capability(e, "qa") ? 20 : 0);
	score += role_score * w.role_affinity / 20;

	// Capability match
	if (!req.required_capabilities.empty()) {
		score += (count_matches(e, req.required_capabilities) * 100 / static_cast<int64_t>(req.required_capabilities.size())) * w.capability_match / 100;
	} else {
		score += w.capability_match / 2;
	}

	// Expected quality: prefer parameters near the role's target, scaled by quantization roughness
	int64_t target_param = 30;
	if (req.role == "mapper") target_param = 12;
	else if (req.role == "coder") target_param = 30;
	else if (req.role == "brain") target_param = 27;
	else if (req.role == "qa") target_param = 27;
	int64_t delta = static_cast<int64_t>(e.parameters_b) - target_param;
	if (delta < 0) delta = -delta;
	int64_t quality_score = std::max<int64_t>(0, 100 - delta);
	if (e.quantization == "Q4_K_M" || e.quantization == "Q5_K_S") quality_score = quality_score * 90 / 100;
	else if (e.quantization == "IQ2_M" || e.quantization == "Q2_K") quality_score = quality_score * 75 / 100;
	score += quality_score * w.expected_quality / 100;

	// Warm endpoint: local is warmer than remote (simple heuristic)
	if (e.placement == Placement::Local) score += w.warm_endpoint_bonus;

	// Memory pressure: penalize larger footprint
	score -= static_cast<int64_t>(e.estimated_memory_gib * w.memory_pressure / 2.0);

	// Latency penalty: remote gets a fixed penalty
	if (e.placement == Placement::Remote) score -= w.latency_penalty;

	// Cost: zero for local; remote needs budget check handled in eligibility for iteration A
	if (e.placement == Placement::Remote) score -= w.estimated_cost;

	// Recent failure: not tracked in iteration A, apply none
	// score -= <history>

	return score;
}

std::string MoeRouter::stable_hash_inputs(const RequestFeatures& req,
										  const HostCapacity& host,
										  const RouterConfig& cfg) {
	std::ostringstream oss;
	oss << req.role << "|";
	for (const auto& c : req.required_capabilities) oss << c << ",";
	oss << "|" << req.parameter_floor_b << "|" << req.context_tokens
		<< "|" << req.allow_remote << "|" << req.allow_hybrid << "|" << req.online_budget_usd
		<< "|" << host.available_ram_gib << "|" << host.available_vram_gib
		<< "|" << host.reserved_memory_gib << "|" << host.logical_cpus
		<< "|" << cfg.parameter_floor_b << "|" << cfg.default_timeout_ms;
	// Simple DJB2 hash
	std::string raw = oss.str();
	unsigned long h = 5381;
	for (char c : raw) h = ((h << 5) + h) + static_cast<unsigned char>(c);
	std::ostringstream hex;
	hex << std::hex << std::setfill('0') << std::setw(16) << h;
	return hex.str();
}

std::string route_failure_to_string(RouteFailure f) {
	switch (f) {
		case RouteFailure::None: return "none";
		case RouteFailure::NoEligibleExpert: return "NoEligibleExpert";
		case RouteFailure::MemoryUnavailable: return "MemoryUnavailable";
		case RouteFailure::ContextTooLarge: return "ContextTooLarge";
		case RouteFailure::CapabilityDenied: return "CapabilityDenied";
		case RouteFailure::BudgetDenied: return "BudgetDenied";
		case RouteFailure::ProviderUnavailable: return "ProviderUnavailable";
		case RouteFailure::Timeout: return "Timeout";
		case RouteFailure::InvalidResponse: return "InvalidResponse";
	}
	return "unknown";
}

static std::string json_escape(const std::string& s) { return leafos::providers::json_escape_string(s); }

std::string route_plan_to_json(const RoutePlan& plan) {
	std::ostringstream oss;
	oss << "{\n";
	oss << "  \"schema\": \"" << plan.schema << "\",\n";
	oss << "  \"selected_expert_id\": \"" << json_escape(plan.selected_expert_id) << "\",\n";
	oss << "  \"selected_model_ref\": \"" << json_escape(plan.selected_model_ref) << "\",\n";
	oss << "  \"selected_provider\": \"" << json_escape(route_failure_to_string(RouteFailure::None)) << "\",\n";
	// Provider/placement/segment strings
	oss << "  \"provider_kind\": \"" << json_escape(provider_kind_to_string(plan.selected_provider)) << "\",\n";
	oss << "  \"placement\": \"" << json_escape(placement_to_string(plan.selected_placement)) << "\",\n";
	oss << "  \"stack_segment\": \"" << json_escape(stack_segment_to_string(plan.selected_stack_segment)) << "\",\n";
	oss << "  \"endpoint_ref\": \"" << json_escape(plan.endpoint_ref) << "\",\n";
	oss << "  \"capabilities_used\": [";
	for (size_t i = 0; i < plan.capabilities_used.size(); ++i) {
		if (i) oss << ", ";
		oss << "\"" << json_escape(plan.capabilities_used[i]) << "\"";
	}
	oss << "],\n";
	oss << "  \"rejected_candidates\": [\n";
	for (size_t i = 0; i < plan.rejected.size(); ++i) {
		const auto& r = plan.rejected[i];
		if (i) oss << ",\n";
		oss << "    {\"expert_id\": \"" << json_escape(r.expert_id) << "\", \"reason\": \"" << json_escape(r.reason) << "\"}";
	}
	oss << "\n  ],\n";
	oss << std::fixed << std::setprecision(2);
	oss << "  \"estimated_memory_gib\": " << plan.estimated_memory_gib << ",\n";
	oss << "  \"context_ceiling\": " << plan.context_ceiling << ",\n";
	oss << "  \"timeout_ms\": " << plan.timeout_ms << ",\n";
	oss << "  \"fallback_policy\": \"" << json_escape(plan.fallback_policy) << "\",\n";
	oss << "  \"terminal_failure\": \"" << route_failure_to_string(plan.terminal_failure) << "\",\n";
	oss << "  \"stable_hash\": \"" << plan.stable_hash << "\"\n";
	oss << "}\n";
	return oss.str();
}

} // namespace leafos::providers
