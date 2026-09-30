"""

TO-DO:
    - Make it fully Python 2 compatible

    IDEAS:
    - Add HeadsUpDisplay presets

    FUTURE:

"""

DATA = {
    "TOOL": "Cams",
    "VERSION": "0.2.96beta",
    "AUTHOR": {
        "name": "Alehaaa",
        "links": {
            "Website": "https://alehaaaa.github.io",
            "GitHub": "https://github.com/Alehaaaa/cams",
            "Instagram": "https://www.instagram.com/alejandro_anim/",
        },
    },
}


def reload():
    """Reload Cams only after retiring its live widgets and callbacks."""
    import importlib
    import sys

    package = sys.modules[__name__]
    if getattr(package, "_reload_in_progress", False):
        return
    package._reload_in_progress = True
    try:
        from . import lifecycle
        if lifecycle._CLEANING_UP:
            return
        lifecycle.cleanup()
        for name in sorted(tuple(sys.modules), key=len, reverse=True):
            if not name.startswith(__name__ + "."):
                continue
            module = sys.modules.pop(name)
            parent_name, _, child = name.rpartition(".")
            parent = sys.modules.get(parent_name)
            if parent is not None and getattr(parent, child, None) is module:
                delattr(parent, child)
        importlib.invalidate_caches()
        importlib.reload(package)
        cams = importlib.import_module(__name__ + ".cams")
        return cams.show()
    finally:
        package._reload_in_progress = False


def unload():
    from . import lifecycle
    lifecycle.cleanup()


def toggle():
    from . import cams
    return cams.toggle()
