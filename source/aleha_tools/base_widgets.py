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
    )
    from PySide6.QtGui import (  # type: ignore
        QIcon,
        QColor,
        QPixmap,
        QPainter,
        QPolygonF,
        QCursor,
        QGuiApplication,
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
    )
    from PySide2.QtGui import (
        QIcon,
        QColor,
        QPixmap,
        QPainter,
        QPolygonF,
        QCursor,
        QGuiApplication,
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

    @classmethod
    def hide(cls):
        if cls._current_tooltip:
            try:
                cls._current_tooltip.close()
            except Exception:
                pass
            cls._current_tooltip = None

    @classmethod
    def show(cls, text, anchor_widget, icon=None, shortcuts=None, description=None):
        cls.hide()
        cls._current_tooltip = QFlatTooltip(text, anchor_widget, icon, shortcuts, description)
        cls._current_tooltip.show_around(anchor_widget)


class QFlatTooltip(QWidget):
    """A floating tooltip with an arrow pointing to its source."""

    BG_COLOR = "#383838"
    HEADER_COLOR = "#2a2a2a"
    TEXT_COLOR = "#bbbbbb"
    ACCENT_COLOR = "#e0e0e0"
    ARROW_W = 12
    ARROW_H = 8

    AUTO_CLOSE_DIST = 40

    IS_MAC = sys.platform == "darwin"

    KEY_MAP = {
        Qt.Key_Alt: "⌥" if sys.platform == "darwin" else "Alt",
        Qt.Key_Shift: "⇧" if sys.platform == "darwin" else "Shift",
        Qt.Key_Control: "⌘" if sys.platform == "darwin" else "Ctrl",
    }
    KEY_ORDER = [Qt.Key_Alt, Qt.Key_Shift, Qt.Key_Control]

    def __init__(self, text, anchor_widget, icon=None, shortcuts=None, description=None):
        super().__init__(get_maya_qt())
        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self.text = text
        self.anchor_widget = anchor_widget
        self.icon_path = icon
        self.shortcuts = shortcuts or []
        self.description = description

        # Cached DPI values for high-frequency timer
        self._buffer = DPI(self.AUTO_CLOSE_DIST)

        self._auto_close_timer = QTimer(self)
        self._auto_close_timer.setInterval(200)
        self._auto_close_timer.timeout.connect(self._check_auto_close)

        self._setup_ui()

    def _check_auto_close(self):
        if not self.isVisible():
            self._auto_close_timer.stop()
            return

        cursor_pos = QCursor.pos()
        tt_geo = self.frameGeometry()

        if tt_geo.contains(cursor_pos):
            return

        if self.anchor_widget and self.anchor_widget.isVisible():
            anc_pos = self.anchor_widget.mapToGlobal(QPoint(0, 0))
            anc_geo = self.anchor_widget.rect()
            anc_geo.moveTo(anc_pos)
            if anc_geo.contains(cursor_pos):
                return
        else:
            self.close()
            return

        # Narrow Bridge (for moving between button and tooltip)
        side = getattr(self, "side", "top")

        # Define the bridge area (narrow vertical lane)
        bridge_l = max(anc_geo.left(), tt_geo.left())
        bridge_r = min(anc_geo.right(), tt_geo.right())

        if side == "top":  # BELOW button
            bridge_top, bridge_bot = anc_geo.bottom(), tt_geo.top()
            # Safety buffer strictly around tooltip (back and sides)
            tt_safety = tt_geo.adjusted(-self._buffer, 0, self._buffer, self._buffer)
        else:  # ABOVE button
            bridge_top, bridge_bot = tt_geo.bottom(), anc_geo.top()
            # Safety buffer strictly around tooltip (front and sides)
            tt_safety = tt_geo.adjusted(-self._buffer, -self._buffer, self._buffer, 0)

        bridge = QRect(bridge_l, bridge_top, bridge_r - bridge_l, bridge_bot - bridge_top)

        if bridge.contains(cursor_pos) or tt_safety.contains(cursor_pos):
            return

        self.close()

    def _format_keys(self, keys_list):
        keys_set = set(keys_list)
        parts = [self.KEY_MAP[k] for k in self.KEY_ORDER if k in keys_set]

        if len(parts) < len(keys_list):
            for k in keys_list:
                if k not in self.KEY_MAP:
                    parts.append(str(k))

        return "".join(parts) + "+Click"

    def _setup_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # Header Section
        self.header = QFrame()
        self.header.setStyleSheet(
            f"background-color: {self.HEADER_COLOR}; border-top-left-radius: {DPI(6)}px; border-top-right-radius: {DPI(6)}px;"
        )
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(DPI(12), DPI(8), DPI(12), DPI(8))
        header_layout.setSpacing(DPI(8))

        if self.icon_path:
            icon_label = QLabel()
            pix = QPixmap(self.icon_path)
            if not pix.isNull():
                dim = DPI(16)
                icon_label.setPixmap(pix.scaled(dim, dim, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                header_layout.addWidget(icon_label)

        self.title_label = QLabel(self.text)
        self.title_label.setStyleSheet(f"color: {self.TEXT_COLOR}; font-size: {DPI(11)}px; font-weight: bold;")
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()

        self.main_layout.addWidget(self.header)

        # Description Section
        if self.description:
            self.desc_label = QLabel(self.description)
            self.desc_label.setWordWrap(True)
            self.desc_label.setStyleSheet(
                f"color: {self.TEXT_COLOR}; font-size: {DPI(11)}px; padding: {DPI(8)}px {DPI(12)}px {DPI(4)}px {DPI(12)}px; background-color: {self.BG_COLOR};"
            )
            self.main_layout.addWidget(self.desc_label)

        # Content Section (Shortcuts)
        if self.shortcuts:
            self.content = QFrame()
            self.content.setStyleSheet(
                f"background-color: {self.BG_COLOR}; border-bottom-left-radius: {DPI(6)}px; border-bottom-right-radius: {DPI(6)}px;"
            )
            content_layout = QVBoxLayout(self.content)
            content_layout.setContentsMargins(0, 0, 0, DPI(12))  # 0 horizontal for side-to-side header
            content_layout.setSpacing(DPI(4))

            # "Shortcuts" mini header with darker side-to-side background
            self.sh_header_frame = QFrame()
            self.sh_header_frame.setStyleSheet(f"background-color: {self.HEADER_COLOR}; border: none;")
            sh_header_layout = QHBoxLayout(self.sh_header_frame)
            sh_header_layout.setContentsMargins(0, DPI(8), 0, DPI(12))
            sh_header_layout.setSpacing(0)

            sh_header = QLabel("Shortcuts")
            sh_header.setStyleSheet(f"color: {self.TEXT_COLOR}; font-size: {DPI(11)}px; font-weight: bold;")
            sh_header.setMinimumHeight(DPI(10))
            sh_header.setAlignment(Qt.AlignCenter)
            sh_header_layout.addWidget(sh_header)

            content_layout.addSpacing(DPI(10))  # Margin before header
            content_layout.addWidget(self.sh_header_frame)
            content_layout.addSpacing(DPI(10))  # More margin after header

            for sh in self.shortcuts:
                row = QHBoxLayout()
                row.setContentsMargins(DPI(12), 0, DPI(12), 0)  # Internal margins for rows
                row.setSpacing(DPI(8))

                # Icon
                icon_lab = QLabel()
                sh_pix = QPixmap(return_icon_path(sh.get("icon", "default")))
                if not sh_pix.isNull():
                    s_dim = DPI(14)
                    icon_lab.setPixmap(sh_pix.scaled(s_dim, s_dim, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                row.addWidget(icon_lab)

                # Label
                name_lab = QLabel(sh.get("label", ""))
                name_lab.setStyleSheet(f"color: {self.TEXT_COLOR}; font-size: {DPI(10.5)}px;")
                row.addWidget(name_lab)

                row.addStretch()

                # Keys
                key_string = self._format_keys(sh.get("keys", []))
                keys_lab = QLabel(key_string)
                keys_lab.setStyleSheet(f"color: {self.TEXT_COLOR}; font-size: {DPI(10.5)}px; font-weight: bold;")
                row.addWidget(keys_lab)

                content_layout.addLayout(row)

            self.main_layout.addWidget(self.content)
        else:
            # Adjust header for single-section look
            self.header.setStyleSheet(f"background-color: {self.BG_COLOR}; border-radius: {DPI(6)}px;")

        self.adjustSize()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)

        # We draw the arrow color based on which section it attaches to
        side = getattr(self, "side", "top")
        arrow_color = self.HEADER_COLOR if side == "top" else self.BG_COLOR
        if not self.shortcuts:
            arrow_color = self.BG_COLOR

        painter.setBrush(QColor(arrow_color))

        aw = DPI(self.ARROW_W)
        ah = DPI(self.ARROW_H)
        ax = self.width() / 2

        if side == "top":
            # Arrow on TOP edge, pointing UP
            poly = QPolygonF([QPointF(ax, 0), QPointF(ax - aw / 2, ah + 1), QPointF(ax + aw / 2, ah + 1)])
            painter.drawPolygon(poly)
        else:
            # Arrow on BOTTOM edge, pointing DOWN
            poly = QPolygonF(
                [QPointF(ax, self.height()), QPointF(ax - aw / 2, self.height() - ah - 1), QPointF(ax + aw / 2, self.height() - ah - 1)]
            )
            painter.drawPolygon(poly)

    def show_around(self, widget):
        self.adjustSize()
        w, h = self.width(), self.height()
        ah = DPI(self.ARROW_H)

        # Center X of target
        target_global = widget.mapToGlobal(QPoint(widget.width() // 2, 0))
        target_x = target_global.x()
        target_y = target_global.y()

        # Default: show on bottom
        pos = QPoint(target_x - w // 2, target_y + widget.height() + DPI(2))
        self.side = "top"
        self.main_layout.setContentsMargins(0, ah, 0, 0)  # Make room for arrow on top

        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()

        if pos.y() + h > geo.bottom():
            # Flip to top
            pos.setY(target_y - h - DPI(2))
            self.side = "bottom"
            self.main_layout.setContentsMargins(0, 0, 0, ah)  # Make room for arrow on bottom

        # Horizontal clamp
        final_x = max(geo.left() + DPI(5), min(pos.x(), geo.right() - w - DPI(5)))
        pos.setX(final_x)

        self.move(pos)
        self.show()
        self._auto_close_timer.start()
