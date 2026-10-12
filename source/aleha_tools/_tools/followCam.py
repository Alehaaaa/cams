"""Follow-camera rig creation with atomic Maya undo and stable channel targets."""
from maya import cmds

from ._camera_rig import (activate_camera, camera_container, camera_transform,
                          camera_undo, ensure_string_attribute)


class followCam:
    def __init__(self):
        self.create_follow_cam()

    def create_follow_cam(self):
        selected = cmds.ls(selection=True, long=True) or []
        if not selected:
            cmds.warning("First, select an object for the Follow Cam to follow.")
            return None
        source, _ = camera_transform(cmds.lookThru(q=True))
        short = selected[0].rsplit("|", 1)[-1].rsplit(":", 1)[-1]
        for separator in ("_", "."):
            if separator in short:
                short = short.rsplit(separator, 1)[0]
                break

        with camera_undo("Create Follow Cam"):
            # Preserve the historical name derived from the selected control.
            camera = cmds.duplicate(source, name=short, inputConnections=False)[0]
            cmds.showHidden(camera)
            cmds.camera(camera, edit=True, lockTransform=False)
            shape = camera_transform(camera)[1]
            cmds.setAttr(shape + ".renderable", False)
            ensure_string_attribute(camera, "cams_type", "camera_follow")

            group = cmds.group(camera, name=camera + "_ORI_GRP")
            point = cmds.pointConstraint(selected[0], group, maintainOffset=True,
                                         name=camera + "_pointConstraint")[0]
            parent = cmds.parentConstraint(selected[0], group, maintainOffset=True,
                                           name=camera + "_parentConstraint")[0]
            point_weight = point + "." + cmds.pointConstraint(point, query=True, weightAliasList=True)[0]
            parent_weight = parent + "." + cmds.parentConstraint(parent, query=True, weightAliasList=True)[0]

            # Explicit paths: selection may change when Maya creates a group or
            # constraint, and abbreviated plugs like ".sx" then lock the wrong node.
            for channel in ("sx", "sy", "sz", "v"):
                cmds.setAttr("%s.%s" % (group, channel), lock=True,
                             channelBox=False, keyable=False)
            cmds.addAttr(group, longName="FaceCamMode", attributeType="enum",
                         enumName="off:on", keyable=True)
            driver = group + ".FaceCamMode"
            cmds.connectAttr(driver, parent_weight, force=True)
            blend = group + ".blendParent1"
            for setting, point_value, blend_value in ((0, 1, 0), (1, 0, 1)):
                cmds.setAttr(driver, setting)
                cmds.setAttr(point_weight, point_value)
                cmds.setAttr(blend, blend_value)
                cmds.setDrivenKeyframe(point_weight, currentDriver=driver)
                cmds.setDrivenKeyframe(blend, currentDriver=driver)
            cmds.setAttr(blend, channelBox=False, keyable=False)
            cmds.setAttr(driver, 1)
            for constraint in (point, parent):
                cmds.setAttr(constraint + ".hiddenInOutliner", True)
            group_id = (cmds.ls(group, uuid=True) or [group])[0]
            ensure_string_attribute(camera, "cams_follow_attr",
                                    "%s|FaceCamMode" % group_id)
            container = camera_container(camera, "FOLLOW", "camera_follow")
            cmds.parent(group, container)
            activate_camera(camera)
        return camera
