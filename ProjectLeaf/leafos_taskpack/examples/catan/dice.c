/*
 * dice.c -- Catan dice production, then RTS harvesting from coin data.
 *
 * The coin flip arrays below are streams of 0/1 values. Three flips encode
 * one die with rejection sampling:
 *
 *   bits 000..101 -> die values 1..6
 *   bits 110..111 -> rejected, read the next three flips
 *
 * Two independent streams produce two dice for the first half of the run. The
 * dice sum is then applied to a small Catan board model: matching numbered
 * tiles produce resources for adjacent settlements and cities.
 *
 * At the midpoint the rules change. Dice harvesting stops and the game becomes
 * an RTS-style economy: each bot chooses one harvest target per simulated time
 * tick. The same Catan number assignments become productivity divisions:
 *
 *   2/12 -> 1, 3/11 -> 2, 4/10 -> 3, 5/9 -> 4, 6/8 -> 5
 *
 * Harvest amount is 100 * productivity level, multiplied by settlement/city
 * output. This makes continual resource increase visible as a real-time
 * advancement problem against bots.
 */

#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>

#define ARRAY_LEN(a) (sizeof(a) / sizeof((a)[0]))
#define MAX_ADJACENT_TILES 3
#define PLAYER_COUNT 3
#define DICE_PHASE_TURNS 7
#define RTS_PHASE_TICKS 7
#define RTS_TICK_SECONDS 5
#define HARVEST_UNIT 100

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

typedef struct DiceRoll {
    int die_a;
    int die_b;
    int sum;
} DiceRoll;

typedef struct HarvestChoice {
    int tile_id;
    Resource resource;
    int number_assignment;
    int productivity_level;
    int building_multiplier;
    int amount;
} HarvestChoice;

static const char *const RESOURCE_NAMES[RESOURCE_COUNT] = {
    "brick", "lumber", "wool", "grain", "ore", "desert"
};

/*
 * These streams are grouped in threes for readability. Example:
 *   0,1,0 -> binary 2 -> die value 3
 */
static const int COIN_FLIPS_DIE_A[] = {
    0,1,0, 0,0,0, 0,1,1, 0,0,1, 1,0,0, 0,0,0, 0,0,1,
    1,0,1, 0,0,0, 1,0,1, 0,1,0, 0,1,1, 1,0,1, 0,0,0
};

