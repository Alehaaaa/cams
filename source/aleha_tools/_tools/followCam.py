import maya.cmds as cmds
import os


class followCam:
    def __init__(self):
        self.create_follow_cam()

    def create_follow_cam(self):
        ori_cam = cmds.lookThru(q=1)
        sel = cmds.ls(sl=1)

        if ori_cam and sel:
            sel = sel[0]
            type_of_camera = "camera_follow"
            new_name = sel

            filters = ["_", "."]
            for f in filters:
                if f in sel:
                    new_name = new_name.rsplit(f, 1)[0]
                    break

            cmds.undoInfo(openChunk=True)
            fol_cam = cmds.duplicate(ori_cam, name=new_name, ic=False)
            fol_cam = fol_cam[0]
            cmds.showHidden(fol_cam)
            cmds.camera(fol_cam, e=1, lt=0)

            for attr in ["cams_type", "cams_follow_attr"]:
                if not cmds.objExists("%s.%s" % (fol_cam, attr)):
                    cmds.addAttr(fol_cam, ln=attr, dt="string")

            cmds.setAttr("%s.renderable" % cmds.listRelatives(fol_cam, shapes=True)[0], False)
            cmds.setAttr("%s.cams_type" % fol_cam, type_of_camera, type="string")

            # Groups the camera and positions it at the selected control
            cam_grp = cmds.group((fol_cam))
            # Constrains the group to the selected control
            point = cmds.pointConstraint(sel, cam_grp, mo=1)
            point = cmds.rename(point, (fol_cam + "_pointConstraint"))
            point_weight = point + "." + cmds.pointConstraint(point, q=1, wal=1)[0]
            # Locks and hides the scale and visibility attributes.
            cmds.setAttr(".sx", lock=True, channelBox=False, keyable=False)
            cmds.setAttr(".sy", lock=True, channelBox=False, keyable=False)
            cmds.setAttr(".sz", lock=True, channelBox=False, keyable=False)
            cmds.setAttr(".v", lock=True, channelBox=False, keyable=False)
            # Creates an orient constraint to be used in face cam mode
            parent = cmds.parentConstraint(sel, cam_grp, mo=1)
            parent = cmds.rename(parent, (fol_cam + "_parentConstraint"))
            parent_weight = parent + "." + cmds.parentConstraint(parent, q=1, wal=1)[0]
            # Renames the camera group
            cam_grp = cmds.rename(cam_grp, fol_cam + "_ORI_GRP")
            if isinstance(cam_grp, list):
                cam_grp = cam_grp[0]

            # Creates a face cam attribute
            attr_name = "FaceCamMode"
            cmds.addAttr(cam_grp, longName=attr_name, attributeType="enum", enumName="off:on")
            cam_grp_attr = "%s.%s" % (cam_grp, attr_name)

            cmds.setAttr(cam_grp_attr, keyable=True)
            # Connects the constraint to the face cam attribute
            cmds.connectAttr(cam_grp_attr, parent_weight, f=1)
            # Set up set driven key
            cmds.setDrivenKeyframe(point_weight, currentDriver=cam_grp_attr)
            # Set first keyframe
            cmds.setAttr(cam_grp_attr, 0)
            cmds.setAttr(point_weight, 1)
            cmds.setAttr(cam_grp + ".blendParent1", 0)
            cmds.setDrivenKeyframe(point_weight, currentDriver=cam_grp_attr)
            cmds.setDrivenKeyframe(cam_grp + ".blendParent1", currentDriver=cam_grp_attr)
            # Set second keyframe
            cmds.setAttr(cam_grp_attr, 1)
            cmds.setAttr(point_weight, 0)
            cmds.setAttr(cam_grp + ".blendParent1", 1)
            cmds.setDrivenKeyframe(point_weight, currentDriver=cam_grp_attr)
            cmds.setDrivenKeyframe(cam_grp + ".blendParent1", currentDriver=cam_grp_attr)
            # Hides the blend parent
            cmds.setAttr(cam_grp + ".blendParent1", channelBox=False, keyable=False)
            # Sets face cam mode to off
            cmds.setAttr(cam_grp_attr, 1)
            # Hide the constraints in the outliner
            cmds.setAttr((point + ".hiddenInOutliner"), True)
            cmds.setAttr((parent + ".hiddenInOutliner"), True)

            try:
                _cam_grp = cmds.ls(cam_grp, uuid=True)[0]
            except Exception:
                _cam_grp = cam_grp

            cmds.setAttr(
                "%s.cams_follow_attr" % fol_cam,
                str(_cam_grp + "|FaceCamMode"),
                type="string",
            )

            main_grp = cmds.createNode("dagContainer", name="%s_FOLLOW_GRP" % fol_cam)
            main_attrs_to_lock = [i.rsplit(".", 1)[-1] for i in cmds.listAnimatable(main_grp)]
            for attr in main_attrs_to_lock:
                cmds.setAttr(main_grp + "." + attr, e=True, keyable=False, lock=True)
            tools_folder = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
            icon_path = os.path.join(tools_folder, "_icons", type_of_camera + ".png")
            cmds.setAttr(main_grp + ".iconName", icon_path, type="string")

            cmds.parent(cam_grp, main_grp)

            # Switches current camera to new camera
            cmds.lookThru(cmds.getPanel(wf=True), fol_cam)
            cmds.camera(fol_cam, e=1, lt=1)

            cmds.select(fol_cam, replace=True)
            cmds.undoInfo(closeChunk=True)
        elif not sel:
            cmds.warning("First, select an object for the Follow Cam to be parented to.")
