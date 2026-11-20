# Host build and tests of the box application. Links the ai-data C blocks from their own folders (single source of truth).
CC      ?= gcc
BUILD   ?= build
AI      = ../../../../ai-data/box
PROTO   = ../../../protocol/c
CORE    = ../core
CFLAGS  ?= -std=c99 -O2 -Wall -Wextra -Wpedantic -D_POSIX_C_SOURCE=200809L \
           -I$(CORE)/include -I$(PROTO)/include -Itest \
           -I$(AI)/fwi/c/include -I$(AI)/gas_chain/c/include -I$(AI)/gas_chain/c/src -I$(AI)/state_machine/c/include \
           -I$(AI)/flame/c/include -I$(AI)/runtime/c/include -I$(AI)/camera/c/include
LIBSRC  = $(wildcard $(CORE)/src/*.c) $(PROTO)/src/ffp.c $(AI)/fwi/c/src/fwi.c $(wildcard $(AI)/gas_chain/c/src/*.c) \
          $(AI)/state_machine/c/src/state_machine.c $(AI)/flame/c/src/flame.c $(AI)/runtime/c/src/box_runtime.c \
          $(wildcard $(AI)/camera/c/src/*.c)
HDR     = $(wildcard $(CORE)/include/*.h $(PROTO)/include/*.h test/*.h)

.PHONY: test sim clean
test: $(BUILD)/test_box_core
	$(BUILD)/test_box_core
$(BUILD):
	mkdir -p $(BUILD)
$(BUILD)/test_box_core: test/test_box_core.c test/mock_hal.c $(LIBSRC) $(HDR) | $(BUILD)
	$(CC) $(CFLAGS) test/test_box_core.c test/mock_hal.c $(LIBSRC) -o $@ -lm
# Scenario runner: prints the radio frames of a box as hex lines (read by the integration tests of the gateway)
sim: $(BUILD)/box_sim
$(BUILD)/box_sim: test/box_sim.c test/mock_hal.c $(LIBSRC) $(HDR) | $(BUILD)
	$(CC) $(CFLAGS) test/box_sim.c test/mock_hal.c $(LIBSRC) -o $@ -lm
clean:
	rm -rf $(BUILD)
