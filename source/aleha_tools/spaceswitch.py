from __future__ import division
# -*- coding: utf-8 -*-

import ast
import math
import sys

from maya import cmds, mel
from maya import OpenMaya as om
from maya import OpenMayaUI as omui

try:
    PYSIDE_VERSION = 6
    from PySide6 import QtCore, QtGui, QtWidgets
    from PySide6.QtWidgets import (
        QWidget,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QFrame,
        QVBoxLayout,
        QSizePolicy,
        QSizeGrip,
        QListWidget,
        QListWidgetItem,
        QGraphicsOpacityEffect,
    )
    from PySide6.QtGui import (
        QIcon,
        QPainter,
        QColor,
        QCursor,
        QPixmap,
        QPen,
        QPolygonF,
        QGuiApplication,
        QBrush,
    )
    from PySide6.QtCore import Qt, QPointF, QPoint, QTimer, QSettings, QSize, QRectF
except ImportError:
    PYSIDE_VERSION = 2
    from PySide2 import QtCore, QtGui, QtWidgets
    from PySide2.QtWidgets import (
        QWidget,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QFrame,
        QVBoxLayout,
        QSizePolicy,
        QSizeGrip,
        QListWidget,
        QListWidgetItem,
        QGraphicsOpacityEffect,
    )
    from PySide2.QtGui import (
        QIcon,
        QPainter,
        QColor,
        QCursor,
        QPixmap,
        QPen,
        QPolygonF,
        QGuiApplication,
        QBrush,
    )
    from PySide2.QtCore import Qt, QPointF, QPoint, QTimer, QSettings, QSize, QRectF

import aleha_tools
from aleha_tools import base_widgets, util, widgets

try:
    from importlib import reload
except ImportError:
    reload = None


DEBUG_RELOAD = False

if DEBUG_RELOAD and reload:
    reload(aleha_tools)
    reload(base_widgets)
    reload(util)
    reload(widgets)


_MAIN_DICT = sys.modules["__main__"].__dict__

DATA = {
    "TOOL": "SpaceSwitch",
    "VERSION": "2.2.0",
}
DATA["AUTHOR"] = aleha_tools.DATA["AUTHOR"]

COLOR_BG_MAIN = "#101010"
COLOR_BG_POPUP = "#444444"
COLOR_BG_TRACK = "#333333"
COLOR_ACCENT_DARK = "#7f4a77"
COLOR_ACCENT_MAIN = "#d384ca"
COLOR_ACCENT_LIGHT = "#e59ed0"
COLOR_ACCENT_HOVER = "#e688da"
COLOR_ACCENT_WHITE = "#f2c3ed"
COLOR_TEXT_MAIN = "#2a2a2a"
COLOR_TEXT_SECONDARY = "#bbbbbb"
COLOR_BLEND_MULTI = "#584655"


class Qtx(object):
    @staticmethod
    def global_pos(event):
        if PYSIDE_VERSION < 6:
            return event.globalPos()
        return event.globalPosition().toPoint()

    @staticmethod
    def local_x(event):
        if PYSIDE_VERSION < 6:
            return int(event.x())
        return int(event.position().x())

    @staticmethod
    def exec_menu(menu, pos):
        fn = getattr(menu, "exec", None) or getattr(menu, "exec_", None)
        if fn:
            return fn(pos)
        return None


class Maya(object):
    @staticmethod
    def exists(node):
        try:
            return bool(node and cmds.objExists(node))
        except Exception:
            return False

    @staticmethod
    def plug(node, attr):
        return "%s.%s" % (node, attr)

    @staticmethod
    def attr_exists(node, attr):
        try:
            return cmds.objExists(Maya.plug(node, attr))
        except Exception:
            return False

    @staticmethod
    def is_referenced(node):
        try:
            return cmds.referenceQuery(node, isNodeReferenced=True)
        except Exception:
            return False

    @staticmethod
    def reference_namespace(node):
        try:
            return cmds.referenceQuery(node, namespace=True).strip(":")
        except Exception:
            return ""

    @staticmethod
    def attr_type(node, attr, default=None):
        try:
            return cmds.attributeQuery(attr, node=node, attributeType=True)
        except Exception:
            return default

    @staticmethod
    def nice_name(node, attr):
        try:
            return cmds.attributeQuery(attr, node=node, niceName=True)
        except Exception:
            return attr

    @staticmethod
    def enum_labels(node, attr):
        try:
            raw = cmds.attributeQuery(attr, node=node, listEnum=True) or []
            if not raw:
                return []

            result = []
            for value in raw[0].split(":"):
                label = value.split("=", 1)[0].strip()
                if any(c.isalnum() for c in label):
                    result.append(label)

            return result
        except Exception:
            return []

    @staticmethod
    def get_float(node, attr, default=0.0):
        try:
            return float(cmds.getAttr(Maya.plug(node, attr)))
        except Exception:
            return float(default)

    @staticmethod
    def numeric_range(node, attr, attr_type):
        if attr_type == "bool":
            return 0.0, 1.0

        try:
            if not cmds.attributeQuery(attr, node=node, minExists=True):
                return None
            if not cmds.attributeQuery(attr, node=node, maxExists=True):
                return None

            mn = cmds.attributeQuery(attr, node=node, minimum=True)[0]
            mx = cmds.attributeQuery(attr, node=node, maximum=True)[0]
            return float(mn), float(mx)
        except Exception:
            return None

    @staticmethod
    def keyed_values(node, attr, fallback=None):
        try:
            values = cmds.keyframe(Maya.plug(node, attr), query=True, valueChange=True) or []
            values = sorted(set(float(v) for v in values))
            if values:
                return values
        except Exception:
            pass

        if fallback is None:
            fallback = Maya.get_float(node, attr)

        return [float(fallback)]

    @staticmethod
    def key_times_for_plug(plug):
        try:
            return set(cmds.keyframe(plug, query=True, timeChange=True) or [])
        except Exception:
            return set()

    @staticmethod
    def key_times_for_node(node):
        try:
            return set(cmds.keyframe(node, query=True, timeChange=True) or [])
        except Exception:
            return set()

    @staticmethod
    def connected(node, attr):
        plug = Maya.plug(node, attr)
        try:
            if cmds.connectionInfo(plug, isDestination=True):
                return True
            if cmds.connectionInfo(plug, isSource=True):
                return True
            return bool(cmds.listConnections(plug, s=True, d=True, plugs=True) or [])
        except Exception:
            return False

    @staticmethod
    def selection(long=False):
        try:
            return cmds.ls(selection=True, long=long) or []
        except Exception:
            return []

    @staticmethod
    def matrix(node):
        return cmds.xform(node, q=True, ws=True, matrix=True)

    @staticmethod
    def set_matrix(node, matrix):
        cmds.xform(node, ws=True, matrix=matrix)


class UndoChunk(object):
    def __init__(self, name="SpaceSwitch"):
        self.name = name
        self.opened = False

    def __enter__(self):
        cmds.undoInfo(openChunk=True, chunkName=self.name)
        self.opened = True
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.opened:
            cmds.undoInfo(closeChunk=True)
        return False


class UndoDisabled(object):
    def __init__(self):
        self.previous_state = None

    def __enter__(self):
        try:
            self.previous_state = cmds.undoInfo(q=True, state=True)
            cmds.undoInfo(stateWithoutFlush=False)
        except Exception:
            self.previous_state = None
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.previous_state is not None:
            try:
                cmds.undoInfo(stateWithoutFlush=self.previous_state)
            except Exception:
                pass
        return False


class RefreshSuspended(object):
    def __enter__(self):
        try:
            cmds.refresh(suspend=True)
        except Exception:
            pass
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            cmds.refresh(suspend=False)
        except Exception:
            pass
        return False


class ProgressBar(object):
    def __init__(self, maximum, status="Working...", interruptable=True):
        self.maximum = maximum
        self.status = status
        self.interruptable = interruptable
        self.ctrl = None
        self.active = False

    def __enter__(self):
        try:
            if cmds.about(batch=True):
                return self
            self.ctrl = mel.eval("$tmp = $gMainProgressBar")
            cmds.progressBar(
                self.ctrl,
                e=True,
                bp=True,
                max=max(1, int(self.maximum)),
                ii=self.interruptable,
                status=self.status,
            )
            self.active = True
        except Exception:
            self.active = False
        return self

    def step(self, status=None):
        if not self.active:
            return False

        try:
            if cmds.progressBar(self.ctrl, q=True, ic=True):
                return True

            kwargs = {"edit": True, "step": 1}
            if status:
                kwargs["status"] = status

            cmds.progressBar(self.ctrl, **kwargs)
        except Exception:
            pass

        return False

    def __exit__(self, exc_type, exc, tb):
        if self.active:
            try:
                cmds.progressBar(self.ctrl, e=True, ep=True)
            except Exception:
                pass
        return False


class CallbackManager(object):
    def __init__(self):
        self.ids = []

    def add(self, cb_id):
        if cb_id is not None:
            self.ids.append(cb_id)

    def clear(self):
        for cb_id in self.ids:
            try:
                om.MMessage.removeCallback(cb_id)
            except Exception:
                pass
        self.ids[:] = []


class GimbalAnalyzer(object):
    ORDER_MAP = {
        "xyz": om.MEulerRotation.kXYZ,
        "yzx": om.MEulerRotation.kYZX,
        "zxy": om.MEulerRotation.kZXY,
        "xzy": om.MEulerRotation.kXZY,
        "yxz": om.MEulerRotation.kYXZ,
        "zyx": om.MEulerRotation.kZYX,
    }

    @staticmethod
    def radians_to_degrees(value):
        return value * (180.0 / math.pi)

    def convert_order_string(self, value):
        return self.ORDER_MAP.get(value, om.MEulerRotation.kZYX)

    @staticmethod
    def middle_axis_value(rotation):
        return {
            om.MEulerRotation.kZXY: rotation.x,
            om.MEulerRotation.kZYX: rotation.y,
            om.MEulerRotation.kXZY: rotation.z,
            om.MEulerRotation.kXYZ: rotation.y,
            om.MEulerRotation.kYZX: rotation.z,
            om.MEulerRotation.kYXZ: rotation.x,
        }[rotation.order]

    def gimbal_percentage(self, rotation):
        mid = self.radians_to_degrees(self.middle_axis_value(rotation))
        return int(abs(((mid + 90) % 180) - 90) / 90 * 100)

    def rotation_order_list(self, obj):
        try:
            if cmds.attributeQuery("rotateOrder", node=obj, exists=True):
                return cmds.attributeQuery("rotateOrder", node=obj, listEnum=True)[0].split(":")
        except Exception:
            pass
        return []

    def rotation_at_time(self, obj, time_value, order_list):
        rx = cmds.getAttr("%s.rotateX" % obj, time=time_value) or 0.0
        ry = cmds.getAttr("%s.rotateY" % obj, time=time_value) or 0.0
        rz = cmds.getAttr("%s.rotateZ" % obj, time=time_value) or 0.0
        idx = int(cmds.getAttr("%s.rotateOrder" % obj, time=time_value) or 0)
        idx = max(0, min(idx, len(order_list) - 1)) if order_list else 0
        order = order_list[idx] if order_list else "xyz"

        return om.MEulerRotation(
            math.radians(rx),
            math.radians(ry),
            math.radians(rz),
            self.convert_order_string(order),
        )

    def compute_all_percentages(self, obj, order_list):
        key_times = set()

        for attr in ("rotateX", "rotateY", "rotateZ"):
            try:
                key_times.update(cmds.keyframe(obj, attribute=attr, query=True, timeChange=True) or [])
            except Exception:
                pass

        if not key_times:
            key_times = {cmds.currentTime(query=True)}

        result = []

        for order_name in order_list:
            target_order = self.convert_order_string(order_name)
            worst = 0

            for time_value in sorted(key_times):
                rotation = self.rotation_at_time(obj, time_value, order_list)
                reordered = om.MEulerRotation(rotation.x, rotation.y, rotation.z, rotation.order)
                reordered.reorderIt(target_order)
                worst = max(worst, self.gimbal_percentage(reordered))

            result.append(worst)

        return result

    @staticmethod
    def classify(percentages):
        labels = [""] * len(percentages)

        if not percentages or len(set(percentages)) == 1:
            return labels

        best = min(percentages)

        for i, value in enumerate(percentages):
            diff = value - best

            if diff == 0:
                labels[i] = "Best"
            elif diff <= 2:
                labels[i] = "Good"
            elif diff <= 6:
                labels[i] = "OK"

        return labels

    def analyze(self, obj):
        order_list = self.rotation_order_list(obj)

        if not order_list:
            return {}

        try:
            percentages = self.compute_all_percentages(obj, order_list)
            labels = self.classify(percentages)
        except Exception:
            return {}

        return {
            order: {
                "percentage": percentages[i],
                "label": labels[i],
            }
            for i, order in enumerate(order_list)
        }


class SwitchOperation(object):
    def __init__(self, xform_target, attr_node, attr, value, label=None, source="local"):
        self.xform_target = xform_target
        self.attr_node = attr_node
        self.attr = attr
        self.value = value
        self.label = label if label is not None else value
        self.source = source

    @property
    def plug(self):
        return Maya.plug(self.attr_node, self.attr)

    def is_valid(self):
        return (
            Maya.exists(self.xform_target)
            and Maya.exists(self.attr_node)
            and cmds.objExists(self.plug)
        )

    def set_value(self, value):
        self.value = value
        return self


class SwitchEntry(object):
    def __init__(
        self,
        display_object,
        attr_node,
        attr,
        values,
        current,
        attr_type,
        min_value,
        max_value,
        xform_target=None,
        source="local",
        marked=None,
        gimbal=None,
        matched=None,
        match_roles=None,
    ):
        self.display_object = display_object
        self.attr_node = attr_node
        self.attr = attr
        self.values = values or []
        self.current = float(current)
        self.attr_type = attr_type
        self.min_value = float(min_value)
        self.max_value = float(max_value)
        self.xform_target = xform_target or display_object
        self.source = source
        self.marked = marked or [self.current]
        self.gimbal = gimbal or {}
        self.matched = matched or []
        self.match_roles = match_roles or []

    def to_dict(self):
        return {
            "enum": self.values,
            "marked": self.marked,
            "keyed_values": sorted(Maya.keyed_values(self.attr_node, self.attr)),
            "current": self.current,
            "attr": self.attr,
            "type": self.attr_type,
            "min": self.min_value,
            "max": self.max_value,
            "attr_node": self.attr_node,
            "xform_target": self.xform_target,
            "source": self.source,
            "gimbal": self.gimbal,
            "matched": self.matched,
            "matchedRole": self.match_roles,
        }


