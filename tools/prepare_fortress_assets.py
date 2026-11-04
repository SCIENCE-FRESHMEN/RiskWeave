#!/usr/bin/env python3
"""Map newer Gazebo identifiers in an isolated source copy to Fortress names.

Dry-run by default. This performs identifier compatibility changes, not a
general SDF/URDF version migration, and records every changed file hash.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET


def convert(text):
    return (text.replace('gz-sim-', 'ignition-gazebo-')
            .replace('gz::sim::', 'ignition::gazebo::')
            .replace('gz.msgs.', 'ignition.msgs.'))


def prepare(source, apply=False):
    source = source.resolve()
    if not (source/'riskweave_console/package.xml').is_file() or not (source/'robots').is_dir():
        raise ValueError('Expected the ROS source directory containing riskweave_console/ and robots/')
    changes = []
    staged = []
    for p in sorted((source/'robots').rglob('*')):
        if not p.is_file() or p.suffix.lower() not in {'.sdf','.world','.urdf','.xacro','.yaml','.py'}:
            continue
        before = p.read_bytes()
        text = before.decode('utf-8')
        after = convert(text)
        if after == text:
            continue
        if p.suffix == '.py':
            ast.parse(after)
        elif p.suffix.lower() != '.yaml':
            ET.fromstring(after)
        encoded = after.encode('utf-8')
        staged.append((p,encoded))
        changes.append({'path':p.relative_to(source).as_posix(),
                        'before_sha256':hashlib.sha256(before).hexdigest(),
                        'after_sha256':hashlib.sha256(encoded).hexdigest()})
    if apply:
        for p, data in staged:
            p.write_bytes(data)
    return {'kind':'Fortress_identifier_overlay','applied':apply,'files_changed':len(changes),
            'changes':changes,
            'scope':'Plugin library/class and message identifiers only; physics, geometry and controller correctness require runtime checks.'}


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--apply',action='store_true',help='Modify the explicitly supplied isolated copy')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    result=prepare(args.source,args.apply)
    if args.output:
        args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'kind':result['kind'],'applied':args.apply,'files_changed':result['files_changed']}))
