from __future__ import division
import maya.cmds as cmds
import maya.OpenMayaUI as omui
import os


try:
    from PySide6.QtWidgets import (  # type: ignore
        QWidget,
        QVBoxLayout,
        QLabel,
        QFrame,
        QLineEdit,
        QMenuBar,
        QGridLayout,
        QComboBox,
        QSizePolicy,
    )
    from PySide6.QtGui import (  # type: ignore
        QIcon,
        QAction,
        QActionGroup,
    )
    from PySide6.QtCore import (  # type: ignore
        Qt,
    )
except ImportError:
    from PySide2.QtWidgets import (
        QWidget,
        QLabel,
        QFrame,
        QVBoxLayout,
        QLineEdit,
        QMenuBar,
        QGridLayout,
        QComboBox,
        QSizePolicy,
        QActionGroup,
        QAction,
    )
    from PySide2.QtGui import (
        QIcon,
        QRegExpValidator,
    )
    from PySide2.QtCore import (
        Qt,
        QRegExp,
    )

    QRegularExpression = QRegExp
    QRegularExpressionValidator = QRegExpValidator

from functools import partial

try:
    from importlib import reload
except ImportError:
    pass

from .. import util
from ..widgets import QFlatDialog, QFlatConfirmDialog

reload(util)


def DPI(val):
    return omui.MQtUtil.dpiScale(val)


def apply_selection(settings):
    # Command for displaying the current frame number (HUD Section 4)
    def HUD_current_frame():
        Current = cmds.currentTime(query=True)
        Total = cmds.playbackOptions(query=True, maxTime=True)
        result = "{} / {}".format(int(Current), int(Total))
        return result

    # Command for displaying the number of total frames
    def HUD_total_frames():
        result = cmds.playbackOptions(query=True, maxTime=True)
        return result

    # Command for displaying the number of total frames
    def HUD_framerate():
        fps_map = {
            "game": 15,
            "film": 24,
            "pal": 25,
            "ntsc": 30,
            "show": 48,
            "palf": 50,
            "ntscf": 60,
        }
        fps = cmds.currentUnit(q=True, t=True)
        if not isinstance(fps, float):
            fps = fps_map.get(fps, "None")
        return str(fps) + "fps"

    def HUD_camera_focal_length():
        # Get the camera attached to the active model panel
        try:
            ModelPane = cmds.getPanel(withFocus=True)
            Camera = cmds.modelPanel(ModelPane, query=True, camera=True)
            Attr = ".focalLength"
            result = cmds.getAttr(Camera + Attr)
        except Exception:
            result = "None"
        return result

    # Command for displaying the scene name (HUD Section 7)
    def HUD_get_scene_name():
        result = cmds.file(query=True, sceneName=True, shortName=True)
        if not result:
            result = "UNTITLED Scene"
        else:
            result = result.rsplit(".", 1)[0]
        return result

    # Command for displaying the current user name (HUD Section 9)
    def HUD_get_username():
        username = os.getenv("USER")
        result = username if username else "UNKNOWN"
        return result

    # Command for displaying the date and hour (HUD Section 9)
    def HUD_get_date():
        import datetime

        result = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        return result

    # Show HUD Display
    FontSize = "large"  # "small" or "large"

    # Remove HUD sections if they already exist
    for pos in [0, 2, 4, 5, 7, 9]:
        cmds.headsUpDisplay(removePosition=[pos, 0])

    headsup_positions = {
        "tlc": ["top_left", 0],
        "tmc": ["top_center", 2],
        "trc": ["top_right", 4],
        "blc": ["bottom_left", 5],
        "bmc": ["bottom_center", 7],
        "brc": ["bottom_right", 9],
    }

    for key, item in headsup_positions.items():
        selected_command = settings[key]
        if selected_command != 0:
            align = item[0].split("_")[-1]

            command = None
            preset = None
            if selected_command == 1:
                label = ""
                command = HUD_get_scene_name
            elif selected_command == 2:
                label = "Frame:"
                command = HUD_current_frame
            elif selected_command == 3:
                label = "Total:"
                command = HUD_total_frames
            elif selected_command == 4:
                label = ""
                command = HUD_framerate
            elif selected_command == 5:
                label = "User:"
                command = HUD_get_username
            elif selected_command == 6:
                preset = "cameraNames"
            elif selected_command == 7:
                label = "Focal Length:"
                command = HUD_camera_focal_length
            elif selected_command == 8:
                preset = "viewAxis"
            elif selected_command == 9:
                label = ""
                command = HUD_get_date
            elif selected_command == 10:
                preset = "sceneTimecode"
            elif selected_command == 11:
                preset = "frameRate"

            else:
                continue

            if command:
                cmds.headsUpDisplay(
                    item[0],
                    section=item[1],
                    block=0,
                    bs=FontSize,
                    label=label,
                    dfs=FontSize,
                    lfs=FontSize,
                    command=command,
                    blockAlignment=align,
                    attachToRefresh=True,
                )
            if preset:
                cmds.headsUpDisplay(
                    item[0],
                    section=item[1],
                    block=0,
                    bs=FontSize,
                    dfs=FontSize,
                    lfs=FontSize,
                    preset=preset,
                    blockAlignment=align,
                )

    # Set HUD display color to Maya default
    cmds.displayColor("headsUpDisplayLabels", 16, dormant=True)
    cmds.displayColor("headsUpDisplayValues", 16, dormant=True)


