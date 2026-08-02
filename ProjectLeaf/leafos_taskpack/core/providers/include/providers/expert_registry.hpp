#pragma once
// LeafOS expert registry: load and validate configured experts.

#include "providers/types.hpp"

#include <filesystem>
#include <map>
#include <optional>
#include <string>
#include <vector>

namespace leafos::providers {

ProviderKind provider_kind_from_string(const std::string& s);
Placement placement_from_string(const std::string& s);

class ExpertRegistry {
public:
	explicit ExpertRegistry(std::string config_root);

	bool load_all(std::string* error_out = nullptr);
	bool add(const ExpertDescriptor& expert, std::string* error_out = nullptr);

	const std::map<std::string, ExpertDescriptor>& experts() const { return experts_; }
	std::optional<ExpertDescriptor> get(const std::string& id) const;
	std::vector<ExpertDescriptor> enabled_experts() const;

	static constexpr uint32_t k_parameter_floor_b = 9; // garden contract floor

private:
	std::filesystem::path config_root_;
	std::map<std::string, ExpertDescriptor> experts_;

	std::optional<ExpertDescriptor> parse_file(const std::filesystem::path& p, std::string* error_out) const;
};

} // namespace leafos::providers