static const int COIN_FLIPS_DIE_B[] = {
    1,0,0, 1,0,0, 1,0,0, 0,0,1, 1,0,0, 1,0,1, 0,1,0,
    1,0,0, 0,0,1, 1,0,1, 0,1,0, 0,1,1, 0,1,0, 0,0,0
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

static const int ROBBER_TILE_ID = 10;

static const int BOT_RESOURCE_PRIORITY[PLAYER_COUNT][RESOURCE_DESERT] = {
    { 2, 3, 1, 5, 5 },
    { 5, 5, 3, 2, 1 },
    { 3, 4, 4, 4, 2 }
};

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

static int next_die_from_coin_flips(
    const int *flips,
    size_t flip_count,
    size_t *cursor,
    const char *stream_name
)
{
    while (*cursor + 2 < flip_count) {
        int b0 = flips[*cursor + 0];
        int b1 = flips[*cursor + 1];
        int b2 = flips[*cursor + 2];
        int raw;

        *cursor += 3;

        if ((b0 != 0 && b0 != 1) || (b1 != 0 && b1 != 1) ||
            (b2 != 0 && b2 != 1)) {
            fprintf(stderr, "%s contains a non-coin value\n", stream_name);
            return 0;
        }

        raw = (b0 << 2) | (b1 << 1) | b2;
        if (raw < 6) {
            return raw + 1;
        }

        printf("  %s rejected bits %d%d%d; reading next three flips\n",
               stream_name, b0, b1, b2);
    }

    fprintf(stderr, "%s ran out of coin flips\n", stream_name);
    return 0;
}

static int next_roll(size_t *cursor_a, size_t *cursor_b, DiceRoll *roll)
{
    roll->die_a = next_die_from_coin_flips(
        COIN_FLIPS_DIE_A, ARRAY_LEN(COIN_FLIPS_DIE_A), cursor_a, "die A");
    roll->die_b = next_die_from_coin_flips(
        COIN_FLIPS_DIE_B, ARRAY_LEN(COIN_FLIPS_DIE_B), cursor_b, "die B");

    if (roll->die_a == 0 || roll->die_b == 0) {
        return 0;
    }

    roll->sum = roll->die_a + roll->die_b;
    return 1;
}

static void add_production_for_roll(
    int roll,
    int production[PLAYER_COUNT][RESOURCE_COUNT]
)
{
    size_t tile_index;

    if (roll == 7) {
        return;
    }

    for (tile_index = 0; tile_index < ARRAY_LEN(BOARD); tile_index++) {
        const Tile *tile = &BOARD[tile_index];
        size_t building_index;

        if (tile->number != roll || tile->resource == RESOURCE_DESERT) {
            continue;
        }
        if (tile->id == ROBBER_TILE_ID) {
            continue;
        }

        for (building_index = 0; building_index < ARRAY_LEN(BUILDINGS);
             building_index++) {
            const Building *building = &BUILDINGS[building_index];

            if (building_touches_tile(building, tile->id)) {
                production[building->player][tile->resource] +=
                    (int)building->kind;
            }
        }
    }
}

static int total_resources_for_player(
    int production[PLAYER_COUNT][RESOURCE_COUNT],
    int player
)
{
    int total = 0;
    size_t resource;

    for (resource = 0; resource < RESOURCE_DESERT; resource++) {
        total += production[player][resource];
    }
    return total;
}

static void print_roll_production(
    int roll,
    int production[PLAYER_COUNT][RESOURCE_COUNT]
)
{
    int player;

    if (roll == 7) {
        printf("  roll 7: robber activated; no production\n");
        return;
    }

    for (player = 0; player < PLAYER_COUNT; player++) {
        int printed_any = 0;
        size_t resource;

        printf("  P%d:", player);
        for (resource = 0; resource < RESOURCE_DESERT; resource++) {
            int amount = production[player][resource];

            if (amount > 0) {
                printf(" +%d %s", amount, resource_name((Resource)resource));
                printed_any = 1;
            }
        }
        if (!printed_any) {
            printf(" no production");
        }
        printf("\n");
    }
}

static int total_resource_count(
    int totals[PLAYER_COUNT][RESOURCE_COUNT],
    int player,
    Resource resource
)
{
    return totals[player][resource];
}

static void print_totals(
    const char *title,
    int totals[PLAYER_COUNT][RESOURCE_COUNT]
)
{
    int player;

    printf("\n%s\n", title);
    printf("player  brick  lumber  wool  grain  ore  total\n");
    printf("------  -----  ------  ----  -----  ---  -----\n");
    for (player = 0; player < PLAYER_COUNT; player++) {
        printf("P%-5d  %5d  %6d  %4d  %5d  %3d  %5d\n",
               player,
               totals[player][RESOURCE_BRICK],
               totals[player][RESOURCE_LUMBER],
               totals[player][RESOURCE_WOOL],
               totals[player][RESOURCE_GRAIN],
               totals[player][RESOURCE_ORE],
               total_resources_for_player(totals, player));
    }
}

static void print_midpoint_rule_change(void)
{
    printf("============================================================\n");
    printf("MIDPOINT RULE CHANGE\n");
    printf("Classic Catan dice harvesting stops here.\n");
    printf("New RTS rule: bots choose harvest targets every %d seconds.\n",
           RTS_TICK_SECONDS);
    printf("Harvest = %d * productivity level * settlement/city output.\n",
           HARVEST_UNIT);
    printf("The same 2..12 board assignments now define productivity.\n");
    printf("============================================================\n\n");
}

static void accumulate_totals(
    int totals[PLAYER_COUNT][RESOURCE_COUNT],
    int production[PLAYER_COUNT][RESOURCE_COUNT]
)
{
    int player;

    for (player = 0; player < PLAYER_COUNT; player++) {
        size_t resource;

        for (resource = 0; resource < RESOURCE_DESERT; resource++) {
            totals[player][resource] += production[player][resource];
        }
    }
}

static int choose_harvest_for_player(
    int player,
    int totals[PLAYER_COUNT][RESOURCE_COUNT],
    HarvestChoice *choice
)
{
    int best_score = -1;
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

            if (tile == NULL || tile->resource == RESOURCE_DESERT) {
                continue;
            }
            if (tile->id == ROBBER_TILE_ID) {
                continue;
            }

            productivity = productivity_level_for_number(tile->number);
            if (productivity <= 0) {
                continue;
            }

            amount = HARVEST_UNIT * productivity * (int)building->kind;
            priority = BOT_RESOURCE_PRIORITY[player][tile->resource];
            stock_penalty = total_resource_count(totals, player, tile->resource);
            score = priority * 100 + amount - stock_penalty;

            if (score > best_score) {
                best_score = score;
                choice->tile_id = tile->id;
                choice->resource = tile->resource;
                choice->number_assignment = tile->number;
                choice->productivity_level = productivity;
                choice->building_multiplier = (int)building->kind;
                choice->amount = amount;
            }
        }
    }

    return best_score >= 0;
}

