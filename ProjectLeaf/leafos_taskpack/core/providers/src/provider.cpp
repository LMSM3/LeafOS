#include "providers/provider.hpp"
#include "providers/minijson.hpp"

#include <iomanip>
#include <sstream>

namespace leafos::providers {

namespace {

std::string json_escape_impl(const std::string& s) {
	std::string out;
	out.reserve(s.size());
	for (char c : s) {
		switch (c) {
			case '"': out += "\\\""; break;
			case '\\': out += "\\\\"; break;
			case '\b': out += "\\b"; break;
			case '\f': out += "\\f"; break;
			case '\n': out += "\\n"; break;
			case '\r': out += "\\r"; break;
			case '\t': out += "\\t"; break;
			default: out += c; break;
		}
	}
	return out;
}

} // namespace

std::string json_escape_string(const std::string& s) {
	return json_escape_impl(s);
}

std::string provider_kind_to_string(ProviderKind kind) {
	switch (kind) {
		case ProviderKind::LlamaCpp: return "llama.cpp";
		case ProviderKind::Ollama: return "ollama";
		case ProviderKind::OpenAICompatible: return "openai_compatible";
		default: return "unknown";
	}
}

std::string placement_to_string(Placement p) {
	switch (p) {
		case Placement::Local: return "local";
		case Placement::Remote: return "remote";
		case Placement::Hybrid: return "hybrid";
		default: return "unknown";
	}
}

std::string stack_segment_to_string(StackSegment s) {
	switch (s) {
		case StackSegment::LocalCpu: return "local_cpu";
		case StackSegment::LocalGpu: return "local_gpu";
		case StackSegment::Remote: return "remote";
		case StackSegment::LocalAny:
		default: return "local_any";
	}
}

std::string thinking_phase_to_string(ThinkingPhase p) {
	switch (p) {
		case ThinkingPhase::Route: return "route";
		case ThinkingPhase::Plan: return "plan";
		case ThinkingPhase::Code: return "code";
		case ThinkingPhase::Review: return "review";
		case ThinkingPhase::Judge: return "judge";
		case ThinkingPhase::Recover: return "recover";
		case ThinkingPhase::Map: return "map";
		case ThinkingPhase::Write: return "write";
		case ThinkingPhase::Idle:
		default: return "idle";
	}
}

std::string chat_request_to_json(const ChatCompletionRequest& req) {
	std::ostringstream oss;
	oss << "{\n";
	oss << "  \"model\": \"" << json_escape_string(req.model) << "\",\n";
	oss << "  \"messages\": [\n";
	for (size_t i = 0; i < req.messages.size(); ++i) {
		if (i) oss << ",\n";
		oss << "    {\"role\": \"" << json_escape_string(req.messages[i].role) << "\", ";
		oss << "\"content\": \"" << json_escape_string(req.messages[i].content) << "\"}";
	}
	oss << "\n  ],\n";
	oss << "  \"max_tokens\": " << req.max_tokens << ",\n";
	oss << "  \"temperature\": " << req.temperature << ",\n";
	oss << "  \"stream\": " << (req.stream ? "true" : "false") << "\n";
	oss << "}\n";
	return oss.str();
}

std::string lane_result_to_json(const LaneResult& res) {
	std::ostringstream oss;
	oss << "{\n";
	oss << "  \"ok\": " << (res.ok ? "true" : "false") << ",\n";
	oss << "  \"finish_reason\": \"" << json_escape_string(res.finish_reason) << "\",\n";
	oss << "  \"content\": \"" << json_escape_string(res.content) << "\",\n";
	oss << "  \"usage\": {\n";
	oss << "    \"prompt_tokens\": " << res.usage.prompt_tokens << ",\n";
	oss << "    \"completion_tokens\": " << res.usage.completion_tokens << ",\n";
	oss << "    \"total_tokens\": " << res.usage.total_tokens << "\n";
	oss << "  },\n";
	oss << "  \"latency_ms\": " << res.latency_ms << ",\n";
	oss << "  \"provider_error\": \"" << json_escape_string(res.provider_error) << "\"\n";
	oss << "}\n";
	return oss.str();
}

} // namespace leafos::providers
