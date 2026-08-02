// LeafOS roundtable — single-file conversational orchestrator.
// Targets the local llama.cpp server at http://127.0.0.1:8080 by default.
// Fails closed with an actionable message when the server is not healthy.

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <winhttp.h>
#pragma comment(lib, "winhttp.lib")

#include "providers/expert_registry.hpp"
#include "providers/host_capacity.hpp"
#include "providers/minijson.hpp"
#include "providers/model_group.hpp"
#include "providers/moe_router.hpp"
#include "providers/provider.hpp"
#include "providers/stack_table.hpp"
#include "providers/types.hpp"

#include <chrono>
#include <cstdlib>
#include <filesystem>
#include <iostream>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

namespace lp = leafos::providers;

namespace {

struct HttpResponse {
	bool ok = false;
	long status = 0;
	std::string body;
	std::string error;
};

std::wstring to_wstring(const std::string& s) {
	if (s.empty()) return std::wstring();
	int n = ::MultiByteToWideChar(CP_UTF8, 0, s.c_str(), -1, nullptr, 0);
	if (n <= 0) return std::wstring();
	std::wstring out(n, 0);
	::MultiByteToWideChar(CP_UTF8, 0, s.c_str(), -1, out.data(), n);
	out.resize(static_cast<size_t>(n) - 1);
	return out;
}

std::string from_wstring(const std::wstring& s) {
	if (s.empty()) return std::string();
	int n = ::WideCharToMultiByte(CP_UTF8, 0, s.c_str(), -1, nullptr, 0, nullptr, nullptr);
	if (n <= 0) return std::string();
	std::string out(n, 0);
	::WideCharToMultiByte(CP_UTF8, 0, s.c_str(), -1, out.data(), n, nullptr, nullptr);
	out.resize(static_cast<size_t>(n) - 1);
	return out;
}

struct ParsedUrl {
	std::string scheme;
	std::string host;
	INTERNET_PORT port = 0;
	std::string path;
};

ParsedUrl parse_url(const std::string& url) {
	ParsedUrl u;
	size_t scheme_end = url.find("://");
	if (scheme_end == std::string::npos) return u;
	u.scheme = url.substr(0, scheme_end);
	size_t authority_start = scheme_end + 3;
	size_t path_start = url.find('/', authority_start);
	std::string authority;
	if (path_start == std::string::npos) {
		authority = url.substr(authority_start);
		u.path = "/";
	} else {
		authority = url.substr(authority_start, path_start - authority_start);
		u.path = url.substr(path_start);
		if (u.path.empty()) u.path = "/";
	}
	size_t colon = authority.find(':');
	if (colon == std::string::npos) {
		u.host = authority;
		u.port = (u.scheme == "https") ? INTERNET_DEFAULT_HTTPS_PORT : INTERNET_DEFAULT_HTTP_PORT;
	} else {
		u.host = authority.substr(0, colon);
		u.port = static_cast<INTERNET_PORT>(std::stoul(authority.substr(colon + 1)));
	}
	return u;
}

void close_handle(HINTERNET h) {
	if (h) ::WinHttpCloseHandle(h);
}

HttpResponse http_request(const std::string& url,
						  const wchar_t* method,
						  const std::string& request_body,
						  uint32_t timeout_ms) {
	HttpResponse res;
	ParsedUrl u = parse_url(url);
	if (u.host.empty() || u.port == 0) {
		res.error = "invalid URL: " + url;
		return res;
	}

	HINTERNET hSession = ::WinHttpOpen(L"LeafOS-Roundtable/1.0",
									   WINHTTP_ACCESS_TYPE_DEFAULT_PROXY,
									   WINHTTP_NO_PROXY_NAME,
									   WINHTTP_NO_PROXY_BYPASS, 0);
	if (!hSession) {
		res.error = "WinHttpOpen failed: " + std::to_string(::GetLastError());
		return res;
	}

	HINTERNET hConnect = ::WinHttpConnect(hSession, to_wstring(u.host).c_str(), u.port, 0);
	if (!hConnect) {
		res.error = "WinHttpConnect failed: " + std::to_string(::GetLastError());
		close_handle(hSession);
		return res;
	}

	DWORD flags = (u.scheme == "https") ? WINHTTP_FLAG_SECURE : 0;
	std::wstring path_w = to_wstring(u.path);
	HINTERNET hRequest = ::WinHttpOpenRequest(hConnect, method, path_w.c_str(),
											  NULL, WINHTTP_NO_REFERER,
											  WINHTTP_DEFAULT_ACCEPT_TYPES, flags);
	if (!hRequest) {
		res.error = "WinHttpOpenRequest failed: " + std::to_string(::GetLastError());
		close_handle(hConnect);
		close_handle(hSession);
		return res;
	}

	::WinHttpSetTimeouts(hRequest, timeout_ms, timeout_ms, timeout_ms, timeout_ms);

	std::wstring headers;
	const void* body_ptr = WINHTTP_NO_REQUEST_DATA;
	DWORD body_len = 0;
	if (!request_body.empty()) {
		headers = L"Content-Type: application/json\r\n";
		body_ptr = request_body.data();
		body_len = static_cast<DWORD>(request_body.size());
	}

	BOOL sent = ::WinHttpSendRequest(hRequest,
									 headers.empty() ? WINHTTP_NO_ADDITIONAL_HEADERS : headers.c_str(),
									 headers.empty() ? 0 : static_cast<DWORD>(headers.size()),
									 const_cast<void*>(body_ptr), body_len, body_len, 0);
	if (!sent) {
		res.error = "WinHttpSendRequest failed: " + std::to_string(::GetLastError());
		close_handle(hRequest);
		close_handle(hConnect);
		close_handle(hSession);
		return res;
	}

	if (!::WinHttpReceiveResponse(hRequest, NULL)) {
		res.error = "WinHttpReceiveResponse failed: " + std::to_string(::GetLastError());
		close_handle(hRequest);
		close_handle(hConnect);
		close_handle(hSession);
		return res;
	}

	DWORD status_code = 0;
	DWORD status_size = sizeof(status_code);
	::WinHttpQueryHeaders(hRequest, WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER,
						  WINHTTP_HEADER_NAME_BY_INDEX, &status_code, &status_size,
						  WINHTTP_NO_HEADER_INDEX);
	res.status = static_cast<long>(status_code);

	std::string body;
	DWORD available = 0;
	while (::WinHttpQueryDataAvailable(hRequest, &available) && available > 0) {
		std::vector<char> buf(available);
		DWORD read = 0;
		if (::WinHttpReadData(hRequest, buf.data(), available, &read) && read > 0) {
			body.append(buf.data(), read);
		}
	}
	res.body = std::move(body);
	res.ok = (res.status >= 200 && res.status < 300);

	close_handle(hRequest);
	close_handle(hConnect);
	close_handle(hSession);
	return res;
}

HttpResponse http_get(const std::string& url, uint32_t timeout_ms) {
	return http_request(url, L"GET", {}, timeout_ms);
}

HttpResponse http_post_json(const std::string& url, const std::string& json, uint32_t timeout_ms) {
	return http_request(url, L"POST", json, timeout_ms);
}

std::string default_system_prompt(const std::string& role) {
	if (role == "mapper") {
		return "You are a context mapper. Distill the user's request into a short list of files, constraints, and goals. Be concise.";
	}
	if (role == "brain") {
		return "You are a planning brain. Decompose the user's request into clear, bounded steps. Identify risks and acceptance criteria.";
	}
	if (role == "coder") {
		return "You are a careful coding assistant. Produce short, correct code or patch snippets. Do not add commentary outside the code block unless asked.";
	}
	if (role == "qa") {
		return "You are a QA reviewer. Inspect the prior plan or code for defects, missing tests, or unsafe assumptions. Be concise.";
	}
	if (role == "synthesizer") {
		return "You are a synthesizer. Summarize the conversation and decide whether the acceptance contract is satisfied.";
	}
	return "You are a helpful assistant.";
}

std::string default_prompt(const std::string& role) {
	if (role == "mapper") return "Map the request: what files and constraints matter?";
	if (role == "brain") return "Plan the next concrete implementation step.";
	if (role == "coder") return "Write a small C++ helper function that sums a vector of integers.";
	if (role == "qa") return "Review the coder's output for correctness and edge cases.";
	if (role == "synthesizer") return "Summarize whether the task is complete.";
	return "Introduce yourself in one sentence.";
}

lp::LaneResult parse_chat_response(const std::string& raw) {
	lp::LaneResult res;
	res.raw_response = raw;
	try {
		leafos::minijson::Value v = leafos::minijson::parse(raw);
		if (v.has_key("error")) {
			res.finish_reason = "error";
			res.provider_error = v["error"]["message"].as_string();
			return res;
		}
		const auto& choices = v["choices"].as_array();
		if (!choices.empty()) {
			const auto& msg = choices[0]["message"];
			res.content = msg["content"].as_string();
			res.finish_reason = choices[0]["finish_reason"].as_string();
		}
		if (v.has_key("usage")) {
			res.usage.prompt_tokens = static_cast<int64_t>(v["usage"]["prompt_tokens"].as_int());
			res.usage.completion_tokens = static_cast<int64_t>(v["usage"]["completion_tokens"].as_int());
			res.usage.total_tokens = static_cast<int64_t>(v["usage"]["total_tokens"].as_int());
		}
		res.ok = true;
	} catch (const std::exception& ex) {
		res.finish_reason = "error";
		res.provider_error = std::string("parse failure: ") + ex.what();
	}
	return res;
}

void print_jsonl_line(const std::string& event_type, const std::string& json) {
	std::cout << "{\"event\":\"" << event_type << "\",\"payload\":" << json << "}\n";
}

struct MemberRecord {
	lp::ExpertDescriptor expert;
	bool eligible = false;
	std::string reason;
};

struct MemberRecord;

std::string group_session_plan_to_json(const lp::ModelGroup& group,
									   const std::vector<MemberRecord>& members,
									   const lp::HostCapacity& host,
									   const std::string& finish_reason,
									   const std::string& error,
									   const lp::StackTable& stack_table) {
	std::ostringstream oss;
	oss << "{\n";
	oss << "  \"schema\": \"leafos.route.session.v1\",\n";
	oss << "  \"group_id\": \"" << lp::json_escape_string(group.id) << "\",\n";
	oss << "  \"slot\": \"" << lp::json_escape_string(group.slot) << "\",\n";
	oss << "  \"phase\": \"" << lp::thinking_phase_to_string(stack_table.phase()) << "\",\n";
	oss << "  \"parallel_load\": " << (group.policy.parallel_load ? "true" : "false") << ",\n";
	oss << "  \"host_ram_gib\": " << host.available_ram_gib << ",\n";
	oss << "  \"host_vram_gib\": " << host.available_vram_gib << ",\n";

	size_t eligible_count = 0;
	for (const auto& m : members) if (m.eligible) ++eligible_count;

	oss << "  \"members_requested\": " << members.size() << ",\n";
	oss << "  \"members_eligible\": " << eligible_count << ",\n";
	oss << "  \"models\": [\n";
	double total_mem = 0.0;
	double simultaneous_mem = 0.0;
	for (size_t i = 0; i < members.size(); ++i) {
		const auto& m = members[i];
		total_mem += m.expert.estimated_memory_gib;
		if (m.eligible && m.expert.placement == lp::Placement::Local) {
			simultaneous_mem = std::max(simultaneous_mem, m.expert.estimated_memory_gib);
		}
		oss << "    {\"expert_id\": \"" << lp::json_escape_string(m.expert.id) << "\",";
		oss << " \"model_ref\": \"" << lp::json_escape_string(m.expert.model_ref) << "\",";
		oss << " \"provider_kind\": \"" << lp::provider_kind_to_string(m.expert.provider) << "\",";
		oss << " \"quantization\": \"" << lp::json_escape_string(m.expert.quantization) << "\",";
		oss << " \"estimated_memory_gib\": " << m.expert.estimated_memory_gib << ",";
		oss << " \"stack_segment\": \"" << lp::stack_segment_to_string(m.expert.stack_segment) << "\",";
		oss << " \"placement\": \"" << lp::placement_to_string(m.expert.placement) << "\",";
		oss << " \"eligible\": " << (m.eligible ? "true" : "false") << ",";
		oss << " \"reason\": \"" << lp::json_escape_string(m.reason) << "\"}";
		if (i + 1 < members.size()) oss << ",";
		oss << "\n";
	}
	oss << "  ],\n";
	oss << "  \"total_estimated_memory_gib\": " << total_mem << ",\n";
	oss << "  \"simultaneous_memory_gib\": " << simultaneous_mem << ",\n";
	oss << "  \"stack_table\": " << stack_table.to_json() << ",\n";
	oss << "  \"load_policy\": \"serial_local_with_remote_fallback\",\n";
	oss << "  \"finish_reason\": \"" << lp::json_escape_string(finish_reason) << "\",\n";
	oss << "  \"error\": \"" << lp::json_escape_string(error) << "\"\n";
	oss << "}\n";
	return oss.str();
}

void print_usage(const char* argv0) {
	std::cerr << "Usage:\n"
			  << "  " << argv0 << " plan --role ROLE [--prompt TEXT] [--context N] [--remote] [--hybrid] [--budget USD] [--dry-run] [--health] [--endpoint URL] [--segment SEG] [--phase PHASE]\n"
			  << "  " << argv0 << " plan --group ID [--dry-run] [--health] [--endpoint URL] [--segment SEG] [--phase PHASE]\n"
			  << "\nExamples:\n"
			  << "  " << argv0 << " plan --role coder --prompt \"Write a hello-world in C++\"\n"
			  << "  " << argv0 << " plan --role coder --dry-run\n"
			  << "  " << argv0 << " plan --role coder --health\n"
			  << "  " << argv0 << " plan --group brain.judge-remote --dry-run\n"
			  << "  " << argv0 << " plan --role coder --segment local_gpu --phase code --dry-run\n";
}

lp::StackSegment segment_from_arg(const std::string& s) {
	if (s == "local_cpu") return lp::StackSegment::LocalCpu;
	if (s == "local_gpu") return lp::StackSegment::LocalGpu;
	if (s == "local_any") return lp::StackSegment::LocalAny;
	if (s == "remote") return lp::StackSegment::Remote;
	return lp::StackSegment::LocalAny;
}

lp::ThinkingPhase phase_from_arg(const std::string& s) {
	if (s == "route") return lp::ThinkingPhase::Route;
	if (s == "plan") return lp::ThinkingPhase::Plan;
	if (s == "code") return lp::ThinkingPhase::Code;
	if (s == "review") return lp::ThinkingPhase::Review;
	if (s == "judge") return lp::ThinkingPhase::Judge;
	if (s == "recover") return lp::ThinkingPhase::Recover;
	if (s == "map") return lp::ThinkingPhase::Map;
	if (s == "write") return lp::ThinkingPhase::Write;
	return lp::ThinkingPhase::Idle;
}

std::string make_run_id() {
	using namespace std::chrono;
	auto now = system_clock::now();
	auto us = duration_cast<microseconds>(now.time_since_epoch()).count();
	std::ostringstream oss;
	oss << "rt-" << us;
	return oss.str();
}

} // namespace

