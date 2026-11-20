# ESP-IDF component (firmware build). Host build and tests: `make test` (see Makefile).
idf_component_register(
    SRCS "src/gc_config.c" "src/gc_quality.c" "src/gc_compensate.c" "src/gc_filter.c"
         "src/gc_baseline.c" "src/gc_score.c" "src/gc_class.c" "src/gc_chain.c"
    INCLUDE_DIRS "include"
    PRIV_INCLUDE_DIRS "src")