class SwitchCatalogBuilder(object):
    ROTATE_ORDER_OPTIONS = ["xyz", "yzx", "zxy", "xzy", "yxz", "zyx"]

    def __init__(self, analyzer, show_rotate_order=True):
        self.analyzer = analyzer
        self.show_rotate_order = show_rotate_order

    @staticmethod
    def add_entry(catalog, key, long_name, entry):
        if key not in catalog:
            catalog[key] = {
                "objects": {},
                "long": long_name or key,
            }

        catalog[key]["objects"][entry.display_object] = entry.to_dict()

    @staticmethod
    def merge_catalogs(primary, secondary):
        for key, data in secondary.items():
            if key not in primary:
                primary[key] = data
                continue

            primary[key].setdefault("objects", {})
            primary[key]["objects"].update(data.get("objects", {}))

            if not primary[key].get("long"):
                primary[key]["long"] = data.get("long", key)

        return primary

    @staticmethod
    def namespace_candidates(namespace):
        parts = namespace.strip(":").split(":")
        while parts:
            yield ":".join(parts)
            parts.pop()

    @staticmethod
    def relative_name(node, root_namespace):
        node = (node or "").strip(":")
        root_namespace = (root_namespace or "").strip(":")
        prefix = root_namespace + ":"

        if root_namespace and node.startswith(prefix):
            return node[len(prefix):]

        return node

    @staticmethod
    def full_name(root_namespace, node):
        node = (node or "").strip(":")
        root_namespace = (root_namespace or "").strip(":")

        if not node:
            return None

        candidates = []

        if root_namespace:
            candidates.append("%s:%s" % (root_namespace, node))

        candidates.append(node)

        for candidate in candidates:
            if Maya.exists(candidate):
                return candidate

        return candidates[0]

    def same_node(self, a, b, root_namespace):
        a = (a or "").strip(":")
        b = (b or "").strip(":")

        if not a or not b:
            return False

        if a == b:
            return True

        rel_a = self.relative_name(a, root_namespace)
        rel_b = self.relative_name(b, root_namespace)

        return rel_a == rel_b or a.endswith(":" + rel_b) or b.endswith(":" + rel_a)

    def find_space_control(self, node):
        namespace = Maya.reference_namespace(node)

        for ns in self.namespace_candidates(namespace):
            control = "%s:C_space_CTL" % ns
            if Maya.exists(control):
                return ns, control

        return None, None

    @staticmethod
    def parse_space_data(raw, source="spaceData"):
        if not raw:
            return {}

        try:
            data = ast.literal_eval(raw)
        except Exception as exc:
            cmds.warning("Could not parse {}: {}".format(source, exc))
            return {}

        if not isinstance(data, dict):
            cmds.warning("{} did not evaluate to a dictionary.".format(source))
            return {}

        return data

    @staticmethod
    def _downstream_nodes(source):
        """Return direct DG destinations for a node or plug."""
        try:
            return cmds.listConnections(
                source,
                source=False,
                destination=True,
                skipConversionNodes=True,
            ) or []
        except (TypeError, RuntimeError, ValueError):
            try:
                return cmds.listConnections(
                    source, source=False, destination=True
                ) or []
            except Exception:
                return []

    @staticmethod
    def _is_transform(node):
        try:
            return cmds.nodeType(node) in ("transform", "joint")
        except Exception:
            return False

    @classmethod
    def _controller_descendants(cls, root, max_depth=8):
        """Find the nearest curve controller below a driven transform."""
        queue = [(root, 0)]
        visited = set()
        matches = []
        nearest_depth = None
        while queue:
            node, depth = queue.pop(0)
            if node in visited or depth > max_depth:
                continue
            visited.add(node)
            try:
                shapes = cmds.listRelatives(
                    node,
                    shapes=True,
                    noIntermediate=True,
                    fullPath=True,
                ) or []
            except Exception:
                shapes = []
            if any(
                cmds.nodeType(shape) == "nurbsCurve"
                for shape in shapes
            ):
                if nearest_depth is None:
                    nearest_depth = depth
                if depth == nearest_depth:
                    matches.append(node)
                continue
            if nearest_depth is not None or depth == max_depth:
                continue
            try:
                children = cmds.listRelatives(
                    node, children=True, type="transform", fullPath=True
                ) or []
            except Exception:
                children = []
            queue.extend((child, depth + 1) for child in children)
        return matches

    @classmethod
    def detect_xform_target(cls, switch_node, attribute, max_nodes=256):
        """Infer the control whose world pose a switch should preserve.

        Space-switch attributes often live on a settings/spacer control while
        their DG output drives an offset group above the animated control. Walk
        only downstream from the switch plug, stop at driven transforms, and
        use a unique nearest curve-controller descendant. Ambiguous networks
        deliberately fall back to the attribute owner.
        """
        plug = "{}.{}".format(switch_node, attribute)
        queue = list(cls._downstream_nodes(plug))
        visited = set()
        driven = []
        while queue and len(visited) < max_nodes:
            node = queue.pop(0)
            if node in visited:
                continue
            visited.add(node)
            if cls._is_transform(node):
                driven.append(node)
                continue
            queue.extend(cls._downstream_nodes(node))

        candidates = []
        for transform in driven:
            controls = cls._controller_descendants(transform)
            candidates.extend(controls or [transform])
        candidates = list(dict.fromkeys(candidates))
        return candidates[0] if len(candidates) == 1 else switch_node

    def local_catalog(self, selection):
        catalog = {}

        for node in selection:
            if not Maya.exists(node):
                continue

            attrs = cmds.listAttr(node, ud=True) or []
            attrs = [
                attr for attr in attrs
                if not cmds.attributeQuery(attr, node=node, hidden=True)
            ]

            if self.show_rotate_order and Maya.attr_exists(node, "rotateOrder"):
                if "rotateOrder" not in attrs:
                    attrs.append("rotateOrder")

            for attr in attrs:
                attr_type = Maya.attr_type(node, attr)

                if not attr_type:
                    continue

                is_enum = attr_type == "enum"
                is_numeric = attr_type in ("bool", "long", "double", "float")

                if not is_enum and not is_numeric:
                    continue

                values = []
                min_value = 0.0
                max_value = 0.0

                if is_enum:
                    values = Maya.enum_labels(node, attr)

                    if len(set(values)) < 2:
                        continue

                    max_value = float(len(values) - 1)
                else:
                    attr_range = Maya.numeric_range(node, attr, attr_type)

                    if attr_range is None:
                        continue

                    min_value, max_value = attr_range

                if attr != "rotateOrder" and not Maya.connected(node, attr):
                    continue

                catalog_key = attr

                if is_enum and attr != "rotateOrder":
                    if [v.lower() for v in values] == [v.lower() for v in self.ROTATE_ORDER_OPTIONS]:
                        catalog_key = "rotateOrder"

                current = Maya.get_float(node, attr)
                gimbal = {}

                # Gimbal analysis is deferred until an option picker opens.

                xform_target = node if attr == "rotateOrder" else self.detect_xform_target(node, attr)
                entry = SwitchEntry(
                    display_object=xform_target,
                    attr_node=node,
                    attr=attr,
                    values=values,
                    current=current,
                    attr_type=attr_type,
                    min_value=min_value,
                    max_value=max_value,
                    xform_target=xform_target,
                    source="local",
                    marked=Maya.keyed_values(node, attr, current),
                    gimbal=gimbal,
                )

                self.add_entry(catalog, catalog_key, Maya.nice_name(node, attr), entry)

        return catalog

    def framestore_catalog(self, selection):
        catalog = {}

        for selected in selection:
            if not Maya.exists(selected):
                continue

            if not Maya.is_referenced(selected):
                continue

            root_namespace, space_control = self.find_space_control(selected)

            if not root_namespace or not space_control:
                continue

            space_data_plug = Maya.plug(space_control, "spaceData")

            if not cmds.objExists(space_data_plug):
                continue

            data = self.parse_space_data(
                cmds.getAttr(space_data_plug),
                source=space_data_plug,
            )

            if not data:
                continue

            self.collect_framestore_node(
                catalog=catalog,
                selected=selected,
                root_namespace=root_namespace,
                space_control=space_control,
                data=data,
            )

        return catalog

    def collect_framestore_node(self, catalog, selected, root_namespace, space_control, data):
        for attr_name, attr_data in data.items():
            spaces = attr_data.get("spaces") or {}

            if not spaces:
                continue

            if not Maya.attr_exists(space_control, attr_name):
                continue

            enum_values = list(spaces.keys())

            if len(enum_values) < 2:
                continue

            matches = self.framestore_matches(
                selected=selected,
                root_namespace=root_namespace,
                spaces=spaces,
            )

            if not matches:
                continue

            current = Maya.get_float(space_control, attr_name)
            long_name = Maya.nice_name(space_control, attr_name)

            for xform_target, match_data in matches.items():
                entry = SwitchEntry(
                    display_object=xform_target,
                    attr_node=space_control,
                    attr=attr_name,
                    values=enum_values,
                    current=current,
                    attr_type=Maya.attr_type(space_control, attr_name, "enum"),
                    min_value=0.0,
                    max_value=float(len(enum_values) - 1),
                    xform_target=xform_target,
                    source="framestore_spaceData",
                    marked=Maya.keyed_values(space_control, attr_name, current),
                    matched=sorted(match_data["spaces"]),
                    match_roles=sorted(match_data["roles"]),
                )

                self.add_entry(catalog, attr_name, long_name, entry)

    def framestore_matches(self, selected, root_namespace, spaces):
        matches = {}

        for space_name, info in spaces.items():
            getters = info.get("get") or []
            setters = info.get("set") or []
            match_types = info.get("matchType") or []
            count = max(len(getters), len(setters), len(match_types))

            for i in range(count):
                getter = getters[i] if i < len(getters) else None
                setter = setters[i] if i < len(setters) else None
                match_type = match_types[i] if i < len(match_types) else "parent"

                getter_full = self.full_name(root_namespace, getter) if getter else None
                setter_full = self.full_name(root_namespace, setter) if setter else None

                selected_is_setter = self.same_node(selected, setter_full, root_namespace)
                selected_is_getter = self.same_node(selected, getter_full, root_namespace)

                if not selected_is_setter and not selected_is_getter:
                    continue

                if selected_is_setter:
                    xform_target = setter_full
                    role = "setter"
                else:
                    xform_target = setter_full or selected
                    role = "getter"

                if not xform_target:
                    continue

                item = matches.setdefault(
                    xform_target,
                    {
                        "spaces": set(),
                        "roles": set(),
                        "matchTypes": set(),
                    },
                )

                item["spaces"].add(space_name)
                item["roles"].add(role)
                item["matchTypes"].add(match_type)

        return matches

    def combined_catalog(self, selection):
        local = self.local_catalog(selection)
        framestore = self.framestore_catalog(selection)

        if not framestore:
            return local

        result = framestore

        if "rotateOrder" in local:
            self.merge_catalogs(result, {"rotateOrder": local["rotateOrder"]})

        for key, data in local.items():
            if key == "rotateOrder":
                continue

            if key not in result:
                result[key] = data

        return result


class Grip(QSizeGrip):
    def __init__(self, parent):
        QSizeGrip.__init__(self, parent)
        self._parent_widget = parent
        self._start_geom = None

    def mousePressEvent(self, event):
        self._start_geom = self._parent_widget.geometry()
        self._parent_widget._suspend_auto_close()
        QSizeGrip.mousePressEvent(self, event)

    def mouseReleaseEvent(self, event):
        QSizeGrip.mouseReleaseEvent(self, event)

        if self._start_geom and self._parent_widget.geometry() != self._start_geom:
            self._parent_widget.showBottomBar()

        self._start_geom = None


