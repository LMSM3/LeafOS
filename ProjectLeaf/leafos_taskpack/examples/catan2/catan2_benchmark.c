/*
 * catan2_benchmark.c -- LeafOS Catan2 RTS benchmark.
 *
 * Catan2 replaces dice harvesting with continual resource increase. Player 0
 * is the LeafOS dual-brain player. Players 1 and 2 are deterministic bots.
 *
 * Optional real brain hooks:
 *   CATAN2_GPU_BRAIN_CMD proposes a tile id for player 0.
 *   CATAN2_CPU_BRAIN_CMD validates/overrides and chooses the final tile id.
 *
 * Each command is invoked as:
 *   <command> "<state-file>" <player> <tick> <gpu-proposal-tile-id>
 *
 * The command should print a tile id, or text containing a tile id. If no real
 * command is configured, or if it returns an illegal choice, the benchmark
 * falls back to local deterministic policy and records the fallback.
 */

#include <ctype.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#ifdef _WIN32
#include <direct.h>
#include <windows.h>
#define POPEN _popen
#define PCLOSE _pclose
#define MKDIR(path) _mkdir(path)
static void sleep_ms(int ms) { Sleep((DWORD)ms); }
#else
#include <sys/stat.h>
#include <unistd.h>
#define POPEN popen
#define PCLOSE pclose
#define MKDIR(path) mkdir((path), 0775)
static void sleep_ms(int ms) { usleep((useconds_t)ms * 1000U); }
#endif

#define ARRAY_LEN(a) (sizeof(a) / sizeof((a)[0]))
#define MAX_ADJACENT_TILES 3
#define PLAYER_COUNT 3
#define AI_PLAYER 0
#define DEFAULT_MINUTES 4
#define DEFAULT_LOGICAL_TICK_SECONDS 5
#define DEFAULT_TICK_MS 5000
#define HARVEST_UNIT 100
#define PATH_BUF 1024
#define CMD_BUF 2048
#define OUT_BUF 512

typedef enum Resource {
    RESOURCE_BRICK = 0,
    RESOURCE_LUMBER,
    RESOURCE_WOOL,
    RESOURCE_GRAIN,
    RESOURCE_ORE,
    RESOURCE_DESERT,
    RESOURCE_COUNT
} Resource;

typedef enum BuildingKind {
    BUILDING_SETTLEMENT = 1,
    BUILDING_CITY = 2
} BuildingKind;

typedef struct Tile {
    int id;
    Resource resource;
    int number;
} Tile;

typedef struct Building {
    int player;
    BuildingKind kind;
    int adjacent_tiles[MAX_ADJACENT_TILES];
} Building;

typedef struct HarvestChoice {
    int tile_id;
    Resource resource;
    int number_assignment;
    int productivity_level;
    int building_multiplier;
    int amount;
    const char *source;
} HarvestChoice;

typedef struct BrainStats {
    int configured;
    int calls;
    int valid;
    int invalid;
    long elapsed_ms;
} BrainStats;

typedef struct Config {
    int minutes;
    int logical_tick_seconds;
    int tick_ms;
    int explicit_ticks;
    int quiet;
    char run_dir[PATH_BUF];
} Config;

static const char *const RESOURCE_NAMES[RESOURCE_COUNT] = {
    "brick", "lumber", "wool", "grain", "ore", "desert"
};

static const Tile BOARD[] = {
    { 0,  RESOURCE_BRICK,  5 },
    { 1,  RESOURCE_LUMBER, 6 },
    { 2,  RESOURCE_WOOL,   8 },
    { 3,  RESOURCE_GRAIN,  9 },
    { 4,  RESOURCE_ORE,    10 },
    { 5,  RESOURCE_LUMBER, 4 },
    { 6,  RESOURCE_BRICK,  3 },
    { 7,  RESOURCE_WOOL,   11 },
    { 8,  RESOURCE_GRAIN,  2 },
    { 9,  RESOURCE_ORE,    12 },
    { 10, RESOURCE_DESERT, 0 },
    { 11, RESOURCE_LUMBER, 8 },
    { 12, RESOURCE_GRAIN,  6 },
    { 13, RESOURCE_WOOL,   5 },
    { 14, RESOURCE_ORE,    9 },
    { 15, RESOURCE_BRICK,  4 },
    { 16, RESOURCE_LUMBER, 10 },
    { 17, RESOURCE_WOOL,   11 },
    { 18, RESOURCE_GRAIN,  3 }
};

