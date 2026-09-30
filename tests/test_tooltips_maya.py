"""Shared tooltip behavior with real Qt widgets in offscreen Maya."""
import os
import sys
import unittest
from unittest import mock
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'source')))
from PySide2 import QtWidgets, QtCore, QtGui, QtTest
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
import maya.standalone
maya.standalone.initialize()
from aleha_tools import tooltips as tt, widgets, base_widgets, util

def wait(ms):
    loop = QtCore.QEventLoop()
    QtCore.QTimer.singleShot(ms, loop.quit)
    loop.exec_()


class TooltipTests(unittest.TestCase):
    def setUp(self):
        tt.QFlatTooltipManager.enabled = True
        self.anchor = QtWidgets.QWidget()
        self.anchor.setGeometry(100, 100, 150, 60)
        self.anchor.show()
        app.processEvents()
        QtGui.QCursor.setPos(self.anchor.mapToGlobal(self.anchor.rect().center()))

    def tearDown(self):
        tt.QFlatTooltipManager.shutdown()
        self.anchor.close()
        self.anchor.deleteLater()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)

    def test_legacy_template_and_structured_content(self):
        data = tt.legacy_tooltip('<title>Camera</title><text>Move & aim</text><separator/><gif>demo.gif</gif>')
        self.assertEqual(data.title, 'Camera')
        self.assertEqual(data.body_lines[0], 'Move & aim')
        self.assertIs(data.body_lines[1], tt.separator)
        self.assertIsInstance(data.body_lines[2], tt.TooltipMedia)
        tt.QFlatTooltipManager.show(anchor_widget=self.anchor, template='<title>Camera</title><text>Move & aim</text>')
        texts = [label.text() for label in tt.QFlatTooltipManager._current_tooltip.findChildren(QtWidgets.QLabel)]
        self.assertIn('Camera', texts)
        self.assertIn('Move & aim', texts)

    def test_handoff_and_shutdown_release_qt_objects(self):
        manager = tt.QFlatTooltipManager
        manager.show(text='First', anchor_widget=self.anchor, source_key='first')
        first = manager._current_tooltip
        manager.show(text='Second', anchor_widget=self.anchor, source_key='second')
        self.assertFalse(first.isVisible())
        self.assertEqual(len(tt.TooltipStackManager._valid_entries()), 1)
        event_filter = manager._mouse_filter
        manager.shutdown()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        self.assertFalse(util.is_valid_widget(event_filter))
        self.assertIsNone(manager._current_tooltip)
        self.assertFalse(tt.TooltipStackManager._valid_entries())

    def test_delayed_request_canceled_when_source_leaves(self):
        manager = tt.QFlatTooltipManager
        manager.delayed_show(delay=20, text='Camera', anchor_widget=self.anchor, source_key='camera')
        manager.source_left(source_key='camera')
        wait(40)
        self.assertIsNone(manager._current_tooltip)
        manager.delayed_show(delay=20, text='Camera', anchor_widget=self.anchor)
        self.anchor.hide()
        wait(40)
        self.assertIsNone(manager._current_tooltip)

    def test_menu_callback_once_and_rich_action_update(self):
        menu = widgets.QFlatMenu('Tools', self.anchor)
        callback = mock.Mock()
        action = menu.addAction('Run', callback=callback)
        callback.assert_not_called()
        action.trigger()
        callback.assert_called_once_with()
        rich = widgets.QFlatAction('Rich', menu)
        menu.addAction(rich)
        body = tt.Tooltip('help', body_lines=(tt.TooltipLink('https://example.com', 'Docs'), tt.separator))
        rich.setToolTipData(text='Updated', tooltip=body)
        with mock.patch.object(tt.QFlatTooltipManager, 'delayed_show') as show:
            menu._on_action_hovered(rich)
            self.assertIs(show.call_args.kwargs['tooltip'], body)
        self.assertFalse(menu.toolTipsVisible())

    def test_icon_only_button_hover(self):
        button = widgets.QFlatPushButton(self.anchor)
        pix = QtGui.QPixmap(10, 10)
        pix.fill(QtGui.QColor('red'))
        button.setIcon(QtGui.QIcon(pix))
        button.enterEvent(QtCore.QEvent(QtCore.QEvent.Enter))
        self.assertFalse(button.get_toolTipData()['icon'].isNull())

    def test_camera_shortcuts_render(self):
        tt.QFlatTooltipManager.show(text='Camera', anchor_widget=self.anchor,
            description='Manage this camera. Right-click for the context menu.',
            shortcuts=widgets.QFlatCamButton.SHORTCUT_CONFIG)
        tip = tt.QFlatTooltipManager._current_tooltip
        labels = [label.text() for label in tip.findChildren(QtWidgets.QLabel)]
        self.assertIn('Shortcuts', labels)
        for shortcut in widgets.QFlatCamButton.SHORTCUT_CONFIG:
            self.assertIn(shortcut['label'], labels)
        app.processEvents()
        if os.environ.get('CAMS_TEST_SCREENSHOTS'):
            tip.grab().save('/tmp/cams-tooltip.png')

    def test_confirmation_is_not_owned_by_hover_manager(self):
        def finish(dialog):
            self.assertIsNone(tt.QFlatTooltipManager._current_tooltip)
            self.assertIn(dialog, tt.TooltipStackManager._valid_entries())
            tt.QFlatTooltipManager.hide()
            self.assertTrue(dialog.isVisible())
            dialog.reject()
        with mock.patch.object(base_widgets.QFlatTooltipConfirm, 'exec_', finish):
            base_widgets.QFlatTooltipConfirm.question(self.anchor, message='Continue?')
        self.assertFalse(tt.TooltipStackManager._valid_entries())

if __name__ == '__main__':
    success = unittest.main(exit=False).result.wasSuccessful()
    maya.standalone.uninitialize()
    sys.exit(0 if success else 1)
