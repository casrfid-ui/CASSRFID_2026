/* PCF8574 expander, MAX17048 fuel gauge, LM75 temperature sensor. */
#ifndef I2C_MISC_H
#define I2C_MISC_H
#include <stdbool.h>
#include <stdint.h>
#include "esp_err.h"

esp_err_t pcf_init(void);                    /* inputs released (high), outputs idle */
void pcf_set(int bit, bool level);           /* output bit; the shadow register is kept */
bool pcf_get(int bit, bool *ok);             /* input bit */

bool fuel_read(int *percent, double *volts); /* MAX17048 */
bool lm75_read(double *celsius);
#endif