int main(int argc, char** argv) {
	if (argc < 3) {
		print_usage(argv[0]);
		return 1;
	}

	std::string command = argv[1];
	if (command != "plan") {
		print_usage(argv[0]);
		return 1;
	}

	std::string role = "coder";
	std::string prompt;
	uint32_t context_tokens = 0;
	bool allow_remote = false;
	bool allow_hybrid = false;
	double online_budget_usd = 0.0;
	bool dry_run = false;
	bool health_mode = false;
	bool debug = false;
	std::string endpoint_base = "http://127.0.0.1:8080";
	std::string group_id;
	std::string segment_arg;
	std::string phase_arg;

	for (int i = 2; i < argc; ++i) {
		std::string arg = argv[i];
		if (arg == "--role" && i + 1 < argc) role = argv[++i];
		else if (arg == "--prompt" && i + 1 < argc) prompt = argv[++i];
		else if (arg == "--context" && i + 1 < argc) context_tokens = static_cast<uint32_t>(std::stoul(argv[++i]));
		else if (arg == "--remote") allow_remote = true;
		else if (arg == "--hybrid") allow_hybrid = true;
		else if (arg == "--budget" && i + 1 < argc) online_budget_usd = std::stod(argv[++i]);
		else if (arg == "--dry-run") dry_run = true;
		else if (arg == "--health") health_mode = true;
		else if (arg == "--debug") debug = true;
		else if (arg == "--endpoint" && i + 1 < argc) endpoint_base = argv[++i];
		else if (arg == "--group" && i + 1 < argc) group_id = argv[++i];
		else if (arg == "--segment" && i + 1 < argc) segment_arg = argv[++i];
		else if (arg == "--phase" && i + 1 < argc) phase_arg = argv[++i];
	}

	if (prompt.empty()) prompt = default_prompt(role);

	std::filesystem::path self = std::filesystem::absolute(argv[0]);
	std::filesystem::path repo_root = self.parent_path().parent_path();
	std::filesystem::current_path(repo_root);

	lp::ExpertRegistry registry(repo_root.string());
	std::string err;
	if (!registry.load_all(&err)) {
		std::cerr << "registry load error: " << err << "\n";
		return 1;
	}

	lp::HostCapacity host = lp::detect_host_capacity();
	lp::MoeRouter router(registry);
	lp::RouterTelemetry telemetry;

	lp::StackTable stack_table(host);
	if (!phase_arg.empty()) stack_table.set_phase(phase_from_arg(phase_arg));

	if (!group_id.empty()) {
		// groups config lives at <taskpack>/config/groups; repo_root is <taskpack>/core/providers.
		std::filesystem::path config_root = repo_root.parent_path().parent_path() / "config";
		lp::GroupRegistry groups(config_root.string());
		if (!groups.load_all(&err)) {
			std::cerr << "group registry load error: " << err << "\n";
			return 1;
		}
		auto gopt = groups.get(group_id);
		if (!gopt) {
			err = "group not found: " + group_id;
			std::cerr << "group load error: " << err << "\n";
			return 1;
		}
		const lp::ModelGroup& group = *gopt;
		if (!group.enabled) {
			err = "group is disabled: " + group_id;
			std::cerr << "group load error: " << err << "\n";
			return 1;
		}

		lp::RequestFeatures req;
		req.role = role;
		req.parameter_floor_b = lp::ExpertRegistry::k_parameter_floor_b;
		req.context_tokens = context_tokens;
		req.allow_remote = group.policy.allow_remote || allow_remote;
		req.allow_hybrid = allow_hybrid;
		req.slot = group.slot;
		req.phase = stack_table.phase();
		if (!segment_arg.empty()) {
			req.preferred_segment = segment_from_arg(segment_arg);
		} else {
			req.preferred_segment = stack_table.preferred_segment_for_phase(req.phase, host);
		}

		std::vector<MemberRecord> members;
		std::string error;
		for (const auto& member : group.members) {
			MemberRecord rec;
			auto eopt = registry.get(member.id);
			if (!eopt) {
				rec.expert = lp::ExpertDescriptor{};
				rec.expert.id = member.id;
				rec.reason = "member not in registry";
				if (error.empty()) error = "member not in registry: " + member.id;
				members.push_back(rec);
				continue;
			}
			rec.expert = *eopt;
			std::vector<std::string> reasons;
			rec.eligible = router.check_eligible(*eopt, req, host, reasons);
			if (!rec.eligible) {
				rec.reason = reasons.empty() ? "unknown" : reasons[0];
			} else {
				rec.reason = "ok";
				if (eopt->placement == lp::Placement::Local) {
					stack_table.assign(eopt->stack_segment, eopt->id, group.slot, eopt->estimated_memory_gib);
				} else {
					stack_table.assign(lp::StackSegment::Remote, eopt->id, group.slot, 0.0);
				}
			}
			members.push_back(rec);
		}

		size_t eligible_count = 0;
		for (const auto& m : members) if (m.eligible) ++eligible_count;
		std::string finish_reason = eligible_count == 0 ? "no_eligible_models" : "session_ready";
		if (eligible_count == group.members.size()) finish_reason = "all_members_ready";
		std::cout << group_session_plan_to_json(group, members, host,
											finish_reason,
											error,
											stack_table);
		return eligible_count == 0 ? 3 : 0;
	}

	lp::RequestFeatures req;
	req.role = role;
	req.parameter_floor_b = lp::ExpertRegistry::k_parameter_floor_b;
	req.context_tokens = context_tokens;
	req.allow_remote = allow_remote;
	req.allow_hybrid = allow_hybrid;
	req.online_budget_usd = online_budget_usd;
	req.phase = stack_table.phase();
	if (!segment_arg.empty()) {
		req.preferred_segment = segment_from_arg(segment_arg);
	} else {
		req.preferred_segment = stack_table.preferred_segment_for_phase(req.phase, host);
	}

	lp::RoutePlan plan = router.plan(req, host, &telemetry);
	stack_table.assign(plan.selected_stack_segment, plan.selected_expert_id, req.slot, plan.estimated_memory_gib);

	std::cout << lp::route_plan_to_json(plan);

	if (health_mode) {
		std::string health_url = endpoint_base + "/health";
		auto hr = http_get(health_url, plan.timeout_ms);
		std::ostringstream oss;
		oss << "{\"url\":\"" << health_url << "\",\"status\":" << hr.status
			<< ",\"ok\":" << (hr.ok ? "true" : "false")
			<< ",\"error\":\"";
		for (char c : hr.error) {
			if (c == '"' || c == '\\') oss << '\\';
			if (c == '\n') oss << "\\n";
			else oss << c;
		}
		oss << "\"}";
		std::cout << oss.str() << "\n";
		return hr.ok ? 0 : 2;
	}

	if (dry_run) {
		lp::LaneResult fake;
		fake.ok = false;
		fake.finish_reason = "dry_run";
		fake.content = "Dry run: routing computed; no provider invoked.";
		std::cout << lp::lane_result_to_json(fake);
		return 0;
	}

	if (plan.terminal_failure != lp::RouteFailure::None) {
		std::cerr << "routing failed: " << lp::route_failure_to_string(plan.terminal_failure) << "\n";
		return 3;
	}

	std::string health_url = endpoint_base + "/health";
	auto hr = http_get(health_url, plan.timeout_ms);
	if (!hr.ok) {
		lp::LaneResult res;
		res.ok = false;
		res.finish_reason = "error";
		res.provider_error = "llama.cpp server not healthy at " + endpoint_base +
							 "; status=" + std::to_string(hr.status) +
							 "; error=" + (hr.error.empty() ? "connection refused or timeout" : hr.error) +
							 " | To launch: llama-server -m <model.gguf> --host 127.0.0.1 --port 8080";
		std::cout << lp::lane_result_to_json(res);
		return 2;
	}

	std::string chat_url = endpoint_base + "/v1/chat/completions";
	lp::ChatCompletionRequest chat_req;
	chat_req.model = plan.selected_model_ref.empty() ? "local-vulkan" : plan.selected_model_ref;
	chat_req.messages.push_back({"system", default_system_prompt(role)});
	chat_req.messages.push_back({"user", prompt});
	chat_req.max_tokens = static_cast<int64_t>(plan.context_ceiling > 0 && plan.context_ceiling < 4096 ? plan.context_ceiling : 512);
	chat_req.temperature = 0.7;
	chat_req.stream = false;

	std::string request_json = lp::chat_request_to_json(chat_req);
	if (debug) {
		std::cerr << "POST " << chat_url << "\n" << request_json << "\n";
	}

	auto t0 = std::chrono::steady_clock::now();
	auto post = http_post_json(chat_url, request_json, plan.timeout_ms);
	auto t1 = std::chrono::steady_clock::now();

	lp::LaneResult result;
	if (!post.ok) {
		result.ok = false;
		result.finish_reason = "error";
		result.provider_error = "chat request failed; status=" + std::to_string(post.status) +
								"; error=" + (post.error.empty() ? "unknown" : post.error);
		result.latency_ms = std::chrono::duration_cast<std::chrono::milliseconds>(t1 - t0).count();
	} else {
		result = parse_chat_response(post.body);
		result.latency_ms = std::chrono::duration_cast<std::chrono::milliseconds>(t1 - t0).count();
	}

	std::cout << lp::lane_result_to_json(result);
	return result.ok ? 0 : 4;
}
