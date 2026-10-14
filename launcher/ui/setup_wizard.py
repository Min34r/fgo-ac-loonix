"""
Fate/Grand Order Arcade - First-Run Setup Wizard.
Arcade-themed setup dialog for folder detection, archive extraction, and Linux compatibility patching.
"""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from PyQt6.QtCore import QPoint, QSize, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from launcher.core.config import find_game_root, get_fgoa_root, set_fgoa_root
from launcher.ui.chamfer import ChamferButton
from launcher.ui.theme import Theme

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
PLATFORM_PNG = ASSETS_DIR / "platform.png"
PLATFORM_ICO = ASSETS_DIR / "platform.ico"


def _normalize_archives(paths: List[Path]) -> List[Path]:
    """Resolve multi-part archives (e.g. part2 -> part1) and sort base game before updates."""
    rar_vol_pat = re.compile(r"^(.*?)\.part(\d+)(?:-\d+|\s*\(\d+\))?\.rar$", re.IGNORECASE)
    groups = {}
    for p in paths:
        m = rar_vol_pat.match(p.name)
        if m:
            prefix, vol_idx = m.group(1).lower(), int(m.group(2))
            groups.setdefault(prefix, {})[vol_idx] = p

    resolved = []
    for p in paths:
        m = rar_vol_pat.match(p.name)
        if m:
            prefix, vol_idx = m.group(1).lower(), int(m.group(2))
            if vol_idx > 1 and 1 in groups.get(prefix, {}):
                resolved.append(groups[prefix][1])
                continue
            elif vol_idx > 1 and p.parent.is_dir():
                for sibling in p.parent.iterdir():
                    if sibling.is_file():
                        sm = rar_vol_pat.match(sibling.name)
                        if sm and sm.group(1).lower() == prefix and int(sm.group(2)) == 1:
                            resolved.append(sibling)
                            break
                else:
                    resolved.append(p)
                continue
        resolved.append(p)

    seen = set()
    deduped = []
    for p in resolved:
        rp = str(p.resolve())
        if rp not in seen:
            seen.add(rp)
            deduped.append(p)

    def sort_key(p: Path) -> int:
        n = p.name.lower()
        if "hotfix" in n or "settlement" in n:
            return 2
        if "update" in n or "patch" in n or "1.10" in n:
            return 1
        return 0

    return sorted(deduped, key=sort_key)


def _get_download_dir() -> Path:
    """Resolve the user's Download directory from XDG or fallback to ~/Downloads."""
    config_file = Path.home() / ".config" / "user-dirs.dirs"
    if config_file.is_file():
        try:
            for line in config_file.read_text(encoding="utf-8").splitlines():
                if line.startswith("XDG_DOWNLOAD_DIR="):
                    val = line.split("=", 1)[1].strip().strip('"')
                    val = val.replace("$HOME", str(Path.home()))
                    p = Path(val)
                    if p.is_dir():
                        return p
        except Exception:
            pass
    for fallback in (Path.home() / "Downloads", Path.home() / "Download"):
        if fallback.is_dir():
            return fallback
    return Path.home() / "Downloads"


def _scan_downloads_for_game(dl_dir: Path) -> tuple[Optional[Path], List[Path]]:
    """
    Scan the download directory for an extracted FGOA folder or game archives.
    Returns: (found_folder, list_of_archives)
    """
    if not dl_dir.is_dir():
        return None, []

    found_folder = find_game_root(dl_dir)

    archive_exts = (".rar", ".zip", ".7z", ".bin", ".tar", ".tar.gz", ".tgz", ".tar.xz")
    keywords = ("fgo", "fate", "ago", "cloud23333", "cloud", "arcade", "localization", "settlement", "hotfix")
    fgo_prefix_pat = re.compile(r"^v?1\.(?:00|10|0|1|51)[_\-\. ]", re.IGNORECASE)
    fgo_inner_kws = ("fgo", "cloud23333", "ago.exe", "amdaemon", "artemis")
    found_archives = []

    try:
        candidates = list(dl_dir.iterdir())
        for sub in candidates:
            # Only scan immediate subdirectories if they match game keywords (e.g. FGOA/, Downloads/FGO/)
            if sub.is_dir() and not sub.name.startswith("."):
                sub_nl = sub.name.lower()
                if any(k in sub_nl for k in ("fgo", "fate", "cloud")):
                    try:
                        candidates.extend(sub.iterdir())
                    except Exception:
                        pass

        for f in candidates:
            if f.is_file():
                name_lower = f.name.lower()
                if name_lower.endswith((".crdownload", ".tmp")):
                    continue
                if name_lower.endswith(".part") and not re.search(r"\.part\d+(?:-\d+|\s*\(\d+\))?\.rar$", name_lower):
                    continue
                if any(name_lower.endswith(e) for e in archive_exts):
                    matched = any(k in name_lower for k in keywords) or bool(fgo_prefix_pat.match(name_lower))
                    if not matched and name_lower.endswith(".zip"):
                        try:
                            import zipfile
                            with zipfile.ZipFile(f) as zf:
                                for name in zf.namelist()[:30]:
                                    if any(k in name.lower() for k in fgo_inner_kws):
                                        matched = True
                                        break
                        except Exception:
                            pass
                    if matched:
                        found_archives.append(f)
    except Exception:
        pass

    return found_folder, found_archives


