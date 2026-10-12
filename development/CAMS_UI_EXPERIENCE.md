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
attributes. HUD Presets rebuilds retire the previous QActionGroup, and each
menu owns its own HUD Editor action so clearing one menu cannot destroy an
action used by another.

## October 2026 integration changes

- Tool Hub detects invalid/deleted Qt actions and resolves replacements on
  reopening. A Maya/PySide2 test deletes a QAction and verifies the fallback;
  another rebuilds the live HUD menu repeatedly.
- Tool launching retains imported shared widget classes across invocations.
  HUD Editor now opens one reusable dialog without an accidental duplicate,
  saves presets through shared settings, refreshes its shelf menu and copies
  each new preset from defaults without mutable aliases.
- MultiCams has a shared-style Qt dialog with editable source camera list
  (add from Maya selection/remove highlighted), name field,
  feedback and one-instance reopening. The Maya rig uses one constraint for
  all source cameras, stepped driven weights and focal-length blending wired
  to camera shapes. One-step undo and rollback on a failed curve write are
  covered by Maya scene tests.
- Existing `.aleha` preference representations are read with literal parsing
  instead of executing preference text.

## Tested and remaining scope

`tests/test_cams_ui_maya.py` runs against Maya 2024/PySide2 and exercises
launcher dispatch and action state, real camera attribute bindings, numeric
validation and color picker/brightness persistence. New coverage checks HUD
reopen/preset isolation, deleted menu actions, two-camera rig switching and
focal lengths, undo and failure rollback. The 36 Space Switcher
Maya tests include standalone Qt interactions, animated rig compensation and
transactional undo. These validate component integration in Maya standalone.
An end-to-end graphical Maya session, dock/undock geometry across OS-specific
workspaces, display scaling and complex multi-viewport HUD interactions remain
manual QA targets. Their behavior must not be described as exhaustively
verified by headless tests.
