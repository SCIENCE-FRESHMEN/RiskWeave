#!/usr/bin/env python3
"""Offline syntax, hygiene and portable mesh-reference checks (standard library)."""
import ast
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]


def verify():
    # Prune before calling stat: Linux symlinks in ignored Docker/colcon logs
    # may be unreadable on Windows and must not break a source-only scan.
    excluded = {'.git', '__pycache__', '.venv', 'build', 'install', 'artifacts', '.pytest_cache'}
    files = []
    for directory, directories, names in os.walk(ROOT, followlinks=False):
        directories[:] = sorted(name for name in directories if name not in excluded)
        for name in names:
            path = Path(directory) / name
            if not path.is_symlink() and path.is_file():
                files.append(path)
    files.sort()
    counts = {'python': 0, 'json': 0, 'xml': 0, 'utf8_files_scanned': 0}
    errors = []
    identity = json.loads((ROOT / 'project.json').read_text(encoding='utf-8'))
    console = ROOT / identity['source_directory'] / identity['console_package']
    manifest = console / 'package.xml'
    if ET.parse(manifest).getroot().findtext('name') != identity['console_package']:
        errors.append({'path': manifest.relative_to(ROOT).as_posix(), 'issue': 'project_package_identity_mismatch'})
    for required in [console / 'resource' / identity['console_package'],
                     console / identity['console_package'] / (identity['replanning_executable'] + '.py'),
                     console / 'launch' / identity['main_launch'],
                     console / 'launch' / identity['replanning_launch']]:
        if not required.is_file():
            errors.append({'path': required.relative_to(ROOT).as_posix(), 'issue': 'missing_renamed_entry'})
    # Previous names are allowed only in unchanged upstream attribution evidence.
    retired = re.compile(r'co' r'muros|chat' r'ty', re.I)
    attribution = {'docs/ORIGIN.md', 'docs/upstream_license_check.json'}
    # Report paths and line numbers, never matched credential values.
    patterns = {
        'credential_like_value': re.compile(
            r'sk-(?:proj-)?[A-Za-z0-9_-]{20,}|AIza[A-Za-z0-9_-]{30,}'
            r'|xai-[A-Za-z0-9_-]{20,}|-----BEGIN (?:RSA |OPENSSH )?PRIVATE KEY-----'),
        'developer_home_path': re.compile(r'(?:file://)?/' r'home/[^\s<>\"\x27]+|[A-Za-z]:\\Users\\'),
    }
    for p in files:
        rel = p.relative_to(ROOT).as_posix()
        data = p.read_bytes()
        if p.name == '.DS_Store':
            errors.append({'path': rel, 'issue': 'directory_metadata'})
        if p.parent.name == 'data' and p.suffix == '.txt' and data:
            errors.append({'path': rel, 'issue': 'nonempty_bundled_history'})
        try:
            text = data.decode('utf-8-sig')
        except UnicodeDecodeError:
            continue
        if '\x00' in text:
            continue
        if retired.search(rel) or (rel not in attribution and retired.search(text)):
            errors.append({'path': rel, 'issue': 'retired_project_identifier'})
        counts['utf8_files_scanned'] += 1
        for label, pattern in patterns.items():
            for match in pattern.finditer(text):
                errors.append({'path': rel, 'line': text.count('\n', 0, match.start()) + 1,
                               'issue': label})
        kind = None
        try:
            if p.suffix == '.py':
                kind = 'python'
                ast.parse(text, filename=rel)
            elif p.suffix == '.json':
                kind = 'json'
                json.loads(text)
            elif p.suffix.lower() in {'.xml', '.sdf', '.world', '.urdf', '.xacro', '.config', '.dae'}:
                kind = 'xml'
                ET.fromstring(text)
        except (SyntaxError, ValueError, ET.ParseError) as exc:
            errors.append({'path': rel, 'issue': 'parse_error', 'detail': str(exc)})
        if kind:
            counts[kind] += 1

    pkg = ROOT / 'riskweave/robots/yahboom/yahboom_rosmaster_description'
    urdf = pkg / 'urdf/robots/rosmaster_x3.urdf'
    meshes = re.findall(r'filename="package://yahboom_rosmaster_description/([^\"]+)"',
                        urdf.read_text(encoding='utf-8'))
    for mesh in meshes:
        if not (pkg / mesh).is_file():
            errors.append({'path': urdf.relative_to(ROOT).as_posix(),
                           'issue': 'missing_package_mesh', 'resource': mesh})
    for setup in ROOT.rglob('setup.py'):
        text = setup.read_text(encoding='utf-8')
        if re.search(r"glob\('data2?/\*'\)", text):
            errors.append({'path': setup.relative_to(ROOT).as_posix(),
                           'issue': 'runtime_data_packaged'})

    return {
        'scope': 'Current workspace UTF-8 text, syntax and selected local resource references',
        'counts': counts,
        'project': identity['name'],
        'console_package': identity['console_package'],
        'retired_identifiers_allowed_only_in_attribution': True,
        'package_mesh_references_checked': len(meshes),
        'errors': errors,
        'dependencies_available': {name: importlib.util.find_spec(name) is not None
                                   for name in ('rclpy', 'launch', 'colcon_core')},
        'limitations': [
            'This checker does not exercise ROS, Gazebo, physical robots or cloud APIs; see environment_probe.json for separate checks.',
            'Credential matching is heuristic; binary payloads and image pixels are not scanned.',
            'Third-party public attribution and contact metadata are retained.',
            'A procedural occupant proxy replaces a missing upstream mesh; original visual equivalence is not established.',
            'Decorative photos/screenshots were removed by editing material bindings; full high-resolution OCR was not run.',
        ],
    }


if __name__ == '__main__':
    result = verify()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(bool(result['errors']))