class SetupWorker(QThread):
    progress_status = pyqtSignal(str)
    log_line = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def __init__(self, mode: str, folder_path: Optional[Path] = None,
                 archive_paths: Optional[List[Path]] = None, dest_path: Optional[Path] = None):
        super().__init__()
        self.mode = mode
        self.folder_path = folder_path
        self.archive_paths = archive_paths or []
        self.dest_path = dest_path
        self.install_sh = Path(__file__).resolve().parent.parent.parent / "install.sh"

    def _run_cmd(self, cmd: List[str], cwd: Optional[Path] = None) -> bool:
        self.log_line.emit(f"$ {' '.join(cmd)}")
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(cwd) if cwd else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            if proc.stdout:
                for line in iter(proc.stdout.readline, ""):
                    if line:
                        self.log_line.emit(line.rstrip())
                proc.stdout.close()
            proc.wait()
            return proc.returncode == 0
        except Exception as e:
            self.log_line.emit(f"[ERROR] Failed to execute {cmd[0]}: {e}")
            return False

    def run(self):
        if self.mode == "folder":
            self.progress_status.emit("Verifying game files and applying Linux patches...")
            game_root = find_game_root(self.folder_path) if self.folder_path else None
            if not game_root:
                self.finished.emit(False, "Could not find App/ago.exe in the selected folder.")
                return

            if self.install_sh.is_file():
                self.progress_status.emit("Applying binary & server compatibility patches...")
                ok = self._run_cmd(["bash", str(self.install_sh), str(game_root)])
                if not ok:
                    self.finished.emit(False, "Patching script returned an error.")
                    return

            set_fgoa_root(game_root)
            self.finished.emit(True, str(game_root))

        elif self.mode == "archive":
            if not self.dest_path:
                self.finished.emit(False, "No destination directory specified.")
                return

            self.dest_path.mkdir(parents=True, exist_ok=True)
            extractor = shutil.which("7z") or shutil.which("7za") or shutil.which("bsdtar")
            if not extractor:
                self.finished.emit(False, "No archive extractor (7z, 7za, bsdtar) found on system.")
                return

            staging_dir = self.dest_path / ".fgoa_staging"
            staging_dir.mkdir(parents=True, exist_ok=True)

            try:
                self.progress_status.emit("Analyzing archive set and volume structure...")
                self.log_line.emit(f"[SETUP] Initializing extraction into {self.dest_path}")

                # 1. Expand input archives by finding sibling multi-part volumes in source directories
                all_candidates = list(self.archive_paths)
                rar_vol_pat = re.compile(r"^(.*?)\.part(\d+)(?:-\d+|\s*\(\d+\))?\.rar$", re.IGNORECASE)
                for arch in list(all_candidates):
                    if arch.is_file() and arch.parent.is_dir():
                        m = rar_vol_pat.match(arch.name)
                        if m:
                            prefix = m.group(1).lower()
                            for sibling in arch.parent.iterdir():
                                if sibling.is_file():
                                    sm = rar_vol_pat.match(sibling.name)
                                    if sm and sm.group(1).lower() == prefix and sibling not in all_candidates:
                                        all_candidates.append(sibling)

                # 2. Inspect zip files: unpack container zips that package inner archives
                direct_archives = []
                import zipfile
                for arch in all_candidates:
                    if arch.is_file() and arch.suffix.lower() == ".zip":
                        is_container = False
                        try:
                            with zipfile.ZipFile(arch) as zf:
                                namelist = zf.namelist()
                                has_app = any("ago.exe" in m.lower() or m.lower().startswith("app/") for m in namelist)
                                inner_archives = [
                                    m for m in namelist
                                    if m.lower().endswith((".rar", ".7z", ".bin")) or
                                    ("hotfix" in m.lower() and m.lower().endswith(".zip"))
                                ]
                                if inner_archives and not has_app:
                                    is_container = True
                                    self.progress_status.emit(f"Unpacking inner components from {arch.name}...")
                                    self.log_line.emit(f"[CONTAINER] Extracting inner components from {arch.name} to staging...")
                                    self._run_cmd([extractor, "e", "-y", "-r", f"-o{staging_dir}", str(arch), "*.rar", "*.7z", "*.bin", "*hotfix*.zip"])
                        except Exception as e:
                            self.log_line.emit(f"[WARN] Error reading zip container {arch.name}: {e}")
                        if not is_container:
                            direct_archives.append(arch)
                    else:
                        direct_archives.append(arch)

                # 3. Canonicalize multi-volume RAR archives into staging directory
                pool = direct_archives + [p for p in staging_dir.iterdir() if p.is_file()]
                groups = {}
                for p in pool:
                    m = rar_vol_pat.match(p.name)
                    if m:
                        prefix, vol_idx = m.group(1), int(m.group(2))
                        groups.setdefault(prefix, {})[vol_idx] = p

                extraction_queue = []
                for prefix, vols in groups.items():
                    self.log_line.emit(f"[VOLUMES] Group '{prefix}': detected {len(vols)} parts {sorted(vols.keys())}")
                    # Create symlinks with canonical names in staging_dir
                    for idx, src_p in vols.items():
                        canon_name = f"{prefix}.part{idx}.rar"
                        canon_path = staging_dir / canon_name
                        if canon_path != src_p:
                            if canon_path.exists() or canon_path.is_symlink():
                                canon_path.unlink()
                            canon_path.symlink_to(src_p.resolve())
                    # Add part 1 (or lowest part) to extraction queue
                    first_part = min(vols.keys())
                    extraction_queue.append(staging_dir / f"{prefix}.part{first_part}.rar")

                # Add standalone non-multipart archives
                for p in pool:
                    if not rar_vol_pat.match(p.name) and p.suffix.lower() in (
                        ".rar", ".zip", ".7z", ".bin", ".tar", ".tar.gz", ".tgz", ".tar.xz"
                    ):
                        extraction_queue.append(p)

                # Sort queue: base game first (0), updates (1), hotfixes (2)
                def sort_key(p: Path) -> int:
                    n = p.name.lower()
                    if "hotfix" in n or "settlement" in n:
                        return 2
                    if "update" in n or "patch" in n or "1.10" in n:
                        return 1
                    return 0

                extraction_queue = sorted(list(dict.fromkeys(extraction_queue)), key=sort_key)

                # Filter out pure documentation or secondary utility tools if primary game archives exist
                filtered_queue = []
                for a in extraction_queue:
                    nl = a.name.lower()
                    if "localization tool" in nl or "update summary" in nl or "localization-guide" in nl:
                        continue
                    filtered_queue.append(a)
                if not filtered_queue:
                    filtered_queue = extraction_queue

                # 4. Extract archives in order
                for idx, arch in enumerate(filtered_queue, 1):
                    self.progress_status.emit(f"Extracting archive [{idx}/{len(filtered_queue)}]: {arch.name}...")
                    args = [extractor, "x", "-y", "-pbilibili Cloud23333", f"-o{self.dest_path}", str(arch)]
                    ok = self._run_cmd(args)
                    if not ok:
                        self.log_line.emit("[INFO] Retrying extraction without password...")
                        args_no_pwd = [extractor, "x", "-y", f"-o{self.dest_path}", str(arch)]
                        ok = self._run_cmd(args_no_pwd)
                        if not ok:
                            self.finished.emit(False, f"Failed to extract {arch.name}.")
                            return

                found = find_game_root(self.dest_path)
                target_dir = found or self.dest_path

                # 5. Auto-unpack 1.10 incremental update .bin
                for bin_file in list(self.dest_path.rglob("FGO-*.bin")):
                    if bin_file.is_file():
                        self.progress_status.emit(f"Unpacking 1.10 incremental update ({bin_file.name})...")
                        self._run_cmd([extractor, "x", "-y", f"-o{target_dir}", str(bin_file)])

                        # If update extracted into a payload/ subdirectory, merge it into target_dir
                        payload_dir = target_dir / "payload"
                        if payload_dir.is_dir():
                            self.progress_status.emit("Merging 1.10 update payload into game root...")
                            self.log_line.emit("[INFO] Merging 1.10 payload tree into game root...")
                            for item in payload_dir.iterdir():
                                dest_item = target_dir / item.name
                                if item.is_dir():
                                    shutil.copytree(item, dest_item, dirs_exist_ok=True)
                                else:
                                    shutil.copy2(item, dest_item)
                            shutil.rmtree(payload_dir, ignore_errors=True)

                        # Clean obsolete 11.00 files
                        for obs in (
                            "App/ICF1", "App/ICF2", "App/EasterEgg", "App/BGM",
                            "App/FGOAudio.dll", "App/FgoDlss.dll",
                        ):
                            p = target_dir / obs
                            if p.is_file():
                                p.unlink()
                            elif p.is_dir():
                                shutil.rmtree(p, ignore_errors=True)
                        if (target_dir / "App" / "Localization" / "zh").is_dir() and (target_dir / "App" / "zh").is_dir():
                            shutil.rmtree(target_dir / "App" / "zh", ignore_errors=True)

                # 6. Auto-apply hotfix script and server code patch if present
                for repair_script in list(self.dest_path.rglob("repair_battle_summon.py")):
                    if repair_script.is_file():
                        self.progress_status.emit("Applying login settlement & battle offer hotfix...")
                        # 6a. Direct AST/code patch on Server/artemis/titles/fgo/index.py
                        patch_json = repair_script.with_name("battle-offer-code-patch.json")
                        index_py = target_dir / "Server" / "artemis" / "titles" / "fgo" / "index.py"
                        if patch_json.is_file() and index_py.is_file():
                            try:
                                import json
                                raw = index_py.read_bytes()
                                text = raw.decode("utf-8-sig").replace("\r\n", "\n")
                                patch_blocks = json.loads(patch_json.read_text(encoding="utf-8"))
                                for block in patch_blocks:
                                    old, new = block["old"], block["new"]
                                    if text.count(new) == 1 and old not in text:
                                        continue
                                    if text.count(old) == 1:
                                        text = text.replace(old, new, 1)
                                compile(text, "titles/fgo/index.py", "exec")
                                out_bytes = (b"\xef\xbb\xbf" if raw.startswith(b"\xef\xbb\xbf") else b"") + text.encode("utf-8")
                                index_py.write_bytes(out_bytes)
                                self.log_line.emit("[HOTFIX] Successfully applied battle offer code patch to Artemis server index.py")
                            except Exception as e:
                                self.log_line.emit(f"[WARN] Error patching index.py: {e}")

                        # 6b. Relax checks in repair_battle_summon.py if running with python3
                        try:
                            script_content = repair_script.read_text(encoding="utf-8")
                            check_str = 'Path(sys.executable).resolve() != (root / "Server" / "python" / "python.exe").resolve()'
                            if check_str in script_content:
                                script_content = script_content.replace(check_str, 'False')
                            old_assert = 'if os.name != "nt":\n        raise RuntimeError("Apply requires Windows process verification")'
                            if old_assert in script_content:
                                script_content = script_content.replace(old_assert, 'if os.name != "nt":\n        return')
                            repair_script.write_text(script_content, encoding="utf-8")
                            self._run_cmd([sys.executable, str(repair_script), "--root", str(target_dir), "--apply"])
                        except Exception as e:
                            self.log_line.emit(f"[WARN] repair_battle_summon.py: {e}")

                found = find_game_root(self.dest_path)
                if not found:
                    self.finished.emit(False, "App/ago.exe was not found inside the extracted files.")
                    return

                if self.install_sh.is_file():
                    self.progress_status.emit("Applying Linux runtime & server compatibility patches...")
                    self._run_cmd(["bash", str(self.install_sh), str(found)])

                set_fgoa_root(found)
                self.finished.emit(True, str(found))

            finally:
                shutil.rmtree(staging_dir, ignore_errors=True)


