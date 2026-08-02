#include "brand.h"

#include <stdio.h>
#include <stdlib.h>

static const char *env_or_default(const char *key, const char *fallback) {
    const char *value = getenv(key);
    return (value == NULL || value[0] == '\0') ? fallback : value;
}

static int int_env_or_default(const char *key, int fallback) {
    const char *value = getenv(key);
    return (value == NULL || value[0] == '\0') ? fallback : atoi(value);
}

void leaf_brand_init(LeafBrand *brand) {
    if (brand == NULL) return;

    brand->project_name = env_or_default("PROJECT_NAME", "LeafOS");
    brand->flower_emoji = env_or_default("FLOWER_EMOJI", "✿");
    brand->default_icon = env_or_default("DEFAULT_ICON", "›");
    brand->flower_emoji_rate = int_env_or_default("FLOWER_EMOJI_RATE", 2);
    brand->no_emoji = int_env_or_default("NO_EMOJI", 0);
    brand->quiet = int_env_or_default("QUIET", 0);
    brand->message_count = 0;

    if (brand->flower_emoji_rate < 0) brand->flower_emoji_rate = 0;
}

const char *leaf_brand_icon(LeafBrand *brand) {
    if (brand == NULL) return "›";

    brand->message_count++;

    if (brand->no_emoji || brand->flower_emoji_rate <= 0) {
        return brand->default_icon;
    }

    if (brand->message_count % brand->flower_emoji_rate == 0) {
        return brand->flower_emoji;
    }

    return brand->default_icon;
}

void leaf_brand_say(LeafBrand *brand, const char *message) {
    if (brand == NULL || message == NULL || brand->quiet) return;
    printf("%s [%s] %s\n", leaf_brand_icon(brand), brand->project_name, message);
}

void leaf_brand_warn(LeafBrand *brand, const char *message) {
    if (brand == NULL || message == NULL) return;
    fprintf(stderr, "! [%s] warning: %s\n", brand->project_name, message);
}
