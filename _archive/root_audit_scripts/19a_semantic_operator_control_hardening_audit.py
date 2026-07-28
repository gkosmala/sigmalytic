#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(".")
REPORT = Path("audit_step19a_semantic_operator_control_hardening_audit.json")

EXCLUDED_DIRS = {
    ".git", ".venv", "venv", "env", "__pycache__",
    ".mypy_cache", ".pytest_cache", "node_modules",
}

PRODUCTION_DIRS = {"backend", "frontend"}
AUDIT_PREFIX_RE = re.compile(r"^\d{2}[a-zA-Z]?_")

CONFIRMATION_TARGET_TERMS = [
    "operator_control_confirmed",
    "d3d_production_confirmed_operator_control",
    "control_confirmed",
    "operator_confirmed",
    "composite_operator_control_confirmed",
]

OPERATOR_CONTEXT_TERMS = [
    "operator_control",
    "operator_dominance",
    "composite_operator_control",
    "d3d_production_confirmed_operator_control",
]

FORBIDDEN_DERIVATION_TERMS = [
    "score",
    "rank",
    "tier",
    "probability",
    "expected_return",
    "edge",
    "gamma",
    "gex",
    "outcome",
    "target",
    "trade_signal",
    "survival_score",
    "campaign_score",
    "composite_score",
    "master_score",
]

EVIDENCE_ALIASES = {
    "tested_supply_exhaustion": [
        "tested_supply_exhaustion",
        "tested supply exhaustion",
        "supply_exhaustion",
        "supply exhaustion",
    ],
    "active_demand_validation": [
        "active_demand_validation",
        "active demand validation",
        "active demand/support validation",
        "active_demand",
    ],
    "support_validation": [
        "support_validation",
        "support validation",
        "active demand/support validation",
    ],
    "structural_location": [
        "structural_location",
        "structural location",
        "structurally meaningful location",
    ],
    "absence_of_contrary_failure": [
        "absence_of_contrary_failure",
        "absence of contrary failure",
        "contrary failure",
    ],
}


def should_scan(path: Path) -> bool:
    if set(path.parts) & EXCLUDED_DIRS:
        return False
    if path.suffix.lower() != ".py":
        return False
    if AUDIT_PREFIX_RE.match(path.name):
        return False
    if not path.parts or path.parts[0] not in PRODUCTION_DIRS:
        return False
    return True


def safe_read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


def add_term(terms: set[str], value: Any) -> None:
    if isinstance(value, str) and value:
        terms.add(value.lower())


def semantic_terms(node: ast.AST | None, include_string_keys: bool = True) -> set[str]:
    terms: set[str] = set()

    if node is None:
        return terms

    def visit(n: ast.AST | None) -> None:
        if n is None:
            return

        if isinstance(n, ast.Name):
            add_term(terms, n.id)
            return

        if isinstance(n, ast.Attribute):
            add_term(terms, n.attr)
            visit(n.value)
            return

        if isinstance(n, ast.keyword):
            add_term(terms, n.arg)
            visit(n.value)
            return

        if isinstance(n, ast.Subscript):
            visit(n.value)
            if include_string_keys and isinstance(n.slice, ast.Constant) and isinstance(n.slice.value, str):
                add_term(terms, n.slice.value)
            else:
                visit(n.slice)
            return

        if isinstance(n, ast.Dict):
            for key in n.keys:
                if include_string_keys and isinstance(key, ast.Constant) and isinstance(key.value, str):
                    add_term(terms, key.value)
                else:
                    visit(key)
            for value in n.values:
                visit(value)
            return

        if isinstance(n, ast.Constant):
            return

        for child in ast.iter_child_nodes(n):
            visit(child)

    visit(node)
    return terms


def contains_any(terms: set[str], needles: list[str]) -> bool:
    joined = " ".join(sorted(terms))
    return any(needle.lower() in joined for needle in needles)


