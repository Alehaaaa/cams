import maya.OpenMayaUI as omui
from importlib import reload
from functools import wraps

# Attempt to import PySide6, fallback to PySide2 if unavailable
try:
    from PySide6.QtWidgets import QMainWindow, QWidget  # type: ignore
    from PySide6.QtGui import QIcon, QAction  # type: ignore
except ImportError:
    from PySide2.QtWidgets import QAction, QMainWindow, QWidget
    from PySide2.QtGui import QIcon

# Import and reload necessary modules
from . import settings, widgets, funcs, util

reload(settings)
reload(widgets)
reload(funcs)
reload(util)


def tool(label, icon="debug", category="General"):
    """
    Decorator to mark a method as a debug tool.
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        wrapper._is_debug_tool = True
        wrapper._label = label
        wrapper._icon = icon
        wrapper._category = category
        wrapper._description = func.__doc__.strip() if func.__doc__ else ""
        return wrapper

    return decorator


class DebugManager:
    def __init__(self, ui):
        self.ui = ui

    def _get_cams_widget(self):
        workspace_control = self.ui.parent().objectName() if self.ui.parent() else self.ui.objectName() + "WorkspaceControl"
        ptr = omui.MQtUtil.findControl(workspace_control)
        if ptr:
            return util.get_maya_qt(ptr, QWidget)
        return None

    @tool("Log UI Structure", category="UI")
    def log_ui_structure(self):
        """Logs the internal tracking state: displayed buttons and camera sets."""
        print("\n--- Cams UI Internal State ---")
        print("Cams Version: %s" % getattr(self.ui, "VERSION", "Unknown"))

        buttons = getattr(self.ui, "all_displayed_buttons", {})
        print("Displayed Buttons Count: %d" % len(buttons))
        for cam, btn in buttons.items():
            valid = util.is_valid_widget(btn)
            print("  - %s: %s (Valid: %s)" % (cam, btn, valid))

        workspace_control = self.ui.parent().objectName() if self.ui.parent() else self.ui.objectName() + "WorkspaceControl"
        print("Workspace Control: %s" % workspace_control)
        print("------------------------------\n")

    @tool("Debug UI Parentage", category="UI")
    def debug_ui_parentage(self):
        """Prints the chain of parent widgets leading to the Maya Main Window."""
        cams_ui = self._get_cams_widget()
        if not cams_ui:
            print("Could not find Cams UI widget.")
            return

        parents = []
        curr = cams_ui
        while curr:
            parents.append(curr)
            curr = curr.parent()

        print("\n--- Cams UI Parent Chain ---")
        for i, w in enumerate(reversed(parents)):
            info = "%s (%s)" % (w.objectName(), w.__class__.__name__)
            if isinstance(w, QMainWindow):
                info += " [MainWindow]"
            print("  " * i + "> " + info)
        print("----------------------------\n")

    @tool("Print Active Prefs", category="Data")
    def print_prefs(self):
        """Dumps currently loaded user preferences to the console."""
        print("\n--- Cams User Prefs ---")
        import json

        prefs = getattr(self.ui, "user_prefs", {})
        print(json.dumps(prefs, indent=4))
        print("-----------------------\n")


def on_show(ui):
    """Entry point for populating the debug menu."""
    menu = getattr(ui, "debug_menu", None)
    if not util.is_valid_widget(menu):
        return

    try:
        menu.clear()
    except RuntimeError:
        return

    manager = DebugManager(ui)

    # Group tools by category
    categories = {}

    for attr_name in dir(manager):
        attr = getattr(manager, attr_name)
        if hasattr(attr, "_is_debug_tool"):
            cat = attr._category
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(attr)

    # Sort categories
    sorted_cats = sorted(categories.keys())

    for i, cat in enumerate(sorted_cats):
        if i > 0:
            menu.addSeparator()

        for tool_func in categories[cat]:
            action = QAction(QIcon(util.return_icon_path(tool_func._icon)), tool_func._label, menu)
            if tool_func._description:
                action.setToolTip(tool_func._description)
                action.setStatusTip(tool_func._description)

            # Connect the tool
            action.triggered.connect(lambda checked=False, f=tool_func: f())
            menu.addAction(action)
