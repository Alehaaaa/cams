# animBot 2.9.3 Space Switcher — executable evidence and Camstool mapping

This is a bounded compatibility investigation, not a claim to possess animBot's
original source. The installed reference is Python bytecode with heavily
obfuscated identifiers. Reproduce the observations without importing animBot:

```
python3.13 development/animbot_space_bytecode.py /Users/aleha/Documents/maya/scripts/animBot/attributeSpaceSwitcher/__hybrid__/attributeSpaceSwitcher313.pyc --find keyframe
python3.13 development/animbot_space_bytecode.py /Users/aleha/Documents/maya/scripts/animBot/attributeSpaceSwitcher/__hybrid__/attributeSpaceSwitcherUI313.pyc --find 'Xform Target'
```

## Reference identity and call boundaries

| Artifact | SHA-256 | Direct observations |
| --- | --- | --- |
| `attributeSpaceSwitcher313.pyc` | `dac99b510de2741e5cab5e65bbb4ae41eb86786b621b93fb15a31f09acd545a4` | Class `AttributeSpaceSwitcher`, exposed selection/asset click/menu entry points, nested switching and gimbal-scoring handlers |
| `attributeSpaceSwitcherUI313.pyc` | `a950657ac1cd50d212feadeadac42b238404e40064beb2bf74a435775ad1c44d` | Widget tree and per-switch Xform Target controls; remove-switch action and explanatory tooltip |
| `animBot/_api/__hybrid__/core313.pyc` | `54f80547649867f5f0358344a4666f429102993c8e2287e04982caa5e2e8ef38` | Shared `Core.checkXformMultiFrameXformLightningMode` and `Core.performMultiFrameXformLightningMode` entry points |

The importer redirects Python 3.13 to `__hybrid__/*313.pyc`; the compiled
modules depend on `animBot._api.__hybrid__.core313`. The shared CORE implementation
is a further behavior boundary. REA CLI 6.4.0 reported `target_unavailable`
(`unsupported binary format`) for these `.pyc` files; bytecode observations
below were obtained using CPython 3.13 `marshal` and `dis`, *not* REA Evidence IDs.

## Evidence-to-implementation trace

| Feature | Compiled evidence | Camstool behavior / verification |
| --- | --- | --- |
| Selection/asset entry | Public class names `selectionAttributeSpaceSwitcher_click`, `assetAttributeSpaceSwitcher_click`, corresponding menus | `combined_catalog` and `asset_catalog`; Maya namespace/curve-shape test |
| Multiple target setup | UI literal `Xform Targets:`, `Add Xform Target`, `Remove this Xform Target` | `SetupTargetsDialog`, per-rig QSettings overrides, multi-target compensation test |
| Remove visible switch | UI literal `Remove Switch (%s)` and `Remove this switch from the panel (you can add it back later if needed).` | Persistent hide for discovered switches, custom removal, and restore menu; Maya view test |
| Main switching | Compiled class nested handler at source-line anchor 1802 calls `setCurrentTime`, `duplicate(parentOnly=True)`, `pointConstraint`, `orientConstraint`, `setAttr`, `setKeyframe`, `deleteNode` | `SwitchExecutor` samples world matrices and writes new switch keys before compensation; Maya current-key/all-keys/multiple-target tests |
| Evaluated frame capture | The same compiled handler has `setCurrentTime` call sites at offsets 248, 352 and 1932 around temporary transform work | Camstool now evaluates each sampled frame and queries `xform(ws=True, matrix=True)` before writing, restoring the original time on exit; a repeated 1→0→1 switch test caught a stale `getAttr(worldMatrix, time=...)` result and verifies the fix |
| Multi-frame pose preservation | Handler references `checkXformMultiFrameXformLightningMode`; key-writing handler at anchor 1954 uses `setCurrentTime` and `setKeyframe` | `collect_frames`, guard frames, stepped attribute keys, compensated T/R/S values; Maya key tests |
| Shared asynchronous multi-frame engine | Space-switch handler at anchor 1802 calls the `Core.checkXformMultiFrameXformLightningMode` method (core line 699), which inspects a shared `lastXformMultiFrameXformLightningModeProcessInstance` | Camstool uses `OperationRunner` with a cancellable coordinator and all Maya scene work on the UI thread; tested through actual Qt thread marshalling |
| Reentrant process guard | `Core.checkXformMultiFrameXformLightningMode` offsets 0–106 compare the active process with `CORE.lastXformMultiFrameXformLightningModeProcessInstance` and return early on an already active/equivalent process; offsets 150–458 enter context managers and handle `RuntimeError` | Camstool rejects an overlapping `_apply_requests` while its undo/compensation job is active; Maya UI test verifies the early return |
| Lightning-mode eligibility | `Core.performMultiFrameXformLightningMode` line 674 checks persisted `multiFrameXformLightningMode`, iterates supplied objects, and branches on `MFn.kJoint` and a per-joint predicate before returning a boolean | Camstool retains its guarded pure-curve rotation-order fast path, with Maya coverage of a nontrivial `jointOrient` rig; the obfuscated joint predicate has not been established |
| Scene callback attachment | `AttributeSpaceSwitcher` handler at line 125 references `CORE.callbackBot`, `MEventMessage.addEventCallback`, and the literal `SelectionChanged` | Camstool adds Maya event callbacks and removes them on close, verified in Maya with pending timers |
| Numeric switch discontinuity | The compiled handler writes explicit switch keys, but its obfuscated tangent decisions have not been completely recovered | Camstool now steps the preceding curve segment when writing a discrete switch key; Maya test exposed 0.84375 pre-switch interpolation before the fix |
| Rotate-order scoring | Named `__getNodeGimbalScores` at anchor 1165; `rotateOrder`, temporary duplicate, transform sampling | `GimbalAnalyzer` computes mean and worst-frame scores; Maya scoring test |
| Runtime cleanup | Handler at anchor 1802 includes `CORE.nodeBot.deleteNode` after temporary duplicate/constraint work | No temporary Maya nodes are created by Camstool's matrix-based compensation; undo chunk and main-thread marshal are tested |
| Reference compensation branch | Handler at anchor 1802 bytecode offsets 830–904 create a parent-only `animBot_Temp_#` duplicate; offsets 1250–1348 conditionally run `pointConstraint`, and 1508–1606 call `orientConstraint`; offsets 1360–1762 read `tx/ty/tz/rx/ry/rz` after constraints | Direct executable control-flow evidence of a temporary-duplicate/constraint sampling route, *not* proof that every target takes that route. Camstool's matrix compensation supports nested parent/child targets in Maya without persistent temporary nodes. |
| Reference explicit channel keys | Main handler at offsets 2248–2430 branches on `isKeyable`: `cmds.setKeyframe(..., attribute=..., time=..., value=...)` if keyable, otherwise invokes an obfuscated attribute setter. At offsets 2836–3116 and 3306 onward, it writes explicit `tx/ty/tz/rx/ry/rz` values reconstructed from temporary references. | Camstool can key channel-box-only switch attributes, and now verifies that switch and compensated transform keys actually appear in Maya's curve data. A deliberately dropped `setKeyframe` raises `PoseCompensationError` for transactional UI rollback. |
| Layered rotation curves | No `animLayer` symbol appears in the searched names/constants of the main switch handler or `core313.pyc`; indirect wrappers and obfuscated names remain possible | Maya 2024's selected layer receives compensation keys while base keys stay unchanged. Camstool's Euler filtering now traverses `animBlendNode*` upstream to reach both base and layered rotation curves; tested through the real Maya DG and widget. This is Maya-derived behavior, not attributed to animBot. |
| Impossible pose and interrupted operation | The reference uses temporary transforms and multiple write/cleanup stages; full exception edges remain obfuscated | Camstool verifies the evaluated matrix after writing, raises `PoseCompensationError` if exact matching is impossible, and rolls the undo chunk back; tests cover fully locked translation, selected-range undo/redo, and cancellation after partial writes |
| UI lifecycle | UI bytecode contains Qt layouts, click callbacks, tooltips, hide/deleteLater | Popup, multi-switch dialog, target setup, callback removal and refresh batching in `SpaceSwitchAlehaWidget` |

