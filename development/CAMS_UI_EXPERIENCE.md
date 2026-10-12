# Camstool overall UI: workflow and integration

The main Maya camera shelf remains the fast path for camera work. The new
**General → Tool Hub** opens a grouped command palette for camera rigs,
animation, viewport HUDs and Cams preferences. Every command reuses the
existing QAction and therefore runs the same lifecycle, shortcuts, callbacks,
and Maya operations as the Tools or General menus. The hub tracks changes to
enabled/visible action state; it is a launcher, not a second implementation of
the tools.
The main camera strip also exposes a compact Cams Tools button beside the
scrollable camera list. The existing General menu action remains available.

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
- Follow Cam and Aim Cam now share guarded camera creation, metadata setup,
  container configuration and undo recovery. The Aim Cam creator adds missing
  `cams_type` and offset metadata on a standard Maya camera; the old path
  raised `setAttr: No object matches name` halfway through creation. Follow
  Cam locks explicitly named group channels, rather than relying on Maya's
  implicit current selection. Both restore the prior selection on failure.
- Camera shelf context actions compare full DAG paths for nested/namespaced
  camera selection. Ephemeral context menu QActionGroups are owned by their
  menu rather than accumulating on the long-lived camera button.
- The Tool Hub refreshes action validity even when its window remains visible
  across repeated openings; this covers another deleted-QAction edge case.
- Multi Switch keeps the same floating dialog and the same option widgets when
  more channels are staged. Diffing by object/attribute identity preserves
  staged choices and scope, removes stale columns, and recomputes grid wrapping
  on both resizing and reordering. Headless Qt checks exercise addition,
  removal, reuse, option retention and 1-to-3-column resize. Larger channel
  sets scroll vertically inside a bounded-height list without window overflow.
- Space Switcher no longer exposes an automatic high-fidelity baking mode. The
  two-pass operation saves evaluated poses at control keys, then switches and
  applies compensation at those keys. Fast Rotate Order performs direct curve
  conversion without entering the pose-pass UI. The intermittent failed-
  trajectory dialog is removed. See the audit for the remaining interpolation
  trade-off between authored keys.

## Tested and remaining scope

`tests/test_cams_ui_maya.py` runs against Maya 2024/PySide2 and exercises
launcher dispatch and action state, real camera attribute bindings, numeric
validation and color picker/brightness persistence. New coverage checks HUD
reopen/preset isolation, deleted menu actions, two-camera rig switching and
focal lengths, Follow/Aim creation from real Maya scene selection, metadata,
single-step undo and constraint-failure rollback, nested camera context
selection and reopening the Tool Hub with a destroyed QAction. The 44 Space Switcher
Maya tests include standalone Qt interactions, animated rig compensation and
transactional undo. These validate component integration in Maya standalone.
An end-to-end graphical Maya session, dock/undock geometry across OS-specific
workspaces, display scaling and complex multi-viewport HUD interactions remain
manual QA targets. Their behavior must not be described as exhaustively
verified by headless tests.
