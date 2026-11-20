# ESP-IDF component (firmware build). Host build and tests: `make test` (see Makefile).
# Component naming: see ../../runtime/c/CMakeLists.txt.
idf_component_register(
    SRCS "src/cam_config.c" "src/cam_quality.c" "src/cam_protocol.c" "src/cam_session.c"
    INCLUDE_DIRS "include")
