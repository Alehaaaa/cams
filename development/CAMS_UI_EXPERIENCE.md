# Camstool overall UI: workflow and integration

The main Maya camera shelf remains the fast path for camera work. The new
**General → Tool Hub** opens a grouped command palette for camera rigs,
animation, viewport HUDs and Cams preferences. Every command reuses the
existing QAction and therefore runs the same lifecycle, shortcuts, callbacks,
and Maya operations as the Tools or General menus. The hub tracks changes to
enabled/visible action state; it is a launcher, not a second implementation of
the tools.

| Area | Primary workflow | Supporting UI |
| --- | --- | --- |
| Camera shelf | View through, rename, duplicate, select and organize cameras | Individual camera context actions and attributes dialog |
| Camera rigs | Create Follow Cam, Aim Cam or MultiCams | Tools menu and Tool Hub |
| Animation | Launch standalone Space Switcher | Tools menu and Tool Hub |
| Viewport | Select a HUD preset, toggle HUD visibility and open editor | HUD Presets, Tools menu and Tool Hub |
| Preferences | Edit camera defaults and refresh scene camera list | General menu and Tool Hub |

Camera attributes and defaults use the same flat section-header style for
lens, clipping and viewport parameters. The default-attribute dialog now
validates numeric ranges before persisting, accepts valid single-digit input,
and keeps gate mask color and opacity connected to their correct Maya camera
attributes. The HUD Editor action is a single reusable action across menus,
and dynamic preset rebuilds retire the previous QActionGroup.

## Tested and remaining scope

`tests/test_cams_ui_maya.py` runs against Maya 2024/PySide2 and exercises
launcher dispatch and action state, real camera attribute bindings, numeric
validation and color picker/brightness persistence. The 35 Space Switcher
Maya tests include standalone Qt interactions, animated rig compensation and
transactional undo. These validate component integration in Maya standalone.
An end-to-end graphical Maya session, dock/undock geometry across OS-specific
workspaces, display scaling and complex multi-viewport HUD interactions remain
manual QA targets. Their behavior must not be described as exhaustively
verified by headless tests.
