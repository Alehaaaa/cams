import os
import ast

# from .util import *


"""
Create functions
"""


def initial_settings():
    # Default settings
    return {
        "startupSettings": {
            "position": ["AttributeEditor", "top"],
            "startup_hud": False,
            "startup_viewport": True,
            "startup_run_cams": True,
            "skip_update": False,
            "confirm_exit": True,
        },
        "defaultCameraSettings": {
            "camera": ("persp", True),
            "overscan": (1.0, True),
            "near_clip": (1.0, True),
            "far_clip": (10000.0, True),
            "display_resolution": (1, True),
            "mask_opacity": (1.0, True),
            "mask_color": ([0.0, 0.0, 0.0], True),
        },
        "hudSettings": {
            "presets": {
                "Default": {
                    "bmc": 6,
                    "trc": 0,
                    "tlc": 0,
                    "tmc": 0,
                    "brc": 0,
                    "blc": 8,
                }
            },
            "selected": 0,
        },
    }


def get_prefs_path(settings=True):
    prefs_dir = os.path.join(
        os.path.dirname(__file__),
        "_prefs",
    )
    if not os.path.exists(prefs_dir):
        os.makedirs(prefs_dir)

    if settings:
        settings = list(initial_settings().keys())

    # Old Maya preferences are deliberately preserved. Reading new preferences
    # must have no destructive side effects.

    return prefs_dir, settings


def get_all_prefs():
    all_prefs = {}
    prefs_path, all_settings = get_prefs_path()
    initial = initial_settings()

    for setting in all_settings:
        setting_path = os.path.join(prefs_path, setting + ".aleha")

        if os.path.exists(setting_path):
            try:
                with open(setting_path, "r") as setting_file:
                    all_prefs[setting] = ast.literal_eval(setting_file.read())
            except Exception:
                all_prefs[setting] = initial[setting]
                save_to_disk(setting, initial[setting])
        else:
            all_prefs[setting] = initial[setting]
            save_to_disk(setting, initial[setting])

    return all_prefs


def get_pref(setting):
    prefs_path, _ = get_prefs_path(settings=False)

    setting_path = os.path.join(prefs_path, setting + ".aleha")

    if os.path.exists(setting_path):
        with open(setting_path, "r") as setting_file:
            return ast.literal_eval(setting_file.read())
    else:
        return None


def save_to_file(prefs_path, setting_name, settings):
    setting_path = os.path.join(prefs_path, setting_name + ".aleha")
    with open(setting_path, "w") as setting_file:
        setting_file.write(str(settings))
    return setting_path


def save_to_disk(setting_name=None, settings=None):
    prefs_path, all_settings = get_prefs_path()

    if settings:
        if setting_name:
            setting_path = save_to_file(prefs_path, setting_name, settings)
        else:
            for setting_name in all_settings:
                setting_path = save_to_file(prefs_path, setting_name, settings)
    else:
        initial = initial_settings()
        for setting_name in all_settings:
            setting_path = save_to_file(prefs_path, setting_name, initial[setting_name])  # noqa: F841