static const Building BUILDINGS[] = {
    { 0, BUILDING_SETTLEMENT, { 0, 1, 2 } },
    { 0, BUILDING_CITY,       { 3, 4, 12 } },
    { 1, BUILDING_SETTLEMENT, { 2, 3, 13 } },
    { 1, BUILDING_SETTLEMENT, { 5, 15, 6 } },
    { 1, BUILDING_CITY,       { 14, 4, 9 } },
    { 2, BUILDING_CITY,       { 11, 12, 2 } },
    { 2, BUILDING_SETTLEMENT, { 7, 17, 13 } },
    { 2, BUILDING_SETTLEMENT, { 8, 18, 6 } }
};

static const int BOT_RESOURCE_PRIORITY[PLAYER_COUNT][RESOURCE_DESERT] = {
    { 4, 4, 4, 4, 4 },
    { 5, 5, 3, 2, 1 },
    { 3, 4, 4, 4, 2 }
};

static const int ROBBER_TILE_ID = 10;

static const char *resource_name(Resource resource)
{
    if (resource < 0 || resource >= RESOURCE_COUNT) {
        return "unknown";
    }
    return RESOURCE_NAMES[resource];
}

static const Tile *find_tile(int tile_id)
{
    size_t i;

    for (i = 0; i < ARRAY_LEN(BOARD); i++) {
        if (BOARD[i].id == tile_id) {
            return &BOARD[i];
        }
    }
    return NULL;
}

static int productivity_level_for_number(int number)
{
    switch (number) {
    case 2:
    case 12:
        return 1;
    case 3:
    case 11:
        return 2;
    case 4:
    case 10:
        return 3;
    case 5:
    case 9:
        return 4;
    case 6:
    case 8:
        return 5;
    default:
        return 0;
    }
}

static int building_touches_tile(const Building *building, int tile_id)
{
    size_t i;

    for (i = 0; i < MAX_ADJACENT_TILES; i++) {
        if (building->adjacent_tiles[i] == tile_id) {
            return 1;
        }
    }
    return 0;
}

static int total_resources_for_player(
    int totals[PLAYER_COUNT][RESOURCE_COUNT],
    int player
)
{
    int total = 0;
    size_t resource;

    for (resource = 0; resource < RESOURCE_DESERT; resource++) {
        total += totals[player][resource];
    }
    return total;
}

static int is_legal_harvest_tile(int player, int tile_id)
{
    const Tile *tile = find_tile(tile_id);
    size_t i;

    if (tile == NULL || tile->resource == RESOURCE_DESERT) {
        return 0;
    }
    if (tile->id == ROBBER_TILE_ID) {
        return 0;
    }
    if (productivity_level_for_number(tile->number) <= 0) {
        return 0;
    }

    for (i = 0; i < ARRAY_LEN(BUILDINGS); i++) {
        if (BUILDINGS[i].player == player &&
            building_touches_tile(&BUILDINGS[i], tile_id)) {
            return 1;
        }
    }
    return 0;
}

static int fill_choice_from_tile(
    int player,
    int tile_id,
    const char *source,
    HarvestChoice *choice
)
{
    const Tile *tile = find_tile(tile_id);
    size_t i;
    int best_multiplier = 0;

    if (!is_legal_harvest_tile(player, tile_id) || tile == NULL) {
        return 0;
    }

    for (i = 0; i < ARRAY_LEN(BUILDINGS); i++) {
        const Building *building = &BUILDINGS[i];

        if (building->player == player &&
            building_touches_tile(building, tile_id) &&
            (int)building->kind > best_multiplier) {
            best_multiplier = (int)building->kind;
        }
    }

    choice->tile_id = tile_id;
    choice->resource = tile->resource;
    choice->number_assignment = tile->number;
    choice->productivity_level = productivity_level_for_number(tile->number);
    choice->building_multiplier = best_multiplier;
    choice->amount = HARVEST_UNIT * choice->productivity_level * best_multiplier;
    choice->source = source;
    return 1;
}

