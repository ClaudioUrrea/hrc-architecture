// SPDX-License-Identifier: MIT
#include "hrc/common.hpp"
#include "hrc/interfaces.hpp"

#include <cerrno>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <ctime>
#include <fstream>
#include <sstream>
#include <stdexcept>
#include <time.h>

namespace hrc {

const char* to_string(Result r) {
  switch (r) {
    case Result::Ok: return "ok";
    case Result::Timeout: return "timeout";
    case Result::Rejected: return "rejected";
    case Result::NotConnected: return "not_connected";
    case Result::CommError: return "comm_error";
    case Result::InvalidArgument: return "invalid_argument";
    case Result::Unsupported: return "unsupported";
  }
  return "?";
}

const char* to_string(FaultCategory c) {
  switch (c) {
    case FaultCategory::None: return "none";
    case FaultCategory::SensorTimeout: return "sensor_timeout";
    case FaultCategory::NetworkPartition: return "network_partition";
    case FaultCategory::ComputationalOverrun: return "computational_overrun";
    case FaultCategory::TrackingLoss: return "tracking_loss";
    case FaultCategory::HardwareCommunication: return "hardware_communication";
    case FaultCategory::MemoryAllocation: return "memory_allocation";
    case FaultCategory::ConfigurationInconsistency: return "configuration_inconsistency";
    case FaultCategory::ConstraintViolation: return "constraint_violation";
  }
  return "?";
}

// ------------------------------------------------------------------ time
int64_t mono_ns() {
  timespec ts{};
  clock_gettime(CLOCK_MONOTONIC, &ts);
  return static_cast<int64_t>(ts.tv_sec) * 1000000000LL + ts.tv_nsec;
}
int64_t wall_ns() {
  timespec ts{};
  clock_gettime(CLOCK_REALTIME, &ts);
  return static_cast<int64_t>(ts.tv_sec) * 1000000000LL + ts.tv_nsec;
}
std::string utc_iso8601(int64_t w) {
  time_t s = static_cast<time_t>(w / 1000000000LL);
  int ms = static_cast<int>((w / 1000000LL) % 1000);
  tm t{};
  gmtime_r(&s, &t);
  char buf[64];
  std::snprintf(buf, sizeof buf, "%04d-%02d-%02dT%02d:%02d:%02d.%03dZ", t.tm_year + 1900, t.tm_mon + 1,
                t.tm_mday, t.tm_hour, t.tm_min, t.tm_sec, ms);
  return buf;
}
void sleep_until_mono(int64_t t_ns) {
  timespec ts{};
  ts.tv_sec = static_cast<time_t>(t_ns / 1000000000LL);
  ts.tv_nsec = static_cast<long>(t_ns % 1000000000LL);
  while (clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &ts, nullptr) == EINTR) {
  }
}

// ------------------------------------------------------------------ SHA-256 (FIPS 180-4)
namespace {
struct Sha256 {
  uint32_t h[8] = {0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};
  uint8_t buf[64];
  size_t blen = 0;
  uint64_t total = 0;
  static uint32_t rotr(uint32_t x, int n) { return (x >> n) | (x << (32 - n)); }
  void block(const uint8_t* p) {
    static const uint32_t k[64] = {
        0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
        0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
        0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
        0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
        0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
        0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
        0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
        0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2};
    uint32_t w[64];
    for (int i = 0; i < 16; ++i)
      w[i] = (uint32_t(p[4 * i]) << 24) | (uint32_t(p[4 * i + 1]) << 16) | (uint32_t(p[4 * i + 2]) << 8) | p[4 * i + 3];
    for (int i = 16; i < 64; ++i) {
      uint32_t s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >> 3);
      uint32_t s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >> 10);
      w[i] = w[i - 16] + s0 + w[i - 7] + s1;
    }
    uint32_t a = h[0], b = h[1], c = h[2], d = h[3], e = h[4], f = h[5], g = h[6], hh = h[7];
    for (int i = 0; i < 64; ++i) {
      uint32_t S1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
      uint32_t ch = (e & f) ^ (~e & g);
      uint32_t t1 = hh + S1 + ch + k[i] + w[i];
      uint32_t S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
      uint32_t mj = (a & b) ^ (a & c) ^ (b & c);
      uint32_t t2 = S0 + mj;
      hh = g; g = f; f = e; e = d + t1; d = c; c = b; b = a; a = t1 + t2;
    }
    h[0] += a; h[1] += b; h[2] += c; h[3] += d; h[4] += e; h[5] += f; h[6] += g; h[7] += hh;
  }
  void update(const uint8_t* p, size_t n) {
    total += n;
    while (n) {
      size_t take = std::min(n, size_t(64) - blen);
      std::memcpy(buf + blen, p, take);
      blen += take; p += take; n -= take;
      if (blen == 64) { block(buf); blen = 0; }
    }
  }
  std::string hex() {
    uint64_t bits = total * 8;
    uint8_t pad = 0x80;
    update(&pad, 1);
    uint8_t z = 0;
    while (blen != 56) update(&z, 1);
    uint8_t len[8];
    for (int i = 0; i < 8; ++i) len[i] = uint8_t(bits >> (56 - 8 * i));
    update(len, 8);
    char out[65];
    for (int i = 0; i < 8; ++i) std::snprintf(out + 8 * i, 9, "%08x", h[i]);
    return std::string(out, 64);
  }
};
}  // namespace

