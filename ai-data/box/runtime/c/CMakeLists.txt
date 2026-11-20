# ESP-IDF component (firmware build). Host build and tests: `make test` (see Makefile).
# ESP-IDF names a component after its folder, and the three blocks all live in a folder called `c`:
# in the firmware project, expose them as components named fwi, gas_chain, state_machine, flame, box_camera and box_runtime
# (symlinks under firmware/components/, or EXTRA_COMPONENT_DIRS with copies). Not tested: no toolchain here.
idf_component_register(
    SRCS "src/box_runtime.c" "esp32/box_nvs.c"
    INCLUDE_DIRS "include" "esp32"
    REQUIRES fwi gas_chain state_machine flame box_camera nvs_flash)
