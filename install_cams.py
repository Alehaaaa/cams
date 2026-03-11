import ssl
import json
import shutil
import zipfile
import urllib.request
import urllib.error
import maya.cmds as cmds
import maya.mel as mel
from pathlib import Path

# --- Constants ---
REPO_OWNER = "Alehaaaa"
REPO_NAME = "camstool"
TOOL_NAME = "cams"
PACKAGE_NAME = "aleha_tools"

# SSL Context for unverified connections (helps with some corporate networks/proxies)
unverified_ssl_context = ssl.create_default_context()
unverified_ssl_context.check_hostname = False
unverified_ssl_context.verify_mode = ssl.CERT_NONE


def download(url, save_path):
    """Downloads a file from a URL with a Maya progress bar."""
    try:
        response = urllib.request.urlopen(url, context=unverified_ssl_context, timeout=60)
    except Exception as e:
        cmds.error(f"Failed to connect to {url}: {e}")
        return False

    if response is None:
        cmds.error("No response from server.")
        return False

    total_size = response.getheader("Content-Length")
    total_size = int(total_size) if total_size else 0
    block_size = 8192

    gMainProgressBar = None
    try:
        gMainProgressBar = mel.eval("$tmp = $gMainProgressBar")
    except Exception:
        pass

    if gMainProgressBar and total_size > 0:
        cmds.progressBar(
            gMainProgressBar,
            edit=True,
            beginProgress=True,
            isInterruptable=False,
            status=f"Downloading {TOOL_NAME.title()}...",
            maxValue=total_size,
        )

    downloaded = 0
    try:
        with open(save_path, "wb") as output:
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


def get_latest_sha():
    """Fetches the latest commit SHA from GitHub to bypass caching."""
    api_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/commits/main"
    try:
        req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, context=unverified_ssl_context, timeout=10) as response:
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                return data.get("sha", "main")
    except Exception:
        pass
    return "main"


def find_shelf_button(label):
    """Finds a shelf button by its label."""
    try:
        gShelfTopLevel = mel.eval("$tmp = $gShelfTopLevel")
        shelves = cmds.tabLayout(gShelfTopLevel, query=True, childArray=True) or []
        for shelf in shelves:
            buttons = cmds.shelfLayout(shelf, query=True, childArray=True) or []
            for btn in buttons:
                if cmds.shelfButton(btn, query=True, label=True) == label:
                    return btn
    except Exception:
        pass
    return None


def add_shelf_button():
    """Adds a shelf button for the tool if it doesn't already exist."""
    current_shelf = cmds.tabLayout(mel.eval("$nul=$gShelfTopLevel"), q=1, st=1)
    if not current_shelf:
        return

    if not find_shelf_button(TOOL_NAME):
        # Determine icon path
        scripts_dir = Path(cmds.internalVar(userScriptDir=True))
        icon_path = scripts_dir / PACKAGE_NAME / "_icons" / f"{TOOL_NAME}.svg"

        cmds.shelfButton(
            parent=current_shelf,
            image=str(icon_path),
            label=TOOL_NAME,
            command=f"import {PACKAGE_NAME}.{TOOL_NAME} as {TOOL_NAME}; {TOOL_NAME}.show()",
            annotation=f"{TOOL_NAME.title()} by Aleha",
            imageOverlayLabel=TOOL_NAME[:4] if len(TOOL_NAME) > 4 else TOOL_NAME,
        )
        print(f"Shelf button for {TOOL_NAME} created on '{current_shelf}'.")