std::string sha256_hex(const void* data, size_t n) {
  Sha256 s;
  s.update(static_cast<const uint8_t*>(data), n);
  return s.hex();
}
std::string sha256_file(const std::string& path) {
  std::FILE* f = std::fopen(path.c_str(), "rb");
  if (!f) throw std::runtime_error("sha256_file: cannot open " + path);
  Sha256 s;
  std::vector<uint8_t> b(1 << 20);
  size_t r;
  while ((r = std::fread(b.data(), 1, b.size(), f)) > 0) s.update(b.data(), r);
  bool err = std::ferror(f);
  std::fclose(f);
  if (err) throw std::runtime_error("sha256_file: read error " + path);
  return s.hex();
}

// ------------------------------------------------------------------ JSON parser
class JsonParser {
 public:
  explicit JsonParser(const std::string& s) : s_(s) {}
  Json run() {
    Json j = value();
    ws();
    if (i_ != s_.size()) fail("trailing characters");
    return j;
  }

 private:
  const std::string& s_;
  size_t i_ = 0;
  [[noreturn]] void fail(const char* m) {
    throw std::runtime_error(std::string("json: ") + m + " at offset " + std::to_string(i_));
  }
  void ws() {
    while (i_ < s_.size()) {
      char c = s_[i_];
      if (c == ' ' || c == '\n' || c == '\r' || c == '\t') { ++i_; continue; }
      if (c == '/' && i_ + 1 < s_.size() && s_[i_ + 1] == '/') {  // allow // comments in config files
        while (i_ < s_.size() && s_[i_] != '\n') ++i_;
        continue;
      }
      break;
    }
  }
  Json value() {
    ws();
    if (i_ >= s_.size()) fail("unexpected end");
    char c = s_[i_];
    Json j;
    if (c == '{') {
      j.type_ = Json::Type::Object;
      ++i_; ws();
      if (s_[i_] == '}') { ++i_; return j; }
      for (;;) {
        ws();
        if (s_[i_] != '"') fail("expected key");
        std::string k = string();
        ws();
        if (s_[i_] != ':') fail("expected ':'");
        ++i_;
        Json v = value();
        if (!j.obj_.count(k)) j.keys_.push_back(k);
        j.obj_[k] = std::move(v);
        ws();
        if (s_[i_] == ',') { ++i_; continue; }
        if (s_[i_] == '}') { ++i_; break; }
        fail("expected ',' or '}'");
      }
    } else if (c == '[') {
      j.type_ = Json::Type::Array;
      ++i_; ws();
      if (s_[i_] == ']') { ++i_; return j; }
      for (;;) {
        j.arr_.push_back(value());
        ws();
        if (s_[i_] == ',') { ++i_; continue; }
        if (s_[i_] == ']') { ++i_; break; }
        fail("expected ',' or ']'");
      }
    } else if (c == '"') {
      j.type_ = Json::Type::String;
      j.s_ = string();
    } else if (s_.compare(i_, 4, "true") == 0) {
      j.type_ = Json::Type::Bool; j.b_ = true; i_ += 4;
    } else if (s_.compare(i_, 5, "false") == 0) {
      j.type_ = Json::Type::Bool; j.b_ = false; i_ += 5;
    } else if (s_.compare(i_, 4, "null") == 0) {
      i_ += 4;
    } else {
      size_t st = i_;
      while (i_ < s_.size() && std::strchr("+-0123456789.eE", s_[i_])) ++i_;
      if (st == i_) fail("unexpected character");
      j.type_ = Json::Type::Number;
      j.n_ = std::stod(s_.substr(st, i_ - st));
    }
    return j;
  }
  std::string string() {
    ++i_;  // opening quote
    std::string out;
    while (i_ < s_.size() && s_[i_] != '"') {
      char c = s_[i_++];
      if (c == '\\') {
        char e = s_[i_++];
        switch (e) {
          case 'n': out += '\n'; break;
          case 't': out += '\t'; break;
          case 'r': out += '\r'; break;
          case 'b': out += '\b'; break;
          case 'f': out += '\f'; break;
          case 'u': {
            unsigned cp = std::stoul(s_.substr(i_, 4), nullptr, 16);
            i_ += 4;
            if (cp < 0x80) out += char(cp);
            else if (cp < 0x800) { out += char(0xC0 | (cp >> 6)); out += char(0x80 | (cp & 0x3F)); }
            else { out += char(0xE0 | (cp >> 12)); out += char(0x80 | ((cp >> 6) & 0x3F)); out += char(0x80 | (cp & 0x3F)); }
            break;
          }
          default: out += e;
        }
      } else {
        out += c;
      }
    }
    if (i_ >= s_.size()) fail("unterminated string");
    ++i_;
    return out;
  }
};

