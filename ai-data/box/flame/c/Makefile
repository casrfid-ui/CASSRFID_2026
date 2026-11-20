# Host build and tests for the C port. The firmware build uses CMakeLists.txt (ESP-IDF component).
CC      ?= gcc
BUILD   ?= build
CFLAGS  ?= -std=c99 -O2 -Wall -Wextra -Wpedantic -Iinclude
LDLIBS  =

.PHONY: all test cli clean
all: test

$(BUILD):
	mkdir -p $(BUILD)

cli: $(BUILD)/flame_cli
test: $(BUILD)/test_flame
	$(BUILD)/test_flame

$(BUILD)/flame_cli: test/flame_cli.c src/flame.c include/flame.h | $(BUILD)
	$(CC) $(CFLAGS) test/flame_cli.c src/flame.c -o $@ $(LDLIBS)

$(BUILD)/test_flame: test/test_flame.c src/flame.c include/flame.h | $(BUILD)
	$(CC) $(CFLAGS) test/test_flame.c src/flame.c -o $@ $(LDLIBS)

clean:
	rm -rf $(BUILD)
