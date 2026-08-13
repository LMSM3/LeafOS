cmake_minimum_required(VERSION 3.20)
project(leafos_providers LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_library(providers_core
	src/expert_registry.cpp
	src/model_group.cpp
	src/moe_router.cpp
	src/stack_table.cpp
	src/host_capacity.cpp
	src/provider.cpp)
target_include_directories(providers_core PUBLIC include)

add_executable(leaf-route src/main.cpp)
target_link_libraries(leaf-route PRIVATE providers_core)

add_executable(leaf-roundtable src/roundtable.cpp)
target_link_libraries(leaf-roundtable PRIVATE providers_core winhttp)
set_target_properties(leaf-roundtable PROPERTIES RUNTIME_OUTPUT_DIRECTORY ${CMAKE_SOURCE_DIR}/bin)

set_target_properties(leaf-route PROPERTIES RUNTIME_OUTPUT_DIRECTORY ${CMAKE_SOURCE_DIR}/bin)

include(CTest)
if(BUILD_TESTING)
	add_executable(test_router tests/test_router.cpp)
	target_link_libraries(test_router PRIVATE providers_core)
	add_test(NAME test_router COMMAND test_router)
endif()
