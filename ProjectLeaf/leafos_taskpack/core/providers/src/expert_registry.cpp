#include "providers/expert_registry.hpp"
#include "providers/minijson.hpp"

#include <algorithm>
#include <fstream>
#include <sstream>

namespace leafos::providers {

ProviderKind provider_kind_from_string(const std::string& s) {
	if (s == "llama.cpp") return ProviderKind::LlamaCpp;
	if (s == "ollama") return ProviderKind::Ollama;
	if (s == "openai_compatible") return ProviderKind::OpenAICompatible;
	return ProviderKind::Unknown;
}

Placement placement_from_string(const std::string& s) {
	if (s == "local") return Placement::Local;
	if (s == "remote") return Placement::Remote;
	if (s == "hybrid") return Placement::Hybrid;
	return Placement::Local;
}

StackSegment stack_segment_from_string(const std::string& s) {
	if (s == "local_cpu") return StackSegment::LocalCpu;
	if (s == "local_gpu") return StackSegment::LocalGpu;
	if (s == "local_any") return StackSegment::LocalAny;
	if (s == "remote") return StackSegment::Remote;
	return StackSegment::LocalAny;
}

ExpertRegistry::ExpertRegistry(std::string config_root)
	: config_root_(std::move(config_root)) {}

static void collect_expert_files(const std::filesystem::path& dir, std::vector<std::filesystem::path>& out) {
	if (!std::filesystem::is_directory(dir)) return;
	for (const auto& e : std::filesystem::recursive_directory_iterator(dir)) {
		if (e.is_regular_file() && e.path().extension() == ".json") {
			out.push_back(e.path());
		}
	}
}

static std::filesystem::path taskpack_experts_dir(const std::filesystem::path& config_root) {
	// If config_root is the providers build tree (<taskpack>/core/providers),
	// also look for the canonical taskpack config tree two levels up.
	return config_root.parent_path().parent_path() / "config" / "experts";
}

bool ExpertRegistry::load_all(std::string* error_out) {
	std::filesystem::path primary = config_root_ / "config" / "experts";
	std::filesystem::path fallback = taskpack_experts_dir(config_root_);
	if (!std::filesystem::is_directory(primary) && !std::filesystem::is_directory(fallback)) {
		if (error_out) *error_out = "experts directory not found: " + primary.string();
		return false;
	}
	bool ok = true;
	std::vector<std::filesystem::path> files;
	collect_expert_files(primary, files);
	if (fallback != primary) collect_expert_files(fallback, files);
	std::sort(files.begin(), files.end(), [](const auto& a, const auto& b) {
		return a.lexically_normal().string() < b.lexically_normal().string();
	});
	for (const auto& f : files) {
		if (f.filename().string() == "expert.schema.json") continue;
		auto opt = parse_file(f, error_out);
		if (!opt) { ok = false; continue; }
		if (!add(*opt, error_out)) ok = false;
	}
	return ok;
}

bool ExpertRegistry::add(const ExpertDescriptor& expert, std::string* error_out) {
	if (expert.id.empty()) {
		if (error_out) *error_out = "refusing anonymous expert";
		return false;
	}
	if (experts_.count(expert.id)) {
		if (error_out) *error_out = "duplicate expert id: " + expert.id;
		return false;
	}
	experts_[expert.id] = expert;
	return true;
}

std::optional<ExpertDescriptor> ExpertRegistry::get(const std::string& id) const {
	auto it = experts_.find(id);
	if (it == experts_.end()) return std::nullopt;
	return it->second;
}

std::vector<ExpertDescriptor> ExpertRegistry::enabled_experts() const {
	std::vector<ExpertDescriptor> out;
	for (const auto& kv : experts_) {
		if (kv.second.enabled) out.push_back(kv.second);
	}
	return out;
}

std::optional<ExpertDescriptor> ExpertRegistry::parse_file(const std::filesystem::path& p, std::string* error_out) const {
	try {
		std::string raw = minijson::read_file(p.string());
		minijson::Value v = minijson::parse(raw);
		ExpertDescriptor e;
		e.schema = v["schema"].as_string();
		if (e.schema != "leafos.expert.v1") {
			if (error_out) *error_out = p.string() + ": unknown schema " + e.schema;
			return std::nullopt;
		}
		e.id = v["id"].as_string();
		e.model_ref = v["model_ref"].as_string();
		if (v.has_key("source_repo")) e.source_repo = v["source_repo"].as_string();
		if (v.has_key("revision")) e.revision = v["revision"].as_string();
		e.parameters_b = static_cast<uint32_t>(v["parameters_b"].as_int());
		e.provider = provider_kind_from_string(v["provider"].as_string());
		e.placement = placement_from_string(v["placement"].as_string());
		if (v.has_key("stack_segment")) {
			e.stack_segment = stack_segment_from_string(v["stack_segment"].as_string());
		} else if (e.placement == Placement::Remote) {
			e.stack_segment = StackSegment::Remote;
		} else {
			e.stack_segment = StackSegment::LocalAny;
		}
		e.endpoint_ref = v["endpoint_ref"].as_string();
		if (v.has_key("quantization")) e.quantization = v["quantization"].as_string();
		e.estimated_memory_gib = v["estimated_memory_gib"].as_number();
		e.context_tokens = static_cast<uint32_t>(v["context_tokens"].as_int());
		for (const auto& cap : v["capabilities"].as_array()) {
			e.capabilities.push_back(cap.as_string());
		}
		if (v.has_key("fallback_chain")) {
			for (const auto& fb : v["fallback_chain"].as_array()) {
				e.fallback_chain.push_back(fb.as_string());
			}
		}
		e.enabled = v["enabled"].as_bool();
		return e;
	} catch (const std::exception& ex) {
		if (error_out) *error_out = std::string("parse error in ") + p.string() + ": " + ex.what();
		return std::nullopt;
	}
}

} // namespace leafos::providers
