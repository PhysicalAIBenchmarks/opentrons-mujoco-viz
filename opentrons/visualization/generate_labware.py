"""
Generate OBJ meshes from Opentrons shared-data labware JSON definitions.

These meshes can be referenced in MJCF as <mesh file="labware.obj"/> to give
the scene real labware geometry instead of the default box/cylinder primitives.

Usage
-----
    # Single labware
    python -m opentrons.visualization.generate_labware \\
        assets/labware_defs/corning_96_wellplate_360ul_flat/1.json

    # Whole directory
    python -m opentrons.visualization.generate_labware assets/labware_defs/

Output: opentrons/visualization/assets/stl/<loadName>.obj

Requirements
------------
    pip install trimesh
    (Optional) Blender for accurate boolean subtraction of well bores.
    Without Blender, well bores are skipped and the mesh is a plain box.

Auto-download shared-data
-------------------------
    from opentrons.visualization.generate_labware import download_shared_data
    download_shared_data()   # writes to assets/labware_defs/
"""

from __future__ import annotations
import json
import pathlib
import sys

ASSETS_DIR = pathlib.Path(__file__).parent / "assets"


def box_mesh(x: float, y: float, z: float, w: float, d: float, h: float):
    import trimesh
    m = trimesh.creation.box(extents=[w, d, h])
    m.apply_translation([x + w / 2, y + d / 2, z + h / 2])
    return m


def cylinder_mesh(cx: float, cy: float, z_bottom: float, diameter: float, depth: float, segments: int = 16):
    import trimesh
    r = diameter / 2
    m = trimesh.creation.cylinder(radius=r, height=depth, sections=segments)
    m.apply_translation([cx, cy, z_bottom + depth / 2])
    return m


def labware_from_def(def_path: str | pathlib.Path):
    """
    Build a trimesh.Trimesh from an Opentrons labware definition JSON.

    The outer body is a box of the labware's xDimension × yDimension × zDimension.
    If a boolean engine is available (Blender / manifold), well bores are subtracted.
    """
    import trimesh

    with open(def_path) as f:
        defn = json.load(f)

    dims = defn["dimensions"]
    W, D, H = dims["xDimension"], dims["yDimension"], dims["zDimension"]
    body = box_mesh(0, 0, 0, W, D, H)

    wells = defn.get("wells", {})
    bore_meshes = []
    for _, well in wells.items():
        shape = well.get("shape", "circular")
        depth = well.get("depth", 5.0)
        z_top = well.get("z", H)
        z_bottom = z_top - depth
        cx = well.get("x", W / 2)
        cy = well.get("y", D / 2)

        if shape == "circular":
            diameter = well.get("diameter", 6.0)
            bore_meshes.append(cylinder_mesh(cx, cy, z_bottom, diameter, depth))
        else:
            xdim = well.get("xDimension", 8.0)
            ydim = well.get("yDimension", 8.0)
            bore_meshes.append(box_mesh(cx - xdim / 2, cy - ydim / 2, z_bottom, xdim, ydim, depth))

    if bore_meshes:
        try:
            import trimesh.boolean as tbool
            if tbool.exists():
                bores = trimesh.util.concatenate(bore_meshes)
                return body.difference(bores, engine="blender")
        except Exception:
            pass

    return body


def convert_labware(def_path: str | pathlib.Path, out_dir: str | pathlib.Path | None = None) -> pathlib.Path:
    """Convert a single labware definition JSON to OBJ. Returns the output path."""
    def_path = pathlib.Path(def_path)
    out_dir = pathlib.Path(out_dir) if out_dir else ASSETS_DIR / "stl"
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(def_path) as f:
        defn = json.load(f)
    name = defn.get("parameters", {}).get("loadName", def_path.stem)
    mesh = labware_from_def(def_path)
    out = out_dir / f"{name}.obj"
    mesh.export(str(out))
    return out


def download_shared_data(out_dir: str | pathlib.Path | None = None) -> list[pathlib.Path]:
    """
    Download Opentrons shared-data labware definitions from the installed
    opentrons-shared-data package (if installed) or from the GitHub release.

    Returns list of downloaded .json paths.
    """
    out_dir = pathlib.Path(out_dir) if out_dir else ASSETS_DIR / "labware_defs"
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[pathlib.Path] = []

    # Try from installed package first
    try:
        import opentrons_shared_data.labware as sd_lw
        import importlib.resources as pkg_res
        for name in sd_lw.load_definition_by_name.__code__.co_consts:
            if isinstance(name, str) and name.endswith(".json"):
                pass  # enumerate via get_all_shared_data_filenames if available
        # Simpler: locate the package data directory
        import opentrons_shared_data
        data_dir = pathlib.Path(opentrons_shared_data.__file__).parent / "labware" / "definitions" / "2"
        if data_dir.exists():
            for json_path in data_dir.rglob("*.json"):
                dest = out_dir / json_path.name
                dest.write_bytes(json_path.read_bytes())
                written.append(dest)
            print(f"Copied {len(written)} definitions from installed opentrons-shared-data → {out_dir}")
            return written
    except ImportError:
        pass

    # Fallback: fetch from GitHub
    import urllib.request
    import urllib.error

    API_URL = (
        "https://raw.githubusercontent.com/Opentrons/opentrons/edge/"
        "shared-data/labware/definitions/2/"
    )
    INDEX_URL = (
        "https://api.github.com/repos/Opentrons/opentrons/contents/"
        "shared-data/labware/definitions/2"
    )
    try:
        with urllib.request.urlopen(INDEX_URL) as resp:
            import json as _json
            entries = _json.loads(resp.read())
        for entry in entries:
            if entry["type"] == "dir":
                dir_url = entry["url"]
                with urllib.request.urlopen(dir_url) as r2:
                    files = _json.loads(r2.read())
                for fentry in files:
                    if fentry["name"].endswith(".json"):
                        dest = out_dir / f"{entry['name']}_{fentry['name']}"
                        with urllib.request.urlopen(fentry["download_url"]) as r3:
                            dest.write_bytes(r3.read())
                        written.append(dest)
    except Exception as e:
        print(f"Warning: could not fetch shared data: {e}")

    print(f"Downloaded {len(written)} definitions → {out_dir}")
    return written


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m opentrons.visualization.generate_labware <def.json|defs_dir/>")
        sys.exit(1)

    target = pathlib.Path(sys.argv[1])
    out_dir = ASSETS_DIR / "stl"
    paths = list(target.rglob("*.json")) if target.is_dir() else [target]

    for p in paths:
        try:
            out = convert_labware(p, out_dir)
            print(f"  {p.stem} → {out}")
        except Exception as e:
            print(f"  SKIP {p.stem} ({e})")


if __name__ == "__main__":
    main()