class HUDWindow(QFlatDialog):
    dlg_instance = None

    @classmethod
    def showUI(cls, parent):
        if not cls.dlg_instance:
            cls.dlg_instance = HUDWindow(parent)

        if cls.dlg_instance.isHidden():
            cls.dlg_instance.show()

        else:
            cls.dlg_instance.raise_()
            cls.dlg_instance.activateWindow()

    def __init__(self, parent=None):
        QFlatDialog.__init__(self, parent)
        self.setWindowTitle("HUD Editor")
        self.setWindowFlags(self.windowFlags() | Qt.WindowCloseButtonHint)

        self.get_prefs()
        self.root_layout.setContentsMargins(0, 0, 0, 0)

        # Menu bar layout
        menu_bar = QMenuBar()
        self.menu_presets = menu_bar.addMenu("Presets")
        self.action_group = QActionGroup(self)
        for i in self.hud_presets:
            self.add_menu_preset(i)

        menu_edit = menu_bar.addMenu("Edit")
        new_btn = menu_edit.addAction(QIcon(util.return_icon_path("select")), "Create New")
        self.duplicate_btn = menu_edit.addAction(QIcon(util.return_icon_path("duplicate")), "Duplicate")
        menu_edit.addSeparator()
        self.reset_btn = menu_edit.addAction(QIcon(util.return_icon_path("refresh")), "Reset Current")
        self.delete_btn = menu_edit.addAction(QIcon(util.return_icon_path("remove")), "Delete Current")

        self.root_layout.setMenuBar(menu_bar)

        new_btn.triggered.connect(lambda: self.new_preset())
        self.duplicate_btn.triggered.connect(lambda: self.new_preset(duplicate=True))
        self.reset_btn.triggered.connect(lambda: self.reset_preset())
        self.delete_btn.triggered.connect(lambda: self.delete_preset())

        # Create a widget to hold the rectangle and comboboxes
        widget = QWidget()
        self.root_layout.addWidget(widget, 1)

        # Create a layout for the widget
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(DPI(10), DPI(2), DPI(10), DPI(2))

        # Create the rectangle and add it to the layout
        rectangle = QFrame()
        rectangle.setFrameShape(QFrame.StyledPanel)
        rectangle.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        width = 350
        rectangle.setMinimumSize(DPI(width), DPI(width / 16 * 9))

        layout.addWidget(rectangle)

        # Create a layout for the comboboxes
        combo_layout = QGridLayout()

        self.all_combos = {
            "tlc": ["top_left", 0],
            "tmc": ["top_mid", 2],
            "trc": ["top_right", 4],
            "blc": ["bottom_left", 5],
            "bmc": ["bottom_mid", 7],
            "brc": ["bottom_right", 9],
        }
        self.hud_items = {
            0: "None",
            1: "Scene Name",
            2: "Current Frame",
            3: "Total Frames",
            4: "Framerate",
            5: "Username",
            6: "Camera Name",
            7: "Focal Length",
            8: "View Axis",
            9: "Date",
            10: "Timecode",
            11: "Refresh Rate",
        }

        self.default_hud = {
            "bmc": 6,
            "trc": 0,
            "tlc": 0,
            "tmc": 0,
            "brc": 0,
            "blc": 8,
        }

        # Create the comboboxes and add them to the layout
        self.tlc = QComboBox()
        self.insert_items(self.tlc, self.hud_items.values())

        combo_layout.addWidget(self.tlc, 0, 0, Qt.AlignTop | Qt.AlignLeft)

        self.tmc = QComboBox()
        self.insert_items(self.tmc, self.hud_items.values())
        combo_layout.addWidget(self.tmc, 0, 1, Qt.AlignTop | Qt.AlignHCenter)

        self.trc = QComboBox()
        self.insert_items(self.trc, self.hud_items.values())
        combo_layout.addWidget(self.trc, 0, 2, Qt.AlignTop | Qt.AlignRight)

        self.blc = QComboBox()
        self.insert_items(self.blc, self.hud_items.values())
        combo_layout.addWidget(self.blc, 2, 0, Qt.AlignBottom | Qt.AlignLeft)

        self.bmc = QComboBox()
        self.insert_items(self.bmc, self.hud_items.values())
        combo_layout.addWidget(self.bmc, 2, 1, Qt.AlignBottom | Qt.AlignHCenter)

        self.brc = QComboBox()
        self.insert_items(self.brc, self.hud_items.values())
        combo_layout.addWidget(self.brc, 2, 2, Qt.AlignBottom | Qt.AlignRight)

        title_layout = QVBoxLayout()
        title_layout.setSpacing(DPI(4))

        self.preset_title = QLineEdit()
        self.preset_title.setStyleSheet("font-size: {}px;".format(DPI(16)))
        self.preset_title.setMaxLength(25)
        title_layout.addWidget(QLabel("Current Preset:"))
        title_layout.addWidget(self.preset_title)
        combo_layout.addLayout(title_layout, 1, 1, Qt.AlignCenter)

        self.preset_title.returnPressed.connect(self.save_prefs)

        # Set the spacing of the combobox layout
        combo_layout.setSpacing(DPI(10))

        # Add the combobox layout to the rectangle
        rectangle.setLayout(combo_layout)

        self.setBottomBar(
            QFlatConfirmDialog.CustomButton(
                "OK",
                callback=partial(self.save_changes, close=True),
                icon=util.return_icon_path("apply"),
                highlight=True,
            ),
            closeButton=True,
        )

        self.refresh_ui()

    def insert_items(self, combo, items):
        for item in items:
            combo.addItem(item)
            if item == "None":
                combo.insertSeparator(combo.count())

    def add_menu_preset(self, preset_name, checked=False):
        preset_btn = QAction(preset_name, self)
        preset_btn.setCheckable(True)
        self.action_group.addAction(preset_btn)
        self.menu_presets.addAction(preset_btn)
        preset_btn.triggered.connect(partial(self.refresh_ui, preset_name, True))
        if checked:
            preset_btn.setChecked(True)

    def save_changes(self, close=False):
        self.save_prefs()
        if close:
            self.close()

        apply_selection(self.hud_presets[self.get_current_preset()])

    def get_current_preset(self):
        return str(self.preset_title.text())

    def get_prefs(self):
        self.prefs_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "_prefs",
            "hudSettings.aleha",
        )

        with open(self.prefs_path, "r") as prefs_file:
            self.user_prefs = eval(prefs_file.read())
            self.hud_presets = self.user_prefs["presets"]

    def save_to_disk(self):
        with open(self.prefs_path, "w") as prefs_file:
            self.user_prefs["presets"] = self.hud_presets
            self.user_prefs["selected"] = list(self.hud_presets.keys()).index(self.get_current_preset())
            prefs_file.write(str(self.user_prefs))

    def save_prefs(self):
        current_preset = self.get_current_preset()
        if self.displayed_preset == "Default" and current_preset != "Default":
            cmds.warning("Cannot modify Default preset name.")
            self.preset_title.setText("Default")
            current_preset = "Default"

        try:
            if current_preset != self.displayed_preset:
                self.hud_presets[current_preset] = self.hud_presets.pop(self.displayed_preset)
                for action in self.menu_presets.actions():
                    if action.text() == self.displayed_preset:
                        self.menu_presets.removeAction(action)
                self.add_menu_preset(current_preset, checked=True)
                self.displayed_preset = current_preset

            for combo in self.all_combos:
                current_text = getattr(self, combo).currentText()
                self.hud_presets[current_preset][combo] = list(self.hud_items.values()).index(current_text)
        except Exception:
            self.preset_title.setText("")
            pass
        self.preset_title.clearFocus()

        self.save_to_disk()

    def new_preset(self, duplicate=False):
        def get_new_name(name="New Preset"):
            for r in range(30):
                preset_name = "%s %s" % (name, r) if r else name
                if preset_name not in list(self.hud_presets.keys()):
                    break
            return preset_name

        if duplicate:
            current_preset = self.get_current_preset()
            preset_name = get_new_name(current_preset)
            self.hud_presets[preset_name] = self.hud_presets[current_preset].copy()
        else:
            preset_name = get_new_name()
            self.hud_presets[preset_name] = self.default_hud

        self.add_menu_preset(preset_name, checked=True)
        self.refresh_ui(preset_name, change=True)
        self.save_prefs()
        self.preset_title.setFocus()

    def delete_preset(self):
        current_preset = self.get_current_preset()

        if current_preset != "Default":
            response = QFlatConfirmDialog.question(
                None,
                "Delete Preset",
                "Do you want to delete '%s'?" % current_preset,
                buttons=QFlatConfirmDialog.Yes | QFlatConfirmDialog.No,
                highlight=QFlatConfirmDialog.No,
            )

            if response == QFlatConfirmDialog.Yes:
                self.hud_presets.pop(current_preset)

                for action in self.menu_presets.actions():
                    if action.text() == current_preset:
                        self.menu_presets.removeAction(action)
                self.refresh_ui()
                self.save_prefs()
        else:
            QFlatConfirmDialog.question(
                None,
                "Cannot delete Default",
                "The Default preset cannot be deleted.",
                buttons=QFlatConfirmDialog.Ok,
                highlight=QFlatConfirmDialog.Ok,
            )

    def reset_preset(self):
        current_preset = self.get_current_preset()

        response = QFlatConfirmDialog.question(
            None,
            "Reset Preset",
            "Do you want to reset '%s' to the default settings?" % current_preset,
            buttons=QFlatConfirmDialog.Yes | QFlatConfirmDialog.No,
            highlight=QFlatConfirmDialog.No,
        )

        if response == QFlatConfirmDialog.Yes:
            self.hud_presets[current_preset] = self.default_hud
            self.refresh_ui()
            self.save_prefs()

    def refresh_ui(self, preset=None, change=False):
        current_preset = self.get_current_preset()

        if len(self.hud_presets.keys()) == 0:
            self.delete_btn.setVisible(False)
            self.duplicate_btn.setVisible(False)
            self.menu_presets
            preset = ""
        else:
            self.duplicate_btn.setVisible(True)
            self.delete_btn.setVisible(True)

            if preset != current_preset:
                if change:
                    if self.displayed_preset != "":
                        for combo in self.all_combos:
                            current_combo = list(self.hud_items.values()).index(getattr(self, combo).currentText())
                            if current_combo != self.user_prefs["presets"][self.displayed_preset][combo]:
                                response = QFlatConfirmDialog.question(
                                    None,
                                    "Unsaved changes",
                                    "Do you want to save the changes made to this preset?",
                                    buttons=QFlatConfirmDialog.Yes | QFlatConfirmDialog.No,
                                    highlight=QFlatConfirmDialog.No,
                                )

                                if response == QFlatConfirmDialog.Yes:
                                    self.save_prefs()
                                break
                    self.preset_title.clearFocus()
                else:
                    pref_sel = self.user_prefs["selected"]
                    selected = pref_sel if len(self.hud_presets.keys()) > pref_sel else -1
                    preset = (list(self.hud_presets.keys()))[selected]
                    self.action_group.actions()[selected].setChecked(True)
                    self.preset_title.clearFocus()

                for combo in self.all_combos:
                    current_selection = self.hud_presets[preset][combo]
                    getattr(self, combo).setCurrentText(
                        self.hud_items.get(current_selection) if current_selection else self.hud_items.get(0)
                    )
            if preset == "Default":
                self.delete_btn.setEnabled(False)
            else:
                self.delete_btn.setEnabled(True)

            self.preset_title.setText(preset)

        if self.preset_title.text():
            self.preset_title.setEnabled(True)
        else:
            self.preset_title.setEnabled(False)

        self.displayed_preset = preset


if __name__ == "__main__":
    HUDWindow.showUI()
