from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "research" / "recovered" / "sequential_portfolio_stage2.py"
OUT = ROOT / "research" / "results" / "stage2_api"
OUT.mkdir(parents=True, exist_ok=True)

text = SRC.read_text(encoding="utf-8")
tree = ast.parse(text)

classes = []
functions = []
arguments = []
for node in ast.walk(tree):
    if isinstance(node, ast.ClassDef):
        fields = []
        for child in node.body:
            if isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
                fields.append(child.target.id)
        classes.append({"name": node.name, "fields": fields, "line": node.lineno})
    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        functions.append({
            "name": node.name,
            "args": [a.arg for a in node.args.args],
            "line": node.lineno,
            "end_line": getattr(node, "end_lineno", None),
        })
    elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "add_argument":
        opts = []
        for arg in node.args:
            try:
                opts.append(ast.literal_eval(arg))
            except Exception:
                opts.append(ast.unparse(arg))
        kwargs = {}
        for kw in node.keywords:
            try:
                kwargs[kw.arg] = ast.literal_eval(kw.value)
            except Exception:
                kwargs[kw.arg] = ast.unparse(kw.value)
        arguments.append({"options": opts, "kwargs": kwargs, "line": node.lineno})

meta = {"classes": classes, "functions": functions, "arguments": arguments}
(OUT / "api.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

lines = ["# Recovered sequential stage-two API", "", "## Classes", "", "```json", json.dumps(classes, indent=2), "```", "", "## Functions", "", "```json", json.dumps(functions, indent=2), "```", "", "## CLI", "", "```json", json.dumps(arguments, indent=2), "```"]
(OUT / "API.md").write_text("\n".join(lines), encoding="utf-8")
print(json.dumps(meta, indent=2))