## Verified and unresolved boundaries

- Verified in Maya 2024 standalone: enum explicit indices; connected/local vs
  user-added attributes; namespaced assets; persistent switch hiding/restoring;
  unchanged world transforms after current-key, all-key and multiple-target
  switches; selected-range boundaries; locked-but-unaffected channels; pre-switch
  numeric hold; failing locked-channel rollback; cancellation after partial
  compensation; single-step undo/redo; coordinator main-thread marshalling;
  repeated/no-op switching; oriented joints; callback disposal; gimbal sample
  ranking and UI widget creation. Additional cases: active animation-layer
  compensation without new base keys, layered Euler-filter curve discovery,
  nested controls with shared space attribute and reversed request order,
  constraint-connected/locked translation with undo, channel-box-only attribute
  switching, silently refused key insertion, and a real Alt-click on a visible
  switch row followed by Maya undo.
- Inference: the duplicate-and-constraint path preserves the old world pose
  across space evaluation. Camstool implements that user-visible invariant with
  sampled matrices rather than reproducing the reference's temporary nodes.
- Not fully recoverable from these observations: obfuscated CORE algorithms,
  animBot's exact failure handling for constraints/locked rig channels, callback
  lifecycle inside Maya's full graphical shell, and commercial plugin-specific
  persistence formats. Maya standalone tests do not simulate every production rig
  or Graph Editor interaction. A Maya probe also found a concrete residual
  limitation: on sparse current-frame switches, altering a compensated curve
  key at frame 5 can change the interpolated world pose at frame 4 even when
  the original key poses at frames 1 and 10 remain fixed. A dense/in-between
  compensation mode or shape-preserving discontinuity handling requires a
  separate algorithm; the current key-sample guarantee does not imply
  continuous-time preservation between those samples.

## Verification scope (Maya 2024)

The expanded `tests/test_spaceswitch_maya.py` suite exercises 32 independent
scenarios, including the six new complex-rig/layer/write-failure cases above
and native Qt mouse interaction. These are scene-level observations. The
failed intermediate-frame probe is recorded as a limitation rather than
misrepresented as a passing regression. The reference branch above also
includes cleanup on cancellation at offsets 1966–2174, but its exact
exception-safety guarantees remain obscured by called wrappers; Camstool's
transaction is verified independently through undo of rejected keys and
constraint-impossible poses.

## Relevant locations

- Discovery and attribute taxonomy: `SwitchCatalogBuilder`, `Maya.enum_items`.
- Evaluated transform preservation, scope and keys: `SwitchExecutor`.
- Per-rig targets, hidden switches, names, menus: `SpaceSwitchAlehaWidget`.
- Executable validation: `tests/test_spaceswitch_maya.py`.

The bytecode utility and this note deliberately leave uncertain claims explicit
so further shared-CORE tracing can extend the reconstruction safely.
