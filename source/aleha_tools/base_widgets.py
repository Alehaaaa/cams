try:
    from PySide6.QtWidgets import (  # type: ignore
        QWidget,
        QHBoxLayout,
        QVBoxLayout,
        QLabel,
        QPushButton,
        QDialog,
        QFrame,
        QSizePolicy,
        QLayout,
        QMenu,
        QApplication,
    )
    from PySide6.QtGui import (  # type: ignore
        QIcon,
        QColor,
        QPixmap,
        QPainter,
        QPolygonF,
        QCursor,
        QGuiApplication,
        QMovie,
        QFontMetrics,
    )
    from PySide6.QtCore import (  # type: ignore
        Qt,
        QSize,
        QEventLoop,
        QPoint,
        QPointF,
        QTimer,
        QRect,
    )
except ImportError:
    from PySide2.QtWidgets import (
        QWidget,
        QHBoxLayout,
        QVBoxLayout,
        QLabel,
        QPushButton,
        QDialog,
        QFrame,
        QSizePolicy,
        QLayout,
        QMenu,
        QApplication,
    )
    from PySide2.QtGui import (
        QIcon,
        QColor,
        QPixmap,
        QPainter,
        QPolygonF,
        QCursor,
        QGuiApplication,
        QMovie,
        QFontMetrics,
    )
    from PySide2.QtCore import (
        Qt,
        QSize,
        QEventLoop,
        QPoint,
        QPointF,
        QTimer,
        QRect,
    )

from functools import partial
import sys
import xml.etree.ElementTree as ET
from .util import (
    DPI,
    return_icon_path,
    get_maya_qt,
)


class DialogButton(dict):
    """A dictionary subclass that supports the | operator to return a list of buttons."""

    def __init__(self, name_or_dict=None, **kwargs):
        if name_or_dict is not None:
            if isinstance(name_or_dict, (str, bytes)):
                kwargs["name"] = name_or_dict
                super().__init__(**kwargs)
            elif isinstance(name_or_dict, dict):
                super().__init__(name_or_dict, **kwargs)
            else:
                super().__init__(**kwargs)
        else:
            super().__init__(**kwargs)

    def copy(self):
        return DialogButton(super().copy())

    def __eq__(self, other):
        if isinstance(other, (str, bytes)):
            return self.get("name") == other
        return super().__eq__(other)

    def __ne__(self, other):
        return not self.__eq__(other)

    def __or__(self, other):
        if isinstance(other, (dict, DialogButton)):
            return DialogButtonList([self, other])
        if isinstance(other, list):
            return DialogButtonList([self] + other)
        # Support dict union for Python 3.9+ if available
        if hasattr(super(), "__or__"):
            return super().__or__(other)
        return NotImplemented

    def __ror__(self, other):
        if isinstance(other, list):
            return DialogButtonList(other + [self])
        if hasattr(super(), "__ror__"):
            return super().__ror__(other)
        return NotImplemented


class DialogButtonList(list):
    """A list subclass that supports the | operator to combine buttons."""

    def __or__(self, other):
        if isinstance(other, (dict, DialogButton)):
            return DialogButtonList(self + [other])
        if isinstance(other, list):
            return DialogButtonList(self + other)
        return self