static int choose_policy_harvest(
    int player,
    int totals[PLAYER_COUNT][RESOURCE_COUNT],
    const char *source,
    HarvestChoice *choice
)
{
    int best_score = -1000000000;
    int best_tile = -1;
    size_t building_index;

    for (building_index = 0; building_index < ARRAY_LEN(BUILDINGS);
         building_index++) {
        const Building *building = &BUILDINGS[building_index];
        size_t adjacent_index;

        if (building->player != player) {
            continue;
        }

        for (adjacent_index = 0; adjacent_index < MAX_ADJACENT_TILES;
             adjacent_index++) {
            const Tile *tile = find_tile(building->adjacent_tiles[adjacent_index]);
            int productivity;
            int amount;
            int priority;
            int stock_penalty;
            int score;

            if (tile == NULL || !is_legal_harvest_tile(player, tile->id)) {
                continue;
            }

            productivity = productivity_level_for_number(tile->number);
            amount = HARVEST_UNIT * productivity * (int)building->kind;
            priority = BOT_RESOURCE_PRIORITY[player][tile->resource];
            stock_penalty = totals[player][tile->resource];
            score = priority * 100 + amount - stock_penalty;

            if (score > best_score) {
                best_score = score;
                best_tile = tile->id;
            }
        }
    }

    if (best_tile < 0) {
        return 0;
    }
    return fill_choice_from_tile(player, best_tile, source, choice);
}

static int parse_last_int(const char *text, int *out)
{
    const char *p = text;
    int found = 0;
    int last = 0;

    while (*p != '\0') {
        int sign = 1;
        long value = 0;

        while (*p != '\0' && !isdigit((unsigned char)*p) && *p != '-') {
            p++;
        }
        if (*p == '\0') {
            break;
        }
        if (*p == '-') {
            sign = -1;
            p++;
        }
        if (!isdigit((unsigned char)*p)) {
            continue;
        }
        while (isdigit((unsigned char)*p)) {
            value = value * 10 + (*p - '0');
            p++;
        }
        last = (int)(value * sign);
        found = 1;
    }

    if (found) {
        *out = last;
    }
    return found;
}

static long elapsed_ms_from(clock_t start, clock_t end)
{
    return (long)(((double)(end - start) * 1000.0) / (double)CLOCKS_PER_SEC);
}

static int call_brain_command(
    const char *command_base,
    const char *state_path,
    int player,
    int tick,
    int gpu_proposal,
    BrainStats *stats,
    int *tile_id
)
{
    char command[CMD_BUF];
    char output[OUT_BUF];
    FILE *pipe;
    clock_t start;
    clock_t end;
    size_t used = 0;

    if (command_base == NULL || command_base[0] == '\0') {
        return 0;
    }

    stats->configured = 1;
    stats->calls++;

    snprintf(command, sizeof(command), "%s \"%s\" %d %d %d",
             command_base, state_path, player, tick, gpu_proposal);

    start = clock();
    pipe = POPEN(command, "r");
    if (pipe == NULL) {
        stats->invalid++;
        return 0;
    }

    output[0] = '\0';
    while (fgets(output + used, (int)(sizeof(output) - used), pipe) != NULL) {
        used = strlen(output);
        if (used + 1 >= sizeof(output)) {
            break;
        }
    }
    PCLOSE(pipe);
    end = clock();
    stats->elapsed_ms += elapsed_ms_from(start, end);

    if (!parse_last_int(output, tile_id)) {
        stats->invalid++;
        return 0;
    }

    if (!is_legal_harvest_tile(player, *tile_id)) {
        stats->invalid++;
        return 0;
    }

    stats->valid++;
    return 1;
}

static void write_state_file(
    const char *run_dir,
    int tick,
    int player,
    int simulated_seconds,
    int gpu_proposal,
    int totals[PLAYER_COUNT][RESOURCE_COUNT],
    char out_path[PATH_BUF]
)
{
    FILE *file;
    size_t i;
    int p;

    snprintf(out_path, PATH_BUF, "%s/state_tick_%04d_player_%d.txt",
             run_dir, tick, player);
    file = fopen(out_path, "w");
    if (file == NULL) {
        out_path[0] = '\0';
        return;
    }

    fprintf(file, "leafos_object=catan2_state\n");
    fprintf(file, "tick=%d\n", tick);
    fprintf(file, "player=%d\n", player);
    fprintf(file, "simulated_seconds=%d\n", simulated_seconds);
    fprintf(file, "gpu_proposal=%d\n", gpu_proposal);
    fprintf(file, "harvest_unit=%d\n", HARVEST_UNIT);
    fprintf(file, "resources=brick,lumber,wool,grain,ore\n");
    for (p = 0; p < PLAYER_COUNT; p++) {
        fprintf(file, "P%d_totals=%d,%d,%d,%d,%d\n",
                p,
                totals[p][RESOURCE_BRICK],
                totals[p][RESOURCE_LUMBER],
                totals[p][RESOURCE_WOOL],
                totals[p][RESOURCE_GRAIN],
                totals[p][RESOURCE_ORE]);
    }
    fprintf(file, "legal_tiles=");
    for (i = 0; i < ARRAY_LEN(BOARD); i++) {
        const Tile *tile = &BOARD[i];

        if (is_legal_harvest_tile(player, tile->id)) {
            fprintf(file, "%d:%s:%d:%d ",
                    tile->id,
                    resource_name(tile->resource),
                    tile->number,
                    productivity_level_for_number(tile->number));
        }
    }
    fprintf(file, "\n");
    fclose(file);
}

