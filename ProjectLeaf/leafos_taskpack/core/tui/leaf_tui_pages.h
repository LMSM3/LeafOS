#ifndef LEAF_TUI_PAGES_H
#define LEAF_TUI_PAGES_H

#include "leaf_tui_input.h"
#include "leaf_tui_state.h"

void leaf_tui_pages_init_colors(void);
void leaf_tui_pages_render(const LeafTuiState *state, const LeafTuiInput *input, const char *external_message);
void leaf_tui_pages_plain(const LeafTuiState *state, int page, int width, int height);

#endif
