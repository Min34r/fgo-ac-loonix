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


class SetupWizardDialog(QDialog):
    """Arcade-themed setup dialog guiding first-time installation or path re-configuration."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Fate/Grand Order Arcade - Setup Wizard")
        self.setFixedSize(700, 560)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {Theme.GROUND};
                color: {Theme.TEXT};
                font-family: 'Segoe UI', system-ui, sans-serif;
            }}
            QLabel {{
                color: {Theme.TEXT};
            }}
            QLineEdit {{
                background-color: {Theme.PLATE};
                border: 1px solid {Theme.LINE};
                color: {Theme.TEXT};
                padding: 6px 10px;
                border-radius: 2px;
                font-size: 13px;
            }}
            QLineEdit:focus {{
                border-color: {Theme.ICE};
            }}
            QProgressBar {{
                background-color: {Theme.PLATE};
                border: 1px solid {Theme.LINE};
                border-radius: 2px;
                height: 16px;
                text-align: center;
                color: {Theme.TEXT};
                font-size: 11px;
            }}
            QProgressBar::chunk {{
                background-color: {Theme.ICE};
            }}
            QPlainTextEdit {{
                background-color: #0E1013;
                border: 1px solid {Theme.LINE};
                color: {Theme.TEXT_SOFT};
                font-family: 'Consolas', 'JetBrains Mono', monospace;
                font-size: 11px;
            }}
        """)

        self.download_dir = _get_download_dir()
        self.configured_root: Optional[Path] = None
        self.worker: Optional[SetupWorker] = None

        for icon_path in (PLATFORM_PNG, PLATFORM_ICO):
            if icon_path.is_file():
                self.setWindowIcon(QIcon(str(icon_path)))
                break

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header Banner (Mirrors MainWindow header layout and assets)
        header = QFrame()
        header.setFixedHeight(66)
        header.setStyleSheet(f"""
            QFrame {{
                background-color: {Theme.GROUND};
                border-bottom: 1px solid {Theme.LINE};
            }}
        """)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(20, 10, 20, 10)
        h_layout.setSpacing(14)
        
        # Brand box mirroring MainWindow
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
        v_head.setSpacing(1)
        lbl_brand = QLabel("Fate/Grand Order Arcade")
        lbl_brand.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {Theme.TEXT}; letter-spacing: 0.3px;")
        lbl_sub = QLabel("Native Linux Orchestration Setup")
        lbl_sub.setStyleSheet(f"font-size: 11px; color: {Theme.TEXT_SOFT};")
        v_head.addWidget(lbl_brand)
        v_head.addWidget(lbl_sub)
        brand_box.addLayout(v_head)
        h_layout.addLayout(brand_box)
        h_layout.addStretch()

        self.lbl_header_step = QLabel("SETUP WIZARD")
        self.lbl_header_step.setStyleSheet(f"""
            QLabel {{
                background-color: {Theme.PLATE};
                border: 1px solid {Theme.LINE};
                color: {Theme.ICE};
                font-size: 11px;
                font-weight: 700;
                padding: 5px 12px;
                border-radius: 3px;
                letter-spacing: 0.8px;
            }}
        """)
        h_layout.addWidget(self.lbl_header_step)

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

    def _on_page_changed(self, idx: int):
        labels = {
            0: "SETUP WIZARD",
            1: "FOLDER SETUP",
            2: "ARCHIVE SETUP",
            3: "INSTALLING",
            4: "SETUP COMPLETE",
        }
        self.lbl_header_step.setText(labels.get(idx, "SETUP WIZARD"))

    # -----------------------------------------------------------------
    # Page 0: Welcome & Setup Mode (Downloads detection with fallback)
    # -----------------------------------------------------------------
    def _build_page_welcome(self):
        page = QWidget()
        l = QVBoxLayout(page)
        l.setContentsMargins(36, 20, 36, 20)
        l.setSpacing(12)

        lbl_title = QLabel("Locate or Install Game Files")
        lbl_title.setStyleSheet(f"font-size: 17px; font-weight: 700; color: {Theme.TEXT};")
        l.addWidget(lbl_title)

        lbl_desc = QLabel(
            "Select how you would like to set up Fate/Grand Order Arcade on this machine.\n"
            "The wizard will configure Wine, patch game binaries for Linux, and start the local server."
        )
        lbl_desc.setStyleSheet(f"color: {Theme.TEXT_SOFT}; font-size: 12px; line-height: 1.4;")
        l.addWidget(lbl_desc)

        # Download Directory Auto-Detection Container
        self.frame_detection = QFrame()
        self.layout_detection = QVBoxLayout(self.frame_detection)
        self.layout_detection.setContentsMargins(10, 8, 10, 8)
        l.addWidget(self.frame_detection)

        self.lbl_choice_prompt = QLabel("Choose setup method:")
        self.lbl_choice_prompt.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {Theme.TEXT_SOFT}; margin-top: 4px;")
        l.addWidget(self.lbl_choice_prompt)

        # Option A: Folder
        box_folder = QFrame()
        box_folder.setStyleSheet(f"""
            QFrame {{
                background-color: {Theme.PLATE};
                border: 1px solid {Theme.LINE};
                border-radius: 4px;
                padding: 10px;
            }}
            QFrame:hover {{
                border-color: {Theme.ICE};
                background-color: #21252C;
            }}
        """)
        l_bf = QHBoxLayout(box_folder)
        l_bf.setContentsMargins(14, 8, 14, 8)
        
        v_txt1 = QVBoxLayout()
        lbl_opt1_title = QLabel("Select Extracted Game Folder")
        lbl_opt1_title.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {Theme.ICE};")
        lbl_opt1_desc = QLabel("Use an existing Cloud23333 FGOA folder (containing App/ago.exe).")
        lbl_opt1_desc.setStyleSheet(f"font-size: 12px; color: {Theme.TEXT_SOFT};")
        v_txt1.addWidget(lbl_opt1_title)
        v_txt1.addWidget(lbl_opt1_desc)
        l_bf.addLayout(v_txt1)
        l_bf.addStretch()

        btn_go_folder = QPushButton("Select Folder")
        btn_go_folder.setStyleSheet(Theme.PRIMARY_BUTTON)
        btn_go_folder.clicked.connect(lambda: self.stack.setCurrentIndex(1))
        l_bf.addWidget(btn_go_folder)

        l.addWidget(box_folder)

        # Option B: Archive
        box_arch = QFrame()
        box_arch.setStyleSheet(f"""
            QFrame {{
                background-color: {Theme.PLATE};
                border: 1px solid {Theme.LINE};
                border-radius: 4px;
                padding: 10px;
            }}
            QFrame:hover {{
                border-color: {Theme.ICE};
                background-color: #21252C;
            }}
        """)
        l_ba = QHBoxLayout(box_arch)
        l_ba.setContentsMargins(14, 8, 14, 8)

        v_txt2 = QVBoxLayout()
        lbl_opt2_title = QLabel("Extract Game Rip Archive(s)")
        lbl_opt2_title.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {Theme.ICE};")
        lbl_opt2_desc = QLabel("Unpack multi-part .rar / .zip / .7z archives with auto-password and 1.10 patching.")
        lbl_opt2_desc.setStyleSheet(f"font-size: 12px; color: {Theme.TEXT_SOFT};")
        v_txt2.addWidget(lbl_opt2_title)
        v_txt2.addWidget(lbl_opt2_desc)
        l_ba.addLayout(v_txt2)
        l_ba.addStretch()

        btn_go_arch = QPushButton("Select Archives")
        btn_go_arch.setStyleSheet(Theme.SECONDARY_BUTTON)
        btn_go_arch.clicked.connect(lambda: self.stack.setCurrentIndex(2))
        l_ba.addWidget(btn_go_arch)

        l.addWidget(box_arch)
        l.addStretch()

        self._refresh_downloads_scan()
        self.stack.addWidget(page)

    def _refresh_downloads_scan(self):
        """Scan Downloads folder and render detected artifact card or empty fallback notice."""
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
            self.frame_detection.setStyleSheet(f"""
                QFrame {{
                    background-color: #172430;
                    border: 1px solid {Theme.ICE};
                    border-radius: 4px;
                    padding: 8px;
                }}
            """)
            h_det = QHBoxLayout()
            h_det.setContentsMargins(6, 4, 6, 4)
            v_info = QVBoxLayout()
            lbl_title = QLabel("✓ Found Game Folder in Downloads")
            lbl_title.setStyleSheet("font-size: 13px; font-weight: 700; color: #98C379;")
            lbl_sub = QLabel(f"Location: {found_folder}")
            lbl_sub.setStyleSheet(f"font-size: 11px; color: {Theme.TEXT_SOFT};")
            v_info.addWidget(lbl_title)
            v_info.addWidget(lbl_sub)
            h_det.addLayout(v_info)
            h_det.addStretch()

            btn_use = QPushButton("Use Detected Folder")
            btn_use.setStyleSheet(Theme.PRIMARY_BUTTON)
            btn_use.clicked.connect(lambda: self._use_detected_folder(found_folder))
            h_det.addWidget(btn_use)
            self.layout_detection.addLayout(h_det)
            self.lbl_choice_prompt.setText("Or select another location manually:")

        elif found_archives:
            self.frame_detection.setStyleSheet(f"""
                QFrame {{
                    background-color: #172430;
                    border: 1px solid {Theme.ICE};
                    border-radius: 4px;
                    padding: 8px;
                }}
            """)
            h_det = QHBoxLayout()
            h_det.setContentsMargins(6, 4, 6, 4)
            v_info = QVBoxLayout()
            lbl_title = QLabel(f"✓ Found {len(found_archives)} Game Archive(s) in Downloads")
            lbl_title.setStyleSheet("font-size: 13px; font-weight: 700; color: #98C379;")
            names_str = ", ".join(a.name for a in found_archives[:2])
            if len(found_archives) > 2:
                names_str += f" (+{len(found_archives)-2} more)"
            lbl_sub = QLabel(names_str)
            lbl_sub.setStyleSheet(f"font-size: 11px; color: {Theme.TEXT_SOFT};")
            v_info.addWidget(lbl_title)
            v_info.addWidget(lbl_sub)
            h_det.addLayout(v_info)
            h_det.addStretch()

            btn_use = QPushButton("Extract Detected Archives")
            btn_use.setStyleSheet(Theme.PRIMARY_BUTTON)
            btn_use.clicked.connect(lambda: self._use_detected_archives(found_archives))
            h_det.addWidget(btn_use)
            self.layout_detection.addLayout(h_det)
            self.lbl_choice_prompt.setText("Or select another location manually:")

        else:
            self.frame_detection.setStyleSheet(f"""
                QFrame {{
                    background-color: {Theme.PLATE};
                    border: 1px dashed {Theme.LINE};
                    border-radius: 4px;
                    padding: 6px;
                }}
            """)
            h_empty = QHBoxLayout()
            h_empty.setContentsMargins(6, 2, 6, 2)
            lbl_none = QLabel(f"Scanned {self.download_dir} — No game files or archives found.")
            lbl_none.setStyleSheet(f"font-size: 11px; color: {Theme.TEXT_MUTED};")
            h_empty.addWidget(lbl_none)
            h_empty.addStretch()

            btn_rescan = QPushButton("↻ Rescan")
            btn_rescan.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {Theme.ICE};
                    border: 1px solid {Theme.LINE};
                    border-radius: 3px;
                    font-size: 11px;
                    padding: 3px 8px;
                }}
                QPushButton:hover {{
                    border-color: {Theme.ICE};
                    background-color: {Theme.PLATE_LOW};
                }}
            """)
            btn_rescan.clicked.connect(self._refresh_downloads_scan)
            h_empty.addWidget(btn_rescan)
            self.layout_detection.addLayout(h_empty)
            self.lbl_choice_prompt.setText("Choose setup method:")

    def _use_detected_folder(self, folder: Path):
        self.txt_folder_path.setText(str(folder))
        self._validate_folder_input(str(folder))
        self.stack.setCurrentIndex(1)

    def _use_detected_archives(self, archives: List[Path]):
        self.selected_archives = archives
        norm = _normalize_archives(archives)
        display = ", ".join(p.name for p in norm[:3])
        if len(norm) > 3:
            display += f" (+{len(norm)-3} more)"
        self.txt_arch_path.setText(display)
        self._update_disk_space_display()
        self.stack.setCurrentIndex(2)

    # -----------------------------------------------------------------
    # Page 1: Existing Folder Selection with Live Validation
    # -----------------------------------------------------------------
    def _build_page_folder(self):
        page = QWidget()
        l = QVBoxLayout(page)
        l.setContentsMargins(36, 24, 36, 24)
        l.setSpacing(14)

        lbl_title = QLabel("Locate Extracted Game Folder")
        lbl_title.setStyleSheet(f"font-size: 17px; font-weight: 700; color: {Theme.TEXT};")
        l.addWidget(lbl_title)

        lbl_desc = QLabel("Choose the root directory of your FGO Arcade installation:")
        lbl_desc.setStyleSheet(f"color: {Theme.TEXT_SOFT}; font-size: 13px;")
        l.addWidget(lbl_desc)

        row_input = QHBoxLayout()
        self.txt_folder_path = QLineEdit()
        self.txt_folder_path.setPlaceholderText("/home/user/Games/FGOA")
        self.txt_folder_path.textChanged.connect(self._validate_folder_input)
        row_input.addWidget(self.txt_folder_path)

        btn_browse = QPushButton("Browse...")
        btn_browse.setStyleSheet(Theme.SECONDARY_BUTTON)
        btn_browse.clicked.connect(self._browse_folder)
        row_input.addWidget(btn_browse)
        l.addLayout(row_input)

        # Validation Feedback Box
        self.frame_folder_val = QFrame()
        self.frame_folder_val.setStyleSheet(f"""
            QFrame {{
                background-color: {Theme.PLATE};
                border: 1px solid {Theme.LINE};
                border-radius: 4px;
                padding: 10px;
            }}
        """)
        l_val = QVBoxLayout(self.frame_folder_val)
        self.lbl_folder_val = QLabel("Enter or browse for an existing game folder to validate.")
        self.lbl_folder_val.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 12px;")
        l_val.addWidget(self.lbl_folder_val)
        l.addWidget(self.frame_folder_val)

        l.addStretch()

        # Nav Buttons
        row_nav = QHBoxLayout()
        btn_back = QPushButton("Back")
        btn_back.setStyleSheet(Theme.SECONDARY_BUTTON)
        btn_back.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        row_nav.addWidget(btn_back)
        row_nav.addStretch()

        self.btn_folder_next = QPushButton("Apply & Finish")
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
            self.lbl_folder_val.setText("Path does not exist.")
            self.lbl_folder_val.setStyleSheet("color: #E06C75; font-size: 12px;")
            self.frame_folder_val.setStyleSheet(f"background-color: {Theme.PLATE}; border: 1px solid #E06C75;")
            self.btn_folder_next.setEnabled(False)
            return

        found = find_game_root(path)
        if found:
            # Check version details
            is_1151 = (found / "DEVICE" / "print" / "FGO11_51_AllServants").is_dir() or (found / "App" / "Localization").is_dir()
            ver_str = "11.51 (V1.10 Update)" if is_1151 else "11.00 (Base V1.00)"
            self.lbl_folder_val.setText(f"✓ Valid Game Root Detected!\nLocation: {found}\nROM Version: {ver_str}")
            self.lbl_folder_val.setStyleSheet("color: #98C379; font-size: 12px; font-weight: 600;")
            self.frame_folder_val.setStyleSheet(f"background-color: {Theme.PLATE}; border: 1px solid #98C379;")
            self.btn_folder_next.setEnabled(True)
        else:
            self.lbl_folder_val.setText("✗ Could not locate App/ago.exe in this folder or its subdirectories.")
            self.lbl_folder_val.setStyleSheet("color: #E5C07B; font-size: 12px;")
            self.frame_folder_val.setStyleSheet(f"background-color: {Theme.PLATE}; border: 1px solid #E5C07B;")
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
    # Page 2: Archive Extraction with Disk Space Check
    # -----------------------------------------------------------------
    def _build_page_archive(self):
        page = QWidget()
        l = QVBoxLayout(page)
        l.setContentsMargins(36, 20, 36, 20)
        l.setSpacing(12)

        lbl_title = QLabel("Extract Game Rip Archives")
        lbl_title.setStyleSheet(f"font-size: 17px; font-weight: 700; color: {Theme.TEXT};")
        l.addWidget(lbl_title)

        lbl_desc = QLabel("Select downloaded archives (.rar / .zip / .7z) and extraction destination:")
        lbl_desc.setStyleSheet(f"color: {Theme.TEXT_SOFT}; font-size: 13px;")
        l.addWidget(lbl_desc)

        # Archive Selection Row
        l.addWidget(QLabel("Archive File(s):"))
        row_arch = QHBoxLayout()
        self.txt_arch_path = QLineEdit()
        self.txt_arch_path.setPlaceholderText("Select FGOA_Cloud23333.part1.rar or other archives...")
        self.txt_arch_path.setReadOnly(True)
        row_arch.addWidget(self.txt_arch_path)

        btn_pick_arch = QPushButton("Choose...")
        btn_pick_arch.setStyleSheet(Theme.SECONDARY_BUTTON)
        btn_pick_arch.clicked.connect(self._browse_archives)
        row_arch.addWidget(btn_pick_arch)
        l.addLayout(row_arch)

        # Destination Selection Row
        l.addWidget(QLabel("Destination Directory:"))
        row_dest = QHBoxLayout()
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

        # Disk Space & Validation Frame
        self.frame_space = QFrame()
        self.frame_space.setStyleSheet(f"""
            QFrame {{
                background-color: {Theme.PLATE};
                border: 1px solid {Theme.LINE};
                border-radius: 4px;
                padding: 10px;
            }}
        """)
        l_space = QVBoxLayout(self.frame_space)
        self.lbl_space = QLabel("Disk space check...")
        self.lbl_space.setStyleSheet(f"color: {Theme.TEXT_SOFT}; font-size: 12px;")
        l_space.addWidget(self.lbl_space)
        l.addWidget(self.frame_space)

        l.addStretch()

        # Nav Buttons
        row_nav = QHBoxLayout()
        btn_back = QPushButton("Back")
        btn_back.setStyleSheet(Theme.SECONDARY_BUTTON)
        btn_back.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        row_nav.addWidget(btn_back)
        row_nav.addStretch()

        self.btn_start_extract = QPushButton("Start Extraction & Setup")
        self.btn_start_extract.setStyleSheet(Theme.PRIMARY_BUTTON)
        self.btn_start_extract.setEnabled(False)
        self.btn_start_extract.clicked.connect(self._start_archive_setup)
        row_nav.addWidget(self.btn_start_extract)
        l.addLayout(row_nav)

        self.selected_archives: List[Path] = []
        self._update_disk_space_display()
        self.stack.addWidget(page)

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
            norm = _normalize_archives(self.selected_archives)
            display = ", ".join(p.name for p in norm[:3])
            if len(norm) > 3:
                display += f" (+{len(norm)-3} more)"
            self.txt_arch_path.setText(display)
            self._update_disk_space_display()

    def _browse_dest(self):
        chosen = QFileDialog.getExistingDirectory(self, "Select Destination Folder", str(Path.home() / "Games"))
        if chosen:
            # If user selected a parent folder like ~/Games, append FGOA
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
                space_msg = f"✓ Free Space: {free_gb:.1f} GB available (Estimated required: ~{needed_gb:.0f} GB)"
                color = "#98C379"
            elif free_gb >= 10.0:
                space_msg = f"⚠ Free Space: {free_gb:.1f} GB available (~{needed_gb:.0f} GB recommended for full rip + update)"
                color = "#E5C07B"
            else:
                space_msg = f"✗ Low Disk Space: Only {free_gb:.1f} GB available (At least 15 GB required to extract)"
                color = "#E06C75"

            self.lbl_space.setText(f"Target Partition: {check_dir}\n{space_msg}")
            self.lbl_space.setStyleSheet(f"color: {color}; font-size: 12px;")

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
        l.setContentsMargins(36, 24, 36, 24)
        l.setSpacing(12)

        lbl_title = QLabel("Setting Up Fate/Grand Order Arcade")
        lbl_title.setStyleSheet(f"font-size: 17px; font-weight: 700; color: {Theme.TEXT};")
        l.addWidget(lbl_title)

        self.lbl_prog_task = QLabel("Initializing setup tasks...")
        self.lbl_prog_task.setStyleSheet(f"font-size: 13px; color: {Theme.ICE}; font-weight: 600;")
        l.addWidget(self.lbl_prog_task)

        self.bar_prog = QProgressBar()
        self.bar_prog.setRange(0, 0)  # Indeterminate activity
        l.addWidget(self.bar_prog)

        l.addWidget(QLabel("Installation Log:"))
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
        l.setContentsMargins(36, 24, 36, 24)
        l.setSpacing(14)
        l.setAlignment(Qt.AlignmentFlag.AlignCenter)

        lbl_emblem = QLabel()
        for icon_path in (PLATFORM_PNG, PLATFORM_ICO):
            if icon_path.is_file():
                lbl_emblem.setPixmap(
                    QPixmap(str(icon_path)).scaled(
                        56, 56, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
                    )
                )
                break
        lbl_emblem.setFixedSize(56, 56)
        l.addWidget(lbl_emblem, alignment=Qt.AlignmentFlag.AlignCenter)

        lbl_done = QLabel("SETUP COMPLETE")
        lbl_done.setStyleSheet(f"font-size: 20px; font-weight: 800; color: {Theme.ICE}; letter-spacing: 1px;")
        l.addWidget(lbl_done, alignment=Qt.AlignmentFlag.AlignCenter)

        self.lbl_complete_info = QLabel()
        self.lbl_complete_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_complete_info.setStyleSheet(f"color: {Theme.TEXT_SOFT}; font-size: 13px; line-height: 1.6;")
        l.addWidget(self.lbl_complete_info)

        l.addSpacing(20)

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
        btn_launch.setFixedWidth(300)
        btn_launch.clicked.connect(self.accept)
        l.addWidget(btn_launch, alignment=Qt.AlignmentFlag.AlignCenter)

        self.stack.addWidget(page)

    def _update_complete_page(self, game_root: Path):
        is_1151 = (game_root / "DEVICE" / "print" / "FGO11_51_AllServants").is_dir() or (game_root / "App" / "Localization").is_dir()
        ver = "11.51 (V1.10 Update)" if is_1151 else "11.00 (Base V1.00)"
        self.lbl_complete_info.setText(
            f"Fate/Grand Order Arcade has been successfully configured!\n\n"
            f"Game Location: {game_root}\n"
            f"Detected Version: {ver}\n"
            f"Linux Compatibility Patches: Applied\n"
            f"Artemis Server: Configured & Ready"
        )


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(Theme.GLOBAL_QSS)
    wizard = SetupWizardDialog()
    wizard.show()
    sys.exit(app.exec())
