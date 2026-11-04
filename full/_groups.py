#!/usr/bin/env python3
"""
Naming rules, number parsing and the saved-groups file for nas_to_msh.py.

Pure Python, no Gmsh needed, so everything here can be tested on its own.
"""

import hashlib
import json
import os
import re

from _terminal import compact

# Naming policy of this script (conservative, not the full OpenFOAM word syntax):
# letters, digits, '_' and '-', starting with a letter or '_'.
NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*")


def check_name(name, label):
    """Return a problem text for a group name, or None if it is fine."""
    if not NAME_RE.fullmatch(name):
        return (f"'{name}' is not allowed: use letters, digits, '_' or '-' "
                "and start with a letter or '_'")
    if re.fullmatch(rf"{label}_\d+", name):
        return f"'{name}' is reserved for {label}s that are left unnamed"
    return None


def parse_tags(text, allowed):
    """'3, 5, 8-10' -> [3, 5, 8, 9, 10], checked against the allowed set."""
    top = max(allowed, default=0)
    tags = set()
    for part in re.split(r"[,\s]+", text.strip()):
        if not part:
            continue
        m = re.fullmatch(r"(\d+)-(\d+)", part)
        if m:
            start, end = int(m[1]), int(m[2])
            if start > end:
                raise ValueError(f"reversed range '{part}'")
            if end > top:      # also stops absurd ranges before they are expanded
                raise ValueError(f"'{part}' goes past the highest available number ({top})")
            tags.update(range(start, end + 1))
        elif part.isdigit():
            tags.add(int(part))
        else:
            raise ValueError(f"cannot parse '{part}'")
    bad = sorted(tags - allowed)
    if bad:
        raise ValueError(f"not available (unknown or already assigned): {bad}")
    return sorted(tags)


# --------------------------------------------------------------------------
# Saved groups (JSON)
# --------------------------------------------------------------------------
def file_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def save_groups(path, nas_file, s_groups, v_groups, entities):
    """entities: {'surface': {tag: bbox}, 'volume': {tag: bbox}} of the mesh."""
    data = {
        "version": 1,
        "input": os.path.basename(nas_file),
        "input_sha256": file_hash(nas_file),
        "surfaces": s_groups,
        "volumes": v_groups,
        "bbox": {label: {str(t): list(bb) for t, bb in ents.items()}
                 for label, ents in entities.items()},
    }
    text = json.dumps(data, indent=2)
    # keep each list of numbers on one line, so the file stays easy to read and edit
    text = re.sub(r"\[([^\[\]{}]*?)\]",
                  lambda m: "[" + re.sub(r"\s+", " ", m.group(1)).strip() + "]", text)
    with open(path, "w") as f:
        f.write(text + "\n")


def load_groups(path):
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        raise ValueError(f"cannot read {path}: {e}")
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a groups file")
    return data


def _same_box(a, b, rel_tol=1e-6):
    if len(a) != 6 or len(b) != 6:
        return False
    tol = rel_tol * max(abs(v) for v in list(a) + list(b)) + 1e-12
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def validate_groups(data, entities, nas_hash):
    """Check a saved-groups dict against the mesh that is loaded now.

    Returns (groups, leftover, problems, warnings); groups and leftover are
    dicts keyed by 'surface' / 'volume'. Any problem means: do not use it.
    """
    problems, warnings = [], []
    groups, leftover = {}, {}

    for label, key in (("surface", "surfaces"), ("volume", "volumes")):
        mesh = entities[label]
        raw = data.get(key, {})
        if not isinstance(raw, dict):
            problems.append(f"'{key}' must map group names to lists of numbers")
            raw = {}
        used = {}
        groups[label] = {}
        for name, tags in raw.items():
            err = check_name(name, label)
            if err:
                problems.append(err)
            if not isinstance(tags, list) or not all(isinstance(t, int) for t in tags):
                problems.append(f"group '{name}': expected a list of whole numbers")
                continue
            for t in tags:
                if t not in mesh:
                    problems.append(f"{label}_{t} (group '{name}') does not exist in this mesh")
                elif t in used:
                    problems.append(f"{label}_{t} is in both '{used[t]}' and '{name}'")
                else:
                    used[t] = name
            groups[label][name] = sorted(set(tags))
        leftover[label] = sorted(set(mesh) - set(used))
        if leftover[label]:
            warnings.append(f"{len(leftover[label])} {label}(s) not in any group: "
                            f"{compact(leftover[label])} -> kept as {label}_N")

    if data.get("input_sha256") != nas_hash:
        changed = []
        for label in ("surface", "volume"):
            saved = data.get("bbox", {}).get(label, {})
            for t, box in entities[label].items():
                old = saved.get(str(t))
                if old is None or not _same_box(old, box):
                    changed.append(f"{label}_{t}")
        if changed:
            problems.append("the mesh differs from the one these groups were saved for "
                            f"(bounding box changed or new: {', '.join(changed[:8])}"
                            f"{' ...' if len(changed) > 8 else ''})")
        else:
            warnings.append("the .nas file changed since the groups were saved, "
                            "but every bounding box still matches")

    return groups, leftover, problems, warnings
