import os
import ssl
import json
import shutil
import zipfile
import urllib.request
import urllib.error
import maya.cmds as cmds
import maya.mel as mel

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
        cmds.error("Failed to connect to {}: {}".format(url, e))
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
            status="Downloading {}...".format(TOOL_NAME.title()),
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
    api_url = "https://api.github.com/repos/{0}/{1}/commits/main".format(REPO_OWNER, REPO_NAME)
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
        scripts_dir = cmds.internalVar(userScriptDir=True)
        icon_path = os.path.join(scripts_dir, PACKAGE_NAME, "_icons", "{}.svg".format(TOOL_NAME))

        cmds.shelfButton(
            parent=current_shelf,
            image=str(icon_path),
            label=TOOL_NAME,
            command="import {0}.{1} as {1}; {1}.show()".format(PACKAGE_NAME, TOOL_NAME),
            annotation="{0} by Aleha".format(TOOL_NAME.title()),
            imageOverlayLabel=TOOL_NAME[:4] if len(TOOL_NAME) > 4 else TOOL_NAME,
        )
        print("Shelf button for {0} created on '{1}'.".format(TOOL_NAME, current_shelf))


def install():
    """Main installation logic."""
    # 0. Initial Prompt
    if not cmds.about(batch=True):
        confirm = cmds.confirmDialog(
            title="Install {0}".format(TOOL_NAME.title()),
            message="Do you want to install {0} by Aleha?".format(TOOL_NAME.title()),
            button=["Install", "Cancel"],
            defaultButton="Install",
            cancelButton="Cancel",
            dismissString="Cancel",
        )
        if confirm != "Install":
            print("Installation cancelled by user.")
            return False

    print("--- Installing {0} ---".format(TOOL_NAME.title()))

    # Define paths
    scripts_dir = cmds.internalVar(userScriptDir=True)
    tools_folder = os.path.join(scripts_dir, PACKAGE_NAME)
    tmp_zip = os.path.join(scripts_dir, "cams_install_tmp.zip")

    # 1. Download
    sha = get_latest_sha()
    download_url = "https://github.com/Alehaaaa/camstool/archive/{0}.zip".format(sha)

    if os.path.exists(tmp_zip):
        os.remove(tmp_zip)

    if not download(download_url, tmp_zip):
        return False

    # 2. Prepare target folder
    if not os.path.exists(tools_folder):
        os.makedirs(tools_folder)
    else:
        # Clean up existing files except _prefs
        print("Cleaning up {0}...".format(tools_folder))
        for item in os.listdir(tools_folder):
            if item == "_prefs":
                continue
            item_path = os.path.join(tools_folder, item)
            try:
                if os.path.isfile(item_path) or os.path.islink(item_path):
                    os.remove(item_path)
                elif os.path.isdir(item_path):
                    shutil.rmtree(item_path)
            except Exception as e:
                print("Warning: Could not remove {0}: {1}".format(item_path, e))

    # 3. Extract
    print("Extracting files...")
    try:
        with zipfile.ZipFile(tmp_zip, "r") as zip_ref:
            for member in zip_ref.namelist():
                # zip structure: camstool-<sha>/source/aleha_tools/...
                parts = member.replace("\\", "/").split("/")
                try:
                    # Find where 'aleha_tools' starts in the path
                    idx = parts.index(PACKAGE_NAME)
                    # Get the path relative to 'aleha_tools'
                    rel_parts = parts[idx + 1 :]

                    if not rel_parts:
                        continue  # Target the package dir itself

                    target_path = os.path.join(tools_folder, *rel_parts)

                    if member.endswith("/") or member.endswith("\\"):
                        if not os.path.exists(target_path):
                            os.makedirs(target_path)
                        continue

                    target_dir = os.path.dirname(target_path)
                    if not os.path.exists(target_dir):
                        os.makedirs(target_dir)

                    with open(target_path, "wb") as f:
                        f.write(zip_ref.read(member))

                except ValueError:
                    # 'aleha_tools' not in this path, skip it
                    continue
    except Exception as e:
        cmds.error("Extraction failed: {0}".format(e))
        return False
    finally:
        if os.path.exists(tmp_zip):
            os.remove(tmp_zip)

    # 4. Finalize
    add_shelf_button()

    # Load the tool
    cmds.evalDeferred("import {0}.{1} as {1}; {1}.show()".format(PACKAGE_NAME, TOOL_NAME), lowestPriority=True)

    # Success Message
    msg = "{0} has been installed successfully!".format(TOOL_NAME.title())
    print("--- {0} Installation Complete ---".format(TOOL_NAME.title()))

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

        icon_path = os.path.join(tools_folder, "_icons", "{0}.svg".format(TOOL_NAME))

        QFlatConfirmDialog.information(
            None, TOOL_NAME.title(), title="Installation Successful", message=msg, icon=str(icon_path), closeButton=True
        )
    except Exception as e:
        print("Failed to show custom dialog: {0}".format(e))
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
            print("Warning: Could not reload installer module '{}': {}".format(module_name, e))

    install()


if __name__ == "__main__":
    # If run directly as a script
    install()
