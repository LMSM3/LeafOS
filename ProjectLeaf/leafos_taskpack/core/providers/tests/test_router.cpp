#include "providers/expert_registry.hpp"
#include "providers/host_capacity.hpp"
#include "providers/moe_router.hpp"
#include "providers/types.hpp"

#include <cassert>
#include <cstdlib>
#include <filesystem>
#include <iostream>
#include <sstream>
#include <string>

using namespace leafos::providers;

static int g_passed = 0;
static int g_failed = 0;

#define CHECK(expr) do { \
	if (!(expr)) { \
		std::cerr << "FAIL " << __FILE__ << ":" << __LINE__ << " " << #expr << "\n"; \
		g_failed++; \
	} else { g_passed++; } \
} while (0)

void test_registry_load() {
	ExpertRegistry reg(std::filesystem::current_path().string());
	std::string err;
	CHECK(reg.load_all(&err));
	CHECK(reg.experts().size() >= 5);
}

void test_7b_rejected_by_garden_floor() {
	ExpertRegistry reg(std::filesystem::current_path().string());
	CHECK(reg.load_all(nullptr));
	auto small = reg.get("qwen25-mapper-7b-q4km-local");
	CHECK(small.has_value());
	CHECK(small->parameters_b == 7);
	CHECK(small->enabled);

	MoeRouter router(reg);
	RequestFeatures req;
	req.role = "mapper";
	req.context_tokens = 1000;
	HostCapacity host{ .available_ram_gib = 64.0, .reserved_memory_gib = 2.0 };
	auto plan = router.plan(req, host);
	bool found = false;
	for (const auto& r : plan.rejected) {
		if (r.expert_id == "qwen25-mapper-7b-q4km-local" && r.reason.find("garden_floor") != std::string::npos) {
			found = true; break;
		}
	}
	CHECK(found);
	// The 14B mapper should be selected instead.
	CHECK(plan.terminal_failure == RouteFailure::None);
}

void test_context_overflow() {
	ExpertRegistry reg(std::filesystem::current_path().string());
	CHECK(reg.load_all(nullptr));
	MoeRouter router(reg);
	RequestFeatures req;
	req.role = "mapper";
	req.context_tokens = 100000; // larger than any local expert
	HostCapacity host{ .available_ram_gib = 64.0, .reserved_memory_gib = 2.0 };
	auto plan = router.plan(req, host);
	CHECK(plan.terminal_failure == RouteFailure::NoEligibleExpert);
}

void test_remote_disabled_by_default() {
	ExpertRegistry reg(std::filesystem::current_path().string());
	CHECK(reg.load_all(nullptr));
	MoeRouter router(reg);
	// "qa" has only remote experts in the installed registry.
	RequestFeatures req;
	req.role = "qa";
	HostCapacity host{ .available_ram_gib = 64.0, .reserved_memory_gib = 2.0 };
	auto plan = router.plan(req, host);
	CHECK(plan.terminal_failure == RouteFailure::NoEligibleExpert);

	req.allow_remote = true;
	auto plan2 = router.plan(req, host);
	CHECK(plan2.terminal_failure == RouteFailure::None);
	CHECK(!plan2.selected_expert_id.empty());
}

void test_tie_break_stable() {
	ExpertRegistry reg(std::filesystem::current_path().string());
	CHECK(reg.load_all(nullptr));
	MoeRouter router(reg);
	// Blue brain has two local experts; scoring must be deterministic across calls.
	RequestFeatures req;
	req.role = "brain";
	HostCapacity host{ .available_ram_gib = 64.0, .reserved_memory_gib = 2.0 };
	auto plan1 = router.plan(req, host);
	auto plan2 = router.plan(req, host);
	CHECK(plan1.terminal_failure == RouteFailure::None);
	CHECK(!plan1.selected_expert_id.empty());
	CHECK(plan1.selected_expert_id == plan2.selected_expert_id);
}

void test_coder_prefers_local_32b() {
	ExpertRegistry reg(std::filesystem::current_path().string());
	CHECK(reg.load_all(nullptr));
	MoeRouter router(reg);
	RequestFeatures req;
	req.role = "coder";
	HostCapacity host{ .available_ram_gib = 64.0, .reserved_memory_gib = 2.0 };
	auto plan = router.plan(req, host);
	CHECK(plan.terminal_failure == RouteFailure::None);
	CHECK(plan.selected_expert_id == "qwen25-coder-32b-iq2m-local");
}

