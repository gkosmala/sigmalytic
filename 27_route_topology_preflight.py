#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any

REPORT = Path("audit_step27_route_topology_preflight.json")

TARGET_FILES = [
    Path("backend/campaign_api.py"),
    Path("backend/main.py"),
]

ROUTE_METHODS = {"get", "post", "put", "delete", "patch"}


def read(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8-sig", errors="replace")


def syntax_result(path: Path) -> dict[str, Any]:
    text = read(path)
    if not text:
        return {"exists": False, "ok": False, "error": "file missing or empty"}

    try:
        ast.parse(text, filename=str(path))
        return {"exists": True, "ok": True, "error": None}
    except SyntaxError as exc:
        return {
            "exists": True,
            "ok": False,
            "error": f"{exc.msg} at line {exc.lineno}",
        }


def decorator_name(node: ast.AST) -> str:
    if isinstance(node, ast.Call):
        return decorator_name(node.func)

    if isinstance(node, ast.Attribute):
        return decorator_name(node.value) + "." + node.attr

    if isinstance(node, ast.Name):
        return node.id

    return ""


def first_string_arg(node: ast.AST) -> str | None:
    if not isinstance(node, ast.Call):
        return None

    if not node.args:
        return None

    first = node.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.value

    return None


def extract_router_assignments(tree: ast.AST) -> list[dict[str, Any]]:
    routers: list[dict[str, Any]] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue

        value = node.value
        if not isinstance(value, ast.Call):
            continue

        func_name = decorator_name(value.func)
        if not func_name.endswith("APIRouter"):
            continue

        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue

            prefix = ""
            tags: list[str] = []

            for kw in value.keywords:
                if kw.arg == "prefix" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                    prefix = kw.value.value

                if kw.arg == "tags" and isinstance(kw.value, (ast.List, ast.Tuple)):
                    for elt in kw.value.elts:
                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                            tags.append(elt.value)

            routers.append({
                "router_name": target.id,
                "line": getattr(node, "lineno", None),
                "prefix": prefix,
                "tags": tags,
            })

    return routers


def extract_routes(tree: ast.AST) -> list[dict[str, Any]]:
    routes: list[dict[str, Any]] = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        for dec in node.decorator_list:
            dec_name = decorator_name(dec)
            parts = dec_name.split(".")
            if len(parts) < 2:
                continue

            method = parts[-1]
            router_name = parts[-2]

            if method not in ROUTE_METHODS:
                continue

            path_arg = first_string_arg(dec)

            routes.append({
                "function": node.name,
                "line": getattr(node, "lineno", None),
                "router_name": router_name,
                "method": method.upper(),
                "path": path_arg,
                "decorator": dec_name,
            })

    return routes


def extract_include_router_calls(tree: ast.AST) -> list[dict[str, Any]]:
    includes: list[dict[str, Any]] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        func_name = decorator_name(node.func)
        if not func_name.endswith("include_router"):
            continue

        router_expr = None
        if node.args:
            router_expr = ast.unparse(node.args[0]) if hasattr(ast, "unparse") else None

        prefix = None
        for kw in node.keywords:
            if kw.arg == "prefix" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                prefix = kw.value.value

        includes.append({
            "line": getattr(node, "lineno", None),
            "call": ast.unparse(node) if hasattr(ast, "unparse") else func_name,
            "router_expr": router_expr,
            "prefix": prefix,
        })

    return includes


def inspect_file(path: Path) -> dict[str, Any]:
    text = read(path)
    syntax = syntax_result(path)

    result: dict[str, Any] = {
        "path": str(path),
        "syntax": syntax,
        "routers": [],
        "routes": [],
        "include_router_calls": [],
        "route_marker_present": "STEP26_CAMPAIGN_PIPELINE_READ_ONLY_VALIDATION_SNAPSHOT_ENDPOINT" in text,
        "snapshot_route_text_present": "pipeline-validation-snapshot" in text,
    }

    if not syntax["ok"]:
        return result

    tree = ast.parse(text, filename=str(path))
    result["routers"] = extract_router_assignments(tree)
    result["routes"] = extract_routes(tree)
    result["include_router_calls"] = extract_include_router_calls(tree)

    return result


def choose_candidate(campaign_api_info: dict[str, Any]) -> dict[str, Any]:
    routers = campaign_api_info.get("routers") or []
    routes = campaign_api_info.get("routes") or []

    if routers:
        router_name = routers[0]["router_name"]
        prefix = routers[0].get("prefix") or ""
    else:
        route_router_names = [route.get("router_name") for route in routes if route.get("router_name")]
        router_name = route_router_names[0] if route_router_names else None
        prefix = ""

    existing_paths = [route.get("path") for route in routes if route.get("path")]
    candidate_path = "/read-only/pipeline-validation-snapshot"

    return {
        "router_name": router_name,
        "router_prefix": prefix,
        "candidate_decorator": f"@{router_name}.get(\"{candidate_path}\")" if router_name else None,
        "candidate_path": candidate_path,
        "existing_route_count": len(existing_paths),
        "candidate_path_already_exists": candidate_path in existing_paths,
        "safe_to_patch": bool(router_name) and candidate_path not in existing_paths,
    }


def main() -> int:
    print("=" * 72)
    print("SIGMALYTIC V2 — STEP 27 ROUTE TOPOLOGY PREFLIGHT")
    print("MODE: LOCAL READ-ONLY ROUTE AUDIT / NO PATCH / NO MUTATION")
    print("=" * 72)

    failures: list[str] = []

    inspected = [inspect_file(path) for path in TARGET_FILES]

    for item in inspected:
        syntax = item["syntax"]
        if syntax["ok"]:
            print("PASS: syntax clean:", item["path"])
        else:
            failures.append(f"syntax failure or missing file: {item['path']}: {syntax['error']}")

    campaign_api_info = inspected[0]
    candidate = choose_candidate(campaign_api_info)

    if not candidate["router_name"]:
        failures.append("could not identify a router name in backend/campaign_api.py")

    if candidate["candidate_path_already_exists"]:
        failures.append("candidate pipeline-validation-snapshot path already exists")

    if campaign_api_info.get("route_marker_present"):
        failures.append("old failed Step 26 route marker still present in backend/campaign_api.py")

    report = {
        "mode": "LOCAL_READ_ONLY_ROUTE_TOPOLOGY_AUDIT_NO_PATCH_NO_MUTATION",
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "inspected_files": inspected,
        "candidate_route": candidate,
        "doctrine": {
            "read_only_audit": True,
            "no_source_patch": True,
            "no_nightly_run": True,
            "no_alpaca_call": True,
            "no_supabase_write": True,
            "no_campaign_mutation": True,
            "no_d3d": True,
            "no_operator_control_confirmation": True,
            "no_trade_signal": True,
            "no_stripe": True,
        },
    }

    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("Report written:", REPORT)

    print("\nCANDIDATE ROUTE")
    for key, value in candidate.items():
        print(f"{key}: {value}")

    print("\nCAMPAIGN API ROUTERS")
    for router in campaign_api_info.get("routers") or []:
        print(f"ROUTER: name={router['router_name']} prefix={router['prefix']} line={router['line']}")

    print("\nCAMPAIGN API EXISTING ROUTES")
    for route in (campaign_api_info.get("routes") or [])[:120]:
        print(
            f"ROUTE: {route['method']} {route['path']} "
            f"router={route['router_name']} function={route['function']} line={route['line']}"
        )

    if failures:
        print("\nFAILURES")
        for failure in failures:
            print("FAIL:", failure)
        print("=" * 72)
        print("FAIL: STEP 27 ROUTE TOPOLOGY PREFLIGHT FAILED")
        print("=" * 72)
        return 1

    print("=" * 72)
    print("PASS: STEP 27 COMPLETE — ROUTE TOPOLOGY PREFLIGHT PASSED")
    print("PASS: safe candidate route identified; no source patch performed.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