class FloatingWidget(base_widgets.QFlatDialog):
    BORDER_RADIUS = util.DPI(5)
    AUTO_CLOSE_DIST = util.DPI(10)
    AUTO_CLOSE_GRACE_MS = 400
    TEXT_COLOR = COLOR_TEXT_SECONDARY

    def __init__(self, popup=False, parent=None):
        base_widgets.QFlatDialog.__init__(self, parent)

        self.setWindowFlags(self.windowFlags() | Qt.Tool | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose, False)

        self._is_dragging = False
        self._drag_offset = QPoint()
        self._drag_start_pos = QPoint()
        self._auto_close_active = True if popup else None

        self._auto_close_timer = QTimer(self)
        self._auto_close_armed = False
        self._auto_close_origin = None
        self._shown_elapsed = QtCore.QElapsedTimer()
        self._auto_close_timer.setInterval(200)
        self._auto_close_timer.timeout.connect(self._process_auto_close_request)

        self._setup_ui()
        self.setMouseTracking(True)

    def _setup_ui(self):
        self.mainContent = QWidget(self)
        self.mainLayout = QVBoxLayout(self.mainContent)
        self.mainLayout.setContentsMargins(util.DPI(6), util.DPI(8), util.DPI(6), util.DPI(8))
        self.mainLayout.setSpacing(2)

        self.root_layout.insertWidget(0, self.mainContent, 1)

        self.grip = Grip(self)
        self.grip.setCursor(Qt.SizeBDiagCursor)

    def setBottomBar(self, *args, **kwargs):
        if self.bottomBar:
            self.bottomBar.setParent(None)
            self.bottomBar.deleteLater()
            self.bottomBar = None

        kwargs.setdefault("margins", 0)
        base_widgets.QFlatDialog.setBottomBar(self, *args, **kwargs)

    def showBottomBar(self):
        self._disable_auto_close()

        if hasattr(self, "_refresh_footer"):
            self._refresh_footer()
        elif not self.bottomBar:
            self.setBottomBar(closeButton=True)

    def place_near_cursor(self):
        self.resize(self.sizeHint())

        cursor_pos = QCursor.pos()
        screen = QGuiApplication.screenAt(cursor_pos) or QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()

        x = max(geo.left(), min(cursor_pos.x(), geo.right() - self.width()))
        y = max(geo.top(), min(cursor_pos.y() - self.height() // 2, geo.bottom() - self.height()))

        self.move(x, y)

    def _is_cursor_within_bounds(self):
        """Geometric intersection check for the main widget and its active sub-popups."""
        cursor_pos = QtGui.QCursor.pos()
        if not util.is_valid_widget(self):
            return False

        if self.frameGeometry().contains(cursor_pos):
            return True

        if (
            hasattr(self, "_active_popup")
            and self._active_popup
            and util.is_valid_widget(self._active_popup)
            and self._active_popup.isVisible()
        ):
            if self._active_popup.frameGeometry().contains(cursor_pos):
                return True
        if (
            hasattr(self, "_multi_switch_dialog")
            and self._multi_switch_dialog
            and util.is_valid_widget(self._multi_switch_dialog)
            and self._multi_switch_dialog.isVisible()
        ):
            if self._multi_switch_dialog.frameGeometry().contains(cursor_pos):
                return True
        return False

    def _process_auto_close_request(self):
        """Evaluates whether the window should close based on current cursor position."""
        if not self._auto_close_active or not self.isVisible():
            self._auto_close_timer.stop()
            return

        if not self._shown_elapsed.isValid():
            return
        remaining_grace = self.AUTO_CLOSE_GRACE_MS - self._shown_elapsed.elapsed()
        if remaining_grace > 0:
            return

        cursor_pos = QtGui.QCursor.pos()
        if self._is_cursor_within_bounds():
            self._auto_close_armed = True
            return

        bounds = self.frameGeometry()
        cursor_distance = self._distance_from_rect(cursor_pos, bounds)
        allowed_distance = self.AUTO_CLOSE_DIST
        if not self._auto_close_armed and self._auto_close_origin is not None:
            # Toolbar popups intentionally open offset from the click. Use that
            # stable launch distance as the pre-interaction baseline, so an
            # untouched popup stays open while movement farther away closes it.
            allowed_distance += self._distance_from_rect(
                self._auto_close_origin, bounds
            )

        if cursor_distance > allowed_distance:
            self.close()

    def _resume_auto_close(self):
        """Resume distance monitoring after a temporary interaction pause."""
        if self._auto_close_active is False:
            self._auto_close_active = True
        self._ensure_auto_close_monitor()

    def _suspend_auto_close(self):
        if self._auto_close_active is True:
            self._auto_close_active = False

        if self._auto_close_timer:
            self._auto_close_timer.stop()

    def _disable_auto_close(self):
        """Permanently stops the auto-close mechanism for the lifetime of the widget."""
        if hasattr(self, "_auto_close_timer") and self._auto_close_timer:
            self._auto_close_timer.stop()
        self._auto_close_active = None
        self._auto_close_armed = False
        self._auto_close_origin = None

    def enterEvent(self, event):
        if self._auto_close_active is True and self._is_cursor_within_bounds():
            self._auto_close_armed = True
        self._ensure_auto_close_monitor()
        base_widgets.QFlatDialog.enterEvent(self, event)

    def leaveEvent(self, event):
        self._ensure_auto_close_monitor()
        base_widgets.QFlatDialog.leaveEvent(self, event)

    def resizeEvent(self, event):
        size = self.grip.sizeHint()
        self.grip.setFixedSize(size)
        self.grip.move(self.width() - size.width(), 0)
        self.grip.raise_()
        base_widgets.QFlatDialog.resizeEvent(self, event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            pos = Qtx.global_pos(event)
            self._is_dragging = True
            self._drag_start_pos = pos
            self._drag_offset = pos - self.frameGeometry().topLeft()
            self._suspend_auto_close()

        base_widgets.QFlatDialog.mousePressEvent(self, event)

    def mouseMoveEvent(self, event):
        if self._is_dragging and event.buttons() & Qt.LeftButton:
            self.move(Qtx.global_pos(event) - self._drag_offset)

        base_widgets.QFlatDialog.mouseMoveEvent(self, event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._is_dragging:
            self._is_dragging = False
            distance = (Qtx.global_pos(event) - self._drag_start_pos).manhattanLength()

            if distance > util.DPI(10):
                self.showBottomBar()
            elif self._auto_close_active is False:
                self._auto_close_active = True
                self._resume_auto_close()

        base_widgets.QFlatDialog.mouseReleaseEvent(self, event)

    def paintEvent(self, event):
        if not self.isVisible():
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(COLOR_BG_TRACK))
        painter.drawRoundedRect(self.rect(), self.BORDER_RADIUS, self.BORDER_RADIUS)

    def closeEvent(self, event):
        self._disable_auto_close()
        base_widgets.QFlatDialog.closeEvent(self, event)
    def showEvent(self, event):
        # Restart the grace window every time the popup (re)appears, not just
        # on first construction -- a reused/hidden-then-reshown widget can hit
        # the same stale-geometry window.
        self._auto_close_timer.stop()
        self._auto_close_armed = False
        self._auto_close_origin = QtGui.QCursor.pos()
        self._shown_elapsed.start()
        base_widgets.QFlatDialog.showEvent(self, event)
        self._ensure_auto_close_monitor()

    def _ensure_auto_close_monitor(self):
        """Poll global cursor distance while a transient popup is visible.

        A top-level Qt tool window does not reliably receive mouse-move or
        leave events after the pointer crosses into Maya or another native
        window. Polling ``QCursor.pos()`` keeps distance-based closing
        independent of application focus and event delivery.
        """
        if (
            self._auto_close_active is True
            and self.isVisible()
            and not self._auto_close_timer.isActive()
        ):
            self._auto_close_timer.start()

    @staticmethod
    def _distance_from_rect(point, rect):
        """Return the shortest screen-space distance from a point to a rectangle."""
        dx = max(rect.left() - point.x(), 0, point.x() - rect.right())
        dy = max(rect.top() - point.y(), 0, point.y() - rect.bottom())
        return (dx * dx + dy * dy) ** 0.5


class PillSlider(QWidget):
    HEIGHT = util.DPI(32)
    HANDLE_RADIUS = util.DPI(13)
    SNAP_POINTS = [0.0, 0.5, 1.0]
    SNAP_THRESHOLD = 0.06

    def __init__(self, value, min_value, max_value, callback, parent=None):
        QWidget.__init__(self, parent)

        self.setFixedSize(util.DPI(140), self.HEIGHT)
        self.value = float(value)
        self.min_value = float(min_value)
        self.max_value = float(max_value)
        self.callback = callback
        self._dragging = False
        self._original_value = self.value

        self.setCursor(Qt.PointingHandCursor)

    def _value_to_x(self, value):
        offset = self.height() / 2.0

        if self.max_value <= self.min_value:
            return self.width() // 2

        inner = self.width() - (2 * offset)
        ratio = (value - self.min_value) / (self.max_value - self.min_value)
        return int(offset + ratio * inner)

    def _x_to_value(self, x):
        offset = self.height() / 2.0
        inner = self.width() - (2 * offset)

        if inner <= 0:
            return self.min_value

        ratio = (x - offset) / float(inner)
        ratio = max(0.0, min(1.0, ratio))

        for snap in self.SNAP_POINTS:
            if abs(ratio - snap) < self.SNAP_THRESHOLD:
                ratio = snap
                break

        return self.min_value + ratio * (self.max_value - self.min_value)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect().adjusted(1, 1, -1, -1)
        radius = rect.height() / 2

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(COLOR_ACCENT_DARK))
        painter.drawRoundedRect(rect, radius, radius)

        center_y = self.height() / 2
        handle_radius = self.HANDLE_RADIUS

        if self._dragging:
            shadow_x = self._value_to_x(self._original_value)
            painter.setBrush(QColor(COLOR_BLEND_MULTI))
            painter.drawEllipse(QPoint(shadow_x, int(center_y)), handle_radius, handle_radius)

        handle_x = self._value_to_x(self.value)
        painter.setBrush(QColor(COLOR_BG_TRACK))
        painter.drawEllipse(QPoint(handle_x, int(center_y)), handle_radius, handle_radius)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._original_value = self.value
            self.value = self._x_to_value(Qtx.local_x(event))
            self.update()

    def mouseMoveEvent(self, event):
        if self._dragging:
            self.value = self._x_to_value(Qtx.local_x(event))
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = False
            self.callback(self.value)




def _t(text):
    return text

ATTRIBUTE_SWITCHER_GLOBE_IMAGE = util.return_icon_path("globe.svg")

def _option_button_stylesheet(compact=False):
    """Return the shared enum-option style used by both switch popups."""
    if compact:
        return (
            "QPushButton { color: %s; background: %s; text-align: left; "
            "padding: %spx; border-radius: %spx; border: none; }"
            "QPushButton:hover { background: %s; }"
            "QPushButton:checked { color: %s; background: %s; font-weight: bold; }"
            % (
                COLOR_ACCENT_HOVER,
                COLOR_ACCENT_DARK,
                util.DPI(7),
                util.DPI(6),
                COLOR_ACCENT_MAIN,
                COLOR_BG_MAIN,
                COLOR_ACCENT_LIGHT,
            )
        )
    return (
        "QPushButton { color: %s; background: %s; text-align: left; "
        "padding: %spx %spx %spx %spx; border-radius: %spx; "
        "font-size: %spx; font-weight: bold; border: none; }"
        "QPushButton:hover, QPushButton:pressed { color: %s; background: %s; }"
        "QPushButton:checked { color: %s; background: %s; }"
        % (
            COLOR_ACCENT_HOVER,
            COLOR_ACCENT_DARK,
            util.DPI(8),
            util.DPI(18),
            util.DPI(8),
            util.DPI(8),
            util.DPI(6),
            util.DPI(11),
            COLOR_ACCENT_DARK,
            COLOR_ACCENT_MAIN,
            COLOR_BG_MAIN,
            COLOR_ACCENT_LIGHT,
        )
    )

def _configure_option_button(button, compact=False):
    """Apply the common interaction and appearance for enum options."""
    button.setFlat(True)
    button.setCursor(QtCore.Qt.PointingHandCursor)
    button.setStyleSheet(_option_button_stylesheet(compact=compact))

def _add_option_state_indicator(button, is_current=False, is_keyed=False):
    """Add the standard current/keyed dot used by attribute options."""
    dot_layout = QtWidgets.QHBoxLayout(button)
    dot_layout.setContentsMargins(0, 0, util.DPI(6), 0)
    dot_layout.addStretch(1)

    dot = QtWidgets.QWidget(button)
    dot.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
    dot_size = util.DPI(10)
    dot.setFixedSize(dot_size, dot_size)
    if is_current:
        color = COLOR_BG_TRACK
    elif is_keyed:
        color = COLOR_BLEND_MULTI
    else:
        color = "transparent"
    dot.setStyleSheet(
        "background: {}; border-radius: {}px;".format(color, dot_size // 2)
    )
    dot_layout.addWidget(dot)

def _rotation_order_option_text(option, gimbal_info):
    """Render the shared GimbalAnalyzer result in every option picker."""
    info = (gimbal_info or {}).get(option, {})
    label = str(info.get("label", "")).strip()
    return "{} ({})".format(option, label) if label else option

def _connect_checkable_button(button, callback, *callback_args):
    """Connect checked buttons across Qt bindings that omit clicked(bool)."""
    def _dispatch(*_signal_args):
        callback(button.isChecked(), *callback_args)

    button.clicked.connect(_dispatch)

def _multi_select_modifier_held():
    """Query Ctrl/Cmd directly instead of relying on Maya key delivery."""
    query_modifiers = getattr(
        QtGui.QGuiApplication, "queryKeyboardModifiers", None
    )
    if callable(query_modifiers):
        modifiers = query_modifiers()
    else:
        modifiers = QtWidgets.QApplication.keyboardModifiers()
    return bool(
        modifiers & (QtCore.Qt.ControlModifier | QtCore.Qt.MetaModifier)
    )

def _populate_attribute_entry_state(entry, objects_map):
    """Populate the shared option/current/key state used by both row types."""
    entry.objects_map = objects_map
    any_obj = next(iter(objects_map.values()))
    entry.is_enum = any_obj.get("type") == "enum"
    entry.min_val = any_obj.get("min", 0)
    entry.max_val = any_obj.get("max", 1)
    entry.options = any_obj.get("enum", [])
    entry.current_indices = {
        obj.get("current") for obj in objects_map.values()
    }
    entry.marked_indices = {
        index
        for obj in objects_map.values()
        for index in obj.get("marked", [])
    }
    keyed_values = {
        index
        for obj in objects_map.values()
        for index in obj.get("keyed_values", [])
    }
    entry.has_mixed_key_values = entry.is_enum and len(keyed_values) > 1
    entry.indices = entry.current_indices | entry.marked_indices
    entry.current_idx = any_obj.get("current", 0)
    entry.gimbal_info = any_obj.get("gimbal", {})

class _StagedAttributeEntry:
    """Non-visual per-target view of a collapsed AttributeItem."""

    def __init__(self, source_item, target, object_data):
        self.enum_attr = source_item.enum_attr
        self.object_label = source_item.parent_dialog._format_object_name(
            [target]
        )
        self.attribute_label = source_item.attribute_label
        _populate_attribute_entry_state(self, {target: object_data})

class _PopupOptionButton(QtWidgets.QPushButton):
    """Option button supporting menu-style press, drag, and release."""

    def __init__(self, text, popup, index, all_frames):
        QtWidgets.QPushButton.__init__(self, text, popup.main_frame)
        self.popup = popup
        self.option_index = index
        self.all_frames = all_frames

    @staticmethod
    def _global_pos(event):
        return Qtx.global_pos(event)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.grabMouse()
            self.popup._begin_option_drag(self)
            event.accept()
            return
        QtWidgets.QPushButton.mousePressEvent(self, event)

    def mouseMoveEvent(self, event):
        if self.popup._drag_active:
            self.popup._update_option_drag(self._global_pos(event))
            event.accept()
            return
        QtWidgets.QPushButton.mouseMoveEvent(self, event)

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton and self.popup._drag_active:
            global_pos = self._global_pos(event)
            try:
                self.releaseMouse()
            except RuntimeError:
                pass
            self.popup._finish_option_drag(global_pos)
            event.accept()
            return
        QtWidgets.QPushButton.mouseReleaseEvent(self, event)

class AttributePopup(QtWidgets.QWidget):
    """
    A floating popup that lists attribute options with a dot for the selected one.
    """

    ALL_KEYFRAMES = "All Keyframes"
    CURRENT_KEYFRAMES = "Current Keyframes"

    def __init__(self, item_widget, on_select):
        QtWidgets.QWidget.__init__(self, item_widget.window())
        self.setWindowFlags(QtCore.Qt.ToolTip | QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)

        self.item_widget = item_widget
        self.options = item_widget.options
        self.current_idx = item_widget.current_idx
        self.indices = item_widget.indices
        self.current_indices = item_widget.current_indices
        self.marked_indices = item_widget.marked_indices
        self.on_select = on_select
        self._option_buttons = []
        self._drag_active = False

        any_obj = next(iter(item_widget.objects_map.values()))
        self.is_enum = any_obj.get("type") == "enum"
        self.min_val = any_obj.get("min", 0)
        self.max_val = any_obj.get("max", 1)

        self._setup_ui()

    def _setup_ui(self):
        """Main entry point for UI construction."""
        self.main_frame = QtWidgets.QFrame(self)
        self.main_frame.setObjectName("PopupFrame")
        self.main_frame.setStyleSheet(
            """
            QFrame#PopupFrame {{
                background-color: {};
                border-radius: {}px;
            }}
        """.format(COLOR_BG_POPUP, util.DPI(8))
        )

        self.content_layout = QtWidgets.QVBoxLayout(self.main_frame)
        self.content_layout.setContentsMargins(util.DPI(20), util.DPI(10), util.DPI(18), util.DPI(16))
        self.content_layout.setSpacing(util.DPI(1))

        if self.is_enum:
            self._build_enum_ui()
        else:
            self._build_numeric_ui()

        # Finalize structure and size
        self.adjustSize()
        self.outer_layout = QtWidgets.QVBoxLayout(self)
        self.outer_layout.setContentsMargins(util.DPI(10), 0, 0, 0)
        self.outer_layout.addWidget(self.main_frame)

    def _build_enum_ui(self):
        """Builds sections for enum discrete options."""
        is_ro = self.item_widget.enum_attr == "rotateOrder"

        if is_ro:
            self._add_category(self.ALL_KEYFRAMES, is_all=True, is_rr=True)
        else:
            self._add_category(self.CURRENT_KEYFRAMES, is_all=False)
            self._add_separator()
            self._add_category(self.ALL_KEYFRAMES, is_all=True)

    def _build_numeric_ui(self):
        """Builds sections for continuous numeric sliders."""
        self._add_slider_section(self.CURRENT_KEYFRAMES, is_all=False)
        self._add_separator()
        self._add_slider_section(self.ALL_KEYFRAMES, is_all=True)

    def _add_category(self, title_text, is_all, is_rr=False):
        """Creates a section with a title and a list of option buttons."""
        self.content_layout.addWidget(self._create_title(title_text))

        for i, opt in enumerate(self.options):
            display_text = (
                _rotation_order_option_text(
                    opt, self.item_widget.gimbal_info
                )
                if is_rr else opt
            )

            btn = self._create_option_button(display_text, i, is_all)
            self.content_layout.addWidget(btn)

            # Extra visual grouping for rotation orders (3+3)
            if is_rr and i == 2:
                self.content_layout.addSpacing(util.DPI(5))

    def _create_title(self, text):
        title = QtWidgets.QLabel(text)
        title.setContentsMargins(0, 0, 0, util.DPI(4))
        title.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        title.setStyleSheet("color: {}; font-size: {}px;".format(COLOR_TEXT_SECONDARY, util.DPI(11)))
        return title

    def _add_separator(self):
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.HLine)
        line.setFixedHeight(1)
        line.setStyleSheet("background-color: {};".format(COLOR_BG_TRACK))
        self.content_layout.addSpacing(util.DPI(10))
        self.content_layout.addWidget(line)
        self.content_layout.addSpacing(util.DPI(10))

    def _add_slider_section(self, title_text, is_all):
        """Creates a section with a title and a PillSlider."""
        self.content_layout.addWidget(self._create_title(title_text))

        slider = PillSlider(
            self.current_idx, self.min_val, self.max_val, lambda v, m=is_all: self.select_option(v, all_frames=m), parent=self.main_frame
        )
        self.content_layout.addWidget(slider)

    def _create_option_button(self, text, index, is_all):
        btn = _PopupOptionButton(text, self, index, is_all)
        _configure_option_button(btn)
        btn.setMinimumWidth(util.DPI(60))
        btn.setSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Fixed)
        _add_option_state_indicator(
            btn,
            is_current=index in self.current_indices,
            is_keyed=index in self.marked_indices,
        )
        self._option_buttons.append(btn)
        return btn

    def _button_at_global_pos(self, global_pos):
        for button in self._option_buttons:
            if not util.is_valid_widget(button) or not button.isVisible():
                continue
            local_pos = button.mapFromGlobal(global_pos)
            if button.rect().contains(local_pos):
                return button
        return None

    def _set_drag_hover_button(self, button):
        for option_button in self._option_buttons:
            if util.is_valid_widget(option_button):
                option_button.setDown(option_button is button)

    def _begin_option_drag(self, button):
        self._drag_active = True
        self._set_drag_hover_button(button)
        self.item_widget._set_popup_active(True)

    def _update_option_drag(self, global_pos):
        self._set_drag_hover_button(self._button_at_global_pos(global_pos))

    def _finish_option_drag(self, global_pos):
        button = self._button_at_global_pos(global_pos)
        self._drag_active = False
        self._set_drag_hover_button(None)
        if button is not None:
            self.select_option(
                button.option_index, all_frames=button.all_frames
            )

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(QtGui.QColor(COLOR_BG_POPUP))

        arrow_w = util.DPI(10)
        arrow_h = util.DPI(15)

        side = getattr(self, "side", "right")
        arrow_y = getattr(self, "arrow_y", self.height() / 2)

        if side == "right":
            # Pointing left, attached to the left side of the frame
            poly = QtGui.QPolygonF(
                [
                    QtCore.QPointF(0, arrow_y),
                    QtCore.QPointF(arrow_w + 1, arrow_y - arrow_h / 2),
                    QtCore.QPointF(arrow_w + 1, arrow_y + arrow_h / 2),
                ]
            )
        else:
            # Pointing right, attached to the right side of the frame
            w = self.width()
            poly = QtGui.QPolygonF(
                [
                    QtCore.QPointF(w, arrow_y),
                    QtCore.QPointF(w - arrow_w - 1, arrow_y - arrow_h / 2),
                    QtCore.QPointF(w - arrow_w - 1, arrow_y + arrow_h / 2),
                ]
            )
        painter.drawPolygon(poly)

    def select_option(self, idx, all_frames=None):
        # Tear ourselves down before calling out to on_select(), not after:
        # on_select() applies the switch, which refreshes the parent
        # dialog's widget list -- and that refresh would otherwise tear
        # this same popup down as a side effect (_close_active_popup(),
        # since this *is* the active popup) while we're still in the
        # middle of handling the click that opened it. closeEvent() below
        # clears the parent's _active_popup handle immediately, so that
        # later _close_active_popup() call just no-ops instead of racing
        # us to close/delete the same widget from two places.
        self.close()
        self.deleteLater()
        self.on_select(idx, all_frames=all_frames)

    def enterEvent(self, event):
        # Notify parent for unified interaction state
        p = self.parent()
        if p and hasattr(p, "_update_interaction_state"):
            p._update_interaction_state(True)
        QtWidgets.QWidget.enterEvent(self, event)

    def leaveEvent(self, event):
        p = self.parent()
        if p and hasattr(p, "_update_interaction_state"):
            # Delay to check if focus moved back to main area
            QtCore.QTimer.singleShot(150, lambda: p._update_interaction_state(False))
        QtWidgets.QWidget.leaveEvent(self, event)

    def closeEvent(self, event):
        self._drag_active = False
        self._set_drag_hover_button(None)
        mouse_grabber = QtWidgets.QWidget.mouseGrabber()
        if mouse_grabber in self._option_buttons:
            try:
                mouse_grabber.releaseMouse()
            except RuntimeError:
                pass
        if util.is_valid_widget(self.item_widget):
            self.item_widget._set_popup_active(False)
        p = self.parent()
        if p:
            # Re-evaluate parent's close conditions
            if hasattr(p, "_active_popup") and p._active_popup == self:
                p._active_popup = None
            if hasattr(p, "_resume_auto_close"):
                p._resume_auto_close()
        QtWidgets.QWidget.closeEvent(self, event)

    def show_beside(self, widget):
        self.adjustSize()
        w, h = self.width(), self.height()

        # Global center Y of the source widget
        target_y_global = widget.mapToGlobal(QtCore.QPoint(0, widget.height() // 2)).y()

        # Default: show on the right
        pos = widget.mapToGlobal(QtCore.QPoint(widget.width(), 0))

        screen = QtGui.QGuiApplication.screenAt(pos) or QtGui.QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()

        self.side = "right"
        # If it overflows on the right, flip to left
        if pos.x() + w > geo.right():
            self.side = "left"
            pos.setX(widget.mapToGlobal(QtCore.QPoint(0, 0)).x() - w)

        # Vertical positioning: center it relative to widget
        y = target_y_global - h // 2

        # Ensure it doesn't go off screen vertically
        if y + h > geo.bottom():
            y = geo.bottom() - h - util.DPI(5)
        if y < geo.top():
            y = geo.top() + util.DPI(5)

        pos.setY(y)
        # Store local y for the arrow tip to keep pointing at the target
        self.arrow_y = target_y_global - y

        # Update margins based on which side the arrow is on
        arrow_w = util.DPI(10)
        if self.side == "right":
            self.outer_layout.setContentsMargins(arrow_w, 0, 0, 0)
        else:
            self.outer_layout.setContentsMargins(0, 0, arrow_w, 0)

        self.move(pos)
        self.show()


class AttributeItem(QtWidgets.QWidget):
    """
    A row item that shows an attribute name and a pill with the current value.
    """

    def __init__(
        self,
        object_label,
        attribute_label,
        enum_attr,
        unique_controls,
        objects_map,
        parent_dialog,
    ):
        QtWidgets.QWidget.__init__(self, parent_dialog.mainContent)
        self.object_label = object_label
        self.attribute_label = attribute_label
        self.label_text = "{} {}".format(object_label, attribute_label)
        self.enum_attr = enum_attr
        self.unique_controls = unique_controls
        self.parent_dialog = parent_dialog

        _populate_attribute_entry_state(self, objects_map)

        self.is_toggle = self.is_enum and len(self.options) <= 2
        self._hover_active = False
        self._popup_active = False
        self.setMouseTracking(True)
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
        self._setup_ui()

    def _setup_ui(self):
        self.main_layout = QtWidgets.QHBoxLayout(self)
        self.main_layout.setContentsMargins(util.DPI(6), util.DPI(6), util.DPI(6), util.DPI(6))
        self.main_layout.setSpacing(util.DPI(6))

        self.multi_checkbox = QtWidgets.QCheckBox(self)
        self.multi_checkbox.setObjectName("HotkeyCommandCheckBox")
        self.multi_checkbox.setVisible(False)
        self.multi_checkbox.setToolTip(_t("Select this channel for a staged multi-switch"))
        self.multi_checkbox.setCursor(QtCore.Qt.PointingHandCursor)
        self.multi_checkbox.setSizePolicy(
            QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed
        )
        self.multi_checkbox.setFocusPolicy(QtCore.Qt.NoFocus)
        self.multi_checkbox.setStyleSheet(
            "#HotkeyCommandCheckBox{background:transparent;spacing:0px;}"
            "#HotkeyCommandCheckBox::indicator{width:%spx;height:%spx;border:1px solid #626262;border-radius:%spx;background:#262626;}"
            "#HotkeyCommandCheckBox::indicator:hover{border-color:#7d7d7d;background:#303030;}"
            "#HotkeyCommandCheckBox::indicator:checked{image:url(%s);border-color:#7d7d7d;background:#363636;}"
            % (util.DPI(11), util.DPI(11), util.DPI(3), util.return_icon_path("apply"))
        )
        self.multi_checkbox.toggled.connect(self._on_multi_checked)

        display_label = self.label_text
        if self.has_mixed_key_values:
            display_label += " *"
        self.name_label = QtWidgets.QLabel(display_label, self)
        self.name_label.setStyleSheet("color: {}; font-size: {}px;".format(COLOR_TEXT_MAIN, util.DPI(11)))
        self.name_label.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        self.name_label.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)

        self.pill_container = QtWidgets.QWidget(self)
        self.pill_container.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        self.pill_container.setFixedSize(util.DPI(60), util.DPI(16))
        self.pill_layout = QtWidgets.QHBoxLayout(self.pill_container)
        self.pill_layout.setContentsMargins(util.DPI(2), 0, util.DPI(2), 0)
        self.pill_layout.setSpacing(util.DPI(2))

        # Indicator 'Ball' style
        self.sq_btn = QtWidgets.QPushButton(self.pill_container)
        self.sq_btn.setFixedSize(util.DPI(12), util.DPI(12))
        self.sq_btn.setFocusPolicy(QtCore.Qt.NoFocus)
        self.sq_btn.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)

        self.val_label = QtWidgets.QLabel(
            self.options[max(0, min(int(self.current_idx), len(self.options) - 1))] if self.is_enum and self.options else "{:.2f}".format(self.current_idx), self.pill_container
        )
        self.val_label.setStyleSheet("color: {}; font-size: {}px;".format(COLOR_ACCENT_LIGHT, util.DPI(11)))
        self.val_label.setAlignment(QtCore.Qt.AlignCenter)

        # Toggles hide text until hover; Enums show text always; Numeric hide always
        self.val_label.setVisible(self.is_enum and not self.is_toggle)

        if self.is_enum:
            if self.is_toggle or self.enum_attr == "rotateOrder":
                self.pill_layout.addWidget(self.sq_btn)
                self.sq_btn.show()
            else:
                self.sq_btn.hide()
            self.pill_layout.addStretch()
            self.pill_layout.addWidget(self.val_label)
            self.pill_layout.addStretch()
        else:
            self.pill_layout.removeWidget(self.sq_btn)
            self.pill_layout.setContentsMargins(util.DPI(2), 0, util.DPI(2), 0)
            self.pill_layout.addWidget(self.val_label)
            self.sq_btn.setParent(self.pill_container)
            QtCore.QTimer.singleShot(0, self._update_numeric_ball_pos)

        self._refresh_pill_style()

        self.main_layout.addWidget(self.multi_checkbox, 0, QtCore.Qt.AlignVCenter)
        self.main_layout.addWidget(self.name_label, 1)
        self.main_layout.addWidget(self.pill_container)

        # Keep layout space but make transparent
        self.pill_opacity = QtWidgets.QGraphicsOpacityEffect(self.pill_container)
        self.pill_container.setGraphicsEffect(self.pill_opacity)
        self.pill_opacity.setOpacity(0.0)

    def _set_popup_active(self, active):
        self._popup_active = bool(active)
        self._hover_active = self._popup_active or self.underMouse()
        self.update()

    def _on_multi_checked(self, checked):
        self._update_multi_checkbox_visibility()
        self.update()
        handler = getattr(
            self.parent_dialog, "_on_attribute_multi_checked", None
        )
        if callable(handler):
            handler(self, checked)

    @staticmethod
    def _multi_select_modifier_held():
        return _multi_select_modifier_held()

    def _update_multi_checkbox_visibility(self):
        if not self.is_enum:
            self.multi_checkbox.hide()
            return
        cursor_inside = self.rect().contains(
            self.mapFromGlobal(QtGui.QCursor.pos())
        )
        should_show = self.multi_checkbox.isChecked() or (
            cursor_inside and self._multi_select_modifier_held()
        )
        self.multi_checkbox.setVisible(should_show)

    def _update_numeric_ball_pos(self):
        if self.is_enum:
            return
        w = self.pill_container.width()
        ball_w = self.sq_btn.width()
        padding = util.DPI(2)  # Match enum layout margins
        usable_w = w - ball_w - (padding * 2)

        if self.max_val <= self.min_val:
            x = padding + (usable_w // 2)
        else:
            ratio = (self.current_idx - self.min_val) / (self.max_val - self.min_val)
            ratio = max(0.0, min(1.0, ratio))
            x = int(padding + (ratio * usable_w))
        self.sq_btn.move(x, (self.pill_container.height() - self.sq_btn.height()) // 2)
        self.sq_btn.show()

    def _refresh_pill_style(self):
        # Colors from reference
        ball_color = COLOR_ACCENT_MAIN
        pill_bg = COLOR_ACCENT_DARK

        if self.current_idx in self.marked_indices:
            ball_color = COLOR_ACCENT_LIGHT

        if self.enum_attr == "rotateOrder":
            self.sq_btn.setStyleSheet("background: transparent; border: none;")
            icon = ATTRIBUTE_SWITCHER_GLOBE_IMAGE

            pixmap = QtGui.QPixmap(icon)
            if not pixmap.isNull():
                # Ensure sizes are integers
                target_size = int(util.DPI(12))
                if target_size < 1:
                    target_size = 12

                pixmap = pixmap.scaled(target_size, target_size, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)

                # Tint the icon
                tinted = QtGui.QPixmap(pixmap.size())
                tinted.fill(QtCore.Qt.transparent)
                painter = QtGui.QPainter(tinted)
                painter.drawPixmap(0, 0, pixmap)
                painter.setCompositionMode(QtGui.QPainter.CompositionMode_SourceIn)
                painter.fillRect(tinted.rect(), QtGui.QColor(ball_color))
                painter.end()

                self.sq_btn.setIcon(QtGui.QIcon(tinted))
                self.sq_btn.setIconSize(QtCore.QSize(target_size, target_size))
            else:
                # Basic dot fallback if SVG fails to load
                self.sq_btn.setIcon(QtGui.QIcon())
                self.sq_btn.setStyleSheet("background: {}; border-radius: {}px; border: none;".format(ball_color, int(util.DPI(6))))
        else:
            self.sq_btn.setIcon(QtGui.QIcon())
            self.sq_btn.setStyleSheet("background: {}; border-radius: {}px; border: none;".format(ball_color, int(util.DPI(6))))

        self.pill_container.setStyleSheet("background: {}; border-radius: {}px;".format(pill_bg, util.DPI(8)))

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        # Draw row background as seen in reference
        rect = self.rect().adjusted(1, 1, -1, -1)
        bg_color = QtGui.QColor(COLOR_ACCENT_MAIN)
        if self.is_enum and self.multi_checkbox.isChecked():
            bg_color = QtGui.QColor(COLOR_BLEND_MULTI)
        elif self._hover_active:
            bg_color = QtGui.QColor(COLOR_ACCENT_WHITE)

        painter.setBrush(QtGui.QBrush(bg_color))
        painter.setPen(QtGui.QPen(QtGui.QColor("#ffffff"), 1))
        painter.drawRoundedRect(rect, 2, 2)

    def enterEvent(self, event):
        self._hover_active = True
        self._update_multi_checkbox_visibility()
        self.update()
        if self.parent_dialog:
            self.parent_dialog._handle_attr_hover(self)
            # Ensure parent interaction state is active when a row is hovered
            if hasattr(self.parent_dialog, "_update_interaction_state"):
                self.parent_dialog._update_interaction_state(True)
        QtWidgets.QWidget.enterEvent(self, event)

    def mouseMoveEvent(self, event):
        self._update_multi_checkbox_visibility()
        QtWidgets.QWidget.mouseMoveEvent(self, event)

    def mousePressEvent(self, event):
        if (
            event.button() == QtCore.Qt.LeftButton
            and self.is_enum
            and self.multi_checkbox.isVisible()
        ):
            self.multi_checkbox.toggle()
            event.accept()
            return
        QtWidgets.QWidget.mousePressEvent(self, event)

    def leaveEvent(self, event):
        self._hover_active = self._popup_active
        if not self.multi_checkbox.isChecked():
            self.multi_checkbox.hide()
        self.update()
        if self.parent_dialog:
            self.parent_dialog._handle_attr_leave(self)
        QtWidgets.QWidget.leaveEvent(self, event)

    def on_select(self, idx, all_frames=None):
        self.current_idx = idx
        self.val_label.setText((self.options[int(idx)] if self.is_enum else "{:.2f}".format(idx)))

        if not self.is_enum:
            self._update_numeric_ball_pos()

        self._refresh_pill_style()

        if all_frames is None:
            return

        if self.is_enum:
            value = self.options[int(idx)]
        else:
            value = idx

        options_map = None

        if self.is_enum:
            for _, item_data in self.parent_dialog._active_switch_widgets.items():
                item, item_options_map = item_data

                if item == self:
                    options_map = item_options_map
                    break
        else:
            operations = []

            for obj, data in self.objects_map.items():
                operations.append(
                    SwitchOperation(
                        xform_target=data.get("xform_target", obj),
                        attr_node=data.get("attr_node", obj),
                        attr=data["attr"],
                        value=idx,
                        label=idx,
                        source=data.get("source", "local"),
                    )
                )

            options_map = {
                idx: {
                    "index": idx,
                    "operations": operations,
                }
            }

        if options_map:
            self.parent_dialog._apply_attribute_switch(
                value,
                self.enum_attr,
                options_map,
                all_frames_override=all_frames,
            )

    def currentText(self):
        return self.options[int(self.current_idx)] if self.options else ""


class MultiAttributeSwitchDialog(FloatingWidget):
    """Stage independent enum choices in a responsive column grid."""

    def __init__(self, parent_dialog, entries):
        FloatingWidget.__init__(self, popup=False, parent=parent_dialog)
        self.parent_dialog = parent_dialog
        self.entries = list(entries or [])
        self._prepare_gimbal_results()
        self._selected_options = {}
        self._option_groups = []
        self._column_widgets = []
        self._all_frames = False
        self.setWindowTitle(_t("Switch Multiple Attributes"))
        self.setMinimumWidth(util.DPI(220))
        self._build_ui()

    def _prepare_gimbal_results(self):
        """Run deferred rotate-order analysis only for staged multi rows."""
        for item, _options_map in self.entries:
            if item.enum_attr != "rotateOrder":
                continue
            try:
                combined = self.parent_dialog.analyze_group_gimbal(
                    item.objects_map
                )
            except Exception as exc:
                cmds.warning(
                    "Error analyzing staged rotate orders: {}".format(exc)
                )
                combined = {}
            item.gimbal_info = combined

    def _build_ui(self):
        title = QtWidgets.QLabel(
            "Switch {} channels".format(len(self.entries)), self.mainContent
        )
        title.setStyleSheet(
            "color: {}; font-size: {}px; font-weight: bold;".format(
                COLOR_TEXT_SECONDARY, util.DPI(14)
            )
        )
        self.mainLayout.addWidget(title)

        self.mainLayout.addSpacing(util.DPI(10))
        self._add_scope_controls()
        self.mainLayout.addSpacing(util.DPI(10))
        self._columns_grid = QtWidgets.QGridLayout()
        self._columns_grid.setContentsMargins(0, 0, 0, 0)
        self._columns_grid.setHorizontalSpacing(util.DPI(6))
        self._columns_grid.setVerticalSpacing(util.DPI(6))
        self.mainLayout.addLayout(self._columns_grid)
        self._build_columns()
        self._layout_columns(QtGui.QGuiApplication.primaryScreen())

        self.setBottomBar(
            buttons=[
                base_widgets.QFlatDialogButton(
                    "Cancel", callback=self._cancel, icon=util.return_icon_path("cancel")
                ),
                base_widgets.QFlatDialogButton(
                    "Apply",
                    callback=self._apply,
                    icon=util.return_icon_path("apply"),
                    highlight=True,
                ),
            ],
            closeButton=False,
            highlight="Apply",
        )
        self._apply_button = next(
            (
                button
                for button in self.bottomBar.findChildren(QtWidgets.QPushButton)
                if button.text() == "Apply"
            ),
            None,
        )
        if self._apply_button is not None:
            self._apply_button.setEnabled(False)

    def _add_scope_controls(self):
        layout = QtWidgets.QHBoxLayout()
        layout.setSpacing(util.DPI(4))
        label = QtWidgets.QLabel(_t("Keyframes"), self.mainContent)
        label.setStyleSheet(
            "color: {}; font-size: {}px;".format(
                COLOR_TEXT_SECONDARY, util.DPI(11)
            )
        )
        layout.addWidget(label)
        layout.addStretch(1)

        group = QtWidgets.QButtonGroup(self)
        group.setExclusive(True)
        for text, all_frames in (
            (AttributePopup.CURRENT_KEYFRAMES, False),
            (AttributePopup.ALL_KEYFRAMES, True),
        ):
            button = QtWidgets.QPushButton(text, self.mainContent)
            button.setCheckable(True)
            _configure_option_button(button, compact=True)
            font = QtGui.QFont(button.font())
            font.setBold(True)
            button.setMinimumWidth(QtGui.QFontMetrics(font).horizontalAdvance(text) + util.DPI(20))
            _connect_checkable_button(
                button, self._choose_scope, all_frames
            )
            group.addButton(button)
            layout.addWidget(button)
            if not all_frames:
                button.setChecked(True)
        self._scope_group = group
        self.mainLayout.addLayout(layout)

    def _build_columns(self):
        for entry_index, (item, options_map) in enumerate(self.entries):
            column = QtWidgets.QWidget(self.mainContent)
            column.setFixedWidth(util.DPI(165))
            column.setStyleSheet("background: transparent;")
            layout = QtWidgets.QVBoxLayout(column)
            layout.setContentsMargins(
                util.DPI(5), util.DPI(5), util.DPI(5), util.DPI(5)
            )
            layout.setSpacing(util.DPI(3))

            object_heading = QtWidgets.QLabel(item.object_label, column)
            object_heading.setWordWrap(False)
            object_heading.setStyleSheet(
                "color: {}; font-size: {}px; background: transparent;".format(
                    COLOR_TEXT_SECONDARY, util.DPI(11)
                )
            )
            object_heading.setToolTip(item.object_label)
            layout.addWidget(object_heading)

            attribute_text = item.attribute_label
            if item.has_mixed_key_values:
                attribute_text += " *"
            attribute_heading = QtWidgets.QLabel(attribute_text, column)
            attribute_heading.setWordWrap(False)
            attribute_heading.setStyleSheet(
                "color: {}; font-size: {}px; font-weight: bold; background: transparent;".format(
                    COLOR_TEXT_SECONDARY, util.DPI(11)
                )
            )
            attribute_heading.setToolTip(item.attribute_label)
            layout.addWidget(attribute_heading)

            group = QtWidgets.QButtonGroup(self)
            group.setExclusive(True)
            self._option_groups.append(group)
            option_count = 0
            for option_index, option in enumerate(item.options):
                if option not in options_map:
                    continue
                option_count += 1
                display_option = (
                    _rotation_order_option_text(option, item.gimbal_info)
                    if item.enum_attr == "rotateOrder" else option
                )
                button = QtWidgets.QPushButton(display_option, column)
                button.setCheckable(True)
                _configure_option_button(button)
                _connect_checkable_button(
                    button, self._choose_option, entry_index, option
                )
                _add_option_state_indicator(
                    button,
                    is_current=option_index in item.current_indices,
                    is_keyed=option_index in item.marked_indices,
                )
                group.addButton(button)
                layout.addWidget(button)
            if not option_count:
                empty = QtWidgets.QLabel(_t("No options"), column)
                empty.setStyleSheet(
                    "color: {}; background: transparent;".format(
                        COLOR_TEXT_SECONDARY
                    )
                )
                layout.addWidget(empty)
            layout.addStretch(1)
            self._column_widgets.append(column)

    def _layout_columns(self, screen):
        while self._columns_grid.count():
            self._columns_grid.takeAt(0)
        available_width = util.DPI(700)
        if screen is not None:
            available_width = screen.availableGeometry().width() - util.DPI(80)
        column_step = util.DPI(171)
        columns_per_row = max(
            1,
            min(len(self._column_widgets), available_width // column_step),
        )
        for index, column in enumerate(self._column_widgets):
            self._columns_grid.addWidget(
                column,
                index // columns_per_row,
                index % columns_per_row,
            )

    def _choose_scope(self, checked, all_frames):
        if checked:
            self._all_frames = all_frames

    def _choose_option(self, checked, entry_index, option):
        if not checked:
            return
        self._selected_options[entry_index] = option
        if self._apply_button is not None:
            self._apply_button.setEnabled(True)

    def _apply(self):
        if not self._selected_options:
            return
        staged_entries = [
            (self.entries[index][0], self.entries[index][1], option)
            for index, option in sorted(self._selected_options.items())
        ]
        self.parent_dialog._apply_multi_switch(
            staged_entries, self._all_frames
        )

    def _cancel(self):
        self.parent_dialog._close_multi_switch_dialog(clear_selection=True)

    def reject(self):
        self._cancel()

    def show_beside(self, widget):
        position = widget.mapToGlobal(QtCore.QPoint(widget.width(), 0))
        screen = (
            QtGui.QGuiApplication.screenAt(position)
            or QtGui.QGuiApplication.primaryScreen()
        )
        self._layout_columns(screen)
        self.adjustSize()
        if screen is not None:
            available = screen.availableGeometry()
            if position.x() + self.width() > available.right():
                position.setX(
                    widget.mapToGlobal(QtCore.QPoint(0, 0)).x() - self.width()
                )
            position.setX(
                max(
                    available.left(),
                    min(position.x(), available.right() - self.width()),
                )
            )
            position.setY(
                max(
                    available.top(),
                    min(position.y(), available.bottom() - self.height()),
                )
            )
        self.move(position)
        self.show()
        self.raise_()

class TargetItemWidget(QWidget):
    def __init__(self, name, list_ref):
        QWidget.__init__(self)

        self.name = name
        self.list_ref = list_ref

        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(4)

        label = QLabel(name.split(":")[-1])

        close_btn = QPushButton()
        base_widgets.QFlatHoverableIcon.apply(close_btn, util.return_icon_path("close"))
        close_btn.setIconSize(QSize(15, 15))
        close_btn.setFixedSize(15, 15)
        close_btn.setFocusPolicy(Qt.NoFocus)
        close_btn.clicked.connect(self._remove)
        close_btn.setStyleSheet(
            """
            QPushButton {
                border: none;
                background: transparent;
                padding: 0px;
                margin: 0px;
            }
            QPushButton:pressed {
                background: #101010;
            }
            """
        )

        layout.addWidget(label)
        layout.addStretch()
        layout.addWidget(close_btn)

    def _remove(self):
        self.list_ref.remove_target(self.name)


class TargetsList(QListWidget):
    def __init__(self, parent=None):
        QListWidget.__init__(self, parent)

        self.backing_store = []
        self.setStyleSheet(
            """
            QListWidget:focus {
                outline: none;
                border: none;
            }
            """
        )

    def add_target(self, name):
        if not Maya.exists(name) or name in self.backing_store:
            return

        self.backing_store.append(name)

        item = QListWidgetItem()
        item.setFlags(Qt.NoItemFlags)

        widget = TargetItemWidget(name, self)
        item.setSizeHint(widget.sizeHint())

        self.addItem(item)
        self.setItemWidget(item, widget)

    def remove_target(self, name):
        if name in self.backing_store:
            self.backing_store.remove(name)

        for i in range(self.count()):
            widget = self.itemWidget(self.item(i))

            if widget and widget.name == name:
                self.takeItem(i)
                break


class SetupTargetsDialog(FloatingWidget):
    def __init__(self, parent, objects_dict, on_close):
        FloatingWidget.__init__(self, popup=False, parent=parent)

        self.on_close = on_close
        self.objects_dict = objects_dict

        if parent and hasattr(parent, "_suspend_auto_close"):
            parent._suspend_auto_close()

        self._create_layouts()
        self.setBottomBar(
            [
                base_widgets.QFlatDialogButton(
                    "Add",
                    callback=self._add_target,
                    icon=util.return_icon_path("add"),
                    highlight=True,
                )
            ],
            closeButton=True,
            spacing=util.DPI(2),
        )

    def _create_layouts(self):
        title = QLabel("Xform targets")
        title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        title.setStyleSheet("font-size: 16px; font-weight: bold; margin-bottom: 4px;")

        self.targets_list = TargetsList(self)
        self.targets_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        for target in list(self.objects_dict.keys()):
            self.targets_list.add_target(target)

        self.mainLayout.addWidget(title)
        self.mainLayout.addWidget(self.targets_list)

    def _add_target(self):
        for obj in Maya.selection():
            self.targets_list.add_target(obj)

    def closeEvent(self, event):
        order = self.targets_list.backing_store
        original_values = list(self.objects_dict.values())
        fallback = original_values[0] if original_values else {}

        new_dict = {}

        for target in order:
            new_dict[target] = dict(self.objects_dict.get(target, fallback))
            new_dict[target]["xform_target"] = target

        self.objects_dict.clear()
        self.objects_dict.update(new_dict)

        if callable(self.on_close):
            self.on_close(self.objects_dict.keys())

        parent = self.parent()

        if parent and hasattr(parent, "_resume_auto_close"):
            parent._resume_auto_close()

        FloatingWidget.closeEvent(self, event)


class Timeline(QWidget):
    def __init__(self, parent, timerange=None, color=(200, 120, 200), autodestroy=300):
        QWidget.__init__(self, parent)

        self.timerange = timerange or [int(f) for f in cmds.timeControl("timeControl1", ra=1, q=True)]
        self.color = QColor(*(list(color) + [70]))
        self.timer = None

        if not self.timerange:
            self.hide()
            return

        self.setGeometry(parent.rect())
        self.show()
        self.raise_()

        if autodestroy is not None:
            self.timer = QTimer(self)
            self.timer.setSingleShot(True)
            self.timer.timeout.connect(self.delete_marker)
            self.timer.start(autodestroy)

    @classmethod
    def create(cls, timerange=None, color=(200, 120, 200), autodestroy=300):
        parent = cls.get_timeline()

        if not parent:
            return None

        return cls(
            parent=parent,
            timerange=timerange,
            color=color,
            autodestroy=autodestroy,
        )

    @classmethod
    def get_timeline(cls):
        try:
            timeline = mel.eval("$tmpVar=$gPlayBackSlider")
            ptr = (
                omui.MQtUtil.findControl(timeline)
                or omui.MQtUtil.findLayout(timeline)
                or omui.MQtUtil.findMenuItem(timeline)
            )

            if ptr:
                return util.get_maya_qt(ptr, QWidget)
        except Exception:
            pass

        return None

    def paintEvent(self, event):
        if not self.timerange:
            return

        try:
            start = cmds.playbackOptions(q=True, minTime=True)
            end = cmds.playbackOptions(q=True, maxTime=True)
        except Exception:
            return

        if end <= start:
            return

        total_width = self.width()
        step = (total_width - (total_width * 0.01)) / float(end - start + 1)

        start_frame, end_frame = self.timerange
        end_frame -= 1

        pos_start = (start_frame - start) * step + (total_width * 0.005)
        pos_end = (end_frame + 1 - start) * step + (total_width * 0.005)

        rect = QRectF(QPointF(pos_start, 0), QPointF(pos_end, self.height()))

        painter = QPainter(self)
        painter.setPen(Qt.NoPen)
        painter.fillRect(rect, QBrush(self.color))

    def delete_marker(self):
        try:
            self.hide()
            self.setParent(None)
            self.deleteLater()
        except RuntimeError:
            pass


class SwitchExecutor(object):
    ROTATE_AXES = ("rotateX", "rotateY", "rotateZ")

    def __init__(self, owner):
        self.owner = owner

    def collect_frames(self, operations, all_frames, timeline_selection, current_frames):
        current_time = cmds.currentTime(query=True)
        if not all_frames and not timeline_selection:
            return [current_time]
        frames = set()
        for operation in operations:
            frames.update(Maya.key_times_for_node(operation.xform_target))
            frames.update(Maya.key_times_for_plug(operation.plug))
        if timeline_selection:
            start, end = current_frames
            frames = {frame for frame in frames if start <= frame < end}
            return sorted(frames)
        return sorted(frames) or [current_time]

    def _rotate_order_fast_eligible(self, operation):
        node = operation.xform_target
        if operation.attr != "rotateOrder" or operation.attr_node != node:
            return False
        # Animated order and non-curve drivers need evaluated world transforms.
        if cmds.getAttr(operation.plug, lock=True) or cmds.listConnections(
            operation.plug, source=True, destination=False
        ):
            return False
        for axis in self.ROTATE_AXES:
            plug = Maya.plug(node, axis)
            if cmds.getAttr(plug, lock=True):
                return False
            sources = cmds.listConnections(plug, source=True, destination=False) or []
            if sources and (len(sources) != 1 or cmds.nodeType(sources[0]) != "animCurveTA"):
                return False
        return True

    def _prepare_rotation(self, operation):
        """Read every original value before editing any curve; never scrub time."""
        node = operation.xform_target
        old_order = int(cmds.getAttr(operation.plug))
        new_order = int(operation.value)
        times = set()
        for axis in self.ROTATE_AXES:
            times.update(Maya.key_times_for_plug(Maya.plug(node, axis)))
        keyed = bool(times)
        samples = []
        to_radians = om.MAngle(1.0, om.MAngle.uiUnit()).asRadians()
        from_radians = om.MAngle(1.0, om.MAngle.kRadians).asUnits(om.MAngle.uiUnit())
        previous = None
        for frame in sorted(times) if keyed else [None]:
            values = [cmds.getAttr(Maya.plug(node, axis), **({"time": frame} if keyed else {}))
                      for axis in self.ROTATE_AXES]
            rotation = om.MEulerRotation(*(list(v * to_radians for v in values) + [old_order]))
            rotation.reorderIt(new_order)
            if previous is not None:
                rotation = rotation.closestSolution(previous)
            previous = rotation
            samples.append((frame, [rotation.x * from_radians, rotation.y * from_radians,
                                    rotation.z * from_radians]))
        return operation, keyed, samples

    def _apply_rotation(self, prepared):
        operation, keyed, samples = prepared
        existing = {axis: Maya.key_times_for_plug(Maya.plug(operation.xform_target, axis))
                    for axis in self.ROTATE_AXES}
        for frame, values in samples:
            for axis, value in zip(self.ROTATE_AXES, values):
                plug = Maya.plug(operation.xform_target, axis)
                if keyed:
                    if frame in existing[axis]:
                        cmds.keyframe(plug, edit=True, time=(frame, frame), valueChange=value)
                    else:
                        cmds.setKeyframe(plug, time=(frame, frame), value=value)
                else:
                    cmds.setAttr(plug, value)
        cmds.setAttr(operation.plug, operation.value)

    @staticmethod
    def _write_attribute(operation, frame, keyed):
        if keyed or Maya.key_times_for_plug(operation.plug):
            cmds.setKeyframe(operation.plug, time=(frame, frame), value=operation.value,
                             outTangentType="step")
        else:
            cmds.setAttr(operation.plug, operation.value)

    def apply_requests(self, requests, timeline_selection, selected_range):
        """Capture the entire batch before writing, then compensate parent first."""
        scheduled = {}
        fast = []
        seen = {}
        for operations, all_frames in requests:
            for operation in operations:
                if not operation.is_valid():
                    continue
                if operation.plug in seen and seen[operation.plug] != operation.value:
                    raise ValueError("Conflicting choices for {}".format(operation.plug))
                seen[operation.plug] = operation.value
                if (self.owner.fast_rotation_order and not timeline_selection
                        and self._rotate_order_fast_eligible(operation)):
                    if not any(item[0].plug == operation.plug for item in fast):
                        fast.append(self._prepare_rotation(operation))
                    continue
                frames = self.collect_frames([operation], all_frames,
                                             timeline_selection, selected_range)
                keyed = all_frames or timeline_selection
                for frame in frames:
                    scheduled.setdefault(frame, []).append((operation, keyed))
        if not scheduled and not fast:
            return set()
        current_time = cmds.currentTime(query=True)
        auto_key = cmds.autoKeyframe(query=True, state=True)
        marker = None
        snapshots = {}
        try:
            if scheduled:
                marker = Timeline.create([min(scheduled), max(scheduled) + 1])
                with UndoDisabled():
                    with ProgressBar(len(scheduled), status="Saving Positions...") as progress:
                        for frame, entries in sorted(scheduled.items()):
                            if progress.step():
                                return set()
                            cmds.currentTime(frame)
                            snapshots[frame] = {op.xform_target: Maya.matrix(op.xform_target)
                                                for op, _ in entries}
            cmds.autoKeyframe(state=False)
            for prepared in fast:
                self._apply_rotation(prepared)
            with ProgressBar(len(scheduled), status="Applying Positions...", interruptable=False) as progress:
                for frame, entries in sorted(scheduled.items()):
                    cmds.currentTime(frame)
                    # All switches first, then one compensation per target. This
                    # prevents one staged channel from invalidating another.
                    for operation, keyed in entries:
                        self._write_attribute(operation, frame, keyed)
                    def depth(target):
                        paths = cmds.ls(target, long=True) or [target]
                        return paths[0].count("|")
                    for target in sorted(snapshots[frame], key=depth):
                        Maya.set_matrix(target, snapshots[frame][target])
                        target_entries = [(op, keyed) for op, keyed in entries if op.xform_target == target]
                        for attr in ("tx", "ty", "tz", "rx", "ry", "rz", "sx", "sy", "sz"):
                            plug = Maya.plug(target, attr)
                            if (any(keyed for _, keyed in target_entries) or auto_key
                                    or Maya.key_times_for_plug(plug)):
                                if cmds.getAttr(plug, settable=True):
                                    cmds.setKeyframe(plug, time=(frame, frame))
                    progress.step()
        finally:
            cmds.autoKeyframe(state=auto_key)
            if scheduled:
                cmds.currentTime(current_time)
            if marker:
                marker.delete_marker()
        return {op.xform_target for entries in scheduled.values() for op, _ in entries} | {item[0].xform_target for item in fast}


class _ContentHeightScrollArea(QtWidgets.QScrollArea):
    """A scroll area that collapses fully and derives height from its content."""

    def minimumSizeHint(self):
        return QtCore.QSize(0, 0)

    def contentSizeHint(self):
        content = self.widget()
        if content is None:
            return QtCore.QSize(0, 0)
        # With widgetResizable enabled, the content widget may already have
        # been collapsed to the viewport. Its layout retains the intrinsic
        # size of the child rows and avoids that sizing feedback loop.
        content_layout = content.layout()
        content_hint = (
            content_layout.sizeHint()
            if content_layout is not None
            else content.sizeHint()
        )
        frame_size = self.frameWidth() * 2
        return QtCore.QSize(
            max(0, content_hint.width()) + frame_size,
            max(0, content_hint.height()) + frame_size,
        )

    def sizeHint(self):
        return self.contentSizeHint()

class SpaceSwitchAlehaWidget(FloatingWidget):
    ROTATE_ORDER_OPTIONS = ["xyz", "yzx", "zxy", "xzy", "yxz", "zyx"]

    def __init__(self, popup=False, parent=None):
        parent = parent or util.get_maya_qt()
        FloatingWidget.__init__(self, popup=popup, parent=parent)

        self._active_popup = None
        self._multi_switch_dialog = None
        self._last_multi_modifier_state = None
        self._popup_pending_item = None
        self._is_ui_hovered = False
        self._active_switch_widgets = {}
        self._geometry_anchor_bottom = None
        self._geometry_fit_pending = True
        self._previous_selection = []
        self._switch_data = {}

        self._popup_timer = QTimer(self)
        self._popup_timer.setSingleShot(True)
        self._popup_timer.setInterval(100)
        self._popup_timer.timeout.connect(self._show_pending_popup)

        self.settings = QSettings(DATA.get("AUTHOR", {}).get("name", "Alehaaa"), DATA.get("TOOL"))
        self._load_persistent_settings()

        self.analyzer = GimbalAnalyzer()
        self.catalog_builder = SwitchCatalogBuilder(self.analyzer, self.show_rotate_order)
        self.executor = SwitchExecutor(self)

        self._cb = CallbackManager()

        self._create_layouts()
        self._create_selection_layout()
        self._add_callbacks()
        self._modifier_timer = QTimer(self)
        self._modifier_timer.setInterval(80)
        self._modifier_timer.timeout.connect(self._poll_multi_select_modifier)
        self._modifier_timer.start()
        self.refresh(force=True)

    def _poll_multi_select_modifier(self):
        """Refresh once whenever the directly queried Ctrl/Cmd state changes."""
        if not self.isVisible():
            self._last_multi_modifier_state = None
            return
        modifier_held = _multi_select_modifier_held()
        if modifier_held == self._last_multi_modifier_state:
            return
        self._last_multi_modifier_state = modifier_held
        self._refresh_multi_checkbox_visibility()

    def _refresh_multi_checkbox_visibility(self):
        if not self.isVisible():
            return
        for item, _options_map in self._active_switch_widgets.values():
            if util.is_valid_widget(item):
                item._update_multi_checkbox_visibility()

    def _selected_multi_entries(self):
        """Return checked enum rows and their option maps in display order."""
        entries = []
        for _key, (item, options_map) in self._active_switch_widgets.items():
            if (
                util.is_valid_widget(item)
                and item.is_enum
                and item.multi_checkbox.isChecked()
            ):
                entries.append((item, options_map))
        return entries

    def _expanded_multi_entries(self, selected_entries=None):
        """Expand collapsed rows into independently configurable targets."""
        entries = []
        for item, options_map in (
            selected_entries
            if selected_entries is not None
            else self._selected_multi_entries()
        ):
            if len(item.objects_map) <= 1:
                entries.append((item, options_map))
                continue
            for target, object_data in item.objects_map.items():
                staged_item = _StagedAttributeEntry(
                    item, target, object_data
                )
                staged_options = self._build_options_map(
                    staged_item.objects_map
                )
                entries.append((staged_item, staged_options))
        return entries

    def _on_attribute_multi_checked(self, item, checked):
        """Update the staged multi-switch UI without changing the scene."""
        self._popup_timer.stop()
        self._popup_pending_item = None
        self._close_active_popup()

        selected_entries = self._selected_multi_entries()
        entries = self._expanded_multi_entries(selected_entries)
        self._close_multi_switch_dialog(clear_selection=False)
        if len(entries) < 2:
            return

        self._multi_switch_dialog = MultiAttributeSwitchDialog(self, entries)
        anchor = (
            item
            if checked and util.is_valid_widget(item)
            else selected_entries[-1][0]
        )
        self._multi_switch_dialog.show_beside(anchor)
        self._update_interaction_state(True, force=True)

    def _close_multi_switch_dialog(self, clear_selection=False):
        """Close the staged dialog and optionally clear all checked rows."""
        dialog = getattr(self, "_multi_switch_dialog", None)
        self._multi_switch_dialog = None
        if dialog and util.is_valid_widget(dialog):
            dialog.hide()
            dialog.deleteLater()

        if clear_selection:
            for item, _options_map in self._selected_multi_entries():
                item.multi_checkbox.blockSignals(True)
                item.multi_checkbox.setChecked(False)
                item.multi_checkbox.blockSignals(False)
                item._update_multi_checkbox_visibility()
                item.update()
        self._update_interaction_state(self._is_cursor_within_bounds(), force=True)

    @staticmethod
    def _new_attribute_container():
        container = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(util.DPI(1))
        layout.setSizeConstraint(QtWidgets.QLayout.SetMinAndMaxSize)
        return container, layout

    def _update_attribute_area_geometry(self):
        """Notify Qt after atomically replacing the attribute content."""
        self.enums_layout.invalidate()
        self.enums_layout.activate()
        self.enums_container.adjustSize()
        self.enums_container.updateGeometry()
        self._update_attribute_scroll_minimum_height()
        self.attributes_scroll.updateGeometry()
        self.mainLayout.invalidate()
        self.mainLayout.activate()
        self._refresh_attribute_scrollbar_margin()

    def _update_attribute_scroll_minimum_height(self):
        """Fit at least one complete enum row whenever rows are available."""
        first_item = self.enums_layout.itemAt(0)
        first_widget = first_item.widget() if first_item is not None else None
        if first_widget is None:
            self.attributes_scroll.setMinimumHeight(0)
            return

        first_widget.ensurePolished()
        item_layout = first_widget.layout()
        if item_layout is not None:
            item_layout.activate()
        row_height = max(
            first_widget.sizeHint().height(),
            first_widget.minimumSizeHint().height(),
        )
        self.attributes_scroll.setMinimumHeight(
            row_height + (self.attributes_scroll.frameWidth() * 2)
        )

    def _update_attribute_scrollbar_margin(self, minimum, maximum):
        """Keep enum rows clear of an overlay-style vertical scrollbar."""
        right_margin = 0
        if maximum > minimum:
            scrollbar = self.attributes_scroll.verticalScrollBar()
            right_margin = scrollbar.sizeHint().width() + util.DPI(2)
        self.enums_layout.setContentsMargins(0, 0, right_margin, 0)

    def _refresh_attribute_scrollbar_margin(self):
        scrollbar = self.attributes_scroll.verticalScrollBar()
        self._update_attribute_scrollbar_margin(
            scrollbar.minimum(), scrollbar.maximum()
        )

    def _replace_attribute_content(self, switch_data):
        """Build a complete replacement off-screen, then swap it in once."""
        new_container, new_layout = self._new_attribute_container()
        new_widgets = {}

        for enum_name, data in (switch_data or {}).items():
            self._create_switch_item(
                enum_name,
                data,
                target_layout=new_layout,
                target_registry=new_widgets,
            )

        old_container = self.attributes_scroll.takeWidget()
        self.enums_container = new_container
        self.enums_layout = new_layout
        self._active_switch_widgets = new_widgets
        self.attributes_scroll.setWidget(new_container)
        if old_container is not None:
            old_container.deleteLater()

        self._update_attribute_area_geometry()

    def _fit_to_available_screen(self):
        """Fit content up to the available screen, then rely on scrolling."""
        screen = QtGui.QGuiApplication.screenAt(self.frameGeometry().center())
        if screen is None:
            screen = QtGui.QGuiApplication.screenAt(QtGui.QCursor.pos())
        screen = screen or QtGui.QGuiApplication.primaryScreen()
        if screen is None:
            return

        available = screen.availableGeometry()
        screen_margin = util.DPI(10)
        max_height = max(
            util.DPI(120), available.height() - (screen_margin * 2)
        )
        self.setMaximumHeight(max_height)

        # Clear the limit from a previous (possibly empty) refresh before
        # asking Qt for the new content-preferred geometry.
        self.attributes_scroll.setMaximumHeight(16777215)
        self.attributes_scroll.updateGeometry()

        # Measure the complete window chrome first. This includes the selection
        # header, layout margins, and the optional persistent-window bottom bar.
        self.mainLayout.invalidate()
        self.mainLayout.activate()
        if self.bottomBar and util.is_valid_widget(self.bottomBar):
            bottom_layout = self.bottomBar.layout()
            if bottom_layout:
                bottom_layout.activate()
            self.bottomBar.adjustSize()
            self.bottomBar.updateGeometry()
        self.root_layout.invalidate()
        self.root_layout.activate()

        scroll_height = self.attributes_scroll.contentSizeHint().height()
        preferred_height = self.root_layout.sizeHint().height()
        chrome_height = max(0, preferred_height - scroll_height)
        available_scroll_height = max(0, max_height - chrome_height)
        self.attributes_scroll.setMaximumHeight(
            min(scroll_height, available_scroll_height)
        )
        self.attributes_scroll.updateGeometry()

        self.mainLayout.invalidate()
        self.mainLayout.activate()
        self.root_layout.invalidate()
        self.root_layout.activate()
        desired_height = min(self.root_layout.sizeHint().height(), max_height)
        anchored_bottom = self._geometry_anchor_bottom
        if anchored_bottom is None:
            anchored_bottom = self.frameGeometry().bottom()
        self.resize(self.width(), desired_height)

        # Keep the bottom edge anchored: content grows upward and collapses
        # downward, which also preserves placement above the toolbar.
        min_y = available.top() + screen_margin
        max_y = available.bottom() - desired_height - screen_margin + 1
        anchored_y = anchored_bottom - desired_height + 1
        self.move(self.x(), max(min_y, min(anchored_y, max_y)))
        self._geometry_anchor_bottom = None

    def _request_geometry_fit(self):
        """Fit now when visible, or once Qt has polished the window for show."""
        self._geometry_fit_pending = True
        if not self.isVisible():
            return
        self._fit_to_available_screen()
        self._geometry_fit_pending = False

    def _create_layouts(self):
        """Builds the main container layouts."""
        self.mainContent.setMinimumWidth(util.DPI(220))
        self.mainContent.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.mainContent.customContextMenuRequested.connect(self._show_context_menu)

        self.attributes_scroll = _ContentHeightScrollArea(self.mainContent)
        self.attributes_scroll.setMinimumSize(0, 0)
        self.attributes_scroll.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred
        )
        self.attributes_scroll.setWidgetResizable(True)
        self.attributes_scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.attributes_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.attributes_scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.attributes_scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
        )
        self.enums_container, self.enums_layout = self._new_attribute_container()
        self.attributes_scroll.setWidget(self.enums_container)
        self.attributes_scroll.verticalScrollBar().rangeChanged.connect(
            self._update_attribute_scrollbar_margin
        )
        self.mainLayout.addWidget(self.attributes_scroll)
        self.mainLayout.addStretch(1)

    def _create_selection_layout(self):
        """Builds the header area showing tool title and current status."""
        selection_layout = QtWidgets.QVBoxLayout()
        selection_layout.setSpacing(util.DPI(5))
        selection_layout.setContentsMargins(0, util.DPI(6), 0, util.DPI(8))

        title_layout = QtWidgets.QHBoxLayout()
        title_layout.setSpacing(util.DPI(6))
        title_layout.setContentsMargins(0, 0, 0, 0)

        title_icon_size = util.DPI(25)
        title_icon = QtWidgets.QLabel()
        title_icon.setFixedSize(title_icon_size, title_icon_size)
        title_icon.setPixmap(
            QtGui.QIcon(util.return_icon_path("spaceswitch.svg")).pixmap(
                title_icon_size,
                title_icon_size,
            )
        )
        title_icon.setAlignment(QtCore.Qt.AlignCenter)

        selection_title = QtWidgets.QLabel("Selection")
        selection_title.setStyleSheet(
            "font-size: %spx; color: %s; font-weight: bold; background: transparent;" % (util.DPI(18), self.TEXT_COLOR)
        )
        selection_title.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
        selection_title.setWordWrap(False)
        selection_title.setFixedHeight(selection_title.fontMetrics().height() + 2)

        title_layout.addWidget(title_icon)
        title_layout.addWidget(selection_title, 1)

        self.selection_label = QtWidgets.QLabel(_t("No switches for selection"))
        self.selection_label.setStyleSheet("color: %s; background: transparent;" % self.TEXT_COLOR)

        selection_layout.addLayout(title_layout)
        selection_layout.addWidget(self.selection_label)

        self.mainLayout.insertLayout(0, selection_layout)

    def _load_persistent_settings(self):
        self.namespace_display = self._setting_bool("namespace_display", False)
        self.all_frames = self._setting_bool("all_frames", False)
        self.euler_filter = self._setting_bool("euler_filter", True)
        self.fast_rotation_order = self._setting_bool("fast_rotation_order", True)
        self.show_rotate_order = self._setting_bool("show_rotate_order", True)

    def _setting_bool(self, key, default):
        value = self.settings.value(key, default)

        if isinstance(value, bool):
            return value

        if isinstance(value, int):
            return bool(value)

        if isinstance(value, str):
            return value.lower() == "true"

        return bool(default)

    def set_setting(self, setting, state, refresh=False):
        self.settings.setValue(setting, state)
        setattr(self, setting, state)

        if setting == "show_rotate_order":
            self.catalog_builder.show_rotate_order = state

        if refresh:
            self.refresh(force=True)

    def _add_callbacks(self):
        try:
            self._cb.add(
                om.MEventMessage.addEventCallback(
                    "SelectionChanged",
                    lambda *a: self.refresh(force=True),
                )
            )
            self._cb.add(
                om.MEventMessage.addEventCallback(
                    "timeChanged",
                    lambda *a: self.refresh(force=True),
                )
            )
            self._cb.add(
                om.MEventMessage.addEventCallback(
                    "Undo",
                    lambda *a: self.refresh(force=True),
                )
            )
            self._cb.add(
                om.MSceneMessage.addCallback(
                    om.MSceneMessage.kAfterOpen,
                    lambda *a: self._refresh_callbacks(),
                )
            )
        except Exception as exc:
            cmds.warning("Could not add Maya callbacks: %s" % exc)

    def _remove_callbacks(self):
        try:
            self._cb.clear()
        except Exception as exc:
            cmds.warning("Could not remove Maya callbacks: %s" % exc)

    def _refresh_callbacks(self, *args):
        self._remove_callbacks()

        if util.is_valid_widget(self):
            self._add_callbacks()

    def _clear_layout(self, layout):
        while layout.count():
            child = layout.takeAt(0)

            if child.widget():
                child.widget().deleteLater()

            if child.layout():
                self._clear_layout(child.layout())

    def _refresh_footer(self):
        self.setBottomBar(closeButton=not self._auto_close_active)

    def refresh(self, force=False):
        self._popup_timer.stop()
        self._popup_pending_item = None
        self._close_multi_switch_dialog(clear_selection=True)
        self._close_active_popup()

        current_selection = Maya.selection(long=False)

        if sorted(current_selection) == sorted(self._previous_selection) and not force:
            self._refresh_footer()
            return

        self._previous_selection = current_selection
        self._rebuild_active_widgets()

    def _rebuild_active_widgets(self):
        try:
            self._switch_data = self.catalog_builder.combined_catalog(self._previous_selection) if self._previous_selection else {}
            self._replace_attribute_content(self._switch_data)
            self.selection_label.setVisible(not bool(self._switch_data))
        except Exception as exc:
            cmds.warning("Error rebuilding SpaceSwitch widgets: {}".format(exc))
        finally:
            self._update_interaction_state(self._is_ui_hovered, force=True)
            self._refresh_footer()
            self._request_geometry_fit()

    def showEvent(self, event):
        FloatingWidget.showEvent(self, event)
        if self._geometry_fit_pending:
            self._fit_to_available_screen()
            self._geometry_fit_pending = False

    def _create_switch_item(self, enum_name, data, target_layout=None, target_registry=None):
        target_nodes = list(data["objects"].keys())
        display_name = self._format_object_name(target_nodes)

        attr_item = AttributeItem(
            display_name,
            data["long"].title(),
            enum_name,
            target_nodes,
            data["objects"],
            self,
        )

        attr_item.setToolTip(self.formatXformTooltipObjects(target_nodes))
        attr_item.setContextMenuPolicy(Qt.CustomContextMenu)
        attr_item.customContextMenuRequested.connect(
            lambda pos, sender=attr_item, item_data=data: self._show_change_target_dialog(sender, item_data)
        )

        options_map = self._build_options_map(data["objects"])
        registry = self._active_switch_widgets if target_registry is None else target_registry
        layout = self.enums_layout if target_layout is None else target_layout
        registry[(enum_name, tuple(target_nodes))] = (attr_item, options_map)
        layout.insertWidget(0, attr_item)

    def _build_options_map(self, objects_data):
        options_map = {}

        for display_object, data in objects_data.items():
            attr_node = data.get("attr_node", display_object)
            xform_target = data.get("xform_target", display_object)
            attr = data.get("attr")
            source = data.get("source", "local")

            for index, option in enumerate(data.get("enum", [])):
                entry = options_map.setdefault(
                    option,
                    {
                        "index": index,
                        "operations": [],
                    },
                )

                entry["operations"].append(
                    SwitchOperation(
                        xform_target=xform_target,
                        attr_node=attr_node,
                        attr=attr,
                        value=index,
                        label=option,
                        source=source,
                    )
                )

        return options_map

    def _format_object_name(self, objects):
        if not objects:
            return ""

        if len(objects) > 1:
            return "(%s)" % len(objects)

        name = objects[0].split("|")[-1]

        if ":" in name and not self.namespace_display:
            name = name.split(":")[-1]

        if len(name) > 50:
            return "..." + name[-50:]

        return name

    @staticmethod
    def formatXformTooltipObjects(objects):
        return "<html>Current xform target/s:<br>%s<br><br><b>Right-click to modify...</b></html>" % "<br>".join(objects)

    def analyze_group_gimbal(self, objects_data):
        results = []
        for node, data in objects_data.items():
            if not data.get("gimbal"):
                data["gimbal"] = self.analyzer.analyze(data.get("xform_target", node))
            results.append(data["gimbal"])
        orders = self.ROTATE_ORDER_OPTIONS
        scores = [max([r[order]["percentage"] for r in results if order in r] or [0])
                  for order in orders]
        labels = self.analyzer.classify(scores)
        return {order: {"percentage": score, "label": label}
                for order, score, label in zip(orders, scores, labels)}

    def _apply_multi_switch(self, staged_entries, all_frames):
        requests = [(option, item.enum_attr, options_map, all_frames)
                    for item, options_map, option in staged_entries if option in options_map]
        self._close_multi_switch_dialog(clear_selection=True)
        self._apply_requests(requests)

    def _apply_requests(self, requests):
        prepared = []
        targets = set()
        for value, attr, options_map, all_frames in requests:
            data = options_map[value]
            operations = [op for op in data.get("operations", []) if op.is_valid()]
            if operations:
                prepared.append((operations, all_frames or attr == "rotateOrder"))
                targets.update(op.xform_target for op in operations)
        if not prepared:
            return
        timeline = mel.eval('$tmp = $gPlayBackSlider')
        selected = cmds.timeControl(timeline, q=True, rangeVisible=True)
        frame_range = cmds.timeControl(timeline, q=True, rangeArray=True)
        self._remove_callbacks()
        try:
            with UndoChunk("SpaceSwitch"):
                with RefreshSuspended():
                    changed = self.executor.apply_requests(prepared, selected, frame_range)
                    if self.euler_filter and changed:
                        self.apply_euler_filter(changed)
        finally:
            self._add_callbacks()
            self.refresh(force=True)

    def _apply_attribute_switch(self, enum_value, enum_attr, options_and_objects, all_frames_override=None):
        all_frames = self.all_frames if all_frames_override is None else all_frames_override
        self._apply_requests([(enum_value, enum_attr, options_and_objects, all_frames)])

    def apply_euler_filter(self, targets):
        curves = []

        for target in targets:
            for attr in ("rx", "ry", "rz"):
                plug = Maya.plug(target, attr)

                if not cmds.objExists(plug):
                    continue

                connected = cmds.listConnections(plug, source=True, type="animCurve") or []
                curves.extend([curve for curve in connected if Maya.exists(curve)])

        curves = sorted(set(curves))

        if curves:
            cmds.filterCurve(*curves)

    def apply_active_changes(self):
        self._apply_requests([(item.currentText(), attr, options, self.all_frames)
                              for (attr, _), (item, options) in list(self._active_switch_widgets.items())
                              if item.currentText() in options])

    def _update_interaction_state(self, is_active, force=False):
        if not is_active:
            cursor = QCursor.pos()

            if util.is_valid_widget(self) and self.frameGeometry().contains(cursor):
                is_active = True

            popup = self._active_popup

            if not is_active and popup and util.is_valid_widget(popup) and popup.isVisible():
                if popup.frameGeometry().contains(cursor):
                    is_active = True

        if not force and self._is_ui_hovered == is_active:
            return

        self._is_ui_hovered = is_active

        if self._is_ui_hovered:
            self._auto_close_timer.stop()
        else:
            self._resume_auto_close()

        for _, item_data in self._active_switch_widgets.items():
            attr_item = item_data[0]

            if not util.is_valid_widget(attr_item):
                continue

            if hasattr(attr_item, "pill_opacity"):
                attr_item.pill_opacity.setOpacity(1.0 if self._is_ui_hovered else 0.0)

            if hasattr(attr_item, "val_label"):
                if not attr_item.is_enum:
                    attr_item.val_label.setVisible(False)
                elif attr_item.is_toggle:
                    attr_item.val_label.setVisible(self._is_ui_hovered)
                else:
                    attr_item.val_label.setVisible(True)

            attr_item.update()

    def enterEvent(self, event):
        self._update_interaction_state(True)
        FloatingWidget.enterEvent(self, event)

    def leaveEvent(self, event):
        QTimer.singleShot(150, lambda: self._update_interaction_state(False))
        FloatingWidget.leaveEvent(self, event)

    def _handle_attr_hover(self, item):
        if item._multi_select_modifier_held() or self._selected_multi_entries():
            self._popup_timer.stop()
            self._popup_pending_item = None
            self._close_active_popup()
            return
        self._popup_pending_item = item
        self._popup_timer.start()

    def _handle_attr_leave(self, item):
        if self._popup_pending_item == item:
            self._popup_pending_item = None

        self._popup_timer.start()

    def _show_pending_popup(self):
        """Displays the attribute choice popup beside the hovered row."""
        if self._selected_multi_entries():
            self._popup_pending_item = None
            self._close_active_popup()
            return

        # Keep the popup while the cursor is over it or an option drag is active.
        if not self._popup_pending_item or not util.is_valid_widget(self._popup_pending_item):
            popup = self._active_popup
            if not popup or not util.is_valid_widget(popup):
                return
            if popup._drag_active or popup.underMouse():
                return
            self._close_active_popup()
            return

        item = self._popup_pending_item

        # If current is same item and visible, do nothing
        if (
            self._active_popup
            and util.is_valid_widget(self._active_popup)
            and self._active_popup.item_widget == item
            and self._active_popup.isVisible()
        ):
            return

        # Otherwise, switch
        self._close_active_popup()

        if item.enum_attr == "rotateOrder":
            item.gimbal_info = self.analyze_group_gimbal(item.objects_map)
        self._active_popup = AttributePopup(item, item.on_select)
        item._set_popup_active(True)
        self._active_popup.show_beside(item)

    def _close_active_popup(self):
        """Safely removes the current popup."""
        popup = getattr(self, "_active_popup", None)
        if not popup or not util.is_valid_widget(popup):
            self._active_popup = None
            return
        item = popup.item_widget
        if util.is_valid_widget(item):
            item._set_popup_active(False)
        popup.hide()
        popup.deleteLater()
        self._active_popup = None

    def _show_change_target_dialog(self, sender, data):
        selection = Maya.selection(long=False)

        def on_close(objects):
            cmds.select(selection, replace=True)
            self._add_callbacks()
            sender.setToolTip(self.formatXformTooltipObjects(objects))
            for key, (item, _) in list(self._active_switch_widgets.items()):
                if item is sender:
                    self._active_switch_widgets[key] = (item, self._build_options_map(data["objects"]))

        self._remove_callbacks()

        dialog = SetupTargetsDialog(self, data["objects"], on_close=on_close)
        dialog.show()

    def _show_context_menu(self, pos):
        self.context_menu = widgets.QFlatMenu(self)
        self.context_menu.aboutToShow.connect(self._suspend_auto_close)
        self.context_menu.aboutToHide.connect(self._resume_auto_close)

        namespace_action = self.context_menu.addAction(
            "Show namespaces",
            description="Show namespaces for listed attributes.",
        )
        namespace_action.setCheckable(True)
        namespace_action.setChecked(self.namespace_display)

        rotate_action = self.context_menu.addAction(
            "Enable Rotate Order",
            description="List Rotate Order attributes for selected objects.",
        )
        rotate_action.setCheckable(True)
        rotate_action.setChecked(self.show_rotate_order)

        self.context_menu.addSeparator()

        euler_action = self.context_menu.addAction(
            "Auto Euler Filter",
            description="Apply euler filter to switched attributes.",
        )
        euler_action.setCheckable(True)
        euler_action.setChecked(self.euler_filter)

        self.context_menu.addSeparator()

        fast_action = self.context_menu.addAction(
            "Fast Rotation Order",
            description="Convert plain rotation curves without moving the playhead.",
        )
        fast_action.setCheckable(True)
        fast_action.setChecked(self.fast_rotation_order)
        fast_action.toggled.connect(lambda state: self.set_setting("fast_rotation_order", state))

        about_action = self.context_menu.addAction(
            "About",
            description="General information about SpaceSwitch and the author.",
        )
        about_action.setIcon(QIcon(util.return_icon_path("info")))
        about_action.triggered.connect(self.show_credits_dialog)

        rotate_action.toggled.connect(lambda state: self.set_setting("show_rotate_order", state, refresh=True))
        namespace_action.toggled.connect(lambda state: self.set_setting("namespace_display", state, refresh=True))
        euler_action.toggled.connect(lambda state: self.set_setting("euler_filter", state))

        Qtx.exec_menu(self.context_menu, QCursor.pos())

    def show_credits_dialog(self):
        self._suspend_auto_close()
        widgets.QAboutDialog.showUI(self, data=DATA)

        if widgets.QAboutDialog.dlg_instance:
            widgets.QAboutDialog.dlg_instance.finished.connect(lambda *args: self._resume_auto_close())

    def closeEvent(self, event):
        self._modifier_timer.stop()
        self._popup_timer.stop()
        self._close_multi_switch_dialog(clear_selection=True)
        self._close_active_popup()
        self._cb.clear()
        FloatingWidget.closeEvent(self, event)
        self.deleteLater()


class SpaceSwitchManager(object):
    @classmethod
    def _launch(cls, popup):
        dialog = _MAIN_DICT.get("_SPACESWITCH_INSTANCE")

        if dialog is not None and util.is_valid_widget(dialog):
            try:
                dialog._cb.clear()
                dialog.close()
            finally:
                dialog = None

        if dialog is None or not util.is_valid_widget(dialog):
            dialog = SpaceSwitchAlehaWidget(popup=popup)
            _MAIN_DICT["_SPACESWITCH_INSTANCE"] = dialog

        if popup:
            dialog.place_near_cursor()

        if dialog.isHidden():
            dialog.show()
        else:
            dialog.raise_()
            dialog.activateWindow()

    @classmethod
    def popup(cls):
        cls._launch(popup=True)

    @classmethod
    def show(cls):
        cls._launch(popup=False)


def show():
    SpaceSwitchManager.show()


def popup():
    SpaceSwitchManager.popup()
