"""Camera sequencer with one shared Cams/Qt workflow and Maya undo transaction."""
import os
import re

from maya import cmds

try:
    from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QLineEdit
except ImportError:
    from PySide2.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QLineEdit

from ..base_widgets import QFlatDialog, QFlatButton, QFlatSectionHeader
from .. import util


def _camera_shape(transform):
    shapes = cmds.listRelatives(transform, shapes=True, fullPath=True, type="camera") or []
    return shapes[0] if shapes else None


def _selected_cameras():
    """Only camera transforms, preserving selection order and full DAG paths."""
    result = []
    for node in cmds.ls(selection=True, long=True, objectsOnly=True) or []:
        transform = node
        if cmds.nodeType(node) == "camera":
            parents = cmds.listRelatives(node, parent=True, fullPath=True) or []
            transform = parents[0] if parents else node
        if _camera_shape(transform) and transform not in result:
            result.append(transform)
    return result


def create_multicam_rig(cameras, name="camview"):
    """Build a single multi-target constraint and matching focal-length network.

    The entire rig is one undo action; any incomplete creation is rolled back.
    """
    cameras = list(dict.fromkeys(cameras))
    if not cameras or any(not cmds.objExists(cam) or not _camera_shape(cam) for cam in cameras):
        raise ValueError("Select at least one valid camera transform.")
    name = (name or "camview").strip()
    if not re.match(r"^[A-Za-z_][A-Za-z_0-9]*$", name):
        raise ValueError("Camera name must use letters, numbers and underscores.")

    old_selection = cmds.ls(selection=True, long=True) or []
    cmds.undoInfo(openChunk=True, chunkName="Create MultiCams")
    success = False
    try:
        transform, shape = cmds.camera(name=name)
        constraint = cmds.parentConstraint(*(cameras + [transform]), maintainOffset=False,
                                           name="multicam_%s_parentConstraint" % transform)[0]
        weights = cmds.parentConstraint(constraint, query=True, weightAliasList=True) or []
        if len(weights) != len(cameras):
            raise RuntimeError("Camera constraint targets did not match the selection.")

        names = []
        for index, camera in enumerate(cameras):
            label = camera.rsplit("|", 1)[-1].replace(":", "_")
            label = re.sub(r"[^A-Za-z_0-9]", "_", label) or "camera"
            candidate = label
            while candidate in names:
                candidate = "%s_%d" % (label, index + 1)
            names.append(candidate)
        cmds.addAttr(transform, longName="selectedCamera", attributeType="enum",
                     enumName=":".join(names), keyable=True)
        driver = transform + ".selectedCamera"
        # One constraint containing all targets. Each weight gets an explicit
        # driven key at every enum index and a stepped output curve.
        for index, weight in enumerate(weights):
            plug = constraint + "." + weight
            for selection_index in range(len(cameras)):
                cmds.setDrivenKeyframe(plug, currentDriver=driver,
                                       driverValue=selection_index,
                                       value=float(index == selection_index))
            curves = cmds.listConnections(plug, source=True, destination=False, type="animCurve") or []
            for curve in curves:
                cmds.keyTangent(curve, edit=True, outTangentType="step")
        focal_sum = cmds.createNode("plusMinusAverage",
                                    name="multicam_%s_focalSum" % transform)
        for index, camera in enumerate(cameras):
            blend = cmds.createNode("multiplyDivide",
                                    name="multicam_%s_focal_%s" % (transform, index))
            cmds.connectAttr(_camera_shape(camera) + ".focalLength",
                             blend + ".input1X", force=True)
            cmds.connectAttr(constraint + "." + weights[index],
                             blend + ".input2X", force=True)
            cmds.connectAttr(blend + ".outputX",
                             "%s.input1D[%d]" % (focal_sum, index), force=True)
        cmds.connectAttr(focal_sum + ".output1D", shape + ".focalLength", force=True)
        cmds.setAttr(shape + ".renderable", False)
        if not cmds.attributeQuery("cams_type", node=transform, exists=True):
            cmds.addAttr(transform, longName="cams_type", dataType="string")
        cmds.setAttr(transform + ".cams_type", "camera_multicams", type="string")

        container = cmds.createNode("dagContainer", name="%s_MultiCams_GRP" % transform)
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                 "_icons", "camera_multicams.png")
        cmds.setAttr(container + ".iconName", icon_path, type="string")
        cmds.parent(transform, container)
        cmds.select(transform, replace=True)
        success = True
        return transform
    finally:
        cmds.undoInfo(closeChunk=True)
        if not success:
            cmds.undo()
            if old_selection:
                cmds.select(old_selection, replace=True)
            else:
                cmds.select(clear=True)