static void append_event(
    FILE *events,
    int tick,
    int simulated_seconds,
    int player,
    const HarvestChoice *choice,
    int total_after
)
{
    if (events == NULL) {
        return;
    }

    fprintf(events,
            "{\"tick\":%d,\"simulated_seconds\":%d,\"player\":%d,"
            "\"source\":\"%s\",\"tile_id\":%d,\"resource\":\"%s\","
            "\"number\":%d,\"productivity\":%d,\"multiplier\":%d,"
            "\"amount\":%d,\"total_after\":%d}\n",
            tick,
            simulated_seconds,
            player,
            choice->source,
            choice->tile_id,
            resource_name(choice->resource),
            choice->number_assignment,
            choice->productivity_level,
            choice->building_multiplier,
            choice->amount,
            total_after);
    fflush(events);
}

static void apply_choice(
    int totals[PLAYER_COUNT][RESOURCE_COUNT],
    const HarvestChoice *choice,
    int player
)
{
    totals[player][choice->resource] += choice->amount;
}

static int choose_dual_brain_harvest(
    int tick,
    int simulated_seconds,
    const char *run_dir,
    int totals[PLAYER_COUNT][RESOURCE_COUNT],
    BrainStats *gpu_stats,
    BrainStats *cpu_stats,
    HarvestChoice *choice
)
{
    const char *gpu_cmd = getenv("CATAN2_GPU_BRAIN_CMD");
    const char *cpu_cmd = getenv("CATAN2_CPU_BRAIN_CMD");
    char state_path[PATH_BUF];
    int gpu_tile = -1;
    int cpu_tile = -1;

    write_state_file(run_dir, tick, AI_PLAYER, simulated_seconds, -1,
                     totals, state_path);
    if (state_path[0] != '\0' &&
        call_brain_command(gpu_cmd, state_path, AI_PLAYER, tick, -1,
                           gpu_stats, &gpu_tile)) {
        if (fill_choice_from_tile(AI_PLAYER, gpu_tile, "gpu_brain", choice)) {
            /* Keep the proposal available for CPU validation. */
        }
    }

    write_state_file(run_dir, tick, AI_PLAYER, simulated_seconds, gpu_tile,
                     totals, state_path);
    if (state_path[0] != '\0' &&
        call_brain_command(cpu_cmd, state_path, AI_PLAYER, tick, gpu_tile,
                           cpu_stats, &cpu_tile)) {
        return fill_choice_from_tile(AI_PLAYER, cpu_tile, "cpu_brain", choice);
    }

    if (gpu_tile >= 0 &&
        fill_choice_from_tile(AI_PLAYER, gpu_tile, "gpu_brain_fallback", choice)) {
        return 1;
    }

    return choose_policy_harvest(AI_PLAYER, totals, "local_ai_fallback", choice);
}

static FILE *open_events_log(const char *run_dir, char path[PATH_BUF])
{
    if (run_dir == NULL || run_dir[0] == '\0') {
        path[0] = '\0';
        return NULL;
    }

    MKDIR(run_dir);
    snprintf(path, PATH_BUF, "%s/events.jsonl", run_dir);
    return fopen(path, "w");
}

