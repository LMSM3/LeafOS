#include "providers/model_group.hpp"
#include "providers/minijson.hpp"
#include "providers/provider.hpp"

#include <filesystem>
#include <fstream>

namespace leafos::providers {

GroupRegistry::GroupRegistry(const std::string& config_root)
	: config_root_(config_root) {}

static std::string read_text(const std::string& path) {
	std::string raw = minijson::read_file(path);
	return raw;
}

bool GroupRegistry::load_all(std::string* error_out) {
	groups_.clear();
	std::filesystem::path root(config_root_);
	std::filesystem::path dir = root / group_dir_name();
	if (!std::filesystem::is_directory(dir)) {
		if (error_out) *error_out = "group directory not found: " + dir.string();
		return false;
	}
	for (const auto& entry : std::filesystem::directory_iterator(dir)) {
		if (!entry.is_regular_file()) continue;
		const auto& p = entry.path();
		if (p.extension() != ".json") continue;
		if (!load_file(p.string(), error_out)) return false;
	}
	return true;
}

std::optional<ModelGroup> GroupRegistry::get(const std::string& id) const {
	auto it = groups_.find(id);
	if (it == groups_.end()) return std::nullopt;
	return it->second;
}

bool GroupRegistry::load_file(const std::string& path, std::string* error_out) {
	using namespace leafos::minijson;
	try {
		std::string raw = read_text(path);
		Value root = parse(raw);
		if (!root.is_object()) throw std::runtime_error("group root is not an object");

		ModelGroup g;
		g.schema = root["schema"].as_string();
		g.id = root["id"].as_string();
		g.slot = root["slot"].as_string();
		g.enabled = root["enabled"].as_bool();
		if (root.has_key("notes")) g.notes = root["notes"].as_string();

		const Value& policy = root["policy"];
		if (policy.is_object()) {
			if (policy.has_key("parallel_load")) g.policy.parallel_load = policy["parallel_load"].as_bool();
			if (policy.has_key("max_vram_gib")) g.policy.max_vram_gib = policy["max_vram_gib"].as_number();
			if (policy.has_key("max_ram_gib")) g.policy.max_ram_gib = policy["max_ram_gib"].as_number();
			if (policy.has_key("allow_remote")) g.policy.allow_remote = policy["allow_remote"].as_bool();
			if (policy.has_key("preferred_quantization")) {
				const Value& pq = policy["preferred_quantization"];
				if (pq.is_array()) {
					for (const auto& v : pq.as_array()) g.policy.preferred_quantization.push_back(v.as_string());
				}
			}
		}

		const Value& members = root["members"];
		if (members.is_array()) {
			for (const auto& m : members.as_array()) {
				if (!m.is_object()) continue;
				GroupMember gm;
				gm.id = m["id"].as_string();
				if (m.has_key("weight")) gm.weight = static_cast<int32_t>(m["weight"].as_int());
				if (m.has_key("remote_only")) gm.remote_only = m["remote_only"].as_bool();
				g.members.push_back(gm);
			}
		}

		if (g.id.empty()) throw std::runtime_error("group missing id");
		groups_[g.id] = std::move(g);
	} catch (const std::exception& e) {
		if (error_out) *error_out = std::string("group parse error in ") + path + ": " + e.what();
		return false;
	}
	return true;
}

} // namespace leafos::providers
