import maya.cmds as cmds
import random
import os


"""
MultiCams Tool
"""


class multicams:
    TITLE = "MultiCams"

    def __init__(self):
        self.__margin__ = 3
        self.__width__ = 90

        self.selected_cameras = None

        # Create window
        if cmds.window(self.TITLE, exists=True):
            cmds.deleteUI(self.TITLE)
        try:
            window = cmds.window(self.TITLE, menuBar=True, rtf=True, tlb=True, s=False)
        except Exception:
            window = cmds.window(self.TITLE, menuBar=True, rtf=True, s=False)

        cmds.columnLayout()
        cmds.separator(h=self.__margin__, st="none")

        cmds.rowLayout(numberOfColumns=5)
        cmds.separator(w=self.__margin__, st="none")
        cmds.rowColumnLayout(numberOfColumns=3)
        cmds.columnLayout()
        self.textScrollList_layout = cmds.columnLayout()
        self.cameras = cmds.textScrollList(w=self.__width__, h=self.__width__ / 1.2)
        cmds.setParent("..")
        cmds.separator(h=5, st="none")
        cmds.button(
            "select_cameras",
            label="Add Camera(s)",
            w=self.__width__,
            h=25,
            bgc=self.getcolor(),
            command=lambda *args: self.get_cameras(),
        )
        cmds.setParent("..")
        cmds.setParent("..")
        cmds.separator(w=15, h=80, st="single", hr=0)
        cmds.columnLayout()
        cmds.text(label="Add cameras and\nhit the button", w=self.__width__)
        cmds.separator(h=8, st="none")
        cmds.button(
            label="Create!",
            w=self.__width__,
            h=35,
            bgc=self.getcolor(),
            command=lambda *args: self.create_multi(),
        )
        cmds.separator(h=8, st="none")
        self.camera_name = cmds.textField(w=self.__width__, placeholderText="Camera name")
        cmds.setParent("..")
        cmds.separator(w=self.__margin__, st="none")
        cmds.setParent("..")
        cmds.separator(h=self.__margin__, st="none")

        cmds.showWindow(window)

    def getcolor(self):
        return [round(random.uniform(0.525, 0.750), 3) for i in range(3)]

    def get_cameras(self):
        __selection__ = cmds.ls(selection=True) or []
        self.selected_cameras = [
            c for c in __selection__ if c in [x.split("|")[-2] for x in cmds.ls(type=("camera"), l=True)]
        ]
        self.selected_cameras.sort()

        cmds.deleteUI(self.cameras)
        self.cameras = cmds.textScrollList(
            parent=self.textScrollList_layout,
            w=self.__width__,
            h=self.__width__ / 1.2,
            append=self.selected_cameras,
        )

    def create_multi(self):
        if not self.selected_cameras:
            return

        input_name = cmds.textField(self.camera_name, q=True, text=True)
        cam_name = input_name if input_name else "camview"

        cmds.undoInfo(openChunk=True)
        new_cam = cmds.rename(cmds.camera()[0], cam_name)

        # Parent new camera to selected ones
        constraint = "multicam_" + new_cam + "_parentConstraint"
        for obj in self.selected_cameras:
            cmds.parentConstraint(obj, new_cam, n=constraint)

        # Lock and Hide attributes
        attributes = [
            str(c).split("|")[-1] for c in cmds.listAnimatable(new_cam) if "%s." % (new_cam) in str(c)
        ]
        for a in attributes:
            cmds.setAttr(a, keyable=False, cb=False, lock=True)

        # Get camera names for enum attribute, shorten them id too long
        enum_names = []
        for s in self.selected_cameras:
            enum_names.append(s)

        # Add enum attribute with shortened names of selected cameras
        cmds.addAttr(
            new_cam,
            niceName="------",
            longName="selectedCamera",
            attributeType="enum",
            keyable=True,
            enumName=":".join(enum_names),
        )

        parent_attributes = []
        for attribute in cmds.listAnimatable(constraint):
            if attribute[-2] == "W" or attribute[-3] == "W":
                parent_attributes.append(attribute.split(".")[-1])

        for i, parent_attribute in enumerate(parent_attributes):
            for j in range(len(parent_attributes)):
                cmds.setDrivenKeyframe(
                    constraint,
                    at=parent_attribute,
                    cd="{}.selectedCamera".format(new_cam),
                    dv=j,
                    v=i == j,
                )
            cmds.setAttr("{}.{}".format(constraint, parent_attribute))

        # cam_name = cmds.camera(new_cam, q = True, name = True)
        plusMinusAverage = "multicam_%s_plusMinusAverage" % (new_cam)

        if not cmds.objExists("multicam_%s_plusMinusAverage" % (new_cam)):
            cmds.shadingNode("plusMinusAverage", asUtility=True, name=plusMinusAverage)

        for i, c in enumerate(self.selected_cameras):
            md_name = "multicam_%s_%s_multiplyDivide" % (new_cam, c)

            if not cmds.objExists(md_name):
                cmds.shadingNode("multiplyDivide", asUtility=True, name=md_name)

            cmds.connectAttr("%s.fl" % (c), "%s.input1X" % (md_name), f=True)

            cmds.connectAttr(
                "%s.%s" % (constraint, parent_attributes[i]),
                "%s.input2X" % (md_name),
                f=True,
            )

            cmds.connectAttr(
                "%s.outputX" % (md_name),
                "%s.input1D[%s]" % (plusMinusAverage, i),
                f=True,
            )

        cmds.connectAttr(
            "%s.output1D" % (plusMinusAverage),
            "%s.fl" % (cmds.listRelatives(new_cam, shapes=True)[0]),
            f=True,
        )
        type_of_camera = "camera_multicams"
        if not cmds.objExists("%s.cams_type" % new_cam):
            cmds.addAttr(new_cam, ln="cams_type", dt="string")
        cmds.setAttr("%s.cams_type" % new_cam, type_of_camera, type="string")

        main_grp = cmds.createNode("dagContainer", name="%s_MultiCams_GRP" % new_cam)
        main_attrs_to_lock = [i.rsplit(".", 1)[-1] for i in cmds.listAnimatable(main_grp)]
        for attr in main_attrs_to_lock:
            cmds.setAttr(main_grp + "." + attr, e=True, keyable=False, lock=True)
        tools_folder = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
        icon_path = os.path.join(tools_folder, "_icons", type_of_camera + ".png")
        cmds.setAttr(main_grp + ".iconName", icon_path, type="string")

        cmds.parent(new_cam, main_grp)

        cmds.select(new_cam, replace=True)
        cmds.undoInfo(closeChunk=True)
