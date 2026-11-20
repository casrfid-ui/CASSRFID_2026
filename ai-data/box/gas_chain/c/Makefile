# Host build and tests for the C port. The firmware build uses CMakeLists.txt (ESP-IDF component).
CC      ?= gcc
BUILD   ?= build
CFLAGS  ?= -std=c99 -O2 -Wall -Wextra -Wpedantic -Iinclude -Isrc
LDLIBS  = -lm
SRC     = $(wildcard src/*.c)
HDR     = $(wildcard src/*.h include/*.h)

.PHONY: all test cli clean
all: test

$(BUILD):
	mkdir -p $(BUILD)

cli: $(BUILD)/gc_cli
test: $(BUILD)/test_gas_chain
	$(BUILD)/test_gas_chain

$(BUILD)/gc_cli: test/gc_cli.c $(SRC) $(HDR) | $(BUILD)
	$(CC) $(CFLAGS) test/gc_cli.c $(SRC) -o $@ $(LDLIBS)

$(BUILD)/test_gas_chain: test/test_gas_chain.c $(SRC) $(HDR) | $(BUILD)
	$(CC) $(CFLAGS) test/test_gas_chain.c $(SRC) -o $@ $(LDLIBS)

clean:
	rm -rf $(BUILD)
