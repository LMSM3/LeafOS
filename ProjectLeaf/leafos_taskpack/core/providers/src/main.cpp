#include "providers/expert_registry.hpp"
#include "providers/host_capacity.hpp"
#include "providers/moe_router.hpp"
#include "providers/minijson.hpp"

#include <filesystem>
#include <iostream>
#include <string>

namespace {

void print_usage(const char* argv0) {
	std::cerr << "Usage:\n"
			  << "  " << argv0 << " plan --role ROLE [--cap CAP]... [--context N] [--remote] [--hybrid] [--budget USD]\n"
			  << "  " << argv0 << " list\n";
}

} // namespace

int main(int argc, char** argv) {
	if (argc < 2) {
		print_usage(argv[0]);
		return 1;
	}

	std::string command = argv[1];
	std::filesystem::path self = std::filesystem::absolute(argv[0]);
	std::filesystem::path repo_root = self.parent_path().parent_path();
	leafos::providers::ExpertRegistry registry(repo_root.string());
	std::string err;
	if (!registry.load_all(&err)) {
		std::cerr << "registry load error: " << err << "\n";
		return 1;
	}

	if (command == "list") {
		for (const auto& kv : registry.experts()) {
			const auto& e = kv.second;
			std::cout << e.id << " " << e.parameters_b << "B "
					  << (e.enabled ? "enabled" : "disabled") << "\n";
		}
		return 0;
	}

	if (command == "plan") {
		leafos::providers::RequestFeatures req;
		req.parameter_floor_b = leafos::providers::ExpertRegistry::k_parameter_floor_b;
		for (int i = 2; i < argc; ++i) {
			std::string arg = argv[i];
			if (arg == "--role" && i + 1 < argc) req.role = argv[++i];
			else if (arg == "--cap" && i + 1 < argc) req.required_capabilities.push_back(argv[++i]);
			else if (arg == "--context" && i + 1 < argc) req.context_tokens = static_cast<uint32_t>(std::stoul(argv[++i]));
			else if (arg == "--remote") req.allow_remote = true;
			else if (arg == "--hybrid") req.allow_hybrid = true;
			else if (arg == "--budget" && i + 1 < argc) req.online_budget_usd = std::stod(argv[++i]);
		}

		leafos::providers::MoeRouter router(registry);
		leafos::providers::HostCapacity host = leafos::providers::detect_host_capacity();
		leafos::providers::RouterTelemetry telemetry;
		auto plan = router.plan(req, host, &telemetry);
		std::cout << leafos::providers::route_plan_to_json(plan);
		return 0;
	}

	print_usage(argv[0]);
	return 1;
}