Json Json::parse(const std::string& text) { return JsonParser(text).run(); }
Json Json::parse_file(const std::string& path) { return parse(read_text_file(path)); }

static const Json kNull;
bool Json::has(const std::string& k) const { return type_ == Type::Object && obj_.count(k); }
const Json& Json::operator[](const std::string& k) const {
  if (type_ != Type::Object) return kNull;
  auto it = obj_.find(k);
  return it == obj_.end() ? kNull : it->second;
}
const Json& Json::operator[](size_t i) const { return (type_ == Type::Array && i < arr_.size()) ? arr_[i] : kNull; }
size_t Json::size() const { return type_ == Type::Array ? arr_.size() : type_ == Type::Object ? obj_.size() : 0; }
double Json::num(double def) const { return type_ == Type::Number ? n_ : (type_ == Type::Bool ? (b_ ? 1 : 0) : def); }
int64_t Json::i64(int64_t def) const { return type_ == Type::Number ? static_cast<int64_t>(std::llround(n_)) : def; }
bool Json::boolean(bool def) const { return type_ == Type::Bool ? b_ : (type_ == Type::Number ? n_ != 0 : def); }
const Json* Json::path(const std::string& p) const {
  const Json* cur = this;
  size_t st = 0;
  while (st <= p.size()) {
    size_t dot = p.find('.', st);
    std::string k = p.substr(st, dot == std::string::npos ? std::string::npos : dot - st);
    if (!cur->has(k)) return nullptr;
    cur = &(*cur)[k];
    if (dot == std::string::npos) break;
    st = dot + 1;
  }
  return cur;
}
double Json::get(const std::string& p, double def) const { auto* j = path(p); return j ? j->num(def) : def; }
std::string Json::get(const std::string& p, const std::string& def) const { auto* j = path(p); return j ? j->str_or(def) : def; }
bool Json::get_bool(const std::string& p, bool def) const { auto* j = path(p); return j ? j->boolean(def) : def; }

