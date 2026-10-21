#!/usr/bin/env python3
"""Export a two-colour keycap as a Bambu Studio / OrcaSlicer 3MF.

Renders the cap and the legend separately with OpenSCAD and packs them as two
parts of ONE object, so the legend keeps its own filament/colour.

Usage:
    python3 export_3mf.py "Q"                      # -> keycap_Q.3mf
    python3 export_3mf.py "Shift" -D units=2.25 -o shift.3mf
    python3 export_3mf.py "Esc" -D 'font="DejaVu Sans:style=Bold"' --legend-filament 3

Any -D option is passed straight to OpenSCAD (same names as the Customizer).
"""
import argparse
import json
import os
import re
import struct
import subprocess
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCAD = os.path.join(HERE, "cherry_mx_keycap.scad")
# Printer/filament settings embedded in the 3MF (taken from special_keycaps.3mf).
# Bambu Studio needs these to open the file with the right printer and colours.
PROJECT_SETTINGS = os.path.join(HERE, "bambu_project_settings.config")


def read_stl(path):
    """Return (vertices, triangles) with shared vertices de-duplicated."""
    with open(path, "rb") as f:
        data = f.read()
    tris = []
    if data[:5] == b"solid" and b"facet" in data[:300]:
        nums = re.findall(rb"vertex\s+(\S+)\s+(\S+)\s+(\S+)", data)
        pts = [tuple(float(c) for c in n) for n in nums]
        tris = [pts[i:i + 3] for i in range(0, len(pts), 3)]
    else:
        (n,) = struct.unpack_from("<I", data, 80)
        for i in range(n):
            v = struct.unpack_from("<9f", data, 84 + i * 50 + 12)
            tris.append([v[0:3], v[3:6], v[6:9]])
    index, verts, faces = {}, [], []
    for tri in tris:
        ids = []
        for p in tri:
            key = tuple(round(c, 5) for c in p)
            if key not in index:
                index[key] = len(verts)
                verts.append(key)
            ids.append(index[key])
        if len(set(ids)) == 3:
            faces.append(ids)
    return verts, faces


def render(part, defines, out):
    cmd = ["openscad", "-q", "-o", out, "-D", f'part="{part}"']
    for d in defines:
        cmd += ["-D", d]
    cmd.append(SCAD)
    r = subprocess.run(cmd)
    if r.returncode and part == "cap":
        sys.exit("OpenSCAD failed")


