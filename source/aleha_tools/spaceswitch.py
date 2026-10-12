from __future__ import division
# -*- coding: utf-8 -*-

import ast
import bisect
import json
import math
import sys
import threading
import traceback
from collections import OrderedDict

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
    def enum_items(node, attr):
        """[(label, value)] honouring explicit indices like "World=0:Chest=3"."""
        try:
            raw = cmds.attributeQuery(attr, node=node, listEnum=True) or []
        except Exception:
            return []
        items = []
        next_value = 0
        for part in (raw[0].split(":") if raw else []):
            label, sep, value = part.partition("=")
            label = label.strip()
            if sep:
                try:
                    next_value = int(value)
                except ValueError:
                    pass
            if any(c.isalnum() for c in label):
                items.append((label, next_value))
            next_value += 1
        return items

    @staticmethod
    def enum_labels(node, attr):
        return [label for label, _value in Maya.enum_items(node, attr)]

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
    def upstream_animation_curves(plug):
        """Find base and layered curves driving one plug, through blend nodes.

        A direct listConnections(type='animCurve') stops at animBlendNode and
        misses animation-layer rotation curves that also need Euler filtering.
        Only traverse Maya's animation blend network, avoiding unrelated rig
        utilities and cyclic dependency graphs.
        """
        pending, visited, curves = [plug], set(), set()
        while pending:
            destination = pending.pop()
            if destination in visited:
                continue
            visited.add(destination)
            for source in cmds.listConnections(destination, source=True,
                                               destination=False,
                                               skipConversionNodes=True) or []:
                node_type = cmds.nodeType(source)
                if node_type.startswith("animCurve"):
                    curves.add(source)
                elif node_type.startswith("animBlendNode"):
                    pending.append(source)
        return sorted(curves)

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

    def compute_all_scores(self, obj, order_list):
        key_times = set()

        for attr in ("rotateX", "rotateY", "rotateZ"):
            try:
                key_times.update(cmds.keyframe(obj, attribute=attr, query=True, timeChange=True) or [])
            except Exception:
                pass

        if not key_times:
            key_times = {cmds.currentTime(query=True)}

        result = []
        samples = [self.rotation_at_time(obj, time_value, order_list)
                   for time_value in sorted(key_times)]

        for order_name in order_list:
            target_order = self.convert_order_string(order_name)
            samples_for_order = []

            for rotation in samples:
                reordered = om.MEulerRotation(rotation.x, rotation.y, rotation.z, rotation.order)
                reordered.reorderIt(target_order)
                samples_for_order.append(self.gimbal_percentage(reordered))

            maximum = max(samples_for_order) if samples_for_order else 0.0
            average = (sum(samples_for_order) / float(len(samples_for_order))
                       if samples_for_order else 0.0)
            # animBot ranks an order by the midpoint of its animation-average
            # and worst-frame gimbal ratios; the UI exposes both components.
            result.append({
                "average": average,
                "maximum": maximum,
                "percentage": (average + maximum) / 2.0,
            })

        return result

    @staticmethod
    def classify(scores):
        labels = [""] * len(scores)

        if not scores:
            return labels

        best = min(scores)

        for i, value in enumerate(scores):
            if value == best:
                labels[i] = "Best"
            elif value < 30:
                labels[i] = "Good"
            elif value < 50:
                labels[i] = "OK"

        return labels

    def analyze(self, obj):
        order_list = self.rotation_order_list(obj)

        if not order_list:
            return {}

        try:
            scores = self.compute_all_scores(obj, order_list)
            percentages = [item["percentage"] for item in scores]
            labels = self.classify(percentages)
        except Exception:
            return {}

        return {
            order: {
                "percentage": percentages[i],
                "average": scores[i]["average"],
                "maximum": scores[i]["maximum"],
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
        # xform_target None = "Could not find Xform Target": switch without holding a pose.
        return (
            (self.xform_target is None or Maya.exists(self.xform_target))
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
        missing_target=False,
        enum_values=None,
    ):
        self.display_object = display_object
        self.attr_node = attr_node
        self.attr = attr
        self.values = values or []
        # Real enum values per option; the UI works in option positions.
        self.enum_values = list(enum_values) if enum_values else None
        self.current = self.position(float(current))
        self.attr_type = attr_type
        self.min_value = float(min_value)
        self.max_value = float(max_value)
        self.missing_target = bool(missing_target)
        self.xform_target = None if self.missing_target else (xform_target or display_object)
        self.source = source
        self.marked = [self.position(v) for v in marked] if marked else [self.current]
        self.gimbal = gimbal or {}
        self.matched = matched or []
        self.match_roles = match_roles or []

    def position(self, raw):
        if not self.enum_values:
            return raw
        value = int(round(raw))
        return float(self.enum_values.index(value)) if value in self.enum_values else raw

    def to_dict(self):
        return {
            "enum": self.values,
            "enum_values": self.enum_values,
            "marked": self.marked,
            "keyed_values": sorted(self.position(v) for v in Maya.keyed_values(self.attr_node, self.attr)),
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
            "missing_target": self.missing_target,
        }


class SwitchCatalogBuilder(object):
    ROTATE_ORDER_OPTIONS = ["xyz", "yzx", "zxy", "xzy", "yxz", "zyx"]

    def __init__(self, analyzer, show_rotate_order=True):
        self.analyzer = analyzer
        self.show_rotate_order = show_rotate_order
        self._target_cache = {}

    def clear_cache(self):
        self._target_cache.clear()

    def xform_targets_for(self, node, attr):
        """Cached detect_xform_targets (it walks the DG; rigs rarely rewire)."""
        key = (node, attr)
        cached = self._target_cache.get(key)
        if cached is not None and all(Maya.exists(t) for t in cached):
            return list(cached)
        result = self.detect_xform_targets(node, attr)
        self._target_cache[key] = list(result)
        return list(result)

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

    MAX_AUTO_TARGETS = 4

    @staticmethod
    def has_settable_xform(node):
        for channel in ("tx", "ty", "tz", "rx", "ry", "rz"):
            try:
                if cmds.getAttr("%s.%s" % (node, channel), settable=True):
                    return True
            except Exception:
                pass
        return False

    @staticmethod
    def _short(node):
        return (cmds.ls(node) or [node])[0]

    @classmethod
    def detect_xform_targets(cls, switch_node, attribute, max_nodes=256):
        """Find the transform(s) to keep in place when this attribute switches.

        animBot's rule of thumb: the xform target is usually the object that
        owns the switch. Otherwise follow the switch downstream to the
        transforms it drives (constraint weights, blend/choice nodes...):

        * it drives the switch owner itself or one of its parents
          (offset/space group above the control) -> the control itself;
        * it drives groups above other controls -> the nearest curve
          controls under them (several targets allowed, e.g. IK + pole).

        Ambiguous results fall back to the owner when it can move; an owner
        that can't move (locked settings node) returns [] -> "Could not find
        Xform Target", and the user is asked to set it up.
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

        owner_long = (cmds.ls(switch_node, long=True) or [switch_node])[0]
        owner_movable = cls.has_settable_xform(switch_node)
        candidates = []
        for transform in driven:
            transform_long = (cmds.ls(transform, long=True) or [transform])[0]
            if transform_long == owner_long or owner_long.startswith(transform_long + "|"):
                candidates.append(switch_node)
                continue
            controls = cls._controller_descendants(transform)
            candidates.extend(controls or [transform])
        candidates = [cls._short(c) for c in candidates]
        candidates = [c for c in dict.fromkeys(candidates) if cls.has_settable_xform(c)]
        if 1 <= len(candidates) <= cls.MAX_AUTO_TARGETS:
            return candidates
        return [switch_node] if owner_movable else []

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

                enum_values = None
                if is_enum:
                    items = Maya.enum_items(node, attr)
                    values = [label for label, _v in items]
                    enum_values = [v for _l, v in items]

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

                targets = [node] if attr == "rotateOrder" else self.xform_targets_for(node, attr)
                marked = Maya.keyed_values(node, attr, current)
                for xform_target in targets or [None]:
                    entry = SwitchEntry(
                        display_object=xform_target or node,
                        attr_node=node,
                        attr=attr,
                        values=values,
                        current=current,
                        attr_type=attr_type,
                        min_value=min_value,
                        max_value=max_value,
                        xform_target=xform_target,
                        source="local",
                        marked=marked,
                        gimbal=gimbal,
                        missing_target=xform_target is None,
                        enum_values=enum_values,
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

    @staticmethod
    def short_relative(node):
        """Node name without DAG path or namespace (stable across references)."""
        return (node or "").split("|")[-1].rpartition(":")[2]

    @staticmethod
    def namespace_of(node):
        return (node or "").split("|")[-1].rpartition(":")[0]

    @classmethod
    def asset_nodes(cls, namespace):
        """Every curve control in the asset namespace ("" = root namespace)."""
        pattern = "%s:*" % namespace if namespace else "*"
        curves = cmds.ls(pattern, type="nurbsCurve", long=True) or []
        parents = cmds.listRelatives(curves, parent=True, fullPath=True) or [] if curves else []
        # Rigs that tag joints/locators as controls (Maya "controller" nodes).
        for tag in cmds.ls(pattern, type="controller") or []:
            parents.extend(cmds.listConnections("%s.controllerObject" % tag,
                                                source=True, destination=False) or [])
        nodes = cmds.ls(list(dict.fromkeys(parents))) or []
        if not namespace:
            nodes = [n for n in nodes if ":" not in n.split("|")[-1]]
        return nodes

    def custom_entry(self, node, attr):
        """Entry for a user-registered attribute; skips the 'connected' filter."""
        if not Maya.exists(node) or not Maya.attr_exists(node, attr):
            return None
        attr_type = Maya.attr_type(node, attr)
        if not attr_type:
            return None
        is_enum = attr_type == "enum"
        if not is_enum and attr_type not in ("bool", "long", "short", "byte", "double", "float"):
            return None
        values, min_value, max_value, enum_values = [], 0.0, 0.0, None
        if is_enum:
            items = Maya.enum_items(node, attr)
            values = [label for label, _v in items]
            enum_values = [v for _l, v in items]
            if len(values) < 2:
                return None
            max_value = float(len(values) - 1)
        else:
            attr_range = Maya.numeric_range(node, attr, attr_type)
            if attr_range is None:
                return None
            min_value, max_value = attr_range
        current = Maya.get_float(node, attr)
        marked = Maya.keyed_values(node, attr, current)
        nice = Maya.nice_name(node, attr)
        results = []
        for xform_target in self.xform_targets_for(node, attr) or [None]:
            entry = SwitchEntry(
                display_object=xform_target or node,
                attr_node=node,
                attr=attr,
                values=values,
                current=current,
                attr_type=attr_type,
                min_value=min_value,
                max_value=max_value,
                xform_target=xform_target,
                source="custom",
                marked=marked,
                missing_target=xform_target is None,
                enum_values=enum_values,
            )
            results.append((attr, nice, entry))
        return results

    def custom_catalog(self, nodes, custom_keys):
        catalog = {}
        if not custom_keys:
            return catalog
        wanted = {}
        for key in custom_keys:
            rel_node, _, attr = key.rpartition(".")
            if rel_node and attr:
                wanted.setdefault(rel_node, []).append(attr)
        for node in nodes:
            for attr in wanted.get(self.short_relative(node), []):
                for result in self.custom_entry(node, attr) or []:
                    self.add_entry(catalog, *result)
        return catalog

    def asset_catalog(self, namespace, custom_keys):
        """One row per control/attribute for the whole asset (no rotate order)."""
        nodes = self.asset_nodes(namespace)
        custom_nodes = []
        for key in custom_keys or []:
            rel_node = key.rpartition(".")[0]
            full = "%s:%s" % (namespace, rel_node) if namespace else rel_node
            if Maya.exists(full):
                custom_nodes.append(full)
        previous = self.show_rotate_order
        self.show_rotate_order = False
        try:
            catalog = self.combined_catalog(nodes) if nodes else {}
        finally:
            self.show_rotate_order = previous
        self.merge_catalogs(catalog, self.custom_catalog(
            list(dict.fromkeys(nodes + custom_nodes)), custom_keys))

        rows = []
        for key, data in catalog.items():
            by_owner = OrderedDict()
            for obj, obj_data in data.get("objects", {}).items():
                by_owner.setdefault(obj_data.get("attr_node") or obj, OrderedDict())[obj] = obj_data
            for owner, objects in by_owner.items():
                first = next(iter(objects))
                rows.append(("%s@%s" % (key, owner),
                             {"objects": objects, "long": data.get("long", key)},
                             (first.split("|")[-1].rpartition(":")[2].lower(),
                              (data.get("long") or key).lower())))
        rows.sort(key=lambda row: row[2], reverse=True)  # rows are inserted at index 0
        return OrderedDict((key, data) for key, data, _ in rows)

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

def _cycle_modifier_held():
    """Alt/Option alone: Alt+Click cycles a row to its next value."""
    query_modifiers = getattr(
        QtGui.QGuiApplication, "queryKeyboardModifiers", None
    )
    if callable(query_modifiers):
        modifiers = query_modifiers()
    else:
        modifiers = QtWidgets.QApplication.keyboardModifiers()
    return bool(modifiers & QtCore.Qt.AltModifier) and not bool(
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

    def __init__(self, source_item, label_node, objects):
        self.enum_attr = source_item.enum_attr
        self.object_label = source_item.parent_dialog._format_object_name(
            [label_node]
        )
        self.attribute_label = source_item.attribute_label
        _populate_attribute_entry_state(self, objects)

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
    # animBot's first scope is the current frame, or every applicable key in a
    # highlighted Time Slider range.  It is deliberately not the Graph Editor
    # key selection (that would make the same menu item context-dependent in a
    # second, invisible way).
    CURRENT_KEYFRAMES = "Current Key(s)"

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
        if self.item_widget.enum_attr == "rotateOrder" and index < len(self.options):
            info = self.item_widget.gimbal_info.get(self.options[index], {})
            if info:
                btn.setToolTip(
                    "Animation Average Gimballed: %d%%\nAnimation Max Gimballed: %d%%"
                    % (int(info.get("average", 0)), int(info.get("maximum", 0))))
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
        self._cycle_hint = False
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

    def _update_cycle_hint(self):
        cursor_inside = self.rect().contains(
            self.mapFromGlobal(QtGui.QCursor.pos())
        )
        hint = cursor_inside and _cycle_modifier_held() and self._can_quick_cycle()
        if hint != self._cycle_hint:
            self._cycle_hint = hint
            self.update()

    def _can_quick_cycle(self):
        if self.is_enum:
            return len(self.options) > 1
        return self.max_val > self.min_val

    def _next_cycle_value(self):
        """Enums step to the next option (wrapping); numerics flip min/max."""
        if self.is_enum:
            return (int(self.current_idx) + 1) % len(self.options)
        midpoint = (self.min_val + self.max_val) / 2.0
        return self.min_val if self.current_idx >= midpoint else self.max_val

    def quick_cycle(self):
        if not self._can_quick_cycle():
            return
        dialog = self.parent_dialog
        if hasattr(dialog, "_close_active_popup"):
            dialog._close_active_popup()
        # Uses the panel's default scope (current frame / all keys / timeline range).
        self.on_select(self._next_cycle_value(), all_frames=dialog.all_frames)

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

        if self._cycle_hint:
            # Small cycle arrow just left of the pill: "Alt+Click = next value".
            size = util.DPI(9)
            pill = self.pill_container.geometry()
            arc = QtCore.QRectF(pill.left() - size - util.DPI(5),
                                pill.center().y() - size / 2.0, size, size)
            pen = QtGui.QPen(QtGui.QColor(COLOR_TEXT_MAIN), max(1.0, util.DPI(1.4)))
            pen.setCapStyle(QtCore.Qt.RoundCap)
            painter.setPen(pen)
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.drawArc(arc, 60 * 16, 280 * 16)
            tip = QtCore.QPointF(arc.right() - size * 0.12, arc.top() + size * 0.18)
            painter.drawLine(tip, tip + QtCore.QPointF(-size * 0.35, -size * 0.08))
            painter.drawLine(tip, tip + QtCore.QPointF(size * 0.02, size * 0.36))

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
        self._update_cycle_hint()
        QtWidgets.QWidget.mouseMoveEvent(self, event)

    def mousePressEvent(self, event):
        if (
            event.button() == QtCore.Qt.LeftButton
            and _cycle_modifier_held()
            and not self.multi_checkbox.isChecked()
        ):
            event.accept()
            # Defer: applying refreshes the panel and may rebuild this row.
            QtCore.QTimer.singleShot(0, self.quick_cycle)
            return
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
        self._cycle_hint = False
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

    def sync_current(self):
        """Refresh the shown value from objects_map without rebuilding the row."""
        _populate_attribute_entry_state(self, self.objects_map)
        if self.is_enum:
            if self.options:
                index = max(0, min(int(round(self.current_idx)), len(self.options) - 1))
                self.val_label.setText(self.options[index])
        else:
            self.val_label.setText("{:.2f}".format(self.current_idx))
            self._update_numeric_ball_pos()
        self._refresh_pill_style()
        self.update()

    def currentText(self):
        if not self.options:
            return ""
        return self.options[max(0, min(int(round(self.current_idx)), len(self.options) - 1))]


class MultiAttributeSwitchDialog(FloatingWidget):
    """Stage independent enum choices in a responsive column grid."""

    def __init__(self, parent_dialog, entries):
        FloatingWidget.__init__(self, popup=False, parent=parent_dialog)
        self.parent_dialog = parent_dialog
        self.entries = list(entries or [])
        self._selected_options = {}
        self._option_groups = []
        self._column_widgets = []
        self._columns_by_key = {}
        self._column_count = 0
        self._layout_order = ()
        self._all_frames = False
        self.setWindowTitle(_t("Switch Multiple Attributes"))
        self.setMinimumWidth(util.DPI(220))
        self._build_ui()

    def _build_ui(self):
        self._title = QtWidgets.QLabel(
            "Switch {} channels".format(len(self.entries)), self.mainContent
        )
        self._title.setStyleSheet(
            "color: {}; font-size: {}px; font-weight: bold;".format(
                COLOR_TEXT_SECONDARY, util.DPI(14)
            )
        )
        self.mainLayout.addWidget(self._title)

        self.mainLayout.addSpacing(util.DPI(10))
        self._add_scope_controls()
        self.mainLayout.addSpacing(util.DPI(10))
        self._columns_container = QtWidgets.QWidget(self.mainContent)
        self._columns_grid = QtWidgets.QGridLayout(self._columns_container)
        self._columns_grid.setContentsMargins(0, 0, 0, 0)
        self._columns_grid.setHorizontalSpacing(util.DPI(6))
        self._columns_grid.setVerticalSpacing(util.DPI(6))
        self._columns_scroll = QtWidgets.QScrollArea(self.mainContent)
        self._columns_scroll.setWidgetResizable(True)
        self._columns_scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self._columns_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self._columns_scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self._columns_scroll.setMinimumHeight(util.DPI(140))
        self._columns_scroll.setMaximumHeight(util.DPI(440))
        self._columns_scroll.setWidget(self._columns_container)
        self.mainLayout.addWidget(self._columns_scroll, 1)
        self.update_entries(self.entries)

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

    @staticmethod
    def _entry_key(entry):
        item, options_map = entry
        return (item.enum_attr,
                tuple(sorted((target, data.get("attr_node"), data.get("attr"))
                             for target, data in item.objects_map.items())),
                tuple(option for option in item.options if option in options_map))

    def _make_column(self, entry_key, item, options_map):
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

            group = QtWidgets.QButtonGroup(column)
            group.setExclusive(True)
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
                    button, self._choose_option, entry_key, option
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
            return column, group

    def update_entries(self, entries):
        """Diff staged columns in place; preserve choices and the open window."""
        entries = list(entries or [])
        keys = [self._entry_key(entry) for entry in entries]
        for key in list(self._columns_by_key):
            if key not in keys:
                column, _group = self._columns_by_key.pop(key)
                self._columns_grid.removeWidget(column)
                column.deleteLater()
                self._selected_options.pop(key, None)
        old_keys = set(self._columns_by_key)
        self.entries = entries
        for key, (item, options_map) in zip(keys, entries):
            if key not in old_keys:
                if item.enum_attr == "rotateOrder":
                    try:
                        item.gimbal_info = self.parent_dialog.analyze_group_gimbal(
                            item.objects_map)
                    except Exception as exc:
                        cmds.warning("Error analyzing staged rotate orders: {}".format(exc))
                        item.gimbal_info = {}
                self._columns_by_key[key] = self._make_column(key, item, options_map)
        self._column_widgets = [self._columns_by_key[key][0] for key in keys]
        self._option_groups = [self._columns_by_key[key][1] for key in keys]
        self._title.setText("Switch {} channels".format(len(entries)))
        if getattr(self, "_apply_button", None) is not None:
            self._apply_button.setEnabled(bool(self._selected_options))
        self._layout_columns()

    def _layout_columns(self):
        available_width = max(util.DPI(165), self.width() - util.DPI(56))
        column_step = util.DPI(171)
        columns_per_row = max(1, min(len(self._column_widgets),
                                      available_width // column_step))
        order = tuple(id(column) for column in self._column_widgets)
        if (columns_per_row == self._column_count and order == self._layout_order
                and self._columns_grid.count() == len(self._column_widgets)):
            return
        self._column_count = columns_per_row
        self._layout_order = order
        while self._columns_grid.count():
            self._columns_grid.takeAt(0)
        for index, column in enumerate(self._column_widgets):
            self._columns_grid.addWidget(
                column,
                index // columns_per_row,
                index % columns_per_row,
            )

    def _choose_scope(self, checked, all_frames):
        if checked:
            self._all_frames = all_frames

    def _choose_option(self, checked, entry_key, option):
        if not checked:
            return
        self._selected_options[entry_key] = option
        if self._apply_button is not None:
            self._apply_button.setEnabled(True)

    def _apply(self):
        if not self._selected_options:
            return
        staged_entries = [(item, options_map, self._selected_options[key])
                          for item, options_map in self.entries
                          for key in [self._entry_key((item, options_map))]
                          if key in self._selected_options]
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
        desired_width = min(screen.availableGeometry().width() - util.DPI(40),
                            util.DPI(40 + 171 * min(len(self.entries), 4))) if screen else util.DPI(400)
        self.resize(max(self.minimumWidth(), desired_width), self.height())
        self._layout_columns()
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

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_columns_grid"):
            self._layout_columns()

class _TargetRow(QWidget):
    """One xform target, styled like the switch rows. Hover shows the remove X."""

    def __init__(self, name, on_remove, on_isolate, parent=None):
        QWidget.__init__(self, parent)
        self.name = name
        self._on_remove = on_remove
        self._on_isolate = on_isolate
        self._hover = False
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(util.DPI(24))
        self.setToolTip("%s<br><br>Click: keep only this target<br>X: remove it" % name)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(util.DPI(8), 0, util.DPI(4), 0)
        layout.setSpacing(util.DPI(4))

        short = name.split("|")[-1]
        namespace, _, base = short.rpartition(":")
        self.label = QLabel(
            ('<span style="color:%s">%s:</span>%s' % (COLOR_ACCENT_DARK, namespace, base))
            if namespace else base)
        self.label.setStyleSheet("color: %s; font-size: %spx; background: transparent;"
                                 % (COLOR_TEXT_MAIN, util.DPI(11)))
        self.label.setAttribute(Qt.WA_TransparentForMouseEvents)

        self.remove_btn = QPushButton(u"✕")
        self.remove_btn.setFixedSize(util.DPI(18), util.DPI(18))
        self.remove_btn.setFocusPolicy(Qt.NoFocus)
        self.remove_btn.setCursor(Qt.PointingHandCursor)
        self.remove_btn.setToolTip(_t("Remove this Xform Target"))
        self.remove_btn.setStyleSheet(
            "QPushButton{background:transparent;border:none;color:%s;font-size:%spx;}"
            "QPushButton:hover{color:#000000;}" % (COLOR_ACCENT_DARK, util.DPI(11)))
        policy = self.remove_btn.sizePolicy()
        policy.setRetainSizeWhenHidden(True)
        self.remove_btn.setSizePolicy(policy)
        self.remove_btn.setVisible(False)
        self.remove_btn.clicked.connect(lambda *a: self._on_remove(self.name))

        layout.addWidget(self.label, 1)
        layout.addWidget(self.remove_btn)

    def enterEvent(self, event):
        self._hover = True
        self.remove_btn.setVisible(True)
        self.update()
        QWidget.enterEvent(self, event)

    def leaveEvent(self, event):
        self._hover = False
        self.remove_btn.setVisible(False)
        self.update()
        QWidget.leaveEvent(self, event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.rect().contains(event.pos()):
            self._on_isolate(self.name)
        QWidget.mouseReleaseEvent(self, event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(COLOR_ACCENT_WHITE if self._hover else COLOR_ACCENT_MAIN))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5),
                                util.DPI(3), util.DPI(3))


class SetupTargetsDialog(FloatingWidget):
    """animBot-style Xform Target setup, driven by the Maya selection.

    Current targets get selected; whatever transforms you select become the
    xform targets of this switch, live. Finish (Enter) or deselect everything
    to keep them; Cancel (Esc) keeps the old ones.
    """

    HELP = ("Xform targets are the transforms kept in place when this attribute "
            "switches. Usually it's the control that owns the switch; if your rig "
            "moves a different control (or several), select those instead.")
    MAX_VISIBLE_ROWS = 8
    WIDTH = 270

    def __init__(self, parent, objects_dict, on_close, switch_label=""):
        FloatingWidget.__init__(self, popup=False, parent=parent)

        self.on_close = on_close
        self.objects_dict = objects_dict
        self.switch_label = switch_label
        self._result = None
        self._finished = False
        self._targets = [t for t, d in objects_dict.items()
                         if not d.get("missing_target") and Maya.exists(t)]
        self._initial_targets = list(self._targets)
        self._rows = OrderedDict()
        self._callbacks = CallbackManager()

        self._selection_timer = QTimer(self)
        self._selection_timer.setSingleShot(True)
        self._selection_timer.setInterval(30)  # coalesce marquee / outliner bursts
        self._selection_timer.timeout.connect(self._on_selection_changed)

        if parent and hasattr(parent, "_suspend_auto_close"):
            parent._suspend_auto_close()

        self._create_layouts()
        self.setBottomBar(
            [
                base_widgets.QFlatDialogButton(
                    "Finish", callback=self.finish,
                    icon=util.return_icon_path("apply"), highlight=True,
                ),
                base_widgets.QFlatDialogButton(
                    "Cancel", callback=self.cancel,
                    icon=util.return_icon_path("cancel"),
                ),
            ],
            closeButton=False,
            spacing=util.DPI(2),
        )
        self.setFixedWidth(util.DPI(self.WIDTH))

        if self._targets:
            cmds.select(self._targets, replace=True)
        else:
            cmds.select(clear=True)
        self._sync_rows(invalid=0)
        self._callbacks.add(om.MEventMessage.addEventCallback(
            "SelectionChanged", lambda *a: self._selection_timer.start()))

    # --- layout ---------------------------------------------------------------
    def _create_layouts(self):
        self.mainLayout.setContentsMargins(util.DPI(10), util.DPI(10), util.DPI(10), util.DPI(6))
        self.mainLayout.setSpacing(util.DPI(6))

        header = QHBoxLayout()
        header.setSpacing(util.DPI(6))
        icon = QLabel()
        size = util.DPI(20)
        icon.setFixedSize(size, size)
        icon.setPixmap(QIcon(util.return_icon_path("spaceswitch.svg")).pixmap(size, size))
        title = QLabel(_t("Xform Targets"))
        title.setStyleSheet("font-size: %spx; font-weight: bold; color: %s; background: transparent;"
                            % (util.DPI(15), COLOR_TEXT_SECONDARY))
        self.help_button = QPushButton("?")
        self.help_button.setCheckable(True)
        self.help_button.setFixedSize(util.DPI(18), util.DPI(18))
        self.help_button.setCursor(Qt.PointingHandCursor)
        self.help_button.setFocusPolicy(Qt.NoFocus)
        self.help_button.setToolTip(_t("What is a Xform Target?"))
        self.help_button.setStyleSheet(
            "QPushButton{border:1px solid %s;border-radius:%spx;color:%s;background:transparent;}"
            "QPushButton:hover,QPushButton:checked{border-color:%s;color:%s;}"
            % (COLOR_TEXT_SECONDARY, util.DPI(9), COLOR_TEXT_SECONDARY, COLOR_ACCENT_LIGHT, COLOR_ACCENT_LIGHT))
        header.addWidget(icon)
        header.addWidget(title, 1)
        header.addWidget(self.help_button)

        switch_name = QLabel(self.switch_label or "")
        switch_name.setStyleSheet(
            "color: %s; background: %s; border-radius: %spx; padding: %spx %spx; font-size: %spx;"
            % (COLOR_ACCENT_WHITE, COLOR_BLEND_MULTI, util.DPI(3), util.DPI(3), util.DPI(6), util.DPI(11)))
        switch_name.setVisible(bool(self.switch_label))

        self.help_label = QLabel(_t(self.HELP))
        self.help_label.setWordWrap(True)
        self.help_label.setStyleSheet("color: %s; font-size: %spx; background: transparent;"
                                      % (COLOR_TEXT_SECONDARY, util.DPI(10)))
        self.help_label.setVisible(False)
        self.help_button.toggled.connect(self._toggle_help)

        self.count_label = QLabel()
        self.count_label.setStyleSheet("color: %s; font-size: %spx; background: transparent;"
                                       % (COLOR_TEXT_SECONDARY, util.DPI(11)))

        self.rows_container = QWidget()
        self.rows_layout = QVBoxLayout(self.rows_container)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(util.DPI(2))
        self.rows_scroll = QtWidgets.QScrollArea()
        self.rows_scroll.setWidget(self.rows_container)
        self.rows_scroll.setWidgetResizable(True)
        self.rows_scroll.setFrameShape(QFrame.NoFrame)
        self.rows_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.rows_scroll.setStyleSheet(
            "QScrollArea{background:transparent;border:none;}"
            "QScrollArea > QWidget > QWidget{background:transparent;}")

        self.empty_label = QLabel(_t("Select the control(s) to keep in place when switching."))
        self.empty_label.setWordWrap(True)
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setStyleSheet(
            "color: %s; border: 1px dashed %s; border-radius: %spx; padding: %spx; background: transparent;"
            % (COLOR_TEXT_SECONDARY, "#555555", util.DPI(4), util.DPI(10)))

        self.note_label = QLabel()
        self.note_label.setWordWrap(True)
        self.note_label.setStyleSheet("color: #e0b060; font-size: %spx; background: transparent;" % util.DPI(10))
        self.note_label.setVisible(False)

        hint = QLabel(_t("Enter / deselect all: finish  ·  Esc: cancel"))
        hint.setStyleSheet("color: #808080; font-size: %spx; background: transparent;" % util.DPI(10))

        self.mainLayout.addLayout(header)
        self.mainLayout.addWidget(switch_name)
        self.mainLayout.addWidget(self.help_label)
        self.mainLayout.addWidget(self.count_label)
        self.mainLayout.addWidget(self.rows_scroll)
        self.mainLayout.addWidget(self.empty_label)
        self.mainLayout.addWidget(self.note_label)
        self.mainLayout.addWidget(hint)

    def _toggle_help(self, checked):
        self.help_label.setVisible(checked)
        self._fit_height()

    # --- live selection ------------------------------------------------------
    @staticmethod
    def _split_targets(nodes):
        valid, invalid = [], 0
        for node in nodes:
            if SwitchCatalogBuilder._is_transform(node) and SwitchCatalogBuilder.has_settable_xform(node):
                valid.append(node)
            else:
                invalid += 1
        return valid, invalid

    def _on_selection_changed(self):
        if self._finished or not util.is_valid_widget(self):
            return
        selection = Maya.selection(long=False)
        valid, invalid = self._split_targets(selection)
        if not selection:
            if self._targets:
                self.finish()  # deselecting all finishes the setup (last targets kept)
            return
        if valid != self._targets:
            self._targets = valid
        self._sync_rows(invalid)

    def _remove_target(self, name):
        if Maya.exists(name):
            cmds.select(name, deselect=True)

    def _isolate_target(self, name):
        if Maya.exists(name):
            cmds.select(name, replace=True)

    def _sync_rows(self, invalid):
        """Diff the row widgets against the targets: no full rebuild, no flicker."""
        self.rows_container.setUpdatesEnabled(False)
        try:
            for name in [n for n in self._rows if n not in self._targets]:
                row = self._rows.pop(name)
                self.rows_layout.removeWidget(row)
                row.deleteLater()
            for index, name in enumerate(self._targets):
                row = self._rows.get(name)
                if row is None:
                    row = _TargetRow(name, self._remove_target, self._isolate_target, self.rows_container)
                    self._rows[name] = row
                if self.rows_layout.indexOf(row) != index:
                    self.rows_layout.removeWidget(row)
                    self.rows_layout.insertWidget(index, row)
        finally:
            self.rows_container.setUpdatesEnabled(True)

        count = len(self._targets)
        self.count_label.setText(_t("%d object%s as Xform Target%s of this Switch") % (
            count, "" if count == 1 else "s", "" if count == 1 else "s"))
        self.rows_scroll.setVisible(bool(count))
        self.empty_label.setVisible(not count)
        self.note_label.setVisible(bool(invalid))
        if invalid:
            self.note_label.setText(_t("%d selected object%s can't be a xform target "
                                       "(not a transform, or translate/rotate locked).")
                                    % (invalid, "" if invalid == 1 else "s"))
        self._fit_height()

    def _fit_height(self):
        """Grow with the list up to MAX_VISIBLE_ROWS, then scroll; keep the top edge."""
        rows = len(self._targets)
        row_h = util.DPI(24) + self.rows_layout.spacing()
        self.rows_scroll.setFixedHeight(max(1, min(rows, self.MAX_VISIBLE_ROWS)) * row_h)
        top_left = self.pos()
        self.mainLayout.activate()
        self.root_layout.activate()
        self.adjustSize()
        if self.isVisible():
            self.move(top_left)

    # --- keys / closing --------------------------------------------------------
    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.finish()
            return
        if event.key() == Qt.Key_Escape:
            self.cancel()
            return
        FloatingWidget.keyPressEvent(self, event)

    def reject(self):  # QDialog's own Esc path would skip our cleanup
        self.cancel()

    def finish(self):
        self._result = list(self._targets) or None
        self.close()

    def cancel(self):
        self._result = None
        self.close()

    def closeEvent(self, event):
        if not self._finished:
            self._finished = True
            self._selection_timer.stop()
            self._callbacks.clear()
            changed = self._result is not None and self._result != self._initial_targets
            if changed:
                original_values = list(self.objects_dict.values())
                fallback = original_values[0] if original_values else {}
                new_dict = OrderedDict()
                for target in self._result:
                    new_dict[target] = dict(self.objects_dict.get(target, fallback))
                    new_dict[target]["xform_target"] = target
                    new_dict[target]["missing_target"] = False
                self.objects_dict.clear()
                self.objects_dict.update(new_dict)
            try:
                cmds.inViewMessage(
                    amg=_t("Xform Target Setup Complete") if changed else _t("Xform Target Setup Skipped"),
                    pos="midCenterTop", fade=True)
            except Exception:
                pass
            if callable(self.on_close):
                self.on_close(list(self._result) if changed else None)
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
            # In mayapy/standalone the UI global has never been declared.
            # An explicit global declaration reads it quietly as an empty
            # string while still finding the real slider in graphical Maya.
            timeline = mel.eval("global string $gPlayBackSlider; $tmpVar=$gPlayBackSlider;")
            if not timeline:
                return None
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


class OperationCancelled(Exception):
    """Raised inside a switch when Esc / the progress bar cancel is pressed."""

    def __init__(self, wrote=False):
        Exception.__init__(self, "SpaceSwitch cancelled")
        self.wrote = wrote


class PoseCompensationError(RuntimeError):
    """The requested space cannot preserve a target's evaluated world pose."""


class _MainThreadMarshal(QtCore.QObject):
    """Run a callable on Maya's main thread and block the calling worker.

    maya.cmds is not thread-safe: every scene read/write hops back here.
    Created lazily from the main thread, so its thread affinity is correct.
    """

    _request = QtCore.Signal(object)

    def __init__(self):
        QtCore.QObject.__init__(self)
        self._request.connect(self._run, QtCore.Qt.QueuedConnection)

    def _run(self, job):
        fn, args, kwargs, event, box = job
        try:
            box["value"] = fn(*args, **kwargs)
        except BaseException as exc:  # re-raised on the worker
            box["error"] = exc
            box["trace"] = traceback.format_exc()
        finally:
            event.set()

    def call(self, fn, *args, **kwargs):
        if QtCore.QThread.currentThread() == self.thread():
            return fn(*args, **kwargs)
        event = threading.Event()
        box = {}
        self._request.emit((fn, args, kwargs, event, box))
        event.wait()
        if "error" in box:
            if not isinstance(box["error"], OperationCancelled):
                print(box.get("trace", ""))
            raise box["error"]
        return box.get("value")


_MARSHAL = []


def _main_thread_marshal():
    if not _MARSHAL:
        _MARSHAL.append(_MainThreadMarshal())
    return _MARSHAL[0]


class _CoordinatorThread(QtCore.QThread):
    def __init__(self, fn):
        QtCore.QThread.__init__(self)
        self._fn = fn
        self.outcome = {}

    def run(self):
        try:
            self.outcome["value"] = self._fn()
        except BaseException as exc:
            self.outcome["error"] = exc


class _InputBlocker(QtCore.QObject):
    """While a switch runs: Esc cancels, all other user input is swallowed.

    The main event loop stays alive (painting, progress, cancel) but nobody can
    scrub, select or edit the scene in the middle of a multi-frame write.
    """

    BLOCKED = (
        QtCore.QEvent.KeyPress, QtCore.QEvent.KeyRelease,
        QtCore.QEvent.MouseButtonPress, QtCore.QEvent.MouseButtonRelease,
        QtCore.QEvent.MouseButtonDblClick, QtCore.QEvent.Wheel,
        QtCore.QEvent.ShortcutOverride,
    )

    def __init__(self, runner):
        QtCore.QObject.__init__(self)
        self._runner = runner

    def eventFilter(self, watched, event):
        etype = event.type()
        if etype not in self.BLOCKED:
            return False
        if etype == QtCore.QEvent.KeyPress and event.key() == QtCore.Qt.Key_Escape:
            self._runner.cancel()
        return True


class OperationRunner(object):
    """TKM-style cooperative operation: coordinator on a worker, Maya on main.

    Small jobs run inline (thread start + marshalling costs more than it saves).
    Larger ones run their coordinator on a QThread while a local QEventLoop
    keeps Maya responsive, so Esc is seen immediately, not between batches.
    """

    INLINE_MAX_STEPS = 8
    SHOW_AFTER_MS = 300
    POLL_MS = 50

    def __init__(self, status="SpaceSwitch"):
        self.status = status
        self.total = 0
        self.done = 0
        self._cancelled = False
        self._bar = None
        self.threaded = False
        self.wrote = False

    # --- called from the coordinator ------------------------------------------
    def main(self, fn, *args, **kwargs):
        return _main_thread_marshal().call(fn, *args, **kwargs)

    def set_total(self, total):
        self.total = max(0, int(total))

    def step(self, status=None):
        self.done += 1
        if status:
            self.status = status
        return self._cancelled

    @property
    def cancelled(self):
        return self._cancelled

    def cancel(self):
        self._cancelled = True

    def check(self, wrote=None):
        if self._cancelled:
            raise OperationCancelled(self.wrote if wrote is None else wrote)

    # --- main thread ----------------------------------------------------------
    def _start_bar(self):
        if self._bar is not None:
            return
        try:
            self._bar = mel.eval("$tmp = $gMainProgressBar")
            cmds.progressBar(self._bar, edit=True, beginProgress=True, isInterruptable=True,
                             status="%s  (Esc to cancel)" % self.status,
                             maxValue=max(1, self.total))
        except Exception:
            self._bar = None

    def _poll(self):
        if self._bar is None:
            return
        try:
            cmds.progressBar(self._bar, edit=True, progress=min(self.done, max(1, self.total)),
                             maxValue=max(1, self.total), status="%s  (Esc to cancel)" % self.status)
            if cmds.progressBar(self._bar, query=True, isCancelled=True):
                self._cancelled = True
        except Exception:
            pass

    def _end_bar(self):
        if self._bar is not None:
            try:
                cmds.progressBar(self._bar, edit=True, endProgress=True)
            except Exception:
                pass
        self._bar = None

    def run(self, coordinator, estimated_steps):
        """Run coordinator(runner); returns its value or raises its exception."""
        if estimated_steps < self.INLINE_MAX_STEPS:
            return coordinator(self)

        self.threaded = True
        app = QtCore.QCoreApplication.instance()
        blocker = _InputBlocker(self)
        loop = QtCore.QEventLoop()
        worker = _CoordinatorThread(lambda: coordinator(self))
        worker.finished.connect(loop.quit)
        show_timer = QtCore.QTimer()
        show_timer.setSingleShot(True)
        show_timer.timeout.connect(self._start_bar)
        poll_timer = QtCore.QTimer()
        poll_timer.setInterval(self.POLL_MS)
        poll_timer.timeout.connect(self._poll)

        _main_thread_marshal()  # make sure it is created on this (main) thread
        if app is not None:
            app.installEventFilter(blocker)
        try:
            show_timer.start(self.SHOW_AFTER_MS)
            poll_timer.start()
            worker.start()
            if worker.isRunning():
                run_loop = getattr(loop, "exec") if PYSIDE_VERSION == 6 else loop.exec_
                run_loop()
            worker.wait()
        finally:
            show_timer.stop()
            poll_timer.stop()
            if app is not None:
                app.removeEventFilter(blocker)
            self._end_bar()

        if "error" in worker.outcome:
            raise worker.outcome["error"]
        return worker.outcome.get("value")


class SwitchExecutor(object):
    ROTATE_AXES = ("rotateX", "rotateY", "rotateZ")
    CHANNELS = ("translateX", "translateY", "translateZ",
                "rotateX", "rotateY", "rotateZ",
                "scaleX", "scaleY", "scaleZ")
    EPSILON = 1e-5

    def __init__(self, owner):
        self.owner = owner
        self.issues = []  # human-readable skipped/partial results of the last run

    @classmethod
    def transform_key_times(cls, node):
        """Key times animBot considers for a pose-preserving space switch.

        Scale curves do not define switch samples in the reference tool; the
        evaluated world matrix at translation/rotation and switch keys already
        contains scale, while sampling scale-only keys creates surprising extra
        switch keys.
        """
        if not node or not Maya.exists(node):
            return set()
        times = set()
        for channel in cls.CHANNELS[:6]:
            times.update(Maya.key_times_for_plug(Maya.plug(node, channel)))
        return times

    # --- frame selection ------------------------------------------------------
    @staticmethod
    def selected_key_times(operations):
        """Key times selected in the Graph Editor/Dope Sheet on the involved nodes."""
        nodes = []
        for operation in operations:
            nodes.extend([operation.xform_target, operation.attr_node])
        nodes = [n for n in dict.fromkeys(nodes) if Maya.exists(n)]
        if not nodes:
            return []
        times = cmds.keyframe(nodes, query=True, selected=True, timeChange=True) or []
        return sorted(set(times))

    def collect_frames(self, operations, all_frames, timeline_selection, current_frames):
        current_time = cmds.currentTime(query=True)
        if not all_frames and not timeline_selection:
            return [current_time]
        frames = set()
        for operation in operations:
            frames.update(self.transform_key_times(operation.xform_target))
            frames.update(Maya.key_times_for_plug(operation.plug))
        if timeline_selection:
            start, end = current_frames
            frames = {frame for frame in frames if start <= frame < end}
            if not frames:  # empty range: switch where the user is looking
                return [current_time if start <= current_time < end else start]
            return sorted(frames)
        return sorted(frames) or [current_time]

    @staticmethod
    def _value_at(plug, frame):
        try:
            return float(cmds.getAttr(plug, time=frame))
        except Exception:
            return None

    @staticmethod
    def guard_frames(frames, target_times, switch_times):
        """Neighbouring keys that must keep the OLD space after a partial switch.

        Keying the switch on a subset of frames would otherwise hold the new
        value until the next switch key and pop every later (and, for a first
        switch key, every earlier) pose. Step guard keys restore the original
        value on the nearest unswitched key on each side.
        """
        frames = set(frames)
        switch_times = set(switch_times)
        ordered = sorted(set(target_times) | switch_times)
        guards = set()
        lowest = min(frames)
        if not any(t < lowest for t in switch_times):
            before = [t for t in target_times if t < lowest]
            if before:
                guards.add(max(before))
        for frame in frames:
            following_switches = [t for t in switch_times if t > frame]
            if following_switches:
                # Existing switch boundaries take precedence over transform
                # samples introduced by earlier trajectory compensation.
                guards.add(min(following_switches))
                continue
            index = bisect.bisect_right(ordered, frame)
            if index < len(ordered) and ordered[index] not in frames:
                guards.add(ordered[index])
        return sorted(guards - switch_times - frames)

    # --- fast rotate order (pure curve math, no time changes) -----------------
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

    # --- planning (main thread) -----------------------------------------------
    def _plan(self, requests, timeline_selection, selected_range):
        """One job per switch plug; a plug can hold several xform targets."""
        groups = OrderedDict()
        for operations, all_frames in requests:
            for operation in operations:
                if not operation.is_valid():
                    continue
                group = groups.get(operation.plug)
                if group is None:
                    group = groups[operation.plug] = {"ops": [], "value": operation.value,
                                                      "all_frames": False}
                elif group["value"] != operation.value:
                    raise ValueError("Conflicting choices for {}".format(operation.plug))
                group["all_frames"] = group["all_frames"] or bool(all_frames)
                if not any(o.xform_target == operation.xform_target for o in group["ops"]):
                    group["ops"].append(operation)

        jobs, fast = [], []
        self.issues = []
        for plug, group in groups.items():
            ops, operation, all_frames = group["ops"], group["ops"][0], group["all_frames"]
            try:
                settable = cmds.getAttr(plug, settable=True)
            except Exception:
                settable = False
            if not settable:
                self.issues.append("%s is locked or driven, not switched" % plug)
                continue
            if (len(ops) == 1 and self.owner.fast_rotation_order and not timeline_selection
                    and self._rotate_order_fast_eligible(operation)):
                if int(cmds.getAttr(operation.plug)) != int(operation.value):
                    fast.append(self._prepare_rotation(operation))
                continue

            switch_times = Maya.key_times_for_plug(plug)
            target_times = set()
            for op in ops:
                if op.xform_target:
                    target_times |= self.transform_key_times(op.xform_target)
            frames = self.collect_frames(
                ops, all_frames, timeline_selection, selected_range)
            # Anything animated is keyed, so the rest of the shot never pops.
            keyed = bool(all_frames or timeline_selection or switch_times or target_times)
            target_value = float(operation.value)
            pending = []
            for frame in frames:
                current = self._value_at(operation.plug, frame)
                if current is None or abs(current - target_value) > self.EPSILON:
                    pending.append(frame)
            frames = pending
            if not frames:
                continue  # already in that space everywhere asked: nothing to do
            guards = {}
            if keyed and not all_frames:
                for frame in self.guard_frames(frames, target_times, switch_times):
                    value = self._value_at(operation.plug, frame)
                    if value is not None and abs(value - target_value) > self.EPSILON:
                        guards[frame] = value
                if timeline_selection:
                    # A selected timeline range is half-open. Restore the old
                    # space at its end rather than holding the new space to
                    # the next distant transform key outside the selection.
                    boundary = float(selected_range[1])
                    if boundary > max(frames):
                        value = self._value_at(operation.plug, boundary)
                        if value is not None and abs(value - target_value) > self.EPSILON:
                            guards[boundary] = value
            jobs.append({"op": operation, "ops": ops, "frames": frames,
                         "keyed": keyed, "guards": guards,
                         "all_frames": all_frames})
        return jobs, fast

    def _key_frames_for_job(self, job, timeline_selection, selected_range):
        """Compensate on existing control keys around the requested switch.

        One set of authored key times is captured once and then applied once.
        No interpolated frames, sampling grid or off-key correction keys.
        """
        frames = set(job["frames"])
        if not job["keyed"]:
            return frames
        original = set(job["guards"])
        switch_times = Maya.key_times_for_plug(job["op"].plug)
        original.update(switch_times)
        for op in job["ops"]:
            if op.xform_target:
                original.update(self.transform_key_times(op.xform_target))
        if not original:
            return frames
        if job["all_frames"]:
            return frames | original
        low, high = min(frames), max(frames)
        if timeline_selection:
            low, high = float(selected_range[0]), float(selected_range[1])
        previous = [time for time in original if time < low]
        following = [time for time in original if time > high]
        first = max(previous) if previous else low
        last = min(following) if following else high
        earlier_switches = [time for time in switch_times if time < low]
        later_switches = [time for time in switch_times if time > high]
        if earlier_switches:
            first = min(first, max(earlier_switches))
        if later_switches:
            last = max(last, min(later_switches))
        return frames | {time for time in original if first <= time <= last}

    # --- writing (main thread, one call per step) ------------------------------
    @staticmethod
    def _capture(frame, targets):
        # World-matrix getAttr(time=...) can evaluate against a different DG
        # context from xform at the *current* frame after repeated key edits.
        # Evaluate the whole scene at the sample, as the reference's temporary
        # duplicate/constraint workflow does, then read the actual DAG matrix.
        cmds.currentTime(frame, update=True)
        return {target: cmds.xform(target, query=True, worldSpace=True, matrix=True)
                for target in targets}

    def _begin_write(self, schedule, targets):
        ctx = {
            "current_time": cmds.currentTime(query=True),
            "auto_key": cmds.autoKeyframe(query=True, state=True),
            "marker": None,
            "depth": {},
            "channels": {},
            "linear_channels": {},
            "warned": set(),
        }
        for target in targets:
            paths = cmds.ls(target, long=True) or [target]
            ctx["depth"][target] = paths[0].count("|")
            settable, animated, locked = [], set(), []
            for channel in self.CHANNELS:
                plug = Maya.plug(target, channel)
                try:
                    if cmds.getAttr(plug, settable=True):
                        settable.append(channel)
                    else:
                        sources = cmds.listConnections(plug, source=True, destination=False,
                                                       skipConversionNodes=True) or []
                        if any(cmds.nodeType(n).startswith("animBlendNode") for n in sources):
                            # A layer's blend-node connection makes getAttr
                            # report non-settable on some Maya/rig versions,
                            # although the active layer can still be keyed.
                            if not cmds.getAttr(plug, lock=True):
                                settable.append(channel)
                        elif channel not in self.CHANNELS[6:]:
                            locked.append(channel)
                except Exception:
                    continue
                if Maya.key_times_for_plug(plug):
                    animated.add(channel)
            ctx["channels"][target] = (settable, animated)
            linear = set()
            for channel in animated:
                plug = Maya.plug(target, channel)
                try:
                    incoming = cmds.keyTangent(plug, query=True, inTangentType=True) or []
                    outgoing = cmds.keyTangent(plug, query=True, outTangentType=True) or []
                    if incoming and outgoing and all(kind == "linear" for kind in
                                                     incoming + outgoing):
                        linear.add(channel)
                except RuntimeError:
                    pass
            ctx["linear_channels"][target] = linear
            # Maya can key selected animation layers even when a blend node
            # makes getAttr(settable=True) false. Successful compensation is
            # checked against the evaluated matrix; key writes are checked
            # separately below. Merely finding a blend node is not a failure.
            if locked and len(locked) < 6:
                self.issues.append("%s: %s locked/driven, pose may not match exactly"
                                   % (target, ", ".join(locked)))
        cmds.autoKeyframe(state=False)
        return ctx

    @staticmethod
    def _write_switches(jobs, fast, executor):
        for job in jobs:
            operation = job["op"]
            if job["keyed"]:
                changed_times = sorted(set(job["frames"]) | set(job["guards"]))
                for frame in job["frames"]:
                    cmds.setKeyframe(operation.plug, time=(frame, frame), value=operation.value,
                                     outTangentType="step")
                for frame, value in job["guards"].items():
                    cmds.setKeyframe(operation.plug, time=(frame, frame), value=value,
                                     outTangentType="step")
                # Maya may quietly refuse to key a channel that is editable but
                # driven by a non-curve source or an inactive animation layer.
                # Detect that before compensating any transforms; the UI can
                # then undo the entire operation as one transaction.
                written = {**{t: float(operation.value) for t in job["frames"]},
                           **job["guards"]}
                actual_times = Maya.key_times_for_plug(operation.plug)
                for frame, value in written.items():
                    evaluated = SwitchExecutor._value_at(operation.plug, frame)
                    if (frame not in actual_times or evaluated is None
                            or abs(evaluated - value) > SwitchExecutor.EPSILON):
                        raise PoseCompensationError(
                            "%s could not be keyed to %s at frame %s"
                            % (operation.plug, value, frame))
                # Maya's default tangent on a pre-existing numeric key can be
                # spline/auto. A stepped outgoing tangent on the NEW switch key
                # alone would interpolate the preceding space into this one.
                # Turn the segment before each written switch/guard into a hold.
                keyed_times = sorted(Maya.key_times_for_plug(operation.plug))
                for frame in changed_times:
                    index = bisect.bisect_left(keyed_times, frame)
                    if index:
                        previous = keyed_times[index - 1]
                        cmds.keyTangent(operation.plug, edit=True,
                                        time=(previous, previous), outTangentType="step")
            else:
                cmds.setAttr(operation.plug, operation.value)
        for prepared in fast:
            executor._apply_rotation(prepared)

    def _channel_values(self, target):
        values = {}
        for compound, axes in (("translate", self.CHANNELS[0:3]),
                               ("rotate", self.CHANNELS[3:6]),
                               ("scale", self.CHANNELS[6:9])):
            try:
                values.update(zip(axes, cmds.getAttr("%s.%s" % (target, compound))[0]))
            except Exception:
                pass
        return values

    def _compensate_frame(self, frame, targets, snapshot, ctx):
        # The space attribute was just keyed at this frame. A no-update time
        # change leaves DG-driven offset groups with stale world matrices,
        # so xform(ws=True) computes the compensation in the previous space.
        cmds.currentTime(frame, update=True)
        for target in sorted(targets, key=lambda t: ctx["depth"].get(t, 0)):
            settable, animated = ctx["channels"][target]
            before = self._channel_values(target)
            pose_error = None
            try:
                Maya.set_matrix(target, snapshot[target])
            except RuntimeError as exc:
                pose_error = exc
            try:
                result_matrix = Maya.matrix(target)
            except RuntimeError as exc:
                pose_error = exc
                result_matrix = None
            if result_matrix is None or any(
                abs(actual - desired) > self.EPSILON
                for actual, desired in zip(result_matrix, snapshot[target])
            ):
                raise PoseCompensationError(
                    "%s at frame %s could not preserve its world transform%s"
                    % (target, frame, ": %s" % pose_error if pose_error else
                       " (locked, connected or constrained channels)")
                )
            after = self._channel_values(target)
            may_key = targets[target] or ctx["auto_key"]
            # Animated channels always get a key (pose locked at the switch);
            # static ones only when compensation actually moved them.
            to_key = [channel for channel in settable
                      if channel in animated
                      or (may_key and abs(after.get(channel, 0.0) - before.get(channel, 0.0)) > self.EPSILON)]
            if to_key:
                cmds.setKeyframe(target, attribute=to_key, time=(frame, frame))
                for channel in to_key:
                    plug = Maya.plug(target, channel)
                    if frame not in Maya.key_times_for_plug(plug):
                        raise PoseCompensationError(
                            "%s could not key compensated pose at frame %s"
                            % (plug, frame))
                    if channel in ctx["linear_channels"][target]:
                        cmds.keyTangent(plug, edit=True, time=(frame, frame),
                                        inTangentType="linear", outTangentType="linear")

    @staticmethod
    def _end_write(ctx):
        try:
            cmds.autoKeyframe(state=ctx["auto_key"])
        finally:
            cmds.currentTime(ctx["current_time"])
            if ctx["marker"]:
                ctx["marker"].delete_marker()

    # --- coordinator ----------------------------------------------------------
    def apply_requests(self, requests, timeline_selection, selected_range, runner=None):
        """Plan, capture world poses, write switches, then compensate per frame.

        Runs as a cooperative coordinator: on a worker thread for long jobs
        (every Maya call marshalled to the main thread), inline for short ones.
        """
        runner = runner or OperationRunner()
        self.last_range = None
        self.issues = []
        estimate = sum(max(1, len(self.transform_key_times(op.xform_target)))
                       if all_frames or timeline_selection else 1
                       for operations, all_frames in requests for op in operations)

        def coordinator(run):
            jobs, fast = run.main(self._plan, requests, timeline_selection, selected_range)
            if not jobs and not fast:
                return set()
            if not jobs:
                # Pure rotate-order conversion edits the original curves in
                # place. No frame capture, timeline pass or compensation UI.
                run.check(wrote=False)
                run.wrote = True
                for prepared in fast:
                    run.main(self._apply_rotation, prepared)
                return {prepared[0].xform_target for prepared in fast}
            schedule = {}
            for job in jobs:
                frames = run.main(self._key_frames_for_job, job,
                                  timeline_selection, selected_range)
                for op in job["ops"]:
                    target = op.xform_target
                    if not target:
                        continue  # no xform target: the switch is written, no pose is held
                    for frame in frames:
                        slot = schedule.setdefault(frame, {})
                        slot[target] = slot.get(target, False) or job["keyed"]
            targets = sorted({t for slot in schedule.values() for t in slot})
            self.last_range = (min(schedule), max(schedule)) if schedule else None
            run.set_total(len(schedule) * 2 + 1)

            marker = (run.main(Timeline.create, [min(schedule), max(schedule) + 1],
                               autodestroy=None)
                      if len(schedule) > 1 else None)
            try:
                snapshots = {}
                run.status = "SpaceSwitch: saving positions"
                initial_time = run.main(cmds.currentTime, query=True)
                try:
                    for frame in sorted(schedule):
                        run.check(wrote=False)
                        snapshots[frame] = run.main(self._capture, frame, list(schedule[frame]))
                        run.step()
                finally:
                    run.main(cmds.currentTime, initial_time, update=True)

                run.check(wrote=False)
                ctx = run.main(self._begin_write, schedule, targets)
                try:
                    run.wrote = True
                    run.main(self._write_switches, jobs, fast, self)
                    run.step("SpaceSwitch: applying positions")
                    for frame in sorted(schedule):
                        run.check()
                        run.main(self._compensate_frame, frame, schedule[frame], snapshots[frame], ctx)
                        run.step()
                finally:
                    run.main(self._end_write, ctx)
            finally:
                if marker is not None:
                    run.main(marker.delete_marker)
            return set(targets) | {item[0].xform_target for item in fast}

        return runner.run(coordinator, estimate)


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
        self._busy = False
        self._setup_dialog = None

        self._popup_timer = QTimer(self)
        self._popup_timer.setSingleShot(True)
        self._popup_timer.setInterval(100)
        self._popup_timer.timeout.connect(self._show_pending_popup)

        # Coalesce bursts of Maya events (scrubbing, marquee selection) into one update.
        self._pending_refresh = None
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(40)
        self._refresh_timer.timeout.connect(self._run_deferred_refresh)

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
        modifier_held = (_multi_select_modifier_held(), _cycle_modifier_held())
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
                item._update_cycle_hint()

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
            by_plug = OrderedDict()
            for target, object_data in item.objects_map.items():
                plug = (object_data.get("attr_node") or target, object_data.get("attr"))
                by_plug.setdefault(plug, OrderedDict())[target] = object_data
            if len(by_plug) <= 1:
                entries.append((item, options_map))
                continue
            for objects in by_plug.values():
                first = next(iter(objects))
                label_node = first if len(objects) == 1 else (
                    next(iter(objects.values())).get("attr_node") or first)
                staged_item = _StagedAttributeEntry(
                    item, label_node, objects
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
        if len(entries) < 2:
            self._close_multi_switch_dialog(clear_selection=False)
            return
        if self._multi_switch_dialog and util.is_valid_widget(self._multi_switch_dialog):
            self._multi_switch_dialog.update_entries(entries)
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

        selection_title = QtWidgets.QLabel(_t("Selection"))
        self.selection_title = selection_title
        selection_title.setStyleSheet(
            "font-size: %spx; color: %s; font-weight: bold; background: transparent;" % (util.DPI(18), self.TEXT_COLOR)
        )
        selection_title.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
        selection_title.setWordWrap(False)
        selection_title.setFixedHeight(selection_title.fontMetrics().height() + 2)

        self.view_button = QtWidgets.QPushButton(u"\u2197")
        self.view_button.setCursor(QtCore.Qt.PointingHandCursor)
        self.view_button.setFocusPolicy(QtCore.Qt.NoFocus)
        self.view_button.setFixedSize(util.DPI(22), util.DPI(22))
        self.view_button.setStyleSheet(
            "QPushButton{background:transparent;border:none;color:%s;font-size:%spx;}"
            "QPushButton:hover{color:%s;}" % (COLOR_TEXT_SECONDARY, util.DPI(16), COLOR_ACCENT_WHITE)
        )
        self.view_button.setToolTip(_t("Open as a window (stays open)"))
        self.view_button.clicked.connect(self.expand_to_window)

        title_layout.addWidget(title_icon)
        title_layout.addWidget(selection_title, 1)
        title_layout.addWidget(self.view_button)

        self.selection_label = QtWidgets.QLabel(_t("No switches for selection"))
        self.selection_label.setStyleSheet("color: %s; background: transparent;" % self.TEXT_COLOR)

        selection_layout.addLayout(title_layout)
        selection_layout.addWidget(self.selection_label)
        self._update_header()

        self.mainLayout.insertLayout(0, selection_layout)

    def _load_persistent_settings(self):
        self.namespace_display = self._setting_bool("namespace_display", False)
        self.all_frames = self._setting_bool("all_frames", False)
        self.euler_filter = self._setting_bool("euler_filter", True)
        self.fast_rotation_order = self._setting_bool("fast_rotation_order", True)
        self.show_rotate_order = self._setting_bool("show_rotate_order", True)
        self.asset_view = self._setting_bool("asset_view", False)
        self._asset_namespace = None

    def _custom_switch_keys(self):
        value = self.settings.value("custom_switches", [])
        if not value:
            return []
        if isinstance(value, str):
            return [value]
        return [str(v) for v in value]

    def _set_custom_switch_keys(self, keys):
        self.settings.setValue("custom_switches", sorted(set(keys)))

    def _hidden_switch_keys(self):
        """Rig-relative attribute identities removed from the automatic panel."""
        value = self.settings.value("hidden_switches", []) or []
        if isinstance(value, str):
            return {value}
        return {str(item) for item in value}

    def _set_hidden_switch_keys(self, keys):
        self.settings.setValue("hidden_switches", sorted(set(keys)))

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
                    lambda *a: self._on_selection_changed(),
                )
            )
            self._cb.add(
                om.MEventMessage.addEventCallback(
                    "timeChanged",
                    lambda *a: self._on_time_changed(),
                )
            )
            self._cb.add(
                om.MEventMessage.addEventCallback(
                    "Undo",
                    lambda *a: self._schedule_refresh("full"),
                )
            )
            self._cb.add(
                om.MEventMessage.addEventCallback(
                    "Redo",
                    lambda *a: self._schedule_refresh("full"),
                )
            )
            self._cb.add(
                om.MSceneMessage.addCallback(
                    om.MSceneMessage.kAfterOpen,
                    lambda *a: (self.catalog_builder.clear_cache(), self._refresh_callbacks()),
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

    def _resume_auto_close(self):
        # Never let the popup auto-close mid-switch or while targets are being picked.
        if getattr(self, "_busy", False):
            return
        dialog = getattr(self, "_setup_dialog", None)
        if dialog is not None and util.is_valid_widget(dialog) and dialog.isVisible():
            return
        FloatingWidget._resume_auto_close(self)

    def _is_popup_mode(self):
        # True/False = popup (auto-close running / briefly suspended); None = window.
        return self._auto_close_active is not None

    def _refresh_footer(self):
        popup_mode = self._is_popup_mode()
        view_button = getattr(self, "view_button", None)
        if view_button is not None and util.is_valid_widget(view_button):
            view_button.setVisible(popup_mode)
        # Rebuilding the bar on every refresh flickers: only when the mode changes.
        if getattr(self, "_footer_mode", "unset") == popup_mode and (popup_mode or self.bottomBar):
            return
        self._footer_mode = popup_mode
        if popup_mode:
            self.setBottomBar(closeButton=False)
            return
        self.setBottomBar(
            [
                base_widgets.QFlatDialogButton(
                    "Add Switch",
                    callback=self.add_switch_from_channel_box,
                    icon=util.return_icon_path("add"),
                )
            ],
            closeButton=True,
            spacing=util.DPI(2),
        )

    def expand_to_window(self):
        """Popup -> persistent window (stays open, gets the bottom bar)."""
        self._geometry_anchor_bottom = self.frameGeometry().bottom()
        self.showBottomBar()
        self._request_geometry_fit()

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

    def _schedule_refresh(self, kind):
        """kind: "values" (time change) or "full" (selection/undo); full wins."""
        if kind == "full" or self._pending_refresh is None:
            self._pending_refresh = kind
        self._refresh_timer.start()

    def _run_deferred_refresh(self):
        kind, self._pending_refresh = self._pending_refresh, None
        if not util.is_valid_widget(self) or not self.isVisible():
            return
        if kind == "values":
            self._update_current_values()
        elif kind == "full":
            self.refresh(force=True)

    def _update_current_values(self):
        """Time changed: only the current values move, keys/targets don't."""
        for item, _options_map in list(self._active_switch_widgets.values()):
            if not util.is_valid_widget(item):
                continue
            changed = False
            for obj, data in item.objects_map.items():
                value = Maya.get_float(data.get("attr_node", obj), data.get("attr"), data.get("current", 0.0))
                enum_values = data.get("enum_values")
                if enum_values and int(round(value)) in enum_values:
                    value = float(enum_values.index(int(round(value))))
                if value != data.get("current"):
                    data["current"] = value
                    changed = True
            if changed:
                item.sync_current()

    def _on_time_changed(self):
        # Never touch the UI during playback; update values once it stops.
        if cmds.play(query=True, state=True):
            return
        self._schedule_refresh("values")

    def _on_selection_changed(self):
        if self.asset_view and self._asset_namespace is not None:
            selection = Maya.selection(long=False)
            if not selection or SwitchCatalogBuilder.namespace_of(selection[0]) == self._asset_namespace:
                self._previous_selection = selection
                return
        self._schedule_refresh("full")

    def _target_overrides(self):
        try:
            value = self.settings.value("target_overrides", "") or ""
            return json.loads(value) if value else {}
        except Exception:
            return {}

    def _custom_names(self):
        try:
            value = self.settings.value("custom_names", "") or ""
            return json.loads(value) if value else {}
        except Exception:
            return {}

    def _set_custom_names(self, names):
        self.settings.setValue("custom_names", json.dumps(names, sort_keys=True))

    def _rename_switch(self, data):
        objects = list(data.get("objects", {}).values())
        if not objects:
            return
        key = self._override_key(objects[0])
        names = self._custom_names()
        current = names.get(key, data.get("long", ""))
        name, accepted = QtWidgets.QInputDialog.getText(
            self, _t("Rename Switch"), _t("Display name:"), text=current)
        if not accepted:
            return
        name = str(name).strip()
        if name:
            names[key] = name
        else:
            names.pop(key, None)
        self._set_custom_names(names)
        self.refresh(force=True)

    def _set_target_overrides(self, overrides):
        self.settings.setValue("target_overrides", json.dumps(overrides, sort_keys=True))

    @staticmethod
    def _override_key(data):
        return "%s.%s" % (SwitchCatalogBuilder.short_relative(data.get("attr_node")), data.get("attr"))

    def _apply_target_overrides(self, catalog):
        overrides = self._target_overrides()
        custom_names = self._custom_names()
        for data in catalog.values():
            objects = data.get("objects", {})
            first = next(iter(objects.values()), None)
            if first:
                custom_name = custom_names.get(self._override_key(first))
                if custom_name:
                    data["long"] = custom_name
            if not overrides:
                continue
            replaced = OrderedDict()
            for obj, obj_data in objects.items():
                targets = overrides.get(self._override_key(obj_data))
                if not targets:
                    replaced[obj] = obj_data
                    continue
                namespace = SwitchCatalogBuilder.namespace_of(obj_data.get("attr_node"))
                added_override = False
                for rel in targets:
                    full = "%s:%s" % (namespace, rel) if namespace else rel
                    if Maya.exists(full):
                        new_data = dict(obj_data)
                        new_data["xform_target"] = full
                        new_data["override"] = True
                        new_data["missing_target"] = False
                        replaced[full] = new_data
                        added_override = True
                if not added_override:
                    replaced[obj] = obj_data
            objects.clear()
            objects.update(replaced)
        return catalog

    def _build_switch_data(self):
        catalog = self._apply_target_overrides(self._build_switch_data_raw())
        hidden = self._hidden_switch_keys()
        if not hidden:
            return catalog
        for key in list(catalog):
            objects = catalog[key].get("objects", {})
            for target, obj_data in list(objects.items()):
                if self._override_key(obj_data) in hidden:
                    del objects[target]
            if not objects:
                del catalog[key]
        return catalog

    def _build_switch_data_raw(self):
        custom_keys = self._custom_switch_keys()
        selection = self._previous_selection
        if self.asset_view:
            if selection:
                self._asset_namespace = SwitchCatalogBuilder.namespace_of(selection[0])
            if self._asset_namespace is None:
                return {}
            return self.catalog_builder.asset_catalog(self._asset_namespace, custom_keys)
        if not selection:
            return {}
        data = self.catalog_builder.combined_catalog(selection)
        return self.catalog_builder.merge_catalogs(
            data, self.catalog_builder.custom_catalog(selection, custom_keys))

    def _update_header(self):
        if not util.is_valid_widget(getattr(self, "selection_title", None)):
            return
        if self.asset_view:
            name = self._asset_namespace
            title = (name.split(":")[-1] if name else _t("Scene")) if name is not None else _t("Asset")
            self.selection_title.setText(title)
            self.selection_label.setText(
                _t("Select a control to pick an asset") if name is None
                else _t("No switches found in this asset"))
        else:
            self.selection_title.setText(_t("Selection"))
            self.selection_label.setText(_t("No switches for selection"))

    def toggle_asset_view(self):
        self.set_setting("asset_view", not self.asset_view)
        self._geometry_anchor_bottom = self.frameGeometry().bottom()
        self.refresh(force=True)

    def add_switch_from_channel_box(self):
        """Register channel-box-highlighted attributes of the selection as switches."""
        selection = Maya.selection(long=False)
        attrs = []
        for flag in ("selectedMainAttributes", "selectedShapeAttributes", "selectedHistoryAttributes"):
            attrs.extend(cmds.channelBox("mainChannelBox", query=True, **{flag: True}) or [])
        if not selection or not attrs:
            cmds.warning("SpaceSwitch: please check your channel selection for valid switches "
                         "(select the control, highlight the attribute in the Channel Box).")
            return
        keys = self._custom_switch_keys()
        added = []
        restored = []
        hidden = self._hidden_switch_keys()
        for node in selection:
            for attr in attrs:
                if not Maya.attr_exists(node, attr):
                    continue
                long_attr = cmds.attributeQuery(attr, node=node, longName=True)
                if self.catalog_builder.custom_entry(node, long_attr) is None:
                    cmds.warning("SpaceSwitch: %s.%s can't be a switch (needs an enum, bool "
                                 "or a numeric attribute with min/max)." % (node, long_attr))
                    continue
                key = "%s.%s" % (SwitchCatalogBuilder.short_relative(node), long_attr)
                if key in hidden:
                    hidden.remove(key)
                    restored.append(key)
                if key not in keys:
                    keys.append(key)
                    added.append(key)
        if not added and not restored:
            cmds.warning("SpaceSwitch: no new enum/numeric attributes to add.")
            return
        self._set_custom_switch_keys(keys)
        self._set_hidden_switch_keys(hidden)
        self.refresh(force=True)

    def _remove_custom_switch(self, data):
        keys = set(self._custom_switch_keys())
        for obj_data in data.get("objects", {}).values():
            keys.discard("%s.%s" % (SwitchCatalogBuilder.short_relative(obj_data.get("attr_node")),
                                    obj_data.get("attr")))
        self._set_custom_switch_keys(keys)
        self.refresh(force=True)

    def _hide_switch(self, data):
        hidden = self._hidden_switch_keys()
        for obj_data in data.get("objects", {}).values():
            hidden.add(self._override_key(obj_data))
        self._set_hidden_switch_keys(hidden)
        self.refresh(force=True)

    def _restore_hidden_switches(self):
        self._set_hidden_switch_keys([])
        self.refresh(force=True)

    def _reset_target_override(self, data):
        overrides = self._target_overrides()
        for obj_data in data.get("objects", {}).values():
            overrides.pop(self._override_key(obj_data), None)
        self._set_target_overrides(overrides)
        self.refresh(force=True)

    def _on_item_context(self, sender, data):
        objects = list(data.get("objects", {}).values())
        is_custom = any(d.get("source") == "custom" for d in objects)
        has_override = any(d.get("override") for d in objects)
        menu = widgets.QFlatMenu(self)
        menu.aboutToShow.connect(self._suspend_auto_close)
        menu.aboutToHide.connect(self._resume_auto_close)
        menu.addAction("Xform Target Setup...", description="Pick the control(s) kept in place when switching.") \
            .triggered.connect(lambda *a: self._show_change_target_dialog(sender, data))
        menu.addAction("Rename Switch...", description="Set the display name saved for this rig attribute.") \
            .triggered.connect(lambda *a: self._rename_switch(data))
        if has_override:
            menu.addAction("Reset Xform Target", description="Go back to the auto-detected target.") \
                .triggered.connect(lambda *a: self._reset_target_override(data))
        if is_custom:
            menu.addAction("Remove Switch", description="Remove this switch from the panel.") \
                .triggered.connect(lambda *a: self._remove_custom_switch(data))
        else:
            menu.addAction("Remove Switch", description="Hide this switch from the panel; it can be restored later.") \
                .triggered.connect(lambda *a: self._hide_switch(data))
        Qtx.exec_menu(menu, QCursor.pos())

    def _rebuild_active_widgets(self):
        try:
            self._switch_data = self._build_switch_data()
            self._replace_attribute_content(self._switch_data)
            self._update_header()
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
        owners = {d.get("attr_node") for d in data["objects"].values()}
        if len(target_nodes) > 1 and len(owners) == 1 and None not in owners:
            display_name = self._format_object_name([owners.pop()])
        else:
            display_name = self._format_object_name(target_nodes)

        attr_item = AttributeItem(
            display_name,
            data["long"].title(),
            enum_name,
            target_nodes,
            data["objects"],
            self,
        )

        if any(d.get("missing_target") for d in data["objects"].values()):
            attr_item.setToolTip(
                "<html><b>Could not find Xform Target</b><br>Switching won't keep the pose."
                "<br><br><b>Right-click to set it up...</b></html>")
        else:
            attr_item.setToolTip(self.formatXformTooltipObjects(target_nodes))
        attr_item.setContextMenuPolicy(Qt.CustomContextMenu)
        attr_item.customContextMenuRequested.connect(
            lambda pos, sender=attr_item, item_data=data: self._on_item_context(sender, item_data)
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
            enum_values = data.get("enum_values") or []

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
                        value=enum_values[index] if index < len(enum_values) else index,
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
        def mean_metric(order, metric):
            values = [r[order][metric] for r in results if order in r]
            return sum(values) / float(len(values)) if values else 0.0

        averages = [mean_metric(order, "average") for order in orders]
        maximums = [mean_metric(order, "maximum") for order in orders]
        scores = [(average + maximum) / 2.0
                  for average, maximum in zip(averages, maximums)]
        labels = self.analyzer.classify(scores)
        return {
            order: {
                "percentage": score,
                "average": average,
                "maximum": maximum,
                "label": label,
            }
            for order, score, average, maximum, label
            in zip(orders, scores, averages, maximums, labels)
        }

    def _apply_multi_switch(self, staged_entries, all_frames):
        requests = [(option, item.enum_attr, options_map, all_frames)
                    for item, options_map, option in staged_entries if option in options_map]
        self._close_multi_switch_dialog(clear_selection=True)
        self._apply_requests(requests)

    _SKIPPED_TARGET_SETUP = set()  # (attr_node, attr) skipped for this Maya session

    def _missing_target_prompt(self, requests):
        """animBot-style: offer setup for a switch with no xform target. True = go on."""
        for value, attr, options_map, _all in requests:
            for op in options_map.get(value, {}).get("operations", []):
                key = (op.attr_node, op.attr)
                if op.xform_target is not None or key in self._SKIPPED_TARGET_SETUP:
                    continue
                self._suspend_auto_close()
                try:
                    answer = cmds.confirmDialog(
                        title="SpaceSwitch",
                        message="Could not find Xform Target for %s.\n\n"
                                "Xform targets are the transforms kept in place when an attribute "
                                "switches. Set one up now, or switch without keeping the pose?"
                                % op.plug,
                        button=["Setup", "Skip for this session", "Cancel"],
                        defaultButton="Setup", cancelButton="Cancel", dismissString="Cancel")
                finally:
                    self._resume_auto_close()
                if answer == "Skip for this session":
                    self._SKIPPED_TARGET_SETUP.add(key)
                    continue
                if answer == "Setup":
                    for item, item_options in self._active_switch_widgets.values():
                        if item_options is options_map and util.is_valid_widget(item):
                            self._show_change_target_dialog(item, {"objects": item.objects_map})
                            break
                return False
        return True

    @staticmethod
    def _timeline_scope():
        """Selected time range, or the current frame outside graphical Maya."""
        now = cmds.currentTime(query=True)
        try:
            timeline = mel.eval('global string $gPlayBackSlider; $tmp=$gPlayBackSlider;')
            if timeline:
                selected = cmds.timeControl(timeline, q=True, rangeVisible=True)
                times = cmds.timeControl(timeline, q=True, rangeArray=True)
                if times and len(times) == 2:
                    return bool(selected), times
        except (RuntimeError, ValueError):
            pass
        return False, [now, now]

    def _apply_requests(self, requests):
        # The cooperative event loop can receive another scripted request
        # while an earlier one is still writing. Never nest undo chunks or
        # start a second compensation against a half-switched scene.
        if self._busy:
            cmds.warning("SpaceSwitch: a switch is already in progress")
            return
        if not self._missing_target_prompt(requests):
            return
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
        selected, frame_range = self._timeline_scope()
        self._close_active_popup()
        self._remove_callbacks()
        self._refresh_timer.stop()
        self._pending_refresh = None
        self._busy = True
        self._suspend_auto_close()
        runner = OperationRunner("SpaceSwitch")
        cancelled = failed = None
        try:
            with UndoChunk("SpaceSwitch"):
                with RefreshSuspended():
                    changed = self.executor.apply_requests(prepared, selected, frame_range, runner)
                    if self.euler_filter and changed:
                        self.apply_euler_filter(changed, self.executor.last_range)
        except OperationCancelled as exc:
            cancelled = exc
        except PoseCompensationError as exc:
            failed = exc  # expected rig limitation; rollback and show a concise warning
        except Exception as exc:
            failed = exc
            traceback.print_exc()
        finally:
            self._busy = False
            self._add_callbacks()
        if cancelled is not None or failed is not None:
            if runner.wrote:
                cmds.undo()  # never leave a half-switched shot: roll back the chunk
            if cancelled is not None:
                cmds.warning("SpaceSwitch: cancelled, %s" % (
                    "partial changes were reverted." if runner.wrote else "nothing was changed."))
            else:
                cmds.warning("SpaceSwitch: failed (%s), %s" % (
                    failed, "changes were reverted." if runner.wrote else "nothing was changed."))
        issues = list(getattr(self.executor, "issues", []) or [])
        if issues and cancelled is None and failed is None:
            for issue in issues:
                cmds.warning("SpaceSwitch: " + issue)
            try:
                cmds.inViewMessage(
                    amg="SpaceSwitch: switched with %d warning%s (see Script Editor)"
                        % (len(issues), "" if len(issues) == 1 else "s"),
                    pos="midCenterTop", fade=True)
            except Exception:
                pass
        self.refresh(force=True)
        self._resume_auto_close()

    def _apply_attribute_switch(self, enum_value, enum_attr, options_and_objects, all_frames_override=None):
        all_frames = self.all_frames if all_frames_override is None else all_frames_override
        self._apply_requests([(enum_value, enum_attr, options_and_objects, all_frames)])

    def apply_euler_filter(self, targets, frame_range=None):
        """Euler-filter only what the switch touched; leave the rest of the shot alone."""
        curves = []

        for target in targets:
            for attr in ("rx", "ry", "rz"):
                plug = Maya.plug(target, attr)

                if not cmds.objExists(plug):
                    continue

                curves.extend(Maya.upstream_animation_curves(plug))

        curves = sorted(set(curves))

        if not curves:
            return
        if frame_range:
            try:
                cmds.filterCurve(*curves, filter="euler",
                                 startTime=frame_range[0], endTime=frame_range[1])
                return
            except TypeError:
                pass  # older Maya without a ranged filterCurve: whole curves
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
        QTimer.singleShot(150, lambda: util.is_valid_widget(self) and self._update_interaction_state(False))
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
        self._close_active_popup()

        def on_close(objects):
            self._setup_dialog = None
            if objects is None:  # skipped / unchanged
                cmds.select(selection, replace=True)
                self._add_callbacks()
                return
            overrides = self._target_overrides()
            for obj_data in data["objects"].values():
                overrides[self._override_key(obj_data)] = [
                    SwitchCatalogBuilder.short_relative(o) for o in objects]
            self._set_target_overrides(overrides)
            cmds.select(selection, replace=True)
            self._add_callbacks()
            if util.is_valid_widget(sender):
                sender.setToolTip(self.formatXformTooltipObjects(objects))
            for key, (item, _) in list(self._active_switch_widgets.items()):
                if item is sender:
                    self._active_switch_widgets[key] = (item, self._build_options_map(data["objects"]))

        self._remove_callbacks()

        label = sender.label_text if util.is_valid_widget(sender) else ""
        dialog = SetupTargetsDialog(self, data["objects"], on_close=on_close, switch_label=label)
        self._setup_dialog = dialog
        dialog.place_near_cursor()
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

        asset_action = self.context_menu.addAction(
            "Asset View",
            description="List every switch of the selected asset instead of just the selection.",
        )
        asset_action.setCheckable(True)
        asset_action.setChecked(self.asset_view)
        asset_action.toggled.connect(lambda *a: self.toggle_asset_view())

        if self._hidden_switch_keys():
            self.context_menu.addAction(
                "Restore Hidden Switches",
                description="Show previously removed automatically detected switches.",
            ).triggered.connect(lambda *a: self._restore_hidden_switches())

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
        # Close the target setup first: it owns a Maya callback and re-adds ours.
        dialog = self._setup_dialog
        if dialog is not None and util.is_valid_widget(dialog):
            dialog.cancel()
        self._modifier_timer.stop()
        self._refresh_timer.stop()
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
