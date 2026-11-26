// SPDX-License-Identifier: MIT
// Time, hashing and a small JSON reader/writer. Self-contained so that the logging and
// provenance chain has no third-party dependency that could change silently.
#pragma once
#include <cstdint>
#include <map>
#include <memory>
#include <string>
#include <vector>

namespace hrc {

int64_t mono_ns();      // CLOCK_MONOTONIC
int64_t wall_ns();      // CLOCK_REALTIME
std::string utc_iso8601(int64_t wall_ns_value);
void sleep_until_mono(int64_t t_ns);

// ------------------------------------------------------------ SHA-256
std::string sha256_hex(const void* data, size_t n);
std::string sha256_file(const std::string& path);  // throws on I/O error

// ------------------------------------------------------------ JSON
class Json {
 public:
  enum class Type { Null, Bool, Number, String, Array, Object };
  Json() = default;
  static Json parse(const std::string& text);  // throws std::runtime_error with position
  static Json parse_file(const std::string& path);

  Type type() const { return type_; }
  bool is_null() const { return type_ == Type::Null; }
  bool has(const std::string& k) const;
  const Json& operator[](const std::string& k) const;  // Null if missing
  const Json& operator[](size_t i) const;
  size_t size() const;
  const std::vector<std::string>& keys() const { return keys_; }

  double num(double def = 0) const;
  int64_t i64(int64_t def = 0) const;
  bool boolean(bool def = false) const;
  const std::string& str() const { return s_; }
  std::string str_or(const std::string& def) const { return type_ == Type::String ? s_ : def; }

  // convenience: path lookup "a.b.c" with default
  double get(const std::string& path, double def) const;
  std::string get(const std::string& path, const std::string& def) const;
  bool get_bool(const std::string& path, bool def) const;
  std::string dump() const;

 private:
  Type type_ = Type::Null;
  bool b_ = false;
  double n_ = 0;
  std::string s_;
  std::vector<Json> arr_;
  std::vector<std::string> keys_;
  std::map<std::string, Json> obj_;
  const Json* path(const std::string& p) const;
  friend class JsonParser;
};

// Streaming JSON writer for manifests (keeps key order as written).
class JsonWriter {
 public:
  JsonWriter& begin_object();
  JsonWriter& end_object();
  JsonWriter& begin_array(const std::string& key = "");
  JsonWriter& end_array();
  JsonWriter& kv(const std::string& k, const std::string& v);
  JsonWriter& kv(const std::string& k, const char* v) { return kv(k, std::string(v)); }
  JsonWriter& kv(const std::string& k, double v);
  JsonWriter& kv(const std::string& k, int64_t v);
  JsonWriter& kv(const std::string& k, int v) { return kv(k, static_cast<int64_t>(v)); }
  JsonWriter& kv(const std::string& k, bool v);
  JsonWriter& key_raw(const std::string& k, const std::string& raw_json);
  JsonWriter& value(const std::string& v);
  JsonWriter& value(double v);
  const std::string& str() const { return out_; }
  static std::string escape(const std::string& s);

 private:
  std::string out_;
  std::vector<bool> first_{};
  void sep();
  void key(const std::string& k);
};

std::string read_text_file(const std::string& path);
void write_text_file(const std::string& path, const std::string& text);
std::string shell_capture(const std::string& cmd);  // trimmed stdout, "" on failure (non-RT use only)

}  // namespace hrc
