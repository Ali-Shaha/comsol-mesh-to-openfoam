#!/usr/bin/env python3
"""
Convert a Nastran (.nas) mesh to a Gmsh MSH 2.2 file for OpenFOAM (gmshToFoam).

Workflow
  1. Reads the .nas file and converts the mesh to first order
     (gmshToFoam cannot read second-order elements).
  2. Writes <name>.msh with one physical group per surface (surface_N)
     and per volume (volume_N).
  3. Asks whether to name the surfaces / volumes.
       - optionally opens a Gmsh viewer in a separate process, showing the
         surface numbers, while open in the terminal
  4. Writes <name>_named.msh (or rewrites <name>.msh with --overwrite).

Usage
  python nas_to_msh.py model.nas
  python nas_to_msh.py model.nas --overwrite
"""

import argparse
import os
import re
import subprocess
import sys

import gmsh

VOLUME_TAG_OFFSET = 1000   # keeps volume tags from clashing with surface tags

# Terminal colors (switched off when the output is piped to a file)
if os.name == "nt":
    os.system("")          # enables ANSI colors in the Windows console
if sys.stdout.isatty():
    RED, GREEN, ORANGE = "\033[91m", "\033[92m", "\033[93m"
    GRAY, NC = "\033[37m", "\033[0m"
else:
    RED = GREEN = ORANGE = GRAY = NC = ""
RULE = "-" * 79


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def ask_yn(prompt):
    """Ask until the answer is y or n."""
    while True:
        answer = input(f"   - {prompt} (y/n): ").strip().lower()
        if answer in ("y", "n"):
            return answer == "y"


def set_msh_options():
    gmsh.option.setNumber("General.Terminal", 0)        # keep Gmsh's messages out of the terminal
    gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)   # what gmshToFoam reads
    gmsh.option.setNumber("Mesh.Binary", 0)


def load(nas_file):
    """Open the .nas file and make sure the mesh is first order."""
    gmsh.open(nas_file)
    gmsh.model.mesh.setOrder(1)


def report_element_types():
    """Print element types / order so you can confirm the mesh is first order."""
    print("   - Element types after conversion")
    higher_order = False
    for t in gmsh.model.mesh.getElementTypes():
        name, dim, order, _, _, _ = gmsh.model.mesh.getElementProperties(t)
        count = len(gmsh.model.mesh.getElementsByType(t)[0])
        print(f"       {name:22s} dim={dim} order={order} count={count}")
        higher_order |= order > 1
    if higher_order:
        print(f"   - {ORANGE}Higher-order elements are still present; gmshToFoam will skip them")
        print(f"     Re-export a first-order mesh from the pre-processor{NC}")
    else:
        print(f"   - {GREEN}All elements are first order{NC}")


def write_default_groups(msh_path):
    """One physical group per surface and per volume, then write the file."""
    for dim, label, offset in [(2, "surface", 0), (3, "volume", VOLUME_TAG_OFFSET)]:
        for _, t in gmsh.model.getEntities(dim):
            pg = gmsh.model.addPhysicalGroup(dim, [t], tag=t + offset)
            gmsh.model.setPhysicalName(dim, pg, f"{label}_{t}")
    gmsh.write(msh_path)


def print_table(dim, label):
    print(f"   - {label.capitalize()}s found")
    for _, t in gmsh.model.getEntities(dim):
        x0, y0, z0, x1, y1, z1 = gmsh.model.getBoundingBox(dim, t)
        n = sum(len(e) for e in gmsh.model.mesh.getElements(dim, t)[1])
        print(f"       {label}_{t:<4} elems={n:<7} "
              f"x[{x0:.4g},{x1:.4g}] y[{y0:.4g},{y1:.4g}] z[{z0:.4g},{z1:.4g}]")


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


# --------------------------------------------------------------------------
# Interactive naming
# --------------------------------------------------------------------------
def parse_tags(text, allowed):
    """'3, 5, 8-10' -> [3, 5, 8, 9, 10], checked against the allowed set."""
    tags = set()
    for part in re.split(r"[,\s]+", text.strip()):
        if not part:
            continue
        m = re.fullmatch(r"(\d+)-(\d+)", part)
        if m:
            tags.update(range(int(m[1]), int(m[2]) + 1))
        elif part.isdigit():
            tags.add(int(part))
        else:
            raise ValueError(f"cannot parse '{part}'")
    bad = sorted(tags - allowed)
    if bad:
        raise ValueError(f"not available (unknown or already assigned): {bad}")
    return sorted(tags)


def ask_groups(dim, label):
    """Ask for (name, tags) pairs until done. Returns (groups, leftover tags)."""
    free = {t for _, t in gmsh.model.getEntities(dim)}
    groups = {}
    while free:
        print(f"\n   - Unassigned {label}s ({len(free)}): {compact(free)}")
        name = input(f"   - {label.capitalize()} group name (Enter to finish): ").strip()
        if not name:
            break
        try:
            tags = parse_tags(input(f"   - Numbers for '{name}' (e.g. 3,5,8-10): "), free)
        except ValueError as e:
            print(f"   - {RED}{e}{NC}")
            continue
        if not tags:
            continue
        groups.setdefault(name, []).extend(tags)
        free -= set(tags)
        print(f"   - {GREEN}{name}: {compact(groups[name])}{NC}")

    if free:
        print(f"\n   - {ORANGE}{len(free)} {label}(s) without a group: {compact(free)}{NC}")
        rest = input(f"   - Name for the remaining {label}s "
                     f"(Enter = keep {label}_N names): ").strip()
        if rest:
            groups.setdefault(rest, []).extend(sorted(free))
            free = set()
    return groups, sorted(free)


