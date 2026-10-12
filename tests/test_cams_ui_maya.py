"""Real Maya 2024/Qt regression checks for the shared Cams interface."""
import os
import copy
import sys
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "source")))

from PySide2 import QtWidgets, QtGui
import shiboken2

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

import maya.standalone
maya.standalone.initialize()
from maya import cmds

from aleha_tools import widgets, base_widgets, cams
from aleha_tools._tools import HUDWindow
from aleha_tools._tools import multicams
from aleha_tools._tools import followCam, aimCam


class PreferencesOwner(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.default_near_clip_plane = (0.1, True)
        self.default_far_clip_plane = (10000.0, True)
        self.default_overscan = (1.0, True)
        self.default_gate_mask_opacity = (0.5, True)
        self.default_gate_mask_color = ([0.1, 0.3, 0.6], True)
        self.default_cam = ("persp", False)
        self.default_cam_btn = QtWidgets.QPushButton("persp", self)
        self.saved = None

    def process_prefs(self, **kwargs):
        self.saved = kwargs


class CamsUITests(unittest.TestCase):
    def test_main_window_tool_hub_open_reuses_dialog_and_handles_dead_action(self):
        class FakeCams(QtWidgets.QWidget):
            show_tool_hub = cams.QCamsWindow.show_tool_hub

        owner = FakeCams()
        owner.tool_hub_window = None
        for key in ("followCam", "aimCam", "multicams", "spaceswitch",
                    "hud_editor_action", "settings_btn", "reload_btn"):
            setattr(owner, key, QtWidgets.QAction(key, owner))
        owner.show_tool_hub()
        first = owner.tool_hub_window
        shiboken2.delete(owner.hud_editor_action)
        owner.show_tool_hub()
        self.assertIs(owner.tool_hub_window, first)
        self.assertFalse(first.tool_buttons["hud_editor_action"].isEnabled())
        owner.hud_editor_action = QtWidgets.QAction("HUD Editor", owner)
        owner.show_tool_hub()
        self.assertTrue(first.tool_buttons["hud_editor_action"].isEnabled())
        owner.close()

    def test_nested_camera_context_menu_tracks_selected_full_dag_path(self):
        cmds.file(new=True, force=True)
        camera, _ = cmds.camera(name="menu_camera")
        group = cmds.group(camera, name="nested_camera_grp")
        full_camera = cmds.ls(camera, long=True)[0]
        parent = QtWidgets.QWidget()
        button = widgets.QFlatCamButton(full_camera, parent)
        menu = widgets.QFlatOpenMenu("Camera Actions", parent)
        cmds.select(full_camera, replace=True)
        button._add_selection_actions(menu)
        self.assertFalse(button.select_action.isVisible())
        self.assertTrue(button.deselect_action.isVisible())
        cmds.select(clear=True)
        menu2 = widgets.QFlatOpenMenu("Camera Actions", parent)
        button._add_selection_actions(menu2)
        self.assertTrue(button.select_action.isVisible())
        self.assertFalse(button.deselect_action.isVisible())
        parent.close()

    def test_follow_and_aim_camera_creators_use_scene_selection(self):
        for creator in (followCam.followCam, aimCam.aimCam):
            with self.subTest(creator=creator.__name__):
                cmds.file(new=True, force=True)
                target = cmds.spaceLocator(name="tracked_item")[0]
                cmds.select(target, replace=True)
                original = cmds.ls(type="camera")
                with mock.patch.object(cmds, "lookThru", side_effect=lambda *a, **kw:
                                       "persp" if kw.get("q") else None), \
                     mock.patch.object(cmds, "getPanel", return_value="modelPanel4"):
                    creator()
                self.assertGreater(len(cmds.ls(type="camera")), len(original))
                new_shape = next(shape for shape in cmds.ls(type="camera") if shape not in original)
                new_cam = cmds.listRelatives(new_shape, parent=True, fullPath=True)[0]
                expected_type = "camera_follow" if creator is followCam.followCam else "camera_aim"
                self.assertEqual(cmds.getAttr(new_cam + ".cams_type"), expected_type)
                if creator is followCam.followCam:
                    identifier, attribute = cmds.getAttr(new_cam + ".cams_follow_attr").split("|")
                    group = cmds.ls(identifier)[0]
                    self.assertTrue(cmds.objExists(group + "." + attribute))
                    self.assertEqual(cmds.getAttr(group + ".FaceCamMode"), 1)
                else:
                    aim_offset = cmds.getAttr(new_cam + ".cams_aim_offset")
                    self.assertTrue(cmds.objExists(aim_offset))
                cmds.undo()
                self.assertEqual(len(cmds.ls(type="camera")), len(original))

    def test_follow_and_aim_camera_failure_undoes_partial_scene(self):
        for creator in (followCam.followCam, aimCam.aimCam):
            with self.subTest(creator=creator.__name__):
                cmds.file(new=True, force=True)
                locator = cmds.spaceLocator(name="failure_target")[0]
                cmds.select(locator, replace=True)
                original_cameras = set(cmds.ls(type="camera"))
                with mock.patch.object(cmds, "lookThru", side_effect=lambda *a, **kw:
                                       "persp" if kw.get("q") else None), \
                     mock.patch.object(cmds, "pointConstraint",
                                       side_effect=RuntimeError("synthetic constraint failure")):
                    with self.assertRaisesRegex(RuntimeError, "synthetic constraint failure"):
                        creator()
                self.assertEqual(set(cmds.ls(type="camera")), original_cameras)
                self.assertEqual(cmds.ls(selection=True), [locator])

    def test_hud_menu_rebuild_keeps_main_hud_action_valid(self):
        parent = QtWidgets.QWidget()
        main_menu = widgets.QFlatOpenMenu("Tools", parent)
        holder = type("HUDMenuHolder", (), {
            "add_presets": cams.QCamsWindow.add_presets,
            "hud_preset_triggered": lambda self, *args: None,
        })()
        holder.menu_presets = widgets.QFlatOpenMenu("HUD Presets", main_menu)
        holder.hud_editor_action = main_menu.addAction("HUD Editor")
        with mock.patch.object(cams.settings, "get_pref", return_value={
                "presets": {"Default": {"bmc": 6}}, "selected": 0}):
            holder.add_presets()
            holder.add_presets()
            holder.add_presets()
        self.assertTrue(shiboken2.isValid(holder.hud_editor_action))
        self.assertEqual(sum(action.text() == "HUD Editor" for action in main_menu.actions()), 1)
        self.assertEqual(sum(action.text() == "HUD Editor" for action in holder.menu_presets.actions()), 1)
        parent.close()

    def test_multicams_qt_workflow_drives_both_sources_and_is_undoable(self):
        cmds.file(new=True, force=True)
        first, shape_a = cmds.camera(name="shot_alpha")
        second, shape_b = cmds.camera(name="shot_beta")
        cmds.setAttr(shape_a + ".focalLength", 30)
        cmds.setAttr(shape_b + ".focalLength", 75)
        cmds.setAttr(first + ".translateX", 3)
        cmds.setAttr(second + ".translateX", 12)
        cmds.select(first, second, replace=True)
        parent = QtWidgets.QWidget()
        dialog = multicams.multicams.showUI(parent)
        self.assertEqual(len(dialog.selected_cameras), 2)
        dialog.cameras.setCurrentRow(1)
        dialog.remove_selected()
        self.assertEqual(len(dialog.selected_cameras), 1)
        cmds.select(second, replace=True)
        dialog.get_cameras()
        self.assertEqual(len(dialog.selected_cameras), 2)
        dialog.camera_name.setText("edit_shot")
        created = dialog.create_multi()
        self.assertTrue(created)
        cmds.undo()
        self.assertFalse(cmds.objExists(created))
        created = multicams.create_multicam_rig([first, second], "edit_shot")
        new_shape = cmds.listRelatives(created, shapes=True, type="camera")[0]
        for i, (position, focal) in enumerate(((3, 30), (12, 75))):
            cmds.setAttr(created + ".selectedCamera", i)
            self.assertAlmostEqual(cmds.xform(created, q=True, ws=True, t=True)[0], position, places=3)
            self.assertAlmostEqual(cmds.getAttr(new_shape + ".focalLength"), focal, places=3)
        dialog.close()
        parent.close()

    def test_multicams_failed_constraint_curve_write_rolls_back_entire_rig(self):
        cmds.file(new=True, force=True)
        first, _ = cmds.camera(name="safe_cam_a")
        second, _ = cmds.camera(name="safe_cam_b")
        cmds.select(first, second, replace=True)
        selected = cmds.ls(selection=True, long=True)
        with mock.patch.object(multicams.cmds, "setDrivenKeyframe",
                               side_effect=RuntimeError("synthetic curve failure")):
            with self.assertRaisesRegex(RuntimeError, "synthetic curve failure"):
                multicams.create_multicam_rig([first, second], "failed_rig")
        self.assertFalse(cmds.objExists("failed_rig"))
        self.assertFalse(cmds.objExists("failed_rig_MultiCams_GRP"))
        self.assertEqual(cmds.ls(selection=True, long=True), selected)

    def test_hud_editor_reopens_single_instance_and_isolates_preset_values(self):
        parent = QtWidgets.QWidget()
        defaults = {"presets": {"Default": {"bmc": 6, "trc": 0, "tlc": 0,
                                             "tmc": 0, "brc": 0, "blc": 8}}, "selected": 0}
        with mock.patch.object(HUDWindow.cams_settings, "get_pref", return_value=copy.deepcopy(defaults)), \
             mock.patch.object(HUDWindow.cams_settings, "save_to_disk"):
            dialog = HUDWindow.HUDWindow.showUI(parent)
            self.assertIs(dialog, HUDWindow.HUDWindow.showUI(parent))
            dialog.new_preset()
            self.assertEqual(dialog.hud_presets["New Preset"]["bmc"], 6)
            dialog.hud_presets["New Preset"]["bmc"] = 4
            self.assertEqual(dialog.hud_presets["Default"]["bmc"], 6)
            dialog.close()
        parent.close()

    def test_tool_hub_survives_deleted_qaction_after_menu_rebuild(self):
        parent = QtWidgets.QWidget()
        actions = {key: QtWidgets.QAction(key, parent) for key in
                   ("followCam", "aimCam", "multicams", "spaceswitch",
                    "hud_editor_action", "settings_btn", "reload_btn")}
        shiboken2.delete(actions["hud_editor_action"])
        dialog = widgets.QToolHubDialog(actions, parent)
        self.assertFalse(dialog.tool_buttons["hud_editor_action"].isEnabled())
        replacement = QtWidgets.QAction("HUD Editor", parent)
        parent.hud_editor_action = replacement
        dialog.show()
        self.assertTrue(dialog.tool_buttons["hud_editor_action"].isEnabled())
        dialog.close()
        parent.close()

    def test_tool_hub_groups_tools_and_dispatches_existing_actions(self):
        parent = QtWidgets.QWidget()
        actions = {}
        for key in ("followCam", "aimCam", "multicams", "spaceswitch",
                    "hud_editor_action", "settings_btn", "reload_btn"):
            actions[key] = QtWidgets.QAction(key, parent)
        triggered = []
        actions["spaceswitch"].triggered.connect(lambda *_: triggered.append("space"))
        actions["followCam"].triggered.connect(lambda *_: triggered.append("follow"))
        dialog = widgets.QToolHubDialog(actions, parent)
        self.assertEqual(len(dialog.tool_buttons), 7)
        headers = [header.text() for header in
                   dialog.findChildren(base_widgets.QFlatSectionHeader)]
        self.assertEqual(headers, ["Camera Rigs", "Animation", "Viewport",
                                   "Cams Settings"])
        dialog.tool_buttons["spaceswitch"].click()
        dialog.tool_buttons["followCam"].click()
        self.assertEqual(triggered, ["space", "follow"])
        actions["followCam"].setEnabled(False)
        self.assertFalse(dialog.tool_buttons["followCam"].isEnabled())
        actions["followCam"].setEnabled(True)
        self.assertTrue(dialog.tool_buttons["followCam"].isEnabled())
        actions["spaceswitch"].setVisible(False)
        self.assertFalse(dialog.tool_buttons["spaceswitch"].isEnabled())
        actions["spaceswitch"].setVisible(True)
        self.assertTrue(dialog.tool_buttons["spaceswitch"].isEnabled())
        dialog.close()
        parent.close()

    def test_camera_attributes_dialog_binds_opacity_and_color_separately(self):
        cmds.file(new=True, force=True)
        _transform, shape = cmds.camera(name="ui_dialog_camera")
        cmds.setAttr(shape + ".displayGateMaskOpacity", 0.22)
        cmds.setAttr(shape + ".displayGateMaskColor", 0.8, 0.4, 0.2, type="double3")
        parent = QtWidgets.QWidget()
        dialog = widgets.QAttributesDialog(shape, parent)
        self.assertEqual(dialog.gate_mask_opacity_slider.value(), 220)
        expected_value = QtGui.QColor.fromRgbF(0.8, 0.4, 0.2).value()
        self.assertEqual(dialog.gate_mask_color_slider.value(), expected_value)
        headers = [header.text() for header in
                   dialog.findChildren(base_widgets.QFlatSectionHeader)]
        self.assertEqual(headers, ["Lens", "Clipping", "Viewport Display"])
        dialog.close()
        parent.close()

    def test_numeric_camera_settings_accept_single_digits_and_reject_empty(self):
        owner = PreferencesOwner()
        dialog = widgets.QSettingsDialog(owner)
        dialog.near_clip_plane.setText("1")
        self.assertTrue(dialog.near_clip_plane.hasAcceptableInput())
        dialog.gate_mask_opacity_value.setText("")
        self.assertFalse(dialog.apply_settings())
        self.assertIsNone(owner.saved)
        dialog.gate_mask_opacity_value.setText("0.75")
        self.assertTrue(dialog.apply_settings())
        self.assertEqual(owner.saved["mask_op"][0], 0.75)
        dialog.close()
        owner.close()

    def test_default_camera_color_picker_saves_visible_color(self):
        owner = PreferencesOwner()
        dialog = widgets.QSettingsDialog(owner)
        chosen = QtGui.QColor("#4488cc")
        with mock.patch.object(widgets.QColorDialog, "getColor", return_value=chosen):
            dialog.show_color_selector(dialog.gate_mask_color_picker)
        dialog.apply_settings()
        self.assertEqual(owner.saved["mask_color"][0],
                         [round(channel / 255.0, 3) for channel in (68, 136, 204)])
        dialog.close()
        owner.close()

    def test_gate_mask_brightness_keeps_chosen_hue_and_saturation(self):
        owner = PreferencesOwner()
        dialog = widgets.QSettingsDialog(owner)
        chosen = QtGui.QColor("#cc8844")
        with mock.patch.object(widgets.QColorDialog, "getColor", return_value=chosen):
            dialog.show_color_selector(dialog.gate_mask_color_picker)
        original_hue, original_saturation, _, _ = chosen.getHsv()
        dialog.gate_mask_color_slider.setValue(190)
        dialog.apply_settings()
        color = QtGui.QColor.fromRgbF(*owner.saved["mask_color"][0])
        hue, saturation, _value, _alpha = color.getHsv()
        self.assertLessEqual(abs(hue - original_hue), 1)
        self.assertLessEqual(abs(saturation - original_saturation), 2)
        dialog.close()
        owner.close()


if __name__ == "__main__":
    unittest.main()
