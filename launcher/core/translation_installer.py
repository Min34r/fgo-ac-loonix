"""
Translation installer module for Fate/Grand Order Arcade.
Downloads and extracts the English/Chinese translation payload into App/zh.
"""

import hashlib
import json
import os
import urllib.request
import zipfile
from PyQt6.QtCore import QThread, pyqtSignal
from launcher.core.config import APP_DIR, FGOA_ROOT

RELEASE_URL = "https://github.com/githubuser420x/FGOAC-scooby/releases/download/v1.1.2/FGOAC-scooby-v1.1.2.zip"
EXPECTED_SHA256 = "76dab15be143f600f34823df0988228a409c1b821d70d8a26343ef18e23ed3a3"


def _verify_sha256(path: str) -> bool:
    if not os.path.isfile(path):
        return False
    with open(path, "rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest() == EXPECTED_SHA256


def patch_fgozh_for_wine(dll_path: str) -> bool:
    """
    Patch fgozh.dll for Wine compatibility.
    Wine's ntdll.dll does not implement NtQueryInformationByName, causing
    MinHook's MH_CreateHookApi to return MH_ERROR_FUNCTION_NOT_FOUND and
    making fgozh.dll DllMain fail inside ago.exe.
    Patching the loop limit from 0x40 to 0x20 at offset 0x14fb3 skips
    NtQueryInformationByName while hooking the 4 supported file APIs:
    (NtCreateFile, NtOpenFile, NtQueryAttributesFile, NtQueryFullAttributesFile).
    """
    if not os.path.isfile(dll_path):
        return False
    try:
        with open(dll_path, "rb") as f:
            data = f.read()
        target = b"\x48\x8d\x45\x40\x48\x3b\xf8\x75\xd7"
        patched = b"\x48\x8d\x45\x20\x48\x3b\xf8\x75\xd7"
        if target in data:
            with open(dll_path, "wb") as f:
                f.write(data.replace(target, patched, 1))
            return True
        return patched in data
    except Exception:
        return False


def ensure_fgozh_patched() -> bool:
    """Ensure all discovered fgozh.dll instances are patched for Wine."""
    candidates = (
        os.path.join(APP_DIR, "zh", "fgozh.dll"),
        os.path.join(APP_DIR, "Localization", "zh", "fgozh.dll"),
        os.path.join(APP_DIR, "fgozh.dll"),
    )
    return any([patch_fgozh_for_wine(c) for c in candidates if os.path.isfile(c)])


def is_translation_installed() -> bool:
    """Check if the translation hook and text files are present in App/zh or App/Localization."""
    zh_dir = os.path.join(APP_DIR, "zh")
    loc_dir = os.path.join(APP_DIR, "Localization")
    return (
        os.path.isfile(os.path.join(zh_dir, "fgozh.dll"))
        and os.path.isfile(os.path.join(zh_dir, "executable-text.json"))
    ) or (os.path.isfile(os.path.join(APP_DIR, "fgozh.dll")) and os.path.isdir(loc_dir))


class TranslationInstallerWorker(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def run(self):
        try:
            self.progress.emit("[TRANSLATION] Preparing download environment...")
            cache_dir = os.path.join(FGOA_ROOT, "scratch", "downloads")
            os.makedirs(cache_dir, exist_ok=True)
            zip_path = os.path.join(cache_dir, "FGOAC-scooby-v1.1.2.zip")

            if os.path.isfile(zip_path) and _verify_sha256(zip_path):
                self.progress.emit("[TRANSLATION] Cached release zip verified valid.")
            else:
                self.progress.emit("[TRANSLATION] Connecting to GitHub release...")
                req = urllib.request.Request(RELEASE_URL, headers={"User-Agent": "FGOA-Linux-Launcher"})
                with urllib.request.urlopen(req) as resp, open(zip_path, "wb") as out:
                    total_size = int(resp.headers.get("Content-Length", 0))
                    downloaded = 0
                    last_pct = -1
                    while chunk := resp.read(65536):
                        out.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            pct = int((downloaded / total_size) * 100)
                            if pct % 10 == 0 and pct != last_pct:
                                last_pct = pct
                                self.progress.emit(
                                    f"[TRANSLATION] Downloading... {pct}% ({downloaded >> 20} MB / {total_size >> 20} MB)"
                                )

                self.progress.emit("[TRANSLATION] Verifying SHA256 checksum...")
                if not _verify_sha256(zip_path):
                    self.finished.emit(False, "Downloaded archive failed SHA256 integrity check.")
                    return

            self.progress.emit("[TRANSLATION] Extracting translation payload into App/zh...")
            app_zh = os.path.join(APP_DIR, "zh")
            os.makedirs(app_zh, exist_ok=True)

            with zipfile.ZipFile(zip_path, "r") as z:
                for member in z.namelist():
                    if member.startswith("payload/App/zh/") and not member.endswith("/"):
                        target = os.path.join(app_zh, member.removeprefix("payload/App/zh/"))
                    elif member == "payload/Server/artemis/titles/fgo/data/summon_candidates.json":
                        target = os.path.join(FGOA_ROOT, "Server", "artemis", "titles", "fgo", "data", "summon_candidates.json")
                    else:
                        continue
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    with z.open(member) as src, open(target, "wb") as dst:
                        dst.write(src.read())

            # Apply Wine compatibility patch to fgozh.dll
            target_dll = os.path.join(app_zh, "fgozh.dll")
            if os.path.isfile(target_dll):
                self.progress.emit("[TRANSLATION] Applying Wine compatibility patch to fgozh.dll...")
                patch_fgozh_for_wine(target_dll)

            # Enable translation in fgo-launcher.json if present
            cfg_path = os.path.join(APP_DIR, "fgo-launcher.json")
            if os.path.isfile(cfg_path):
                try:
                    with open(cfg_path, "r", encoding="utf-8") as f:
                        cfg_data = json.load(f)
                    cfg_data["chineseEnabled"] = True
                    with open(cfg_path, "w", encoding="utf-8") as f:
                        json.dump(cfg_data, f, indent=2)
                except Exception:
                    pass

            self.progress.emit("[TRANSLATION] English translation successfully installed into App/zh!")
            self.finished.emit(True, "English translation files successfully downloaded, patched for Wine, and installed!")
        except Exception as e:
            self.finished.emit(False, str(e))
