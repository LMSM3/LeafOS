/* core/loaders/loader_demo_v2.c
 * LeafOS C loader demo v2 -- multi-platform, version-aware.
 * Targets: macOS (x86_64 + arm64), Linux, WSL, Windows (MSYS2/MinGW).
 * Build:   make   -or-   cc core/loaders/loader_demo_v2.c core/brand/brand.c -o build/leaf_loader_demo_v2
 */
#include "../brand/brand.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

/* ── Platform abstraction ────────────────────────────────────────────────── */
#if defined(_WIN32) || defined(__MINGW32__)
#  include <windows.h>
#  define LEAF_OS_LABEL "Windows"
   static void leaf_sleep_ms(int ms) { Sleep((DWORD)ms); }
   static int  leaf_enable_ansi(void) {
	   HANDLE h = GetStdHandle(STD_OUTPUT_HANDLE);
	   DWORD  m = 0;
	   if (!GetConsoleMode(h, &m)) return 0;
	   return SetConsoleMode(h, m | ENABLE_VIRTUAL_TERMINAL_PROCESSING) ? 1 : 0;
   }
   static const char *leaf_os_name(void) { return LEAF_OS_LABEL; }

#elif defined(__APPLE__) && defined(__MACH__)
#  include <unistd.h>
#  include <sys/utsname.h>
#  define LEAF_OS_LABEL "macOS"
   static void leaf_sleep_ms(int ms) { usleep((useconds_t)ms * 1000); }
   static int  leaf_enable_ansi(void) { return 1; }
   static const char *leaf_os_name(void) {
	   static char buf[64];
	   struct utsname u;
	   if (uname(&u) == 0) snprintf(buf, sizeof(buf), "macOS (%s %s)", u.sysname, u.release);
	   else snprintf(buf, sizeof(buf), "macOS");
	   return buf;
   }

#else
#  include <unistd.h>
#  define LEAF_OS_LABEL "Linux"
   static void leaf_sleep_ms(int ms) { usleep((useconds_t)ms * 1000); }
   static int  leaf_enable_ansi(void) { return 1; }
   static const char *leaf_os_name(void) {
	   FILE *f = fopen("/proc/version", "r");
	   if (!f) return LEAF_OS_LABEL;
	   static char buf[32];
	   char tmp[256];
	   if (fgets(tmp, sizeof(tmp), f)) {
		   if (strstr(tmp, "icrosoft") || strstr(tmp, "WSL"))
			   snprintf(buf, sizeof(buf), "WSL");
		   else
			   snprintf(buf, sizeof(buf), "Linux");
	   } else {
		   snprintf(buf, sizeof(buf), LEAF_OS_LABEL);
	   }
	   fclose(f);
	   return buf;
   }
#endif

/* ── ANSI colours ────────────────────────────────────────────────────────── */
#define A_RESET   "\x1b[0m"
#define A_BOLD    "\x1b[1m"
#define A_GREEN   "\x1b[32m"
#define A_YELLOW  "\x1b[33m"
#define A_CYAN    "\x1b[36m"

/* ── Version ─────────────────────────────────────────────────────────────── */
#define LEAF_DEMO_VER "2.0.0"

static void print_header(LeafBrand *b, int ansi) {
	if (ansi)
		printf("%s%s%s leaf_loader_demo v%s\n",
			   A_BOLD, A_GREEN, leaf_brand_icon(b), LEAF_DEMO_VER);
	else
		printf("%s leaf_loader_demo v%s\n", leaf_brand_icon(b), LEAF_DEMO_VER);
	printf("  platform : %s\n", leaf_os_name());
	printf("  compiled : " __DATE__ " " __TIME__ "\n");
	printf("  C std    : C%d\n",
#if __STDC_VERSION__ >= 201112L
		11
#elif __STDC_VERSION__ >= 199901L
		99
#else
		89
#endif
	);
	if (ansi) printf(A_RESET);
	printf("\n");
}

/* ── Loader frames ───────────────────────────────────────────────────────── */
typedef struct { const char **frames; int n; const char *name; } Loader;

/* Unicode */
static const char *fr_orbit[]   = {"\xe2\x97\x90","\xe2\x97\x93","\xe2\x97\x91","\xe2\x97\x92"};
static const char *fr_braille[] = {
	"\xe2\xa0\x8b","\xe2\xa0\x99","\xe2\xa0\xb9","\xe2\xa0\xb8","\xe2\xa0\xbc",
	"\xe2\xa0\xb4","\xe2\xa0\xa6","\xe2\xa0\xa7","\xe2\xa0\x87","\xe2\xa0\x8f"
};
static const char *fr_bounce[]  = {
	"\xe2\x96\x81","\xe2\x96\x82","\xe2\x96\x83","\xe2\x96\x84","\xe2\x96\x85",
	"\xe2\x96\x86","\xe2\x96\x87","\xe2\x96\x88","\xe2\x96\x87","\xe2\x96\x86",
	"\xe2\x96\x85","\xe2\x96\x84"
};
/* ASCII fallbacks */
static const char *fr_spin[]  = {"|", "/", "-", "\\"};
static const char *fr_dots[]  = {".", "..", "...", "....", "...", ".."};
static const char *fr_bar[]   = {"[    ]","[=   ]","[==  ]","[=== ]","[====]"};

static void run_loader(LeafBrand *b, Loader *l, int ansi) {
	for (int i = 0; i < 24; i++) {
		if (ansi)
			printf("\r%s%s%s [%s] %s %s%s",
				   A_BOLD, A_GREEN, leaf_brand_icon(b),
				   b->project_name, l->name, l->frames[i % l->n], A_RESET);
		else
			printf("\r%s [%s] %s %s",
				   leaf_brand_icon(b), b->project_name, l->name, l->frames[i % l->n]);
		fflush(stdout);
		leaf_sleep_ms(60);
	}
	printf("\r%s [%s] %s done         \n",
		   leaf_brand_icon(b), b->project_name, l->name);
}

/* ── main ────────────────────────────────────────────────────────────────── */
int main(int argc, char **argv) {
	int ansi = leaf_enable_ansi();
	for (int i = 1; i < argc; i++)
		if (strcmp(argv[i], "--no-ansi") == 0) { ansi = 0; break; }

	LeafBrand brand;
	leaf_brand_init(&brand);

	print_header(&brand, ansi);

	Loader unicode_loaders[] = {
		{ fr_orbit,   4,  "orbit"   },
		{ fr_braille, 10, "braille" },
		{ fr_bounce,  12, "bounce"  },
	};
	Loader ascii_loaders[] = {
		{ fr_spin, 4, "spin"  },
		{ fr_dots, 6, "dots"  },
		{ fr_bar,  5, "bar"   },
	};

	Loader *set   = ansi ? unicode_loaders : ascii_loaders;
	int     count = 3;

	leaf_brand_say(&brand, "C loader demo v2 starting");
	for (int i = 0; i < count; i++)
		run_loader(&brand, &set[i], ansi);
	leaf_brand_say(&brand, "C loader demo v2 complete");
	return 0;
}
