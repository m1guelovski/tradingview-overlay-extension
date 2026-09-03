from __future__ import annotations

import ast
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGET = "research/family_search/sequential_portfolio_stage2.py"
OUT = ROOT / "research" / "recovered"
OUT.mkdir(parents=True, exist_ok=True)

commits = subprocess.check_output(["git", "log", "--format=%H", "--all", "--", TARGET], cwd=ROOT, text=True).splitlines()
report = []
selected = None
for commit in commits:
    try:
        source = subprocess.check_output(["git", "show", f"{commit}:{TARGET}"], cwd=ROOT)
        text = source.decode("utf-8")
        tree = ast.parse(text)
    except Exception as exc:
        report.append({"commit": commit, "status": "invalid", "error": repr(exc)})
        continue
    functions = [n.name for n in tree.body if isinstance(n, ast.FunctionDef)]
    classes = [n.name for n in tree.body if isinstance(n, ast.ClassDef)]
    report.append({"commit": commit, "status": "valid", "size": len(source), "functions": functions, "classes": classes})
    selected = (commit, text)
    break
if selected is None:
    raise SystemExit("No valid historical implementation found")
commit, text = selected
(OUT / "sequential_portfolio_stage2.py").write_text(text, encoding="utf-8")

workflow_hits = []
for wf in sorted((ROOT / ".github" / "workflows").glob("*.y*ml")):
    body = wf.read_text(encoding="utf-8", errors="ignore")
    if "sequential_portfolio_stage2.py" in body:
        workflow_hits.append({"path": str(wf.relative_to(ROOT)), "content": body})
        (OUT / f"workflow__{wf.name}").write_text(body, encoding="utf-8")

(OUT / "recovery_report_v2.json").write_text(json.dumps({
    "selected_commit": commit,
    "history": report,
    "workflow_hits": [x["path"] for x in workflow_hits],
}, indent=2), encoding="utf-8")
print(json.dumps({"selected_commit": commit, "workflow_hits": [x["path"] for x in workflow_hits]}, indent=2))