class multicams(QFlatDialog):
    """Legacy public entrypoint, now using the same Qt controls as the Cams UI."""

    TITLE = "MultiCams"
    dlg_instance = None

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setWindowTitle(self.TITLE)
        self.setMinimumWidth(util.DPI(360))
        self.selected_cameras = []
        layout = QVBoxLayout()
        layout.setContentsMargins(util.DPI(14), util.DPI(12),
                                  util.DPI(14), util.DPI(12))
        layout.setSpacing(util.DPI(7))
        layout.addWidget(QFlatSectionHeader("Source Cameras", self))
        self.cameras = QListWidget(self)
        self.cameras.setMinimumHeight(util.DPI(125))
        layout.addWidget(self.cameras)
        button_row = QHBoxLayout()
        button_row.setSpacing(util.DPI(6))
        self.add_button = QFlatButton("Add Selected", parent=self)
        self.add_button.clicked.connect(self.get_cameras)
        button_row.addWidget(self.add_button)
        self.remove_button = QFlatButton("Remove Highlighted", parent=self)
        self.remove_button.clicked.connect(self.remove_selected)
        button_row.addWidget(self.remove_button)
        layout.addLayout(button_row)
        layout.addWidget(QFlatSectionHeader("New Camera", self))
        self.camera_name = QLineEdit(self)
        self.camera_name.setPlaceholderText("camview")
        layout.addWidget(self.camera_name)
        self.feedback = QLabel("Select camera transforms in Maya, then add them here.", self)
        self.feedback.setWordWrap(True)
        layout.addWidget(self.feedback)
        self.root_layout.addLayout(layout)
        self.create_button = QFlatButton("Create MultiCams", highlight=True, parent=self)
        self.create_button.clicked.connect(self.create_multi)
        footer = QHBoxLayout()
        footer.setContentsMargins(util.DPI(14), 0, util.DPI(14), util.DPI(12))
        footer.addWidget(self.create_button)
        self.root_layout.addLayout(footer)
        self.get_cameras()

    @classmethod
    def showUI(cls, parent=None):
        if cls.dlg_instance is None or not util.is_valid_widget(cls.dlg_instance):
            cls.dlg_instance = cls(parent)
        cls.dlg_instance.show()
        cls.dlg_instance.raise_()
        cls.dlg_instance.activateWindow()
        return cls.dlg_instance

    def get_cameras(self):
        for camera in _selected_cameras():
            if camera not in self.selected_cameras:
                self.selected_cameras.append(camera)
        # Cameras deleted or replaced while the dialog is open must not be used.
        self.selected_cameras = [c for c in self.selected_cameras
                                 if cmds.objExists(c) and _camera_shape(c)]
        self.cameras.clear()
        self.cameras.addItems(self.selected_cameras)
        self.create_button.setEnabled(bool(self.selected_cameras))
        return list(self.selected_cameras)

    def remove_selected(self):
        remove = {item.text() for item in self.cameras.selectedItems()}
        self.selected_cameras = [camera for camera in self.selected_cameras
                                 if camera not in remove]
        self.cameras.clear()
        self.cameras.addItems(self.selected_cameras)
        self.create_button.setEnabled(bool(self.selected_cameras))

    def create_multi(self):
        # Refresh stale references without changing the user's source list.
        self.selected_cameras = [c for c in self.selected_cameras
                                 if cmds.objExists(c) and _camera_shape(c)]
        self.create_button.setEnabled(bool(self.selected_cameras))
        if not self.selected_cameras:
            self.feedback.setText("Add at least one valid Maya camera.")
            return None
        try:
            result = create_multicam_rig(self.selected_cameras,
                                         self.camera_name.text() or "camview")
        except (RuntimeError, ValueError) as exc:
            self.feedback.setText(str(exc))
            cmds.warning("MultiCams: %s" % exc)
            return None
        self.feedback.setText("Created %s" % result)
        self.close()
        return result
