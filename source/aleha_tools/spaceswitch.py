# -*- coding: utf-8 -*-

#
#
#  Copy this file in your scripts directory:
#     %USERPROFILE%\Documents\maya\scripts
#
#  or in a speficic version:
#     %USERPROFILE%\Documents\maya\XXXX\scripts
#
#
#  Run as a DIALOG with:
#
#    import aleha_tools.spaceswitch as spaceswitch
#    spaceswitch.show()
#
#
#  Run as a POPUP with:
#
#    import aleha_tools.spaceswitch as spaceswitch
#    spaceswitch.popup()
#
#


import sys
import math

from maya import cmds
from maya import mel
from maya import OpenMaya as om
from maya import OpenMayaUI as omui

try:
    PYSIDE_VERSION = 2
    from PySide2.QtCore import *  # noqa: F403
    from PySide2.QtGui import *  # noqa: F403
    from PySide2.QtWidgets import *  # noqa: F403
except ImportError:
    PYSIDE_VERSION = 6
    from PySide6.QtCore import *  # noqa: F403
    from PySide6.QtGui import *  # noqa: F403
    from PySide6.QtWidgets import *  # noqa: F403

import aleha_tools
from aleha_tools import base_widgets, util, widgets

from importlib import reload

reload(aleha_tools)
reload(base_widgets)
reload(util)
reload(widgets)

CONTEXTUAL_CURSOR = QCursor(QPixmap(":/rmbMenu.png"), hotX=11, hotY=8)
_MAIN_DICT = sys.modules["__main__"].__dict__


DATA = {
    "TOOL": "SpaceSwitch",
    "VERSION": "1.3.5",
}
DATA["AUTHOR"] = aleha_tools.DATA["AUTHOR"]

# Color Palette
COLOR_BG_MAIN = "#101010"
COLOR_BG_POPUP = "#444444"
COLOR_BG_TRACK = "#333333"
COLOR_ACCENT_DARK = "#7f4a77"
COLOR_ACCENT_MAIN = "#d384ca"
COLOR_ACCENT_LIGHT = "#e59ed0"
COLOR_ACCENT_HOVER = "#e688da"
COLOR_ACCENT_WHITE = "#f2c3ed"
COLOR_TEXT_MAIN = "#2a2a2a"  # Darker text for readability on light accents
COLOR_TEXT_SECONDARY = "#bbbbbb"
COLOR_BLEND_MULTI = "#584655"


# =================================================================================
#  1. INFRASTRUCTURE & MAPPING
# =================================================================================


class CallbackManager:
    def __init__(self):
        self.ids = []

    def add(self, cb_id):
        self.ids.append(cb_id)

    def clear(self):
        for i in self.ids:
            try:
                om.MMessage.removeCallback(i)
            except Exception:
                pass
        del self.ids[:]


class GimbalAnalyzer:
    def __init__(self):
        self.rotation_orders = {
            "xyz": om.MEulerRotation.kXYZ,
            "yzx": om.MEulerRotation.kYZX,
            "zxy": om.MEulerRotation.kZXY,
            "xzy": om.MEulerRotation.kXZY,
            "yxz": om.MEulerRotation.kYXZ,
            "zyx": om.MEulerRotation.kZYX,
        }

    def radians_to_degrees(self, radians):
        return radians * (180.0 / math.pi)

    def get_middle_axis_value(self, rotation):
        return {
            om.MEulerRotation.kZXY: rotation.x,
            om.MEulerRotation.kZYX: rotation.y,
            om.MEulerRotation.kXZY: rotation.z,
            om.MEulerRotation.kXYZ: rotation.y,
            om.MEulerRotation.kYZX: rotation.z,
            om.MEulerRotation.kYXZ: rotation.x,
        }[rotation.order]

    def compute_gimbal_percentage(self, rotation):
        mid = self.radians_to_degrees(self.get_middle_axis_value(rotation))
        return int(abs(((mid + 90) % 180) - 90) / 90 * 100)

    def convert_order_string(self, s):
        return self.rotation_orders.get(s, om.MEulerRotation.kZYX)

    def _safe_get_depend_node(self, sel_list, index=0):
        """Supports API 2.0 and classic API calling styles."""
        try:
            # API 2.0
            return sel_list.getDependNode(index)
        except TypeError:
            # Classic API signature: getDependNode(index, MObject)
            mobj = om.MObject()
            sel_list.getDependNode(index, mobj)
            return mobj

    def get_rotation(self, obj):
        sel = om.MSelectionList()
        sel.add(obj)
        node = self._safe_get_depend_node(sel, 0)
        tfm = om.MFnTransform(node)
        return tfm.rotation()  # MEulerRotation (radians)

    def get_rotation_order_list(self, obj):
        if cmds.attributeQuery("rotateOrder", node=obj, exists=True):
            return cmds.attributeQuery("rotateOrder", node=obj, listEnum=True)[0].split(":")
        return []

    def _rotation_at_time(self, obj, t, order_list):
        """Get MEulerRotation at time t WITHOUT changing current time or UI."""
        rx = cmds.getAttr("%s.rotateX" % obj, time=t)
        ry = cmds.getAttr("%s.rotateY" % obj, time=t)
        rz = cmds.getAttr("%s.rotateZ" % obj, time=t)
        idx = int(cmds.getAttr("%s.rotateOrder" % obj, time=t))
        idx = max(0, min(idx, len(order_list) - 1)) if order_list else 0
        current_order_str = order_list[idx] if order_list else "xyz"

        return om.MEulerRotation(
            math.radians(rx or 0.0),
            math.radians(ry or 0.0),
            math.radians(rz or 0.0),
            self.convert_order_string(current_order_str),
        )

    def compute_all_percentages(self, obj, order_list):
        """
        Worst-case gimbal % per order across ALL keyed frames (or current time if unkeyed),
        without pausing OGS or touching the timeline.
        """
        key_times = set()
        for attr in ("rotateX", "rotateY", "rotateZ"):
            k = cmds.keyframe(obj, attribute=attr, query=True, timeChange=True)
            if k:
                key_times.update(k)
        if not key_times:
            key_times = {cmds.currentTime(query=True)}

        key_times = sorted(key_times)

        percentages = []
        for target_order_str in order_list:
            target_order = self.convert_order_string(target_order_str)
            worst = 0
            for t in key_times:
                rot_t = self._rotation_at_time(obj, t, order_list)
                # copy before reordering
                reordered = om.MEulerRotation(rot_t.x, rot_t.y, rot_t.z, rot_t.order)
                reordered.reorderIt(target_order)
                g = self.compute_gimbal_percentage(reordered)
                if g > worst:
                    worst = g
            percentages.append(worst)
        return percentages

    def classify_percentages(self, percentages):
        labels = [""] * len(percentages)
        if not percentages or len(set(percentages)) == 1:
            return labels

        best = min(percentages)
        for i, val in enumerate(percentages):
            diff = val - best
            if diff == 0:
                labels[i] = "Best"
            elif diff <= 2:
                labels[i] = "Good"
            elif diff <= 6:
                labels[i] = "OK"
        return labels

    def analyze(self, obj):
        """
        Returns:
          {
            "xyz": {"percentage": 12, "label": "Good"},
            "yzx": {"percentage": 10, "label": "Best"},
            ...
          }
        """
        order_list = self.get_rotation_order_list(obj)
        if not order_list:
            return {}

        percentages = self.compute_all_percentages(obj, order_list)
        labels = self.classify_percentages(percentages)

        result = {}
        for i, order in enumerate(order_list):
            result[order] = {"percentage": percentages[i], "label": labels[i]}
        return result


