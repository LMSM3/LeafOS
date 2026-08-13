#pragma once

#include "leaf/memory/event.hpp"

#include <cstdint>
#include <filesystem>
#include <string>
#include <vector>

namespace leaf::memory {

struct JournalRecord {
	std::uint64_t offset = 0;
	Event event;
};

struct JournalVerification {
	bool valid = false;
	bool recovered_truncated_tail = false;
	std::uint64_t valid_records = 0;
	std::string message;
};

class Journal {
public:
	explicit Journal(std::filesystem::path path);

	bool append(const Event& event, std::string& error);
	JournalVerification verify(std::vector<JournalRecord>* records = nullptr) const;
	JournalVerification recover();

private:
	std::filesystem::path path_;
};

} // namespace leaf::memory
