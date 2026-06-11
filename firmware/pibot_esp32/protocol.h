// PiBot wire protocol — AVR/Arduino side. Mirrors pibot/protocol/codec.py.
//
// ASCII framing:
//   command   : >SEQ,NAME,ARG...*CC\n   (CC = CRC-8 hex over the payload between
//                                        the leading marker and '*')
//   ack       : ACK SEQ\n
//   nak       : NAK SEQ REASON\n
//   telemetry : <SEQ,TYPE,FIELD...*CC\n
//
// CRC-8: polynomial 0x07, init 0x00 — identical to the host codec, so a frame built
// here verifies on the Pi and vice-versa.
#ifndef PIBOT_PROTOCOL_H
#define PIBOT_PROTOCOL_H

#include <Arduino.h>

#define PIBOT_MAX_ARGS 4
#define PIBOT_NAME_LEN 12

struct PibotCommand {
  int seq;
  char name[PIBOT_NAME_LEN];
  float args[PIBOT_MAX_ARGS];
  uint8_t argc;
};

// CRC-8 (poly 0x07, init 0x00) over `len` bytes of `data`.
uint8_t pibot_crc8(const char *data, size_t len);

// Parse one command frame (without trailing newline). Verifies the marker is '>' and
// the CRC matches. Returns true on success; on failure sets `reason` to a short code
// ("crc", "frame", "marker", ...) for a NAK.
bool pibot_parse_command(const char *line, PibotCommand &out, const char *&reason);

// Build response frames into `out` (NUL-terminated, no newline appended — caller adds).
void pibot_build_ack(int seq, char *out, size_t cap);
void pibot_build_nak(int seq, const char *reason, char *out, size_t cap);
void pibot_build_telemetry(int seq, const char *type, const float *fields, uint8_t n,
                           char *out, size_t cap);

#endif  // PIBOT_PROTOCOL_H