class HoverableIcon:
    HIGHLIGHT_HEX = "#282828"

    @staticmethod
    def apply(btn, icon_path, highlight=False, brighten_amount=80):
        base_icon = QIcon(icon_path)
        if highlight:
            btn._icon_normal = HoverableIcon._color_icon(base_icon, HoverableIcon.HIGHLIGHT_HEX, btn.iconSize())
        else:
            btn._icon_normal = base_icon

        btn._icon_hover = HoverableIcon._brighten_icon(btn._icon_normal, brighten_amount, btn.iconSize())

        btn.setIcon(btn._icon_normal)

        prev_enter = btn.enterEvent
        prev_leave = btn.leaveEvent

        def enterEvent(event):
            btn.setIcon(btn._icon_hover)
            if prev_enter:
                return prev_enter(event)

        def leaveEvent(event):
            btn.setIcon(btn._icon_normal)
            if prev_leave:
                return prev_leave(event)

        btn.enterEvent = enterEvent
        btn.leaveEvent = leaveEvent

    @staticmethod
    def _color_icon(icon, color, size):
        if isinstance(color, (str, bytes)):
            color = QColor(color)

        pix = icon.pixmap(size)
        img = pix.toImage()
        for x in range(img.width()):
            for y in range(img.height()):
                c = img.pixelColor(x, y)
                if c.alpha() > 0:
                    img.setPixelColor(x, y, QColor(color.red(), color.green(), color.blue(), c.alpha()))

        return QIcon(QPixmap.fromImage(img))

    @staticmethod
    def _brighten_icon(icon, amount, size):
        pix = icon.pixmap(size)
        img = pix.toImage()
        for x in range(img.width()):
            for y in range(img.height()):
                c = img.pixelColor(x, y)
                img.setPixelColor(
                    x,
                    y,
                    QColor(
                        min(c.red() + amount, 255),
                        min(c.green() + amount, 255),
                        min(c.blue() + amount, 255),
                        c.alpha(),
                    ),
                )
        return QIcon(QPixmap.fromImage(img))


