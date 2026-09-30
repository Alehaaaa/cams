"""Own Cams UI lifetime across imports, workspace changes, and reloads."""
import sys
from maya import cmds
try:
    from PySide6 import QtCore, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtWidgets
from . import util

WORKSPACE_CONTROL = "CamsWorkspaceControl"
_INSTANCE_KEY = "_aleha_cams_instance"
_CLEANING_UP = False


def get_window():
    app = QtWidgets.QApplication.instance()
    window = getattr(app, _INSTANCE_KEY, None) if app else None
    if window is not None and util.is_valid_widget(window) and not getattr(window, "_shutting_down", False):
        return window
    return None


def set_window(window):
    app = QtWidgets.QApplication.instance()
    if app:
        setattr(app, _INSTANCE_KEY, window)


def cleanup(delete_workspace=True, close_tools=True):
    global _CLEANING_UP
    if _CLEANING_UP:
        return
    _CLEANING_UP = True
    failures = []
    try:
        from .tooltips import QFlatTooltipManager
        QFlatTooltipManager.shutdown()
        window = get_window()
        # Retire the singleton before deleting native controls or processing Qt.
        set_window(None)
        candidates = [window] if window is not None else []
        app = QtWidgets.QApplication.instance()
        if app:
            for widget in app.allWidgets():
                if not util.is_valid_widget(widget) or widget in candidates:
                    continue
                module = type(widget).__module__
                if (module == "aleha_tools.cams" and type(widget).__name__ == "QCamsWindow") or (
                    close_tools and module.startswith("aleha_tools.") and widget.isWindow()
                ):
                    candidates.append(widget)
        for widget in candidates:
            if not util.is_valid_widget(widget):
                continue
            try:
                shutdown = getattr(widget, "_begin_shutdown", None)
                if shutdown:
                    shutdown()
                widget.close()
                widget.deleteLater()
            except Exception as exc:
                failures.append(str(exc))
        if close_tools:
            sys.modules["__main__"].__dict__.pop("_SPACESWITCH_INSTANCE", None)
            from .base_widgets import QFlatTooltipManager
            QFlatTooltipManager.hide()
        if delete_workspace:
            try:
                if cmds.workspaceControl(WORKSPACE_CONTROL, exists=True):
                    cmds.deleteUI(WORKSPACE_CONTROL, control=True)
                if cmds.workspaceControlState(WORKSPACE_CONTROL, exists=True):
                    cmds.workspaceControlState(WORKSPACE_CONTROL, remove=True)
            except Exception as exc:
                failures.append(str(exc))
        # Flush deletions without running arbitrary pending Maya/UI events.
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        if failures:
            raise RuntimeError("Cams cleanup incomplete: " + "; ".join(failures))
    finally:
        _CLEANING_UP = False
