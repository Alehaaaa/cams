"""Real Maya 2024/Qt regression checks for the shared Cams interface."""
import os
import sys
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "source")))

from PySide2 import QtWidgets, QtGui

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

import maya.standalone
maya.standalone.initialize()
from maya import cmds

from aleha_tools import widgets, base_widgets


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
