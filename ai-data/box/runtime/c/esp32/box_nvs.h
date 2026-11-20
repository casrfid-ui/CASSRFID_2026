/* NVS (flash) key-value store for the runtime. NOT compiled in this repository: needs ESP-IDF. */
#ifndef BOX_NVS_H
#define BOX_NVS_H
#include "box_runtime.h"
#ifdef __cplusplus
extern "C" {
#endif
/* nvs_flash_init() must have been called by the application before the first use. */
extern const box_kv_t box_nvs_kv;
#ifdef __cplusplus
}
#endif
#endif
