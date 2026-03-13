import os
import ssl
import json
import shutil
import zipfile
import urllib.request
import urllib.error
from pathlib import Path
from http.client import responses

try:
    from importlib import reload
except ImportError:
    pass

try:
    from PySide6.QtCore import QTimer, QThread, Signal
except ImportError:
    from PySide2.QtCore import QTimer, QThread, Signal

import maya.cmds as cmds
import maya.mel as mel

from . import funcs, util
from .util import compare_versions
from .base_widgets import QFlatConfirmDialog, QFlatTooltipConfirm

# Constants
REPO = "https://raw.githubusercontent.com/Alehaaaa/camstool/main/"
NO_DATA_ERROR = "<hl>No Data</hl>\nCould not sync with the server."
NO_SERVER_ERROR = "<hl>%s %s</hl>\nCould not sync with the server."

# SSL Context
unverified_ssl_context = ssl.create_default_context()
unverified_ssl_context.check_hostname = False
unverified_ssl_context.verify_mode = ssl.CERT_NONE


def formatPath(path):
    path = str(path).replace("/", os.sep)
    path = path.replace("\\", os.sep)
    return path


def download(downloadUrl, saveFile):
    response = urllib.request.urlopen(downloadUrl, context=unverified_ssl_context, timeout=60)

    if response is None:
        cmds.warning("Error trying to install.")
        return

    total_size = response.getheader("Content-Length")
    total_size = int(total_size) if total_size else 0
    block_size = 8192

    try:
        gMainProgressBar = mel.eval("$tmp = $gMainProgressBar")
        if total_size > 0 and gMainProgressBar:
            cmds.progressBar(
                gMainProgressBar,
                edit=True,
                beginProgress=True,
                isInterruptable=False,
                status="Downloading Update...",
                maxValue=total_size,
            )
    except Exception:
        gMainProgressBar = None

    downloaded = 0
    try:
        with open(saveFile, "wb") as output:
            while True:
                buffer = response.read(block_size)
                if not buffer:
                    break
                downloaded += len(buffer)
                output.write(buffer)
                if gMainProgressBar and total_size > 0:
                    cmds.progressBar(gMainProgressBar, edit=True, progress=downloaded)
    finally:
        if gMainProgressBar and total_size > 0:
            cmds.progressBar(gMainProgressBar, edit=True, endProgress=True)
    return True


def install(tool, command=None, file_path=None):
    # Derive the actual installation path of `aleha_tools`
    toolsFolder = Path(__file__).resolve().parent
    scriptPath = toolsFolder.parent

    tmpZipFile = scriptPath / "tmp.zip"

    if tmpZipFile.is_file():
        try:
            tmpZipFile.unlink()
        except OSError:
            pass

    if file_path:
        shutil.copy(file_path, tmpZipFile)
    else:
        # We need to make sure we're grabbing the most up-to-date `.zip`
        # Because raw.githubusercontent caches, we can use the explicit SHA
        sha = "main"
        if "raw.githubusercontent.com" in REPO:
            parts = str(REPO).split("raw.githubusercontent.com/")[-1].strip("/").split("/")
            if len(parts) >= 2:
                owner, repo = parts[0], parts[1]
                branch = parts[2] if len(parts) > 2 else "main"
                try:
                    api_url = "https://api.github.com/repos/%s/%s/commits/%s" % (owner, repo, branch)
                    req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req, context=unverified_ssl_context, timeout=10) as response:
                        if response.status == 200:
                            data = json.loads(response.read().decode("utf-8"))
                            sha = data.get("sha", "main")
                except Exception:
                    pass

        # Download the main source archive directly to ensure we get the latest uncached files
        FileUrl = "https://github.com/Alehaaaa/camstool/archive/%s.zip" % sha
        download(FileUrl, tmpZipFile)

    if not tmpZipFile.is_file():
        return cmds.error("Error trying to install.")

    zfobj = zipfile.ZipFile(tmpZipFile)
    fileList = zfobj.namelist()

    if not fileList:
        return cmds.error("Error trying to install.")

    # Remove old tool files
    if toolsFolder.is_dir():
        for filename in toolsFolder.iterdir():
            if filename.name != "_prefs":
                if filename.is_file():
                    try:
                        filename.unlink()
                    except OSError:
                        pass
                elif filename.is_dir():
                    try:
                        shutil.rmtree(filename)
                    except OSError:
                        pass

    for name in fileList:
        # GitHub archives look like: camstool-main/source/aleha_tools/__init__.py
        path_in_zip = Path(name)
        parts = path_in_zip.parts

        # Find where 'aleha_tools' starts in the path
        try:
            aleha_idx = parts.index("aleha_tools")
            rel_parts = parts[aleha_idx + 1 :]
        except ValueError:
            continue

        if not rel_parts:
            # This is the aleha_tools directory itself
            continue

        filename = toolsFolder.joinpath(*rel_parts)
        d = filename.parent

        if not d.exists():
            d.mkdir(parents=True)

        if name.endswith("/") or name.endswith(os.sep):
            continue

        uncompressed = zfobj.read(name)
        with open(filename, "wb") as output:
            output.write(uncompressed)

    zfobj.close()
    if tmpZipFile.is_file():
        tmpZipFile.unlink()

    if not file_path:
        add_shelf_button(tool, command)

    return True


