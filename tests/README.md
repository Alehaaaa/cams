Run each regression suite in a separate Maya 2024 `mayapy` process (PySide2):

```sh
QT_QPA_PLATFORM=offscreen /path/to/mayapy tests/test_spaceswitch_maya.py
QT_QPA_PLATFORM=offscreen /path/to/mayapy tests/test_cams_lifecycle_maya.py
QT_QPA_PLATFORM=offscreen /path/to/mayapy tests/test_tooltips_maya.py
```

SpaceSwitch tests use actual Maya scenes, curves, transforms, undo, and offscreen Qt widgets. Cams lifecycle tests use real Qt widgets with native workspace/shelf commands mocked. Set `CAMS_TEST_SCREENSHOTS=1` to save SpaceSwitch previews to `/tmp/cams-spaceswitch.png` and `/tmp/cams-multiswitch.png`.

Tooltip tests cover legacy templates, structured action help, hover cancellation, callback dispatch, confirmation ownership, and event-filter cleanup using real Qt widgets.

Interactive Maya checks still required:

- Ctrl/Cmd-select enum rows, choose per-control values, then Apply or Cancel; check single undo and unchanged world poses on production rigs.
- Switch a constrained/layered rig through a selected timeline range; compare the fast rotation-order mode with the fallback.
- Dock Cams at the shelf, timeline, and side panels; collapse/restore, float/redock, and change Maya workspaces.
- Hover camera buttons and menu actions; move into tooltip links and out again, then reload with a tooltip visible.
- Toggle the shelf button repeatedly and use General → System → Reload Cams with SpaceSwitch open; verify no duplicate windows, tab overlays, or callbacks.

Reload entry point: `import aleha_tools; aleha_tools.reload()`. Regular `cams.show()` reuses the live window; shelf buttons use `aleha_tools.toggle()`.
