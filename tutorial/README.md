# pitzDaily – Alternative mesh sources

This tutorial supports two mesh-generation options:

- **`blockMesh`**: Generate the mesh using `system/blockMeshDict`.
- **`nas`**: Import a COMSOL NASTRAN mesh (`.nas`) using [`comsol-to-openfoam-mesh`](https://github.com/Ali-shaha/comsol-to-openfoam-mesh) and `gmshToFoam`.

## Usage

Run interactively:

```bash
./Allrun
```

Or specify the mesh source directly:

```bash
./Allrun blockMesh   # Use blockMesh
./Allrun nas         # Use COMSOL/NASTRAN mesh
```

For the NASTRAN option, Python 3, the Gmsh Python module, and the mesh converter are required. Configure the converter path and input mesh in `Allrun`.

The script also assigns the required patch types and runs the simulation.