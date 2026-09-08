"""Source parity plus compiled branch fixture; never claims a live omission."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def function_body(text, signature):
    start = text.index("{", text.index(signature))
    # This specific upstream method contains no braces inside strings/comments.
    depth = 0
    for index in range(start, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    raise ValueError("unterminated audit function")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--namigator-root", type=Path, required=True)
    parser.add_argument("--executable", type=Path, required=True)
    args = parser.parse_args()
    source = args.namigator_root / "pathfind/Map.cpp"
    raw = source.read_bytes()
    original = function_body(raw.decode(), "bool Map::FindHeights(")
    fixture = function_body(
        (ROOT / "native/height_enumeration_audit/main.cpp").read_text(),
        "bool AuditMap::FindHeights(",
    )
    if original.replace("\r\n", "\n") != fixture:
        raise ValueError("audit fixture no longer matches installed source")
    completed = subprocess.run(
        [str(args.executable.resolve())],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    report = json.loads(completed.stdout)
    report["map_cpp_sha256"] = hashlib.sha256(raw).hexdigest()
    report["source_body_parity"] = True
    report["binary_sha256"] = hashlib.sha256(args.executable.read_bytes()).hexdigest()
    print(json.dumps(report))


if __name__ == "__main__":
    main()
