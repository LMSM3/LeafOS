#include "leaf_tui_json.h"

#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define LEAF_JSON_MAX_BYTES (4U * 1024U * 1024U)
#define LEAF_JSON_MAX_TOKENS 16384

static int allocate_token(LeafJsonDoc *doc, LeafJsonType type, int start, int parent) {
    LeafJsonToken *token;
    if (doc->token_count >= LEAF_JSON_MAX_TOKENS) {
        return -1;
    }
    token = &doc->tokens[doc->token_count];
    token->type = type;
    token->start = start;
    token->end = -1;
    token->size = 0;
    token->parent = parent;
    if (parent >= 0) {
        doc->tokens[parent].size++;
    }
    return doc->token_count++;
}

static int parse_string(LeafJsonDoc *doc, size_t *position, int parent) {
    size_t cursor = *position + 1;
    int token = allocate_token(doc, LEAF_JSON_STRING, (int)cursor, parent);
    if (token < 0) {
        return -1;
    }
    while (cursor < doc->length) {
        char value = doc->text[cursor];
        if (value == '"') {
            doc->tokens[token].end = (int)cursor;
            *position = cursor;
            return token;
        }
        if (value == '\\') {
            cursor++;
            if (cursor >= doc->length) {
                return -1;
            }
            if (doc->text[cursor] == 'u') {
                if (cursor + 4 >= doc->length) {
                    return -1;
                }
                cursor += 4;
            }
        } else if ((unsigned char)value < 0x20) {
            return -1;
        }
        cursor++;
    }
    return -1;
}

static int parse_primitive(LeafJsonDoc *doc, size_t *position, int parent) {
    size_t cursor = *position;
    int token = allocate_token(doc, LEAF_JSON_PRIMITIVE, (int)cursor, parent);
    if (token < 0) {
        return -1;
    }
    while (cursor < doc->length) {
        char value = doc->text[cursor];
        if (value == ',' || value == ']' || value == '}' || isspace((unsigned char)value)) {
            break;
        }
        if ((unsigned char)value < 0x20 || value == ':' || value == '"') {
            return -1;
        }
        cursor++;
    }
    if (cursor == (size_t)doc->tokens[token].start) {
        return -1;
    }
    doc->tokens[token].end = (int)cursor;
    *position = cursor - 1;
    return token;
}

static int parse_document(LeafJsonDoc *doc) {
    int parent = -1;
    size_t position;
    for (position = 0; position < doc->length; position++) {
        char value = doc->text[position];
        int token;
        if (isspace((unsigned char)value) || value == ':' || value == ',') {
            continue;
        }
        if (value == '{' || value == '[') {
            token = allocate_token(doc, value == '{' ? LEAF_JSON_OBJECT : LEAF_JSON_ARRAY, (int)position, parent);
            if (token < 0) {
                return -1;
            }
            parent = token;
            continue;
        }
        if (value == '}' || value == ']') {
            LeafJsonType expected = value == '}' ? LEAF_JSON_OBJECT : LEAF_JSON_ARRAY;
            if (parent < 0 || doc->tokens[parent].type != expected) {
                return -1;
            }
            doc->tokens[parent].end = (int)position + 1;
            parent = doc->tokens[parent].parent;
            continue;
        }
        if (value == '"') {
            if (parse_string(doc, &position, parent) < 0) {
                return -1;
            }
            continue;
        }
        if (parse_primitive(doc, &position, parent) < 0) {
            return -1;
        }
    }
    return parent == -1 && doc->token_count > 0 && doc->tokens[0].end >= 0 ? 0 : -1;
}

int leaf_json_load(const char *path, LeafJsonDoc *doc, char *error, size_t error_size) {
    FILE *handle;
    long length;
    memset(doc, 0, sizeof(*doc));
    handle = fopen(path, "rb");
    if (!handle) {
        snprintf(error, error_size, "cannot open snapshot: %s", path);
        return -1;
    }
    if (fseek(handle, 0, SEEK_END) != 0 || (length = ftell(handle)) < 0 || (unsigned long)length > LEAF_JSON_MAX_BYTES) {
        fclose(handle);
        snprintf(error, error_size, "snapshot is unreadable or exceeds %u bytes", LEAF_JSON_MAX_BYTES);
        return -1;
    }
    rewind(handle);
    doc->text = (char *)malloc((size_t)length + 1);
    doc->tokens = (LeafJsonToken *)calloc(LEAF_JSON_MAX_TOKENS, sizeof(LeafJsonToken));
    if (!doc->text || !doc->tokens) {
        fclose(handle);
        leaf_json_free(doc);
        snprintf(error, error_size, "snapshot allocation failed");
        return -1;
    }
    if (fread(doc->text, 1, (size_t)length, handle) != (size_t)length) {
        fclose(handle);
        leaf_json_free(doc);
        snprintf(error, error_size, "snapshot read failed");
        return -1;
    }
    fclose(handle);
    doc->text[length] = '\0';
    doc->length = (size_t)length;
    if (parse_document(doc) != 0 || doc->tokens[0].type != LEAF_JSON_OBJECT) {
        leaf_json_free(doc);
        snprintf(error, error_size, "snapshot JSON is invalid or too complex");
        return -1;
    }
    return 0;
}

