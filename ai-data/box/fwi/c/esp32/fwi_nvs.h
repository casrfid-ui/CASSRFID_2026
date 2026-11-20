/* NVS (flash) storage for the FWI state: the 24 h rain history and the three codes survive a reboot. */
#ifndef FWI_NVS_H
#define FWI_NVS_H
#include "fwi.h"
#ifdef __cplusplus
extern "C" {
#endif
/* nvs_flash_init() must have been called by the application before the first use. */
extern const fwi_storage_t fwi_nvs_storage;
#ifdef __cplusplus
}
#endif
#endif
