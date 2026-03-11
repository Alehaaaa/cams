try:
    from PySide6.QtWidgets import (  # type: ignore
        QWidget,
        QLayout,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QFrame,
        QMenu,
        QWidgetAction,
        QApplication,
        QScrollArea,
        QSlider,
        QLineEdit,
        QFormLayout,
        QVBoxLayout,
        QCheckBox,
        QColorDialog,
        QTextBrowser,
    )
    from PySide6.QtGui import (  # type: ignore
        QIcon,
        QPainter,
        QAction,
        QActionGroup,
        QDoubleValidator,
        QRegularExpressionValidator,
        QColor,
        QDrag,
        QCursor,
        QPalette,
        QWheelEvent,
        QPixmap,
        QFontMetrics,
        QPen,
    )
    from PySide6.QtCore import (  # type: ignore
        Qt,
        QEvent,
        Signal,
        QPointF,
        QPoint,
        QRegularExpression,
        QMimeData,
        QTimer,
    )
except ImportError:
    from PySide2.QtWidgets import (
        QWidget,
        QLayout,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QFrame,
        QMenu,
        QWidgetAction,
        QActionGroup,
        QApplication,
        QScrollArea,
        QSlider,
        QLineEdit,
        QFormLayout,
        QVBoxLayout,
        QCheckBox,
        QColorDialog,
        QTextBrowser,
    )
    from PySide2.QtGui import (
        QIcon,
        QPainter,
        QRegExpValidator,
        QDoubleValidator,
        QColor,
        QDrag,
        QCursor,
        QPalette,
        QWheelEvent,
        QPixmap,
        QFontMetrics,
        QPen,
    )
    from PySide2.QtCore import (
        Qt,
        QEvent,
        Signal,
        QRegExp,
        QPointF,
        QPoint,
        QMimeData,
        QTimer,
    )

    QRegularExpression = QRegExp
    QRegularExpressionValidator = QRegExpValidator

import maya.cmds as cmds
import webbrowser

from functools import partial

from .util import (
    DPI,
    return_icon_path,
    get_cameras,
    getcolor,
    get_python_version,
)
from .funcs import (
    check_if_valid_camera,
    duplicate_cam,
    delete_cam,
    tear_off_cam,
    select_cam,
    deselect_cam,
    look_thru,
    save_display_to_cam,
    set_cam_display,
    get_cam_display,
    get_panels_from_camera,
    get_preferences_display,
    display_menu_elements,
    rename_cam,
)
from .base_widgets import (
    QFlatDialog,
    QFlatConfirmDialog,
    TooltipManager,
)
from . import DATA

CONTEXTUAL_CURSOR = QCursor(QPixmap(":/rmbMenu.png"), hotX=11, hotY=8)


# """
# QPainter for the cameras shelf tabBar
# """


