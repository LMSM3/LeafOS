#ifndef LEAF_TUI_JSON_H
#define LEAF_TUI_JSON_H

#include <stddef.h>

typedef enum {
    LEAF_JSON_UNDEFINED = 0,
    LEAF_JSON_OBJECT,
    LEAF_JSON_ARRAY,
    LEAF_JSON_STRING,
    LEAF_JSON_PRIMITIVE
} LeafJsonType;

typedef struct {
    LeafJsonType type;
    int start;
    int end;
    int size;
    int parent;
} LeafJsonToken;

typedef struct {
    char *text;
    size_t length;
    LeafJsonToken *tokens;
    int token_count;
} LeafJsonDoc;

int leaf_json_load(const char *path, LeafJsonDoc *doc, char *error, size_t error_size);
void leaf_json_free(LeafJsonDoc *doc);
int leaf_json_object_get(const LeafJsonDoc *doc, int object, const char *key);
int leaf_json_array_get(const LeafJsonDoc *doc, int array, int index);
int leaf_json_array_size(const LeafJsonDoc *doc, int array);
int leaf_json_copy(const LeafJsonDoc *doc, int token, char *output, size_t output_size);
double leaf_json_number(const LeafJsonDoc *doc, int token, double fallback);
long leaf_json_integer(const LeafJsonDoc *doc, int token, long fallback);
int leaf_json_boolean(const LeafJsonDoc *doc, int token, int fallback);

#endif