void leaf_json_free(LeafJsonDoc *doc) {
    free(doc->text);
    free(doc->tokens);
    memset(doc, 0, sizeof(*doc));
}

static int token_equals(const LeafJsonDoc *doc, int token, const char *value) {
    size_t length;
    if (token < 0 || token >= doc->token_count || doc->tokens[token].type != LEAF_JSON_STRING) {
        return 0;
    }
    length = (size_t)(doc->tokens[token].end - doc->tokens[token].start);
    return strlen(value) == length && strncmp(doc->text + doc->tokens[token].start, value, length) == 0;
}

int leaf_json_object_get(const LeafJsonDoc *doc, int object, const char *key) {
    int index;
    if (object < 0 || object >= doc->token_count || doc->tokens[object].type != LEAF_JSON_OBJECT) {
        return -1;
    }
    for (index = object + 1; index < doc->token_count; index++) {
        if (doc->tokens[index].start >= doc->tokens[object].end) {
            break;
        }
        if (doc->tokens[index].parent == object && token_equals(doc, index, key)) {
            int value = index + 1;
            return value < doc->token_count && doc->tokens[value].parent == object ? value : -1;
        }
    }
    return -1;
}

int leaf_json_array_get(const LeafJsonDoc *doc, int array, int requested) {
    int index;
    int found = 0;
    if (array < 0 || array >= doc->token_count || doc->tokens[array].type != LEAF_JSON_ARRAY || requested < 0) {
        return -1;
    }
    for (index = array + 1; index < doc->token_count; index++) {
        if (doc->tokens[index].start >= doc->tokens[array].end) {
            break;
        }
        if (doc->tokens[index].parent == array) {
            if (found == requested) {
                return index;
            }
            found++;
        }
    }
    return -1;
}

int leaf_json_array_size(const LeafJsonDoc *doc, int array) {
    int index;
    int count = 0;
    if (array < 0 || array >= doc->token_count || doc->tokens[array].type != LEAF_JSON_ARRAY) {
        return 0;
    }
    for (index = array + 1; index < doc->token_count; index++) {
        if (doc->tokens[index].start >= doc->tokens[array].end) {
            break;
        }
        if (doc->tokens[index].parent == array) {
            count++;
        }
    }
    return count;
}

int leaf_json_copy(const LeafJsonDoc *doc, int token, char *output, size_t output_size) {
    int cursor;
    size_t written = 0;
    if (!output || output_size == 0) {
        return -1;
    }
    output[0] = '\0';
    if (token < 0 || token >= doc->token_count) {
        return -1;
    }
    for (cursor = doc->tokens[token].start; cursor < doc->tokens[token].end && written + 1 < output_size; cursor++) {
        char value = doc->text[cursor];
        if (doc->tokens[token].type == LEAF_JSON_STRING && value == '\\' && cursor + 1 < doc->tokens[token].end) {
            char escaped = doc->text[++cursor];
            if (escaped == 'u') {
                int skip;
                for (skip = 0; skip < 4 && cursor + 1 < doc->tokens[token].end; skip++) {
                    cursor++;
                }
                value = '?';
            } else {
                switch (escaped) {
                    case 'n': value = '\n'; break;
                    case 'r': value = '\r'; break;
                    case 't': value = '\t'; break;
                    case 'b': value = '\b'; break;
                    case 'f': value = '\f'; break;
                    default: value = escaped; break;
                }
            }
        }
        output[written++] = value;
    }
    output[written] = '\0';
    return 0;
}

double leaf_json_number(const LeafJsonDoc *doc, int token, double fallback) {
    char buffer[64];
    char *end = NULL;
    double value;
    if (leaf_json_copy(doc, token, buffer, sizeof(buffer)) != 0 || strcmp(buffer, "null") == 0) {
        return fallback;
    }
    value = strtod(buffer, &end);
    return end && *end == '\0' ? value : fallback;
}

long leaf_json_integer(const LeafJsonDoc *doc, int token, long fallback) {
    return (long)leaf_json_number(doc, token, (double)fallback);
}

int leaf_json_boolean(const LeafJsonDoc *doc, int token, int fallback) {
    char buffer[16];
    if (leaf_json_copy(doc, token, buffer, sizeof(buffer)) != 0) {
        return fallback;
    }
    if (strcmp(buffer, "true") == 0) {
        return 1;
    }
    if (strcmp(buffer, "false") == 0) {
        return 0;
    }
    return fallback;
}