def install():
    """Main installation logic."""
    # 0. Initial Prompt
    if not cmds.about(batch=True):
        confirm = cmds.confirmDialog(
            title=f"Install {TOOL_NAME.title()}",
            message=f"Do you want to install {TOOL_NAME.title()} by Aleha?",
            button=["Install", "Cancel"],
            defaultButton="Install",
            cancelButton="Cancel",
            dismissString="Cancel",
        )
        if confirm != "Install":
            print("Installation cancelled by user.")
            return False

    print(f"--- Installing {TOOL_NAME.title()} ---")

    # Define paths
    scripts_dir = Path(cmds.internalVar(userScriptDir=True))
    tools_folder = scripts_dir / PACKAGE_NAME
    tmp_zip = scripts_dir / "cams_install_tmp.zip"

    # 1. Download
    sha = get_latest_sha()
    download_url = f"https://github.com/Alehaaaa/camstool/archive/{sha}.zip"

    if tmp_zip.exists():
        tmp_zip.unlink()

    if not download(download_url, tmp_zip):
        return False

    # 2. Prepare target folder
    if not tools_folder.exists():
        tools_folder.mkdir(parents=True)
    else:
        # Clean up existing files except _prefs
        print(f"Cleaning up {tools_folder}...")
        for item in tools_folder.iterdir():
            if item.name == "_prefs":
                continue
            try:
                if item.is_file() or item.is_symlink():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
            except Exception as e:
                print(f"Warning: Could not remove {item}: {e}")

    # 3. Extract
    print("Extracting files...")
    try:
        with zipfile.ZipFile(tmp_zip, "r") as zip_ref:
            for member in zip_ref.namelist():
                # zip structure: camstool-<sha>/source/aleha_tools/...
                parts = Path(member).parts
                try:
                    # Find where 'aleha_tools' starts in the path
                    idx = parts.index(PACKAGE_NAME)
                    # Get the path relative to 'aleha_tools'
                    rel_parts = parts[idx + 1 :]

                    if not rel_parts:
                        continue  # Target the package dir itself

                    target_path = tools_folder.joinpath(*rel_parts)

                    if member.endswith("/") or member.endswith("\\"):
                        if not target_path.exists():
                            target_path.mkdir(parents=True)
                        continue

                    if not target_path.parent.exists():
                        target_path.parent.mkdir(parents=True)

                    with open(target_path, "wb") as f:
                        f.write(zip_ref.read(member))

                except ValueError:
                    # 'aleha_tools' not in this path, skip it
                    continue
    except Exception as e:
        cmds.error(f"Extraction failed: {e}")
        return False
    finally:
        if tmp_zip.exists():
            tmp_zip.unlink()

    # 4. Finalize
    add_shelf_button()

    # Load the tool
    cmds.evalDeferred(f"import {PACKAGE_NAME}.{TOOL_NAME} as {TOOL_NAME}; {TOOL_NAME}.show()", lowestPriority=True)

    # Success Message
    msg = f"{TOOL_NAME.title()} has been installed successfully!"
    print(f"--- {TOOL_NAME.title()} Installation Complete ---")

    # Try to use QFlatConfirmDialog if available
    try:
        import importlib
        import sys

        # Ensure scripts_dir is in sys.path
        if str(scripts_dir) not in sys.path:
            sys.path.append(str(scripts_dir))

        # Try to import package and refresh if needed
        if PACKAGE_NAME in sys.modules:
            importlib.reload(sys.modules[PACKAGE_NAME])
        else:
            importlib.import_module(PACKAGE_NAME)

        from aleha_tools.base_widgets import QFlatConfirmDialog

        icon_path = tools_folder / "_icons" / f"{TOOL_NAME}.svg"

        QFlatConfirmDialog.information(
            None, TOOL_NAME.title(), title="Installation Successful", message=msg, icon=str(icon_path), closeButton=True
        )
    except Exception as e:
        print(f"Failed to show custom dialog: {e}")
        cmds.confirmDialog(title="Success", message=msg, button=["OK"])

    return True


def onMayaDroppedPythonFile(filePath, *args, **kwargs):
    """
    Entry point for drag and drop in Maya.
    Maya passes the path to the dropped file as the first argument.
    """
    import sys
    import os
    import importlib

    # Get module name from filename
    module_name = os.path.splitext(os.path.basename(filePath))[0]
    if module_name in sys.modules:
        try:
            importlib.reload(sys.modules[module_name])
        except Exception as e:
            print(f"Warning: Could not reload installer module '{module_name}': {e}")

    install()


if __name__ == "__main__":
    # If run directly as a script
    install()
