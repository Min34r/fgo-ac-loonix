"""
Translation installer module for Fate/Grand Order Arcade.
Downloads and extracts the English/Chinese translation payload into App/zh.
"""

import hashlib
import json
import os
import urllib.request
import zipfile
from pathlib import Path
from PyQt6.QtCore import QThread, pyqtSignal

try:
    from launcher.core.config import FGOA_ROOT
except ImportError:
    from .config import FGOA_ROOT

RELEASE_URL = "https://github.com/githubuser420x/FGOAC-scooby/releases/download/v1.1.2/FGOAC-scooby-v1.1.2.zip"
EXPECTED_SHA256 = "76dab15be143f600f34823df0988228a409c1b821d70d8a26343ef18e23ed3a3"


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
            data = bytearray(f.read())
        target_pattern = b"\x48\x8d\x45\x40\x48\x3b\xf8\x75\xd7"
        patched_pattern = b"\x48\x8d\x45\x20\x48\x3b\xf8\x75\xd7"
        pos = data.find(target_pattern)
        if pos != -1:
            data[pos : pos + len(patched_pattern)] = patched_pattern
            with open(dll_path, "wb") as f:
                f.write(data)
            return True
        return data.find(patched_pattern) != -1
    except Exception:
        return False


def ensure_fgozh_patched() -> bool:
    """Ensure all discovered fgozh.dll instances are patched for Wine."""
    patched_any = False
    candidates = [
        os.path.join(FGOA_ROOT, "App", "zh", "fgozh.dll"),
        os.path.join(FGOA_ROOT, "App", "fgozh.dll"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            if patch_fgozh_for_wine(c):
                patched_any = True
    return patched_any


def is_translation_installed() -> bool:
    """Check if the translation hook and text files are present in App/zh."""
    zh_dir = os.path.join(FGOA_ROOT, "App", "zh")
    dll_path = os.path.join(zh_dir, "fgozh.dll")
    text_json = os.path.join(zh_dir, "executable-text.json")
    return os.path.isfile(dll_path) and os.path.isfile(text_json)


class TranslationInstallerWorker(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def run(self):
        try:
            self.progress.emit("[TRANSLATION] Preparing download environment...")
            cache_dir = os.path.join(FGOA_ROOT, "scratch", "downloads")
            os.makedirs(cache_dir, exist_ok=True)
            zip_path = os.path.join(cache_dir, "FGOAC-scooby-v1.1.2.zip")

            need_download = True
            if os.path.isfile(zip_path):
                self.progress.emit("[TRANSLATION] Verifying existing cached zip checksum...")
                hasher = hashlib.sha256()
                with open(zip_path, "rb") as f:
                    for chunk in iter(lambda: f.read(65536), b""):
                        hasher.update(chunk)
                if hasher.hexdigest() == EXPECTED_SHA256:
                    self.progress.emit("[TRANSLATION] Cached release zip verified valid.")
                    need_download = False
                else:
                    self.progress.emit("[TRANSLATION] Cached zip invalid, downloading full release...")

            if need_download:
                self.progress.emit(f"[TRANSLATION] Connecting to GitHub release...")
                req = urllib.request.Request(
                    RELEASE_URL,
                    headers={"User-Agent": "FGOA-Linux-Launcher"}
                )
                with urllib.request.urlopen(req) as resp, open(zip_path, "wb") as out:
                    total_size = int(resp.headers.get("Content-Length", 0))
                    downloaded = 0
                    last_reported_pct = -1
                    while True:
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        out.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            pct = int((downloaded / total_size) * 100)
                            if pct % 10 == 0 and pct != last_reported_pct:
                                last_reported_pct = pct
                                mb_down = downloaded // 1024 // 1024
                                mb_tot = total_size // 1024 // 1024
                                self.progress.emit(f"[TRANSLATION] Downloading... {pct}% ({mb_down} MB / {mb_tot} MB)")

                self.progress.emit("[TRANSLATION] Verifying SHA256 checksum...")
                hasher = hashlib.sha256()
                with open(zip_path, "rb") as f:
                    for chunk in iter(lambda: f.read(65536), b""):
                        hasher.update(chunk)
                if hasher.hexdigest() != EXPECTED_SHA256:
                    self.finished.emit(False, "Downloaded archive failed SHA256 integrity check.")
                    return

            self.progress.emit("[TRANSLATION] Extracting translation payload into App/zh...")
            app_zh = os.path.join(FGOA_ROOT, "App", "zh")
            os.makedirs(app_zh, exist_ok=True)

            with zipfile.ZipFile(zip_path, "r") as z:
                for member in z.namelist():
                    if member.startswith("payload/App/zh/") and not member.endswith("/"):
                        rel_path = member[len("payload/App/zh/"):]
                        target_file = os.path.join(app_zh, rel_path)
                        os.makedirs(os.path.dirname(target_file), exist_ok=True)
                        with z.open(member) as src, open(target_file, "wb") as dst:
                            dst.write(src.read())

                    # Also summon candidates if included in payload
                    if member == "payload/Server/artemis/titles/fgo/data/summon_candidates.json":
                        cand_target = os.path.join(
                            FGOA_ROOT, "Server", "artemis", "titles", "fgo", "data", "summon_candidates.json"
                        )
                        os.makedirs(os.path.dirname(cand_target), exist_ok=True)
                        with z.open(member) as src, open(cand_target, "wb") as dst:
                            dst.write(src.read())

            # Apply Wine compatibility patch to fgozh.dll
            target_dll = os.path.join(app_zh, "fgozh.dll")
            if os.path.isfile(target_dll):
                self.progress.emit("[TRANSLATION] Applying Wine compatibility patch to fgozh.dll...")
                patch_fgozh_for_wine(target_dll)

            # Enable translation in fgo-launcher.json if present
            cfg_path = os.path.join(FGOA_ROOT, "App", "fgo-launcher.json")
            if os.path.isfile(cfg_path):
                try:
                    with open(cfg_path, "r") as f:
                        cfg_data = json.load(f)
                    cfg_data["chineseEnabled"] = True
                    with open(cfg_path, "w") as f:
                        json.dump(cfg_data, f, indent=2)
                except Exception:
                    pass

            self.progress.emit("[TRANSLATION] English translation successfully installed into App/zh!")
            self.finished.emit(True, "English translation files successfully downloaded, patched for Wine, and installed!")
        except Exception as e:
            self.finished.emit(False, str(e))
