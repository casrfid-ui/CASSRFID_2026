# Host build and tests for the C port. The firmware build uses CMakeLists.txt (ESP-IDF component).
CC      ?= gcc
BUILD   ?= build
CFLAGS  ?= -std=c99 -O2 -Wall -Wextra -Wpedantic -Iinclude 
LDLIBS  = -lm
SRC     = $(wildcard src/*.c)
HDR     = $(wildcard src/*.h include/*.h)

.PHONY: all test cli clean
all: test

$(BUILD):
	mkdir -p $(BUILD)

cli: $(BUILD)/sm_cli
test: $(BUILD)/test_state_machine
	$(BUILD)/test_state_machine

$(BUILD)/sm_cli: test/sm_cli.c $(SRC) $(HDR) | $(BUILD)
	$(CC) $(CFLAGS) test/sm_cli.c $(SRC) -o $@ $(LDLIBS)

$(BUILD)/test_state_machine: test/test_state_machine.c $(SRC) $(HDR) | $(BUILD)
	$(CC) $(CFLAGS) test/test_state_machine.c $(SRC) -o $@ $(LDLIBS)

clean:
	rm -rf $(BUILD)
