import maya.cmds as cmds
import os


class aimCam:
    def __init__(self):
        self.create_aim_cam()

    def create_aim_cam(self):
        ori_cam = cmds.lookThru(q=1)
        sel = cmds.ls(sl=1)

        if ori_cam and sel:
            sel = sel[0]
            type_of_camera = "camera_aim"

            if ":" in ori_cam:
                new_name = ori_cam.split(":")[-1]
                group_name = "%s_AIM_GRP" % new_name
            else:
                new_name = "%s_AIM" % ori_cam
                group_name = "%s_GRP" % new_name

            cmds.undoInfo(openChunk=True)
            aim_cam = cmds.duplicate(ori_cam, name=new_name, ic=False)
            aim_cam = aim_cam[0]
            cmds.showHidden(aim_cam)
            cmds.setAttr("%s.renderable" % cmds.listRelatives(aim_cam, shapes=True)[0], False)
            for ax in "xyz":
                for attr in "trs":
                    cmds.setAttr("%s.%s%s" % (aim_cam, attr, ax), lock=0)

            cmds.setAttr("%s.cams_type" % aim_cam, type_of_camera, type="string")

            offset = cmds.spaceLocator(n="%s_Offset" % aim_cam)
            off_grp = cmds.group(offset, name="%s_Offset_GRP" % aim_cam, w=1)
            cmds.setAttr("%s.cams_aim_offset" % aim_cam, offset[0], type="string")
            cmds.hide(offset)

            main_grp = cmds.createNode("dagContainer", name=group_name)
            main_attrs_to_lock = [i.rsplit(".", 1)[-1] for i in cmds.listAnimatable(main_grp)]
            for attr in main_attrs_to_lock:
                cmds.setAttr(main_grp + "." + attr, e=True, keyable=False, lock=True)
            tools_folder = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
            icon_path = os.path.join(tools_folder, "_icons", type_of_camera + ".png")
            cmds.setAttr(main_grp + ".iconName", icon_path, type="string")

            cmds.pointConstraint(ori_cam, aim_cam)
            cmds.pointConstraint(sel, off_grp)
            cmds.aimConstraint(offset, aim_cam, mo=1)

            cmds.parent(aim_cam, main_grp)
            cmds.parent(off_grp, main_grp)

            cmds.lookThru(cmds.getPanel(wf=True), aim_cam)
            cmds.camera(aim_cam, e=1, lt=1)

            cmds.select(aim_cam, replace=True)
            cmds.undoInfo(closeChunk=True)
        elif not sel:
            cmds.warning("First, select an object for the Aim Cam to point to.")
