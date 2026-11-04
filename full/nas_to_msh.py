#!/usr/bin/env python3
"""
Convert a Nastran (.nas) mesh, e.g. exported from COMSOL, to a Gmsh MSH 2.2
file with named patches / cell zones for OpenFOAM (gmshToFoam).

Workflow
  1. Reads the .nas file, converts it to first order and checks that every
     element type is one gmshToFoam can read.
  2. Creates one physical group per surface (surface_N) and volume (volume_N).
  3. Asks whether you want to name them. Optionally a Gmsh window with the
     surface numbers opens while you keep typing here.
  4. Writes the .msh to a temporary file, reads it back to check the groups and
     element counts, and only then moves it to its final place.
  5. Saves the names in <name>_groups.json, so the next export of the same
     model can be converted without questions (--groups).

Usage
  python nas_to_msh.py model.nas                       (interactive)
  python nas_to_msh.py model.nas --groups model_groups.json   (no questions)
  python nas_to_msh.py model.nas --overwrite           (replace <name>.msh)
  python nas_to_msh.py model.nas --verbose             (Gmsh messages, tracebacks)

Files (keep them in the same folder)
  nas_to_msh.py   this file: the mesh logic
  _terminal.py    colors, banner, prompts, tables
  _groups.py      naming rules, number parsing, saved groups
  _viewer.py      Gmsh window that shows the surface numbers
"""

import argparse
import os
import sys
import tempfile
import traceback

import gmsh

import _viewer
from _groups import (check_name, file_hash, load_groups, parse_tags,
                     save_groups, validate_groups)
from _terminal import (ask, ask_yn, banner, compact, detail, fail, finish, good,
                       hint, section, step, table, warn)

# Gmsh element types that gmshToFoam reads: triangle, quad | tet, hex, prism, pyramid
SUPPORTED = {2: {2, 3}, 3: {4, 5, 6, 7}}


# --------------------------------------------------------------------------
# Gmsh helpers
# --------------------------------------------------------------------------
def open_mesh(args, quiet=False):
    """Set the options, read the .nas file and make it first order."""
    say = (lambda msg: None) if quiet else step
    gmsh.option.setNumber("General.Terminal", 1 if args.verbose else 0)
    gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)   # what gmshToFoam reads
    gmsh.option.setNumber("Mesh.Binary", 0)
    gmsh.option.setNumber("Mesh.SaveAll", 0)            # only write grouped elements,
    say(f"Read {args.nas}")                              # even if a config file says otherwise
    gmsh.open(args.nas)
    say("Convert to first-order elements")
    gmsh.model.mesh.setOrder(1)


def report_mesh():
    """List the element types; stop if gmshToFoam could not use the mesh."""
    step("Element types in the mesh")
    print()
    rows, unsupported = [], set()
    for t in gmsh.model.mesh.getElementTypes():
        name, dim, order, _, _, _ = gmsh.model.mesh.getElementProperties(t)
        if dim in SUPPORTED and t not in SUPPORTED[dim]:
            unsupported.add(len(rows))
        rows.append([name, dim, order, len(gmsh.model.mesh.getElementsByType(t)[0])])
    table(["Type", "Dim", "Order", "Count"], rows, align="lrrr", highlight=unsupported)
    print()

    errors = 0
    if unsupported:
        fail("Element types gmshToFoam cannot read (orange rows)")
        hint("COMSOL NASTRAN export: enable 'Export as linear elements'")
        errors += 1
    if not any(r[1] == 3 for r in rows):
        fail("No volume elements in the mesh")
        errors += 1
    if not any(r[1] == 2 for r in rows):
        warn("No boundary elements found, so there are no surfaces to name")
        hint("COMSOL NASTRAN export: enable the boundary (shell) elements")
    if any(r[1] < 2 for r in rows):
        step("Point and line elements are ignored (they are not written)")
    if errors:
        raise RuntimeError("the mesh cannot be read by gmshToFoam")
    good("All volume and surface elements are types gmshToFoam reads")


def entity_info():
    """{'surface': {tag: bbox}, 'volume': {tag: bbox}} of the loaded mesh."""
    return {label: {t: list(gmsh.model.getBoundingBox(dim, t))
                    for _, t in gmsh.model.getEntities(dim)}
            for dim, label in ((2, "surface"), (3, "volume"))}


def count_elements(dim, tag=-1):
    return sum(len(e) for e in gmsh.model.mesh.getElements(dim, tag)[1])


def volume_offset(entities):
    """Volume tags start above every surface tag, so the two never overlap."""
    return max(entities["surface"], default=0)


def create_default_groups(entities):
    offset = volume_offset(entities)
    for dim, label, shift in [(2, "surface", 0), (3, "volume", offset)]:
        for t in entities[label]:
            pg = gmsh.model.addPhysicalGroup(dim, [t], tag=t + shift)
            gmsh.model.setPhysicalName(dim, pg, f"{label}_{t}")


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