void test_json_output_has_schema() {
	ExpertRegistry reg(std::filesystem::current_path().string());
	CHECK(reg.load_all(nullptr));
	MoeRouter router(reg);
	RequestFeatures req;
	req.role = "mapper";
	HostCapacity host{ .available_ram_gib = 64.0, .reserved_memory_gib = 2.0 };
	auto plan = router.plan(req, host);
	std::string json = route_plan_to_json(plan);
	CHECK(json.find("leafos.route.plan.v1") != std::string::npos);
	CHECK(json.find("\"selected_expert_id\"") != std::string::npos);
}

void test_allow_list_pins_single_expert() {
	ExpertRegistry reg(std::filesystem::current_path().string());
	CHECK(reg.load_all(nullptr));
	MoeRouter router(reg);
	RequestFeatures req;
	req.role = "mapper";
	req.filter.allow_ids = { "qwen25-mapper-14b-q4km-local" };
	HostCapacity host{ .available_ram_gib = 64.0, .reserved_memory_gib = 2.0 };
	auto plan = router.plan(req, host);
	CHECK(plan.terminal_failure == RouteFailure::None);
	CHECK(plan.selected_expert_id == "qwen25-mapper-14b-q4km-local");
	bool found = false;
	for (const auto& r : plan.rejected) {
		if (r.reason.find("allow_list") != std::string::npos) found = true;
	}
	CHECK(found);
}

void test_deny_list_excludes_expert() {
	ExpertRegistry reg(std::filesystem::current_path().string());
	CHECK(reg.load_all(nullptr));
	MoeRouter router(reg);
	RequestFeatures req;
	req.role = "mapper";
	req.filter.deny_ids = { "qwen25-mapper-14b-q4km-local" };
	HostCapacity host{ .available_ram_gib = 64.0, .reserved_memory_gib = 2.0 };
	auto plan = router.plan(req, host);
	CHECK(plan.terminal_failure == RouteFailure::NoEligibleExpert);
	bool found = false;
	for (const auto& r : plan.rejected) {
		if (r.expert_id == "qwen25-mapper-14b-q4km-local" && r.reason.find("deny_list") != std::string::npos) {
			found = true; break;
		}
	}
	CHECK(found);
}

void test_require_quantization_excludes_others() {
	ExpertRegistry reg(std::filesystem::current_path().string());
	CHECK(reg.load_all(nullptr));
	MoeRouter router(reg);
	RequestFeatures req;
	req.role = "coder";
	// The installed Blue coder primary uses Q6_K; require it explicitly.
	req.filter.require_quantization = { "Q6_K" };
	HostCapacity host{ .available_ram_gib = 64.0, .reserved_memory_gib = 2.0 };
	auto plan = router.plan(req, host);
	CHECK(plan.terminal_failure == RouteFailure::None);
	CHECK(plan.selected_expert_id == "blue-coder-primary");
}

std::filesystem::path g_repo_root;

int main(int argc, char** argv) {
	g_repo_root = std::filesystem::absolute(argv[0]).parent_path().parent_path();
	std::filesystem::current_path(g_repo_root);

	// tests may run from core/providers; normalize to taskpack root for recursive expert discovery
	if (!std::filesystem::is_directory(g_repo_root / "config" / "experts")) {
		g_repo_root = g_repo_root.parent_path().parent_path();
		if (!std::filesystem::is_directory(g_repo_root / "config" / "experts")) {
			std::cerr << "cannot locate config/experts from " << argv[0] << "\n";
			return 1;
		}
		std::filesystem::current_path(g_repo_root);
	}

	test_registry_load();
	test_7b_rejected_by_garden_floor();
	test_context_overflow();
	test_remote_disabled_by_default();
	test_tie_break_stable();
	test_coder_prefers_local_32b();
	test_json_output_has_schema();
	test_allow_list_pins_single_expert();
	test_deny_list_excludes_expert();
	test_require_quantization_excludes_others();

	std::cout << g_passed << " passed, " << g_failed << " failed\n";
	return g_failed == 0 ? 0 : 1;
}
