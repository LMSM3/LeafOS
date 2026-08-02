#pragma once
// LeafOS predefined model group loader.

#include <cstdint>
#include <map>
#include <string>
#include <vector>
#include <optional>

namespace leafos::providers {

struct GroupMember {
	std::string id;
	int32_t weight = 0;
	bool remote_only = false;
};

struct GroupPolicy {
	bool parallel_load = false;
	std::vector<std::string> preferred_quantization;
	double max_vram_gib = 0.0;
	double max_ram_gib = 0.0;
	bool allow_remote = false;
};

struct ModelGroup {
	std::string schema;
	std::string id;
	std::string slot;
	bool enabled = false;
	GroupPolicy policy;
	std::vector<GroupMember> members;
	std::string notes;
};

class GroupRegistry {
public:
	explicit GroupRegistry(const std::string& config_root);

	// Load all *.json files under <config_root>/groups/.
	bool load_all(std::string* error_out);

	const std::map<std::string, ModelGroup>& groups() const { return groups_; }
	std::optional<ModelGroup> get(const std::string& id) const;

	static std::string group_dir_name() { return "groups"; }

private:
	std::string config_root_;
	std::map<std::string, ModelGroup> groups_;

	bool load_file(const std::string& path, std::string* error_out);
};

} // namespace leafos::providers
