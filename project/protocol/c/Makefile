CC ?= gcc
BUILD ?= build
CFLAGS ?= -std=c99 -O2 -Wall -Wextra -Wpedantic -Iinclude
.PHONY: test clean
test: $(BUILD)/test_ffp $(BUILD)/ffp_cli
	$(BUILD)/test_ffp $(BUILD)/vectors.txt
$(BUILD):
	mkdir -p $(BUILD)
$(BUILD)/test_ffp: test/test_ffp.c src/ffp.c include/ffp.h | $(BUILD)
	$(CC) $(CFLAGS) test/test_ffp.c src/ffp.c -o $@ -lm
$(BUILD)/ffp_cli: test/ffp_cli.c src/ffp.c include/ffp.h | $(BUILD)
	$(CC) $(CFLAGS) test/ffp_cli.c src/ffp.c -o $@ -lm
clean:
	rm -rf $(BUILD)