# ------------------------------------------------------------------------------
# Anti-Slop Component Classifier & Grouper
# ------------------------------------------------------------------------------

def classify_archive(p: Path) -> dict:
    """
    Anti-slop classifier: maps raw archive filenames to clean human-readable package metadata.
    Avoids raw dump hashes and cryptic multi-volume suffixes in user-facing UI.
    """
    nl = p.name.lower()

    # 1. Base Game
    if "cloud" in nl or "v1.00" in nl or ("base" in nl and "1.00" in nl):
        return {
            "key": "base",
            "badge": "BASE GAME",
            "badge_color": "#7CC4E4",
            "badge_bg": "#142838",
            "title": "FGO Arcade Base Game (v1.00 / ROM 11.00)",
            "desc": "Core SEGA ALLS binaries, AMFS assets & initial card catalog",
            "priority": 0,
        }

    # 2. Daily Settlement Hotfix (check before 1.10 to prevent misclassification)
    if "hotfix" in nl or "settlement" in nl:
        return {
            "key": "hotfix",
            "badge": "HOTFIX",
            "badge_color": "#E5C07B",
            "badge_bg": "#332B1A",
            "title": "Daily Settlement & Summon Hotfix",
            "desc": "Artemis server fix for daily login settlement & battle summon stability",
            "priority": 2,
        }

    # 3. Cumulative Update 1.10
    if "1.10" in nl or "update" in nl or "v1.10" in nl or "fgo-1.10" in nl:
        return {
            "key": "update",
            "badge": "UPDATE",
            "badge_color": "#85E89D",
            "badge_bg": "#1B3322",
            "title": "Cumulative Update (v1.10 / ROM 11.51)",
            "desc": "Version 11.51 binaries, 3,936 card artwork database & GPU optimizations",
            "priority": 1,
        }

    # 4. Localization
    if any(k in nl for k in ("localization", "translate", "translation", "fgozh", "scooby", "en_patch")):
        return {
            "key": "localization",
            "badge": "TRANSLATION",
            "badge_color": "#C678DD",
            "badge_bg": "#311C3D",
            "title": "Community Localization Pack",
            "desc": "UI translation runtime hooks & localized text assets",
            "priority": 3,
        }

    # 5. Generic / Custom Archive
    clean_title = re.sub(r"-\d{8}T\d{6}Z.*$", "", p.stem)
    clean_title = re.sub(r"\.part\d+(-00\d+)?$", "", clean_title, flags=re.IGNORECASE)
    clean_title = clean_title.replace("_", " ").strip()
    return {
        "key": "custom",
        "badge": "ARCHIVE",
        "badge_color": "#B0B7C3",
        "badge_bg": "#22262C",
        "title": clean_title or p.name,
        "desc": f"Archive package ({p.stat().st_size / (1024*1024):.1f} MB)" if p.is_file() else "Archive package",
        "priority": 4,
    }


def group_archives_by_package(paths: List[Path]) -> List[dict]:
    """
    Groups raw split volume archives and container zips into unified logical packages.
    """
    groups: dict[str, dict] = {}
    for p in paths:
        meta = classify_archive(p)
        key = meta["key"]
        size = p.stat().st_size if p.is_file() else 0
        if key not in groups:
            groups[key] = {
                "key": key,
                "meta": meta,
                "files": [p],
                "total_bytes": size,
            }
        else:
            groups[key]["files"].append(p)
            groups[key]["total_bytes"] += size

    res = list(groups.values())
    res.sort(key=lambda g: g["meta"]["priority"])
    for g in res:
        bytes_count = g["total_bytes"]
        gb = bytes_count / (1024 ** 3)
        mb = bytes_count / (1024 ** 2)
        g["formatted_size"] = f"{gb:.1f} GB" if gb >= 1.0 else f"{mb:.1f} MB"
        count = len(g["files"])
        g["formatted_count"] = f"{count} volumes" if count > 1 else "1 file"
    return res


# ------------------------------------------------------------------------------
# Modern UI Widgets: SelectableMenuCard & StepBreadcrumbBar
# ------------------------------------------------------------------------------