def apply_all(entities, s_groups, s_left, v_groups, v_left):
    apply_groups(2, "surface", s_groups, s_left, first_tag=1)
    apply_groups(3, "volume", v_groups, v_left, first_tag=volume_offset(entities) + 1)


# --------------------------------------------------------------------------
# Writing and checking
# --------------------------------------------------------------------------
def physical_summary():
    """What a .msh should contain: elements per group, and elements per dimension."""
    groups = {}
    for dim, pg in gmsh.model.getPhysicalGroups():
        name = gmsh.model.getPhysicalName(dim, pg)
        groups[(dim, name)] = sum(count_elements(dim, e)
                                  for e in gmsh.model.getEntitiesForPhysicalGroup(dim, pg))
    return groups, {dim: count_elements(dim) for dim in (2, 3)}


def verify_msh(path, expected):
    """Read the written file in a fresh Gmsh session and compare. Returns problems."""
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.open(path)
        found = physical_summary()
    finally:
        gmsh.finalize()

    problems = []
    for key in sorted(set(expected[0]) | set(found[0])):
        if expected[0].get(key) != found[0].get(key):
            problems.append(f"group '{key[1]}': {expected[0].get(key)} elements expected, "
                            f"{found[0].get(key)} in the file")
    for dim in expected[1]:
        if expected[1][dim] != found[1][dim]:
            problems.append(f"{dim}D elements: {expected[1][dim]} expected, "
                            f"{found[1][dim]} in the file")
    return problems


def publish(tmp_path, dest, expected, force):
    """Check the temporary file by reading it back, then move it into place."""
    name = os.path.basename(dest)
    step(f"Check {name} by reading it back")
    problems = verify_msh(tmp_path, expected)
    if problems:
        for p in problems:
            fail(p)
        raise RuntimeError(f"{name} does not contain what was intended; nothing was written")
    if os.path.exists(dest) and not force:
        warn(f"{name} already exists")
        if not ask_yn("Overwrite it"):
            raise RuntimeError(f"{name} was not overwritten; nothing was written")
    os.replace(tmp_path, dest)
    good(f"Wrote {dest}")


# --------------------------------------------------------------------------
# Naming
# --------------------------------------------------------------------------
def show_entities(label, boxes):
    step(f"{label.capitalize()}s found: {len(boxes)}")
    print()
    rows = []
    for t, (x0, y0, z0, x1, y1, z1) in boxes.items():
        n = count_elements(2 if label == "surface" else 3, t)
        rows.append([f"{label}_{t}", n,
                     f"x[{x0:.4g},{x1:.4g}] y[{y0:.4g},{y1:.4g}] z[{z0:.4g},{z1:.4g}]"])
    table(["Name", "Elems", "BBox"], rows, align="lrl")


def ask_groups(label, available):
    """Ask for (name, numbers) pairs until done. Returns (groups, leftover)."""
    free = set(available)
    groups = {}
    while free:
        print()
        step(f"Unassigned {label}s ({len(free)}): {compact(free)}")
        name = ask(f"{label.capitalize()} group name (Enter to finish)")
        if not name:
            break
        err = check_name(name, label)
        if err:
            fail(err)
            continue
        try:
            tags = parse_tags(ask(f"Numbers for '{name}' (e.g. 3,5,8-10)"), free)
        except ValueError as e:
            fail(str(e))
            continue
        if not tags:
            continue
        groups.setdefault(name, []).extend(tags)
        free -= set(tags)
        good(f"{name}: {compact(groups[name])}")

    if free:
        print()
        warn(f"{len(free)} {label}(s) without a group: {compact(free)}")
        while True:
            rest = ask(f"Name for the remaining {label}s (Enter = keep {label}_N names)")
            err = check_name(rest, label) if rest else None
            if err:
                fail(err)
                continue
            if rest:
                groups.setdefault(rest, []).extend(sorted(free))
                free = set()
            break
    return groups, sorted(free)


def show_summary(label, groups, leftover):
    step(f"{label.capitalize()} groups")
    for name, tags in groups.items():
        detail(f"{name:<20}: {compact(tags)}")
    if leftover:
        detail(f"{'(not named)':<20}: {compact(leftover)}  -> kept as {label}_N")


