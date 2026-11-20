# Host build and tests of the box runtime. Links the three blocks from their own folders.
CC      ?= gcc
BUILD   ?= build
FWI     = ../../fwi/c
GAS     = ../../gas_chain/c
SMC     = ../../state_machine/c
FLM     = ../../flame/c
CFLAGS  ?= -std=c99 -O2 -Wall -Wextra -Wpedantic -Iinclude -I$(FWI)/include -I$(GAS)/include -I$(GAS)/src -I$(SMC)/include -I$(FLM)/include
LDLIBS  = -lm
SRC     = src/box_runtime.c $(FWI)/src/fwi.c $(wildcard $(GAS)/src/*.c) $(SMC)/src/state_machine.c $(FLM)/src/flame.c
HDR     = $(wildcard include/*.h $(FWI)/include/*.h $(GAS)/include/*.h $(GAS)/src/*.h $(SMC)/include/*.h $(FLM)/include/*.h)

.PHONY: all test cli clean
all: test

$(BUILD):
	mkdir -p $(BUILD)

cli: $(BUILD)/box_cli
test: $(BUILD)/test_box_runtime
	$(BUILD)/test_box_runtime

$(BUILD)/box_cli: test/box_cli.c $(SRC) $(HDR) | $(BUILD)
	$(CC) $(CFLAGS) test/box_cli.c $(SRC) -o $@ $(LDLIBS)

$(BUILD)/test_box_runtime: test/test_box_runtime.c $(SRC) $(HDR) | $(BUILD)
	$(CC) $(CFLAGS) test/test_box_runtime.c $(SRC) -o $@ $(LDLIBS)

clean:
	rm -rf $(BUILD)