def add_shelf_button(tool, command=None):
    from .util import find_shelf_button

    currentShelf = cmds.tabLayout(mel.eval("$nul=$gShelfTopLevel"), q=1, st=1)

    if not find_shelf_button(tool):
        toolsFolder = Path(__file__).resolve().parent
        icon_path = toolsFolder / "_icons" / (tool + ".svg")
        cmds.shelfButton(
            parent=currentShelf,
            i=str(icon_path),
            label=tool,
            c=command or "import aleha_tools." + tool + " as " + tool + ";" + tool + ".show()",
            annotation=tool.title() + " by Aleha",
        )

        QFlatConfirmDialog.information(
            None,
            "Success",
            title="Shelf button created",
            message="You can now click the %s button on the shelf to launch the tool." % tool.title(),
            closeButton=True,
        )


def _fetch_repo_file(filename):
    sha = "main"
    if "raw.githubusercontent.com" in REPO:
        parts = str(REPO).split("raw.githubusercontent.com/")[-1].strip("/").split("/")
        if len(parts) >= 2:
            owner, repo = parts[0], parts[1]
            branch = parts[2] if len(parts) > 2 else "main"
            api_url = "https://api.github.com/repos/%s/%s/commits/%s" % (owner, repo, branch)
            try:
                req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, context=unverified_ssl_context, timeout=10) as response:
                    if response.status == 200:
                        data = json.loads(response.read().decode("utf-8"))
                        if "sha" in data:
                            sha = data["sha"]
            except Exception:
                pass

    url = REPO.replace("/main/", "/%s/" % sha) + filename
    success, result = _download_text(url)

    if not success and sha != "main":
        success, result = _download_text(REPO + filename)

    return success, result


def _download_text(url):
    try:
        with urllib.request.urlopen(url, context=unverified_ssl_context, timeout=30) as response:
            if response.status == 200:
                text = response.read().decode("utf-8")
                if not text:
                    return False, NO_DATA_ERROR
                return True, text
            else:
                error_message = responses.get(response.status, "Unknown Error")
                return False, NO_SERVER_ERROR % (response.status, error_message)
    except urllib.error.URLError as e:
        reason = getattr(e, "reason", e)
        return False, "Network error: %s" % reason
    except TimeoutError:
        return False, "Connection timed out."
    except Exception as e:
        return False, "Unexpected error: %s" % e


def get_latest_version():
    success, result = _fetch_repo_file("version")
    if success:
        return True, result.strip()
    return False, result


def _get_changelog():
    success, result = _fetch_repo_file("release_notes.json")
    if success:
        try:
            return True, json.loads(result)
        except Exception:
            return False, "Error parsing changelog data."
    return False, result


