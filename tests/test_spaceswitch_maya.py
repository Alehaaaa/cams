"""SpaceSwitch regression coverage with Maya 2024 and real Qt widgets."""
import os
import sys
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "source")))

from PySide2 import QtCore, QtTest, QtWidgets

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

import maya.standalone

maya.standalone.initialize()

from maya import cmds

from aleha_tools import spaceswitch


class _Owner(object):
    fast_rotation_order = False


class _FastOwner(object):
    fast_rotation_order = True


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

    def test_current_frame_switch_preserves_intermediate_world_trajectory(self):
        offset = cmds.createNode("transform", name="trajectory_offset")
        control = self._enum_control("trajectory_ctrl", "World:Offset")
        control = cmds.parent(control, offset)[0]
        condition = cmds.createNode("condition", name="trajectory_condition")
        cmds.setAttr(condition + ".secondTerm", 1)
        cmds.setAttr(condition + ".colorIfTrueR", 10)
        cmds.connectAttr(control + ".space", condition + ".firstTerm")
        cmds.connectAttr(condition + ".outColorR", offset + ".translateX")
        cmds.setKeyframe(control, attribute="translateX", time=1, value=2)
        cmds.setKeyframe(control, attribute="translateX", time=10, value=8)
        cmds.keyTangent(control + ".translateX", edit=True,
                        time=(1, 10), inTangentType="spline", outTangentType="spline")
        cmds.currentTime(5)
        samples = [1 + i * 0.25 for i in range(37)]
        before = {frame: cmds.getAttr(control + ".worldMatrix[0]", time=frame)
                  for frame in samples}
        with spaceswitch.UndoChunk("TrajectorySwitch"):
            spaceswitch.SwitchExecutor(_Owner()).apply_requests(
                [([spaceswitch.SwitchOperation(control, control, "space", 1)], False)],
                False, [5, 5])
        self.assertEqual(cmds.getAttr(control + ".space", time=4), 0)
        self.assertEqual(cmds.getAttr(control + ".space", time=5), 1)
        self.assertEqual(cmds.getAttr(control + ".space", time=10), 0)
        for frame in samples:
            actual = cmds.getAttr(control + ".worldMatrix[0]", time=frame)
            self.assertTrue(all(abs(a-b) < 1e-4 for a, b in zip(before[frame], actual)),
                            "World trajectory changed at frame %s: %s -> %s"
                            % (frame, before[frame], actual))
        cmds.undo()
        for frame in samples:
            self.assertTrue(all(abs(a-b) < 1e-5 for a, b in zip(
                before[frame], cmds.getAttr(control + ".worldMatrix[0]", time=frame))))

    def test_subframe_probe_detects_curve_shape_error_between_baked_keys(self):
        offset = cmds.createNode("transform", name="subframe_offset")
        control = self._enum_control("subframe_ctrl", "World:Offset")
        control = cmds.parent(control, offset)[0]
        condition = cmds.createNode("condition", name="subframe_condition")
        cmds.setAttr(condition + ".secondTerm", 1)
        cmds.setAttr(condition + ".colorIfTrueR", 8)
        cmds.connectAttr(control + ".space", condition + ".firstTerm")
        cmds.connectAttr(condition + ".outColorR", offset + ".translateX")
        cmds.setKeyframe(control, attribute="translateX", time=1, value=2)
        cmds.setKeyframe(control, attribute="translateX", time=10, value=8)
        cmds.keyTangent(control + ".translateX", edit=True, inTangentType="spline",
                        outTangentType="spline")
        samples = [1 + i * 0.125 for i in range(73)]
        before = {t: cmds.getAttr(control + ".worldMatrix[0]", time=t) for t in samples}
        cmds.currentTime(5)
        with spaceswitch.UndoChunk("SubframeSwitch"):
            spaceswitch.SwitchExecutor(_Owner()).apply_requests(
                [([spaceswitch.SwitchOperation(control, control, "space", 1)], False)],
                False, [5, 5])
        error = max(abs(before[t][12] - cmds.getAttr(control + ".worldMatrix[0]", time=t)[12])
                    for t in samples)
        self.assertLess(error, 0.001, "Unexpected subframe world trajectory error: %g" % error)

    def test_adaptive_compensation_with_flat_and_linear_tangents_and_undo(self):
        offset = cmds.createNode("transform", name="weighted_offset")
        control = self._enum_control("weighted_ctrl", "World:Offset")
        control = cmds.parent(control, offset)[0]
        condition = cmds.createNode("condition", name="weighted_condition")
        cmds.setAttr(condition + ".secondTerm", 1)
        cmds.setAttr(condition + ".colorIfTrueR", 9)
        cmds.connectAttr(control + ".space", condition + ".firstTerm")
        cmds.connectAttr(condition + ".outColorR", offset + ".translateX")
        cmds.setKeyframe(control + ".translateX", time=1, value=3)
        cmds.setKeyframe(control + ".translateX", time=10, value=13)
        cmds.keyTangent(control + ".translateX", edit=True, time=(1, 1),
                        inTangentType="flat", outTangentType="flat")
        cmds.keyTangent(control + ".translateX", edit=True, time=(10, 10),
                        inTangentType="linear", outTangentType="linear")
        sample_times = [1 + index / 16.0 for index in range(145)]
        expected = {time: cmds.getAttr(control + ".worldMatrix[0]", time=time)[12]
                    for time in sample_times}
        cmds.currentTime(5)
        with spaceswitch.UndoChunk("AdaptiveTangents"):
            spaceswitch.SwitchExecutor(_Owner()).apply_requests(
                [([spaceswitch.SwitchOperation(control, control, "space", 1)], False)],
                False, [5, 5])
        self.assertLess(max(abs(cmds.getAttr(control + ".worldMatrix[0]", time=t)[12] - expected[t])
                            for t in sample_times), 0.002)
        cmds.undo()
        self.assertEqual(cmds.getAttr(control + ".space", time=5), 0)

    def test_timeline_range_preserves_motion_outside_selected_interval(self):
        offset = cmds.createNode("transform", name="range_motion_offset")
        control = self._enum_control("range_motion_ctrl", "World:Offset")
        control = cmds.parent(control, offset)[0]
        condition = cmds.createNode("condition", name="range_motion_condition")
        cmds.setAttr(condition + ".secondTerm", 1)
        cmds.setAttr(condition + ".colorIfTrueR", 11)
        cmds.connectAttr(control + ".space", condition + ".firstTerm")
        cmds.connectAttr(condition + ".outColorR", offset + ".translateX")
        cmds.setKeyframe(control, attribute="translateX", time=1, value=1)
        cmds.setKeyframe(control, attribute="translateX", time=5, value=8)
        cmds.setKeyframe(control, attribute="translateX", time=10, value=3)
        samples = range(1, 11)
        before = {t: cmds.getAttr(control + ".worldMatrix[0]", time=t) for t in samples}
        cmds.currentTime(5)
        with spaceswitch.UndoChunk("RangeMotionSwitch"):
            spaceswitch.SwitchExecutor(_Owner()).apply_requests(
                [([spaceswitch.SwitchOperation(control, control, "space", 1)], False)],
                True, [4, 8])
        self.assertEqual(cmds.getAttr(control + ".space", time=3), 0)
        self.assertEqual(cmds.getAttr(control + ".space", time=5), 1)
        self.assertEqual(cmds.getAttr(control + ".space", time=8), 0)
        for t in samples:
            self.assertTrue(all(abs(a-b) < 1e-4 for a, b in zip(
                before[t], cmds.getAttr(control + ".worldMatrix[0]", time=t))),
                "Selected-range world trajectory changed at %s" % t)
        cmds.undo()
        self.assertEqual(cmds.getAttr(control + ".space", time=5), 0)

    def test_layered_translation_trajectory_and_base_curve_ownership(self):
        offset = cmds.createNode("transform", name="trajectory_layer_offset")
        control = self._enum_control("trajectory_layer_ctrl", "World:Offset")
        control = cmds.parent(control, offset)[0]
        condition = cmds.createNode("condition", name="trajectory_layer_condition")
        cmds.setAttr(condition + ".secondTerm", 1)
        cmds.setAttr(condition + ".colorIfTrueR", 12)
        cmds.connectAttr(control + ".space", condition + ".firstTerm")
        cmds.connectAttr(condition + ".outColorR", offset + ".translateX")
        cmds.setKeyframe(control, attribute="translateX", time=1, value=1)
        cmds.setKeyframe(control, attribute="translateX", time=10, value=7)
        cmds.select(control)
        layer = cmds.animLayer("TrajectoryLayer")
        cmds.animLayer(layer, edit=True, addSelectedObjects=True)
        cmds.animLayer(layer, edit=True, selected=True, preferred=True)
        cmds.setKeyframe(control, attribute="translateX", time=1, value=4, animLayer=layer)
        cmds.setKeyframe(control, attribute="translateX", time=10, value=9, animLayer=layer)
        root = cmds.animLayer(q=True, root=True)
        base_curve = cmds.animLayer(root, q=True,
                                    findCurveForPlug=control + ".translateX")[0]
        layer_curve = cmds.animLayer(layer, q=True,
                                     findCurveForPlug=control + ".translateX")[0]
        original_base = cmds.keyframe(base_curve, q=True, valueChange=True)
        samples = range(1, 11)
        before = {t: cmds.getAttr(control + ".worldMatrix[0]", time=t) for t in samples}
        cmds.currentTime(5)
        with spaceswitch.UndoChunk("LayeredTrajectory"):
            spaceswitch.SwitchExecutor(_Owner()).apply_requests(
                [([spaceswitch.SwitchOperation(control, control, "space", 1)], False)],
                False, [5, 5])
        self.assertEqual(cmds.keyframe(base_curve, q=True, valueChange=True),
                         original_base)
        self.assertIn(6, cmds.keyframe(layer_curve, q=True, timeChange=True))
        for t in samples:
            self.assertTrue(all(abs(a-b) < 1e-4 for a, b in zip(
                before[t], cmds.getAttr(control + ".worldMatrix[0]", time=t))),
                "Layered world trajectory changed at %s" % t)

    def test_animation_layer_space_switch_preserves_pose_and_layer_keys(self):
        offset = cmds.createNode("transform", name="layer_offset")
        control = self._enum_control("layer_ctrl", "World:Offset")
        control = cmds.parent(control, offset)[0]
        condition = cmds.createNode("condition", name="layer_condition")
        cmds.setAttr(condition + ".secondTerm", 1)
        cmds.setAttr(condition + ".colorIfTrueR", 10)
        cmds.connectAttr(control + ".space", condition + ".firstTerm")
        cmds.connectAttr(condition + ".outColorR", offset + ".translateX")
        cmds.setKeyframe(control, attribute="translateX", time=1, value=2)
        cmds.setKeyframe(control, attribute="translateX", time=10, value=5)
        cmds.select(control)
        layer = cmds.animLayer("SpaceTestLayer")
        cmds.animLayer(layer, edit=True, addSelectedObjects=True)
        cmds.animLayer(layer, edit=True, selected=True, preferred=True)
        cmds.setKeyframe(control, attribute="translateX", time=1, value=3, animLayer=layer)
        cmds.setKeyframe(control, attribute="translateX", time=10, value=6, animLayer=layer)
        layer_curve = cmds.animLayer(layer, query=True,
                                    findCurveForPlug=control + ".translateX")
        original_layer_keys = cmds.keyframe(layer_curve, query=True, timeChange=True) or []
        self.assertNotIn(5, original_layer_keys)
        base_curve = cmds.animLayer(cmds.animLayer(query=True, root=True), query=True,
                                    findCurveForPlug=control + ".translateX")
        original_base_keys = cmds.keyframe(base_curve, query=True, timeChange=True) or []
        cmds.currentTime(5)
        before = {frame: cmds.getAttr(control + ".worldMatrix[0]", time=frame)
                  for frame in (1, 5, 10)}
        operation = spaceswitch.SwitchOperation(control, control, "space", 1)
        with spaceswitch.UndoChunk("LayeredSpaceSwitch"):
            spaceswitch.SwitchExecutor(_Owner()).apply_requests(
                [([operation], False)], False, [5, 5])
        self.assertEqual(cmds.getAttr(control + ".space", time=5), 1)
        self.assertTrue(cmds.animLayer(layer, query=True, blendNodes=True))
        self.assertTrue(layer_curve)
        self.assertIn(5, cmds.keyframe(layer_curve, query=True, timeChange=True) or [],
                      "Compensation must key the active layer, preserving the base animation")
        self.assertEqual(cmds.keyframe(base_curve, query=True, timeChange=True) or [],
                         original_base_keys)
        for frame, matrix in before.items():
            after = cmds.getAttr(control + ".worldMatrix[0]", time=frame)
            self.assertTrue(all(abs(a - b) < 1e-4 for a, b in zip(matrix, after)),
                            "Layered world pose changed at %s: %s -> %s" % (frame, matrix, after))

    def test_nested_driven_controls_compensate_in_parent_first_order(self):
        offset = cmds.createNode("transform", name="nested_offset")
        parent = self._enum_control("nested_parent", "World:Offset")
        parent = cmds.parent(parent, offset)[0]
        child = cmds.createNode("transform", name="nested_child", parent=parent)
        cmds.setAttr(child + ".translateX", 3)
        cmds.setAttr(parent + ".rotateY", 20)
        condition = cmds.createNode("condition", name="nested_condition")
        cmds.setAttr(condition + ".secondTerm", 1)
        cmds.setAttr(condition + ".colorIfTrueR", 9)
        cmds.connectAttr(parent + ".space", condition + ".firstTerm")
        cmds.connectAttr(condition + ".outColorR", offset + ".translateX")
        before = {n: cmds.xform(n, q=True, ws=True, matrix=True)
                  for n in (parent, child)}
        operations = [spaceswitch.SwitchOperation(n, parent, "space", 1)
                      for n in (child, parent)]
        with spaceswitch.UndoChunk("NestedTargets"):
            spaceswitch.SwitchExecutor(_Owner()).apply_requests(
                [(operations, False)], False, [1, 1])
        for n, matrix in before.items():
            self.assertTrue(all(abs(a-b) < 1e-5 for a, b in zip(
                matrix, cmds.xform(n, q=True, ws=True, matrix=True))), n)
        cmds.undo()
        self.assertEqual(cmds.getAttr(parent + ".space"), 0)

    def test_constraint_connected_translation_failure_is_undoable(self):
        offset = cmds.createNode("transform", name="constrained_offset")
        control = self._enum_control("constrained_ctrl", "World:Offset")
        control = cmds.parent(control, offset)[0]
        condition = cmds.createNode("condition", name="constraint_condition")
        cmds.setAttr(condition + ".secondTerm", 1)
        cmds.setAttr(condition + ".colorIfTrueR", 10)
        cmds.connectAttr(control + ".space", condition + ".firstTerm")
        cmds.connectAttr(condition + ".outColorR", offset + ".translateX")
        driver = cmds.createNode("transform", name="constraint_driver", parent=offset)
        cmds.pointConstraint(driver, control)
        cmds.setAttr(control + ".translateX", lock=True)
        before = cmds.xform(control, q=True, ws=True, matrix=True)
        with self.assertRaises(spaceswitch.PoseCompensationError):
            with spaceswitch.UndoChunk("ConstrainedTarget"):
                spaceswitch.SwitchExecutor(_Owner()).apply_requests(
                    [([spaceswitch.SwitchOperation(control, control, "space", 1)], False)],
                    False, [1, 1])
        cmds.undo()
        self.assertEqual(cmds.getAttr(control + ".space"), 0)
        self.assertTrue(all(abs(a-b) < 1e-5 for a, b in zip(
            before, cmds.xform(control, q=True, ws=True, matrix=True))))
        self.assertFalse(cmds.ls("camstool_spaceTemp_*"))

    def test_channel_box_only_switch_keys_when_animation_requires_it(self):
        offset = cmds.createNode("transform", name="nonkeyable_offset")
        control = cmds.createNode("transform", name="nonkeyable_ctrl", parent=offset)
        cmds.addAttr(control, longName="space", attributeType="enum",
                     enumName="World:Offset", keyable=False)
        cmds.setAttr(control + ".space", channelBox=True)
        condition = cmds.createNode("condition", name="nonkeyable_condition")
        cmds.setAttr(condition + ".secondTerm", 1)
        cmds.setAttr(condition + ".colorIfTrueR", 8)
        cmds.connectAttr(control + ".space", condition + ".firstTerm")
        cmds.connectAttr(condition + ".outColorR", offset + ".translateX")
        cmds.setKeyframe(control, attribute="translateX", time=1, value=2)
        cmds.setKeyframe(control, attribute="translateX", time=8, value=5)
        before = {t: cmds.getAttr(control + ".worldMatrix[0]", time=t) for t in (1, 8)}
        with spaceswitch.UndoChunk("NonkeyableSwitch"):
            spaceswitch.SwitchExecutor(_Owner()).apply_requests(
                [([spaceswitch.SwitchOperation(control, control, "space", 1)], True)],
                False, [1, 8])
        self.assertEqual([cmds.getAttr(control + ".space", time=t) for t in (1, 8)],
                         [1, 1])
        for t, matrix in before.items():
            self.assertTrue(all(abs(a-b) < 1e-5 for a, b in zip(
                matrix, cmds.getAttr(control + ".worldMatrix[0]", time=t))))
        self.assertEqual(set(cmds.keyframe(control + ".space", q=True, timeChange=True) or []),
                         {1, 8})

    def test_silently_rejected_switch_key_aborts_before_pose_write(self):
        offset = cmds.createNode("transform", name="rejected_offset")
        control = self._enum_control("rejected_ctrl", "World:Offset")
        control = cmds.parent(control, offset)[0]
        condition = cmds.createNode("condition", name="rejected_condition")
        cmds.setAttr(condition + ".secondTerm", 1)
        cmds.setAttr(condition + ".colorIfTrueR", 10)
        cmds.connectAttr(control + ".space", condition + ".firstTerm")
        cmds.connectAttr(condition + ".outColorR", offset + ".translateX")
        cmds.setKeyframe(control, attribute="translateX", time=1, value=1)
        cmds.setKeyframe(control, attribute="translateX", time=8, value=4)
        original_key = cmds.setKeyframe

        def reject_switch_key(*args, **kwargs):
            if args and args[0] == control + ".space":
                return None  # Maya can refuse an edit without raising
            return original_key(*args, **kwargs)

        before = cmds.xform(control, q=True, ws=True, matrix=True)
        with mock.patch.object(spaceswitch.cmds, "setKeyframe", side_effect=reject_switch_key):
            with self.assertRaisesRegex(spaceswitch.PoseCompensationError,
                                        "could not be keyed"):
                with spaceswitch.UndoChunk("RejectedSwitch"):
                    spaceswitch.SwitchExecutor(_Owner()).apply_requests(
                        [([spaceswitch.SwitchOperation(control, control, "space", 1)], True)],
                        False, [1, 8])
        cmds.undo()
        self.assertEqual(cmds.getAttr(control + ".space"), 0)
        self.assertTrue(all(abs(a-b) < 1e-5 for a, b in zip(
            before, cmds.xform(control, q=True, ws=True, matrix=True))))

    def test_euler_filter_discovers_rotation_curves_through_animation_layers(self):
        control = cmds.createNode("transform", name="layer_rotate_ctrl")
        cmds.setKeyframe(control, attribute="rotateY", time=1, value=170)
        cmds.setKeyframe(control, attribute="rotateY", time=10, value=-170)
        root_curve = cmds.listConnections(control + ".rotateY", type="animCurve")[0]
        cmds.select(control)
        layer = cmds.animLayer("RotationLayer")
        cmds.animLayer(layer, edit=True, addSelectedObjects=True)
        cmds.animLayer(layer, edit=True, preferred=True, selected=True)
        cmds.setKeyframe(control, attribute="rotateY", time=1, value=20, animLayer=layer)
        cmds.setKeyframe(control, attribute="rotateY", time=10, value=50, animLayer=layer)
        layer_curve = cmds.animLayer(layer, query=True,
                                    findCurveForPlug=control + ".rotateY")[0]
        found = spaceswitch.Maya.upstream_animation_curves(control + ".rotateY")
        self.assertIn(root_curve, found)
        self.assertIn(layer_curve, found)
        parent = QtWidgets.QWidget()
        widget = spaceswitch.SpaceSwitchAlehaWidget(popup=False, parent=parent)
        with mock.patch.object(spaceswitch.cmds, "filterCurve") as filter_curve:
            widget.apply_euler_filter([control], (1, 10))
        args, kwargs = filter_curve.call_args
        self.assertIn(root_curve, args)
        self.assertIn(layer_curve, args)
        self.assertEqual((kwargs["startTime"], kwargs["endTime"]), (1, 10))
        widget.apply_euler_filter([control], (1, 10))
        widget.close()
        parent.close()

    def test_alt_click_on_visible_switch_row_executes_and_undoes(self):
        offset = cmds.createNode("transform", name="click_offset")
        control = self._enum_control("click_ctrl", "World:Offset")
        control = cmds.parent(control, offset)[0]
        condition = cmds.createNode("condition", name="click_condition")
        cmds.setAttr(condition + ".secondTerm", 1)
        cmds.setAttr(condition + ".colorIfTrueR", 7)
        cmds.connectAttr(control + ".space", condition + ".firstTerm")
        cmds.connectAttr(condition + ".outColorR", offset + ".translateX")
        cmds.select(control)
        parent = QtWidgets.QWidget()
        widget = spaceswitch.SpaceSwitchAlehaWidget(popup=False, parent=parent)
        widget.euler_filter = False
        widget.show()
        widget.refresh(force=True)
        app.processEvents()
        row = next(item for (item, _options) in widget._active_switch_widgets.values()
                   if item.enum_attr == "space")
        before = cmds.xform(control, q=True, ws=True, matrix=True)
        with mock.patch.object(spaceswitch, "_cycle_modifier_held", return_value=True):
            QtTest.QTest.mouseClick(row, QtCore.Qt.LeftButton,
                                    QtCore.Qt.AltModifier, pos=row.rect().center())
            app.processEvents()
        self.assertEqual(cmds.getAttr(control + ".space"), 1)
        self.assertTrue(all(abs(a-b) < 1e-5 for a, b in zip(
            before, cmds.xform(control, q=True, ws=True, matrix=True))))
        cmds.undo()
        self.assertEqual(cmds.getAttr(control + ".space"), 0)
        widget.close()
        parent.close()

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

    def test_one_attribute_compensates_multiple_targets(self):
        settings = self._enum_control("space_settings", "World:Moved")
        condition = cmds.createNode("condition", name="multi_target_condition")
        cmds.setAttr(condition + ".secondTerm", 1)
        cmds.setAttr(condition + ".colorIfTrueR", 7)
        cmds.connectAttr(settings + ".space", condition + ".firstTerm")
        targets = []
        for index in (1, 2):
            offset = cmds.createNode("transform", name="offset_%s" % index)
            target = cmds.createNode("transform", name="control_%s" % index, parent=offset)
            cmds.connectAttr(condition + ".outColorR", offset + ".translateX")
            cmds.setAttr(target + ".translateX", index * 3)
            targets.append(target)
        before = {target: cmds.xform(target, q=True, ws=True, matrix=True)
                  for target in targets}
        operations = [spaceswitch.SwitchOperation(target, settings, "space", 1)
                      for target in targets]

        with spaceswitch.UndoChunk("MultiTargetSpaceSwitch"):
            changed = spaceswitch.SwitchExecutor(_Owner()).apply_requests(
                [(operations, False)], False, [1, 1])

        self.assertEqual(changed, set(targets))
        self.assertEqual(cmds.getAttr(settings + ".space"), 1)
        for target in targets:
            after = cmds.xform(target, q=True, ws=True, matrix=True)
            self.assertTrue(all(abs(a - b) < 1e-5 for a, b in zip(before[target], after)))

    def test_locked_unaffected_channel_does_not_prevent_pose_compensation(self):
        offset = cmds.createNode("transform", name="locked_offset")
        control = cmds.createNode("transform", name="locked_ctrl", parent=offset)
        cmds.addAttr(control, longName="space", attributeType="enum",
                     enumName="World:Offset", keyable=True)
        condition = cmds.createNode("condition", name="locked_condition")
        cmds.setAttr(condition + ".secondTerm", 1)
        cmds.setAttr(condition + ".colorIfTrueR", 9)
        cmds.connectAttr(control + ".space", condition + ".firstTerm")
        cmds.connectAttr(condition + ".outColorR", offset + ".translateX")
        cmds.setAttr(control + ".translateX", 2)
        cmds.setAttr(control + ".rotateY", lock=True)
        before = cmds.xform(control, q=True, ws=True, matrix=True)

        operation = spaceswitch.SwitchOperation(control, control, "space", 1)
        with spaceswitch.UndoChunk("LockedChannelSpaceSwitch"):
            executor = spaceswitch.SwitchExecutor(_Owner())
            executor.apply_requests([([operation], False)], False, [1, 1])

        after = cmds.xform(control, q=True, ws=True, matrix=True)
        self.assertEqual(cmds.getAttr(control + ".space"), 1)
        self.assertTrue(all(abs(a - b) < 1e-5 for a, b in zip(before, after)),
                        "An unrelated locked rotation must not block translation compensation")
        self.assertFalse(cmds.ls("camstool_spaceTemp_*", type="transform"))

    def test_impossible_locked_pose_fails_instead_of_silently_popping(self):
        offset = cmds.createNode("transform", name="impossible_offset")
        control = cmds.createNode("transform", name="impossible_ctrl", parent=offset)
        cmds.addAttr(control, longName="space", attributeType="enum",
                     enumName="World:Offset", keyable=True)
        condition = cmds.createNode("condition", name="impossible_condition")
        cmds.setAttr(condition + ".secondTerm", 1)
        cmds.setAttr(condition + ".colorIfTrueR", 9)
        cmds.connectAttr(control + ".space", condition + ".firstTerm")
        cmds.connectAttr(condition + ".outColorR", offset + ".translateX")
        for channel in ("translateX", "translateY", "translateZ"):
            cmds.setAttr(control + "." + channel, lock=True)
        before = cmds.xform(control, q=True, ws=True, matrix=True)
        operation = spaceswitch.SwitchOperation(control, control, "space", 1)

        with self.assertRaises(spaceswitch.PoseCompensationError):
            with spaceswitch.UndoChunk("ImpossiblePoseSwitch"):
                spaceswitch.SwitchExecutor(_Owner()).apply_requests(
                    [([operation], False)], False, [1, 1])
        cmds.undo()
        self.assertEqual(cmds.getAttr(control + ".space"), 0)
        self.assertTrue(all(abs(a - b) < 1e-5 for a, b in zip(
            before, cmds.xform(control, q=True, ws=True, matrix=True))))

    def test_ui_rolls_back_failed_switch_and_restores_state(self):
        offset = cmds.createNode("transform", name="rollback_offset")
        control = cmds.createNode("transform", name="rollback_ctrl", parent=offset)
        cmds.addAttr(control, longName="space", attributeType="enum",
                     enumName="World:Offset", keyable=True)
        condition = cmds.createNode("condition", name="rollback_condition")
        cmds.setAttr(condition + ".secondTerm", 1)
        cmds.setAttr(condition + ".colorIfTrueR", 9)
        cmds.connectAttr(control + ".space", condition + ".firstTerm")
        cmds.connectAttr(condition + ".outColorR", offset + ".translateX")
        cmds.setAttr(control + ".translateX", lock=True)
        cmds.setAttr(control + ".translateY", lock=True)
        cmds.setAttr(control + ".translateZ", lock=True)
        cmds.select(control)
        parent = QtWidgets.QWidget()
        widget = spaceswitch.SpaceSwitchAlehaWidget(popup=False, parent=parent)
        widget.euler_filter = False
        options = widget._build_options_map(widget._build_switch_data()["space"]["objects"])
        initial_time = cmds.currentTime(q=True)
        initial_auto_key = cmds.autoKeyframe(q=True, state=True)

        widget._apply_requests([("Offset", "space", options, False)])

        self.assertEqual(cmds.getAttr(control + ".space"), 0)
        self.assertEqual(cmds.currentTime(q=True), initial_time)
        self.assertEqual(cmds.autoKeyframe(q=True, state=True), initial_auto_key)
        self.assertFalse(widget._busy)
        self.assertFalse(cmds.ls("camstool_spaceTemp_*"))
        widget.close()
        parent.close()

    def test_selected_timeline_range_preserves_outside_keys_and_undo_redo(self):
        offset = cmds.createNode("transform", name="range_offset")
        control = cmds.createNode("transform", name="range_ctrl", parent=offset)
        cmds.addAttr(control, longName="space", attributeType="enum",
                     enumName="World:Offset", keyable=True)
        condition = cmds.createNode("condition", name="range_condition")
        cmds.setAttr(condition + ".secondTerm", 1)
        cmds.setAttr(condition + ".colorIfTrueR", 8)
        cmds.connectAttr(control + ".space", condition + ".firstTerm")
        cmds.connectAttr(condition + ".outColorR", offset + ".translateX")
        for frame, value in ((1, 1), (5, 4), (10, 10)):
            cmds.setKeyframe(control, attribute="translateX", time=frame, value=value)
        before = {frame: cmds.getAttr(control + ".worldMatrix[0]", time=frame)
                  for frame in (1, 5, 10)}
        operation = spaceswitch.SwitchOperation(control, control, "space", 1)

        with spaceswitch.UndoChunk("RangeSpaceSwitch"):
            spaceswitch.SwitchExecutor(_Owner()).apply_requests(
                [([operation], False)], True, [4, 8])

        self.assertEqual([cmds.getAttr(control + ".space", time=t) for t in (1, 5, 10)],
                         [0, 1, 0])
        for frame in before:
            self.assertTrue(all(abs(a - b) < 1e-5 for a, b in zip(
                before[frame], cmds.getAttr(control + ".worldMatrix[0]", time=frame))))
        cmds.undo()
        self.assertEqual([cmds.getAttr(control + ".space", time=t) for t in (1, 5, 10)],
                         [0, 0, 0])
        cmds.redo()
        self.assertEqual([cmds.getAttr(control + ".space", time=t) for t in (1, 5, 10)],
                         [0, 1, 0])

    def test_cancel_after_partial_write_rolls_back_all_frames(self):
        offset = cmds.createNode("transform", name="cancel_offset")
        control = cmds.createNode("transform", name="cancel_ctrl", parent=offset)
        cmds.addAttr(control, longName="space", attributeType="enum",
                     enumName="World:Offset", keyable=True)
        condition = cmds.createNode("condition", name="cancel_condition")
        cmds.setAttr(condition + ".secondTerm", 1)
        cmds.setAttr(condition + ".colorIfTrueR", 8)
        cmds.connectAttr(control + ".space", condition + ".firstTerm")
        cmds.connectAttr(condition + ".outColorR", offset + ".translateX")
        for frame, value in ((1, 1), (5, 4), (10, 10)):
            cmds.setKeyframe(control, attribute="translateX", time=frame, value=value)
        cmds.select(control)
        parent = QtWidgets.QWidget()
        widget = spaceswitch.SpaceSwitchAlehaWidget(popup=False, parent=parent)
        widget.euler_filter = False
        options = widget._build_options_map(widget._build_switch_data()["space"]["objects"])

        class CancelAfterFirstCompensation(spaceswitch.OperationRunner):
            def step(self, status=None):
                result = super(CancelAfterFirstCompensation, self).step(status)
                if self.done >= (self.total - 1) // 2 + 2:
                    # All sampled captures, switch write, one compensated frame.
                    self.cancel()
                return result

        with mock.patch.object(spaceswitch, "OperationRunner", CancelAfterFirstCompensation):
            widget._apply_requests([("Offset", "space", options, True)])

        self.assertEqual([cmds.getAttr(control + ".space", time=t) for t in (1, 5, 10)],
                         [0, 0, 0])
        self.assertEqual(cmds.keyframe(control + ".space", q=True, keyframeCount=True), 0)
        self.assertFalse(widget._busy)
        widget.close()
        parent.close()

    def test_reentrant_ui_request_is_ignored_during_active_switch(self):
        parent = QtWidgets.QWidget()
        widget = spaceswitch.SpaceSwitchAlehaWidget(popup=False, parent=parent)
        widget._busy = True
        with mock.patch.object(widget, "_missing_target_prompt") as prompt:
            widget._apply_requests([])
        prompt.assert_not_called()
        self.assertTrue(widget._busy)
        widget._busy = False
        widget.close()
        parent.close()

    def test_close_removes_maya_callbacks_and_pending_refresh(self):
        parent = QtWidgets.QWidget()
        widget = spaceswitch.SpaceSwitchAlehaWidget(popup=False, parent=parent)
        self.assertTrue(widget._cb.ids)
        widget._refresh_timer.start()
        widget._popup_timer.start()
        widget.close()
        self.assertFalse(widget._cb.ids)
        self.assertFalse(widget._refresh_timer.isActive())
        self.assertFalse(widget._popup_timer.isActive())
        parent.close()

    def test_rotation_order_on_oriented_joint_keeps_world_rotation(self):
        cmds.select(clear=True)
        joint = cmds.joint(name="oriented_joint")
        cmds.setAttr(joint + ".jointOrientY", 30)
        cmds.setKeyframe(joint, attribute="rotateX", time=1, value=20)
        cmds.setKeyframe(joint, attribute="rotateY", time=8, value=55)
        before = {frame: cmds.getAttr(joint + ".worldMatrix[0]", time=frame)
                  for frame in (1, 8)}
        operation = spaceswitch.SwitchOperation(joint, joint, "rotateOrder", 5)

        with spaceswitch.UndoChunk("JointRotationOrder"):
            spaceswitch.SwitchExecutor(_FastOwner()).apply_requests(
                [([operation], True)], False, [1, 8])

        self.assertEqual(cmds.getAttr(joint + ".rotateOrder"), 5)
        for frame, matrix in before.items():
            after = cmds.getAttr(joint + ".worldMatrix[0]", time=frame)
            self.assertTrue(all(abs(a - b) < 1e-4 for a, b in zip(matrix, after)),
                            "Joint pose changed at frame %s" % frame)

    def test_repeated_switches_and_noop_keep_pose_and_key_count(self):
        offset = cmds.createNode("transform", name="repeat_offset")
        control = cmds.createNode("transform", name="repeat_ctrl", parent=offset)
        cmds.addAttr(control, longName="space", attributeType="enum",
                     enumName="World:Offset", keyable=True)
        condition = cmds.createNode("condition", name="repeat_condition")
        cmds.setAttr(condition + ".secondTerm", 1)
        cmds.setAttr(condition + ".colorIfTrueR", 6)
        cmds.connectAttr(control + ".space", condition + ".firstTerm")
        cmds.connectAttr(condition + ".outColorR", offset + ".translateX")
        cmds.setKeyframe(control, attribute="translateX", time=1, value=2)
        cmds.setKeyframe(control, attribute="translateX", time=8, value=9)
        cmds.currentTime(5)
        before = cmds.xform(control, q=True, ws=True, matrix=True)
        executor = spaceswitch.SwitchExecutor(_Owner())

        for value in (1, 1, 0, 1):
            op = spaceswitch.SwitchOperation(control, control, "space", value)
            captured = cmds.getAttr(control + ".worldMatrix[0]", time=5)
            with spaceswitch.UndoChunk("RepeatedSpaceSwitch"):
                executor.apply_requests([([op], False)], False, [5, 5])
            after = cmds.xform(control, q=True, ws=True, matrix=True)
            self.assertTrue(all(abs(a - b) < 1e-5 for a, b in zip(before, after)),
                            "Repeated switch to %s: %r -> %r; sampled=%r, tx=%s" %
                            (value, before, after, captured,
                             cmds.getAttr(control + ".translateX")))
            self.assertEqual(cmds.getAttr(control + ".space"), value)
            self.assertEqual(cmds.keyframe(control + ".space", q=True, keyframeCount=True), 3)

    def test_numeric_space_switch_is_discrete_until_keyed_frame(self):
        node = cmds.createNode("transform", name="numeric_space_ctrl")
        cmds.addAttr(node, longName="spaceBlend", attributeType="double",
                     minValue=0, maxValue=1, keyable=True)
        cmds.setKeyframe(node, attribute="spaceBlend", time=1, value=0)
        cmds.setKeyframe(node, attribute="spaceBlend", time=10, value=0)
        cmds.currentTime(5)
        op = spaceswitch.SwitchOperation(node, node, "spaceBlend", 1)
        with spaceswitch.UndoChunk("NumericSpaceSwitch"):
            spaceswitch.SwitchExecutor(_Owner()).apply_requests(
                [([op], False)], False, [5, 5])
        self.assertAlmostEqual(cmds.getAttr(node + ".spaceBlend", time=4), 0.0)
        self.assertAlmostEqual(cmds.getAttr(node + ".spaceBlend", time=5), 1.0)
        self.assertAlmostEqual(cmds.getAttr(node + ".spaceBlend", time=10), 0.0)

    def test_conflicting_multi_target_choices_do_not_write_partial_keys(self):
        node = self._enum_control("conflict_ctrl")
        operations = [spaceswitch.SwitchOperation(node, node, "space", value)
                      for value in (0, 3)]
        executor = spaceswitch.SwitchExecutor(_Owner())
        with self.assertRaises(ValueError):
            executor.apply_requests([([operations[0]], False),
                                     ([operations[1]], False)], False, [1, 1])
        self.assertEqual(cmds.getAttr(node + ".space"), 0)
        self.assertEqual(cmds.keyframe(node + ".space", query=True, keyframeCount=True), 0)

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

    def test_detected_switch_can_be_hidden_and_restored_across_views(self):
        node = self._enum_control("hidden_ctrl")
        cmds.createNode("nurbsCurve", name="hidden_ctrlShape", parent=node)
        condition = cmds.createNode("condition", name="hidden_condition")
        cmds.connectAttr(node + ".space", condition + ".firstTerm")
        cmds.select(node, replace=True)
        parent = QtWidgets.QWidget()
        widget = spaceswitch.SpaceSwitchAlehaWidget(popup=False, parent=parent)

        data = widget._build_switch_data()
        self.assertIn("space", data)
        widget._hide_switch(data["space"])
        self.assertNotIn("space", widget._build_switch_data())
        self.assertIn("hidden_ctrl.space", widget._hidden_switch_keys())

        widget.toggle_asset_view()
        self.assertNotIn("space@hidden_ctrl", widget._build_switch_data())
        widget._restore_hidden_switches()
        self.assertTrue(any(item.get("objects") for item in widget._build_switch_data().values()))
        self.assertFalse(widget._hidden_switch_keys())
        widget.close()
        parent.close()

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
