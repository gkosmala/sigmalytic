#!/usr/bin/env python3
"""
Sigmalytic V2 Step 2 — D3F.2 callback-safe Status Center locator v1.1.

Purpose:
    Locate callback-safe Status/Admin/Setup branches and classify leftover
    D3F.1B marker artifacts without mistaking dead source text for a live mount.

Mode:
    Read-only source inspection. No patch. No commit. No write.
"""
from __future__ import annotations

import argparse
import ast
import re
from pathlib import Path

PANEL_BUILDER = "_build_d3f1b_today_controlled_persistence_lifecycle_panel"
PANEL_MARKER = "d3f1b-today-entrypoint-controlled-persistence-mount"

STRICT_FORBIDDEN_TEXT = [
    "D3F.1B TODAY ENTRYPOINT INITIAL DASH LAYOUT MOUNT",
    "_build_d3f1b_today_controlled_persistence_lifecycle_panel(),",
]


def line_context(lines: list[str], line_number: int, radius: int = 6) -> str:
    start = max(1, line_number - radius)
    end = min(len(lines), line_number + radius)
    return "\n".join(f"{i:5}: {lines[i-1]}" for i in range(start, end + 1))


class BuilderCallVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.calls: list[int] = []

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if isinstance(func, ast.Name) and func.id == PANEL_BUILDER:
            self.calls.append(getattr(node, "lineno", -1))
        self.generic_visit(node)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default="frontend/sigmalytic_app_TODAY.py")
    args = parser.parse_args()

    path = Path(args.file)
    if not path.exists():
        raise SystemExit(f"FAIL: file not found: {path}")

    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    print("=" * 72)
    print("SIGMALYTIC V2 — D3F.2 CALLBACK-SAFE LOCATOR V1.1")
    print("MODE: READ-ONLY SOURCE INSPECTION")
    print("=" * 72)
    print(f"FILE: {path}")

    tree = ast.parse(text, filename=str(path))
    print("PASS: Python syntax parses clean.")

    if 'html.Main(id="main-content")' not in text:
        raise SystemExit('FAIL: main-content shell missing.')
    print("PASS: main-content shell exists.")

    for marker in STRICT_FORBIDDEN_TEXT:
        if marker in text:
            raise SystemExit(f"FAIL: strict forbidden global mount text exists: {marker}")
        print(f"PASS: strict forbidden global text absent: {marker}")

    visitor = BuilderCallVisitor()
    visitor.visit(tree)

    if visitor.calls:
        print("FAIL: D3F.1B panel builder is still called in source:")
        for line_number in visitor.calls:
            print("-" * 72)
            print(f"CALL at line {line_number}")
            print(line_context(lines, line_number))
        return 1

    print("PASS: no AST call to D3F.1B panel builder exists.")

    marker_hits = [
        idx for idx, line in enumerate(lines, start=1)
        if PANEL_MARKER in line
    ]

    if marker_hits:
        print("WARN: leftover D3F.1B marker text exists in source but no builder call was found.")
        print("CLASSIFICATION: ORPHAN/DEAD ARTIFACT UNLESS LATER PROVEN MOUNTED.")
        for line_number in marker_hits:
            print("-" * 72)
            print(f"MARKER TEXT at line {line_number}")
            print(line_context(lines, line_number))
    else:
        print("PASS: no leftover D3F.1B marker text exists.")

    print("\nCANDIDATE CALLBACK/TAB BRANCHES")
    patterns = [
        r"def\s+render_main\s*\(",
        r"def\s+.*status.*\(",
        r"def\s+.*setup.*\(",
        r"if\s+.*tab.*==\s*['\"]admin['\"]",
        r"elif\s+.*tab.*==\s*['\"]admin['\"]",
        r"if\s+.*tab.*==\s*['\"]setup['\"]",
        r"elif\s+.*tab.*==\s*['\"]setup['\"]",
        r"if\s+.*tab.*==\s*['\"]preferences['\"]",
        r"elif\s+.*tab.*==\s*['\"]preferences['\"]",
        r"status_center",
        r"build_status",
        r"main-content",
    ]

    found_any = False
    seen: set[int] = set()

    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            line_number = text[:match.start()].count("\n") + 1
            if line_number in seen:
                continue
            seen.add(line_number)
            print("-" * 72)
            print(f"MATCH: {pattern} at line {line_number}")
            print(line_context(lines, line_number))
            found_any = True

    if not found_any:
        print("WARN: no obvious safe Status/Admin callback branch was located.")
        return 1

    print("=" * 72)
    print("PASS: callback-safe candidates listed above.")
    print("PASS: no D3F.1B panel builder call is mounted in source.")
    print("NEXT: select only a callback-rendered branch for any future D3E.9 status card.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
