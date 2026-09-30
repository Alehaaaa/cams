"""Reusable help metadata and tooltip hooks for Cams widgets, actions, and menus."""
import inspect
from .tooltips import QtCore, QtGui, QtWidgets, QFlatTooltipManager, clean_tool_text, _tooltip_from_data
from .util import is_valid_widget
QAction = getattr(QtGui, "QAction", None) or QtWidgets.QAction


def _status_description(description="", status_description=None, tooltip=None):
    value = status_description if status_description is not None else description
    if not value and tooltip is not None:
        value = _tooltip_from_data(tooltip).first_line
    if isinstance(value, (list, tuple)):
        value = next((str(line) for line in value if str(line).strip()), "")
    return clean_tool_text(value).split("\n")[0]


def _push_help(widget, data):
    HelpSystem.push(widget, data.get("status_title") or data.get("text", ""),
                    _status_description(data.get("description", ""), data.get("status_description"), data.get("tooltip")))


class HelpSystem:
    """Centralized utility for pushing help text to all Maya help channels."""

    @staticmethod
    def clean(raw):
        return clean_tool_text(raw)

    @staticmethod
    def get_desc(raw):
        return _status_description(raw)

    @classmethod
    def push(cls, widget_or_action, title="", description=""):
        """Pushes data to StatusTip, ToolTip, and internal properties."""
        raw_title = title or ""
        raw_desc = description or ""

        c_title = cls.clean(raw_title)
        if not c_title and hasattr(widget_or_action, "objectName"):
            c_title = cls.clean(widget_or_action.objectName())

        c_desc = cls.get_desc(raw_desc)
        # Avoid redundancy: if description starts with/is the title, strip it
        if c_title and c_desc:
            if c_title.lower() == c_desc.lower():
                c_desc = ""
            elif c_desc.lower().startswith(c_title.lower()):
                c_desc = c_desc[len(c_title) :].strip(" -:,.")
                # Restore sentence case safely
                if c_desc:
                    c_desc = c_desc[0].upper() + c_desc[1:]

        status = f"{c_title} - {c_desc}" if (c_title and c_desc) else (c_title or c_desc)

        is_action = isinstance(widget_or_action, QAction)
        if hasattr(widget_or_action, "setStatusTip") and not is_action:
            widget_or_action.setStatusTip(status)
            try:
                status_event = QtGui.QStatusTipEvent(status)
                QtWidgets.QApplication.sendEvent(widget_or_action, status_event)
            except Exception:
                pass

        if hasattr(widget_or_action, "setProperty"):
            widget_or_action.setProperty("cams_title", raw_title)
            widget_or_action.setProperty("cams_description", raw_desc)
            widget_or_action.setProperty("description", raw_desc)

class TooltipMixin:
    def _clear_tooltip_hover_state(self, anchor_unavailable=False):
        source_key = "widget:{}".format(id(self))
        QFlatTooltipManager.source_left(
            source_key=source_key,
            anchor_widget=self,
            anchor_unavailable=anchor_unavailable,
        )
        if hasattr(self, "_hover"):
            self._hover = False
        if hasattr(self, "_handle_hover"):
            self._handle_hover = False
        try:
            self.update()
        except (RuntimeError, AttributeError):
            pass

    def setData(
        self,
        text="",
        description="",
        shortcuts=None,
        icon=None,
        tooltip=None,
        status_title=None,
        status_description=None,
        command_id=None,
        command_label=None,
        command_icon=None,
    ):
        # Automatically pick up the widget's icon if not provided
        if not icon and hasattr(self, "_icon"):
            icon = self._icon

        self._toolTipData = {
            "text": text,
            "description": description,
            "shortcuts": shortcuts or [],
            "icon": icon,
            "tooltip": tooltip,
            "status_title": status_title,
            "status_description": _status_description(
                description=description,
                status_description=status_description,
                tooltip=tooltip,
            ),
            "command_id": command_id,
            "command_label": command_label,
            "command_icon": command_icon,
        }
        _push_help(self, self._toolTipData)

    def get_toolTipData(self):
        return getattr(self, "_toolTipData", {})

    def get_base_tooltip_data(self):
        """Return stable action help for controls without modifier variants."""
        return dict(self.get_toolTipData())

    def setToolTipData(self, **kwargs):
        self._has_tooltip = True
        self.setData(**kwargs)

    def setTooltipInfo(self, title: str, description: str = "", tooltip=None):
        self.setToolTipData(text=title, description=description, tooltip=tooltip)

    def enterEvent(self, event: QtCore.QEvent):
        # Refresh description and trigger Maya event
        data = getattr(self, "_toolTipData", {})
        _push_help(self, data)

        try:
            super().enterEvent(event)
        except (AttributeError, TypeError):
            pass

        if QFlatTooltipManager.enabled and getattr(self, "_has_tooltip", False):
            if data.get("text") or data.get("description") or data.get("tooltip"):
                source_key = "widget:{}".format(id(self))
                if QFlatTooltipManager.is_current_source(source_key):
                    return
                # Pass the rich tooltip directly to the tooltip manager.
                QFlatTooltipManager.delayed_show(anchor_widget=self, source_key=source_key, **data)

    def leaveEvent(self, event: QtCore.QEvent):
        self._clear_tooltip_hover_state()
        try:
            super().leaveEvent(event)
        except (AttributeError, TypeError):
            pass

    def hideEvent(self, event: QtCore.QEvent):
        self._clear_tooltip_hover_state(anchor_unavailable=True)
        try:
            super().hideEvent(event)
        except (AttributeError, TypeError):
            pass