# Check for Updates
class UpdateCheckWorker(QThread):
    finished = Signal(bool, object, object)  # success, latest_version, changelog

    def __init__(self, installed_version, force=False, delay=0, parent=None):
        super().__init__(parent)
        self.installed_version = installed_version
        self.force = force
        self.delay = delay

    def run(self):
        if self.delay > 0:
            self.msleep(self.delay)

        success, latest_version = get_latest_version()
        if not success:
            self.finished.emit(False, latest_version, None)
            return

        if not self.force:
            comp = compare_versions(latest_version, self.installed_version)
            if comp <= 0:
                self.finished.emit(True, None, None)
                return

        success, changelog = _get_changelog()
        if not success:
            self.finished.emit(False, changelog, None)
            return

        self.finished.emit(True, latest_version, changelog)


def _check_for_updates(ui, warning=True, force=False):
    # Prevent overlapping update checks
    if getattr(ui, "_update_worker", None) is not None and ui._update_worker.isRunning():
        if warning:
            util.make_inViewMessage("<b>Update Check</b><br>Currently checking for updates...", "info.svg")
        return

    installed_version = ui.VERSION

    def handle_result(success, latest_version, changelog):
        # Cleanup worker reference when finished
        if getattr(ui, "_update_worker", None) is not None:
            ui._update_worker.deleteLater()
            ui._update_worker = None

        if not success:
            if warning:
                util.make_inViewMessage(latest_version)  # latest_version contains error msg here
            return

        if latest_version is None:
            if warning:
                util.make_inViewMessage("<hl>" + installed_version + "</hl>\nYou are up-to-date.")
            return

        # Latest version found, process it
        is_blocked = bool(changelog.get("blocked", False))
        if is_blocked:
            if warning:
                util.make_inViewMessage(
                    "<hl>Updates are blocked</hl>\nPlease wait until the problem is solved.",
                    "warning.svg",
                )
            return

        last_release_notes = changelog.get("versions", {}).get(latest_version, [])
        formated_changelog = "<br/>".join(["- " + line.replace("<", "&lt;").replace(">", "&gt;") for line in last_release_notes])

        template = f"<title>Version {latest_version} available\n(using {installed_version})</title><text>These are the changes made:</text><separator/><text>{formated_changelog}</text>"

        result = QFlatTooltipConfirm.question(
            ui.menu_bar,
            title="Update available",
            template=template,
            icon=util.return_icon_path("update.svg"),
            buttons=[
                QFlatTooltipConfirm.CustomButton("Install", positive=True, icon=util.return_icon_path("install")),
                QFlatTooltipConfirm.CustomButton("Skip", positive=True, icon=util.return_icon_path("skip")),
                QFlatTooltipConfirm.No,
            ],
            highlight="Install",
        )

        if result and result.get("positive"):
            funcs.install_userSetup()

            if result.get("name") == "Install":
                from . import updater

                reload(updater)

                command = "import aleha_tools.cams as cams\ncams.show()"
                if not updater.install(ui.TITLE.lower(), command):
                    return

                def _post_update():
                    import aleha_tools
                    import aleha_tools.cams as cams
                    from importlib import reload

                    reload(aleha_tools)
                    reload(cams)
                    cams.show()

                    QFlatTooltipConfirm.information(
                        ui.menu_bar,
                        message="You have successfully updated the tool!<br><br>" + "These were the last changes:<br>" + formated_changelog,
                        title="Installed %s %s" % (ui.TITLE, latest_version.replace("\n", "").replace("\r", "")),
                        icon=util.return_icon_path("success.svg"),
                    )

                QTimer.singleShot(0, _post_update)
                ui.process_prefs(skip_update=False)

            elif result.get("name") == "Skip":
                ui.process_prefs(skip_update=True)

    # Delay startup check slightly to ensure UI is ready
    delay = 0 if warning or force else 1000

    ui._update_worker = UpdateCheckWorker(installed_version, force=force, delay=delay, parent=ui)
    ui._update_worker.finished.connect(handle_result)
    ui._update_worker.start()
