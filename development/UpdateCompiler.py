import maya.cmds as cmds
import maya.mel as mel

import sys
import json
import zipfile
import logging
import shutil
import importlib
import re
from pathlib import Path


class CompileCams:
    def __init__(self, source_path=None, destination=None, cams_version=None) -> None:
        """
        Initialize the compiler.
        Args:
            source_path: Path to the source directory. If None, it will be detected.
            destination: Path to the project root. If None, it will be detected.
            cams_version: Version string. If None, it will be read from aleha_tools.
        """
        # Determine destination first as other paths depend on it
        self.destination = Path(destination) if destination else Path(__file__).resolve().parents[1]
        self.source_path = Path(source_path) if source_path else self.destination / "source" / "aleha_tools"

        if not cams_version:
            # Add source_path's parent to sys.path to ensure we can import aleha_tools
            # especially if calling from outside the repo structure.
            parent_dir = str(self.source_path.parent)
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)

            try:
                import aleha_tools  # type: ignore

                importlib.reload(aleha_tools)
                cams_version = aleha_tools.DATA["VERSION"]
            except (ImportError, KeyError, AttributeError):
                logging.warning(
                    "Could not automatically detect version from aleha_tools. Please provide cams_version."
                )
                cams_version = "0.0.0"

        self.cams_version = cams_version

        self.zip_file = "aleha_tools-%s.zip" % self.cams_version
        self.zip_destination_path = self.destination / "versions" / self.zip_file
        self.json_notes = self.destination / "release_notes.json"

    @staticmethod
    def create_progressbar(mainBar, filename):
        message = "Saving file: %s" % filename

        cmds.progressBar(
            mainBar,
            edit=True,
            beginProgress=True,
            isInterruptable=False,
            status=message,
        )

    @staticmethod
    def prompt_for_notes(version):
        notes = cmds.promptDialog(
            title="Cams Release Notes",
            message="Enter %s release notes:" % version,
            button=["OK", "Cancel"],
            defaultButton="OK",
            cancelButton="Cancel",
            dismissString="Cancel",
        )

        if notes == "OK":
            return cmds.promptDialog(query=True, text=True)

        return False

    def main(self):
        all_notes = self.read_version_notes(self.cams_version, self.json_notes)

        if not all_notes:

            def _load_module(path, name):
                spec = importlib.util.spec_from_file_location(name, str(path))
                if not spec:
                    raise ImportError("No module at '%s'" % path)
                module = importlib.util.module_from_spec(spec)
                try:
                    spec.loader.exec_module(module)
                except Exception as e:
                    raise ImportError("Error in '%s': %s" % (path, e))
                return module

            def _run_method(module, cls_name, method="main", *args):
                if not hasattr(module, cls_name):
                    raise AttributeError("No class '%s' in '%s'" % (cls_name, module.__name__))

                instance = getattr(module, cls_name)(*args)

                if not hasattr(instance, method) or not callable(getattr(instance, method)):
                    raise AttributeError("No callable method '%s' in '%s'" % (method, cls_name))
                return getattr(instance, method)()

            path = Path(__file__).parent / "ChangesCompiler.py"
            name = "generate_changes_cams"
            cls = "CamsToolUpdater"
            method = "run"

            all_notes = _run_method(
                _load_module(path, name),
                cls,
                method,
                self.source_path,
                self.cams_version,
            )

            logging.info("Automatically made the changelog: %s" % str(all_notes))

            # Use os.startfile on windows, otherwise try subprocess or system
            if sys.platform == "win32":
                import os

                os.startfile(str(self.json_notes))
            else:
                import subprocess

                try:
                    subprocess.run(["open", str(self.json_notes)])
                except Exception:
                    pass

            if all_notes:
                self.update_release_notes(self.cams_version, all_notes, self.json_notes)
            else:
                logging.info("No notes provided. Exiting.")
                return

        self.zip_directory(self.source_path)

        logging.info("Saved Version %s in: %s" % (self.cams_version, self.zip_destination_path))

        cmds.evalDeferred(
            lambda: (
                "from importlib import reload;import importlib;import aleha_tools.cams as cams;reload(cams); cams.show()"
            ),
            lowestPriority=True,
        )

    def read_version_notes(self, version, json_file):
        if not Path(json_file).exists():
            return None
        with open(json_file, "r") as file:
            data = json.load(file)

        return data.get("versions", {}).get(version)

    def update_release_notes(self, version, notes, json_file):
        json_file = Path(json_file)
        if json_file.exists():
            with open(json_file, "r") as file:
                data = json.load(file)
        else:
            data = {"versions": {}}

        data["versions"][version] = notes

        # Keep versions ordered descending using our robust comparison
        try:
            from aleha_tools.util import compare_versions
            from functools import cmp_to_key

            ordered_versions = sorted(
                data["versions"].items(),
                key=cmp_to_key(lambda x, y: compare_versions(x[0], y[0])),
                reverse=True,
            )
        except (ImportError, Exception):
            ordered_versions = sorted(data["versions"].items(), key=lambda x: x[0], reverse=True)

        data["versions"] = dict(ordered_versions)

        with open(json_file, "w") as file:
            json.dump(data, file, indent=4)

    def copy_all_files(self, source_path, saved_path):
        source_path = Path(source_path)
        saved_path = Path(saved_path)

        if not saved_path.exists():
            saved_path.mkdir(parents=True)

        for item in source_path.iterdir():
            dst = saved_path / item.name

            if item.is_file():
                shutil.copy2(item, dst)
            elif item.is_dir():
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(item, dst)

    def zip_directory(self, source_path):
        source_path = Path(source_path)
        data_file = source_path / "__init__.py"

        if data_file.is_file():
            # Match "VERSION": or 'VERSION':
            version_pattern = re.compile(r"(['\"]VERSION['\"]:\s*['\"])([^'\"]+)(['\"])")

            with open(data_file, "r") as file:
                content = file.read()

            new_content = version_pattern.sub(r"\g<1>" + self.cams_version + r"\g<3>", content)

            with open(data_file, "w") as file:
                file.write(new_content)

        mainBar = mel.eval("$tmp = $gMainProgressBar")

        # Create versions folder if missing
        self.zip_destination_path.parent.mkdir(parents=True, exist_ok=True)

        # ZipFile expects a string or file-like object. Path is supported in 3.6+
        with zipfile.ZipFile(self.zip_destination_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            # We use rglob("*") to walk through everything
            for item in source_path.rglob("*"):
                # Skip certain folders
                if any(part in item.parts for part in ("_prefs", "__pycache__")):
                    continue

                if item.is_file():
                    if item.name.endswith(".pyc"):
                        continue
                    self.create_progressbar(mainBar, item.name)
                    arc_name = Path("aleha_tools") / item.relative_to(source_path)
                    zipf.write(item, arcname=arc_name)

        # Update root version file
        with open(self.destination / "version", "w") as f:
            f.write(self.cams_version)

        # Save 'latest' version
        latest_path = self.destination / "versions" / "aleha_tools-latest.zip"
        if latest_path.is_file():
            latest_path.unlink()
        shutil.copy(self.zip_destination_path, latest_path)

        cmds.progressBar(mainBar, edit=True, endProgress=True)


if __name__ == "__main__":
    compiler = CompileCams()
    compiler.main()
