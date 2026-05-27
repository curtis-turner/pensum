#!/usr/bin/env python3
import json
import sys

data = json.load(sys.stdin)
command = data.get("tool_input", {}).get("command", "")

redirects = {
    "pip install": "uv add",
    "pip3 install": "uv add",
    "pip uninstall": "uv remove",
    "pip3 uninstall": "uv remove",
    "python -m pip": "uv add / uv remove",
    "python3 -m pip": "uv add / uv remove",
    "python -m pytest": "uv run pytest",
    "python3 -m pytest": "uv run pytest",
}

for pattern, replacement in redirects.items():
    if pattern in command:
        print(f"Blocked: '{pattern}' detected. Use '{replacement}' instead.", file=sys.stderr)
        sys.exit(2)

bare_prefixes = ("pip ", "pip3 ", "python ", "python3 ", "pytest ", "ruff ")
for bare in bare_prefixes:
    if command.startswith(bare) and not command.startswith("uv run"):
        print(f"Blocked: bare '{bare.strip()}' command. Use uv (e.g. 'uv add', 'uv run').", file=sys.stderr)
        sys.exit(2)

bare_exact = {"pip", "pip3", "python", "python3", "pytest", "ruff"}
if command.strip() in bare_exact:
    print(f"Blocked: use 'uv run {command.strip()}' instead.", file=sys.stderr)
    sys.exit(2)
