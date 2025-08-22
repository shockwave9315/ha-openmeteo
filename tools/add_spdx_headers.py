#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# SPDX-License-Identifier: Apache-2.0

import os, sys, io

HEADER = "# SPDX-License-Identifier: Apache-2.0\n"

def process_file(path: str):
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    # if header already present, skip
    if "SPDX-License-Identifier: Apache-2.0" in content.splitlines()[:5]:
        return False
    # insert after shebang if present, else at top
    lines = content.splitlines(True)
    if lines and lines[0].startswith("#!"):
        lines.insert(1, HEADER)
    else:
        lines.insert(0, HEADER)
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    return True

def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    changed = 0
    for dirpath, _, filenames in os.walk(root):
        for name in filenames:
            if name.endswith(".py"):
                p = os.path.join(dirpath, name)
                try:
                    if process_file(p):
                        changed += 1
                        print(f"added SPDX to: {p}")
                except Exception as e:
                    print(f"skip {p}: {e}")
    print(f"done. changed {changed} files.")

if __name__ == "__main__":
    main()
