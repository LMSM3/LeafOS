#ifndef LEAF_BRAND_H
#define LEAF_BRAND_H

#ifdef __cplusplus
extern "C" {
#endif

typedef struct LeafBrand {
    const char *project_name;
    const char *flower_emoji;
    const char *default_icon;
    int flower_emoji_rate;
    int no_emoji;
    int quiet;
    int message_count;
} LeafBrand;

void leaf_brand_init(LeafBrand *brand);
const char *leaf_brand_icon(LeafBrand *brand);
void leaf_brand_say(LeafBrand *brand, const char *message);
void leaf_brand_warn(LeafBrand *brand, const char *message);

#ifdef __cplusplus
}
#endif

#endif
