// 测试文件
#define SINGLE_LINE_MACRO 100

#define MULTILINE_MACRO \
    { \
        1, 2, 3 \
    }

#define BUILD_BF_MAP_TYPE_MAP         \
{                                     \
    {"Invalid",     bfmtInvalid},     \
    {"BattleField", bfmtBattleField}, \
    {"KillRush",    bfmtKillRush},    \
    {"TongLeague",  bfmtTongLeague},  \
    {"ArenaTower",  bfmtArenaTower},  \
}

#define ANOTHER_MACRO 200
