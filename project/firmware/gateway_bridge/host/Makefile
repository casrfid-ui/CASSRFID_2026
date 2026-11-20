CC ?= gcc
BUILD ?= build
PROTO = ../../../protocol/c
CORE = ../core
CFLAGS ?= -std=c99 -O2 -Wall -Wextra -Wpedantic -D_POSIX_C_SOURCE=200809L -I$(CORE)/include -I$(PROTO)/include
SRC = $(wildcard $(CORE)/src/*.c) $(PROTO)/src/ffp.c
HDR = $(wildcard $(CORE)/include/*.h $(PROTO)/include/*.h)
.PHONY: test clean
test: $(BUILD)/test_bridge
	$(BUILD)/test_bridge
$(BUILD):
	mkdir -p $(BUILD)
$(BUILD)/test_bridge: test/test_bridge.c $(SRC) $(HDR) | $(BUILD)
	$(CC) $(CFLAGS) test/test_bridge.c $(SRC) -o $@ -lm
clean:
	rm -rf $(BUILD)
