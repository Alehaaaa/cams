"""SpaceSwitch regression coverage with Maya 2024 and real Qt widgets."""
import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "source")))

from PySide2 import QtCore, QtWidgets

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

import maya.standalone

maya.standalone.initialize()

from maya import cmds

from aleha_tools import spaceswitch


class _Owner(object):
    fast_rotation_order = False


class SpaceSwitchTests(unittest.TestCase):
    def setUp(self):
        cmds.file(new=True, force=True)
        self.settings = QtCore.QSettings(
            spaceswitch.DATA.get("AUTHOR", {}).get("name", "Alehaaa"),
            spaceswitch.DATA.get("TOOL"),
        )
        self.settings.clear()

    def tearDown(self):
        for widget in list(app.topLevelWidgets()):
            if isinstance(widget, spaceswitch.FloatingWidget):
                widget.close()
                widget.deleteLater()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        self.settings.clear()

    @staticmethod
    def _enum_control(name="ctrl", enum_name="World:Chest=3:Head"):
        node = cmds.createNode("transform", name=name)
        cmds.addAttr(node, longName="space", attributeType="enum", enumName=enum_name, keyable=True)
        return node

    def test_sparse_enum_values_are_preserved(self):
        node = self._enum_control()
        items = spaceswitch.Maya.enum_items(node, "space")
        self.assertEqual(items, [("World", 0), ("Chest", 3), ("Head", 4)])

        builder = spaceswitch.SwitchCatalogBuilder(spaceswitch.GimbalAnalyzer())
        entry = builder.custom_entry(node, "space")[0][2].to_dict()
        self.assertEqual(entry["enum_values"], [0, 3, 4])

    def test_selection_discovery_requires_connection_but_custom_does_not(self):
        node = self._enum_control()
        builder = spaceswitch.SwitchCatalogBuilder(spaceswitch.GimbalAnalyzer())
        self.assertNotIn("space", builder.local_catalog([node]))
        self.assertIn("space", builder.custom_catalog([node], ["ctrl.space"]))

        condition = cmds.createNode("condition")
        cmds.connectAttr(node + ".space", condition + ".firstTerm")
        self.assertIn("space", builder.local_catalog([node]))

    def test_asset_catalog_finds_controls_in_namespace(self):
        cmds.namespace(add="hero")
        node = self._enum_control("hero:hand_CTRL")
        shape = cmds.createNode("nurbsCurve", name="hero:hand_CTRLShape", parent=node)
        self.assertTrue(cmds.objExists(shape))
        condition = cmds.createNode("condition", name="hero:space_condition")
        cmds.connectAttr(node + ".space", condition + ".firstTerm")

        builder = spaceswitch.SwitchCatalogBuilder(spaceswitch.GimbalAnalyzer())
        catalog = builder.asset_catalog("hero", [])
        self.assertTrue(catalog)
        rows = [item for data in catalog.values() for item in data["objects"].values()]
        self.assertTrue(any(item["attr_node"] == node and item["attr"] == "space" for item in rows))

    def test_switch_preserves_world_pose_and_is_one_undo(self):
        parent = cmds.createNode("transform", name="space_grp")
        control = cmds.createNode("transform", name="ctrl", parent=parent)
        cmds.addAttr(control, longName="space", attributeType="enum", enumName="World:Offset", keyable=True)
        condition = cmds.createNode("condition", name="space_condition")
        cmds.setAttr(condition + ".secondTerm", 1)
        cmds.setAttr(condition + ".colorIfTrueR", 10.0)
        cmds.setAttr(condition + ".colorIfFalseR", 0.0)
        cmds.connectAttr(control + ".space", condition + ".firstTerm")
        cmds.connectAttr(condition + ".outColorR", parent + ".translateX")
        cmds.setAttr(control + ".translateX", 2.0)
        before = cmds.xform(control, query=True, worldSpace=True, matrix=True)

        operation = spaceswitch.SwitchOperation(control, control, "space", 1, "Offset")
        executor = spaceswitch.SwitchExecutor(_Owner())
        with spaceswitch.UndoChunk("SpaceSwitchTest"):
            changed = executor.apply_requests([([operation], False)], False, [1.0, 1.0])

        after = cmds.xform(control, query=True, worldSpace=True, matrix=True)
        self.assertEqual(changed, {control})
        self.assertEqual(cmds.getAttr(control + ".space"), 1)
        self.assertTrue(all(abs(a - b) < 1e-6 for a, b in zip(before, after)))

        cmds.undo()
        self.assertEqual(cmds.getAttr(control + ".space"), 0)
        undone = cmds.xform(control, query=True, worldSpace=True, matrix=True)
        self.assertTrue(all(abs(a - b) < 1e-6 for a, b in zip(before, undone)))

    def test_current_frame_switch_preserves_neighboring_animation(self):
        parent = cmds.createNode("transform", name="space_offset")
        control = self._enum_control("animated_ctrl", "World:Offset")
        control = cmds.parent(control, parent)[0]
        condition = cmds.createNode("condition", name="space_condition")
        cmds.setAttr(condition + ".secondTerm", 1)
        cmds.setAttr(condition + ".colorIfTrueR", 10)
        cmds.connectAttr(control + ".space", condition + ".firstTerm")
        cmds.connectAttr(condition + ".outColorR", parent + ".translateX")
        for frame, x in ((1, 0), (5, 4), (10, 9)):
            cmds.setKeyframe(control, attribute="translateX", time=frame, value=x)
        cmds.setKeyframe(control, attribute="space", time=1, value=0)
        cmds.setKeyframe(control, attribute="space", time=10, value=0)
        cmds.currentTime(5)
        before = {frame: cmds.getAttr(control + ".worldMatrix[0]", time=frame)
                  for frame in (1, 5, 10)}

        operation = spaceswitch.SwitchOperation(control, control, "space", 1)
        executor = spaceswitch.SwitchExecutor(_Owner())
        with spaceswitch.UndoChunk("PartialSpaceSwitch"):
            executor.apply_requests([([operation], False)], False, [5, 5])

        for frame in (1, 5, 10):
            after = cmds.getAttr(control + ".worldMatrix[0]", time=frame)
            self.assertTrue(all(abs(a - b) < 1e-5 for a, b in zip(before[frame], after)),
                            "World pose changed at frame %s: %r -> %r; tx=%s; space=%s" %
                            (frame, before[frame], after,
                             cmds.getAttr(control + ".translateX", time=frame),
                             cmds.getAttr(control + ".space", time=frame)))
        self.assertEqual(cmds.getAttr(control + ".space", time=5), 1)
        self.assertEqual(cmds.getAttr(control + ".space", time=10), 0)

    def test_all_keys_preserves_world_pose_on_each_animated_frame(self):
        parent = cmds.createNode("transform", name="all_keys_offset")
        control = cmds.createNode("transform", name="all_keys_ctrl", parent=parent)
        cmds.addAttr(control, longName="space", attributeType="enum",
                     enumName="World:Offset", keyable=True)
        condition = cmds.createNode("condition", name="all_keys_condition")
        cmds.setAttr(condition + ".secondTerm", 1)
        cmds.setAttr(condition + ".colorIfTrueR", 12)
        cmds.connectAttr(control + ".space", condition + ".firstTerm")
        cmds.connectAttr(condition + ".outColorR", parent + ".translateX")
        for frame, x in ((1, 0), (5, 4), (10, 9)):
            cmds.setKeyframe(control, attribute="translateX", time=frame, value=x)
        before = {frame: cmds.getAttr(control + ".worldMatrix[0]", time=frame)
                  for frame in (1, 5, 10)}

        operation = spaceswitch.SwitchOperation(control, control, "space", 1)
        with spaceswitch.UndoChunk("AllKeysSpaceSwitch"):
            changed = spaceswitch.SwitchExecutor(_Owner()).apply_requests(
                [([operation], True)], False, [1, 10])

        self.assertEqual(changed, {control})
        for frame in (1, 5, 10):
            self.assertEqual(cmds.getAttr(control + ".space", time=frame), 1)
            after = cmds.getAttr(control + ".worldMatrix[0]", time=frame)
            self.assertTrue(all(abs(a - b) < 1e-5 for a, b in zip(before[frame], after)),
                            "World pose changed at frame %s: %r -> %r" %
                            (frame, before[frame], after))

    def test_asset_view_and_add_switch_controls_exist(self):
        parent = QtWidgets.QWidget()
        widget = spaceswitch.SpaceSwitchAlehaWidget(popup=False, parent=parent)
        widget.show()
        app.processEvents()
        self.assertTrue(hasattr(widget, "view_button"))
        self.assertTrue(any(button.text() == "Add Switch" for button in widget.findChildren(QtWidgets.QPushButton)))
        widget.toggle_asset_view()
        self.assertTrue(widget.asset_view)
        self.assertIn(widget.selection_title.text(), ("Asset", "Scene"))
        widget.close()
        parent.close()

    def test_long_operation_marshals_maya_work_to_main_thread(self):
        node = cmds.createNode("transform", name="threaded_ctrl")
        runner = spaceswitch.OperationRunner("Threaded SpaceSwitch Test")

        def coordinator(active_runner):
            active_runner.set_total(9)
            for value in range(9):
                active_runner.main(cmds.setAttr, node + ".translateX", float(value))
                active_runner.step()
            return active_runner.main(cmds.getAttr, node + ".translateX")

        result = runner.run(coordinator, 9)
        self.assertTrue(runner.threaded)
        self.assertEqual(runner.done, 9)
        self.assertEqual(result, 8.0)

    def test_current_scope_ignores_graph_editor_key_selection(self):
        node = self._enum_control()
        cmds.setKeyframe(node, attribute="space", time=1, value=0)
        cmds.setKeyframe(node, attribute="space", time=8, value=3)
        cmds.selectKey(node + ".space", time=(8, 8), add=True)
        cmds.currentTime(3)
        operation = spaceswitch.SwitchOperation(node, node, "space", 4, "Head")
        executor = spaceswitch.SwitchExecutor(_Owner())
        jobs, _fast = executor._plan([([operation], False)], False, [3, 3])
        self.assertEqual(jobs[0]["frames"], [3.0])
        self.assertEqual(spaceswitch.AttributePopup.CURRENT_KEYFRAMES, "Current Key(s)")

    def test_all_keys_uses_translate_rotate_and_switch_keys_not_scale_only(self):
        node = self._enum_control()
        cmds.setKeyframe(node, attribute="translateX", time=2, value=1)
        cmds.setKeyframe(node, attribute="rotateY", time=4, value=20)
        cmds.setKeyframe(node, attribute="scaleX", time=6, value=2)
        cmds.setKeyframe(node, attribute="space", time=8, value=3)
        operation = spaceswitch.SwitchOperation(node, node, "space", 4, "Head")
        frames = spaceswitch.SwitchExecutor(_Owner()).collect_frames(
            [operation], True, False, [1, 10])
        self.assertEqual(frames, [2.0, 4.0, 8.0])

    def test_custom_switch_name_is_applied_by_attribute_identity(self):
        node = self._enum_control()
        widget_parent = QtWidgets.QWidget()
        widget = spaceswitch.SpaceSwitchAlehaWidget(popup=False, parent=widget_parent)
        widget._set_custom_names({"ctrl.space": "Hand Follow"})
        catalog = spaceswitch.SwitchCatalogBuilder(
            spaceswitch.GimbalAnalyzer()).custom_catalog([node], ["ctrl.space"])
        customized = widget._apply_target_overrides(catalog)
        self.assertEqual(customized["space"]["long"], "Hand Follow")
        widget.close()
        widget_parent.close()

    def test_gimbal_ranking_uses_average_and_worst_frame(self):
        node = cmds.createNode("transform", name="gimbal_ctrl")
        cmds.setKeyframe(node, attribute="rotateY", time=1, value=0)
        cmds.setKeyframe(node, attribute="rotateY", time=2, value=90)
        analyzer = spaceswitch.GimbalAnalyzer()
        scores = analyzer.compute_all_scores(node, analyzer.rotation_order_list(node))
        xyz = scores[0]
        self.assertAlmostEqual(xyz["average"], 50.0)
        self.assertAlmostEqual(xyz["maximum"], 100.0)
        self.assertAlmostEqual(xyz["percentage"], 75.0)
        self.assertEqual(analyzer.classify([10, 25, 45, 60]),
                         ["Best", "Good", "OK", ""])


if __name__ == "__main__":
    success = unittest.main(exit=False).result.wasSuccessful()
    maya.standalone.uninitialize()
    sys.exit(0 if success else 1)
