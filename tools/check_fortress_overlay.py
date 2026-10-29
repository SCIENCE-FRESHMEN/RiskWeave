#!/usr/bin/env python3
"""Check Gazebo compatibility mapping without modifying project assets."""
from pathlib import Path
import tempfile
import unittest
from prepare_fortress_assets import prepare, convert


class OverlayChecks(unittest.TestCase):
    def test_identifiers_preserve_geometry_and_pose(self):
        source='<sdf version="1.8"><world name="test"><plugin filename="gz-sim-physics-system" name="gz::sim::systems::Physics"/><pose>1 2 3 0 0 0</pose></world></sdf>'
        result=convert(source)
        self.assertIn('ignition-gazebo-physics-system',result)
        self.assertIn('ignition::gazebo::systems::Physics',result)
        self.assertIn('<pose>1 2 3 0 0 0</pose>',result)
        self.assertEqual(convert(result),result)

    def test_dry_run_then_apply_only_to_supplied_copy(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'riskweave_console').mkdir()
            (root/'riskweave_console/package.xml').write_text('<package/>')
            (root/'robots').mkdir()
            p=root/'robots/world.sdf'
            p.write_text('<sdf><world name="test"><plugin filename="gz-sim-physics-system"/></world></sdf>')
            before=p.read_bytes()
            self.assertEqual(prepare(root)['files_changed'],1)
            self.assertEqual(p.read_bytes(),before)
            self.assertEqual(prepare(root,True)['files_changed'],1)
            self.assertNotEqual(p.read_bytes(),before)
            self.assertEqual(prepare(root,True)['files_changed'],0)


if __name__=='__main__':
    unittest.main(verbosity=2)