class ActionTooltipMixin:
    """Keep rich help in Python so Qt does not flatten structured content."""
    def setToolTipData(self, text=None, description="", tooltip=None, shortcuts=None, **kwargs):
        self._tooltip_help = dict(title=text or self.text(), description=description,
                                  tooltip=tooltip, shortcuts=list(shortcuts or ()), **kwargs)
        HelpSystem.push(self, self._tooltip_help["title"], description)
        self.setToolTip("")
        self.setStatusTip("")

    def get_toolTipData(self):
        return dict(getattr(self, "_tooltip_help", {}))


class QFlatAction(ActionTooltipMixin, QAction):
    pass


class MenuTooltipMixin:
    def _init_tooltip_menu(self):
        self._action_help_store = {}
        self.hovered.connect(self._on_action_hovered)
        self.triggered.connect(lambda *_: QFlatTooltipManager.hide())

    @staticmethod
    def _set_native_action_tips(action, title, description="", tooltip=None):
        # Rich help belongs to the custom tooltip. Avoid native QAction status
        # events which can crash older Maya/Qt builds while hovering menus.
        action.setToolTip("")
        action.setStatusTip("")

    def _action_tooltip_key(self, action):
        if action is None or not is_valid_widget(action) or isinstance(action, QtWidgets.QWidgetAction):
            return None
        try:
            key = action.property("cams_tooltip_source_key")
            if not key:
                key = "menu-action:{}".format(id(action))
                action.setProperty("cams_tooltip_source_key", key)
            return key
        except (RuntimeError, ValueError, TypeError, AttributeError, KeyError, IndexError):
            return None

    @staticmethod
    def _clear_native_action_tips(action):
        try:
            action.setStatusTip("")
            action.setToolTip("")
        except (RuntimeError, ValueError, TypeError, AttributeError, KeyError, IndexError):
            pass

    def _set_action_help(
        self,
        action,
        title,
        description="",
        tooltip=None,
        shortcuts=None,
        command_id=None,
        command_icon=None,
    ):
        if action is None or not is_valid_widget(action):
            return
        if isinstance(action, QtWidgets.QWidgetAction):
            self._clear_native_action_tips(action)
            return
        if hasattr(action, "setProperty"):
            # Store the full Tooltip in a Python dict (not via Qt property)
            # so that body_lines / TooltipMedia objects survive the round-trip.
            source_key = self._action_tooltip_key(action)
            if source_key:
                self._action_help_store[source_key] = {
                    "title": title,
                    "description": description,
                    "tooltip": tooltip,
                    "shortcuts": list(shortcuts or ()),
                    "command_id": command_id,
                    "command_label": title,
                    "command_icon": command_icon,
                }
            action.setProperty("cams_command_id", command_id)
            action.setProperty("cams_command_label", title)
            action.setProperty("cams_command_icon", command_icon)
        HelpSystem.push(action, title, description)
        self._set_native_action_tips(action, title, description, tooltip)

    @staticmethod
    def _cursor_target_rect(pos=None):
        return QtCore.QRect(pos or QtGui.QCursor.pos(), QtCore.QSize(1, 1))

    def _menu_at_global_pos(self, pos):
        widget = QtWidgets.QApplication.widgetAt(pos)
        visited = set()
        while widget:
            widget_id = id(widget)
            if widget_id in visited:
                break
            visited.add(widget_id)
            if isinstance(widget, QtWidgets.QMenu):
                return widget
            parent_widget = getattr(widget, "parentWidget", None)
            if callable(parent_widget):
                widget = parent_widget()
                continue
            parent = getattr(widget, "parent", None)
            widget = parent() if callable(parent) else None
        for widget in QtWidgets.QApplication.topLevelWidgets():
            if isinstance(widget, QtWidgets.QMenu) and widget.isVisible() and widget.frameGeometry().contains(pos):
                return widget
        return self

    def _action_global_rect(self, action, pos=None):
        pos = pos or QtGui.QCursor.pos()
        menu = self._menu_at_global_pos(pos)
        try:
            local_pos = menu.mapFromGlobal(pos)
            hovered_action = menu.actionAt(local_pos)
            rect_action = hovered_action or action
            rect = menu.actionGeometry(rect_action)
        except (RuntimeError, ValueError, TypeError, AttributeError, KeyError, IndexError):
            return self._cursor_target_rect(pos)
        if not rect.isValid():
            return self._cursor_target_rect(pos)
        rect.moveTo(menu.mapToGlobal(rect.topLeft()))
        return rect

    def _on_action_hovered(self, action):
        if action is None or not is_valid_widget(action) or isinstance(action, QtWidgets.QWidgetAction):
            QFlatTooltipManager.hide()
            return
        if action.property("cams_tooltip_enabled") is False:
            QFlatTooltipManager.hide()
            return

        source_key = self._action_tooltip_key(action)
        if not source_key:
            return
        if QFlatTooltipManager.is_current_source(source_key):
            return

        try:
            # Retrieve Python-side data to preserve Tooltip objects and shortcut descriptors.
            action_help = dict(self._action_help_store.get(source_key, {}))
            action_help.update(getattr(action, "_tooltip_help", {}))
            title = (
                action_help.get("title")
                or action.property("cams_title")
                or action.text()
            )
            desc = action_help.get("description")
            if desc is None:
                desc = action.property("cams_description") or ""
            tooltip = action_help.get("tooltip")
            shortcuts = action_help.get("shortcuts", ())
            command_id = (
                action_help.get("command_id")
                or action.property("cams_command_id")
                or None
            )
            command_label = (
                action_help.get("command_label")
                or action.property("cams_command_label")
                or title
            )
            command_icon = (
                action_help.get("command_icon")
                or action.property("cams_command_icon")
                or None
            )
        except (RuntimeError, ValueError, TypeError, AttributeError, KeyError, IndexError):
            return

        if not (title or desc or tooltip):
            QFlatTooltipManager.hide()
            return

        if QFlatTooltipManager.enabled:
            if tooltip is not None:
                display_tooltip = tooltip
            elif desc:
                display_tooltip = tuple(desc) if isinstance(desc, (list, tuple)) else (desc,)
            else:
                display_tooltip = ""

            cursor_pos = QtGui.QCursor.pos()
            icon = action.icon() if not action.icon().isNull() else None
            QFlatTooltipManager.delayed_show(
                text=title,
                anchor_widget=self,
                target_rect=self._action_global_rect(action, cursor_pos),
                target_pos=cursor_pos,
                description=desc,
                tooltip=display_tooltip,
                shortcuts=shortcuts,
                icon_obj=icon,
                command_id=command_id,
                command_label=command_label,
                command_icon=command_icon,
                source_key=source_key,
            )

    def addAction(self, *args, **kwargs):
        metadata = {key: kwargs.pop(key, None) for key in
                    ("description", "tooltip", "shortcuts", "command_id", "command_icon")}
        enabled = kwargs.pop("tooltip_enabled", True)
        callback = kwargs.pop("callback", None)
        label = kwargs.pop("label", None)
        keep_open = kwargs.pop("open", False)
        result = super().addAction(*args, **kwargs)
        action = args[0] if args and isinstance(args[0], QAction) else result
        if action is None:
            return result
        action.setProperty("cams_tooltip_enabled", enabled)
        if keep_open:
            action.setProperty("cams_keep_menu_open", True)
            action.setData("keep_open")
        if callback:
            try:
                accepts_checked = any(p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD, p.VAR_POSITIONAL)
                                      for p in inspect.signature(callback).parameters.values())
            except (TypeError, ValueError):
                accepts_checked = False
            def invoke(checked=False):
                if action.isCheckable() and accepts_checked:
                    callback(checked)
                else:
                    callback()
            action.triggered.connect(invoke)
        existing = getattr(action, "_tooltip_help", {})
        data = {key: value if value is not None else existing.get(key) for key, value in metadata.items()}
        self._set_action_help(action, label or existing.get("title") or action.text().replace("&", ""), **data)
        return action

    def addMenu(self, *args, **kwargs):
        metadata = {key: kwargs.pop(key, None) for key in
                    ("description", "tooltip", "shortcuts", "command_id", "command_icon")}
        result = super().addMenu(*args, **kwargs)
        action = result.menuAction() if hasattr(result, "menuAction") else result
        self._set_action_help(action, action.text().replace("&", ""), **metadata)
        return result

    def hideEvent(self, event):
        QFlatTooltipManager.source_left(anchor_widget=self, anchor_unavailable=True)
        super().hideEvent(event)

    def leaveEvent(self, event):
        QFlatTooltipManager.source_left(anchor_widget=self)
        super().leaveEvent(event)
