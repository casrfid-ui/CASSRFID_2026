/* Minimal NMEA 0183 parser: GGA (position, fix, satellites, altitude) and RMC (UTC date and time, validity). */
#ifndef NMEA_H
#define NMEA_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    bool have_pos;              /* a GGA with fix quality > 0 was seen */
    int32_t lat_e7, lon_e7;
    int16_t alt_m;
    uint8_t sats;
    bool have_time;             /* an RMC with status A was seen */
    int64_t unix_s;
} nmea_fix_t;

/* Feed one line (with or without CR/LF, "$..." with optional "*hh"). Returns 1 if it updated `fix`, 0 if it was another
 * sentence, -1 if malformed or the checksum is wrong. */
int nmea_feed(nmea_fix_t *fix, const char *line);

int64_t nmea_days_from_civil(int y, unsigned m, unsigned d);

#ifdef __cplusplus
}
#endif
#endif
