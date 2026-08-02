#include "leaf/memory/journal.hpp"

#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>

namespace {

std::string read_file(const std::filesystem::path& path) {
	std::ifstream input(path, std::ios::binary);
	std::ostringstream contents;
	contents << input.rdbuf();
	return contents.str();
}

std::string json_escape(const std::string& value) {
	std::string escaped;
	for (const char character : value) {
		if (character == '"' || character == '\\') escaped.push_back('\\');
		escaped.push_back(character);
	}
	return escaped;
}

void print_result(bool ok, const std::string& message, std::uint64_t records = 0, bool recovered = false) {
	std::cout << "{\"ok\":" << (ok ? "true" : "false")
			  << ",\"message\":\"" << json_escape(message) << "\""
			  << ",\"records\":" << records
			  << ",\"recovered_truncated_tail\":" << (recovered ? "true" : "false")
			  << "}\n";
}

bool option_value(int argc, char** argv, const std::string& option, std::string& value) {
	for (int index = 0; index + 1 < argc; ++index) {
		if (argv[index] == option) {
			value = argv[index + 1];
			return true;
		}
	}
	return false;
}

} // namespace

int main(int argc, char** argv) {
	if (argc < 2) {
		print_result(false, "usage: leaf-memory <append|verify|recover|replay> --journal PATH [--event PATH]");
		return 2;
	}

	const std::string command = argv[1];
	std::string journal_path;
	if (!option_value(argc - 2, argv + 2, "--journal", journal_path) || journal_path.empty()) {
		print_result(false, "--journal PATH is required");
		return 2;
	}
	leaf::memory::Journal journal(journal_path);

	if (command == "append") {
		std::string event_path;
		if (!option_value(argc - 2, argv + 2, "--event", event_path) || event_path.empty()) {
			print_result(false, "append requires --event PATH");
			return 2;
		}
		const auto parsed = leaf::memory::parse_event(read_file(event_path));
		if (parsed.status != leaf::memory::ValidationStatus::valid) {
			print_result(false, parsed.message);
			return 1;
		}
		std::string error;
		if (!journal.append(parsed.event, error)) {
			print_result(false, error);
			return 1;
		}
		print_result(true, "event appended", 1);
		return 0;
	}

	if (command == "verify") {
		const auto result = journal.verify();
		print_result(result.valid, result.message, result.valid_records, result.recovered_truncated_tail);
		return result.valid && !result.recovered_truncated_tail ? 0 : 1;
	}

	if (command == "recover") {
		const auto result = journal.recover();
		print_result(result.valid, result.message, result.valid_records, result.recovered_truncated_tail);
		return result.valid ? 0 : 1;
	}

	if (command == "replay") {
		std::vector<leaf::memory::JournalRecord> records;
		const auto result = journal.verify(&records);
		if (!result.valid || result.recovered_truncated_tail) {
			print_result(false, result.message, result.valid_records, result.recovered_truncated_tail);
			return 1;
		}
		std::cout << "{\"ok\":true,\"records\":" << records.size() << ",\"events\":[";
		for (std::size_t index = 0; index < records.size(); ++index) {
			if (index != 0) std::cout << ',';
			std::cout << records[index].event.canonical_json;
		}
		std::cout << "]}\n";
		return 0;
	}

	print_result(false, "unsupported command: " + command);
	return 2;
}