class FlatButton(QPushButton):
    """A customizable, flat-styled button for the bottom bar."""

    STYLE_SHEET = """
        QPushButton {
            color: %s;
            background-color: %s;
            border-radius: %spx;
            padding: %spx %spx;
            font-weight: %s;
            font-size: %spx;
        }
        QPushButton:hover {
            background-color: %s;
        }
        QPushButton:pressed {
            background-color: %s;
        }
    """

    DEFAULT_COLOR = "#ffffff"
    DEFAULT_BACKGROUND = "#5D5D5D"
    DEFAULT_HOVER_BACKGROUND = "#707070"
    DEFAULT_PRESSED_BACKGROUND = "#252525"

    HIGHLIGHT_COLOR = "#282828"
    HIGHLIGHT_BACKGROUND = "#bdbdbd"
    HIGHLIGHT_HOVER_BACKGROUND = "#cfcfcf"
    HIGHLIGHT_PRESSED_BACKGROUND = "#707070"

    DEFAULT_FONT_SIZE = DPI(12)
    HIGHLIGHT_FONT_SIZE = DPI(15)

    BUTTON_BORDER_RADIUS = DPI(9)

    def __init__(
        self,
        text,
        color=DEFAULT_COLOR,
        background=DEFAULT_BACKGROUND,
        icon_path=None,
        border=BUTTON_BORDER_RADIUS,
        highlight=False,
        parent=None,
    ):
        super().__init__(text, parent)
        self.setFlat(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(DPI(34))

        # Consistent Icon Size
        self.setIconSize(QSize(DPI(19), DPI(19)))
        if icon_path:
            HoverableIcon.apply(self, icon_path, highlight=highlight)

        v_padding = 2  # Tight padding since height is fixed

        if highlight:
            color = self.HIGHLIGHT_COLOR
            background = self.HIGHLIGHT_BACKGROUND
            hover_background = self.HIGHLIGHT_HOVER_BACKGROUND
            pressed_background = self.HIGHLIGHT_PRESSED_BACKGROUND
            font_size = self.HIGHLIGHT_FONT_SIZE
            weight = "bold"
        elif background != self.DEFAULT_BACKGROUND:
            try:
                base_background = int(background.lstrip("#"), 16)
                r, g, b = (
                    (base_background >> 16) & 0xFF,
                    (base_background >> 8) & 0xFF,
                    base_background & 0xFF,
                )
            except Exception:
                r, g, b = 93, 93, 93
            hover_background = "#%02x%02x%02x" % (min(r + 10, 255), min(g + 10, 255), min(b + 10, 255))
            pressed_background = "#%02x%02x%02x" % (max(r - 10, 0), max(g - 10, 0), max(b - 10, 0))
            font_size = self.DEFAULT_FONT_SIZE
            weight = "normal"
        else:
            hover_background = self.DEFAULT_HOVER_BACKGROUND
            pressed_background = self.DEFAULT_PRESSED_BACKGROUND
            font_size = self.DEFAULT_FONT_SIZE
            weight = "normal"

        actual_border = min(int(border), int(DPI(34)) // 2)

        self.setStyleSheet(
            self.STYLE_SHEET
            % (
                color,
                background,
                actual_border,
                int(DPI(v_padding)),
                int(DPI(12)),
                weight,
                int(font_size),
                hover_background,
                pressed_background,
            )
        )


class BottomBar(QFrame):
    """
    A container widget for arranging FlatButtons horizontally.
    """

    def __init__(self, buttons=[], margins=8, spacing=6, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(DPI(margins), DPI(margins), DPI(margins), DPI(margins))
        layout.setSpacing(DPI(spacing))

        for button in buttons:
            layout.addWidget(button)


class QFlatDialog(QDialog):
    # Button Preconfigurations
    Yes = DialogButton("Yes", positive=True, icon=return_icon_path("apply"))
    Ok = DialogButton("Ok", positive=True, icon=return_icon_path("apply"))

    No = DialogButton("No", positive=False, icon=return_icon_path("cancel"))
    Cancel = DialogButton("Cancel", positive=False, icon=return_icon_path("cancel"))
    Close = DialogButton("Close", positive=False, icon=return_icon_path("close"))

    CustomButton = DialogButton

    def __init__(self, parent=None, buttons=None, highlight=None, closeButton=False):
        if parent is None:
            parent = get_maya_qt()

        super().__init__(parent)
        if sys.platform != "win32":
            self.setWindowFlags(self.windowFlags() | Qt.Tool)

        self.root_layout = QVBoxLayout(self)
        self.root_layout.setSizeConstraint(QLayout.SetMinAndMaxSize)
        self.root_layout.setContentsMargins(0, 0, 0, 0)
        self.root_layout.setSpacing(0)

        self.bottomBar = None

        self._highlighted = highlight
        self._buttons_to_init = buttons
        self._default_button = None

    def _buttonConfigHook(self, index, config):
        """Hook for subclasses to modify button configuration before creation."""
        return config

    def _defineButtons(self, buttons):
        created_buttons = []
        for i, btn_data in enumerate(buttons):
            if isinstance(btn_data, (str, bytes)):
                config = DialogButton(btn_data)
            else:
                config = btn_data.copy()

            config = self._buttonConfigHook(i, config)

            # Handle automatic highlighting if matches highlight name or dict
            is_highlighted = config.get("highlight", False)
            if self._highlighted:
                if btn_data == self._highlighted or config.get("name") == self._highlighted:
                    is_highlighted = True

            btn = FlatButton(
                text=config.get("name", "Button"),
                background=config.get("background", "#5D5D5D"),
                icon_path=config.get("icon"),
                highlight=is_highlighted,
            )

            # Connect callback if provided
            callback = config.get("callback")
            if callback and callable(callback):
                btn.clicked.connect(callback)

            if is_highlighted:
                btn.setAutoDefault(True)
                btn.setDefault(True)
                self._default_button = btn

            created_buttons.append(btn)
        return created_buttons

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if self._default_button:
                self._default_button.click()
                return
        super().keyPressEvent(event)

    def setBottomBar(self, buttons=None, margins=8, spacing=6, closeButton=False, highlight=None):
        """Dynamically creates and adds a bottom bar with custom buttons."""
        if self.bottomBar:
            self.root_layout.removeWidget(self.bottomBar)
            self.bottomBar.setParent(None)
            self.bottomBar.deleteLater()
            self.bottomBar = None

        if highlight:
            self._highlighted = highlight

        # Prepare button data list
        btn_data = []
        if buttons:
            if isinstance(buttons, (list, tuple)):
                btn_data.extend(buttons)
            else:
                btn_data.append(buttons)

        if closeButton:
            close_cfg = self.Close.copy()
            # If no callback is defined, default to self.close
            if not close_cfg.get("callback"):
                close_cfg["callback"] = self.close
            btn_data.append(close_cfg)

        created_buttons = self._defineButtons(btn_data)

        if created_buttons:
            self.bottomBar = BottomBar(buttons=created_buttons, margins=margins, spacing=spacing, parent=self)
            self.root_layout.addWidget(self.bottomBar)


class QFlatConfirmDialog(QFlatDialog):
    TEXT_COLOR = "#bbbbbb"

    def __init__(
        self,
        window="Confirm",
        title="",
        message="",
        buttons=["Ok"],
        closeButton=True,
        highlight=None,
        icon=None,
        exclusive=True,
        parent=None,
    ):
        super().__init__(parent=parent, buttons=buttons, highlight=highlight, closeButton=closeButton)

        # Ensure we are a Dialog but inherit Tool if parent has it
        new_flags = self.windowFlags() | Qt.Dialog
        if parent and (parent.windowFlags() & Qt.Tool):
            new_flags |= Qt.Tool

        self.setWindowFlags(new_flags)
        if parent:
            self.setParent(parent)

        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.setWindowTitle(window or "Confirm")
        self.clicked_button = None

        self._exclusive = exclusive
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)

        content_widget = QWidget()
        content_layout = QHBoxLayout(content_widget)
        content_layout.setContentsMargins(DPI(25), DPI(20), DPI(25), DPI(20))

        if icon:
            icon_label = QLabel()
            pix = QPixmap(icon)
            if not pix.isNull():
                icon_dim = DPI(80)
                icon_label.setPixmap(pix.scaled(icon_dim, icon_dim, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                icon_label.setFixedSize(icon_dim, icon_dim)
                content_layout.addWidget(icon_label, 0, Qt.AlignTop)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(DPI(5))
        content_layout.addLayout(text_layout, 1)

        if title:
            self.title_label = QLabel(title)
            self.title_label.setWordWrap(True)
            self.title_label.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Minimum)
            self.title_label.setStyleSheet("font-size: %spx; color: %s; font-weight: bold;" % (DPI(18), self.TEXT_COLOR))
            text_layout.addWidget(self.title_label)

        self.message_label = QLabel(message)
        self.message_label.setWordWrap(True)
        self.message_label.setStyleSheet("font-size: %spx; color: %s;" % (DPI(11.5), self.TEXT_COLOR))
        text_layout.addWidget(self.message_label)

        self.root_layout.addWidget(content_widget)

        self.setBottomBar(buttons, closeButton=closeButton, highlight=highlight)
        self.adjustSize()

    def _buttonConfigHook(self, index, config):
        """
        Adds specific callback logic for confirmation buttons.
        Determine if this button  is considered "positive
        """
        if isinstance(config, (str, bytes)):
            name = config
            is_pos = index == 0
            original_config = DialogButton(name, positive=is_pos)
        else:
            name = config.get("name", "Button")
            is_pos = config.get("positive", index == 0)
            # Take a snapshot to avoid polluting the result with the internal callback
            original_config = config.copy()

        config["callback"] = partial(self._on_button_clicked, original_config)
        return config

    def _on_button_clicked(self, config):
        self.clicked_button = config
        if config.get("positive", False):
            self.accept()
        else:
            self.reject()

    @classmethod
    def information(
        cls,
        parent,
        window,
        message,
        buttons=None,
        highlight=None,
        closeButton=True,
        title=None,
        **kwargs,
    ):
        """Static-like helper to create and show a confirm dialog."""
        if buttons is None and not closeButton:
            buttons = [cls.Close]
        dlg = cls(
            window=window,
            title=title,
            message=message,
            buttons=buttons,
            highlight=highlight,
            closeButton=closeButton,
            parent=parent,
            **kwargs,
        )
        dlg.exec_()
        return dlg.clicked_button

    @classmethod
    def question(
        cls,
        parent,
        window,
        message,
        buttons=None,
        highlight=None,
        closeButton=False,
        title="Are you sure?",
        **kwargs,
    ):
        """Static-like helper to create and show a confirm dialog."""
        if buttons is None and not closeButton:
            buttons = [cls.Yes, cls.No]
        dlg = cls(
            window=window,
            title=title,
            message=message,
            buttons=buttons,
            highlight=highlight,
            closeButton=closeButton,
            parent=parent,
            **kwargs,
        )
        dlg.exec_()
        return dlg.clicked_button

    def confirm(self):
        """Executes the dialog and returns True if a 'positive' button was clicked."""
        if self._exclusive:
            return self.exec_() == QDialog.Accepted

        self.show()
        self.raise_()
        self.activateWindow()
        loop = QEventLoop()
        self.finished.connect(loop.quit)
        loop.exec_()
        return self.result() == QDialog.Accepted


class TooltipManager:
    """Manages global state for QFlatTooltips ensuring only one exists at a time."""

    _current_tooltip = None
    _timer = None

    @classmethod
    def is_active(cls):
        """Returns True if a tooltip is visible or a show timer is running."""
        return (cls._current_tooltip and cls._current_tooltip.isVisible()) or (cls._timer and cls._timer.isActive())

    @classmethod
    def cancel_timer(cls):
        """Stops any pending show request without closing the current tooltip."""
        if cls._timer:
            cls._timer.stop()

    @classmethod
    def hide(cls):
        cls.cancel_timer()
        if cls._current_tooltip:
            try:
                cls._current_tooltip.close()
            except Exception:
                pass
            cls._current_tooltip = None

    @classmethod
    def show(
        cls,
        text="",
        anchor_widget=None,
        icon=None,
        shortcuts=None,
        description=None,
        template=None,
        action_rect=None,
        icon_obj=None,
        target_rect=None,
    ):
        if cls._timer:
            cls._timer.stop()
        cls.hide()
        cls._current_tooltip = QFlatTooltip(
            text=text, anchor_widget=anchor_widget, icon=icon, shortcuts=shortcuts, description=description, template=template, icon_obj=icon_obj
        )
        cls._current_tooltip.show_around(anchor_widget, action_rect, target_rect=target_rect)

    @classmethod
    def delayed_show(cls, delay=800, **kwargs):
        """Unified delayed showing for both buttons and menu actions."""
        if cls._timer and cls._timer.isActive():
            cls._timer.stop()

        if not cls._timer:
            cls._timer = QTimer()
            cls._timer.setSingleShot(True)

        try:
            cls._timer.timeout.disconnect()
        except Exception:
            pass

        cls._timer.timeout.connect(lambda: cls.show(**kwargs))
        cls._timer.setInterval(delay)
        cls._timer.start()


class QFlatTooltip(QWidget):
    """A floating tooltip with an arrow pointing to its source."""

    BG_COLOR = "#333333"
    HEADER_COLOR = "#282828"
    TEXT_COLOR = "#bbbbbb"
    ACCENT_COLOR = "#e0e0e0"

    ARROW_W = 12
    ARROW_H = 8
    BORDER_RADIUS = 8

    MAX_WIDTH = 320
    MIN_WIDTH = 220

    IS_MAC = sys.platform == "darwin"
    KEY_MAP = {
        Qt.Key_Alt: "⌥" if IS_MAC else "Alt",
        Qt.Key_Shift: "⇧" if IS_MAC else "Shift",
        Qt.Key_Control: "⌘" if IS_MAC else "Ctrl",
    }
    KEY_ORDER = [Qt.Key_Control, Qt.Key_Alt, Qt.Key_Shift]

    def __init__(self, text="", anchor_widget=None, icon=None, shortcuts=None, description=None, template=None, icon_obj=None):
        super().__init__(get_maya_qt())
        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self.anchor_widget = anchor_widget
        self.shortcuts = shortcuts or []
        self.icon_obj = icon_obj

        if template is None:
            template = ""
            if icon:
                template += f"<icon>{icon}</icon>"
            if text:
                template += f"<title>{text}</title>"
            if description:
                template += f"<text>{description}</text>"
        self.template = template

        self._auto_close_timer = QTimer(self)
        self._auto_close_timer.setInterval(200)
        self._auto_close_timer.timeout.connect(self._check_auto_close)

        self._setup_ui()

    def _check_auto_close(self):
        """Strictly manages tooltip visibility based on cursor location."""
        if not self.isVisible():
            self._auto_close_timer.stop()
            return

        cursor_pos = QCursor.pos()
        tt_geo = self.frameGeometry()
        side = getattr(self, "side", "top")

        buffer = DPI(30)
        # Expansion: Left, Top, Right, Bottom
        if side == "top":
            tt_safety = tt_geo.adjusted(-buffer, 0, buffer, buffer)
        else:
            tt_safety = tt_geo.adjusted(-buffer, -buffer, buffer, 0)

        if tt_safety.contains(cursor_pos):
            return

        # Determine anchor geometry
        if getattr(self, "target_rect", None):
            anc_geo = self.target_rect
        elif getattr(self, "action_rect", None) and self.anchor_widget and self.anchor_widget.isVisible():
            anc_pos = self.anchor_widget.mapToGlobal(self.action_rect.topLeft())
            anc_geo = QRect(anc_pos, self.action_rect.size())
        elif self.anchor_widget and self.anchor_widget.isVisible():
            anc_geo = self.anchor_widget.rect()
            anc_geo.moveTo(self.anchor_widget.mapToGlobal(QPoint(0, 0)))
        else:
            self.close()
            return

        if anc_geo.contains(cursor_pos):
            return

        if isinstance(self.anchor_widget, QMenu):
            active_popup = QApplication.activePopupWidget()
            if active_popup and active_popup.geometry().contains(cursor_pos):
                return

        bridge_l = max(anc_geo.left(), tt_geo.left())
        bridge_r = min(anc_geo.right(), tt_geo.right())

        if side == "top":
            bridge_top, bridge_bot = anc_geo.bottom() - 1, tt_geo.top() + 1
        else:
            bridge_top, bridge_bot = tt_geo.bottom() - 1, anc_geo.top() + 1

        bridge = QRect(bridge_l, bridge_top, bridge_r - bridge_l, bridge_bot - bridge_top)
        if bridge.contains(cursor_pos):
            return

        self.close()

    def _format_keys(self, keys_list):
        keys_set = set(keys_list)
        parts = [self.KEY_MAP[k] for k in self.KEY_ORDER if k in keys_set]

        if len(parts) < len(keys_list):
            for k in keys_list:
                if k not in self.KEY_MAP:
                    parts.append(str(k))

        return ("" if self.IS_MAC else "+").join(parts) + "+Click"

    def _setup_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self.main_layout.setSizeConstraint(QVBoxLayout.SetMinAndMaxSize)
        self.setStyleSheet(f"QFlatTooltip > QFrame#BgFrame {{ background-color: {self.BG_COLOR}; border-radius: {DPI(self.BORDER_RADIUS)}px; }}")

        self.bg_frame = QFrame()
        self.bg_frame.setObjectName("BgFrame")
        self.bg_frame.setMinimumWidth(DPI(self.MIN_WIDTH))
        self.bg_frame.setMaximumWidth(DPI(self.MAX_WIDTH))
        self.bg_layout = QVBoxLayout(self.bg_frame)
        self.bg_layout.setContentsMargins(0, 0, 0, 0)
        self.bg_layout.setSpacing(0)
        self.main_layout.addWidget(self.bg_frame)

        self._build_content()
        self.adjustSize()

    def _build_content(self):
        try:
            safe_template = self.template.replace("&", "&amp;")
            root = ET.fromstring(f"<root>{safe_template}</root>")
        except Exception as e:
            root = ET.fromstring(f"<root><text>Invalid tooltip XML: {e}</text></root>")

        # Header Handling
        header_frame, header_layout = self._create_section_frame("", top_corners=True)
        has_header = self._populate_header(root, header_layout)
        self.has_header = has_header

        if has_header:
            header_layout.addStretch()
            self.bg_layout.addWidget(header_frame)
        else:
            header_frame.hide()
            header_frame.setParent(None)

        # Main Content
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(DPI(4))

        self._populate_content(root, content_layout)

        if content_layout.count() > 0:
            self.bg_layout.addLayout(content_layout)
            # Safe distance at bottom or between content and shortcuts
            self.bg_layout.addSpacing(DPI(16))

        # Shortcuts Section
        if self.shortcuts:
            self._build_shortcuts_section()

    def _create_section_frame(self, color, top_corners=False):
        frame = QFrame()
        radius = DPI(self.BORDER_RADIUS) if top_corners else 0
        frame.setStyleSheet(
            f"background-color: {color}; border-top-left-radius: {radius}px; border-top-right-radius: {radius}px; border-bottom-left-radius: 0px; border-bottom-right-radius: 0px;"
        )
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(DPI(12), DPI(12), DPI(12), DPI(12))
        layout.setSpacing(DPI(8))
        return frame, layout

    def _populate_header(self, root, layout):
        has_items = False

        # Add explicit icon if provided
        if self.icon_obj and not self.icon_obj.isNull():
            lbl = self._create_icon_label(self.icon_obj, dim=29)
            layout.addWidget(lbl)
            has_items = True

        for child in root:
            if child.tag == "icon" and not has_items:
                pix = QPixmap(child.text)
                if not pix.isNull():
                    layout.addWidget(self._create_icon_label(pix, dim=29))
                    has_items = True
            elif child.tag == "title":
                layout.addWidget(self._create_text_label(child.text or "", size=18, bold=True, elide=True))
                has_items = True

            # Stop header processing at first non-header tag
            if child.tag not in ["title", "icon"]:
                break
        return has_items

    def _populate_content(self, root, layout):
        in_content = False
        for child in root:
            if not in_content and child.tag not in ["title", "icon"]:
                in_content = True
            if not in_content:
                continue

            if child.tag == "text":
                lbl = QLabel(child.text or "")
                lbl.setWordWrap(True)
                lbl.setMaximumWidth(DPI(320))
                # Extra bottom margin (DPI 6) to account for font descenders (g, p, q)
                lbl.setContentsMargins(DPI(12), DPI(4), DPI(12), DPI(6))
                lbl.setStyleSheet(f"color: {self.TEXT_COLOR}; font-size: {DPI(11.1)}px; background-color: transparent;")
                layout.addWidget(lbl)
            elif child.tag == "separator":
                sep = QFrame()
                sep.setFixedHeight(1)
                sep.setStyleSheet(f"background-color: {self.HEADER_COLOR}; margin: {DPI(4)}px {DPI(12)}px;")
                layout.addWidget(sep)
            elif child.tag in ["image", "gif"]:
                layout.addWidget(self._create_media_label(child.text or "", is_gif=(child.tag == "gif")))

    def _build_shortcuts_section(self):
        frame, layout = self._create_section_frame(self.HEADER_COLOR)
        layout.setContentsMargins(0, DPI(4), 0, DPI(4))

        title_lbl = self._create_text_label("Shortcuts", size=16, bold=True, elide=True, align=Qt.AlignCenter)
        title_lbl.setMinimumHeight(DPI(20))
        layout.addWidget(title_lbl)

        self.bg_layout.addSpacing(DPI(10))
        self.bg_layout.addWidget(frame)
        self.bg_layout.addSpacing(DPI(12))

        for sh in self.shortcuts:
            row = QHBoxLayout()
            row.setContentsMargins(DPI(12), 0, DPI(12), 0)
            row.setSpacing(DPI(20))

            pix = QPixmap(return_icon_path(sh.get("icon", "default")))
            row.addWidget(self._create_icon_label(pix, dim=17))

            name = QLabel(sh.get("label", ""))
            name.setStyleSheet(f"color: {self.TEXT_COLOR}; font-size: {DPI(10.5)}px;")
            row.addWidget(name)
            row.addStretch()

            keys = QLabel(self._format_keys(sh.get("keys", [])))
            keys.setStyleSheet(f"color: {self.TEXT_COLOR}; font-size: {DPI(10.5)}px;")
            row.addWidget(keys)
            self.bg_layout.addLayout(row)
            self.bg_layout.addSpacing(DPI(4))

        self.bg_layout.addSpacing(DPI(16))

    def _create_icon_label(self, source, dim=16):
        lbl = QLabel()
        px_dim = DPI(dim)
        pix = source.pixmap(px_dim, px_dim) if hasattr(source, "pixmap") else source
        lbl.setPixmap(pix.scaled(px_dim, px_dim, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        return lbl

    def _create_text_label(self, text, size=11, bold=False, elide=False, align=None):
        lbl = QLabel(text)
        style = f"color: {self.TEXT_COLOR}; font-size: {DPI(size)}px;"
        if bold:
            style += " font-weight: bold;"
        lbl.setStyleSheet(style)
        if align:
            lbl.setAlignment(align)

        lbl.setWordWrap(True)

        if elide and " " not in text:
            f = lbl.font()
            f.setPixelSize(DPI(size))
            f.setBold(bold)
            fm = QFontMetrics(f)
            limit = DPI(self.MAX_WIDTH - 40)
            if fm.horizontalAdvance(text) > limit:
                lbl.setText(fm.elidedText(text, Qt.ElideLeft, limit))
        return lbl

    def _create_media_label(self, path, is_gif=False):
        lbl = QLabel()
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setContentsMargins(DPI(12), DPI(4), DPI(12), DPI(4))
        if is_gif or path.endswith(".gif"):
            movie = QMovie(path)
            movie.setScaledSize(QSize(DPI(300), DPI(150)))
            movie.start()
            lbl.setMovie(movie)
        else:
            pix = QPixmap(path)
            if not pix.isNull():
                if pix.width() > DPI(300):
                    pix = pix.scaledToWidth(DPI(300), Qt.SmoothTransformation)
                lbl.setPixmap(pix)
        return lbl

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)

        # We draw the arrow color based on which section it attaches to
        side = getattr(self, "side", "top")
        arrow_color = self.BG_COLOR

        painter.setBrush(QColor(arrow_color))

        aw = DPI(self.ARROW_W)
        ah = DPI(self.ARROW_H)
        ax = getattr(self, "arrow_x", self.width() / 2)

        if side == "top":
            # Arrow on TOP edge, pointing UP
            poly = QPolygonF([QPointF(ax, 0), QPointF(ax - aw / 2, ah + 1), QPointF(ax + aw / 2, ah + 1)])
            painter.drawPolygon(poly)
        else:
            # Arrow on BOTTOM edge, pointing DOWN
            poly = QPolygonF([QPointF(ax, self.height()), QPointF(ax - aw / 2, self.height() - ah - 1), QPointF(ax + aw / 2, self.height() - ah - 1)])
            painter.drawPolygon(poly)

    def show_around(self, widget, action_rect=None, target_rect=None):
        self.action_rect = action_rect
        self.target_rect = target_rect  # Global QRect
        self.anchor_widget = widget

        cursor_pos = QCursor.pos()
        cursor_x = cursor_pos.x()
        ah = DPI(self.ARROW_H)

        if target_rect:
            # If a global rect is provided, use it directly
            target_x = cursor_x
            target_y = target_rect.bottom() + 1
            widget_h = 0
            self._global_anc = target_rect
        elif action_rect:
            # Map action rect to global coordinates
            global_anc = QRect(widget.mapToGlobal(action_rect.topLeft()), action_rect.size())
            target_x = cursor_x
            target_y = global_anc.bottom() + 1
            widget_h = 0
            self._global_anc = global_anc
            self.target_rect = global_anc
        else:
            target_global = widget.mapToGlobal(QPoint(0, 0))
            target_x = cursor_x
            target_y = target_global.y()
            widget_h = widget.height()
            self._global_anc = QRect(target_global, widget.size())
            self.target_rect = self._global_anc

        # Try BELOW position first
        self.side = "top"
        self.main_layout.setContentsMargins(0, ah, 0, 0)
        self.main_layout.activate()
        self.adjustSize()
        w, h = self.width(), self.height()

        pos = QPoint(target_x - w // 2, target_y + widget_h + DPI(2))

        screen = QGuiApplication.screenAt(cursor_pos) or QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()

        if pos.y() + h > geo.bottom():
            # Flip to ABOVE position
            self.side = "bottom"
            self.main_layout.setContentsMargins(0, 0, 0, ah)
            self.main_layout.activate()
            self.adjustSize()
            w, h = self.width(), self.height()

            pos.setY(self._global_anc.top() - h - DPI(2))

        # Horizontal clamping
        final_x = max(geo.left() + DPI(5), min(pos.x(), geo.right() - w - DPI(5)))
        pos.setX(final_x)
        self.move(pos)

        # Calculate relative arrow X position
        arrow_x = target_x - final_x
        aw = DPI(self.ARROW_W)
        self.arrow_x = max(DPI(6) + aw / 2, min(arrow_x, w - DPI(6) - aw / 2))
        self.update()

        self._auto_close_timer.start()
        self.show()