# --------------------------------------------------------------------------
# The two ways to run
# --------------------------------------------------------------------------
def convert_interactive(args, tmp, msh, msh_named, groups_file):
    tmp_default = os.path.join(tmp, "default.msh")
    tmp_named = os.path.join(tmp, "named.msh")
    viewer = None
    result = None
    try:
        # ---- Session 1: default groups, then collect the names from the user ----
        gmsh.initialize()
        try:
            open_mesh(args)
            report_mesh()
            entities = entity_info()

            step("Create default groups (surface_N, volume_N)")
            create_default_groups(entities)
            expected_default = physical_summary()
            gmsh.write(tmp_default)
            print()

            if ask_yn("Name the surfaces and volumes"):
                if ask_yn("Open a viewer to see the surface numbers"):
                    viewer, reason = _viewer.start(tmp_default)
                    if viewer:
                        good("Viewer started. Keep going here while it is open")
                    else:
                        warn(f"Viewer did not start: {reason}")
                        hint("Run 'python _viewer.py <file>.msh' to see the full message")
                print()
                show_entities("surface", entities["surface"])
                print()
                show_entities("volume", entities["volume"])
                print()
                s_groups, s_left = ask_groups("surface", entities["surface"])
                print()
                v_groups, v_left = ask_groups("volume", entities["volume"])

                print()
                show_summary("surface", s_groups, s_left)
                show_summary("volume", v_groups, v_left)
                print()
                if ask_yn(f"Write {os.path.basename(msh_named)}"):
                    result = (s_groups, s_left, v_groups, v_left)
                else:
                    warn("Named mesh not written")
        finally:
            gmsh.finalize()
            _viewer.stop(viewer)

        if result is None:
            print()
            publish(tmp_default, msh, expected_default, force=args.overwrite)
            return msh

        # ---- Session 2: fresh Gmsh, so no leftover names from session 1 ----
        s_groups, s_left, v_groups, v_left = result
        print()
        step("Reload the mesh in a fresh Gmsh session")
        gmsh.initialize()
        try:
            open_mesh(args, quiet=True)
            step("Apply the group names")
            apply_all(entities, s_groups, s_left, v_groups, v_left)
            expected_named = physical_summary()
            gmsh.write(tmp_named)
        finally:
            gmsh.finalize()
        publish(tmp_named, msh_named, expected_named, force=args.overwrite)

        # ---- Remember the names for the next export of this model ----
        if (not os.path.exists(groups_file) or args.overwrite
                or ask_yn(f"{os.path.basename(groups_file)} exists. Overwrite")):
            save_groups(groups_file, args.nas, s_groups, v_groups, entities)
            good(f"Saved the names to {groups_file}")
            hint(f"Next time: python nas_to_msh.py {args.nas} --groups {groups_file}")
        return msh_named
    finally:
        _viewer.stop(viewer)


def convert_batch(args, tmp, msh_named):
    """No questions: take the names from a saved groups file."""
    tmp_named = os.path.join(tmp, "named.msh")
    gmsh.initialize()
    try:
        open_mesh(args)
        report_mesh()
        entities = entity_info()

        step(f"Read the groups from {args.groups}")
        data = load_groups(args.groups)
        groups, left, problems, warnings = validate_groups(
            data, entities, file_hash(args.nas))
        for w in warnings:
            warn(w)
        if problems:
            for p in problems:
                fail(p)
            raise RuntimeError("the saved groups do not fit this mesh")
        good("The saved groups fit this mesh")

        step("Apply the group names")
        apply_all(entities, groups["surface"], left["surface"],
                  groups["volume"], left["volume"])
        expected = physical_summary()
        gmsh.write(tmp_named)
    finally:
        gmsh.finalize()
    publish(tmp_named, msh_named, expected, force=True)
    return msh_named


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def run(args):
    base = os.path.splitext(args.nas)[0]
    msh = base + ".msh"
    msh_named = msh if args.overwrite else base + "_named.msh"
    outdir = os.path.dirname(os.path.abspath(args.nas))

    banner(args.nas, gmsh.__version__)
    section("Start conversion")

    # temporary files live next to the .nas, so moving them into place is one step
    with tempfile.TemporaryDirectory(prefix=".nas_to_msh_", dir=outdir) as tmp:
        if args.groups:
            final = convert_batch(args, tmp, msh_named)
        else:
            final = convert_interactive(args, tmp, msh, msh_named, base + "_groups.json")
    finish(final)


def main():
    ap = argparse.ArgumentParser(description="Convert .nas to a named .msh (MSH 2.2).")
    ap.add_argument("nas", help="input Nastran file")
    ap.add_argument("--groups", metavar="FILE",
                    help="apply the names from a saved groups file and ask nothing")
    ap.add_argument("--overwrite", action="store_true",
                    help="replace <name>.msh instead of writing <name>_named.msh, "
                         "and replace existing files without asking")
    ap.add_argument("--verbose", action="store_true",
                    help="show Gmsh's own messages and Python tracebacks")
    args = ap.parse_args()

    if not os.path.isfile(args.nas):
        print()
        fail(f"File not found: {args.nas}\n")
        sys.exit(1)

    try:
        run(args)
    except (KeyboardInterrupt, EOFError):
        print()
        warn("Aborted by user\n")
        sys.exit(130)
    except Exception as e:
        print()
        fail(f"Error: {e}\n")
        if args.verbose:
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
