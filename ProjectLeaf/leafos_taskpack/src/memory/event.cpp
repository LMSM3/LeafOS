#include "leaf/memory/event.hpp"

#include <array>
#include <cctype>
#include <iomanip>
#include <sstream>
#include <utility>
#include <vector>

namespace leaf::memory {
namespace {

constexpr std::array<std::uint32_t, 64> k_sha256 = {
	0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
	0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
	0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
	0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
	0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
	0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
	0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
	0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2
};

std::uint32_t rotate_right(std::uint32_t value, std::uint32_t bits) {
	return (value >> bits) | (value << (32U - bits));
}

std::string canonicalize_json(const std::string& json) {
	std::string canonical;
	canonical.reserve(json.size());
	bool in_string = false;
	bool escaped = false;
	for (const char ch : json) {
		if (in_string) {
			canonical.push_back(ch);
			if (escaped) {
				escaped = false;
			} else if (ch == '\\') {
				escaped = true;
			} else if (ch == '"') {
				in_string = false;
			}
		} else if (ch == '"') {
			in_string = true;
			canonical.push_back(ch);
		} else if (!std::isspace(static_cast<unsigned char>(ch))) {
			canonical.push_back(ch);
		}
	}
	return canonical;
}

bool extract_string(const std::string& json, const std::string& key, std::string& value, std::size_t* value_offset = nullptr) {
	const std::string marker = "\"" + key + "\":\"";
	const auto start = json.find(marker);
	if (start == std::string::npos) return false;
	const auto content_start = start + marker.size();
	std::size_t cursor = content_start;
	bool escaped = false;
	while (cursor < json.size()) {
		if (!escaped && json[cursor] == '"') break;
		if (!escaped && json[cursor] == '\\') escaped = true;
		else escaped = false;
		++cursor;
	}
	if (cursor == json.size()) return false;
	value = json.substr(content_start, cursor - content_start);
	if (value_offset) *value_offset = content_start;
	return true;
}

bool extract_positive_sequence(const std::string& json, std::uint64_t& value) {
	const std::string marker = "\"sequence\":";
	const auto start = json.find(marker);
	if (start == std::string::npos) return false;
	const auto number_start = start + marker.size();
	const auto number_end = json.find_first_not_of("0123456789", number_start);
	if (number_end == number_start) return false;
	try {
		value = std::stoull(json.substr(number_start, number_end - number_start));
	} catch (...) {
		return false;
	}
	return value > 0;
}

bool has_required_value(const std::string& json, const std::string& key) {
	return json.find("\"" + key + "\":") != std::string::npos;
}

} // namespace

std::string sha256_hex(const std::string& value) {
	std::array<std::uint32_t, 8> state = {
		0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
		0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19
	};
	std::vector<std::uint8_t> bytes(value.begin(), value.end());
	const std::uint64_t bit_length = static_cast<std::uint64_t>(bytes.size()) * 8U;
	bytes.push_back(0x80U);
	while ((bytes.size() % 64U) != 56U) bytes.push_back(0U);
	for (int shift = 56; shift >= 0; shift -= 8) bytes.push_back(static_cast<std::uint8_t>(bit_length >> shift));

	for (std::size_t offset = 0; offset < bytes.size(); offset += 64) {
		std::array<std::uint32_t, 64> words{};
		for (std::size_t index = 0; index < 16; ++index) {
			words[index] = (static_cast<std::uint32_t>(bytes[offset + index * 4]) << 24U) |
						   (static_cast<std::uint32_t>(bytes[offset + index * 4 + 1]) << 16U) |
						   (static_cast<std::uint32_t>(bytes[offset + index * 4 + 2]) << 8U) |
						   static_cast<std::uint32_t>(bytes[offset + index * 4 + 3]);
		}
		for (std::size_t index = 16; index < words.size(); ++index) {
			const auto s0 = rotate_right(words[index - 15], 7) ^ rotate_right(words[index - 15], 18) ^ (words[index - 15] >> 3U);
			const auto s1 = rotate_right(words[index - 2], 17) ^ rotate_right(words[index - 2], 19) ^ (words[index - 2] >> 10U);
			words[index] = words[index - 16] + s0 + words[index - 7] + s1;
		}
		auto a = state[0]; auto b = state[1]; auto c = state[2]; auto d = state[3];
		auto e = state[4]; auto f = state[5]; auto g = state[6]; auto h = state[7];
		for (std::size_t index = 0; index < words.size(); ++index) {
			const auto sigma1 = rotate_right(e, 6) ^ rotate_right(e, 11) ^ rotate_right(e, 25);
			const auto choose = (e & f) ^ (~e & g);
			const auto temporary1 = h + sigma1 + choose + k_sha256[index] + words[index];
			const auto sigma0 = rotate_right(a, 2) ^ rotate_right(a, 13) ^ rotate_right(a, 22);
			const auto majority = (a & b) ^ (a & c) ^ (b & c);
			const auto temporary2 = sigma0 + majority;
			h = g; g = f; f = e; e = d + temporary1;
			d = c; c = b; b = a; a = temporary1 + temporary2;
		}
		state[0] += a; state[1] += b; state[2] += c; state[3] += d;
		state[4] += e; state[5] += f; state[6] += g; state[7] += h;
	}

	std::ostringstream output;
	for (const auto word : state) output << std::hex << std::setfill('0') << std::setw(8) << word;
	return output.str();
}

ValidationResult parse_event(std::string json) {
	ValidationResult result;
	Event event;
	event.canonical_json = canonicalize_json(json);
	if (event.canonical_json.empty() || event.canonical_json.front() != '{' || event.canonical_json.back() != '}') {
		result.message = "event must be a JSON object";
		return result;
	}
	std::string schema;
	if (!extract_string(event.canonical_json, "schema", schema)) {
		result.message = "missing schema";
		return result;
	}
	if (schema != "leafos.memory.event.v1") {
		result.status = ValidationStatus::unsupported;
		result.message = "unsupported memory event schema";
		return result;
	}
	if (!extract_string(event.canonical_json, "event_id", event.metadata.event_id) ||
		!extract_string(event.canonical_json, "run_id", event.metadata.run_id) ||
		!extract_positive_sequence(event.canonical_json, event.metadata.sequence)) {
		result.message = "missing or invalid event identity";
		return result;
	}
	for (const char* required : {"project_id", "timestamp_utc", "kind", "epistemic_class", "source", "scope", "content", "retrieval", "integrity"}) {
		if (!has_required_value(event.canonical_json, required)) {
			result.message = std::string("missing required field: ") + required;
			return result;
		}
	}
	std::size_t hash_offset = 0;
	if (!extract_string(event.canonical_json, "payload_sha256", event.metadata.payload_sha256, &hash_offset) || event.metadata.payload_sha256.size() != 64) {
		result.message = "missing or invalid payload_sha256";
		return result;
	}
	std::string previous;
	if (extract_string(event.canonical_json, "previous_event_sha256", previous)) {
		if (previous.size() != 64) {
			result.message = "invalid previous_event_sha256";
			return result;
		}
		event.metadata.previous_event_sha256 = previous;
		event.metadata.has_previous_event = true;
	} else if (event.canonical_json.find("\"previous_event_sha256\":null") == std::string::npos) {
		result.message = "missing previous_event_sha256";
		return result;
	}

	std::string payload = event.canonical_json;
	payload.replace(hash_offset, 64, 64, '0');
	const auto calculated_hash = sha256_hex(payload);
	if (event.metadata.payload_sha256 != std::string(64, '0') && event.metadata.payload_sha256 != calculated_hash) {
		result.message = "payload_sha256 does not match canonical payload";
		return result;
	}
	event.canonical_json.replace(hash_offset, 64, calculated_hash);
	event.metadata.payload_sha256 = calculated_hash;
	result.status = ValidationStatus::valid;
	result.message = "valid";
	result.event = std::move(event);
	return result;
}

} // namespace leaf::memory