def apply_groups(dim, label, groups, leftover, first_tag):
    tag = first_tag
    for name, tags in groups.items():
        pg = gmsh.model.addPhysicalGroup(dim, tags, tag=tag)
        gmsh.model.setPhysicalName(dim, pg, name)
        tag += 1
    for t in leftover:
        pg = gmsh.model.addPhysicalGroup(dim, [t], tag=tag)
        gmsh.model.setPhysicalName(dim, pg, f"{label}_{t}")
        tag += 1


# --------------------------------------------------------------------------
# Viewer (runs in its own process so the terminal stays usable)
# --------------------------------------------------------------------------
def viewer_process(msh_file):
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.open(msh_file)
        gmsh.option.setNumber("Mesh.SurfaceFaces", 1)
        gmsh.option.setNumber("Mesh.SurfaceEdges", 0)
        gmsh.option.setNumber("Mesh.VolumeEdges", 0)
        gmsh.option.setNumber("Mesh.VolumeFaces", 0)
        gmsh.option.setNumber("Mesh.ColorCarousel", 2)     # one color per physical group
        gmsh.option.setNumber("Mesh.SurfaceLabels", 1)
        gmsh.option.setNumber("Mesh.LabelType", 2)         # label = physical tag = surface number
        gmsh.option.setNumber("Mesh.LabelSampling", 150)   # fewer labels, less clutter
        gmsh.fltk.run()
    finally:
        gmsh.finalize()


def start_viewer(nas_file, msh_file):
    # Output is discarded so Gmsh's banner / Info lines don't clutter the prompts.
    # To debug the viewer, run:  python nas_to_msh.py model.nas --view-msh model.msh
    return subprocess.Popen([sys.executable, os.path.abspath(__file__),
                             nas_file, "--view-msh", msh_file],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Convert .nas to a named .msh (MSH 2.2).")
    ap.add_argument("nas", help="input Nastran file")
    ap.add_argument("--overwrite", action="store_true",
                    help="rewrite <name>.msh with the names instead of "
                         "writing <name>_named.msh")
    ap.add_argument("--view-msh", help=argparse.SUPPRESS)   # internal: viewer mode
    args = ap.parse_args()

    if args.view_msh:
        viewer_process(args.view_msh)
        return

    base = os.path.splitext(args.nas)[0]
    msh = base + ".msh"
    msh_named = msh if args.overwrite else base + "_named.msh"

    print(f"\n{RULE}")
    print(f"{GRAY}Script{NC}         :: nas_to_msh.py")
    print(f"{GRAY}Gmsh version{NC}   :: {gmsh.__version__}")
    print(f"{GRAY}Input file{NC}     :: {args.nas}")
    print(f"{RULE}\n\n")
    print(f"{GREEN}Convert a Nastran mesh to a named MSH 2.2 file (for gmshToFoam){NC}")
    print(f"{RULE}\n\nStart conversion\n{RULE}\n")

    viewer = None
    named = False
    try:
        # ---- Session 1: default .msh, then collect the groups from the user ----
        gmsh.initialize()
        try:
            set_msh_options()
            print(f"   - Read {args.nas} and convert to first-order elements")
            load(args.nas)
            report_element_types()
            print("   - Create default groups (surface_N, volume_N)")
            write_default_groups(msh)
            print(f"   - {GREEN}Wrote {msh}{NC}\n")

            named = ask_yn("Name the surfaces and volumes")
            if named:
                if ask_yn("Open a viewer to see the surface numbers"):
                    viewer = start_viewer(args.nas, msh)
                    print(f"   - {GREEN}Viewer started. Keep going here while it is open{NC}")

                print()
                print_table(2, "surface")
                print()
                print_table(3, "volume")

                s_groups, s_left = ask_groups(2, "surface")
                v_groups, v_left = ask_groups(3, "volume")
        finally:
            gmsh.finalize()

        # ---- Session 2: fresh Gmsh so no leftover names from session 1 ----
        if named:
            gmsh.initialize()
            try:
                set_msh_options()
                print("\n   - Reload the mesh in a fresh Gmsh session")
                load(args.nas)
                print("   - Apply the group names")
                apply_groups(2, "surface", s_groups, s_left, first_tag=1)
                apply_groups(3, "volume", v_groups, v_left, first_tag=VOLUME_TAG_OFFSET)
                gmsh.write(msh_named)
                print(f"   - {GREEN}Wrote {msh_named}{NC}")
            finally:
                gmsh.finalize()

    finally:
        if viewer is not None and viewer.poll() is None:
            viewer.terminate()

    final = os.path.basename(msh_named if named else msh)
    print(f"\n{RULE}\nEnd conversion\n")
    print(f"Note: Run 'gmshToFoam {final}' in the case folder. All patches")
    print("      are of type 'patch' afterwards; set the cyclic pairs and other")
    print("      types in constant/polyMesh/boundary.\n\n")


if __name__ == "__main__":
    main()