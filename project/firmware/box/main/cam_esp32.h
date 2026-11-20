/* cam_hw_t for the OV2640 on the ESP32-CAM: power gate, grayscale 160x120 for the quality check, JPEG for the upload,
 * Wi-Fi station to the gateway, HTTP POST of the frame (protocol v1, see ai-data/box/camera and gateway vision). */
#ifndef CAM_ESP32_H
#define CAM_ESP32_H
#include "box_camera.h"
const cam_hw_t *cam_esp32_hw(void);
#endif
