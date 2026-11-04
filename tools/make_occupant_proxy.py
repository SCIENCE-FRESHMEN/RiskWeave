#!/usr/bin/env python3
"""Generate an explicitly synthetic seated occupant proxy in centimetres.

This is a local procedural replacement for a missing upstream visual asset.
It is not the original paper mesh and is unsuitable for claiming VLM parity.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / 'riskweave/robots/multi_robot/models/sitting_human_01'


def generate():
    lines = ['# Procedural research occupant proxy; not the upstream paper mesh.',
             '# Coordinates are centimetres; world files apply a 0.01 scale.']
    vertices = 0
    def box(name, center, size):
        nonlocal vertices
        lines.append('o ' + name)
        for sx, sy, sz in [(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),
                           (-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]:
            xyz = [center[i] + sign * size[i] / 2 for i, sign in enumerate((sx,sy,sz))]
            lines.append('v ' + ' '.join(f'{v:g}' for v in xyz))
        for face in [(1,4,3,2),(5,6,7,8),(1,2,6,5),(2,3,7,6),(3,4,8,7),(4,1,5,8)]:
            lines.append('f ' + ' '.join(str(vertices + index) for index in face))
        vertices += 8
    box('torso', (0,0,78), (32,20,45))
    box('head', (0,0,113), (20,20,20))
    for sign, side in [(-1,'left'),(1,'right')]:
        box(side+'_thigh', (sign*11,20,49), (12,42,12))
        box(side+'_shin', (sign*11,37,26), (12,12,42))
        box(side+'_foot', (sign*11,43,5), (14,24,8))
        box(side+'_arm', (sign*23,10,76), (10,32,10))
    mesh = MODEL / 'meshes/sitting_human.obj'
    mesh.parent.mkdir(parents=True, exist_ok=True)
    mesh.write_text('\n'.join(lines)+'\n', encoding='utf-8')
    (MODEL/'model.config').write_text('''<?xml version="1.0"?>
<model><name>Procedural research occupant proxy</name><version>1.0</version>
<sdf version="1.6">model.sdf</sdf>
<description>Locally generated box-based seated occupant. Replaces a missing mesh for resource closure; NOT an original paper asset.</description></model>
''', encoding='utf-8')
    (MODEL/'model.sdf').write_text('''<?xml version="1.0"?>
<sdf version="1.6"><model name="research_occupant_proxy"><static>true</static>
<link name="body"><visual name="procedural_proxy"><geometry><mesh>
<uri>model://sitting_human_01/meshes/sitting_human.obj</uri><scale>0.01 0.01 0.01</scale>
</mesh></geometry><material><ambient>0.5 0.5 0.5 1</ambient><diffuse>0.5 0.5 0.5 1</diffuse></material>
</visual></link></model></sdf>
''', encoding='utf-8')
    return mesh


if __name__ == '__main__':
    print(generate().relative_to(ROOT))
