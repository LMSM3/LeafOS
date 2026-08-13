#include "leaf/memory/journal.hpp"

#include <array>
#include <cstring>
#include <fstream>
#include <system_error>

namespace leaf::memory {
namespace {

constexpr std::array<char, 4> k_magic = {'L', 'M', 'E', 'M'};
constexpr std::uint16_t k_format_version = 1;
constexpr std::size_t k_header_size = 4 + 2 + 2 + 8 + 4 + 64;
constexpr std::uint32_t k_max_payload_bytes = 16U * 1024U * 1024U;

void write_u16(std::ostream& stream, std::uint16_t value) {
	for (unsigned int index = 0; index < 2; ++index) stream.put(static_cast<char>((value >> (index * 8U)) & 0xffU));
}

void write_u32(std::ostream& stream, std::uint32_t value) {
	for (unsigned int index = 0; index < 4; ++index) stream.put(static_cast<char>((value >> (index * 8U)) & 0xffU));
}

void write_u64(std::ostream& stream, std::uint64_t value) {
	for (unsigned int index = 0; index < 8; ++index) stream.put(static_cast<char>((value >> (index * 8U)) & 0xffU));
}

bool read_u16(std::istream& stream, std::uint16_t& value) {
	value = 0;
	for (unsigned int index = 0; index < 2; ++index) {
		const int byte = stream.get();
		if (byte == EOF) return false;
		value |= static_cast<std::uint16_t>(static_cast<unsigned char>(byte)) << (index * 8U);
	}
	return true;
}

bool read_u32(std::istream& stream, std::uint32_t& value) {
	value = 0;
	for (unsigned int index = 0; index < 4; ++index) {
		const int byte = stream.get();
		if (byte == EOF) return false;
		value |= static_cast<std::uint32_t>(static_cast<unsigned char>(byte)) << (index * 8U);
	}
	return true;
}

bool read_u64(std::istream& stream, std::uint64_t& value) {
	value = 0;
	for (unsigned int index = 0; index < 8; ++index) {
		const int byte = stream.get();
		if (byte == EOF) return false;
		value |= static_cast<std::uint64_t>(static_cast<unsigned char>(byte)) << (index * 8U);
	}
	return true;
}

JournalVerification read_journal(const std::filesystem::path& path, std::vector<JournalRecord>* records) {
	JournalVerification result;
	result.valid = true;
	if (!std::filesystem::exists(path)) {
		result.message = "empty journal";
		return result;
	}

	std::ifstream input(path, std::ios::binary);
	if (!input) {
		result.valid = false;
		result.message = "cannot open journal";
		return result;
	}

	std::uint64_t offset = 0;
	std::string previous_hash;
	for (;;) {
		const auto record_offset = offset;
		std::array<char, 4> magic{};
		input.read(magic.data(), static_cast<std::streamsize>(magic.size()));
		if (input.gcount() == 0 && input.eof()) break;
		if (input.gcount() != static_cast<std::streamsize>(magic.size()) || magic != k_magic) {
			result.recovered_truncated_tail = true;
			result.message = "truncated or invalid record header";
			break;
		}
		offset += magic.size();
		std::uint16_t version = 0;
		std::uint16_t reserved = 0;
		std::uint64_t sequence = 0;
		std::uint32_t payload_length = 0;
		if (!read_u16(input, version) || !read_u16(input, reserved) || !read_u64(input, sequence) || !read_u32(input, payload_length)) {
			result.recovered_truncated_tail = true;
			result.message = "truncated record header";
			break;
		}
		offset += 2 + 2 + 8 + 4;
		std::array<char, 64> checksum{};
		input.read(checksum.data(), static_cast<std::streamsize>(checksum.size()));
		if (input.gcount() != static_cast<std::streamsize>(checksum.size()) || version != k_format_version || reserved != 0 || payload_length > k_max_payload_bytes) {
			result.recovered_truncated_tail = true;
			result.message = "invalid record framing";
			break;
		}
		offset += checksum.size();
		std::string payload(payload_length, '\0');
		input.read(payload.data(), static_cast<std::streamsize>(payload.size()));
		if (input.gcount() != static_cast<std::streamsize>(payload.size())) {
			result.recovered_truncated_tail = true;
			result.message = "truncated record payload";
			break;
		}
		offset += payload.size();
		if (sha256_hex(payload) != std::string(checksum.data(), checksum.size())) {
			result.valid = false;
			result.message = "record checksum mismatch";
			return result;
		}
		const auto parsed = parse_event(payload);
		if (parsed.status != ValidationStatus::valid || parsed.event.metadata.sequence != sequence) {
			result.valid = false;
			result.message = "invalid event payload";
			return result;
		}
		if (result.valid_records == 0) {
			if (parsed.event.metadata.has_previous_event) {
				result.valid = false;
				result.message = "first record must not have a previous hash";
				return result;
			}
		} else if (!parsed.event.metadata.has_previous_event || parsed.event.metadata.previous_event_sha256 != previous_hash) {
			result.valid = false;
			result.message = "per-run hash chain mismatch";
			return result;
		}
		previous_hash = parsed.event.metadata.payload_sha256;
		++result.valid_records;
		if (records) records->push_back({record_offset, parsed.event});
	}
	if (result.message.empty()) result.message = "journal verified";
	return result;
}

} // namespace

Journal::Journal(std::filesystem::path path) : path_(std::move(path)) {}

bool Journal::append(const Event& event, std::string& error) {
	const auto verification = verify();
	if (!verification.valid || verification.recovered_truncated_tail) {
		error = verification.recovered_truncated_tail ? "journal requires recovery before append" : verification.message;
		return false;
	}
	std::vector<JournalRecord> records;
	const auto current = verify(&records);
	if (!current.valid) {
		error = current.message;
		return false;
	}
	if (event.canonical_json.size() > k_max_payload_bytes) {
		error = "event exceeds journal payload limit";
		return false;
	}
	if (records.empty()) {
		if (event.metadata.sequence != 1 || event.metadata.has_previous_event) {
			error = "first event must be sequence 1 without a previous hash";
			return false;
		}
	} else {
		const auto& prior = records.back().event.metadata;
		if (event.metadata.sequence != prior.sequence + 1 || !event.metadata.has_previous_event ||
			event.metadata.previous_event_sha256 != prior.payload_sha256) {
			error = "event sequence or previous hash does not continue the journal";
			return false;
		}
	}

	std::filesystem::create_directories(path_.parent_path());
	std::ofstream output(path_, std::ios::binary | std::ios::app);
	if (!output) {
		error = "cannot open journal for append";
		return false;
	}
	output.write(k_magic.data(), static_cast<std::streamsize>(k_magic.size()));
	write_u16(output, k_format_version);
	write_u16(output, 0);
	write_u64(output, event.metadata.sequence);
	write_u32(output, static_cast<std::uint32_t>(event.canonical_json.size()));
	const auto checksum = sha256_hex(event.canonical_json);
	output.write(checksum.data(), static_cast<std::streamsize>(checksum.size()));
	output.write(event.canonical_json.data(), static_cast<std::streamsize>(event.canonical_json.size()));
	output.flush();
	if (!output) {
		error = "journal append failed";
		return false;
	}
	return true;
}

JournalVerification Journal::verify(std::vector<JournalRecord>* records) const {
	if (records) records->clear();
	return read_journal(path_, records);
}

JournalVerification Journal::recover() {
	std::vector<JournalRecord> records;
	auto result = verify(&records);
	if (!result.valid || !result.recovered_truncated_tail) return result;

	std::uint64_t valid_size = 0;
	if (!records.empty()) {
		const auto& last = records.back();
		valid_size = last.offset + k_header_size + last.event.canonical_json.size();
	}
	std::error_code error;
	std::filesystem::resize_file(path_, valid_size, error);
	if (error) {
		result.valid = false;
		result.message = "failed to truncate journal during recovery";
		return result;
	}
	result.message = "truncated journal tail removed";
	return result;
}

} // namespace leaf::memory
