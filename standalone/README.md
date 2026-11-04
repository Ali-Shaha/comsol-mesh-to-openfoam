# nas-to-msh: standalone version

A single-file version for when you want something small to read or copy. It converts a Nastran (`.nas`) mesh, for example one exported from COMSOL, to a Gmsh MSH 2.2 file with named surfaces and volumes for `gmshToFoam`. For the background and the COMSOL export settings, see the [main README](../README.md).

## Usage

```bash
pip install gmsh
python nas_to_msh.py model.nas
```

| Option | Effect |
|---|---|
| `--overwrite` | Write the names into `<model>.msh` instead of `<model>_named.msh` |

The script always writes `<model>.msh` first, with default `surface_N` / `volume_N` names, then asks whether you want to name them. If you do, it also writes `<model>_named.msh`. Existing files are replaced without asking.
