# Host build and tests for the C port. The firmware build uses CMakeLists.txt (ESP-IDF component).
CC      ?= gcc
BUILD   ?= build
CFLAGS  ?= -std=c99 -O2 -Wall -Wextra -Wpedantic -Iinclude
LDLIBS  = -lm

.PHONY: all test cli clean
all: test

$(BUILD):
	mkdir -p $(BUILD)

cli: $(BUILD)/fwi_cli
test: $(BUILD)/test_fwi
	$(BUILD)/test_fwi

$(BUILD)/fwi_cli: test/fwi_cli.c src/fwi.c include/fwi.h | $(BUILD)
	$(CC) $(CFLAGS) test/fwi_cli.c src/fwi.c -o $@ $(LDLIBS)

$(BUILD)/test_fwi: test/test_fwi.c src/fwi.c include/fwi.h | $(BUILD)
	$(CC) $(CFLAGS) test/test_fwi.c src/fwi.c -o $@ $(LDLIBS)

clean:
	rm -rf $(BUILD)
