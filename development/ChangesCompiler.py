import difflib
import zipfile
import requests  # type: ignore
import re
import shutil
import os
from pathlib import Path


class CamsToolUpdater:
    def __init__(self, script_folder=None, cams_version=None):
        self.project_root = Path(os.path.realpath(__file__)).parents[1]
        self.versions_folder = self.project_root / "versions"

        self.script_folder = (
            Path(script_folder) if script_folder else self.project_root / "source" / "aleha_tools"
        )

        self.index = None

        if cams_version:
            self.cams_version = cams_version
        else:
            self.index = -1
            try:
                # Assuming aleha_tools is importable
                import aleha_tools  # type: ignore
                import importlib

                importlib.reload(aleha_tools)
                self.cams_version = aleha_tools.DATA["VERSION"]
            except Exception:
                self.cams_version = "0.0.0"

        # Use system temp directory
        self.tmpFolder = Path(os.environ.get("TEMP", os.environ.get("TMPDIR", "/tmp"))) / "cams_tmp"
        self.tmpScriptFolder = self.tmpFolder / "aleha_tools"
        self.changes_folder = self.tmpFolder / "changes"

        self.base_url = "https://generativelanguage.googleapis.com/v1beta/models"

        # Manually load .env file to identify GEMINI_API_KEY without dotenv module
        env_path = Path(os.path.realpath(__file__)).parent / ".env"
        if env_path.exists():
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, value = line.split("=", 1)
                        if key.strip() == "GEMINI_API_KEY":
                            value = value.strip()
                            # Handle quotes
                            if (value.startswith('"') and value.endswith('"')) or (
                                value.startswith("'") and value.endswith("'")
                            ):
                                value = value[1:-1]
                            os.environ["GEMINI_API_KEY"] = value
                            break

        self.api_key = os.environ.get("GEMINI_API_KEY")
        self.model = "gemini-2.5-flash"
        self.all_changes = {}

    def _gemini_payload(self, message):
        return {"contents": [{"parts": [{"text": message}]}]}

    def _gemini_parse(self, response):
        try:
            return response["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError):
            return None

    def complete_chat(self, message):
        if not self.api_key:
            return False, "API key not found"

        url = "%s/%s:generateContent" % (self.base_url, self.model)
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key,
        }
        payload = self._gemini_payload(message)

        try:
            response = requests.post(url, json=payload, headers=headers)
            response.raise_for_status()
            return True, self._gemini_parse(response.json())
        except Exception as e:
            return False, "API Request Failed: %s" % e

    def download_latest_version(self):
        if self.tmpFolder.exists():
            shutil.rmtree(self.tmpFolder)

        self.tmpFolder.mkdir(parents=True, exist_ok=True)
        self.changes_folder.mkdir(parents=True, exist_ok=True)

        if not self.versions_folder.exists():
            print("Versions folder not found: %s" % self.versions_folder)
            return

        try:
            from aleha_tools.util import compare_versions
            from functools import cmp_to_key

            def get_version_from_name(name):
                # Extra version from 'aleha_tools-0.2.5.zip'
                match = re.search(r"aleha_tools-(.*?)\.zip", name)
                return match.group(1) if match else "0.0.0"

            all_version_files = sorted(
                [f for f in self.versions_folder.iterdir() if f.suffix == ".zip"],
                key=cmp_to_key(
                    lambda x, y: compare_versions(
                        get_version_from_name(x.name), get_version_from_name(y.name)
                    )
                ),
            )
        except Exception:
            all_version_files = sorted([f for f in self.versions_folder.iterdir() if f.suffix == ".zip"])

        if not all_version_files:
            print("No version files found.")
            return

        latest_file = all_version_files[-1]

        # If latest matches current version and we are not forcing index, use the previous one
        if not self.index and self.cams_version in latest_file.name and len(all_version_files) > 1:
            latest_file = all_version_files[-2]

        tmpZipFile = self.tmpFolder / latest_file.name
        shutil.copy(latest_file, tmpZipFile)

        with zipfile.ZipFile(tmpZipFile) as zfobj:
            for name in zfobj.namelist():
                filename = self.tmpFolder / name
                if name.endswith("/"):  # It's a directory
                    filename.mkdir(parents=True, exist_ok=True)
                    continue

                filename.parent.mkdir(parents=True, exist_ok=True)
                with open(filename, "wb") as output:
                    output.write(zfobj.read(name))

        if tmpZipFile.is_file():
            tmpZipFile.unlink()

    def analyze_changes(self):
        if not self.tmpScriptFolder.exists():
            print("Tmp script folder not found: %s" % self.tmpScriptFolder)
            return

        for tmp_path in self.tmpScriptFolder.rglob("*.py"):
            relative_path = tmp_path.relative_to(self.tmpScriptFolder)
            current_path = self.script_folder / relative_path

            if not current_path.exists():
                continue

            with open(tmp_path, "r", encoding="utf-8", errors="replace") as source:
                with open(current_path, "r", encoding="utf-8", errors="replace") as endpoint:
                    diff = difflib.unified_diff(
                        source.readlines(),
                        endpoint.readlines(),
                        fromfile="%s (old)" % tmp_path.name,
                        tofile="%s (new)" % tmp_path.name,
                    )

                    changes = list(diff)
                    if changes:
                        self.all_changes[tmp_path.name] = changes
                        changes_file = self.changes_folder / relative_path.with_suffix(".txt")
                        changes_file.parent.mkdir(parents=True, exist_ok=True)
                        with open(changes_file, "w", encoding="utf-8") as changes_log:
                            for line in changes:
                                changes_log.write(line)

    def generate_changelog(self):
        if not self.all_changes:
            return []

        formatted_changes = "\n".join(
            ["\n" + file + "\n" + "".join(changes) for file, changes in self.all_changes.items()]
        )

        max_length = 10000
        if len(formatted_changes) > max_length:
            formatted_changes = formatted_changes[:max_length] + "\n\n... (truncated)"

        prompt = (
            "Make a simple changelog up to 4 lines of 30 characters each. "
            "Add an 'And more...' if there are too many. Format it like a Python list, "
            "for example: ['change.', 'change.', 'change.', 'change.']:\n\n"
            "%s" % formatted_changes
        )

        gpt_log_file = self.tmpFolder / "gpt_log.txt"
        if gpt_log_file.is_file():
            gpt_log_file.unlink()

        with open(gpt_log_file, "w", encoding="utf-8") as gpt_log:
            gpt_log.write(prompt + "\n\n\n\n")

        success, response = self.complete_chat(prompt)

        if not success:
            return [response]

        with open(gpt_log_file, "a", encoding="utf-8") as gpt_log:
            gpt_log.write(response)

        try:
            # Dangerous but keeping previous behavior
            changelog = eval(response)
        except Exception:
            changelog = response

        if isinstance(changelog, str):
            changelog = re.findall(r"'(.*?)'", changelog)

        try:
            for index, change in enumerate(changelog):
                change = change.strip()
                if change.endswith(","):
                    change = change[:-1]
                if not change.endswith("."):
                    change += "."
                changelog[index] = change
        except Exception as e:
            print("Error formatting changelog: %s" % e)

        return changelog

    def run(self):
        self.download_latest_version()
        self.analyze_changes()
        changelog = self.generate_changelog()
        return changelog


if __name__ == "__main__":
    updater = CamsToolUpdater()
    changelog = updater.run()
    if changelog:
        print("\n".join(changelog))
