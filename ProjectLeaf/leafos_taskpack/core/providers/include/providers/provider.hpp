#pragma once
// LeafOS provider-neutral lane invocation interface (minimal real-use contract).

#include "providers/types.hpp"

#include <cstdint>
#include <string>
#include <vector>

namespace leafos::providers {

struct LaneMessage {
	std::string role;   // "system", "user", "assistant"
	std::string content;
};

struct TokenUsage {
	int64_t prompt_tokens = -1;
	int64_t completion_tokens = -1;
	int64_t total_tokens = -1;
};

struct LaneResult {
	bool ok = false;
	std::string finish_reason;       // "stop", "length", "timeout", "error"
	std::string content;
	std::string raw_response;
	TokenUsage usage;
	int64_t latency_ms = -1;
	std::string provider_error;      // sanitized, no secrets
};

// Serialize a chat request following the /v1/chat/completions contract.
struct ChatCompletionRequest {
	std::string model;
	std::vector<LaneMessage> messages;
	int64_t max_tokens = 512;
	double temperature = 0.7;
	bool stream = false;
};

std::string chat_request_to_json(const ChatCompletionRequest& req);
std::string lane_result_to_json(const LaneResult& res);
std::string json_escape_string(const std::string& s);
std::string provider_kind_to_string(ProviderKind kind);
std::string placement_to_string(Placement p);
std::string stack_segment_to_string(StackSegment s);
std::string thinking_phase_to_string(ThinkingPhase p);

} // namespace leafos::providers
