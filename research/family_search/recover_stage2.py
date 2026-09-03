from __future__ import annotations

import ast
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGET = "research/family_search/sequential_portfolio_stage2.py"
OUT = ROOT / "research" / "recovered"
OUT.mkdir(parents=True, exist_ok=True)

commits = subprocess.check_output(
    ["git", "log", "--format=%H", "--all", "--", TARGET],
    cwd=ROOT,
    text=True,
).splitlines()

report = []
selected = None
for commit in commits:
    try:
        source = subprocess.check_output(["git", "show", f"{commit}:{TARGET}"], cwd=ROOT)
    except subprocess.CalledProcessError as exc:
        report.append({"commit": commit, "status": "missing", "error": str(exc)})
        continue
    try:
        text = source.decode("utf-8")
    except UnicodeDecodeError as exc:
        report.append({"commit": commit, "status": "non_utf8", "error": str(exc), "size": len(source)})
        continue
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        report.append({"commit": commit, "status": "syntax_error", "error": str(exc), "size": len(source)})
        continue
    functions = [n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    classes = [n.name for n in tree.body if isinstance(n, ast.ClassDef)]
    report.append({"commit": commit, "status": "valid", "size": len(source), "functions": functions, "classes": classes})
    selected = (commit, text)
    break

if selected is None:
    raise SystemExit("No syntactically valid historical stage-two implementation found")

commit, text = selected
(OUT / "sequential_portfolio_stage2.py").write_text(text, encoding="utf-8")
(OUT / "recovery_report.json").write_text(json.dumps({"selected_commit": commit, "history": report}, indent=2), encoding="utf-8")
print(json.dumps(report[0], indent=2))
