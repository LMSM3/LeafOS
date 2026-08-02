#pragma once
// Minimal dependency-free JSON parser for LeafOS provider configs.

#include <map>
#include <string>
#include <vector>
#include <stdexcept>
#include <cctype>
#include <fstream>

namespace leafos::minijson {

struct Value {
	enum Type { Null, Bool, Number, String, Array, Object } type = Null;
	bool b = false;
	double n = 0.0;
	std::string s;
	std::vector<Value> a;
	std::map<std::string, Value> o;

	bool is_null() const { return type == Null; }
	bool is_bool() const { return type == Bool; }
	bool is_number() const { return type == Number; }
	bool is_string() const { return type == String; }
	bool is_array() const { return type == Array; }
	bool is_object() const { return type == Object; }

	bool as_bool() const { return b; }
	double as_number() const { return n; }
	long long as_int() const { return static_cast<long long>(n); }
	const std::string& as_string() const { return s; }
	const std::vector<Value>& as_array() const { return a; }
	const std::map<std::string, Value>& as_object() const { return o; }

	bool has_key(const std::string& k) const {
		return is_object() && o.find(k) != o.end();
	}
	const Value& operator[](const std::string& k) const {
		static const Value empty;
		auto it = o.find(k);
		if (it == o.end()) return empty;
		return it->second;
	}
};

using Array = std::vector<Value>;
using Object = std::map<std::string, Value>;

inline std::string parse_string(const std::string& text, size_t& i);
inline Value parse_value(const std::string& text, size_t& i);



inline void skip_ws(const std::string& text, size_t& i) {
	while (i < text.size() && std::isspace(static_cast<unsigned char>(text[i]))) ++i;
}

inline std::string parse_string(const std::string& text, size_t& i) {
	if (text[i] != '"') throw std::runtime_error("expected string");
	++i;
	std::string out;
	while (i < text.size() && text[i] != '"') {
		if (text[i] == '\\' && i + 1 < text.size()) {
			char nxt = text[i + 1];
			switch (nxt) {
				case '"': out += '"'; break;
				case '\\': out += '\\'; break;
				case '/': out += '/'; break;
				case 'b': out += '\b'; break;
				case 'f': out += '\f'; break;
				case 'n': out += '\n'; break;
				case 'r': out += '\r'; break;
				case 't': out += '\t'; break;
				default: out += nxt; break;
			}
			i += 2;
		} else {
			out += text[i++];
		}
	}
	if (i >= text.size()) throw std::runtime_error("unterminated string");
	++i; // closing quote
	return out;
}

inline Value parse_number(const std::string& text, size_t& i) {
	size_t start = i;
	if (text[i] == '-') ++i;
	while (i < text.size() && std::isdigit(static_cast<unsigned char>(text[i]))) ++i;
	if (i < text.size() && text[i] == '.') {
		++i;
		while (i < text.size() && std::isdigit(static_cast<unsigned char>(text[i]))) ++i;
	}
	if (i < text.size() && (text[i] == 'e' || text[i] == 'E')) {
		++i;
		if (i < text.size() && (text[i] == '+' || text[i] == '-')) ++i;
		while (i < text.size() && std::isdigit(static_cast<unsigned char>(text[i]))) ++i;
	}
	Value v; v.type = Value::Number; v.n = std::stod(text.substr(start, i - start));
	return v;
}

inline Value parse_keyword(const std::string& text, size_t& i) {
	if (text.compare(i, 4, "true") == 0) { i += 4; Value v; v.type = Value::Bool; v.b = true; return v; }
	if (text.compare(i, 5, "false") == 0) { i += 5; Value v; v.type = Value::Bool; v.b = false; return v; }
	if (text.compare(i, 4, "null") == 0) { i += 4; Value v; return v; }
	std::string snippet = text.substr(i, std::min<size_t>(20, text.size() - i));
	throw std::runtime_error(std::string("unknown keyword near: '") + snippet + "'");
}

inline Value parse_array(const std::string& text, size_t& i) {
	++i; // [
	Value v; v.type = Value::Array;
	skip_ws(text, i);
	while (i < text.size() && text[i] != ']') {
		v.a.push_back(parse_value(text, i));
		skip_ws(text, i);
		if (i < text.size() && text[i] == ',') { ++i; skip_ws(text, i); }
	}
	if (i >= text.size() || text[i] != ']') throw std::runtime_error("unterminated array");
	++i;
	return v;
}

inline Value parse_object(const std::string& text, size_t& i) {
	++i; // {
	Value v; v.type = Value::Object;
	skip_ws(text, i);
	while (i < text.size() && text[i] != '}') {
		skip_ws(text, i);
		std::string key = parse_string(text, i);
		skip_ws(text, i);
		if (i >= text.size() || text[i] != ':') throw std::runtime_error("expected :");
		++i;
		skip_ws(text, i);
		v.o[key] = parse_value(text, i);
		skip_ws(text, i);
		if (i < text.size() && text[i] == ',') { ++i; skip_ws(text, i); }
	}
	if (i >= text.size() || text[i] != '}') throw std::runtime_error("unterminated object");
	++i;
	return v;
}

inline Value parse_value(const std::string& text, size_t& i) {
	skip_ws(text, i);
	if (i >= text.size()) throw std::runtime_error("unexpected end of JSON");
	char c = text[i];
	if (c == '{') return parse_object(text, i);
	if (c == '[') return parse_array(text, i);
	if (c == '"') { Value v; v.type = Value::String; v.s = parse_string(text, i); return v; }
	if (c == '-' || std::isdigit(static_cast<unsigned char>(c))) return parse_number(text, i);
	return parse_keyword(text, i);
}

inline Value parse(const std::string& text) {
	size_t i = 0;
	Value v = parse_value(text, i);
	skip_ws(text, i);
	if (i != text.size()) throw std::runtime_error("trailing JSON data");
	return v;
}

inline std::string read_file(const std::string& path) {
	std::ifstream f(path, std::ios::binary);
	if (!f) throw std::runtime_error("cannot open " + path);
	std::string raw((std::istreambuf_iterator<char>(f)), std::istreambuf_iterator<char>());
	if (raw.size() >= 3 &&
		static_cast<unsigned char>(raw[0]) == 0xEF &&
		static_cast<unsigned char>(raw[1]) == 0xBB &&
		static_cast<unsigned char>(raw[2]) == 0xBF) {
		raw.erase(0, 3);
	}
	return raw;
}

} // namespace leafos::minijson
