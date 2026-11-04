#!/usr/bin/env python3
"""
Opens a Gmsh window that shows the surface numbers of a .msh file.

nas_to_msh.py starts this as a separate process, so the terminal prompts stay
usable while the window is open. To see the full error if the window does not
come up, run it directly:

    python _viewer.py model.msh
"""

import os
import subprocess
import sys
import tempfile

import gmsh

STARTUP_WAIT = 1.5   # seconds to wait before we assume the window is up


def start(msh_file):
    """Launch the viewer in the background.

    Returns (process, None) when it is running, or (None, reason) when it
    stopped right away. A failing viewer is never fatal for the conversion.
    """
    with tempfile.TemporaryFile(mode="w+") as log:
        proc = subprocess.Popen([sys.executable, os.path.abspath(__file__), msh_file],
                                stdout=subprocess.DEVNULL, stderr=log)
        try:
            proc.wait(timeout=STARTUP_WAIT)
        except subprocess.TimeoutExpired:
            return proc, None                      # still running: window is up
        log.seek(0)
        lines = log.read().strip().splitlines()
    return None, (lines[-1] if lines else f"closed right away (exit code {proc.returncode})")


def stop(proc):
    """Close the viewer if it is still open (terminate, then kill if needed)."""
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def show(msh_file):
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


if __name__ == "__main__":
    show(sys.argv[1])
