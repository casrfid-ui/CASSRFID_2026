set(P ${CMAKE_CURRENT_LIST_DIR}/../../../../protocol/c)
idf_component_register(SRCS ${P}/src/ffp.c INCLUDE_DIRS ${P}/include)