def is_confirmation_target(node: ast.AST | None) -> bool:
    return contains_any(semantic_terms(node), CONFIRMATION_TARGET_TERMS)


def has_forbidden_derivation(node: ast.AST | None) -> bool:
    return contains_any(semantic_terms(node), FORBIDDEN_DERIVATION_TERMS)


def has_operator_context(node: ast.AST | None) -> bool:
    return contains_any(semantic_terms(node), OPERATOR_CONTEXT_TERMS)


def explicit_false_or_empty(node: ast.AST | None) -> bool:
    if isinstance(node, ast.Constant) and node.value is False:
        return True
    if isinstance(node, ast.List) and len(node.elts) == 0:
        return True
    if isinstance(node, ast.Tuple) and len(node.elts) == 0:
        return True
    if isinstance(node, ast.Set) and len(node.elts) == 0:
        return True
    if isinstance(node, ast.Dict) and len(node.keys) == 0:
        return True
    return False


def source_line(lines: list[str], node: ast.AST) -> str:
    line_no = getattr(node, "lineno", 0)
    if 1 <= line_no <= len(lines):
        return lines[line_no - 1].strip()
    return ""


class Visitor(ast.NodeVisitor):
    def __init__(self, path: Path, lines: list[str]) -> None:
        self.path = path
        self.lines = lines
        self.condition_stack: list[ast.AST] = []
        self.blockers: list[dict[str, Any]] = []
        self.reviews: list[dict[str, Any]] = []

    def finding(self, severity: str, category: str, node: ast.AST) -> dict[str, Any]:
        return {
            "severity": severity,
            "category": category,
            "path": str(self.path),
            "line": getattr(node, "lineno", None),
            "text": source_line(self.lines, node),
        }

    def condition_has_forbidden(self) -> bool:
        return any(has_forbidden_derivation(test) for test in self.condition_stack)

    def check_assignment(self, node: ast.AST, targets: list[ast.AST], value: ast.AST | None) -> None:
        for target in targets:
            if not is_confirmation_target(target):
                continue

            if explicit_false_or_empty(value):
                self.reviews.append(self.finding("REVIEW", "CONFIRMATION_TARGET_EXPLICITLY_FALSE_OR_EMPTY", node))
                continue

            if has_forbidden_derivation(value) or self.condition_has_forbidden():
                self.blockers.append(self.finding("BLOCKER", "EXECUTABLE_SCORE_DERIVED_OPERATOR_CONTROL_CONFIRMATION", node))
            else:
                self.reviews.append(self.finding("REVIEW", "EXECUTABLE_OPERATOR_CONTROL_CONFIRMATION_TARGET_REVIEW", node))

    def visit_Assign(self, node: ast.Assign) -> None:
        self.check_assignment(node, list(node.targets), node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self.check_assignment(node, [node.target], node.value)
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self.check_assignment(node, [node.target], node.value)
        self.generic_visit(node)

    def visit_If(self, node: ast.If) -> None:
        if has_operator_context(node.test) and has_forbidden_derivation(node.test):
            self.reviews.append(self.finding("REVIEW", "OPERATOR_CONDITION_REFERENCES_SCORE_OR_GAMMA_DIAGNOSTIC_REVIEW", node))

        self.condition_stack.append(node.test)
        for item in node.body:
            self.visit(item)
        self.condition_stack.pop()

        for item in node.orelse:
            self.visit(item)

    def visit_Call(self, node: ast.Call) -> None:
        func_terms = semantic_terms(node.func)

        confirm_like = contains_any(func_terms, [
            "confirm_operator_control",
            "set_operator_control_confirmed",
            "authorize_d3d",
            "execute_d3d",
        ])

        if confirm_like:
            arg_forbidden = any(has_forbidden_derivation(arg) for arg in node.args)
            kw_forbidden = any(has_forbidden_derivation(kw.value) for kw in node.keywords)

            if arg_forbidden or kw_forbidden or self.condition_has_forbidden():
                self.blockers.append(self.finding("BLOCKER", "CALL_MAY_CONFIRM_OPERATOR_CONTROL_FROM_FORBIDDEN_DERIVATION", node))
            else:
                self.reviews.append(self.finding("REVIEW", "CALL_MAY_CONFIRM_OPERATOR_CONTROL_REVIEW", node))

        self.generic_visit(node)


def evidence_presence(all_text: str) -> dict[str, bool]:
    lower = all_text.lower()
    return {
        canonical: any(alias.lower() in lower for alias in aliases)
        for canonical, aliases in EVIDENCE_ALIASES.items()
    }


def main() -> int:
    print("=" * 72)
    print("SIGMALYTIC V2 — STEP 19A SEMANTIC OPERATOR-CONTROL HARDENING AUDIT")
    print("MODE: LOCAL AST AUDIT / NO PRODUCTION MUTATION")
    print("=" * 72)

    files = sorted(path for path in ROOT.rglob("*.py") if should_scan(path))
    blockers: list[dict[str, Any]] = []
    reviews: list[dict[str, Any]] = []
    syntax_failures: list[dict[str, str]] = []
    full_text: list[str] = []

    for path in files:
        text = safe_read(path)
        full_text.append(text)
        lines = text.splitlines()

        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError as exc:
            syntax_failures.append({"path": str(path), "error": f"{exc.msg} at line {exc.lineno}"})
            continue

        visitor = Visitor(path, lines)
        visitor.visit(tree)
        blockers.extend(visitor.blockers)
        reviews.extend(visitor.reviews)

    evidence = evidence_presence("\n".join(full_text))
    missing_evidence_terms = [term for term, present in evidence.items() if not present]

    report = {
        "mode": "LOCAL_AST_AUDIT_NO_PRODUCTION_MUTATION",
        "status": "PASS" if not blockers and not syntax_failures else "FAIL",
        "summary": {
            "files_scanned": len(files),
            "blockers": len(blockers),
            "reviews": len(reviews),
            "syntax_failures": len(syntax_failures),
            "missing_evidence_terms": missing_evidence_terms,
        },
        "evidence_presence": evidence,
        "doctrine": {
            "operator_control_is_evidence_not_score": True,
            "text_only_doctrine_strings_not_blockers": True,
            "no_supabase_write": True,
            "no_campaign_mutation": True,
            "no_d3d": True,
            "no_operator_control_confirmation": True,
            "no_trade_signal": True,
            "no_stripe": True,
        },
        "syntax_failures": syntax_failures,
        "blockers": blockers,
        "reviews": reviews[:250],
    }

    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"Files scanned: {len(files)}")
    print(f"Blockers: {len(blockers)}")
    print(f"Reviews: {len(reviews)}")
    print(f"Syntax failures: {len(syntax_failures)}")
    print(f"Evidence presence: {evidence}")
    print(f"Missing evidence terms: {missing_evidence_terms}")
    print(f"Report written: {REPORT}")

    if blockers:
        print("\nBLOCKERS")
        for finding in blockers[:100]:
            print(f"BLOCKER: {finding['path']}:{finding['line']} — {finding['category']} — {finding['text']}")

    if reviews:
        print("\nREVIEWS")
        for finding in reviews[:100]:
            print(f"REVIEW: {finding['path']}:{finding['line']} — {finding['category']} — {finding['text']}")

    if blockers or syntax_failures:
        print("=" * 72)
        print("FAIL: STEP 19A FOUND EXECUTABLE OPERATOR-CONTROL HARDENING BLOCKERS")
        print("SEND FULL OUTPUT")
        print("=" * 72)
        return 1

    print("=" * 72)
    print("PASS: STEP 19A COMPLETE — NO EXECUTABLE SCORE-DERIVED OPERATOR-CONTROL CONFIRMATION PATH FOUND")
    print("PASS: doctrine/warning strings were not treated as executable blockers.")
    print("PASS: proceed to operator-control evidence contract hardening.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
