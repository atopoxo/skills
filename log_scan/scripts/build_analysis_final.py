#!/usr/bin/env python
"""Run parts 1 and 2, merge, and write temporary_else_analysis.json"""
import json
import os
import sys

# Run part 1 to build the base output
import build_analysis_part1
output = build_analysis_part1.output

# Add part 2 entries
import build_analysis_part2
output["c/c++"].extend(build_analysis_part2.cc_remaining)

# Validate output
total = (
    len(output["tab_load"]) +
    len(output["lua_call"]) +
    len(output["lua"]) +
    len(output["c/c++"])
)
print(f"Total entries: {total}")
print(f"  tab_load: {len(output['tab_load'])}")
print(f"  lua_call: {len(output['lua_call'])}")
print(f"  lua: {len(output['lua'])}")
print(f"  c/c++: {len(output['c/c++'])}")

# Validate required fields per category
def validate_category(items, category, required_fields):
    for i, item in enumerate(items):
        missing = [f for f in required_fields if f not in item]
        if missing:
            print(f"WARNING: {category}[{i}] missing fields: {missing}")
        # Validate wrecker_info not empty
        if "wrecker_info" in item and len(item["wrecker_info"]) == 0:
            print(f"WARNING: {category}[{i}] has empty wrecker_info!")
        # Validate source=llm => need_analyse=true
        if item.get("source") == "llm" and item.get("need_analyse") == False:
            print(f"WARNING: {category}[{i}] source=llm but need_analyse=false!")

lua_required = ["source", "reference_doc", "count", "encoding", "file_path", "line_num",
                "select_content", "error", "reference", "need_analyse", "suggestion",
                "wrecker_info", "wrecker_index"]
cc_required = lua_required  # same required fields for c/c++ and lua

validate_category(output["lua"], "lua", lua_required)
validate_category(output["c/c++"], "c/c++", cc_required)

# Write output
out_dir = r"Y:\AI\skills\log_scan\scripts\.results\final_result_2026_05_16_11_33_04"
os.makedirs(out_dir, exist_ok=True)
out_path = os.path.join(out_dir, "temporary_else_analysis.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"\nWritten to: {out_path}")
print(f"File size: {os.path.getsize(out_path)} bytes")
