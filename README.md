# comsol-to-openfoam-mesh

Convert a **COMSOL mesh to OpenFOAM**. The tool takes the Nastran (`.nas`) mesh exported from COMSOL Multiphysics and turns it into a Gmsh MSH 2.2 file with **named surfaces and volumes**, ready for OpenFOAM's `gmshToFoam`. It works with any Nastran mesh, not only COMSOL's.

```
COMSOL  ──►  model.nas  ──►  nas_to_msh.py  ──►  model_named.msh  ──►  gmshToFoam  ──►  OpenFOAM case
```

## Why this exists

- `gmshToFoam` reads only first-order elements. COMSOL's NASTRAN export writes second-order elements by default, and `gmshToFoam` skips them (it only prints an "Unhandled element" message), which can leave you with a fraction of your cells.
- Nastran files carry no usable surface names. Without names, every boundary arrives in OpenFOAM as `surface_1 … surface_N`.

The script converts the mesh to first order, checks that `gmshToFoam` can read every element type, and lets you name boundary groups (for example `inlet`, `outlet`, `walls`) and volume zones before writing the `.msh`.

## Two versions

| | `full/` | `standalone/` |
|---|---|---|
| Files | 4 files, kept together | 1 file |
| First-order conversion | yes | yes |
| Element-type check (stops on types `gmshToFoam` cannot read) | yes | warning for higher-order only |
| Interactive naming, optional Gmsh viewer with surface numbers | yes | yes |
| Name and number validation | yes | no |
| Written file is read back and checked | yes | no |
| Asks before replacing existing files | yes | no |
| Saves names to `<model>_groups.json` and reuses them (`--groups`) | yes | no |

Use `full/` for real work. Use `standalone/` when you want a single small file to read or copy.

## Requirements

- Python 3
- The Gmsh Python module: `pip install gmsh` (developed with Gmsh 4.15.2)
- A graphical display, only if you want the surface-number viewer

```bash
pip install -r requirements.txt
```

## Quick start: COMSOL mesh to OpenFOAM

1. **Export from COMSOL** as NASTRAN (`.nas`). In the export settings, enable the boundary (shell) elements and the option to export linear elements. The labels can differ between COMSOL versions. COMSOL also writes the geometric entity index of every element into the property ID field of the file, which is where the surface and volume numbers come from.
2. **Run the script** (keep the files of `full/` together in one folder):

   ```bash
   python nas_to_msh.py model.nas
   ```
3. **Answer the questions.** The script gives every surface and volume a default name (`surface_N`, `volume_N`), then asks whether you want to name them.
4. **Convert to OpenFOAM** in the case folder:

   ```bash
   gmshToFoam model_named.msh
   ```
5. **Check the result.** A successful conversion does not, by itself, show that the mesh is suitable for simulation. Run `checkMesh` and review the imported boundaries, including patch names and types, before proceeding.

## Naming surfaces and volumes

Type a group name, then the numbers that belong to it. Numbers can be a list, a range, or both:

```
   - Unassigned surfaces (46): 1-46
   - Surface group name (Enter to finish): inlet
   - Numbers for 'inlet' (e.g. 3,5,8-10): 1-5
   - inlet: 1-5
```

- Press Enter on an empty group name to finish. Surfaces left over can get one common name (for example `walls`) or keep their `surface_N` names.
- To find out which number is which surface, answer **y** to the viewer question. A Gmsh window opens with the surface numbers while you keep typing in the terminal.
- Reusing a name adds to the existing group.

Name rules in `full/`: letters, digits, `_` and `-`; the first character must be a letter or `_`; names of the form `surface_<number>` and `volume_<number>` are reserved for unnamed leftovers. The standalone version does not check names.

## Options (`full/`)

| Option | Effect |
|---|---|
| `--groups FILE` | Apply the names from a saved groups file and ask nothing (batch mode). |
| `--overwrite` | Write the names into `<model>.msh` instead of `<model>_named.msh`, and replace existing files without asking. |
| `--verbose` | Show Gmsh's own messages, and Python tracebacks on errors. |

Files written (interactive run):

| Answer to "name the surfaces?" | Result |
|---|---|
| y | `<model>_named.msh` and `<model>_groups.json` |
| n | `<model>.msh` with default names |

### Reusing names for a new export

After an interactive run, the names are stored in `<model>_groups.json`:

```json
{
  "version": 1,
  "input": "model.nas",
  "input_sha256": "…",
  "surfaces": { "inlet": [1, 2, 3], "wall": [4, 5, 6] },
  "volumes": { "fluid": [1] },
  "bbox": { "…": "bounding boxes written by the script" }
}
```

When you re-export the same model from COMSOL, for example with a different element size, run:

```bash
python nas_to_msh.py model.nas --groups model_groups.json
```

The script checks that every group number exists in the new mesh and that the surfaces are still where they were (bounding boxes). If the geometry changed, it refuses and lists what moved, so old names are never applied to the wrong surfaces silently. If only the file changed but every bounding box still matches, it warns and continues. Surfaces that are not in any group keep their `surface_N` names.

## Troubleshooting

**`gmshToFoam` prints "Unhandled element" and the case has far fewer cells than the COMSOL mesh.**
The `.msh` contains second-order elements, which `gmshToFoam` skips. This tool converts the mesh to first order before writing it. You can also enable the linear-elements option in COMSOL's NASTRAN export.

**The script stops and lists element types in orange, or reports "No volume elements".**
The mesh contains element types `gmshToFoam` cannot read, or only surface elements. Export again from COMSOL as a 3D mesh with linear elements.

**"No boundary elements found", so there are no surfaces to name.**
The export did not include boundary (shell) elements. Enable them in COMSOL's NASTRAN export settings and export again.

**The viewer window does not open.**
It needs a graphical display. The conversion continues without it, and you can read the surface numbers from the tables in the terminal instead.

## Limitations

- **First order only.** Midside nodes are dropped. Curved boundaries become straight between corner nodes, which matters on coarse meshes.
- **Element types.** Boundary faces must be triangles or quads; cells must be tetrahedra, hexahedra, prisms or pyramids. Point and line elements are ignored.
- **Patch types stay `patch`.** Set walls, cyclic pairs and other types afterwards in `constant/polyMesh/boundary` (or with `createPatch`).
- **Surface numbers.** They are Gmsh's numbering of what is stored in the `.nas` file. COMSOL's boundary indices are expected to match, but check a few surfaces in the viewer the first time.
- **The viewer** needs a graphical display, so it does not work over plain SSH without X forwarding. A failing viewer never stops the conversion.
- **Boundary elements** must coincide with the outer cell faces, otherwise `gmshToFoam` may report errors.

## Repository layout

```
comsol-to-openfoam-mesh/
├── README.md
├── LICENSE
├── requirements.txt
├── .gitignore
├── full/
│   ├── nas_to_msh.py     main script: the mesh logic
│   ├── _terminal.py      colors, banner, prompts, tables
│   ├── _groups.py        naming rules, number parsing, saved groups
│   └── _viewer.py        Gmsh window showing the surface numbers
└── standalone/
    └── nas_to_msh.py     single-file version
```

## License

See the `LICENSE` file.