class ShelfPainter(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.tabbar_width = DPI(16)
        self.line_thickness = DPI(1)
        self.line_color = QColor(130, 130, 130)
        self.margin = DPI(4)
        self.center = DPI(5)
        self.offset = DPI(1.5)

    def paintEvent(self, event):
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

        color = self.palette().color(self.backgroundRole())
        painter = QPainter(self)
        painter.setPen(QPen(color, self.tabbar_width))
        painter.drawLine(self.tabbar_width // 2, 0, self.tabbar_width // 2, self.height())

        pen = QPen(self.line_color)
        pen.setWidth(1)  # Line width of 1 pixel
        pen.setStyle(Qt.CustomDashLine)  # Enable custom dash pattern
        pen.setDashPattern([0.01, DPI(3)])  # 1 pixel dot, 1 pixel space
        painter.setPen(pen)

        painter.drawLine(
            QPointF(self.center - self.offset, self.margin / 3),
            QPointF(self.center - self.offset, self.height() - self.margin),
        )
        painter.drawLine(
            QPointF(self.center + self.offset, self.margin / 3),
            QPointF(self.center + self.offset, self.height() - self.margin),
        )

    def resizeEvent(self, event):
        self.update()

    def updateDrawingParameters(
        self,
        tabbar_width=None,
        line_thickness=None,
        line_color=None,
        margin=None,
        center=None,
        offset=None,
    ):
        """Update drawing parameters and refresh the widget."""
        if tabbar_width is not None:
            self.tabbar_width = tabbar_width.width()
        if line_thickness is not None:
            self.line_thickness = line_thickness
        if line_color is not None:
            self.line_color = line_color
        if margin is not None:
            self.margin = margin
        if center is not None:
            self.center = center
        if offset is not None:
            self.offset = offset
        self.update()


"""
QMenu that doesn't close
"""


class MenuTitleAction(QWidgetAction):
    def __init__(self, version, parent=None):
        super().__init__(parent)
        self.version = version
        self.website = DATA["AUTHOR"]["website"]

        self.triggered.connect(self._on_triggered)

    def _on_triggered(self):
        webbrowser.open(self.website)

    def createWidget(self, parent):
        label = QLabel("CAMS %s" % self.version, parent)
        label.setCursor(Qt.PointingHandCursor)
        label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        label.setFixedHeight(DPI(32))
        label.setContentsMargins(DPI(25), 0, DPI(20), DPI(1))
        label.setStyleSheet(
            """
            QLabel {
                font-size: """
            + str(DPI(14))
            + """px;
                font-weight: bold;
                color: #bbbbbb;
            }
            QLabel:hover {
                background-color: rgb(80, 133, 164);
                color: #e0e0e0;
            }
            """
        )

        return label


class OpenMenu(QMenu):
    def __init__(self, title=None, parent=None):
        super().__init__(title, parent) if title else super().__init__(parent)

        if parent and hasattr(parent, "destroyed"):
            parent.destroyed.connect(self.close)

        self.triggered.connect(self._on_action_triggered)

    def _on_action_triggered(self, action):
        if isinstance(action, QWidgetAction):
            return

    def mouseReleaseEvent(self, e):
        action = self.actionAt(e.pos())
        if action and action.isEnabled():
            if action.isCheckable():
                action.setEnabled(False)
                super().mouseReleaseEvent(e)
                action.setEnabled(True)
                action.trigger()
            elif action.data() == "keep_open":
                action.trigger()
            else:
                super().mouseReleaseEvent(e)
        else:
            super().mouseReleaseEvent(e)


"""
QLineEdit that doesn't trigger next action
"""


class QFlatRenameEdit(QLineEdit):
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            self.returnPressed.emit()
            return
        super().keyPressEvent(event)


"""
QPushButton hover detection
"""


class QFlatCamButton(QPushButton):
    dropped = Signal(tuple)
    singleClicked = Signal()
    doubleClicked = Signal()

    SHORTCUT_CONFIG = [
        {"icon": "select", "label": "Select", "keys": [Qt.Key_Shift], "action": "select_cam"},
        {"icon": "deselect", "label": "Deselect", "keys": [Qt.Key_Control], "action": "deselect_cam"},
        {"icon": "duplicate", "label": "Duplicate", "keys": [Qt.Key_Control, Qt.Key_Shift], "action": "duplicate_cam"},
        {"icon": "rename", "label": "Rename", "keys": [Qt.Key_Control, Qt.Key_Alt], "action": "rename"},
        {"icon": "remove", "label": "Remove", "keys": [Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt], "action": "remove_cam"},
        {"icon": "tear_off", "label": "Tear off", "keys": [Qt.Key_Shift, Qt.Key_Alt], "action": "tear_off"},
        {"icon": "attributes", "label": "Attributes", "keys": [Qt.Key_Alt], "action": "attributes"},
    ]

    # Cache for pre-calculated key sets
    _SHORTCUT_SETS = {tuple(sorted(c["keys"])): c for c in SHORTCUT_CONFIG}
    _ICON_CACHE = {}

    @property
    def camera(self):
        return self._camera

    def __init__(self, camera, ui=None, width=True):
        super().__init__()
        # Variables
        self._camera = camera
        self._parentUI = ui
        self._width = width

        # Internal variables
        self._is_modifiable = check_if_valid_camera(self._camera)
        self._start_pos = None

        # Settings
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.setCursor(CONTEXTUAL_CURSOR)
        self.setFixedHeight(DPI(25))

        self._update_button_name()

        if self._camera:
            self._camera_short_name = self._camera.split("|")[-1].split(":")[-1]

        # Initialization sequence
        # Common UI Initialization
        self._initialize_camera_type()  # Must be first for icons
        self._setup_icons()
        self._setup_styles()
        self._setup_inline_rename()
        self._setup_tooltip()
        self._setup_event_handlers()

    def _emit_single_click(self):
        self.singleClicked.emit()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Draw Background
        current_variant = getattr(self, "_current_bg_variant", "base")
        color_val = getattr(self, "%s_color" % current_variant, self.base_color)

        if self.isDown() or self.isChecked():
            color_val = self.dark_color

        # Parse "r, g, b" string to QColor
        try:
            rgb = [int(float(x)) for x in color_val.split(",")]
            bg_color = QColor(*rgb)
        except ValueError:
            bg_color = QColor(128, 128, 128)  # Fallback

        painter.setPen(Qt.NoPen)
        painter.setBrush(bg_color)
        painter.drawRoundedRect(self.rect(), DPI(5), DPI(5))

        # Draw Icon
        icon_size = DPI(16)
        icon_x = DPI(4)
        icon_y = (self.height() - icon_size) // 2

        current_icon = self.icon()
        if not current_icon.isNull():
            current_icon.paint(painter, icon_x, icon_y, icon_size, icon_size)

        # Draw Text
        if not self._renaming_active:
            text_x = icon_x + icon_size + DPI(4)
            padding_right = DPI(4)
            text_rect = self.rect().adjusted(text_x, 0, -padding_right, 0)
            painter.setPen(Qt.black)

            painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, self.text())

        # Draw Menu dots hint on hover
        if current_variant in ("light", "dark") and not self._renaming_active:
            dots_size = DPI(6)
            dots_x = self.width() - dots_size - DPI(1)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(0, 0, 0, 150) if current_variant == "light" else Qt.black)
            for i in range(3):
                dy = (self.height() // 2) - DPI(4) + i * DPI(4)
                painter.drawEllipse(QPointF(dots_x + dots_size / 2, dy), DPI(1.5), DPI(1.5))

    # Initialization Helpers ##################################################
    def _initialize_camera_type(self):
        self.cam_type = "camera"
        type_attr = "%s.cams_type" % self._camera
        if cmds.objExists(type_attr):
            self.cam_type = cmds.getAttr(type_attr)

    def _setup_styles(self):
        base_color = getcolor(self._camera)
        self.base_color = ", ".join(str(int(round(x))) for x in base_color)
        self.light_color = ", ".join(str(int(round(x * 1.2))) for x in base_color)
        self.dark_color = ", ".join(str(int(round(x * 0.6))) for x in base_color)

        self.setStyleSheet(
            """
            QPushButton {
                padding-left: %spx;
                padding-right: %spx;
                color: black;
                background-color: rgb(%s);
                border-radius: %spx;
            }
            QToolTip { 
                background-color: rgb(%s);
            }
        """
            % (DPI(4), DPI(4), self.base_color, DPI(5), self.light_color)
        )
        self.setStatusTip("Look thru %s" % self._camera)

    def _setup_icons(self):
        icon_names = ["select", "deselect", "duplicate", "rename", "remove", "tear_off", "attributes"]

        # Ensure default icon is cached
        default_icon_path = return_icon_path(self.cam_type)
        if default_icon_path not in self._ICON_CACHE:
            self._ICON_CACHE[default_icon_path] = QIcon(default_icon_path)
        self.icons = {"default": self._ICON_CACHE[default_icon_path]}

        for name in icon_names:
            path = return_icon_path(name)
            if path not in self._ICON_CACHE:
                self._ICON_CACHE[path] = QIcon(path)
            self.icons[name] = self._ICON_CACHE[path]

        self.setIcon(self.icons["default"])

    def _setup_inline_rename(self):
        self.inline_rename_field = QFlatRenameEdit(self)
        self.inline_rename_field.hide()
        self.inline_rename_field.returnPressed.connect(self._finish_inline_rename)
        self.inline_rename_field.editingFinished.connect(self._finish_inline_rename)
        # Style matches button but white background for input
        self.inline_rename_field.setStyleSheet(
            """
            QLineEdit {
                border-radius: %spx;
                padding: %spx;
                color: black;
                background-color: rgba(0, 0, 0, 50); 
                selection-background-color: rgba(255, 255, 255, 100);
            }
        """
            % (DPI(2), DPI(2))
        )
        self._renaming_active = False

    def _setup_event_handlers(self):
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.installEventFilter(self)

        if self._parentUI:
            try:
                self._parentUI.keys_pressed_changed.connect(self._handle_key_modifiers)
            except Exception:
                pass

        # Click management
        self._click_timer = QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.setInterval(250)
        self._click_timer.timeout.connect(self._emit_single_click)

    def _setup_tooltip(self):
        self._tooltip_timer = QTimer(self)
        self._tooltip_timer.setSingleShot(True)
        self._tooltip_timer.setInterval(800)
        self._tooltip_timer.timeout.connect(self._show_tooltip)

    def _show_tooltip(self):
        if self.underMouse() and not self._renaming_active:
            icon_path = return_icon_path(self.cam_type)
            cam_name = "Maya Camera" if self.cam_type == "camera" else f"{self.cam_type.capitalize()} Camera"
            desc = f"Manage this {cam_name}. Use modifier keys for shortcuts, Right-Click for the context menu, or Drag & Drop to reorder and assign to viewports."
            TooltipManager.show(self._camera, self, icon=icon_path, shortcuts=self.SHORTCUT_CONFIG, description=desc)

    def _hide_tooltip(self):
        self._tooltip_timer.stop()
        # We no longer force-hide here as the QFlatTooltip manages its own
        # distance-based closure now.

    # Context Menu Management #################################################
    def _show_context_menu(self, pos):
        if not cmds.objExists(self._camera):
            self._parentUI.reload_cams_UI()
            return

        self._set_background_color("light")

        menu = OpenMenu()
        self._build_context_menu(menu)
        menu.exec_(self.mapToGlobal(pos))

        if not self.underMouse():
            self._set_background_color("base")
            self.setIcon(self.icons["default"])

    def _build_context_menu(self, menu):
        self._add_title_section(menu)
        self._add_selection_actions(menu)
        self._add_duplicate_action(menu)
        self._add_rename_section(menu)

        menu.addSeparator()
        self._add_default_camera_menu(menu)
        self._add_display_options_menu(menu)

        menu.addSeparator()
        self._add_camera_specific_actions(menu)
        self._add_common_actions(menu)

    def _add_title_section(self, menu):
        if not self._camera:
            return

        label = QLabel(self._truncated_name())
        # style
        label.setStyleSheet(
            """
            font-size: %spx; 
            font-weight: bold;
            padding: 0 %spx;
        """
            % (DPI(14), DPI(20))
        )
        label.setFixedHeight(DPI(32))

        action = QWidgetAction(self)
        action.setDefaultWidget(label)
        menu.addAction(action)

    def _add_selection_actions(self, menu):
        self.select_action = menu.addAction(self.icons["select"], "Select", partial(select_cam, self._camera, self))
        self.deselect_action = menu.addAction(self.icons["deselect"], "Deselect", partial(deselect_cam, self._camera, self))

        is_selected = self._camera in (cmds.ls(selection=True) or [])
        self.select_action.setVisible(not is_selected)
        self.deselect_action.setVisible(is_selected)

    def _add_duplicate_action(self, menu):
        menu.addAction(
            self.icons["duplicate"],
            "Duplicate",
            partial(duplicate_cam, self._camera, self),
        )

    def _add_rename_section(self, menu):
        if not self._is_modifiable:
            return

        # Trigger inline rename on the BUTTON
        menu.addAction(self.icons["rename"], "Rename", self.start_inline_rename)

    def _add_default_camera_menu(self, menu):
        if self._camera == self._parentUI.default_cam[0]:
            default_cam_menu = OpenMenu("Default camera")
            default_cam_menu.setIcon(self.icons["default"])
            default_cam_menu_grp = QActionGroup(self)

            for c in get_cameras(default=True):
                action = default_cam_menu.addAction(c, partial(self._set_default_cam, (c, True), menu))
                default_cam_menu_grp.addAction(action)
                action.setCheckable(True)
                if c == self._camera:
                    action.setChecked(True)
                    action.setEnabled(False)
            menu.addMenu(default_cam_menu)
        menu.addSeparator()

    def _set_default_cam(self, default_cam, menu):
        self._parentUI.process_prefs(cam=default_cam)
        menu.close()

    def _add_display_options_menu(self, menu):
        display_menu = OpenMenu("Viewport Show")
        display_menu.setTearOffEnabled(True)
        self._build_display_menu(display_menu)
        menu.addMenu(display_menu)

    def _build_display_menu(self, menu):
        self.show_elements = display_menu_elements()

        cam_panels = get_panels_from_camera(self._camera)
        preferences = get_preferences_display(self._camera)

        for section, elements in self.show_elements.items():
            menu.addSeparator()
            section_action = menu.addAction(section)
            section_action.setCheckable(True)

            element_actions = []
            for label, attr, is_plugin in elements:
                action = menu.addAction("     %s" % label)
                action.setCheckable(True)
                state = self._get_display_state(attr, is_plugin, cam_panels, preferences)
                action.setChecked(state)
                element_actions.append((action, attr, is_plugin))

            section_state = all(a[0].isChecked() for a in element_actions)
            section_action.setChecked(section_state)

            # Connect actions
            section_action.triggered.connect(partial(self._toggle_section, section_action, element_actions))
            for action, attr, is_plugin in element_actions:
                action.triggered.connect(partial(self._update_display_attribute, attr, is_plugin, action))

    # Display State Management ################################################
    def _get_display_state(self, attribute, is_plugin, panels, preferences):
        if panels:
            state = get_cam_display(panels, attribute, is_plugin)
            return state or False
        state = preferences.get(attribute, (None, False))[1]
        return state or False

    def _toggle_section(self, section_action, elements):
        state = section_action.isChecked()
        for action, attr, is_plugin in elements:
            action.setChecked(state)
            self._update_display_attribute(attr, is_plugin, state)

    def _update_display_attribute(self, attribute, is_plugin, state):
        if isinstance(state, QAction):
            state = state.isChecked()
        panels = get_panels_from_camera(self._camera)

        if panels:
            set_cam_display(panels, attribute, is_plugin, state)
        save_display_to_cam(self._camera, [(attribute, is_plugin, state)])

    def mousePressEvent(self, event):
        TooltipManager.hide()  # Force hide on interaction
        if event.button() == Qt.LeftButton:
            self._click_timer.stop()
            self._start_pos = event.pos()
            self._set_background_color("dark")
        elif event.button() == Qt.RightButton:
            self._set_background_color("dark")
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        is_dots_click = False
        current_variant = getattr(self, "_current_bg_variant", "base")
        if current_variant in ("light", "dark"):
            dots_size = DPI(6)
            dots_x = self.width() - dots_size - DPI(1)
            if event.pos().x() >= dots_x:
                is_dots_click = True

        if event.button() == Qt.LeftButton:
            self._start_pos = None
            if self.rect().contains(event.pos()) and not self._renaming_active:
                if is_dots_click:
                    self._show_context_menu(event.pos())
                else:
                    self._click_timer.start()

        if self.underMouse():
            self._set_background_color("light")
        else:
            self._set_background_color("base")
            self.setIcon(self.icons["default"])

        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            dots_size = DPI(6)
            dots_x = self.width() - dots_size - DPI(1)
            if event.pos().x() >= dots_x:
                return  # Ignored on context menu dots

            self._click_timer.stop()
            self.start_inline_rename()
            self.doubleClicked.emit()  # Emit doubleClicked signal

    def mouseMoveEvent(self, event):
        if not self._should_start_drag(event):
            return

        drag = QDrag(self)
        mime = QMimeData()
        mime.setData("application/maya-data", b"")
        drag.setMimeData(mime)
        drag.setPixmap(self.grab())
        drag.setHotSpot(event.pos() - self.rect().topLeft())

        TooltipManager.hide()  # Force hide on drag
        self.setDown(False)
        self._set_background_color("base")  # Reset to base before drag starts
        self.setIcon(self.icons["default"])  # Reset icon

        drag.exec_(Qt.MoveAction)

        # After drag, reset state based on mouse position
        if self.underMouse():
            self._set_background_color("light")
        else:
            self._set_background_color("base")
            self.setIcon(self.icons["default"])

        self._handle_drop_position(event)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Enter:
            self._tooltip_timer.start()
            self._handle_key_modifiers()
            self._set_background_color("light")

        elif event.type() == QEvent.Leave:
            self._hide_tooltip()
            self.setIcon(self.icons["default"])
            self._set_background_color("base")

        return super().eventFilter(obj, event)

    # UI Utilities ############################################################
    def _truncated_name(self, length=18):
        return "..%s" % self._camera[-length + 2 :] if len(self._camera) > length else self._camera

    def _update_button_name(self):
        self.setText(self._truncated_name(10))
        if self._width:
            font_metrics = QFontMetrics(self.font())
            text_width = font_metrics.horizontalAdvance(self.text())
            # Padding: Icon (16) + Left(4) + Mid(4) + Right(4) = 28.
            # Dots are skinny overlay-only.
            padding = DPI(28)
            self.setFixedWidth(text_width + padding)

    def _set_background_color(self, variant):
        self._current_bg_variant = variant
        self.update()  # Trigger repaint

    # Modifier Key Handling ###################################################
    def _handle_key_modifiers(self):
        if not self.underMouse():
            return

        mods_pressed = self._parentUI.keys_pressed
        active_keys = tuple(sorted([k for k in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt) if mods_pressed.get(k)]))

        icon_name = "default"
        action = partial(look_thru, cam=self._camera, ui=self._parentUI)

        if active_keys in self._SHORTCUT_SETS:
            cfg = self._SHORTCUT_SETS[active_keys]
            icon_name = cfg["icon"]
            act_type = cfg["action"]

            if act_type == "select_cam":
                action = partial(select_cam, self._camera)
            elif act_type == "deselect_cam":
                action = partial(deselect_cam, self._camera)
            elif act_type == "duplicate_cam":
                action = partial(duplicate_cam, self._camera, self)
            elif act_type == "rename":
                action = self.start_inline_rename
            elif act_type == "remove_cam":
                action = partial(delete_cam, self._camera, self._parentUI)
            elif act_type == "tear_off":
                action = partial(tear_off_cam, self._camera)
            elif act_type == "attributes":
                action = partial(Attributes.showUI, self._camera, self.window())

        self.setIcon(self.icons[icon_name])
        try:
            self.singleClicked.disconnect()
        except Exception:
            pass
        self.singleClicked.connect(action)

    def start_inline_rename(self):
        if not self._is_modifiable:
            return

        self._renaming_active = True

        # Calculate offsets for inline editor
        icon_width = DPI(16) + DPI(8)  # Icon + padding

        # Height for 'font metrics' look - slightly taller than font
        fm = QFontMetrics(self.font())
        height = fm.height() + DPI(4)

        # Centered vertically
        y_pos = (self.height() - height) // 2

        rect = self.rect()
        rect.setLeft(rect.left() + icon_width)
        rect.setTop(y_pos)
        rect.setHeight(height)
        # Right padding
        rect.setRight(rect.right() - DPI(4))

        self.inline_rename_field.setGeometry(rect)
        self.inline_rename_field.setText(self._camera)
        self.inline_rename_field.show()
        self.inline_rename_field.setFocus()
        self.inline_rename_field.selectAll()
        self.update()  # Repaint to hide text

    def _finish_inline_rename(self):
        if not self._renaming_active:
            return

        self._renaming_active = False
        new_name = self.inline_rename_field.text().strip()
        self.inline_rename_field.hide()
        self.update()  # Repaint to show text

        # Restore text (will be overwritten if rename succeeds and UI reloads)
        if hasattr(self, "_original_text"):
            self.setText(self._original_text)

        if new_name and new_name != self._camera:
            success = rename_cam(self._camera, new_name, self._parentUI)
            if success:
                # Assuming rename_cam updates file/scene state but we might need
                # to manually update this object if UI reload doesn't happen fast enough
                # causing flickering, but generally rename_cam calls ui.reload_cams_UI()
                pass

    # Drag and Drop ###########################################################
    def _should_start_drag(self, event):
        return event.buttons() == Qt.LeftButton and (event.pos() - self._start_pos).manhattanLength() >= QApplication.startDragDistance()

    def _handle_drop_position(self, event):
        btn_pos = event.globalPos() - QPoint(self.width() // 2, self.height() // 2)
        self.dropped.emit((btn_pos, QCursor.pos()))
        self._start_pos = None

    # Camera Type Specific ####################################################
    def _add_camera_specific_actions(self, menu):
        if self.cam_type == "camera_aim":
            self._add_aim_actions(menu)
        elif self.cam_type == "camera_follow":
            self._add_follow_actions(menu)

    def _add_aim_actions(self, menu):
        offset_attr = "%s.cams_aim_offset" % self._camera
        if cmds.objExists(offset_attr):
            menu.addAction(
                QIcon(return_icon_path("aim")),
                "Position Aim",
                partial(self._position_aim_offset, offset_attr),
            )

    def _add_follow_actions(self, menu):
        const_attr = "%s.cams_follow_attr" % self._camera
        if cmds.objExists(const_attr):
            attribute = cmds.getAttr(const_attr)
            if attribute:
                if "|" in attribute:
                    uuid, attr = attribute.split("|")
                    camera_grp = cmds.ls(uuid)
                    if not camera_grp:
                        return
                    else:
                        camera_grp = camera_grp[0]
                    follow_mode_attr = "%s.%s" % (camera_grp, attr)
                else:
                    try:
                        camera_grp = attribute.rsplit(".", 1)[0]
                        follow_mode_attr = attribute
                    except Exception as e:
                        print("Error occurred: %s" % e)
                        return

                if not cmds.objExists(follow_mode_attr):
                    return

                follow_mode_menu = OpenMenu("Follow Mode")
                current_mode = cmds.getAttr(follow_mode_attr)

                modes = [("Position, Rotation", True), ("Only Position", False)]

                group = QActionGroup(self)
                for label, mode in modes:
                    action = follow_mode_menu.addAction(label)
                    action.setCheckable(True)
                    action.setChecked(mode == current_mode)
                    action.triggered.connect(partial(cmds.setAttr, follow_mode_attr, mode))
                    group.addAction(action)

                follow_mode_menu.addSeparator()

                mute_menu = OpenMenu("Active Channels", self)
                mute_menu.setTearOffEnabled(True)

                mute_channels = [
                    ("Translate X", "tx"),
                    ("Translate Y", "ty"),
                    ("Translate Z", "tz"),
                    ("Rotate X", "rx"),
                    ("Rotate Y", "ry"),
                    ("Rotate Z", "rz"),
                ]

                for name, channel in mute_channels:
                    mute_channel_attr = "%s.%s" % (camera_grp, channel)

                    action = mute_menu.addAction(name)
                    action.setCheckable(True)
                    action.setChecked(not cmds.mute(mute_channel_attr, q=True))
                    action.triggered.connect(partial(self._mute_follow_channel, action, mute_channel_attr))

                follow_mode_menu.addMenu(mute_menu)

                menu.addMenu(follow_mode_menu)

    def _mute_follow_channel(self, action, channel):
        cmds.mute(channel, disable=action.isChecked())

    # Common Actions ##########################################################
    def _add_common_actions(self, menu):
        menu.addSeparator()
        self._add_filmgate_action(menu)
        self._add_attributes_action(menu)
        self._add_defaults_action(menu)
        menu.addSeparator()
        self._add_tearoff_action(menu)
        menu.addSeparator()
        self._add_delete_action(menu)

    def _add_filmgate_action(self, menu):
        action = menu.addAction("FilmGate Mask", self._toggle_filmgate)
        action.setCheckable(True)
        action.setChecked(cmds.getAttr("%s.displayFilmGate" % self._camera) and cmds.getAttr("%s.displayGateMask" % self._camera))

    def _toggle_filmgate(self):
        cmds.setAttr("%s.displayFilmGate" % self._camera, self.sender().isChecked())
        cmds.setAttr("%s.displayGateMask" % self._camera, self.sender().isChecked())

    def _add_attributes_action(self, menu):
        menu.addAction(
            self.icons["attributes"],
            "Attributes",
            partial(Attributes.showUI, self._camera, self.window()),
        )

    def _add_defaults_action(self, menu):
        menu.addAction(
            QIcon(return_icon_path("default")),
            "Apply Defaults",
            partial(self._parentUI.apply_camera_default, self._camera, self),
        )

    def _add_tearoff_action(self, menu):
        menu.addAction(self.icons["tear_off"], "Tear Off Copy", partial(tear_off_cam, self._camera))

    def _add_delete_action(self, menu):
        if self._camera != self._parentUI.default_cam[0] and not cmds.referenceQuery(self._camera, isNodeReferenced=True):
            menu.addSeparator()
            menu.addAction(
                self.icons["remove"],
                "Delete",
                partial(delete_cam, self._camera, self._parentUI),
            )

    # Aim Offset Handling #####################################################
    def _position_aim_offset(self, offset_attr):
        try:
            offset_obj = self._find_aim_offset_object(offset_attr)
            cmds.select(offset_obj)
            cmds.setToolTo("moveSuperContext")
        except Exception as e:
            cmds.error("Could not select Aim Locator for %s: %s" % (self._camera, str(e)))

    def _find_aim_offset_object(self, offset_attr):
        try:
            type_info = eval(cmds.getAttr(offset_attr))
            return cmds.ls(type_info[1], type=type_info[0])[0]
        except Exception:
            return self._fallback_find_offset_object(offset_attr)

    def _fallback_find_offset_object(self, offset_attr):
        attr_value = cmds.getAttr(offset_attr)
        candidates = cmds.ls(attr_value.lstrip("|"), long=True)

        for candidate in candidates:
            if self._is_valid_offset(candidate):
                self._update_offset_reference(candidate, offset_attr)
                return candidate

        return self._find_child_locator()

    def _is_valid_offset(self, candidate):
        parents = cmds.listRelatives(candidate, parent=True, fullPath=True)
        return parents and self._camera in cmds.listRelatives(parents[0].split("|")[1], children=True)

    def _update_offset_reference(self, candidate, offset_attr):
        type_ref = "['%s', '%s']" % (cmds.objectType(candidate), cmds.ls(candidate, uuid=True)[0])
        cmds.setAttr(offset_attr, type_ref, type="string")

    def _find_child_locator(self):
        parent = cmds.listRelatives(self._camera, parent=True)[0]
        for child in cmds.listRelatives(parent, allDescendents=True):
            if cmds.objectType(child) == "locator":
                return child
        raise ValueError("No valid aim offset found")


"""
QScroll for the cameras layout
"""


class HorizontalScrollArea(QScrollArea):
    def __init__(self, height, parent=None):
        super().__init__(parent)

        self.setFrameStyle(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setWidgetResizable(True)
        self.setFixedHeight(height)

        # Create a container widget for the content
        self.container_widget = QWidget(self)
        self.container_layout = QHBoxLayout(self.container_widget)
        self.container_layout.setContentsMargins(0, 0, 0, 0)
        self.container_layout.setSpacing(DPI(5))

        # Set the container widget as the scroll area's widget
        self.setWidget(self.container_widget)

    def wheelEvent(self, event):
        if event.type() == QWheelEvent.Wheel:
            delta = event.angleDelta().y() / 120  # Normalizing delta
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - (delta * 30))
            event.accept()
        super().wheelEvent(event)


"""
Attributes
"""


class Attributes(QFlatDialog):
    dlg_instance = None

    @classmethod
    def showUI(cls, cams, parent):
        try:
            cls.dlg_instance.close()
            cls.dlg_instance.deleteLater()
        except Exception:
            pass

        cls.dlg_instance = Attributes(cams, parent)
        cls.dlg_instance.show()

    def __init__(self, cam, parent=None):
        super().__init__(parent)

        self.cam = cam

        self.setWindowTitle("Attributes: " + self.cam)
        self.setWindowFlags(self.windowFlags() | Qt.WindowCloseButtonHint)

        # First section: Attributes
        self.onlyFloat = QDoubleValidator(self)

        self.create_layouts()
        self.create_widgets()
        self.create_connections()

        self.setFixedSize(self.sizeHint().width(), self.sizeHint().height())

    def create_layouts(self):
        self.form_layout = QFormLayout()
        self.form_layout.setContentsMargins(DPI(15), DPI(15), DPI(15), DPI(15))
        self.form_layout.setVerticalSpacing(DPI(10))
        self.form_layout.setSpacing(DPI(10))
        self.root_layout.addLayout(self.form_layout)
        self.focal_length_container = QHBoxLayout()
        self.near_clip_plane_container = QHBoxLayout()
        self.far_clip_plane_container = QHBoxLayout()
        self.overscan_container = QHBoxLayout()
        self.opacity_container = QHBoxLayout()
        self.color_slider_and_picker = QHBoxLayout()
        self.apply_buttons = QHBoxLayout()

    def create_widgets(self):
        self.focal_length_slider = QSlider(Qt.Horizontal)
        self.focal_length_slider.setRange(2500, 500000)
        self.focal_length_slider.setValue(int(round(cmds.getAttr(self.cam + ".fl") * 1000)))

        self.focal_length_value = QLineEdit()
        self.focal_length_value.setText(str(self.get_float(self.focal_length_slider.value())))
        self.focal_length_value.setFixedWidth(DPI(80))

        self.overscan_slider = QSlider(Qt.Horizontal)
        self.overscan_slider.setRange(1000, 2000)
        self.overscan_slider.setValue(int(cmds.getAttr(self.cam + ".overscan") * 1000))

        self.overscan_value = QLineEdit()
        self.overscan_value.setText(str(self.get_float(self.overscan_slider.value())))
        self.overscan_value.setFixedWidth(DPI(80))

        self.near_clip_plane = QLineEdit()
        self.far_clip_plane = QLineEdit()
        self.near_clip_plane.setFixedWidth(DPI(80))
        self.far_clip_plane.setFixedWidth(DPI(80))

        self.focal_length_value.setValidator(self.onlyFloat)
        self.overscan_value.setValidator(self.onlyFloat)
        self.near_clip_plane.setValidator(self.onlyFloat)
        self.far_clip_plane.setValidator(self.onlyFloat)

        self.near_clip_plane.setText(str(cmds.getAttr(self.cam + ".ncp")))
        self.far_clip_plane.setText(str(cmds.getAttr(self.cam + ".fcp")))

        self.near_clip_lock = self.create_lock_button()
        self.near_clip_lock.setVisible(False)
        self.near_clip_plane_container.addWidget(self.near_clip_plane)
        self.near_clip_plane_container.addStretch()
        self.near_clip_plane_container.addWidget(self.near_clip_lock)

        self.far_clip_lock = self.create_lock_button()
        self.far_clip_lock.setVisible(False)
        self.far_clip_plane_container.addWidget(self.far_clip_plane)
        self.far_clip_plane_container.addStretch()
        self.far_clip_plane_container.addWidget(self.far_clip_lock)

        self.focal_length_lock = self.create_lock_button()
        self.focal_length_lock.setVisible(False)
        self.focal_length_container.addWidget(self.focal_length_value)
        self.focal_length_container.addWidget(self.focal_length_slider)
        self.focal_length_container.addStretch()
        self.focal_length_container.addWidget(self.focal_length_lock)

        self.overscan_lock = self.create_lock_button()
        self.overscan_lock.setVisible(False)
        self.overscan_container.addWidget(self.overscan_value)
        self.overscan_container.addWidget(self.overscan_slider)
        self.overscan_container.addStretch()
        self.overscan_container.addWidget(self.overscan_lock)

        # Second section: Display Attributes
        self.gate_mask_opacity_slider = QSlider(Qt.Horizontal)
        self.gate_mask_opacity_slider.setRange(0, 1000)
        self.gate_mask_opacity_slider.setValue(int(round(cmds.getAttr(self.cam + ".displayGateMaskOpacity") * 1000)))
        self.gate_mask_opacity_value = QLineEdit()
        self.gate_mask_opacity_value.setText(str(self.get_float(self.gate_mask_opacity_slider.value())))
        self.gate_mask_opacity_value.setFixedWidth(DPI(80))

        self.opacity_lock = self.create_lock_button()
        self.opacity_lock.setVisible(False)
        self.opacity_container.addWidget(self.gate_mask_opacity_value)
        self.opacity_container.addWidget(self.gate_mask_opacity_slider)
        self.opacity_container.addStretch()
        self.opacity_container.addWidget(self.opacity_lock)

        self.gate_mask_color_slider = QSlider(Qt.Horizontal)
        self.gate_mask_color_slider.setRange(0, 255)
        self.gate_mask_color_slider.setValue(128)
        self.gate_mask_color_picker = QPushButton()
        self.gate_mask_color_picker.setObjectName("gateMaskColorPicker")

        self.gate_mask_color_picker.setFixedWidth(DPI(80))
        self.gate_mask_color_picker.setFixedHeight(DPI(17))

        self.update_button_color(self.cam)

        self.color_lock = self.create_lock_button()
        self.color_lock.setVisible(False)
        self.color_slider_and_picker.addWidget(self.gate_mask_color_picker)
        self.color_slider_and_picker.addWidget(self.gate_mask_color_slider)
        self.color_slider_and_picker.addStretch()
        self.color_slider_and_picker.addWidget(self.color_lock)

        self.form_layout.addRow("Focal Length:", self.focal_length_container)
        self.form_layout.addRow(QFrame(frameShape=QFrame.HLine))
        self.form_layout.addRow("Near Clip Plane:", self.near_clip_plane_container)
        self.form_layout.addRow("Far Clip Plane:", self.far_clip_plane_container)
        self.form_layout.addRow(QFrame(frameShape=QFrame.HLine))
        self.form_layout.addRow("Overscan:", self.overscan_container)
        self.form_layout.addRow("Gate Mask Opacity:", self.opacity_container)
        self.form_layout.addRow("Gate Mask Color:", self.color_slider_and_picker)

        self.form_layout.addRow(self.apply_buttons)

        self.all_widgets = [
            {
                "target": [self.focal_length_value, self.focal_length_slider],
                "attr": ".fl",
                "lock": self.focal_length_lock,
            },
            {
                "target": [self.overscan_value, self.overscan_slider],
                "attr": ".overscan",
                "lock": self.overscan_lock,
            },
            {
                "target": [self.near_clip_plane],
                "attr": ".ncp",
                "lock": self.near_clip_lock,
            },
            {
                "target": [self.far_clip_plane],
                "attr": ".fcp",
                "lock": self.far_clip_lock,
            },
            {
                "target": [self.gate_mask_opacity_value, self.gate_mask_color_slider],
                "attr": ".displayGateMaskOpacity",
                "lock": self.opacity_lock,
            },
            {
                "target": [self.gate_mask_color_picker, self.gate_mask_opacity_slider],
                "attr": ".displayGateMaskColor",
                "lock": self.color_lock,
            },
        ]

        self.setBottomBar(
            QFlatConfirmDialog.CustomButton(
                "OK",
                callback=partial(self.apply_modifications, self.cam, close=True),
                icon=return_icon_path("apply"),
                highlight=True,
            ),
            closeButton=True,
        )

    def create_connections(self):
        for widget in self.all_widgets:
            attr = self.cam + widget.get("attr", "")
            targets = widget.get("target", [])
            lock_btn = widget.get("lock", "")

            settable = True

            if not cmds.getAttr(attr, settable=True):
                settable = False
                lock_btn.setVisible(True)
                lock_btn.clicked.connect(partial(self.disconnect_locked_attr, attr, targets, lock_btn))

            for target in targets:
                value = cmds.getAttr(attr)
                if isinstance(target, QLineEdit):
                    target.setText(str(str(self.get_float(value * 1000))))
                    target.returnPressed.connect(partial(self.apply_modifications, self.cam, close=True))
                elif isinstance(target, QSlider) and not isinstance(value, list):
                    target.setValue(int(round(value * 1000)))

                target.setEnabled(settable)

        self.focal_length_slider.valueChanged.connect(
            lambda: self.focal_length_value.setText(str(self.get_float(self.focal_length_slider.value())))
        )

        self.overscan_slider.valueChanged.connect(lambda: self.overscan_value.setText(str(self.get_float(self.overscan_slider.value()))))

        self.gate_mask_opacity_slider.valueChanged.connect(
            lambda: self.gate_mask_opacity_value.setText(self.get_float(self.gate_mask_opacity_slider.value()))
        )

        self.gate_mask_color_picker.clicked.connect(lambda: self.show_color_selector(self.gate_mask_color_picker))

        self.gate_mask_color_slider.valueChanged.connect(lambda: self.update_button_value(self.gate_mask_color_slider.value()))

    def create_lock_button(self):
        lock_btn = QPushButton()
        lock_btn.setToolTip("Break connection")
        lock_btn.setStatusTip("Break connection")

        lock_btn.setIcon(QIcon(return_icon_path("locked")))
        lock_btn.setFixedSize(DPI(15), DPI(15))

        return lock_btn

    def disconnect_locked_attr(self, attr, targets, lock_btn):
        res = QFlatConfirmDialog.question(
            None,
            "Break connection",
            "Do you want to break the connection to\n'" + attr + "'?",
            buttons=QFlatConfirmDialog.Yes | QFlatConfirmDialog.No,
            highlight=QFlatConfirmDialog.No,
        )
        if res != QFlatConfirmDialog.Yes:
            return
        connections = cmds.listConnections(attr, plugs=True)
        if connections:
            cmds.disconnectAttr(connections[0], attr)

        for target in targets:
            target.setEnabled(True)

        lock_btn.setVisible(False)

    """
    Create functions
    """

    def apply_modifications(self, cam, close=False):
        cmds.undoInfo(chunkName="applyCamAttributes", openChunk=True)
        try:
            self.get_picker_color()
            parameters = {
                "fl": self.focal_length_value.text(),
                "overscan": self.overscan_value.text(),
                "ncp": self.near_clip_plane.text(),
                "fcp": self.far_clip_plane.text(),
                "displayGateMaskOpacity": self.gate_mask_opacity_value.text(),
                "displayGateMaskColor": self.gate_mask_color_rgbf,
            }

            for i, v in parameters.items():
                attr = cam + "." + i
                if cmds.getAttr(attr, settable=True):
                    if v:
                        if not isinstance(v, list):
                            cmds.setAttr(attr, float(v))
                        else:
                            r, g, b = v
                            cmds.setAttr(attr, r, g, b, type="double3")

            if close:
                self.close()
        finally:
            cmds.undoInfo(closeChunk=True)

    def get_float(self, value):
        return "%.3f" % (value / 1000.0)

    def get_picker_color(self):
        style_sheet = self.gate_mask_color_picker.styleSheet()
        import re

        match = re.search(r"#[0-9a-fA-F]{6}", style_sheet)
        if match:
            bg_color = match.group(0)
            qcolor = QColor(bg_color)
            r, g, b, _ = qcolor.getRgbF()
            self.gate_mask_color_rgbf = [r, g, b]
        else:
            self.gate_mask_color_rgbf = [0.5, 0.5, 0.5]

    def update_button_color(self, cam):
        rgb = cmds.getAttr(cam + ".displayGateMaskColor")[0]
        qcolor = QColor(*[int(q * 255) for q in rgb])
        h, s, v, _ = qcolor.getHsv()
        qcolor.setHsv(h, s, v)
        self.gate_mask_color_picker.setStyleSheet("#gateMaskColorPicker { background-color: %s; }" % qcolor.name())
        self.gate_mask_color_slider.setValue(v)

    def update_button_value(self, value):
        color = self.gate_mask_color_picker.palette().color(QPalette.Button)
        h, s, v, _ = color.getHsv()
        color.setHsv(h, s, value)
        self.gate_mask_color_picker.setStyleSheet("#gateMaskColorPicker { background-color: %s; }" % color.name())

    def show_color_selector(self, button):
        initial_color = button.palette().color(QPalette.Base)
        color = QColorDialog.getColor(initial=initial_color)
        if color.isValid():
            button.setStyleSheet("#%s { background-color: %s; }" % (button.objectName(), color.name()))
            h, s, v, _ = color.getHsv()
            self.gate_mask_color_slider.setValue(v)


"""
Default Settings
"""


class DefaultSettings(QFlatDialog):
    dlg_instance = None

    @classmethod
    def showUI(cls, parent):
        try:
            cls.dlg_instance.close()
            cls.dlg_instance.deleteLater()
        except Exception:
            pass

        cls.dlg_instance = DefaultSettings(parent)
        cls.dlg_instance.show()

    def __init__(self, parent=None):
        super().__init__(parent)

        self._parentUI = parent

        self.setWindowFlags(self.windowFlags() | Qt.WindowCloseButtonHint)
        self.setWindowTitle("Default Attributes")

        self.create_layouts()
        self.create_widgets()
        self.create_connections()

        self.setFixedSize(DPI(320), self.sizeHint().height())

    def create_layouts(self):
        self.main_layout = QFormLayout()
        self.main_layout.setContentsMargins(DPI(15), DPI(15), DPI(15), DPI(15))
        self.main_layout.setVerticalSpacing(DPI(10))
        self.main_layout.setSpacing(DPI(10))
        self.root_layout.addLayout(self.main_layout)

    def create_widgets(self):
        if get_python_version() < 3:
            onlyFloat = QRegExpValidator(QRegExp(r"[0-9].+"))
        else:
            onlyFloat = QRegularExpressionValidator(QRegularExpression(r"[0-9].+"))  # type: ignore

        description_label = QLabel("Mark the default attributes you want to be saved.")
        description_label.setAlignment(Qt.AlignCenter)

        self.near_clip_plane = QLineEdit()
        self.far_clip_plane = QLineEdit()
        self.near_clip_plane.setText(str(self._parentUI.default_near_clip_plane[0]))
        self.far_clip_plane.setText(str(self._parentUI.default_far_clip_plane[0]))

        self.near_clip_plane.setEnabled(self._parentUI.default_near_clip_plane[1])
        self.far_clip_plane.setEnabled(self._parentUI.default_far_clip_plane[1])

        self.overscan_slider = QSlider(Qt.Horizontal)
        self.overscan_value = QLineEdit()
        self.overscan_slider.setRange(1000, 2000)
        self.overscan_slider.setValue((float(self._parentUI.default_overscan[0]) * 1000))
        self.overscan_value.setText(str(self.get_float(self.overscan_slider.value())))

        self.overscan_slider.setEnabled(self._parentUI.default_overscan[1])
        self.overscan_value.setEnabled(self._parentUI.default_overscan[1])

        self.gate_mask_opacity_slider = QSlider(Qt.Horizontal)
        self.gate_mask_opacity_slider.setRange(0, 1000)
        self.gate_mask_opacity_slider.setValue(int(float(self._parentUI.default_gate_mask_opacity[0]) * 1000))

        self.gate_mask_opacity_value = QLineEdit()
        self.gate_mask_opacity_value.setText(str(self.get_float(self.gate_mask_opacity_slider.value())))

        self.gate_mask_opacity_slider.setEnabled(self._parentUI.default_gate_mask_opacity[1])
        self.gate_mask_opacity_value.setEnabled(self._parentUI.default_gate_mask_opacity[1])

        overscan_container = QHBoxLayout()
        overscan_container.addWidget(self.overscan_value)
        overscan_container.addWidget(self.overscan_slider)

        gate_mask_opacity_container = QHBoxLayout()
        gate_mask_opacity_container.addWidget(self.gate_mask_opacity_value)
        gate_mask_opacity_container.addWidget(self.gate_mask_opacity_slider)

        color_slider_and_picker = QHBoxLayout()
        self.gate_mask_color_slider = QSlider(Qt.Horizontal)
        self.gate_mask_color_slider.setRange(0, 255)
        self.gate_mask_color_slider.setValue(128)
        self.gate_mask_color_picker = QPushButton()
        self.gate_mask_color_picker.setObjectName("gateMaskColorPicker")

        self.gate_mask_color_picker.setFixedWidth(DPI(80))
        self.gate_mask_color_picker.setFixedHeight(DPI(17))

        self.gate_mask_color_picker.setEnabled(self._parentUI.default_gate_mask_color[1])
        self.gate_mask_color_slider.setEnabled(self._parentUI.default_gate_mask_color[1])

        self.update_button_color()

        color_slider_and_picker.addWidget(self.gate_mask_color_picker)
        color_slider_and_picker.addWidget(self.gate_mask_color_slider)

        self.near_clip_plane.setValidator(onlyFloat)
        self.far_clip_plane.setValidator(onlyFloat)
        self.overscan_value.setValidator(onlyFloat)
        self.gate_mask_opacity_value.setValidator(onlyFloat)

        self.near_clip_plane.setFixedWidth(DPI(80))
        self.far_clip_plane.setFixedWidth(DPI(80))
        self.overscan_value.setFixedWidth(DPI(80))
        self.gate_mask_opacity_value.setFixedWidth(DPI(80))

        layout_dict = {
            "Near Clip Plane": self.near_clip_plane,
            "Far Clip Plane": self.far_clip_plane,
            "Overscan": overscan_container,
            "Gate Mask Opacity": gate_mask_opacity_container,
            "Gate Mask Color": color_slider_and_picker,
        }

        self.main_layout.addRow(description_label)
        self.main_layout.addRow(QFrame(frameShape=QFrame.HLine))
        # Loop through each key-value pair in the dictionary and add it to the layout with a checkbox
        for index, (key, value) in enumerate(layout_dict.items()):
            if index == 2:
                self.main_layout.addRow(QFrame(frameShape=QFrame.HLine))

            widget_container = QHBoxLayout()
            widget_container.setSpacing(DPI(5))
            checkbox = QCheckBox()
            checkbox.setFixedWidth(DPI(15))
            widget_container.addWidget(checkbox)
            label = QLabel(key)
            label.setFixedWidth(DPI(100))
            widget_container.addWidget(label)
            if isinstance(value, QLayout):
                for i in range(value.count()):
                    widget = value.itemAt(i).widget()
                    if isinstance(widget, QWidget):
                        checkbox.setChecked(widget.isEnabled())
                        checkbox.toggled.connect(lambda checked=checkbox.isChecked(), v=widget: v.setEnabled(checked))
                widget_container.addLayout(value)
            if isinstance(value, QWidget):
                checkbox.setChecked(value.isEnabled())
                checkbox.toggled.connect(lambda checked=checkbox.isChecked(), v=value: v.setEnabled(checked))
                widget_container.addWidget(value)
            self.main_layout.addRow(widget_container)

        self.setBottomBar(
            buttons=QFlatConfirmDialog.CustomButton(
                "OK",
                callback=partial(self.apply_settings, close=True),
                icon=return_icon_path("apply"),
            ),
            closeButton=True,
            highlight="OK",
        )

    def create_connections(self):
        self.overscan_slider.valueChanged.connect(lambda: self.overscan_value.setText(str(self.get_float(self.overscan_slider.value()))))

        self.gate_mask_opacity_slider.valueChanged.connect(
            lambda: self.gate_mask_opacity_value.setText(self.get_float(self.gate_mask_opacity_slider.value()))
        )

        self.gate_mask_color_picker.clicked.connect(lambda: self.show_color_selector(self.gate_mask_color_picker))

        self.gate_mask_color_slider.valueChanged.connect(lambda: self.update_button_value(self.gate_mask_color_slider.value()))

        all_widgets = [
            self.near_clip_plane,
            self.far_clip_plane,
            self.overscan_value,
            self.gate_mask_opacity_value,
        ]

        for widget in all_widgets:
            widget.returnPressed.connect(self.apply_settings)

    def get_float(self, value):
        return "{:.3f}".format(value / 1000.0)

    def update_button_color(self):
        rgb = self._parentUI.default_gate_mask_color[0]
        qcolor = QColor(*[int(q * 255) for q in rgb])
        h, s, v, _ = qcolor.getHsv()
        qcolor.setHsv(h, s, v)
        self.gate_mask_color_picker.setStyleSheet("#gateMaskColorPicker { background-color: %s; }" % qcolor.name())
        self.gate_mask_color_slider.setValue(v)

    def update_button_value(self, value):
        color = self.gate_mask_color_picker.palette().color(QPalette.Button)
        h, s, v, _ = color.getHsv()
        color.setHsv(h, s, value)
        self.gate_mask_color_picker.setStyleSheet("#gateMaskColorPicker { background-color: %s; }" % color.name())

    def show_color_selector(self, button):
        initial_color = button.palette().color(QPalette.Base)
        color = QColorDialog.getColor(initial=initial_color)
        if color.isValid():
            button.setStyleSheet("#%s { background-color: %s; }" % (button.objectName(), color.name()))
            h, s, v, _ = color.getHsv()
            self.gate_mask_color_slider.setValue(v)

    def apply_settings(self, close=False):
        near = float(self.near_clip_plane.text()), self.near_clip_plane.isEnabled()
        far = float(self.far_clip_plane.text()), self.far_clip_plane.isEnabled()
        overscan = float(self.overscan_value.text()), self.overscan_value.isEnabled()
        mask_op = (
            float(self.gate_mask_opacity_value.text()),
            self.gate_mask_opacity_value.isEnabled(),
        )
        r, g, b, _ = self.gate_mask_color_picker.palette().color(QPalette.Button).getRgb()
        mask_color = (
            [round(x / 255.0, 3) for x in [r, g, b]],
            self.gate_mask_color_picker.isEnabled(),
        )

        self._parentUI.process_prefs(
            near=near,
            far=far,
            overscan=overscan,
            mask_op=mask_op,
            mask_color=mask_color,
        )
        if self._parentUI.default_cam[1]:
            self._parentUI.default_cam_btn.setText(self._parentUI.default_cam[0])
        if close:
            self.close()


"""
Coffee window
"""


class Coffee(QFlatDialog):
    _instance = None
    _check_updates = Signal()

    @classmethod
    def showUI(cls, parent, data=None):
        tool_data = data
        name = "%s_coffee_dlg" % tool_data["TOOL"].lower()

        if cmds.window(name, exists=True):
            cmds.deleteUI(name)

        cls._instance = Coffee(parent, data=data)
        cls._instance.show()
        cls._instance.raise_()
        cls._instance.activateWindow()

        return cls._instance

    def __init__(self, parent=None, data=None):
        super().__init__(parent)

        self._parentUI = parent
        self._data = data

        self._author = self._data.get("AUTHOR")

        name = "%s_coffee_dlg" % self._data["TOOL"].lower()
        self.setObjectName(name)
        self.setWindowTitle("About " + self._data["TOOL"])

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(DPI(20), DPI(20), DPI(20), 0)
        content_layout.setSpacing(DPI(12))

        # Logo Section
        logo_label = QLabel()
        logo_label.setAlignment(Qt.AlignCenter)
        logo_path = return_icon_path("logo.svg")
        logo_pixmap = QPixmap(logo_path).scaled(DPI(80), DPI(80), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        logo_label.setPixmap(logo_pixmap)
        content_layout.addWidget(logo_label)

        # Tool Name
        tool_name = QLabel("%s Tool" % self._data["TOOL"])
        tool_name.setAlignment(Qt.AlignCenter)
        tool_name.setStyleSheet("font-size: %spx; font-weight: bold; color: #ececec;" % DPI(20))
        content_layout.addWidget(tool_name)

        # Version Badge (Clickable)
        version_btn = QPushButton("v%s" % self._data["VERSION"])
        version_btn.setCursor(Qt.PointingHandCursor)
        version_btn.setStyleSheet(
            """
            QPushButton {
                background-color: rgba(76, 175, 80, 0.15);
                border: 1px solid #4CAF50;
                color: #81C784;
                border-radius: %spx;
                padding: %spx %spx;
                font-size: %spx;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #4CAF50;
                color: white;
            }
        """
            % (DPI(4), DPI(4), DPI(8), DPI(11))
        )
        version_btn.clicked.connect(self._check_updates.emit)
        content_layout.addWidget(version_btn, alignment=Qt.AlignCenter)

        # Info Section
        info_text = """
            <div style='text-align: center; color: #888888; font-size: %spx;'>
                <p>© 2023 by <a href='%s' style='color: #cccccc; text-decoration: none;'>%s</a>. All rights reserved.</p>
                <div style='margin-top: 10px;'>
                    <a href='%s' style='color: #5D99C6; text-decoration: none;'>Instagram</a> &nbsp;|&nbsp; 
                    <a href='%s' style='color: #5D99C6; text-decoration: none;'>Website</a>
                </div>
                <p style='margin-top: 15px; font-style: italic; color: #777777;'>
                    If you like this tool, consider sending me some love!
                </p>
            </div>
        """ % (
            DPI(11),
            self._author["website"],
            self._author["name"],
            self._author["instagram"],
            self._author["website"],
        )
        # Combine info text and style into one HTML document
        full_info_html = (
            """
            <style>
                a { color: #5D99C6; text-decoration: none; }
                a:hover { color: #A0C8EA; }
            </style>
            <div style='text-align: center;'>
                %s
            </div>
        """
            % info_text
        )

        info_browser = QTextBrowser()
        info_browser.setHtml(full_info_html)
        info_browser.setReadOnly(True)
        info_browser.setFrameShape(QFrame.NoFrame)
        info_browser.setStyleSheet("background: transparent;")
        info_browser.viewport().setStyleSheet("background: transparent;")
        info_browser.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        info_browser.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        info_browser.setOpenExternalLinks(True)
        info_browser.setFocusPolicy(Qt.NoFocus)
        info_browser.setFixedHeight(DPI(85))

        content_layout.addWidget(info_browser)
        self.root_layout.addWidget(content_widget)

        self.setBottomBar(closeButton=True)
        self.resize(DPI(300), DPI(150))
        self.adjustSize()