def mesh_xml(obj_id, verts, faces):
    v = "\n".join(f'     <vertex x="{x:g}" y="{y:g}" z="{z:g}"/>' for x, y, z in verts)
    t = "\n".join(f'     <triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in faces)
    return (f'  <object id="{obj_id}" p:UUID="{obj_id:08x}-81cb-4c03-9d28-80fed5dfa1dc" type="model">\n   <mesh>\n    <vertices>\n{v}\n'
            f'    </vertices>\n    <triangles>\n{t}\n    </triangles>\n   </mesh>\n  </object>')


NS = ('xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
      'xmlns:BambuStudio="http://schemas.bambulab.com/package/2021" '
      'xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06" '
      'requiredextensions="p"')


def write_3mf(out, name, parts, colours=None, bed_center=(128, 128)):
    """parts: list of (part_name, filament, verts, faces)."""
    sub_objects = "\n".join(mesh_xml(i + 1, v, f) for i, (_, _, v, f) in enumerate(parts))
    sub_model = (f'<?xml version="1.0" encoding="UTF-8"?>\n<model unit="millimeter" {NS}>\n'
                 f' <metadata name="BambuStudio:3mfVersion">1</metadata>\n'
                 f' <resources>\n{sub_objects}\n </resources>\n <build/>\n</model>\n')

    obj_id = len(parts) + 1
    comps = "\n".join(f'    <component p:path="/3D/Objects/object_1.model" objectid="{i + 1}" '
                      f'p:UUID="{i + 1:04x}0000-b206-40ff-9872-83e8017abed1" transform="1 0 0 0 1 0 0 0 1 0 0 0"/>' for i in range(len(parts)))
    cx, cy = bed_center
    main_model = (f'<?xml version="1.0" encoding="UTF-8"?>\n<model unit="millimeter" xml:lang="en-US" {NS}>\n'
                  f' <metadata name="Application">BambuStudio-02.07.01.57</metadata>\n'
                  f' <metadata name="BambuStudio:3mfVersion">1</metadata>\n'
                  f' <resources>\n  <object id="{obj_id}" p:UUID="{obj_id:08x}-61cb-4c03-9d28-80fed5dfa1dc" type="model">\n   <components>\n{comps}\n'
                  f'   </components>\n  </object>\n </resources>\n'
                  f' <build p:UUID="2c7c17d8-22b5-4d84-8835-1976022ea369">\n'
                  f'  <item objectid="{obj_id}" p:UUID="{obj_id:08x}-b1ec-4553-aec9-835e5b724bb4" transform="1 0 0 0 1 0 0 0 1 {cx} {cy} 0" printable="1"/>\n'
                  f' </build>\n</model>\n')

    part_cfg = "\n".join(
        f'    <part id="{i + 1}" subtype="normal_part">\n'
        f'      <metadata key="name" value="{pname}"/>\n'
        f'      <metadata key="matrix" value="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"/>\n'
        f'      <metadata key="extruder" value="{fil}"/>\n'
        f'      <mesh_stat face_count="{len(faces)}" edges_fixed="0" degenerate_facets="0" '
        f'facets_removed="0" facets_reversed="0" backwards_edges="0"/>\n'
        f'    </part>'
        for i, (pname, fil, _, faces) in enumerate(parts))
    settings = (f'<?xml version="1.0" encoding="UTF-8"?>\n<config>\n  <object id="{obj_id}">\n'
                f'    <metadata key="name" value="{name}"/>\n'
                f'    <metadata key="extruder" value="{parts[0][1]}"/>\n{part_cfg}\n  </object>\n'
                f'  <plate>\n    <metadata key="plater_id" value="1"/>\n'
                f'    <model_instance>\n      <metadata key="object_id" value="{obj_id}"/>\n'
                f'      <metadata key="instance_id" value="0"/>\n    </model_instance>\n  </plate>\n'
                f'</config>\n')

    content_types = ('<?xml version="1.0" encoding="UTF-8"?>\n'
                     '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
                     ' <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>\n'
                     ' <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>\n'
                     '</Types>\n')
    rels = ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
            ' <Relationship Target="/3D/3dmodel.model" Id="rel-1" '
            'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>\n</Relationships>\n')
    model_rels = ('<?xml version="1.0" encoding="UTF-8"?>\n'
                  '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
                  ' <Relationship Target="/3D/Objects/object_1.model" Id="rel-1" '
                  'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>\n</Relationships>\n')

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels)
        z.writestr("3D/3dmodel.model", main_model)
        z.writestr("3D/_rels/3dmodel.model.rels", model_rels)
        z.writestr("3D/Objects/object_1.model", sub_model)
        z.writestr("Metadata/model_settings.config", settings)
        if os.path.exists(PROJECT_SETTINGS):
            with open(PROJECT_SETTINGS) as f:
                project = json.load(f)
            for i, c in (colours or {}).items():
                fc = project.setdefault("filament_colour", [])
                while len(fc) < i:
                    fc.append(fc[-1] if fc else "#FFFFFFFF")
                fc[i - 1] = c
            z.writestr("Metadata/project_settings.config", json.dumps(project, indent=4))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("legend", help="text on top of the key")
    ap.add_argument("-D", dest="defines", action="append", default=[],
                    help="extra OpenSCAD variable, e.g. -D units=1.5")
    ap.add_argument("-o", "--output")
    ap.add_argument("--cap-filament", type=int, default=1)
    ap.add_argument("--legend-filament", type=int, default=2)
    ap.add_argument("--cap-colour", help="hex colour for the cap filament slot, e.g. #1E1E1E")
    ap.add_argument("--legend-colour", help="hex colour for the legend filament slot, e.g. #FFFFFF")
    args = ap.parse_args()

    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", args.legend) or "blank"
    out = args.output or os.path.join(HERE, f"keycap_{safe}.3mf")
    legend_lit = args.legend.replace("\\", "\\\\").replace('"', '\\"')
    defines = [f'legend="{legend_lit}"'] + args.defines

    with tempfile.TemporaryDirectory() as tmp:
        parts = []
        for part, fil in (("cap", args.cap_filament), ("legend", args.legend_filament)):
            stl = os.path.join(tmp, f"{part}.stl")
            render(part, defines, stl)
            verts, faces = read_stl(stl) if os.path.exists(stl) and os.path.getsize(stl) else ([], [])
            if faces:
                parts.append((part, fil, verts, faces))
        if not parts:
            sys.exit("nothing rendered")
        colours = {}
        if args.cap_colour:
            colours[args.cap_filament] = args.cap_colour
        if args.legend_colour:
            colours[args.legend_filament] = args.legend_colour
        write_3mf(out, f"keycap_{safe}", parts, colours)
    print(f"wrote {out} ({', '.join(f'{p[0]}: filament {p[1]}' for p in parts)})")


if __name__ == "__main__":
    main()
