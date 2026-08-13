#include "../brand/brand.h"

#include <stdio.h>
#include <time.h>

#ifdef _WIN32
#include <windows.h>
static void leaf_sleep_ms(int ms) { Sleep((DWORD)ms); }
#else
#include <unistd.h>
static void leaf_sleep_ms(int ms) { usleep((useconds_t)ms * 1000); }
#endif

static void run_loader(LeafBrand *brand, const char *name, const char **frames, int n) {
    for (int i = 0; i < 24; i++) {
        printf("\r%s [%s] %s %s", leaf_brand_icon(brand), brand->project_name, name, frames[i % n]);
        fflush(stdout);
        leaf_sleep_ms(60);
    }
    printf("\r%s [%s] %s done       \n", leaf_brand_icon(brand), brand->project_name, name);
}

int main(void) {
    LeafBrand brand;
    leaf_brand_init(&brand);

    const char *dots[] = {".", "..", "...", "....", "...", ".."};
    const char *bar[] = {"[    ]", "[=   ]", "[==  ]", "[=== ]", "[====]"};
    const char *orbit[] = {"◐", "◓", "◑", "◒"};

    leaf_brand_say(&brand, "C loader demo starting");
    run_loader(&brand, "dots3", dots, 6);
    run_loader(&brand, "bar", bar, 5);
    run_loader(&brand, "orbit", orbit, 4);
    leaf_brand_say(&brand, "C loader demo complete");

    return 0;
}
