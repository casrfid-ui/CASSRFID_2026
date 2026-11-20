# The ai-data C blocks are used in place (no copy): fwi, gas_chain, state_machine, flame, runtime, camera.
# One ESP-IDF component, because every block lives in a folder called `c`.
set(AI ${CMAKE_CURRENT_LIST_DIR}/../../../../../ai-data/box)
file(GLOB GAS_SRC ${AI}/gas_chain/c/src/gc_*.c)
file(GLOB CAM_SRC ${AI}/camera/c/src/cam_*.c)
idf_component_register(
    SRCS ${AI}/fwi/c/src/fwi.c ${GAS_SRC}
         ${AI}/state_machine/c/src/state_machine.c ${AI}/flame/c/src/flame.c
         ${AI}/runtime/c/src/box_runtime.c ${CAM_SRC}
    INCLUDE_DIRS ${AI}/fwi/c/include ${AI}/gas_chain/c/include ${AI}/state_machine/c/include ${AI}/flame/c/include
                 ${AI}/runtime/c/include ${AI}/camera/c/include
    PRIV_INCLUDE_DIRS ${AI}/gas_chain/c/src)