# =================================================================================
#  2. UI FOUNDATION
# =================================================================================


class Grip(QSizeGrip):
    """
    A custom QSizeGrip that signals the parent to pause auto-closing on resizing.
    """

    def __init__(self, parent):
        super().__init__(parent)
        self._parent_widget = parent
        self._start_geom = None

    def mousePressEvent(self, e):
        self._start_geom = self._parent_widget.geometry()
        self._parent_widget._suspend_auto_close()
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        super().mouseReleaseEvent(e)
        if self._start_geom and self._parent_widget.geometry() != self._start_geom:
            self._parent_widget.showBottomBar()
        self._start_geom = None

    def eventFilter(self, obj, event):
        return False


class FloatingWidget(base_widgets.QFlatDialog):
    """
    A draggable, frameless, rounded widget wrapper.
    Can be instantiated as a temporary popup or a pinned window.
    """

    BORDER_RADIUS = util.DPI(5)
    AUTO_CLOSE_DIST = util.DPI(10)
    AUTO_CLOSE_PERIOD_MS = 300
    TEXT_COLOR = COLOR_TEXT_SECONDARY

    def __init__(self, popup=False, parent=None):
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() | Qt.Tool | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose, False)

        self._is_dragging = False
        self._drag_offset = QPoint()
        self._drag_start_pos = QPoint()

        self._auto_close_active = True if popup else None

        # Event-driven auto-close mechanism
        self._auto_close_timer = QTimer(self)
        self._auto_close_timer.setSingleShot(True)
        self._auto_close_timer.setInterval(200)
        self._auto_close_timer.timeout.connect(self._process_auto_close_request)

        self._setup_ui()
        self.setMouseTracking(True)

    def enterEvent(self, event):
        self._auto_close_timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self._auto_close_active:
            self._auto_close_timer.start()
        super().leaveEvent(event)

    def _process_auto_close_request(self):
        """Evaluates whether the window should close based on current cursor position."""
        if not self._auto_close_active or not self.isVisible():
            return

        if self._is_cursor_within_bounds():
            return  # Cursor is in a valid interaction zone

        cursor_pos = QCursor.pos()
        bounds = self.frameGeometry()

        # Calculate Manhattan distance slop for a more forgiving interaction feel
        dx = max(bounds.left() - cursor_pos.x(), 0, cursor_pos.x() - bounds.right())
        dy = max(bounds.top() - cursor_pos.y(), 0, cursor_pos.y() - bounds.bottom())

        if (dx * dx + dy * dy) > (self.AUTO_CLOSE_DIST * self.AUTO_CLOSE_DIST):
            self.close()

    def _is_cursor_within_bounds(self):
        """Geometric intersection check for the main widget and its active sub-popups."""
        cursor_pos = QCursor.pos()
        if not util.is_valid_widget(self):
            return False

        if self.frameGeometry().contains(cursor_pos):
            return True

        if hasattr(self, "_active_popup") and self._active_popup and util.is_valid_widget(self._active_popup) and self._active_popup.isVisible():
            if self._active_popup.frameGeometry().contains(cursor_pos):
                return True
        return False

    def _setup_ui(self):
        self.mainContent = QWidget(self)
        self.mainLayout = QVBoxLayout(self.mainContent)
        self.mainLayout.setContentsMargins(util.DPI(6), util.DPI(8), util.DPI(6), util.DPI(8))
        self.mainLayout.setSpacing(2)

        self.root_layout.insertWidget(0, self.mainContent, 1)

        self.grip = Grip(self)
        self.grip.setCursor(Qt.SizeBDiagCursor)

    def paintEvent(self, event):
        if not self.isVisible():
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(COLOR_BG_TRACK))

        # Use drawRoundedRect for clean, all-around rounded corners
        rect = self.rect()
        r = self.BORDER_RADIUS
        p.drawRoundedRect(rect, r, r)

    def setBottomBar(self, *args, **kwargs):
        """Overrides QFlatDialog to manage bottom bar while allowing popup timer to persist."""
        if self.bottomBar:
            self.bottomBar.setParent(None)
            self.bottomBar.deleteLater()
            self.bottomBar = None

        kwargs.setdefault("margins", 0)
        super().setBottomBar(*args, **kwargs)

    def showBottomBar(self):
        """Disables auto-kill and adds a default close button if no bar exists."""
        if hasattr(self, "_refresh_footer"):
            self._refresh_footer()
        elif not self.bottomBar:
            self.setBottomBar(closeButton=True)
        self._disable_auto_close()

    def place_near_cursor(self):
        self.resize(self.sizeHint())
        w, h = self.width(), self.height()
        cursor_pos = QCursor.pos()
        screen = QGuiApplication.screenAt(cursor_pos) or QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()

        x = max(geo.left(), min(cursor_pos.x(), geo.right() - w))
        y = max(geo.top(), min(cursor_pos.y() - h // 2, geo.bottom() - h))
        self.move(x, y)

    def _check_mouse_distance_and_close(self):
        self._check_kill_condition()

    def resizeEvent(self, event):
        s = self.grip.sizeHint()
        self.grip.setFixedSize(s)
        self.grip.move(self.width() - s.width(), 0)
        self.grip.raise_()
        super().resizeEvent(event)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._is_dragging = True
            if PYSIDE_VERSION < 6:
                global_position = e.globalPos()
            else:
                global_position = e.globalPosition().toPoint()
            self._drag_start_pos = global_position
            self._drag_offset = global_position - self.frameGeometry().topLeft()
            self._suspend_auto_close()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._is_dragging and (e.buttons() & Qt.LeftButton):
            if PYSIDE_VERSION < 6:
                global_position = e.globalPos()
            else:
                global_position = e.globalPosition().toPoint()
            self.move(global_position - self._drag_offset)
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self._is_dragging:
            self._is_dragging = False
            if PYSIDE_VERSION < 6:
                global_position = e.globalPos()
            else:
                global_position = e.globalPosition().toPoint()

            # Check if we moved enough to convert to "show mode" (persistent window)
            drag_dist = (global_position - self._drag_start_pos).manhattanLength()
            if drag_dist > util.DPI(10):
                self.showBottomBar()
            elif self._auto_close_active is False:
                # Resume tracking after small click/drag
                self._auto_close_active = True
                self._resume_auto_close()

        super().mouseReleaseEvent(e)

    def _resume_auto_close(self):
        """Restarts the auto-close timer if the cursor is currently outside the bounds."""
        if self._auto_close_active is True and not self._is_cursor_within_bounds():
            self._auto_close_timer.start()

    def _suspend_auto_close(self):
        """Pauses the auto-close timer and updates tracking state."""
        if self._auto_close_active is True:
            self._auto_close_active = False
        if hasattr(self, "_auto_close_timer"):
            self._auto_close_timer.stop()

    def _disable_auto_close(self):
        """Permanently stops the auto-close mechanism for the lifetime of the widget."""
        if hasattr(self, "_auto_close_timer") and self._auto_close_timer:
            self._auto_close_timer.stop()
        self._auto_close_active = None

    def closeEvent(self, e):
        self._disable_auto_close()
        super().closeEvent(e)


# =================================================================================
#  3. SPECIFIC WIDGETS
# =================================================================================


class PillSlider(QWidget):
    """
    A custom pill-shaped slider for numeric attributes.
    """

    HEIGHT = util.DPI(32)
    HANDLE_RADIUS = util.DPI(13)

    SNAP_POINTS = [0.0, 0.5, 1.0]
    SNAP_THRESHOLD = 0.06

    def __init__(self, value, min_val, max_val, callback, parent=None):
        super().__init__(parent)
        self.setFixedSize(util.DPI(140), self.HEIGHT)
        self.value = float(value)
        self.min_val = float(min_val)
        self.max_val = float(max_val)
        self.callback = callback
        self._dragging = False
        self._original_value = self.value
        self.setCursor(Qt.PointingHandCursor)

    def _val_to_pos(self, val):
        offset = self.height() / 2.0
        if self.max_val <= self.min_val:
            return self.width() // 2
        w_inner = self.width() - (2 * offset)
        ratio = (val - self.min_val) / (self.max_val - self.min_val)
        return int(offset + ratio * w_inner)

    def _pos_to_val(self, x):
        offset = self.height() / 2.0
        w_inner = self.width() - (2 * offset)
        if w_inner <= 0:
            return self.min_val
        ratio = (x - offset) / float(w_inner)
        ratio = max(0.0, min(1.0, ratio))

        # Autosnap at snap points
        for snap in self.SNAP_POINTS:
            if abs(ratio - snap) < self.SNAP_THRESHOLD:
                ratio = snap
                break

        return self.min_val + ratio * (self.max_val - self.min_val)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Track
        rect = self.rect().adjusted(1, 1, -1, -1)
        r = rect.height() / 2
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(COLOR_ACCENT_DARK))
        painter.drawRoundedRect(rect, r, r)

        hy = self.height() / 2
        hr = self.HANDLE_RADIUS

        # Shadow Handle (Original position)
        if self._dragging:
            sx = self._val_to_pos(self._original_value)
            painter.setBrush(QColor(COLOR_BLEND_MULTI))
            painter.drawEllipse(QPoint(sx, int(hy)), hr, hr)

        # Handle
        hx = self._val_to_pos(self.value)
        painter.setBrush(QColor(COLOR_BG_TRACK))
        painter.drawEllipse(QPoint(hx, int(hy)), hr, hr)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._original_value = self.value
            self.value = self._pos_to_val(event.x())
            self.update()

    def mouseMoveEvent(self, event):
        if self._dragging:
            self.value = self._pos_to_val(event.x())
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = False
            self.callback(self.value)


class AttributePopup(QWidget):
    """
    A floating popup that lists attribute options with a dot for the selected one.
    """

    ALL_KEYFRAMES = "All Keyframes"
    CURRENT_KEYFRAMES = "Current Keyframes"

    def __init__(self, item_widget, options, current_idx, current_indices, marked_indices, on_select):
        super().__init__(item_widget.window())
        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self.item_widget = item_widget
        self.options = options
        self.current_idx = current_idx
        self.current_indices = current_indices
        self.marked_indices = marked_indices
        self.on_select = on_select

        any_obj = next(iter(item_widget.objects_map.values()))
        self.is_enum = any_obj.get("type") == "enum"
        self.min_val = any_obj.get("min", 0)
        self.max_val = any_obj.get("max", 1)

        self._setup_ui()

    def _setup_ui(self):
        """Main entry point for UI construction."""
        self.main_frame = QFrame(self)
        self.main_frame.setObjectName("PopupFrame")
        self.main_frame.setStyleSheet(f"""
            QFrame#PopupFrame {{
                background-color: {COLOR_BG_POPUP};
                border-radius: {util.DPI(8)}px;
            }}
        """)

        self.content_layout = QVBoxLayout(self.main_frame)
        self.content_layout.setContentsMargins(util.DPI(20), util.DPI(10), util.DPI(18), util.DPI(16))
        self.content_layout.setSpacing(util.DPI(1))

        if self.is_enum:
            self._build_enum_ui()
        else:
            self._build_numeric_ui()

        # Finalize structure and size
        self.adjustSize()
        self.outer_layout = QVBoxLayout(self)
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
            # Special formatting for rotation orders
            display_text = opt
            if is_rr and self.item_widget.gimbal_info:
                info = self.item_widget.gimbal_info.get(opt, {})
                label = info.get("label", "")
                if label:
                    display_text = f"{opt} ({label})"

            btn = self._create_option_button(display_text, i, is_all)
            self.content_layout.addWidget(btn)

            # Extra visual grouping for rotation orders (3+3)
            if is_rr and i == 2:
                self.content_layout.addSpacing(util.DPI(5))

    def _create_title(self, text):
        title = QLabel(text)
        title.setContentsMargins(0, 0, 0, util.DPI(4))
        title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        title.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: {util.DPI(11)}px;")
        return title

    def _add_separator(self):
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFixedHeight(1)
        line.setStyleSheet(f"background-color: {COLOR_BG_TRACK};")
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
        btn = QPushButton(text)
        btn.setFlat(True)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setMinimumWidth(util.DPI(60))
        btn.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)

        # Style with design tokens
        btn.setStyleSheet(f"""
            QPushButton {{
                color: {COLOR_ACCENT_HOVER};
                background-color: {COLOR_ACCENT_DARK};
                text-align: left;
                padding: {util.DPI(8)}px {util.DPI(18)}px {util.DPI(8)}px {util.DPI(8)}px;
                border-radius: {util.DPI(6)}px;
                font-size: {util.DPI(11)}px;
                font-weight: bold;
                border: none;
            }}
            QPushButton:hover {{
                background-color: {COLOR_ACCENT_MAIN};
                color: {COLOR_ACCENT_DARK};
            }}
        """)

        # Sync indicator dot
        dot_layout = QHBoxLayout(btn)
        dot_layout.setContentsMargins(0, 0, util.DPI(6), 0)
        dot_layout.addStretch()

        dot = QWidget()
        dot.setAttribute(Qt.WA_TransparentForMouseEvents)
        dot_size = util.DPI(10)
        dot.setFixedSize(dot_size, dot_size)

        is_keyed = index in self.marked_indices
        is_current = index in self.current_indices
        multi_current = len(self.current_indices) > 1

        if is_current or is_keyed:
            c = COLOR_BG_TRACK if not (is_current and multi_current) else COLOR_BLEND_MULTI
            dot.setStyleSheet(f"background: {c}; border-radius: {dot_size // 2}px;")
        else:
            dot.setStyleSheet("background: transparent;")

        dot_layout.addWidget(dot)
        btn.clicked.connect(lambda checked=False: self.select_option(index, all_frames=is_all))
        return btn

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(COLOR_BG_POPUP))

        arrow_w = util.DPI(10)
        arrow_h = util.DPI(15)

        side = getattr(self, "side", "right")
        arrow_y = getattr(self, "arrow_y", self.height() / 2)

        if side == "right":
            # Pointing left, attached to the left side of the frame
            poly = QPolygonF(
                [
                    QPointF(0, arrow_y),
                    QPointF(arrow_w + 1, arrow_y - arrow_h / 2),
                    QPointF(arrow_w + 1, arrow_y + arrow_h / 2),
                ]
            )
        else:
            # Pointing right, attached to the right side of the frame
            w = self.width()
            poly = QPolygonF(
                [
                    QPointF(w, arrow_y),
                    QPointF(w - arrow_w - 1, arrow_y - arrow_h / 2),
                    QPointF(w - arrow_w - 1, arrow_y + arrow_h / 2),
                ]
            )
        painter.drawPolygon(poly)

    def select_option(self, idx, all_frames=None):
        self.on_select(idx, all_frames=all_frames)
        # closing triggers closeEvent which clears parent handle and resumes timer
        self.close()

    def enterEvent(self, event):
        # Notify parent for unified interaction state
        p = self.parent()
        if p and hasattr(p, "_update_interaction_state"):
            p._update_interaction_state(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        p = self.parent()
        if p and hasattr(p, "_update_interaction_state"):
            # Delay to check if focus moved back to main area
            QTimer.singleShot(150, lambda: p._update_interaction_state(False))
        super().leaveEvent(event)

    def closeEvent(self, event):
        p = self.parent()
        if p:
            # Re-evaluate parent's close conditions
            if hasattr(p, "_active_popup") and p._active_popup == self:
                p._active_popup = None
            if hasattr(p, "_resume_auto_close"):
                p._resume_auto_close()
        super().closeEvent(event)

    def show_beside(self, widget):
        self.adjustSize()
        w, h = self.width(), self.height()

        # Global center Y of the source widget
        target_y_global = widget.mapToGlobal(QPoint(0, widget.height() // 2)).y()

        # Default: show on the right
        pos = widget.mapToGlobal(QPoint(widget.width(), 0))

        screen = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()

        self.side = "right"
        # If it overflows on the right, flip to left
        if pos.x() + w > geo.right():
            self.side = "left"
            pos.setX(widget.mapToGlobal(QPoint(0, 0)).x() - w)

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


class AttributeItem(QWidget):
    """
    A row item that shows an attribute name and a pill with the current value.
    """

    def __init__(self, label_text, enum_attr, unique_controls, objects_map, parent_dialog):
        super().__init__(parent_dialog.mainContent)
        self.label_text = label_text
        self.enum_attr = enum_attr
        self.unique_controls = unique_controls
        self.objects_map = objects_map
        self.parent_dialog = parent_dialog

        # Extract options and status
        any_obj = next(iter(objects_map.values()))
        self.is_enum = any_obj.get("type") == "enum"
        self.min_val = any_obj.get("min", 0)
        self.max_val = any_obj.get("max", 1)

        self.options = any_obj.get("enum", [])
        self.current_indices = {obj.get("current") for obj in objects_map.values()}
        self.current_idx = any_obj.get("current", 0)
        self.marked_indices = {idx for obj in objects_map.values() for idx in obj.get("marked", [])}
        self.gimbal_info = any_obj.get("gimbal", {})

        self.is_toggle = self.is_enum and len(self.options) <= 2
        self._hover_active = False
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self._setup_ui()

    def _setup_ui(self):
        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(util.DPI(6), util.DPI(6), util.DPI(6), util.DPI(6))
        self.main_layout.setSpacing(util.DPI(6))

        self.name_label = QLabel(self.label_text, self)
        self.name_label.setStyleSheet(f"color: {COLOR_TEXT_MAIN}; font-size: {util.DPI(11)}px;")
        self.name_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.pill_container = QWidget(self)
        self.pill_container.setFixedSize(util.DPI(60), util.DPI(16))
        self.pill_layout = QHBoxLayout(self.pill_container)
        self.pill_layout.setContentsMargins(util.DPI(2), 0, util.DPI(2), 0)
        self.pill_layout.setSpacing(util.DPI(2))

        # Indicator 'Ball' style
        self.sq_btn = QPushButton(self.pill_container)
        self.sq_btn.setFixedSize(util.DPI(12), util.DPI(12))
        self.sq_btn.setFocusPolicy(Qt.NoFocus)
        self.sq_btn.setAttribute(Qt.WA_TransparentForMouseEvents)

        self.val_label = QLabel(
            self.options[int(self.current_idx)] if self.is_enum and self.options else f"{self.current_idx:.2f}", self.pill_container
        )
        self.val_label.setStyleSheet(f"color: {COLOR_ACCENT_LIGHT}; font-size: {util.DPI(11)}px;")
        self.val_label.setAlignment(Qt.AlignCenter)

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
            QTimer.singleShot(0, self._update_numeric_ball_pos)

        self._refresh_pill_style()

        self.main_layout.addWidget(self.name_label, 1)
        self.main_layout.addWidget(self.pill_container)

        # Keep layout space but make transparent
        self.pill_opacity = QGraphicsOpacityEffect(self.pill_container)
        self.pill_container.setGraphicsEffect(self.pill_opacity)
        self.pill_opacity.setOpacity(0.0)

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
            icon_path = util.return_icon_path("globe.svg")

            pixmap = QPixmap(icon_path)
            if not pixmap.isNull():
                # Ensure sizes are integers
                target_size = int(util.DPI(12))
                if target_size < 1:
                    target_size = 12

                pixmap = pixmap.scaled(target_size, target_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)

                # Tint the icon
                tinted = QPixmap(pixmap.size())
                tinted.fill(Qt.transparent)
                painter = QPainter(tinted)
                painter.drawPixmap(0, 0, pixmap)
                painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
                painter.fillRect(tinted.rect(), QColor(ball_color))
                painter.end()

                self.sq_btn.setIcon(QIcon(tinted))
                self.sq_btn.setIconSize(QSize(target_size, target_size))
            else:
                # Basic dot fallback if SVG fails to load
                self.sq_btn.setIcon(QIcon())
                self.sq_btn.setStyleSheet(f"background: {ball_color}; border-radius: {int(util.DPI(6))}px; border: none;")
        else:
            self.sq_btn.setIcon(QIcon())
            self.sq_btn.setStyleSheet(f"background: {ball_color}; border-radius: {int(util.DPI(6))}px; border: none;")

        self.pill_container.setStyleSheet(f"background: {pill_bg}; border-radius: {util.DPI(8)}px;")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Draw row background as seen in reference
        rect = self.rect().adjusted(1, 1, -1, -1)
        bg_color = QColor(COLOR_ACCENT_MAIN)
        if self._hover_active:
            bg_color = QColor(COLOR_ACCENT_WHITE)

        painter.setBrush(QBrush(bg_color))
        painter.setPen(QPen(QColor("white"), 1))
        painter.drawRoundedRect(rect, 2, 2)

    def enterEvent(self, event):
        self._hover_active = True
        self.update()
        if self.parent_dialog:
            self.parent_dialog._handle_attr_hover(self)
            # Ensure parent interaction state is active when a row is hovered
            if hasattr(self.parent_dialog, "_update_interaction_state"):
                self.parent_dialog._update_interaction_state(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover_active = False
        self.update()
        if self.parent_dialog:
            self.parent_dialog._handle_attr_leave(self)
        super().leaveEvent(event)

    def on_select(self, idx, all_frames=None):
        self.current_idx = idx
        if self.is_enum:
            self.val_label.setText(self.options[int(idx)])
        else:
            self._update_numeric_ball_pos()
        self._refresh_pill_style()

        # Immediate scene apply if mode is specified (selection from popup)
        if all_frames is not None:
            # Find the required data mapping from the parent dialog
            options_map = None
            # For numeric, we don't use the standard options_map label lookup
            if not self.is_enum:
                # Construct a virtual entry for the value
                options_map = {
                    idx: {
                        "objects": list(self.objects_map.keys()),
                        "index": idx,
                        "attrs": {o: d["attr"] for o, d in self.objects_map.items()},
                    }
                }
            else:
                for (attr, _), (item, o_map) in self.parent_dialog._active_switch_widgets.items():
                    if item == self:
                        options_map = o_map
                        break

            if options_map:
                val = idx if not self.is_enum else self.options[int(idx)]
                self.parent_dialog._apply_attribute_switch(val, self.enum_attr, options_map, all_frames_override=all_frames)

    def currentText(self):
        return self.options[self.current_idx] if self.options else ""


# =================================================================================
#  4. SETUP DIALOGS
# =================================================================================


class SetupTargetsDialog(FloatingWidget):
    def __init__(self, parent, objects_dict, on_close):
        super().__init__(popup=False, parent=parent)
        self.on_close = on_close

        if parent and hasattr(parent, "_suspend_auto_close"):
            parent._suspend_auto_close()

        self.objects_dict = objects_dict
        self._create_layouts()
        self.setBottomBar(
            [base_widgets.DialogButton("Add", callback=self._add_target, icon=util.return_icon_path("add"), highlight=True)],
            closeButton=True,
            spacing=util.DPI(2),
        )

    def _add_target(self):
        for obj in cmds.ls(selection=True):
            self.targets_list.add_target(obj)

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

    def closeEvent(self, event):
        new_order = self.targets_list.backing_store

        new_dict = {}
        for t in new_order:
            new_dict[t] = self.objects_dict.get(t) or list(self.objects_dict.values())[0]

        self.objects_dict.clear()
        self.objects_dict.update(new_dict)

        if callable(self.on_close):
            self.on_close(self.objects_dict.keys())

        parent = self.parent()
        if parent and hasattr(parent, "_resume_auto_close"):
            parent._resume_auto_close()

        super().closeEvent(event)


class TargetItemWidget(QWidget):
    def __init__(self, name, list_ref):
        super().__init__()
        self.name = name
        self.list_ref = list_ref

        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(4)

        label = QLabel(name.split(":")[-1])
        close_btn = QPushButton()
        base_widgets.HoverableIcon.apply(close_btn, util.return_icon_path("close"))

        close_btn.setIconSize(QSize(15, 15))
        close_btn.setFixedSize(15, 15)
        close_btn.setFocusPolicy(Qt.NoFocus)
        close_btn.clicked.connect(self._remove)
        close_btn.setStyleSheet("""
            QPushButton {
                border: none;
                background: transparent;
                padding: 0px;
                margin: 0px;
            }
            QPushButton:pressed {
                background: {COLOR_BG_MAIN};
            }
            """)

        layout.addWidget(label)
        layout.addStretch()
        layout.addWidget(close_btn)

    def _remove(self):
        self.list_ref.remove_target(self.name)


class TargetsList(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.backing_store = []
        self.setStyleSheet("""
            QListWidget:focus {
                outline: none;
                border: none;
        }
        """)

    def add_target(self, name):
        if not cmds.objExists(name) or name in self.backing_store:
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
            if self.itemWidget(self.item(i)).name == name:
                self.takeItem(i)
                break


class Timeline(QWidget):
    def __init__(self, timerange=None, color=(200, 120, 200), autodestroy=300, parent=None):
        """
        Initializes the timeline marker.

        :param timerange: Tuple (start_frame, end_frame).
        :param color: Tuple (R, G, B | 0-255) default: purple.
        :param autodestroy: milliseconds before the marker == removed.
        """
        parent = parent or self.get_timeline()
        if not parent:
            return
        super().__init__(parent)

        self.timerange = timerange or [int(f) for f in cmds.timeControl("timeControl1", ra=1, q=True)]
        if not self.timerange:
            return

        args = list(color) + [70]
        self.color = QColor(*args)

        if parent:
            self.setGeometry(parent.rect())
            self.show()

            if autodestroy is not None:
                # Set up a timer to remove the marker
                self.timer = QTimer(self)
                self.timer.setSingleShot(True)
                self.timer.timeout.connect(self.delete_marker)
                self.timer.start(autodestroy)

    @classmethod
    def get_timeline(cls):
        """Fetches the Maya timeline widget."""
        tline = mel.eval("$tmpVar=$gPlayBackSlider")
        ptr = omui.MQtUtil.findControl(tline) or omui.MQtUtil.findLayout(tline) or omui.MQtUtil.findMenuItem(tline)
        if ptr:
            return util.get_maya_qt(ptr, QWidget)

    def paintEvent(self, event):
        """Handles painting the timeline marker on the playback slider."""
        if not self.timerange:
            return

        start = cmds.playbackOptions(q=True, minTime=True)
        end = cmds.playbackOptions(q=True, maxTime=True)
        total_width = self.width()
        step = (total_width - (total_width * 0.01)) / (end - start + 1)

        sframe, eframe = self.timerange
        eframe -= 1  # Adjust to be within range

        pos_start = (sframe - start) * step + (total_width * 0.005)
        pos_end = (eframe + 1 - start) * step + (total_width * 0.005)
        rect = QRectF(QPointF(pos_start, 0), QPointF(pos_end, self.height()))

        painter = QPainter(self)
        pen = QPen(self.color)
        pen.setWidth(step + step * 0.005)

        painter.setPen(pen)
        painter.fillRect(rect, QBrush(self.color))

    def delete_marker(self):
        """Removes the marker safely."""
        try:
            self.setParent(None)
            self.deleteLater()
        except RuntimeError:
            pass


# =================================================================================
#  5. APPLICATION (SPACE SWITCH)
# =================================================================================


class SpaceSwitchAlehaWidget(FloatingWidget):
    ROTATE_ORDER_OPTIONS = ["xyz", "yzx", "zxy", "xzy", "yxz", "zyx"]

    """
    The main widget for the Space Switch tool, now with configurable modes.
    """

    def __init__(self, popup=False, parent=None):
        parent = parent or util.get_maya_qt()
        super().__init__(popup=popup, parent=parent)

        self._active_popup = None
        self._popup_pending_item = None
        self._is_ui_hovered = False
        self._popup_timer = QTimer(self)
        self._popup_timer.setSingleShot(True)
        self._popup_timer.setInterval(100)
        self._popup_timer.timeout.connect(self._show_pending_popup)
        self.settings = QSettings(DATA.get("AUTHOR", {}).get("NAME"), DATA.get("TOOL"))
        self._load_persistent_settings()

        self.analyzer = GimbalAnalyzer()
        self._cb = CallbackManager()

        self._create_layouts()
        self._create_selection_layout()
        self._add_callbacks()

        self._active_switch_widgets = {}
        self._previous_selection = []

        self.refresh()

    def closeEvent(self, e):
        self._cb.clear()
        super().closeEvent(e)
        self.deleteLater()

    # =================================================================================
    #  2. UI CONSTRUCTION & LIFECYCLE
    # =================================================================================

    def _create_layouts(self):
        """Builds the main container layouts."""
        self.mainContent.setMinimumWidth(util.DPI(220))
        self.mainContent.setContextMenuPolicy(Qt.CustomContextMenu)
        self.mainContent.customContextMenuRequested.connect(self._show_context_menu)

        self.enums_layout = QVBoxLayout()
        self.enums_layout.setSpacing(util.DPI(1))

        self.mainLayout.addLayout(self.enums_layout)
        self.mainLayout.addStretch(1)

    def _create_selection_layout(self):
        """Builds the header area showing tool title and current status."""
        selection_layout = QVBoxLayout()
        selection_layout.setSpacing(util.DPI(5))
        selection_layout.setContentsMargins(0, util.DPI(6), 0, util.DPI(8))

        selection_title = QLabel("Selection")
        selection_title.setStyleSheet("font-size: %spx; color: %s; font-weight: bold; background: transparent;" % (util.DPI(18), self.TEXT_COLOR))
        selection_title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        selection_title.setWordWrap(False)
        selection_title.setFixedHeight(selection_title.fontMetrics().height() + 2)

        self.selection_label = QLabel("No switches for selection")
        self.selection_label.setStyleSheet("color: %s; background: transparent;" % self.TEXT_COLOR)

        selection_layout.addWidget(selection_title)
        selection_layout.addWidget(self.selection_label)

        self.mainLayout.insertLayout(0, selection_layout)

    def _refresh_footer(self):
        """Updates the interaction bar based on whether valid switches exist."""
        # Show Close only if not in popup mode (pinned)
        should_close = not self._auto_close_active
        self.setBottomBar(closeButton=should_close)

    def _clear_layout(self, layout):
        """Recursively clears a layout of all its child widgets."""
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
            if child.layout():
                self._clear_layout(child.layout())

    # =================================================================================
    # 3. STATE & SETTINGS
    # =================================================================================

    def _load_persistent_settings(self):
        """Loads user preferences from local storage."""
        self.namespace_display = self.__fix_setting(self.settings.value("namespace_display", False))
        self.all_frames = self.__fix_setting(self.settings.value("all_frames", False))
        self.euler_filter = self.__fix_setting(self.settings.value("euler_filter", True))
        self.show_rotate_order = self.__fix_setting(self.settings.value("show_rotate_order", True))

    @staticmethod
    def __fix_setting(setting):
        if isinstance(setting, bool):
            return setting
        elif isinstance(setting, int):
            return bool(setting)
        elif isinstance(setting, str):
            return setting.lower() == "true"
        else:
            return False

    def set_setting(self, setting, state, refresh=False):
        self.settings.setValue(setting, state)
        setattr(self, setting, state)

        if refresh:
            self.refresh(force=True)

    # =================================================================================
    # 4. MAYA INTEGRATION
    # =================================================================================

    def _add_callbacks(self):
        try:
            self._cb.add(om.MEventMessage.addEventCallback("SelectionChanged", self.refresh))
            self._cb.add(om.MEventMessage.addEventCallback("timeChanged", self.refresh))
            self._cb.add(om.MEventMessage.addEventCallback("Undo", self.refresh))

            self._cb.add(om.MSceneMessage.addCallback(om.MSceneMessage.kAfterOpen, self._refresh_callbacks))
        except Exception as e:
            cmds.warning("Could not add Maya callbacks: %s" % e)

    def apply_active_changes(self):
        """Commits all currently selected enum values to the scene."""
        for (enum_attr, _), (attr_item, options_and_objects) in self._active_switch_widgets.items():
            enum_value = attr_item.currentText()
            self._apply_attribute_switch(enum_value, enum_attr, options_and_objects)

    def _remove_callbacks(self):
        try:
            self._cb.clear()
        except Exception as e:
            cmds.warning("Could not remove Maya callbacks: %s" % e)

    def _refresh_callbacks(self, *args):
        self._remove_callbacks()
        self._add_callbacks()

    def _get_selected_nodes(self, long=False):
        """Returns the current Maya selection."""
        return cmds.ls(selection=True, long=long)

    def _fetch_attribute_data(self):
        """Analyzes active selection for compatible space-switch attributes and returns structured data."""
        attr_catalog = {}

        def _is_connected(node, attr):
            plug = "%s.%s" % (node, attr)
            try:
                if cmds.connectionInfo(plug, isDestination=True) or cmds.connectionInfo(plug, isSource=True):
                    return True
                return bool(cmds.listConnections(plug, s=True, d=True, plugs=True) or [])
            except Exception:
                return False

        for node in self._previous_selection:
            # Only user-defined attrs (excludes Maya defaults), but allow rotateOrder if requested
            ordered_attrs = cmds.listAttr(node, ud=True) or []
            if self.show_rotate_order and cmds.attributeQuery("rotateOrder", node=node, exists=True):
                if "rotateOrder" not in ordered_attrs:
                    ordered_attrs.append("rotateOrder")

            if ordered_attrs:
                for enum_attr in ordered_attrs:
                    try:
                        attr_type = cmds.attributeQuery(enum_attr, node=node, attributeType=True)
                    except Exception:
                        continue

                    is_enum = attr_type == "enum"
                    is_numeric = attr_type in ["bool", "long", "double", "float"]

                    if not is_enum and not is_numeric:
                        continue

                    enum_values_clean = []
                    min_val, max_val = 0, 0

                    if is_enum:
                        raw = cmds.attributeQuery(enum_attr, node=node, listEnum=True) or []
                        if not raw:
                            continue

                        # Clean labels
                        enum_values_raw = raw[0].split(":")
                        for v in enum_values_raw:
                            label = v.split("=", 1)[0].strip()
                            if any(c.isalnum() for c in label):
                                enum_values_clean.append(label)

                        if len(set(enum_values_clean)) < 2:
                            continue
                    else:
                        if attr_type == "bool":
                            min_val, max_val = 0, 1
                        else:
                            if not (
                                cmds.attributeQuery(enum_attr, node=node, minExists=True)
                                and cmds.attributeQuery(enum_attr, node=node, maxExists=True)
                            ):
                                continue
                            min_val = cmds.attributeQuery(enum_attr, node=node, minimum=True)[0]
                            max_val = cmds.attributeQuery(enum_attr, node=node, maximum=True)[0]

                    # Must be connected to something (unless it's rotateOrder)
                    if enum_attr != "rotateOrder" and not _is_connected(node, enum_attr):
                        continue

                    catalog_key = enum_attr
                    if attr_type == "enum":
                        if enum_attr != "rotateOrder":
                            # Case-insensitive comparison of enum labels to detect rotation order copies
                            current_opts = [o.lower() for o in enum_values_clean]
                            if current_opts == [r.lower() for r in self.ROTATE_ORDER_OPTIONS]:
                                catalog_key = "rotateOrder"

                    long_name = cmds.attributeQuery(enum_attr, node=node, niceName=True)

                    if catalog_key not in attr_catalog.keys():
                        attr_catalog[catalog_key] = {
                            "objects": {},
                            "long": long_name,
                        }

                    # If this node already has an attribute contributing to this catalog key,
                    # avoid duplication. Prioritize the native 'rotateOrder' if it appears.
                    if node in attr_catalog[catalog_key]["objects"]:
                        if enum_attr == "rotateOrder":
                            attr_catalog[catalog_key]["objects"][node]["attr"] = enum_attr
                        continue

                    attr_catalog[catalog_key]["objects"][node] = {
                        "enum": enum_values_clean,
                        "marked": [],
                        "current": [],
                        "attr": enum_attr,
                        "type": attr_type,
                        "min": float(min_val),
                        "max": float(max_val),
                    }

                    # Keyed values and current
                    keys = cmds.keyframe("%s.%s" % (node, enum_attr), query=True, valueChange=True) or []
                    attr_catalog[catalog_key]["objects"][node]["marked"] = list(set(float(x) for x in keys)) or [
                        float(cmds.getAttr("%s.%s" % (node, enum_attr)))
                    ]
                    attr_catalog[catalog_key]["objects"][node]["current"] = float(cmds.getAttr("%s.%s" % (node, enum_attr)))

                    # If it's effectively rotateOrder and requested, analyze gimbal
                    if catalog_key == "rotateOrder" and self.show_rotate_order:
                        gimbal_data = self.analyzer.analyze(node)
                        attr_catalog[catalog_key]["objects"][node]["gimbal"] = gimbal_data

        return attr_catalog

    # =================================================================================
    #  6. INTERACTION & HOVER LOGIC
    # =================================================================================

    def _update_interaction_state(self, is_active, force=False):
        """Unified interaction management for multi-window focus tracking."""
        if not is_active:
            cursor_pos = QCursor.pos()
            if util.is_valid_widget(self) and self.frameGeometry().contains(cursor_pos):
                is_active = True
            if not is_active and self._active_popup and util.is_valid_widget(self._active_popup) and self._active_popup.isVisible():
                if self._active_popup.frameGeometry().contains(cursor_pos):
                    is_active = True

        if not force and self._is_ui_hovered == is_active:
            return

        self._is_ui_hovered = is_active

        # Toggle auto-close based on interaction
        if self._is_ui_hovered:
            self._auto_close_timer.stop()
        else:
            self._resume_auto_close()

        for (enum_attr, _), (attr_item, _) in self._active_switch_widgets.items():
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
        super().enterEvent(event)

    def leaveEvent(self, event):
        # Small delay to see if we moved to the popup or just left
        QTimer.singleShot(150, lambda: self._update_interaction_state(False))
        super().leaveEvent(event)

    def _handle_attr_hover(self, item):
        self._popup_pending_item = item
        self._popup_timer.start()

    def _handle_attr_leave(self, item):
        # Delay hiding to allow transition
        if self._popup_pending_item == item:
            self._popup_pending_item = None
        self._popup_timer.start()

    def _show_pending_popup(self):
        """Displays the attribute choice popup beside the hovered row."""
        # If no pending item or it was deleted, hide current
        if not self._popup_pending_item or not util.is_valid_widget(self._popup_pending_item):
            if self._active_popup and util.is_valid_widget(self._active_popup) and not self._active_popup.underMouse():
                self._active_popup.hide()
            elif self._active_popup and util.is_valid_widget(self._active_popup) and self._active_popup.underMouse():
                pass
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

        self._active_popup = AttributePopup(item, item.options, item.current_idx, item.current_indices, item.marked_indices, item.on_select)
        self._active_popup.show_beside(item)
        item._hover_active = True
        item.update()

    def _close_active_popup(self):
        """Safely removes the current popup."""
        if hasattr(self, "_active_popup") and self._active_popup and util.is_valid_widget(self._active_popup):
            self._active_popup.hide()
            self._active_popup.deleteLater()
            self._active_popup = None

    # =================================================================================
    #  8. HELPERS
    # =================================================================================

    def _format_object_name(self, objects):
        """Returns a human-friendly string for one or multiple objects."""
        if not objects:
            return ""
        if len(objects) == 1:
            name = objects[0].split("|")[-1]
            if ":" in name and not self.namespace_display:
                name = name.split(":")[-1]
            return ("..." + name[:50]) if len(name) > 50 else name
        return "(%s)" % len(objects)

    @staticmethod
    def formatXformTooltipObjects(objects):
        """Formats the HTML tooltip for target objects."""
        return "<html>Current xform target/s:<br>%s<br><br><b>Right-click to modify...</b></html>" % "<br>".join(objects)

    # =================================================================================
    #  5. REFRESH & UPDATE LOGIC
    # =================================================================================

    def refresh(self, timeChange=False, force=False, *args):
        """Main update orchestration. Synchronizes UI state with current Maya selection."""
        if timeChange:
            return

        self._close_active_popup()
        current_sel = self._get_selected_nodes(long=False)

        # Detect selection change or forced refresh
        selection_is_same = sorted(current_sel) == sorted(self._previous_selection)
        if selection_is_same and not force:
            self._refresh_footer()
            return

        self._previous_selection = current_sel
        self._rebuild_active_widgets()

    def _rebuild_active_widgets(self):
        """Fetches data and replaces existing UI elements with new switch widgets."""
        self._clear_layout(self.enums_layout)
        self._active_switch_widgets.clear()

        if not self._previous_selection:
            self.selection_label.setVisible(True)
            self.adjustSize()
            self._refresh_footer()
            return

        try:
            self._switch_data = self._fetch_attribute_data()
            if not self._switch_data:
                self.selection_label.setVisible(True)
            else:
                self.selection_label.setVisible(False)
                for enum_name, data in self._switch_data.items():
                    self._create_switch_item(enum_name, data)

        except Exception as e:
            cmds.warning(f"Error rebuilding SpaceSwitch widgets: {e}")
        finally:
            self._update_interaction_state(self._is_ui_hovered, force=True)
            self._refresh_footer()
            self.adjustSize()

    def _create_switch_item(self, enum_name, data):
        """Instantiates and registers a single AttributeItem based on provided metadata."""
        target_nodes = sorted(data["objects"].keys())
        display_name = self._format_object_name(target_nodes)

        attr_item = AttributeItem(
            f"{display_name} {data['long'].title()}",
            enum_name,
            target_nodes,
            data["objects"],
            self,
        )

        attr_item.setToolTip(self.formatXformTooltipObjects(target_nodes))
        attr_item.setContextMenuPolicy(Qt.CustomContextMenu)
        attr_item.customContextMenuRequested.connect(lambda pos, s=attr_item, d=data: self._show_change_target_dialog(s, d))

        options_map = self._build_options_map(data["objects"])
        self._active_switch_widgets[(enum_name, tuple(target_nodes))] = (attr_item, options_map)
        self.enums_layout.insertWidget(0, attr_item)

    def _build_options_map(self, objects_data):
        """Constructs a mapping of enum options to their respective object target sets."""
        options_map = {}
        for obj, data in objects_data.items():
            for i, o in enumerate(data["enum"]):
                entry = options_map.setdefault(o, {"objects": [], "index": i, "attrs": {}})
                entry["objects"].append(obj)
                entry["attrs"][obj] = data.get("attr")
        return options_map

    @staticmethod
    def do_xform(target, enum_attr, enum_value, xform=None):
        xform = xform or cmds.xform(target, q=True, ws=True, matrix=True)
        cmds.setAttr(("{}.{}").format(target, enum_attr), enum_value)
        cmds.xform(target, ws=True, matrix=xform)

    def multiple_frames(self, enum_attr, enum_value, keyframes, target_attrs=None):
        marker_widget = None

        try:
            # Color timeline
            timerange = [list(keyframes.keys())[0], list(keyframes.keys())[-1] + 1]
            if cmds.timeControl("timeControl1", q=1, rv=1):
                timerange = [int(f) for f in cmds.timeControl("timeControl1", ra=1, q=True)]

            if int(cmds.about(v=1)) >= 2024:
                cmds.playbackOptions(sv=False)

            marker_widget = Timeline(timerange)

            # Start Progress Bar
            gMainProgressBar = mel.eval("$tmp = $gMainProgressBar")
            bar_value = 1
            max_bar_value = len(keyframes.keys())
            cmds.progressBar(gMainProgressBar, e=True, bp=True, max=max_bar_value)

            dictionary_xforms = {}
            current_time = cmds.currentTime(q=True)
            for frame, targets in keyframes.items():
                cmds.currentTime(frame)
                dictionary_xforms[frame] = {}
                for t in targets:
                    dictionary_xforms[frame][t] = cmds.xform(t, q=True, ws=True, matrix=True)
                cmds.progressBar(
                    gMainProgressBar,
                    edit=True,
                    status="Saving Positions (%s/%s)..." % (bar_value, max_bar_value),
                    step=1,
                )
                bar_value += 1
            bar_value = 1
            cmds.progressBar(gMainProgressBar, e=True, ep=True)
            cmds.progressBar(gMainProgressBar, e=True, bp=True, max=max_bar_value)
            for frame, targets in dictionary_xforms.items():
                for target, xform in targets.items():
                    cmds.currentTime(frame)
                    attr = target_attrs[target] if target_attrs else enum_attr
                    self.do_xform(target, attr, enum_value, xform)
                    cmds.progressBar(
                        gMainProgressBar,
                        edit=True,
                        status="Applying Positions (%s/%s)..." % (bar_value, max_bar_value),
                        step=1,
                    )
                    bar_value += 1

            cmds.currentTime(current_time)
            cmds.progressBar(gMainProgressBar, e=True, ep=True)

        finally:
            if marker_widget:
                marker_widget.delete_marker()

    @staticmethod
    def _collect_keyframes(targets, all_frames, timeline_selection, current_frames):
        if not timeline_selection and not all_frames:
            return targets, [cmds.currentTime(query=True)]

        # Gather all keyframes across targets
        all_keys = set(sum([cmds.keyframe(t, query=True) or [] for t in targets], []))
        keyframes = {frame: [t for t in targets if frame in (cmds.keyframe(t, query=True) or [])] for frame in sorted(all_keys)}

        # Restrict to timeline selection range if active
        if timeline_selection:
            keyframes = {f: objs for f, objs in keyframes.items() if current_frames[0] <= f <= current_frames[1]}

        return keyframes

    def _apply_attribute_switch(self, enum_value, enum_attr, options_and_objects, all_frames_override=None):
        all_frames_setting = all_frames_override if all_frames_override is not None else self.all_frames

        # Special case: rotateOrder always applies to all frames
        if enum_attr == "rotateOrder":
            if isinstance(enum_value, (str, bytes)) and " " in enum_value.strip():
                enum_value = enum_value.split(" ")[0]
            all_frames_setting = True

        targets = options_and_objects[enum_value]["objects"]
        target_attrs = options_and_objects[enum_value]["attrs"]
        enum_index = options_and_objects[enum_value].get("index", enum_value)

        cmds.undoInfo(openChunk=True)
        cmds.refresh(suspend=True)
        self._remove_callbacks()

        # Save temporary keys
        temp_keyframes = {}

        timeline_selection = cmds.timeControl("timeControl1", q=True, rv=True)
        current_frames = cmds.timeControl("timeControl1", q=True, ra=True)

        keyframes = self._collect_keyframes(targets, all_frames_setting, timeline_selection, current_frames)
        sorted_targets = sorted(targets, key=lambda x: x.count("|"), reverse=True)

        try:
            if sorted_targets:
                # Case 1: dict - multiple frames
                if isinstance(keyframes, dict) and keyframes:
                    self.multiple_frames(enum_attr, enum_index, keyframes, target_attrs)

                # Case 2: list - single frame
                elif isinstance(keyframes, list) and keyframes:
                    cmds.currentTime(keyframes[0])
                    for target in sorted_targets:
                        self.do_xform(target, target_attrs[target], enum_index)

                # Case 3: no explicit keys - create temp key only if attr has none
                else:
                    current_time = cmds.currentTime(query=True)
                    for target in sorted_targets:
                        attr_name = target_attrs[target]
                        attr_plug = "%s.%s" % (target, attr_name)
                        existing_keys = cmds.keyframe(attr_plug, query=True, keyframeCount=True) or 0

                        if existing_keys == 0:
                            temp_keyframes.setdefault(target, {}).setdefault(attr_name, []).append(current_time)
                            cmds.keyframe(attr_plug)

                        self.do_xform(target, attr_name, enum_index)

            if self.euler_filter:
                self.apply_euler_filter(sorted_targets)

        finally:
            cmds.refresh(suspend=False)

            # Remove temporary keys if created
            for target, attributes in temp_keyframes.items():
                for attr, keys in attributes.items():
                    for frame in keys:
                        cmds.cutKey("%s.%s" % (target, attr), time=(frame,))

            self._add_callbacks()
            self.refresh(force=True)
            cmds.undoInfo(closeChunk=True)

        cmds.showWindow("MayaWindow")

    def apply_euler_filter(self, targets):
        anim_curves = []

        for target in targets:
            for attr in ["rx", "ry", "rz"]:
                attribute = "%s.%s" % (target, attr)
                if cmds.objExists(attribute):
                    anim_curve = cmds.listConnections(attribute, source=True, type="animCurve")
                    if anim_curve:
                        anim_curve = anim_curve[0]
                        if cmds.objExists(anim_curve):
                            anim_curves.append(anim_curve)

        anim_curves = list(set(anim_curves))
        cmds.filterCurve(*anim_curves)

    def _show_context_menu(self, pos):
        """Displays global tool configuration menu."""
        self.context_menu = QMenu(self)
        self.context_menu.aboutToShow.connect(self._suspend_auto_close)
        self.context_menu.aboutToHide.connect(self._resume_auto_close)

        self.toggle_namespaces_action = self.context_menu.addAction("Show namespaces")
        self.toggle_namespaces_action.setCheckable(True)
        self.toggle_namespaces_action.setChecked(self.namespace_display)

        self.show_rotate_order_action = self.context_menu.addAction("Enable Rotate Order")
        self.show_rotate_order_action.setCheckable(True)
        self.show_rotate_order_action.setChecked(self.show_rotate_order)

        self.context_menu.addSeparator()

        self.euler_filter_action = self.context_menu.addAction("Auto Euler Filter")
        self.euler_filter_action.setCheckable(True)
        self.euler_filter_action.setChecked(self.euler_filter)

        self.context_menu.addSeparator()
        self.about_action = self.context_menu.addAction("About")
        self.about_action.setIcon(QIcon(util.return_icon_path("info")))
        self.about_action.triggered.connect(self.show_credits_dialog)

        self.show_rotate_order_action.toggled.connect(lambda state: self.set_setting("show_rotate_order", state, refresh=True))
        self.toggle_namespaces_action.toggled.connect(lambda state: self.set_setting("namespace_display", state, refresh=True))
        self.euler_filter_action.toggled.connect(lambda state: self.set_setting("euler_filter", state))

        exec_fn = getattr(self.context_menu, "exec", None) or getattr(self.context_menu, "exec_", None)
        exec_fn(QCursor.pos())

    def _show_change_target_dialog(self, sender, data):
        """Opens the UI for multi-target management."""
        selection = self._get_selected_nodes(long=False)

        def on_close(objects):
            cmds.select(selection, replace=True)
            self._add_callbacks()
            sender.setToolTip(self.formatXformTooltipObjects(objects))

        objects_dict = data["objects"]
        self._remove_callbacks()
        dlg = SetupTargetsDialog(self, objects_dict, on_close=on_close)
        dlg.show()

    def show_credits_dialog(self):
        """Displays credits/donation dialog."""
        self._suspend_auto_close()
        widgets.Coffee.showUI(self, data=DATA)
        if widgets.Coffee._instance:
            widgets.Coffee._instance.finished.connect(lambda *args: self._resume_auto_close())

    # =================================================================================
    #  7. APPLICATION ACTIONS
    # =================================================================================


# =================================================================================
#  6. ENTRY POINTS & MANAGER
# =================================================================================


class SpaceSwitchManager:
    """
    Manages the creation and display of the SpaceSwitchAlehaWidget instance.
    """

    @classmethod
    def _launch(cls, popup):
        dlg = _MAIN_DICT.get("_SPACESWITCH_INSTANCE")
        if dlg is not None and util.is_valid_widget(dlg):
            try:
                dlg._cb.clear()
                dlg.close()
            finally:
                dlg = None

        if not (dlg is not None and util.is_valid_widget(dlg)):
            dlg = SpaceSwitchAlehaWidget(popup=popup)
            _MAIN_DICT["_SPACESWITCH_INSTANCE"] = dlg

        if popup:
            dlg.place_near_cursor()

        if dlg.isHidden():
            dlg.show()
        else:
            dlg.raise_()
            dlg.activateWindow()

    @classmethod
    def popup(cls):
        """Launches the tool as a temporary popup near the cursor with auto-close enabled."""
        cls._launch(popup=True)

    @classmethod
    def show(cls):
        """Launches the tool as a persistent window with the bottom bar visible."""
        cls._launch(popup=False)


def show():
    """Entry point to launch SpaceSwitch in pinned mode."""
    SpaceSwitchManager.show()


def popup():
    """Entry point to launch SpaceSwitch in popup mode."""
    SpaceSwitchManager.popup()
