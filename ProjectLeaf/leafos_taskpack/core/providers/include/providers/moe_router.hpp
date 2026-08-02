#pragma once
// LeafOS deterministic orchestration-level expert router.

#include "providers/expert_registry.hpp"
#include "providers/types.hpp"

#include <map>
#include <string>
#include <vector>

namespace leafos::providers {

struct RoutingWeights {
	int64_t role_affinity = 100;
	int64_t capability_match = 80;
	int64_t expected_quality = 60;
	int64_t warm_endpoint_bonus = 20;
	int64_t memory_pressure = 30;
	int64_t latency_penalty = 10;
	int64_t estimated_cost = 40;
	int64_t recent_failure_penalty = 50;
};

struct RouterConfig {
	RoutingWeights weights;
	uint32_t parameter_floor_b = 9;
	double local_reserved_memory_gib = 2.0;
	uint32_t default_timeout_ms = 60000;
	double default_online_budget_usd = 0.0;
};

struct RouterTelemetry {
	std::vector<std::string> notes;
};

class MoeRouter {
public:
	explicit MoeRouter(const ExpertRegistry& registry, RouterConfig config = {});

	// Produce a dry-run route plan without invoking any provider.
	RoutePlan plan(const RequestFeatures& req,
				   const HostCapacity& host,
				   RouterTelemetry* telemetry = nullptr) const;

	// Return whether a specific expert passes hard eligibility + allow-model filters.
	bool check_eligible(const ExpertDescriptor& expert,
						const RequestFeatures& req,
						const HostCapacity& host,
						std::vector<std::string>& reasons) const;

	const RouterConfig& config() const { return config_; }

private:
	const ExpertRegistry& registry_;
	RouterConfig config_;

	bool is_eligible(const ExpertDescriptor& expert,
					 const RequestFeatures& req,
					 const HostCapacity& host,
					 std::vector<std::string>& reasons) const;
	int64_t score_eligible(const ExpertDescriptor& expert,
						   const RequestFeatures& req,
						   const HostCapacity& host) const;
	static std::string stable_hash_inputs(const RequestFeatures& req,
									  const HostCapacity& host,
									  const RouterConfig& cfg);
};


std::string route_plan_to_json(const RoutePlan& plan);
std::string route_failure_to_string(RouteFailure f);

} // namespace leafos::providers