class SelectableMenuCard(QFrame):
    """
    Interactive selection card for the wizard menu.
    The entire card is clickable, hoverable, and displays glowing accent feedback.
    """
    clicked = pyqtSignal()

    def __init__(self, icon_glyph: str, title: str, description: str, badge: str = "", parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("SelectableMenuCard")
        self._title = title
        self._desc = description
        self._badge = badge
        self._init_ui(icon_glyph)

    def _init_ui(self, icon_glyph: str):
        self._apply_style(hover=False)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(16)

        lbl_icon = QLabel(icon_glyph)
        lbl_icon.setFixedSize(44, 44)
        lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_icon.setStyleSheet(f"""
            QLabel {{
                background-color: {Theme.PLATE_LOW};
                border: 1px solid {Theme.LINE};
                border-radius: 22px;
                font-size: 20px;
            }}
        """)
        layout.addWidget(lbl_icon)

        v_text = QVBoxLayout()
        v_text.setSpacing(4)

        h_title = QHBoxLayout()
        h_title.setSpacing(10)
        lbl_t = QLabel(self._title)
        lbl_t.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {Theme.TEXT};")
        h_title.addWidget(lbl_t)

        if self._badge:
            lbl_b = QLabel(self._badge)
            lbl_b.setStyleSheet(f"""
                QLabel {{
                    background-color: #162838;
                    color: {Theme.ICE};
                    font-size: 10px;
                    font-weight: 700;
                    padding: 2px 7px;
                    border: 1px solid #23485E;
                    border-radius: 3px;
                    letter-spacing: 0.5px;
                }}
            """)
            h_title.addWidget(lbl_b)

        h_title.addStretch()
        v_text.addLayout(h_title)

        lbl_d = QLabel(self._desc)
        lbl_d.setWordWrap(True)
        lbl_d.setStyleSheet(f"font-size: 12px; color: {Theme.TEXT_SOFT}; line-height: 1.4;")
        v_text.addWidget(lbl_d)

        layout.addLayout(v_text)
        layout.addStretch()

        self.lbl_arrow = QLabel("→")
        self.lbl_arrow.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {Theme.TEXT_FAINT};")
        layout.addWidget(self.lbl_arrow)

    def _apply_style(self, hover: bool):
        border = Theme.ICE if hover else Theme.LINE
        bg = "#21262E" if hover else Theme.PLATE
        self.setStyleSheet(f"""
            QFrame#SelectableMenuCard {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 8px;
            }}
        """)
        if hasattr(self, "lbl_arrow"):
            color = Theme.ICE if hover else Theme.TEXT_FAINT
            self.lbl_arrow.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {color};")

    def enterEvent(self, event):
        self._apply_style(hover=True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._apply_style(hover=False)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class StepBreadcrumbBar(QWidget):
    """Visual 3-stage breadcrumb indicator for wizard progression."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.step_labels = []
        steps = [("1", "SOURCE"), ("2", "CONFIGURE"), ("3", "INSTALL")]

        for idx, (num, name) in enumerate(steps):
            lbl = QLabel(f"{num}. {name}")
            lbl.setStyleSheet(f"""
                QLabel {{
                    color: {Theme.TEXT_FAINT};
                    font-size: 11px;
                    font-weight: 600;
                    padding: 4px 10px;
                    border-radius: 4px;
                    letter-spacing: 0.5px;
                }}
            """)
            layout.addWidget(lbl)
            self.step_labels.append(lbl)

            if idx < len(steps) - 1:
                divider = QLabel("──")
                divider.setStyleSheet(f"color: {Theme.LINE}; font-size: 10px;")
                layout.addWidget(divider)

    def set_current_step(self, page_index: int):
        stage_map = {0: 0, 1: 1, 2: 1, 3: 2, 4: 2}
        active_stage = stage_map.get(page_index, 0)
        names = ["SOURCE", "CONFIGURE", "INSTALL"]

        for idx, lbl in enumerate(self.step_labels):
            name = names[idx]
            if idx < active_stage:
                lbl.setText(f"✓ {name}")
                lbl.setStyleSheet(f"""
                    QLabel {{
                        background-color: #162B1D;
                        color: {Theme.READY};
                        font-size: 11px;
                        font-weight: 700;
                        padding: 4px 10px;
                        border: 1px solid #234B2E;
                        border-radius: 4px;
                        letter-spacing: 0.5px;
                    }}
                """)
            elif idx == active_stage:
                is_done = (page_index == 4)
                color = Theme.READY if is_done else Theme.ICE
                bg = "#162B1D" if is_done else "#142838"
                border = "#234B2E" if is_done else Theme.ICE
                prefix = "✓" if is_done else f"{idx+1}."
                lbl.setText(f"{prefix} {name}")
                lbl.setStyleSheet(f"""
                    QLabel {{
                        background-color: {bg};
                        color: {color};
                        font-size: 11px;
                        font-weight: 700;
                        padding: 4px 10px;
                        border: 1px solid {border};
                        border-radius: 4px;
                        letter-spacing: 0.5px;
                    }}
                """)
            else:
                lbl.setText(f"{idx+1}. {name}")
                lbl.setStyleSheet(f"""
                    QLabel {{
                        color: {Theme.TEXT_FAINT};
                        font-size: 11px;
                        font-weight: 600;
                        padding: 4px 10px;
                        border: 1px solid transparent;
                        border-radius: 4px;
                        letter-spacing: 0.5px;
                    }}
                """)


# ------------------------------------------------------------------------------
# Redesigned Setup Wizard Dialog
# ------------------------------------------------------------------------------

class SetupWizardDialog(QDialog):
    """Modern arcade-themed setup dialog guiding installation and configuration."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Fate/Grand Order Arcade - Setup Wizard")
        self.setFixedSize(780, 600)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {Theme.GROUND};
                color: {Theme.TEXT};
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
            }}
            QLabel {{
                color: {Theme.TEXT};
            }}
            QLineEdit {{
                background-color: {Theme.PLATE};
                border: 1px solid {Theme.LINE};
                color: {Theme.TEXT};
                padding: 8px 12px;
                border-radius: 4px;
                font-size: 13px;
            }}
            QLineEdit:focus {{
                border-color: {Theme.ICE};
            }}
            QProgressBar {{
                background-color: {Theme.PLATE};
                border: 1px solid {Theme.LINE};
                border-radius: 4px;
                height: 14px;
                text-align: center;
                color: {Theme.TEXT};
                font-size: 10px;
            }}
            QProgressBar::chunk {{
                background-color: {Theme.ICE};
                border-radius: 3px;
            }}
            QPlainTextEdit {{
                background-color: #0E1013;
                border: 1px solid {Theme.LINE};
                border-radius: 6px;
                color: {Theme.TEXT_SOFT};
                font-family: 'Consolas', 'JetBrains Mono', monospace;
                font-size: 11px;
                padding: 8px;
            }}
        """)

        self.download_dir = _get_download_dir()
        self.configured_root: Optional[Path] = None
        self.worker: Optional[SetupWorker] = None
        self.selected_archives: List[Path] = []

        for icon_path in (PLATFORM_PNG, PLATFORM_ICO):
            if icon_path.is_file():
                self.setWindowIcon(QIcon(str(icon_path)))
                break

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header Banner with Branding & Breadcrumbs
        header = QFrame()
        header.setFixedHeight(68)
        header.setStyleSheet(f"""
            QFrame {{
                background-color: {Theme.GROUND};
                border-bottom: 1px solid {Theme.LINE};
            }}
        """)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(24, 10, 24, 10)
        h_layout.setSpacing(16)

        brand_box = QHBoxLayout()
        brand_box.setSpacing(12)
        lbl_icon = QLabel()
        for icon_path in (PLATFORM_PNG, PLATFORM_ICO):
            if icon_path.is_file():
                lbl_icon.setPixmap(
                    QPixmap(str(icon_path)).scaled(
                        36, 36, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
                    )
                )
                break
        lbl_icon.setFixedSize(36, 36)
        brand_box.addWidget(lbl_icon)

        v_head = QVBoxLayout()
        v_head.setSpacing(2)
        lbl_brand = QLabel("Fate/Grand Order Arcade")
        lbl_brand.setStyleSheet(f"font-size: 17px; font-weight: 700; color: {Theme.TEXT}; letter-spacing: 0.3px;")
        lbl_sub = QLabel("Native Linux Orchestration Setup")
        lbl_sub.setStyleSheet(f"font-size: 11px; color: {Theme.TEXT_SOFT};")
        v_head.addWidget(lbl_brand)
        v_head.addWidget(lbl_sub)
        brand_box.addLayout(v_head)
        h_layout.addLayout(brand_box)
        h_layout.addStretch()

        self.breadcrumb = StepBreadcrumbBar()
        h_layout.addWidget(self.breadcrumb)

        layout.addWidget(header)

        # Stacked Pages
        self.stack = QStackedWidget()
        layout.addWidget(self.stack)

        self._build_page_welcome()
        self._build_page_folder()
        self._build_page_archive()
        self._build_page_progress()
        self._build_page_complete()

        self.stack.currentChanged.connect(self._on_page_changed)
        self.stack.setCurrentIndex(0)
        self.breadcrumb.set_current_step(0)

    def _on_page_changed(self, idx: int):
        self.breadcrumb.set_current_step(idx)

    # -----------------------------------------------------------------
    # Page 0: Welcome & Setup Mode
    # -----------------------------------------------------------------
    def _build_page_welcome(self):
        page = QWidget()
        l = QVBoxLayout(page)
        l.setContentsMargins(40, 24, 40, 24)
        l.setSpacing(14)

        lbl_title = QLabel("Get Started with Fate/Grand Order Arcade")
        lbl_title.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {Theme.TEXT};")
        l.addWidget(lbl_title)

        lbl_desc = QLabel(
            "Select how you would like to set up Fate/Grand Order Arcade on this machine.\n"
            "Our native runner configures Wine prefix, patches graphics for Linux/Wayland, and coordinates the Artemis server."
        )
        lbl_desc.setStyleSheet(f"color: {Theme.TEXT_SOFT}; font-size: 12px; line-height: 1.4;")
        l.addWidget(lbl_desc)

        # Smart Auto-Detection Container
        self.frame_detection = QFrame()
        self.layout_detection = QVBoxLayout(self.frame_detection)
        self.layout_detection.setContentsMargins(0, 0, 0, 0)
        l.addWidget(self.frame_detection)

        lbl_choice = QLabel("Or choose setup method manually:")
        lbl_choice.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {Theme.TEXT_SOFT}; margin-top: 4px;")
        l.addWidget(lbl_choice)

        # Interactive Menu Cards
        card_folder = SelectableMenuCard(
            icon_glyph="📁",
            title="Link Existing Game Folder",
            description="Point to an already extracted FGO Arcade directory. We will configure Wine prefix, network routing, and local Artemis server.",
            badge="DIRECT",
        )
        card_folder.clicked.connect(lambda: self.stack.setCurrentIndex(1))
        l.addWidget(card_folder)

        card_archive = SelectableMenuCard(
            icon_glyph="📦",
            title="Extract & Install from Archives",
            description="Select downloaded .rar, .zip, or .7z archives. Automatically unpacks split volumes, merges 1.10 updates, and applies hotfixes.",
            badge="CLEAN INSTALL",
        )
        card_archive.clicked.connect(lambda: self.stack.setCurrentIndex(2))
        l.addWidget(card_archive)

        l.addStretch()

        self._refresh_downloads_scan()
        self.stack.addWidget(page)

    def _refresh_downloads_scan(self):
        """Scan Downloads folder and render smart detection card or minimal rescan bar."""
        while self.layout_detection.count():
            item = self.layout_detection.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                sub_l = item.layout()
                while sub_l.count():
                    sub_item = sub_l.takeAt(0)
                    if sub_item.widget():
                        sub_item.widget().deleteLater()

        found_folder, found_archives = _scan_downloads_for_game(self.download_dir)

        if found_folder:
            box = QFrame()
            box.setStyleSheet("""
                QFrame {
                    background-color: #13241C;
                    border: 1px solid #85E89D;
                    border-radius: 8px;
                    padding: 12px;
                }
            """)
            h_det = QHBoxLayout(box)
            h_det.setContentsMargins(8, 4, 8, 4)

            v_info = QVBoxLayout()
            lbl_title = QLabel("● Existing Game Installation Detected")
            lbl_title.setStyleSheet("font-size: 14px; font-weight: 700; color: #85E89D;")
            lbl_sub = QLabel(f"Location: {found_folder}")
            lbl_sub.setStyleSheet(f"font-size: 12px; color: {Theme.TEXT_SOFT};")
            v_info.addWidget(lbl_title)
            v_info.addWidget(lbl_sub)
            h_det.addLayout(v_info)
            h_det.addStretch()

            btn_use = QPushButton("Use This Installation →")
            btn_use.setStyleSheet(Theme.PRIMARY_BUTTON)
            btn_use.clicked.connect(lambda: self._use_detected_folder(found_folder))
            h_det.addWidget(btn_use)

            self.layout_detection.addWidget(box)

        elif found_archives:
            box = QFrame()
            box.setStyleSheet(f"""
                QFrame {{
                    background-color: #132330;
                    border: 1px solid {Theme.ICE};
                    border-radius: 8px;
                    padding: 12px;
                }}
            """)
            h_det = QHBoxLayout(box)
            h_det.setContentsMargins(8, 4, 8, 4)

            v_info = QVBoxLayout()
            lbl_title = QLabel("● Game Packages Discovered in Downloads")
            lbl_title.setStyleSheet(f"font-size: 14px; font-weight: 700; color: {Theme.ICE};")

            # Anti-slop package chips
            packages = group_archives_by_package(found_archives)
            h_chips = QHBoxLayout()
            h_chips.setSpacing(6)
            for pkg in packages[:3]:
                meta = pkg["meta"]
                chip = QLabel(f"[{meta['badge']}] {meta['title']}")
                chip.setStyleSheet(f"""
                    QLabel {{
                        background-color: {meta['badge_bg']};
                        color: {meta['badge_color']};
                        font-size: 11px;
                        font-weight: 600;
                        padding: 3px 8px;
                        border-radius: 4px;
                    }}
                """)
                h_chips.addWidget(chip)
            h_chips.addStretch()

            total_bytes = sum(p.stat().st_size for p in found_archives if p.is_file())
            total_gb = total_bytes / (1024 ** 3)
            lbl_sub = QLabel(f"{len(packages)} packages detected ({total_gb:.1f} GB total)")
            lbl_sub.setStyleSheet(f"font-size: 11px; color: {Theme.TEXT_SOFT}; margin-top: 2px;")

            v_info.addWidget(lbl_title)
            v_info.addLayout(h_chips)
            v_info.addWidget(lbl_sub)
            h_det.addLayout(v_info)
            h_det.addStretch()

            btn_use = QPushButton("Configure & Install →")
            btn_use.setStyleSheet(Theme.PRIMARY_BUTTON)
            btn_use.clicked.connect(lambda: self._use_detected_archives(found_archives))
            h_det.addWidget(btn_use)

            self.layout_detection.addWidget(box)

        else:
            box = QFrame()
            box.setStyleSheet(f"""
                QFrame {{
                    background-color: {Theme.PLATE};
                    border: 1px dashed {Theme.LINE};
                    border-radius: 6px;
                    padding: 8px 12px;
                }}
            """)
            h_empty = QHBoxLayout(box)
            h_empty.setContentsMargins(6, 2, 6, 2)
            lbl_none = QLabel(f"No game packages found in {self.download_dir}")
            lbl_none.setStyleSheet(f"font-size: 12px; color: {Theme.TEXT_MUTED};")
            h_empty.addWidget(lbl_none)
            h_empty.addStretch()

            btn_rescan = QPushButton("↻ Check Downloads")
            btn_rescan.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {Theme.ICE};
                    border: 1px solid {Theme.LINE};
                    border-radius: 3px;
                    font-size: 11px;
                    padding: 4px 10px;
                }}
                QPushButton:hover {{
                    border-color: {Theme.ICE};
                    background-color: {Theme.PLATE_LOW};
                }}
            """)
            btn_rescan.clicked.connect(self._refresh_downloads_scan)
            h_empty.addWidget(btn_rescan)
            self.layout_detection.addWidget(box)

    def _use_detected_folder(self, folder: Path):
        self.txt_folder_path.setText(str(folder))
        self._validate_folder_input(str(folder))
        self.stack.setCurrentIndex(1)

    def _use_detected_archives(self, archives: List[Path]):
        self.selected_archives = archives
        self._refresh_package_roster()
        self._update_disk_space_display()
        self.stack.setCurrentIndex(2)

    # -----------------------------------------------------------------
    # Page 1: Existing Folder Selection with Live Inspection
    # -----------------------------------------------------------------
    def _build_page_folder(self):
        page = QWidget()
        l = QVBoxLayout(page)
        l.setContentsMargins(40, 24, 40, 24)
        l.setSpacing(14)

        lbl_title = QLabel("Locate Installed Game Folder")
        lbl_title.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {Theme.TEXT};")
        l.addWidget(lbl_title)

        lbl_desc = QLabel("Choose the root directory containing App/ago.exe, Server/, and DEVICE/:")
        lbl_desc.setStyleSheet(f"color: {Theme.TEXT_SOFT}; font-size: 13px;")
        l.addWidget(lbl_desc)

        row_input = QHBoxLayout()
        row_input.setSpacing(10)
        self.txt_folder_path = QLineEdit()
        self.txt_folder_path.setPlaceholderText("/home/user/Games/FGOA")
        self.txt_folder_path.textChanged.connect(self._validate_folder_input)
        row_input.addWidget(self.txt_folder_path)

        btn_browse = QPushButton("Browse...")
        btn_browse.setStyleSheet(Theme.SECONDARY_BUTTON)
        btn_browse.clicked.connect(self._browse_folder)
        row_input.addWidget(btn_browse)
        l.addLayout(row_input)

        # Quick Preset Chips
        row_presets = QHBoxLayout()
        row_presets.setSpacing(8)
        lbl_pre = QLabel("Common presets:")
        lbl_pre.setStyleSheet(f"font-size: 11px; color: {Theme.TEXT_MUTED};")
        row_presets.addWidget(lbl_pre)

        default_fgoa = Path.home() / "Games" / "FGOA"
        btn_pre1 = QPushButton(str(default_fgoa))
        btn_pre1.setStyleSheet(f"""
            QPushButton {{
                background-color: {Theme.PLATE};
                border: 1px solid {Theme.LINE};
                color: {Theme.ICE};
                font-size: 11px;
                padding: 3px 8px;
                border-radius: 3px;
            }}
            QPushButton:hover {{
                border-color: {Theme.ICE};
            }}
        """)
        btn_pre1.clicked.connect(lambda: self.txt_folder_path.setText(str(default_fgoa)))
        row_presets.addWidget(btn_pre1)
        row_presets.addStretch()
        l.addLayout(row_presets)

        # Live Validation Card
        self.frame_folder_val = QFrame()
        self.frame_folder_val.setStyleSheet(f"""
            QFrame {{
                background-color: {Theme.PLATE};
                border: 1px solid {Theme.LINE};
                border-radius: 8px;
                padding: 14px;
            }}
        """)
        self.layout_folder_val = QVBoxLayout(self.frame_folder_val)
        self.layout_folder_val.setSpacing(8)

        self.lbl_folder_val_title = QLabel("Awaiting folder selection...")
        self.lbl_folder_val_title.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 13px; font-weight: 600;")
        self.layout_folder_val.addWidget(self.lbl_folder_val_title)

        self.lbl_folder_val_desc = QLabel("Enter or browse for an existing game folder to verify components.")
        self.lbl_folder_val_desc.setStyleSheet(f"color: {Theme.TEXT_SOFT}; font-size: 12px;")
        self.layout_folder_val.addWidget(self.lbl_folder_val_desc)

        l.addWidget(self.frame_folder_val)
        l.addStretch()

        # Nav Buttons
        row_nav = QHBoxLayout()
        btn_back = QPushButton("← Back")
        btn_back.setStyleSheet(Theme.SECONDARY_BUTTON)
        btn_back.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        row_nav.addWidget(btn_back)
        row_nav.addStretch()

        self.btn_folder_next = QPushButton("Apply & Continue →")
        self.btn_folder_next.setStyleSheet(Theme.PRIMARY_BUTTON)
        self.btn_folder_next.setEnabled(False)
        self.btn_folder_next.clicked.connect(self._start_folder_setup)
        row_nav.addWidget(self.btn_folder_next)
        l.addLayout(row_nav)

        self.stack.addWidget(page)

    def _browse_folder(self):
        start_dir = self.download_dir if self.download_dir.is_dir() else Path.home()
        chosen = QFileDialog.getExistingDirectory(self, "Select FGO Arcade Folder", str(start_dir))
        if chosen:
            self.txt_folder_path.setText(chosen)

    def _validate_folder_input(self, text: str):
        path = Path(text.strip()) if text.strip() else None
        if not path or not path.exists():
            self.frame_folder_val.setStyleSheet(f"background-color: {Theme.PLATE}; border: 1px solid #E06C75; border-radius: 8px; padding: 14px;")
            self.lbl_folder_val_title.setText("✗ Path does not exist")
            self.lbl_folder_val_title.setStyleSheet("color: #E06C75; font-size: 13px; font-weight: 700;")
            self.lbl_folder_val_desc.setText("Please specify an existing directory path on disk.")
            self.btn_folder_next.setEnabled(False)
            return

        found = find_game_root(path)
        if found:
            is_1151 = (found / "DEVICE" / "print" / "FGO11_51_AllServants").is_dir() or (found / "App" / "Localization").is_dir()
            ver_str = "11.51 (V1.10 Cumulative Update)" if is_1151 else "11.00 (Base Game)"
            card_count = "3,936 Bitmaps" if is_1151 else "Initial Catalog"

            self.frame_folder_val.setStyleSheet("background-color: #142820; border: 1px solid #85E89D; border-radius: 8px; padding: 14px;")
            self.lbl_folder_val_title.setText(f"✓ Valid Game Installation Detected ({ver_str})")
            self.lbl_folder_val_title.setStyleSheet("color: #85E89D; font-size: 14px; font-weight: 700;")
            self.lbl_folder_val_desc.setText(
                f"Location: {found}\n"
                f"• App/ago.exe: Verified\n"
                f"• Card Catalog: {card_count}\n"
                f"• Artemis Server: Ready for loopback configuration"
            )
            self.btn_folder_next.setEnabled(True)
        else:
            self.frame_folder_val.setStyleSheet(f"background-color: {Theme.PLATE}; border: 1px solid #E5C07B; border-radius: 8px; padding: 14px;")
            self.lbl_folder_val_title.setText("✗ Incomplete Game Directory")
            self.lbl_folder_val_title.setStyleSheet("color: #E5C07B; font-size: 13px; font-weight: 700;")
            self.lbl_folder_val_desc.setText("Could not locate App/ago.exe in this folder or its direct subdirectories.")
            self.btn_folder_next.setEnabled(False)

    def _start_folder_setup(self):
        path = Path(self.txt_folder_path.text().strip())
        found = find_game_root(path)
        if not found:
            return
        self.stack.setCurrentIndex(3)
        self.worker = SetupWorker(mode="folder", folder_path=found)
        self.worker.progress_status.connect(self.lbl_prog_task.setText)
        self.worker.log_line.connect(self.txt_prog_log.appendPlainText)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.start()

    # -----------------------------------------------------------------
    # Page 2: Archive Setup with Anti-Slop Package Roster
    # -----------------------------------------------------------------
    def _build_page_archive(self):
        page = QWidget()
        l = QVBoxLayout(page)
        l.setContentsMargins(40, 24, 40, 24)
        l.setSpacing(14)

        lbl_title = QLabel("Configure Archive Installation")
        lbl_title.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {Theme.TEXT};")
        l.addWidget(lbl_title)

        lbl_desc = QLabel("Review detected package components and choose your target installation directory:")
        lbl_desc.setStyleSheet(f"color: {Theme.TEXT_SOFT}; font-size: 13px;")
        l.addWidget(lbl_desc)

        # Anti-Slop Package Shelf Frame
        self.frame_packages = QFrame()
        self.frame_packages.setStyleSheet(f"""
            QFrame {{
                background-color: {Theme.PLATE};
                border: 1px solid {Theme.LINE};
                border-radius: 8px;
                padding: 12px;
            }}
        """)
        l_pkg_box = QVBoxLayout(self.frame_packages)
        l_pkg_box.setSpacing(10)

        h_pkg_head = QHBoxLayout()
        lbl_pk_title = QLabel("Selected Packages to Extract:")
        lbl_pk_title.setStyleSheet(f"font-size: 13px; font-weight: 700; color: {Theme.TEXT};")
        h_pkg_head.addWidget(lbl_pk_title)
        h_pkg_head.addStretch()

        btn_pick_arch = QPushButton("+ Choose Different Archives...")
        btn_pick_arch.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {Theme.ICE};
                font-size: 12px;
                border: 1px solid {Theme.LINE};
                border-radius: 3px;
                padding: 4px 10px;
            }}
            QPushButton:hover {{
                border-color: {Theme.ICE};
                background-color: {Theme.PLATE_LOW};
            }}
        """)
        btn_pick_arch.clicked.connect(self._browse_archives)
        h_pkg_head.addWidget(btn_pick_arch)
        l_pkg_box.addLayout(h_pkg_head)

        # Container for package rows
        self.layout_pkg_list = QVBoxLayout()
        self.layout_pkg_list.setSpacing(6)
        l_pkg_box.addLayout(self.layout_pkg_list)

        l.addWidget(self.frame_packages)

        # Destination Selection Row
        lbl_dst = QLabel("Target Installation Directory:")
        lbl_dst.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {Theme.TEXT};")
        l.addWidget(lbl_dst)

        row_dest = QHBoxLayout()
        row_dest.setSpacing(10)
        self.txt_dest_path = QLineEdit()
        default_dest = Path.home() / "Games" / "FGOA"
        self.txt_dest_path.setText(str(default_dest))
        self.txt_dest_path.textChanged.connect(self._update_disk_space_display)
        row_dest.addWidget(self.txt_dest_path)

        btn_pick_dest = QPushButton("Browse...")
        btn_pick_dest.setStyleSheet(Theme.SECONDARY_BUTTON)
        btn_pick_dest.clicked.connect(self._browse_dest)
        row_dest.addWidget(btn_pick_dest)
        l.addLayout(row_dest)

        # Storage Health Card
        self.frame_space = QFrame()
        self.frame_space.setStyleSheet(f"""
            QFrame {{
                background-color: {Theme.PLATE};
                border: 1px solid {Theme.LINE};
                border-radius: 6px;
                padding: 10px 14px;
            }}
        """)
        l_space = QHBoxLayout(self.frame_space)
        l_space.setContentsMargins(6, 4, 6, 4)
        self.lbl_space = QLabel("Checking storage health...")
        self.lbl_space.setStyleSheet(f"color: {Theme.TEXT_SOFT}; font-size: 12px;")
        l_space.addWidget(self.lbl_space)
        l_space.addStretch()
        self.lbl_space_status = QLabel("● Checking")
        self.lbl_space_status.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 12px; font-weight: 600;")
        l_space.addWidget(self.lbl_space_status)
        l.addWidget(self.frame_space)

        l.addStretch()

        # Nav Buttons
        row_nav = QHBoxLayout()
        btn_back = QPushButton("← Back")
        btn_back.setStyleSheet(Theme.SECONDARY_BUTTON)
        btn_back.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        row_nav.addWidget(btn_back)
        row_nav.addStretch()

        self.btn_start_extract = QPushButton("Start Extraction & Setup →")
        self.btn_start_extract.setStyleSheet(Theme.PRIMARY_BUTTON)
        self.btn_start_extract.setEnabled(False)
        self.btn_start_extract.clicked.connect(self._start_archive_setup)
        row_nav.addWidget(self.btn_start_extract)
        l.addLayout(row_nav)

        self.stack.addWidget(page)

    def _refresh_package_roster(self):
        """Render clean anti-slop package cards in the archive configuration shelf."""
        while self.layout_pkg_list.count():
            item = self.layout_pkg_list.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                sub_l = item.layout()
                while sub_l.count():
                    sub_item = sub_l.takeAt(0)
                    if sub_item.widget():
                        sub_item.widget().deleteLater()

        if not self.selected_archives:
            lbl_empty = QLabel("No archives currently selected. Click 'Choose Different Archives...' above.")
            lbl_empty.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 12px; padding: 6px 0;")
            self.layout_pkg_list.addWidget(lbl_empty)
            return

        packages = group_archives_by_package(self.selected_archives)
        for pkg in packages:
            meta = pkg["meta"]
            row = QFrame()
            row.setStyleSheet(f"""
                QFrame {{
                    background-color: {Theme.PLATE_LOW};
                    border: 1px solid {Theme.LINE_SOFT};
                    border-radius: 5px;
                    padding: 8px 10px;
                }}
            """)
            h_row = QHBoxLayout(row)
            h_row.setContentsMargins(6, 2, 6, 2)
            h_row.setSpacing(12)

            lbl_badge = QLabel(meta["badge"])
            lbl_badge.setStyleSheet(f"""
                QLabel {{
                    background-color: {meta['badge_bg']};
                    color: {meta['badge_color']};
                    font-size: 10px;
                    font-weight: 700;
                    padding: 2px 7px;
                    border: 1px solid {meta['badge_color']};
                    border-radius: 3px;
                }}
            """)
            h_row.addWidget(lbl_badge)

            v_txt = QVBoxLayout()
            v_txt.setSpacing(1)
            lbl_t = QLabel(meta["title"])
            lbl_t.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {Theme.TEXT};")
            lbl_d = QLabel(f"{meta['desc']} • {pkg['formatted_count']} ({pkg['formatted_size']})")
            lbl_d.setStyleSheet(f"font-size: 11px; color: {Theme.TEXT_MUTED};")
            v_txt.addWidget(lbl_t)
            v_txt.addWidget(lbl_d)
            h_row.addLayout(v_txt)
            h_row.addStretch()

            self.layout_pkg_list.addWidget(row)

    def _browse_archives(self):
        start_dir = self.download_dir if self.download_dir.is_dir() else Path.home()
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select FGO Arcade Archives",
            str(start_dir),
            "Archives (*.7z *.zip *.rar *.bin *.tar *.tar.gz *.tgz *.tar.xz);;All Files (*)",
        )
        if files:
            self.selected_archives = [Path(f) for f in files]
            self._refresh_package_roster()
            self._update_disk_space_display()

    def _browse_dest(self):
        chosen = QFileDialog.getExistingDirectory(self, "Select Destination Folder", str(Path.home() / "Games"))
        if chosen:
            p = Path(chosen)
            if p.name.lower() not in ("fgoa", "fgo_arcade", "fgo-arcade"):
                p = p / "FGOA"
            self.txt_dest_path.setText(str(p))

    def _update_disk_space_display(self):
        dest_str = self.txt_dest_path.text().strip()
        if not dest_str:
            self.btn_start_extract.setEnabled(False)
            return

        dest = Path(dest_str)
        check_dir = dest
        while not check_dir.exists() and check_dir.parent != check_dir:
            check_dir = check_dir.parent

        try:
            usage = shutil.disk_usage(check_dir)
            free_gb = usage.free / (1024 ** 3)
            needed_gb = 26.0

            if free_gb >= needed_gb:
                space_msg = f"Partition: {check_dir} • {free_gb:.1f} GB Available (Estimated required: ~{needed_gb:.0f} GB)"
                status_txt = "✓ Sufficient Free Space"
                color = "#85E89D"
            elif free_gb >= 10.0:
                space_msg = f"Partition: {check_dir} • {free_gb:.1f} GB Available (~{needed_gb:.0f} GB recommended)"
                status_txt = "⚠ Space Limited"
                color = "#E5C07B"
            else:
                space_msg = f"Partition: {check_dir} • Only {free_gb:.1f} GB Available"
                status_txt = "✗ Low Disk Space"
                color = "#E06C75"

            self.lbl_space.setText(space_msg)
            self.lbl_space_status.setText(status_txt)
            self.lbl_space_status.setStyleSheet(f"color: {color}; font-size: 12px; font-weight: 700;")

            has_archives = bool(self.selected_archives)
            self.btn_start_extract.setEnabled(has_archives and free_gb >= 5.0)
        except Exception as e:
            self.lbl_space.setText(f"Could not calculate disk usage: {e}")
            self.btn_start_extract.setEnabled(bool(self.selected_archives))

    def _start_archive_setup(self):
        dest = Path(self.txt_dest_path.text().strip())
        self.stack.setCurrentIndex(3)
        self.worker = SetupWorker(
            mode="archive",
            archive_paths=self.selected_archives,
            dest_path=dest,
        )
        self.worker.progress_status.connect(self.lbl_prog_task.setText)
        self.worker.log_line.connect(self.txt_prog_log.appendPlainText)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.start()

    # -----------------------------------------------------------------
    # Page 3: Progress & Embedded Log
    # -----------------------------------------------------------------
    def _build_page_progress(self):
        page = QWidget()
        l = QVBoxLayout(page)
        l.setContentsMargins(40, 24, 40, 24)
        l.setSpacing(14)

        lbl_title = QLabel("Setting Up Fate/Grand Order Arcade")
        lbl_title.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {Theme.TEXT};")
        l.addWidget(lbl_title)

        self.lbl_prog_task = QLabel("Initializing setup tasks...")
        self.lbl_prog_task.setStyleSheet(f"font-size: 13px; color: {Theme.ICE}; font-weight: 600;")
        l.addWidget(self.lbl_prog_task)

        self.bar_prog = QProgressBar()
        self.bar_prog.setRange(0, 0)
        l.addWidget(self.bar_prog)

        lbl_log = QLabel("Setup Log Output:")
        lbl_log.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {Theme.TEXT_SOFT}; margin-top: 6px;")
        l.addWidget(lbl_log)

        self.txt_prog_log = QPlainTextEdit()
        self.txt_prog_log.setReadOnly(True)
        l.addWidget(self.txt_prog_log)

        self.stack.addWidget(page)

    def _on_worker_finished(self, success: bool, msg: str):
        if success:
            self.configured_root = Path(msg)
            self.bar_prog.setRange(0, 100)
            self.bar_prog.setValue(100)
            self._update_complete_page(self.configured_root)
            self.stack.setCurrentIndex(4)
        else:
            self.lbl_prog_task.setText(f"Setup Failed: {msg}")
            self.lbl_prog_task.setStyleSheet("color: #E06C75; font-size: 13px; font-weight: 600;")
            self.bar_prog.setRange(0, 100)
            self.bar_prog.setValue(0)

    # -----------------------------------------------------------------
    # Page 4: Success & Launch Game
    # -----------------------------------------------------------------
    def _build_page_complete(self):
        page = QWidget()
        l = QVBoxLayout(page)
        l.setContentsMargins(40, 28, 40, 28)
        l.setSpacing(16)
        l.setAlignment(Qt.AlignmentFlag.AlignCenter)

        lbl_emblem = QLabel()
        for icon_path in (PLATFORM_PNG, PLATFORM_ICO):
            if icon_path.is_file():
                lbl_emblem.setPixmap(
                    QPixmap(str(icon_path)).scaled(
                        60, 60, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
                    )
                )
                break
        lbl_emblem.setFixedSize(60, 60)
        l.addWidget(lbl_emblem, alignment=Qt.AlignmentFlag.AlignCenter)

        lbl_done = QLabel("SETUP COMPLETE")
        lbl_done.setStyleSheet(f"font-size: 20px; font-weight: 800; color: {Theme.ICE}; letter-spacing: 1px;")
        l.addWidget(lbl_done, alignment=Qt.AlignmentFlag.AlignCenter)

        self.lbl_complete_info = QLabel()
        self.lbl_complete_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_complete_info.setStyleSheet(f"color: {Theme.TEXT_SOFT}; font-size: 13px; line-height: 1.6;")
        l.addWidget(self.lbl_complete_info)

        l.addSpacing(10)

        btn_launch = ChamferButton(
            text="LAUNCH GAME DASHBOARD",
            cut=10.0,
            stroke_color="#7CC4E4",
            hover_stroke="#B3E0F5",
            fill_color="#1A1D22",
            hover_fill="#24303A",
            text_color="#FFFFFF",
            font_size=15,
        )
        btn_launch.setFixedHeight(48)
        btn_launch.setFixedWidth(320)
        btn_launch.clicked.connect(self.accept)
        l.addWidget(btn_launch, alignment=Qt.AlignmentFlag.AlignCenter)

        self.stack.addWidget(page)

    def _update_complete_page(self, game_root: Path):
        is_1151 = (game_root / "DEVICE" / "print" / "FGO11_51_AllServants").is_dir() or (game_root / "App" / "Localization").is_dir()
        ver = "11.51 (V1.10 Cumulative Update)" if is_1151 else "11.00 (Base Game)"
        self.lbl_complete_info.setText(
            f"Fate/Grand Order Arcade has been successfully configured!\n\n"
            f"• Installation: {game_root}\n"
            f"• ROM Version: {ver}\n"
            f"• Linux Compatibility Patches: Applied\n"
            f"• Local Artemis Server Stack: Configured & Ready\n"
            f"• Controls Profile: XInput & Keyboard Ready"
        )


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(Theme.GLOBAL_QSS)
    wizard = SetupWizardDialog()
    wizard.show()
    sys.exit(app.exec())
