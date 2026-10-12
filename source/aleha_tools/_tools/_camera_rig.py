"""Common Maya camera-rig creation and recovery helpers."""
import os
from contextlib import contextmanager

from maya import cmds


@contextmanager
def camera_undo(label):
    """One undo step on success; undo a partially created rig on failure."""
    selection = cmds.ls(selection=True, long=True) or []
    cmds.undoInfo(openChunk=True, chunkName=label)
    completed = False
    try:
        yield
        completed = True
    finally:
        cmds.undoInfo(closeChunk=True)
        if not completed:
            cmds.undo()
            if selection:
                cmds.select([node for node in selection if cmds.objExists(node)],
                            replace=True)
            else:
                cmds.select(clear=True)


def ensure_string_attribute(node, attr, value=None):
    if not cmds.attributeQuery(attr, node=node, exists=True):
        cmds.addAttr(node, longName=attr, dataType="string")
    if value is not None:
        cmds.setAttr("%s.%s" % (node, attr), value, type="string")


def camera_transform(node):
    if not node or not cmds.objExists(node):
        raise RuntimeError("No active camera is available.")
    if cmds.nodeType(node) == "camera":
        node = cmds.listRelatives(node, parent=True, fullPath=True)[0]
    shapes = cmds.listRelatives(node, shapes=True, type="camera") or []
    if not shapes:
        raise RuntimeError("%s is not a camera." % node)
    return node, shapes[0]


def camera_container(camera, suffix, icon):
    container = cmds.createNode("dagContainer", name="%s_%s_GRP" % (camera, suffix))
    for plug in cmds.listAnimatable(container) or []:
        channel = plug.rsplit(".", 1)[-1]
        cmds.setAttr(container + "." + channel, edit=True, keyable=False, lock=True)
    icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                             "_icons", icon + ".png")
    cmds.setAttr(container + ".iconName", icon_path, type="string")
    return container


def activate_camera(camera):
    try:
        panel = cmds.getPanel(withFocus=True)
        if panel and cmds.getPanel(typeOf=panel) == "modelPanel":
            cmds.lookThru(panel, camera)
    except RuntimeError:
        pass
    cmds.camera(camera, edit=True, lockTransform=True)
    cmds.select(camera, replace=True)