static void write_summary(
    const char *run_dir,
    int ticks,
    int minutes,
    int logical_tick_seconds,
    int totals[PLAYER_COUNT][RESOURCE_COUNT],
    const BrainStats *gpu_stats,
    const BrainStats *cpu_stats
)
{
    char path[PATH_BUF];
    FILE *file;
    int player;

    if (run_dir == NULL || run_dir[0] == '\0') {
        return;
    }

    snprintf(path, sizeof(path), "%s/summary.json", run_dir);
    file = fopen(path, "w");
    if (file == NULL) {
        return;
    }

    fprintf(file, "{\n");
    fprintf(file, "  \"leafos_object\": \"catan2_benchmark_summary\",\n");
    fprintf(file, "  \"minutes\": %d,\n", minutes);
    fprintf(file, "  \"ticks\": %d,\n", ticks);
    fprintf(file, "  \"logical_tick_seconds\": %d,\n", logical_tick_seconds);
    fprintf(file, "  \"harvest_unit\": %d,\n", HARVEST_UNIT);
    fprintf(file, "  \"players\": [\n");
    for (player = 0; player < PLAYER_COUNT; player++) {
        fprintf(file,
                "    {\"player\": %d, \"total\": %d, "
                "\"brick\": %d, \"lumber\": %d, \"wool\": %d, "
                "\"grain\": %d, \"ore\": %d}%s\n",
                player,
                total_resources_for_player(totals, player),
                totals[player][RESOURCE_BRICK],
                totals[player][RESOURCE_LUMBER],
                totals[player][RESOURCE_WOOL],
                totals[player][RESOURCE_GRAIN],
                totals[player][RESOURCE_ORE],
                player == PLAYER_COUNT - 1 ? "" : ",");
    }
    fprintf(file, "  ],\n");
    fprintf(file,
            "  \"gpu_brain\": {\"configured\": %d, \"calls\": %d, "
            "\"valid\": %d, \"invalid\": %d, \"elapsed_ms\": %ld},\n",
            gpu_stats->configured, gpu_stats->calls, gpu_stats->valid,
            gpu_stats->invalid, gpu_stats->elapsed_ms);
    fprintf(file,
            "  \"cpu_brain\": {\"configured\": %d, \"calls\": %d, "
            "\"valid\": %d, \"invalid\": %d, \"elapsed_ms\": %ld}\n",
            cpu_stats->configured, cpu_stats->calls, cpu_stats->valid,
            cpu_stats->invalid, cpu_stats->elapsed_ms);
    fprintf(file, "}\n");
    fclose(file);
}

static void print_totals(int totals[PLAYER_COUNT][RESOURCE_COUNT])
{
    int player;

    printf("\nCatan2 benchmark totals\n");
    printf("player  role         brick  lumber  wool  grain  ore  total\n");
    printf("------  -----------  -----  ------  ----  -----  ---  -----\n");
    for (player = 0; player < PLAYER_COUNT; player++) {
        printf("P%-5d  %-11s  %5d  %6d  %4d  %5d  %3d  %5d\n",
               player,
               player == AI_PLAYER ? "dual-brain" : "bot",
               totals[player][RESOURCE_BRICK],
               totals[player][RESOURCE_LUMBER],
               totals[player][RESOURCE_WOOL],
               totals[player][RESOURCE_GRAIN],
               totals[player][RESOURCE_ORE],
               total_resources_for_player(totals, player));
    }
}

static void usage(const char *name)
{
    printf("usage: %s [--minutes N] [--ticks N] [--tick-ms N] "
           "[--logical-tick-sec N] [--run-dir PATH] [--quiet]\n", name);
    printf("profiles: 4 minutes, 8 minutes, and 64 minutes are intended.\n");
}

static int parse_int_arg(const char *text, int *out)
{
    char *end = NULL;
    long value = strtol(text, &end, 10);

    if (end == text || *end != '\0' || value < 0 || value > 1000000) {
        return 0;
    }
    *out = (int)value;
    return 1;
}

static int parse_args(int argc, char **argv, Config *config)
{
    int i;

    config->minutes = DEFAULT_MINUTES;
    config->logical_tick_seconds = DEFAULT_LOGICAL_TICK_SECONDS;
    config->tick_ms = DEFAULT_TICK_MS;
    config->explicit_ticks = 0;
    config->quiet = 0;
    config->run_dir[0] = '\0';

    for (i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--help") == 0 || strcmp(argv[i], "-h") == 0) {
            usage(argv[0]);
            return 0;
        } else if (strcmp(argv[i], "--quiet") == 0) {
            config->quiet = 1;
        } else if (i + 1 >= argc) {
            fprintf(stderr, "missing value after %s\n", argv[i]);
            return -1;
        } else if (strcmp(argv[i], "--minutes") == 0) {
            if (!parse_int_arg(argv[++i], &config->minutes)) {
                return -1;
            }
        } else if (strcmp(argv[i], "--ticks") == 0) {
            if (!parse_int_arg(argv[++i], &config->explicit_ticks)) {
                return -1;
            }
        } else if (strcmp(argv[i], "--tick-ms") == 0) {
            if (!parse_int_arg(argv[++i], &config->tick_ms)) {
                return -1;
            }
        } else if (strcmp(argv[i], "--logical-tick-sec") == 0) {
            if (!parse_int_arg(argv[++i], &config->logical_tick_seconds) ||
                config->logical_tick_seconds <= 0) {
                return -1;
            }
        } else if (strcmp(argv[i], "--run-dir") == 0) {
            snprintf(config->run_dir, sizeof(config->run_dir), "%s", argv[++i]);
        } else {
            fprintf(stderr, "unknown argument: %s\n", argv[i]);
            return -1;
        }
    }
    return 1;
}

