# box camera (C)

Image quality check, request headers, strict response parser and the capture-and-send session. C99, no heap.
Hardware is reached through `cam_hw_t` (camera power, grayscale and JPEG capture, Wi-Fi, HTTP POST, clock): implemented by the firmware, mocked in `test/test_camera.c`.

```
make test   # 119 checks
make cli    # parity tool used by ../python/tests/test_c_parity.py
```
Protocol and limits: `../FICHE.md`. Gateway side: `../../../gateway/vision`.