std::string Json::dump() const {
  switch (type_) {
    case Type::Null: return "null";
    case Type::Bool: return b_ ? "true" : "false";
    case Type::Number: {
      char b[64];
      std::snprintf(b, sizeof b, "%.17g", n_);
      return b;
    }
    case Type::String: return "\"" + JsonWriter::escape(s_) + "\"";
    case Type::Array: {
      std::string o = "[";
      for (size_t i = 0; i < arr_.size(); ++i) o += (i ? "," : "") + arr_[i].dump();
      return o + "]";
    }
    case Type::Object: {
      std::string o = "{";
      bool first = true;
      for (auto& k : keys_) {
        o += (first ? "" : ",") + std::string("\"") + JsonWriter::escape(k) + "\":" + obj_.at(k).dump();
        first = false;
      }
      return o + "}";
    }
  }
  return "null";
}

// ------------------------------------------------------------------ JSON writer
std::string JsonWriter::escape(const std::string& s) {
  std::string o;
  for (unsigned char c : s) {
    switch (c) {
      case '"': o += "\\\""; break;
      case '\\': o += "\\\\"; break;
      case '\n': o += "\\n"; break;
      case '\r': o += "\\r"; break;
      case '\t': o += "\\t"; break;
      default:
        if (c < 0x20) { char b[8]; std::snprintf(b, sizeof b, "\\u%04x", c); o += b; }
        else o += char(c);
    }
  }
  return o;
}
void JsonWriter::sep() {
  if (!first_.empty()) {
    if (!first_.back()) out_ += ",";
    first_.back() = false;
  }
}
void JsonWriter::key(const std::string& k) { sep(); out_ += "\"" + escape(k) + "\":"; }
JsonWriter& JsonWriter::begin_object() { sep(); out_ += "{"; first_.push_back(true); return *this; }
JsonWriter& JsonWriter::end_object() { out_ += "}"; first_.pop_back(); return *this; }
JsonWriter& JsonWriter::begin_array(const std::string& k) {
  if (k.empty()) sep(); else key(k);
  out_ += "["; first_.push_back(true); return *this;
}
JsonWriter& JsonWriter::end_array() { out_ += "]"; first_.pop_back(); return *this; }
JsonWriter& JsonWriter::kv(const std::string& k, const std::string& v) { key(k); out_ += "\"" + escape(v) + "\""; return *this; }
JsonWriter& JsonWriter::kv(const std::string& k, double v) {
  key(k);
  char b[64];
  if (std::isfinite(v)) std::snprintf(b, sizeof b, "%.10g", v); else std::snprintf(b, sizeof b, "null");
  out_ += b; return *this;
}
JsonWriter& JsonWriter::kv(const std::string& k, int64_t v) { key(k); out_ += std::to_string(v); return *this; }
JsonWriter& JsonWriter::kv(const std::string& k, bool v) { key(k); out_ += v ? "true" : "false"; return *this; }
JsonWriter& JsonWriter::key_raw(const std::string& k, const std::string& raw) { key(k); out_ += raw; return *this; }
JsonWriter& JsonWriter::value(const std::string& v) { sep(); out_ += "\"" + escape(v) + "\""; return *this; }
JsonWriter& JsonWriter::value(double v) { sep(); char b[64]; std::snprintf(b, sizeof b, "%.10g", v); out_ += b; return *this; }

// ------------------------------------------------------------------ files
std::string read_text_file(const std::string& path) {
  std::ifstream f(path, std::ios::binary);
  if (!f) throw std::runtime_error("cannot read " + path);
  std::stringstream ss;
  ss << f.rdbuf();
  return ss.str();
}
void write_text_file(const std::string& path, const std::string& text) {
  std::ofstream f(path, std::ios::binary | std::ios::trunc);
  if (!f) throw std::runtime_error("cannot write " + path);
  f << text;
  if (!f) throw std::runtime_error("write failed " + path);
}
std::string shell_capture(const std::string& cmd) {
  std::FILE* p = popen((cmd + " 2>/dev/null").c_str(), "r");
  if (!p) return "";
  std::string o;
  char b[512];
  while (std::fgets(b, sizeof b, p)) o += b;
  pclose(p);
  while (!o.empty() && (o.back() == '\n' || o.back() == '\r' || o.back() == ' ')) o.pop_back();
  return o;
}

}  // namespace hrc
