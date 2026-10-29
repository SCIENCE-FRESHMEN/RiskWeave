#!/usr/bin/env python3
"""Resolve local resources reachable from selected worlds; does not run Gazebo."""
import argparse
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def check(worlds):
    models = {p.parent.name: p.parent for p in (ROOT / 'riskweave/robots').rglob('model.config')}
    packages = {ET.parse(p).getroot().findtext('name'): p.parent for p in ROOT.rglob('package.xml')}
    checked, missing, external, queue = set(), [], [], list(worlds)
    def resolve(uri, source):
        if not uri or uri.startswith('#'):
            return
        if uri.startswith(('http://', 'https://')):
            external.append({'source': source.relative_to(ROOT).as_posix(), 'uri': uri})
            return
        if uri.startswith(('model://', 'package://')):
            scheme, rest = uri.split('://', 1)
            name, _, suffix = rest.partition('/')
            base = (models if scheme == 'model' else packages).get(name)
            target = base / (suffix or 'model.sdf') if base else None
        else:
            target = source.parent / uri.removeprefix('file://').replace('\\', '/')
        if target is None or not target.is_file():
            missing.append({'source': source.relative_to(ROOT).as_posix(), 'uri': uri})
            return
        queue.append(target.resolve())
    while queue:
        path = queue.pop().resolve()
        if path in checked:
            continue
        checked.add(path)
        if path.suffix.lower() in {'.sdf', '.world', '.urdf', '.dae'}:
            tree = ET.parse(path)
            for element in tree.iter():
                tag = element.tag.rsplit('}',1)[-1]
                if tag == 'uri':
                    resolve((element.text or '').strip(), path)
                if tag == 'mesh' and 'filename' in element.attrib:
                    resolve(element.attrib['filename'], path)
                if tag == 'image':
                    for child in element:
                        if child.tag.rsplit('}',1)[-1] == 'init_from':
                            resolve((child.text or '').strip(), path)
        elif path.suffix.lower() in {'.obj', '.mtl'}:
            for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
                if line.startswith(('mtllib ', 'map_Kd ', 'map_Ka ', 'map_Ks ', 'map_Bump ')):
                    resolve(line.split(maxsplit=1)[1].strip(), path)
    return {'kind': 'static_resource_graph', 'files_checked': len(checked),
            'worlds': [p.relative_to(ROOT).as_posix() for p in worlds],
            'missing': missing, 'external': external,
            'limitations': 'No plugin library, SDF runtime semantics, rendering or physics validation.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    worlds = [ROOT / 'riskweave/robots/multi_robot/worlds' / name
              for name in ('food_court.sdf', 'foodcourt_world.sdf', 'foodcourt_world_small.sdf')]
    result = check(worlds)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'files_checked': result['files_checked'], 'missing_count': len(result['missing']),
                      'external_count': len(result['external']), 'missing_sample': result['missing'][:8]}))
    sys.exit(bool(result['missing']))
