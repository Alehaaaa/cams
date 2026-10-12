"""Aim camera rig creation from the active viewport and Maya selection."""
from maya import cmds

from ._camera_rig import (activate_camera, camera_container, camera_transform,
                          camera_undo, ensure_string_attribute)


class aimCam:
    def __init__(self):
        self.create_aim_cam()

    def create_aim_cam(self):
        selected = cmds.ls(selection=True, long=True) or []
        if not selected:
            cmds.warning("First, select an object for the Aim Cam to point to.")
            return None
        source, _ = camera_transform(cmds.lookThru(q=True))
        short = source.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
        name = ("%s_AIM" % short) if ":" not in source else short
        with camera_undo("Create Aim Cam"):
            camera = cmds.duplicate(source, name=name, inputConnections=False)[0]
            cmds.showHidden(camera)
            shape = camera_transform(camera)[1]
            cmds.setAttr(shape + ".renderable", False)
            for channel in "trs":
                for axis in "xyz":
                    cmds.setAttr("%s.%s%s" % (camera, channel, axis), lock=False)
            ensure_string_attribute(camera, "cams_type", "camera_aim")

            offset = cmds.spaceLocator(name=camera + "_Offset")[0]
            offset_group = cmds.group(offset, name=camera + "_Offset_GRP",
                                      world=True)
            ensure_string_attribute(camera, "cams_aim_offset", offset)
            cmds.hide(offset)

            container = camera_container(camera, "AIM", "camera_aim")
            cmds.pointConstraint(source, camera)
            cmds.pointConstraint(selected[0], offset_group)
            cmds.aimConstraint(offset, camera, maintainOffset=True)
            cmds.parent(camera, container)
            cmds.parent(offset_group, container)
            activate_camera(camera)
        return camera