int main(int argc, char **argv)
{
    Config config;
    int totals[PLAYER_COUNT][RESOURCE_COUNT] = {{0}};
    BrainStats gpu_stats = {0};
    BrainStats cpu_stats = {0};
    FILE *events;
    char events_path[PATH_BUF];
    int ticks;
    int tick;

    int parsed = parse_args(argc, argv, &config);
    if (parsed <= 0) {
        return parsed == 0 ? EXIT_SUCCESS : EXIT_FAILURE;
    }

    ticks = config.explicit_ticks > 0
        ? config.explicit_ticks
        : (config.minutes * 60) / config.logical_tick_seconds;
    if (ticks <= 0) {
        ticks = 1;
    }

    events = open_events_log(config.run_dir, events_path);

    printf("Catan2 LeafOS dual-brain benchmark\n");
    printf("duration=%d minute(s), ticks=%d, logical_tick=%ds, sleep=%dms\n",
           config.minutes, ticks, config.logical_tick_seconds, config.tick_ms);
    printf("gpu_brain=%s\n",
           getenv("CATAN2_GPU_BRAIN_CMD") ? getenv("CATAN2_GPU_BRAIN_CMD") : "not configured");
    printf("cpu_brain=%s\n",
           getenv("CATAN2_CPU_BRAIN_CMD") ? getenv("CATAN2_CPU_BRAIN_CMD") : "not configured");
    if (events != NULL) {
        printf("events=%s\n", events_path);
    }
    printf("\n");

    for (tick = 1; tick <= ticks; tick++) {
        int simulated_seconds = tick * config.logical_tick_seconds;
        int player;

        if (!config.quiet) {
            printf("tick %4d simulated_time=%6ds\n", tick, simulated_seconds);
        }

        for (player = 0; player < PLAYER_COUNT; player++) {
            HarvestChoice choice;
            int ok;

            if (player == AI_PLAYER) {
                ok = choose_dual_brain_harvest(
                    tick, simulated_seconds, config.run_dir,
                    totals, &gpu_stats, &cpu_stats, &choice);
            } else {
                ok = choose_policy_harvest(player, totals, "bot_policy", &choice);
            }

            if (!ok) {
                fprintf(stderr, "player %d has no legal choice at tick %d\n",
                        player, tick);
                continue;
            }

            apply_choice(totals, &choice, player);
            append_event(events, tick, simulated_seconds, player, &choice,
                         total_resources_for_player(totals, player));

            if (!config.quiet) {
                printf("  P%d %-18s tile=%2d %-6s prod=%d x%d +%d total=%d\n",
                       player,
                       choice.source,
                       choice.tile_id,
                       resource_name(choice.resource),
                       choice.productivity_level,
                       choice.building_multiplier,
                       choice.amount,
                       total_resources_for_player(totals, player));
            }
        }

        if (!config.quiet) {
            printf("\n");
        }
        if (config.tick_ms > 0 && tick < ticks) {
            sleep_ms(config.tick_ms);
        }
    }

    if (events != NULL) {
        fclose(events);
    }

    print_totals(totals);
    printf("\nBrain stats\n");
    printf("gpu configured=%d calls=%d valid=%d invalid=%d elapsed_ms=%ld\n",
           gpu_stats.configured, gpu_stats.calls, gpu_stats.valid,
           gpu_stats.invalid, gpu_stats.elapsed_ms);
    printf("cpu configured=%d calls=%d valid=%d invalid=%d elapsed_ms=%ld\n",
           cpu_stats.configured, cpu_stats.calls, cpu_stats.valid,
           cpu_stats.invalid, cpu_stats.elapsed_ms);

    write_summary(config.run_dir, ticks, config.minutes,
                  config.logical_tick_seconds, totals, &gpu_stats, &cpu_stats);
    return EXIT_SUCCESS;
}
