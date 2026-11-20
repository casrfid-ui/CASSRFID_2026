# Host build and tests for the C port. The firmware build uses CMakeLists.txt (ESP-IDF component).
CC      ?= gcc
BUILD   ?= build
CFLAGS  ?= -std=c99 -O2 -Wall -Wextra -Wpedantic -Iinclude
LDLIBS  = -lm
SRC     = $(wildcard src/*.c)
HDR     = $(wildcard include/*.h)

.PHONY: all test cli clean
all: test

$(BUILD):
	mkdir -p $(BUILD)

cli: $(BUILD)/cam_cli
test: $(BUILD)/test_camera
	$(BUILD)/test_camera

$(BUILD)/cam_cli: test/cam_cli.c $(SRC) $(HDR) | $(BUILD)
	$(CC) $(CFLAGS) test/cam_cli.c $(SRC) -o $@ $(LDLIBS)

$(BUILD)/test_camera: test/test_camera.c $(SRC) $(HDR) | $(BUILD)
	$(CC) $(CFLAGS) test/test_camera.c $(SRC) -o $@ $(LDLIBS)

clean:
	rm -rf $(BUILD)
