#!/usr/bin/env python3
"""
Terminal look for nas_to_msh.py 

"""

import os
import sys

RULE = "-" * 79

# --------------------------------------------------------------------------
# Colors (off when output is piped or logged)
# --------------------------------------------------------------------------
if os.name == "nt":
    os.system("")          # enables ANSI colors in the Windows console

if sys.stdout.isatty():
    RED, GREEN, ORANGE = "\033[91m", "\033[92m", "\033[93m"
    GRAY, NC = "\033[37m", "\033[0m"
else:
    RED = GREEN = ORANGE = GRAY = NC = ""


# --------------------------------------------------------------------------
# Lines
# --------------------------------------------------------------------------
def step(msg):   print(f"   - {msg}")
def good(msg):   print(f"   - {GREEN}{msg}{NC}")
def warn(msg):   print(f"   - {ORANGE}{msg}{NC}")
def fail(msg):   print(f"   - {RED}{msg}{NC}")
def detail(msg): print(f"       {msg}")
def hint(msg):   print(f"     {ORANGE}{msg}{NC}")   # continues a warning, like in the bash tutorials


def section(title):
    print(f"\n{title}\n{RULE}\n")


# --------------------------------------------------------------------------
# Banner / end note
# --------------------------------------------------------------------------
def banner(nas_file, gmsh_version):
    print(f"\n{RULE}")
    print(f"{GRAY}Script{NC}         :: nas_to_msh.py")
    print(f"{GRAY}Gmsh version{NC}   :: {gmsh_version}")
    print(f"{GRAY}Input file{NC}     :: {nas_file}")
    print(f"{RULE}\n\n")
    print(f"{GREEN}Convert a Nastran mesh to a named MSH 2.2 file "
          f"(for gmshToFoam){NC}")
    print(RULE)


def finish(msh_path):
    print(f"\n{RULE}\nEnd conversion\n")
    print(f"Note: Run 'gmshToFoam {os.path.basename(msh_path)}' in the case folder. All patches")
    print("      are of type 'patch' afterwards; set the cyclic pairs and other")
    print("      types in constant/polyMesh/boundary.\n\n")


# --------------------------------------------------------------------------
# Questions
# --------------------------------------------------------------------------
def ask(prompt):
    return input(f"   - {prompt}: ").strip()


def ask_yn(prompt):
    """Repeat until the answer is y or n (same behavior as the bash scripts)."""
    while True:
        answer = ask(f"{prompt} (y/n)").lower()
        if answer in ("y", "n"):
            return answer == "y"


# --------------------------------------------------------------------------
# Formatting
# --------------------------------------------------------------------------
def compact(tags):
    """[1, 2, 3, 5, 7, 8] -> '1-3, 5, 7-8'"""
    tags = sorted(tags)
    out, i = [], 0
    while i < len(tags):
        j = i
        while j + 1 < len(tags) and tags[j + 1] == tags[j] + 1:
            j += 1
        out.append(str(tags[i]) if i == j else f"{tags[i]}-{tags[j]}")
        i = j + 1
    return ", ".join(out)


def table(headers, rows, align=None, highlight=()):
    """Print a table whose columns line up under their headers.

    align     : string with 'l' or 'r' per column (default: all left)
    highlight : indices of rows to print in orange
    Column widths are measured from the content, nothing is hard-coded.
    """
    align = align or "l" * len(headers)
    widths = [max([len(str(h))] + [len(str(r[i])) for r in rows])
              for i, h in enumerate(headers)]

    def fmt(cells):
        parts = [str(c).rjust(w) if a == "r" else str(c).ljust(w)
                 for c, w, a in zip(cells, widths, align)]
        return "  ".join(parts).rstrip()

    line = "-" * (sum(widths) + 2 * (len(widths) - 1))
    detail(fmt(headers))
    detail(line)
    for i, r in enumerate(rows):
        detail(f"{ORANGE}{fmt(r)}{NC}" if i in highlight else fmt(r))
    detail(line)
