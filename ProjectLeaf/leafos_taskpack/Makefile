# Makefile -- Multi-platform build for LeafOS
# Targets : all  mac  linux  wsl  windows  clean  info
# Override: make CC=clang   or   make CC=x86_64-w64-mingw32-gcc

SHELL   := bash
ROOT    := $(dir $(realpath $(lastword $(MAKEFILE_LIST))))
SRC_DIR := $(ROOT)core
BLD_DIR := $(ROOT)build
BRAND_C := $(SRC_DIR)/brand/brand.c
DEMO_V1 := $(SRC_DIR)/loaders/loader_demo.c
DEMO_V2 := $(SRC_DIR)/loaders/loader_demo_v2.c

# ── Platform detection ────────────────────────────────────────────────────────
UNAME_S := $(shell uname -s 2>/dev/null || echo Windows_NT)
UNAME_M := $(shell uname -m 2>/dev/null || echo x86_64)

ifeq ($(UNAME_S),Darwin)
	PLATFORM := mac
	CC       ?= cc
	EXT      :=
	CFLAGS   += -arch $(UNAME_M)
	LDFLAGS  :=
else ifeq ($(UNAME_S),Linux)
	PLATFORM := linux
	WSL      := $(shell grep -qi microsoft /proc/version 2>/dev/null && echo 1 || echo 0)
	ifeq ($(WSL),1)
		PLATFORM := wsl
	endif
	CC  ?= cc
	EXT :=
	LDFLAGS :=
else
	# Windows (MSYS2 / MinGW / Git Bash)
	PLATFORM := windows
	CC       ?= gcc
	EXT      := .exe
	CFLAGS   += -D_WIN32_WINNT=0x0601
	LDFLAGS  :=
endif

CFLAGS  += -Wall -Wextra -O2 -std=c11 -I$(SRC_DIR)
CXX     ?= g++
CXXFLAGS += -Wall -Wextra -O2 -std=c++17 -I$(ROOT)include

OUT_V1  := $(BLD_DIR)/leaf_loader_demo$(EXT)
OUT_V2  := $(BLD_DIR)/leaf_loader_demo_v2$(EXT)
MEMORY_CLI := $(BLD_DIR)/leaf-memory$(EXT)
TUI_CLI := $(BLD_DIR)/leaf-tui$(EXT)
MEMORY_SRC := $(ROOT)cli/leaf-memory.cpp $(ROOT)src/memory/event.cpp $(ROOT)src/memory/journal.cpp
FLOWER_MONITOR_SRC := $(ROOT)core/monitor/flower.c
FLOWER_MONITOR := $(BLD_DIR)/flower-monitor

FLOWER_DEFAULT :=
ifneq ($(filter $(PLATFORM),linux wsl),)
	FLOWER_DEFAULT := $(FLOWER_MONITOR)
endif

# ── Targets ───────────────────────────────────────────────────────────────────
.PHONY: all mac linux wsl windows clean info tui flower-monitor

all: info $(OUT_V1) $(OUT_V2) $(MEMORY_CLI) $(FLOWER_DEFAULT)

mac linux wsl windows: all

$(BLD_DIR):
	mkdir -p $(BLD_DIR)

$(OUT_V1): $(DEMO_V1) $(BRAND_C) | $(BLD_DIR)
	$(CC) $(CFLAGS) $^ -o $@ $(LDFLAGS)
	@echo "  built [$(PLATFORM)/$(UNAME_M)]: $(notdir $@)"

$(OUT_V2): $(DEMO_V2) $(BRAND_C) | $(BLD_DIR)
	$(CC) $(CFLAGS) $^ -o $@ $(LDFLAGS)
	@echo "  built [$(PLATFORM)/$(UNAME_M)]: $(notdir $@)"

$(MEMORY_CLI): $(MEMORY_SRC) | $(BLD_DIR)
	$(CXX) $(CXXFLAGS) $^ -o $@ $(LDFLAGS)
	@echo "  built [$(PLATFORM)/$(UNAME_M)]: $(notdir $@)"

tui:
	bash $(ROOT)bin/build_tui.sh

flower-monitor: $(FLOWER_MONITOR)

$(FLOWER_MONITOR): $(FLOWER_MONITOR_SRC) | $(BLD_DIR)
	@if [ "$(PLATFORM)" != "linux" ] && [ "$(PLATFORM)" != "wsl" ]; then \
		echo "flower-monitor requires Linux or WSL"; \
		exit 1; \
	fi
	$(CC) $(CFLAGS) $< -o $@ -lm
	@echo "  built [$(PLATFORM)/$(UNAME_M)]: $(notdir $@)"

info:
	@echo "LeafOS build  platform=$(PLATFORM)  cc=$(CC)  arch=$(UNAME_M)"

clean:
	rm -rf $(BLD_DIR)
	@echo "  cleaned build/"