static void run_rts_tick(
    int tick,
    int elapsed_seconds,
    int totals[PLAYER_COUNT][RESOURCE_COUNT],
    int rts_totals[PLAYER_COUNT][RESOURCE_COUNT]
)
{
    int player;

    printf("RTS tick %2d  simulated_time=%3ds\n", tick, elapsed_seconds);

    for (player = 0; player < PLAYER_COUNT; player++) {
        HarvestChoice choice;

        if (!choose_harvest_for_player(player, totals, &choice)) {
            printf("  P%d has no legal harvest target\n", player);
            continue;
        }

        totals[player][choice.resource] += choice.amount;
        rts_totals[player][choice.resource] += choice.amount;

        printf("  P%d chooses tile %d %-6s assignment=%2d productivity=%d",
               player,
               choice.tile_id,
               resource_name(choice.resource),
               choice.number_assignment,
               choice.productivity_level);
        printf(" output=x%d -> +%d %s\n",
               choice.building_multiplier,
               choice.amount,
               resource_name(choice.resource));
    }
    printf("\n");
}

int main(void)
{
    size_t cursor_a = 0;
    size_t cursor_b = 0;
    int totals[PLAYER_COUNT][RESOURCE_COUNT] = {{0}};
    int dice_totals[PLAYER_COUNT][RESOURCE_COUNT] = {{0}};
    int rts_totals[PLAYER_COUNT][RESOURCE_COUNT] = {{0}};
    int turn;
    int tick;

    printf("Catan production from coin-flip dice data\n");
    printf("Robber tile id: %d\n\n", ROBBER_TILE_ID);

    for (turn = 1; turn <= DICE_PHASE_TURNS; turn++) {
        DiceRoll roll;
        int production[PLAYER_COUNT][RESOURCE_COUNT] = {{0}};

        if (!next_roll(&cursor_a, &cursor_b, &roll)) {
            break;
        }

        add_production_for_roll(roll.sum, production);
        accumulate_totals(totals, production);
        accumulate_totals(dice_totals, production);

        printf("Turn %2d: die A=%d die B=%d roll=%d\n",
               turn, roll.die_a, roll.die_b, roll.sum);
        print_roll_production(roll.sum, production);
        printf("\n");
    }

    print_totals("Dice-phase production totals", dice_totals);
    print_midpoint_rule_change();

    for (tick = 1; tick <= RTS_PHASE_TICKS; tick++) {
        run_rts_tick(tick, tick * RTS_TICK_SECONDS, totals, rts_totals);
    }

    print_totals("RTS harvest totals", rts_totals);
    print_totals("Combined final production totals", totals);
    return EXIT_SUCCESS;
}
