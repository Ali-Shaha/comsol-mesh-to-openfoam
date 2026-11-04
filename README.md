# comsol-mesh-to-openfoam

Convert a **COMSOL mesh to OpenFOAM**.

This tool takes a NASTRAN (`.nas`) mesh exported from COMSOL Multiphysics and converts it into a Gmsh MSH 2.2 file with **named surfaces and volumes**, ready for OpenFOAM's `gmshToFoam`. It works with any NASTRAN mesh, not only those exported from COMSOL.

```text
COMSOL  ──►  model.nas  ──►  nas_to_msh.py  ──►  model_named.msh  ──►  gmshToFoam  ──►  OpenFOAM case
```

## Documentation

For a detailed explanation of the conversion process, script IO, and practical workflow, see the [project article on my website](https://ali-shaha.github.io/posts/2026/11/comsol-mesh-to-openfoam/).

## Why this exists

- `gmshToFoam` reads only first-order elements. COMSOL's NASTRAN export writes second-order elements by default, and `gmshToFoam` skips them (printing an "Unhandled element" message), which can leave you with only a fraction of your cells.
- NASTRAN files carry no usable surface names. Without names, every boundary arrives in OpenFOAM as `surface_1` ... `surface_N`.

The script converts the mesh to first order, checks that `gmshToFoam` can read every element type, and lets you name boundary groups (for example, `inlet`, `outlet`, `walls`) and volume zones before writing the `.msh` file.

## Two versions

| | `full/` | `standalone/` |
|---|---|---|
| Files | 4 files, kept together | 1 file |
| First-order conversion | Yes | Yes |
| Element-type check | Yes | Warning for higher-order elements only |
| Interactive naming, optional Gmsh viewer with surface numbers | Yes | Yes |
| Name / number validation | Yes | No |
| Written file is read back and checked | Yes | No |
| Saves names to `<model>_groups.json` and reuses them (`--groups`) | Yes | No |

Use `full/` for more sanity checks. Use `standalone/` when you want a single file to read or copy.

## Requirements

- Python 3
- Gmsh Python module: `pip install gmsh` (developed with Gmsh 4.15.2)
- A graphical display, only if you want to use the surface-number viewer

Install the dependencies:

```bash
pip install -r requirements.txt
```

## Quick start: COMSOL mesh to OpenFOAM

1. **Export from COMSOL** as NASTRAN (`.nas`). In the export settings, enable boundary (shell) elements and the option to export linear elements. The labels can differ between COMSOL versions. COMSOL also writes the geometric entity index of every element into the property ID field of the file. This is where the surface and volume numbers come from.

2. **Run the script** (keep all files in `full/` together in the same folder):

   ```bash
   python nas_to_msh.py model.nas
   ```

3. **Answer the questions.** The script assigns every surface and volume a default name (`surface_N`, `volume_N`), then asks whether you want to give them custom names.

4. **Convert to OpenFOAM** in the case folder:

   ```bash
   gmshToFoam model_named.msh
   ```

5. **Check the result.** A successful conversion does not, by itself, mean that the mesh is suitable for simulation. Run `checkMesh` and review the imported boundaries, including patch names and types, before proceeding.

## OpenFOAM tutorial

A `pitzDaily` OpenFOAM tutorial is included in [`tutorial/`](tutorial/). It demonstrates how to use the converter in an OpenFOAM case, with two mesh-generation options: the standard `blockMesh` workflow or a COMSOL-exported NASTRAN mesh converted using `nas_to_msh.py` and `gmshToFoam`. See the [tutorial README](tutorial/README.md) for setup and run instructions.

## Naming surfaces and volumes

Enter a group name, followed by the numbers belonging to that group. Numbers can be specified as a list, a range, or a combination of both.

Example:

```text
Unassigned surfaces (46): 1-46
Surface group name (Enter to finish): inlet
Numbers for 'inlet' (e.g. 3,5,8-10): 1-5
inlet: 1-5
```

- Press Enter on an empty group name to finish.
- Remaining surfaces can be assigned a common name (for example, `walls`) or keep their default `surface_N` names.
- To identify which number corresponds to which surface, answer **y** when asked whether to open the viewer. A Gmsh window displays the surface numbers while you continue entering names in the terminal.
- Reusing a name adds the new numbers to the existing group.

**Name rules in `full/`:** Names may contain letters, digits, `_` and `-`. The first character must be a letter or `_`. Names of the form `surface_<number>` and `volume_<number>` are reserved for unnamed leftovers.

The standalone version does not validate names.

## Options (`full/`)

| Option | Effect |
|---|---|
| `--groups FILE` | Apply names from a saved groups file without interactive questions (batch mode). |
| `--overwrite` | Write the names into `<model>.msh` instead of `<model>_named.msh`, replacing existing files without asking. |
| `--verbose` | Show Gmsh's own messages and Python tracebacks on errors. |

### Output files

The files written depend on your answer to the question "Name the surfaces?":

| Answer | Result |
|---|---|
| `y` | `<model>_named.msh` and `<model>_groups.json` |
| `n` | `<model>.msh` with default names |

### Reusing names for a new export

After an interactive run, the names are stored in `<model>_groups.json`.

An example of the saved structure:

```json
{
  "version": 1,
  "input": "model.nas",
  "input_sha256": "...",
  "surfaces": {
    "inlet": [1, 2, 3],
    "wall": [4, 5, 6]
  },
  "volumes": {
    "fluid": [1]
  }
}
```

The file also stores bounding boxes for the named surfaces and volumes.

When you re-export the same model from COMSOL, for example with a different element size, run:

```bash
python nas_to_msh.py model.nas --groups model_groups.json
```

The script checks that every group number exists in the new mesh and that the surfaces are still in the same locations (using bounding boxes).

If the geometry has changed, the script refuses to apply the saved names and lists what has moved. This prevents old names from being silently applied to the wrong surfaces.

If only the file has changed but every bounding box still matches, the script warns and continues. Surfaces that are not included in any group retain their `surface_N` names.

## Troubleshooting

**`gmshToFoam` prints "Unhandled element" and the OpenFOAM case has far fewer cells than the COMSOL mesh.**

The `.msh` file contains second-order elements, which `gmshToFoam` skips. This tool converts the mesh to first order before writing it. Alternatively, you can enable the linear-elements option in COMSOL's NASTRAN export settings.

**The script stops and lists element types in orange, or reports "No volume elements".**

The mesh contains element types that `gmshToFoam` cannot read, or it contains only surface elements. Export again from COMSOL as a 3D mesh with linear elements.

**"No boundary elements found", so there are no surfaces to name.**

The export did not include boundary (shell) elements. Enable them in COMSOL's NASTRAN export settings and export again.

**The viewer window does not open.**

The viewer requires a graphical display. The conversion continues without it, and you can read the surface numbers from the tables in the terminal instead.

## Limitations

- **First order only.** Midside nodes are dropped. Curved boundaries become straight between corner nodes, which can matter on coarse meshes.
- **Element types.** Boundary faces must be triangles or quads; cells must be tetrahedra, hexahedra, prisms or pyramids. Point and line elements are ignored.
- **Patch types remain `patch`.** Set wall, cyclic and other patch types afterwards in `constant/polyMesh/boundary` or with `createPatch`.
- **Surface numbers.** These are Gmsh's numbering of the entities stored in the `.nas` file. COMSOL's boundary indices are expected to match, but check a few surfaces in the viewer the first time.
- **The viewer.** It requires a graphical display, so it does not work over plain SSH without X forwarding. A viewer failure does not stop the conversion.
- **Boundary elements.** They must coincide with the outer cell faces; otherwise, `gmshToFoam` may report errors.

## Repository layout

```text
comsol-mesh-to-openfoam/
├── README.md
├── LICENSE
├── requirements.txt
├── .gitignore
├── full/
│   ├── nas_to_msh.py     main script: mesh logic
│   ├── _terminal.py      colors, banner, prompts, tables
│   ├── _groups.py        naming rules, number parsing, saved groups
│   └── _viewer.py        Gmsh window showing surface numbers
└── standalone/
    └── nas_to_msh.py     single-file version
```

## License

See the [LICENSE](LICENSE) file.