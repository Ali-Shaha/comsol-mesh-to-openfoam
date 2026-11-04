# nas-to-msh: full version

The recommended version. It converts a Nastran (`.nas`) mesh, for example one exported from COMSOL, to a Gmsh MSH 2.2 file with named surfaces and volumes for `gmshToFoam`. For the background and the COMSOL export settings, see the [main README](../README.md).

## Files

Keep all four files together in one folder.

| File | Purpose |
|---|---|
| `nas_to_msh.py` | The script you run: the mesh logic |
| `_terminal.py` | Colors, banner, prompts, tables |
| `_groups.py` | Naming rules, number parsing, saved groups |
| `_viewer.py` | Gmsh window that shows the surface numbers |

## Usage

```bash
pip install gmsh
python nas_to_msh.py model.nas
```

| Option | Effect |
|---|---|
| `--groups FILE` | Apply the names from a saved groups file and ask nothing |
| `--overwrite` | Write the names into `<model>.msh` and replace existing files without asking |
| `--verbose` | Show Gmsh's own messages and Python tracebacks |

An interactive run writes `<model>_named.msh` and `<model>_groups.json`. If you answer "n" to naming, it writes `<model>.msh` with the default `surface_N` / `volume_N` names.

## Gmsh Viewer

The script starts the viewer for you when you ask for it. You can also run it by hand on any `.msh` file:

```bash
python _viewer.py model.msh
```

The labels show each surface's physical group tag, which is the surface number in a mesh with default names. To get such a file, run the script and answer "n" to naming. Run directly, the viewer prints any error message, which helps when the window does not open (it needs a graphical display).
