#pragma once

#include <cstdint>
#include <string>

namespace leaf::memory {

enum class ValidationStatus {
	valid,
	invalid,
	unsupported
};

struct EventMetadata {
	std::string event_id;
	std::string run_id;
	std::uint64_t sequence = 0;
	std::string payload_sha256;
	std::string previous_event_sha256;
	bool has_previous_event = false;
};

struct Event {
	std::string canonical_json;
	EventMetadata metadata;
};

struct ValidationResult {
	ValidationStatus status = ValidationStatus::invalid;
	std::string message;
	Event event;
};

ValidationResult parse_event(std::string json);
std::string sha256_hex(const std::string& value);

} // namespace leaf::memory
