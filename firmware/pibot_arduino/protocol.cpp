#include "protocol.h"

#include <stdio.h>
#include <string.h>
#include <stdlib.h>

uint8_t pibot_crc8(const char *data, size_t len) {
  uint8_t crc = 0;
  for (size_t i = 0; i < len; i++) {
    crc ^= (uint8_t)data[i];
    for (uint8_t b = 0; b < 8; b++) {
      crc = (crc & 0x80) ? (uint8_t)((crc << 1) ^ 0x07) : (uint8_t)(crc << 1);
    }
  }
  return crc;
}

bool pibot_parse_command(const char *line, PibotCommand &out, const char *&reason) {
  if (line == nullptr || line[0] != '>') {
    reason = "marker";
    return false;
  }

  // Locate the CRC delimiter '*'.
  const char *star = strrchr(line, '*');
  if (star == nullptr) {
    reason = "frame";
    return false;
  }

  // Verify CRC-8 over the payload (between '>' and '*').
  size_t payload_len = (size_t)(star - (line + 1));
  uint8_t expected = (uint8_t)strtol(star + 1, nullptr, 16);
  if (pibot_crc8(line + 1, payload_len) != expected) {
    reason = "crc";
    return false;
  }

  // Copy payload to a scratch buffer we can tokenize.
  char buf[96];
  if (payload_len >= sizeof(buf)) {
    reason = "len";
    return false;
  }
  memcpy(buf, line + 1, payload_len);
  buf[payload_len] = '\0';

  // Tokenize on commas: SEQ, NAME, arg0, arg1, ...
  out.argc = 0;
  char *save = nullptr;
  char *tok = strtok_r(buf, ",", &save);
  if (tok == nullptr) {
    reason = "fields";
    return false;
  }
  out.seq = atoi(tok);

  tok = strtok_r(nullptr, ",", &save);
  if (tok == nullptr) {
    reason = "fields";
    return false;
  }
  strncpy(out.name, tok, PIBOT_NAME_LEN - 1);
  out.name[PIBOT_NAME_LEN - 1] = '\0';

  while ((tok = strtok_r(nullptr, ",", &save)) != nullptr && out.argc < PIBOT_MAX_ARGS) {
    out.args[out.argc++] = atof(tok);
  }
  reason = "";
  return true;
}

void pibot_build_ack(int seq, char *out, size_t cap) {
  snprintf(out, cap, "ACK %d", seq);
}

void pibot_build_nak(int seq, const char *reason, char *out, size_t cap) {
  snprintf(out, cap, "NAK %d %s", seq, reason);
}

void pibot_build_telemetry(int seq, const char *type, const float *fields, uint8_t n,
                           char *out, size_t cap) {
  // payload = "SEQ,TYPE,f0,f1,..."
  char payload[80];
  int len = snprintf(payload, sizeof(payload), "%d,%s", seq, type);
  for (uint8_t i = 0; i < n && len < (int)sizeof(payload); i++) {
    len += snprintf(payload + len, sizeof(payload) - len, ",%g", (double)fields[i]);
  }
  uint8_t crc = pibot_crc8(payload, strlen(payload));
  snprintf(out, cap, "<%s*%02X", payload, crc);
}
