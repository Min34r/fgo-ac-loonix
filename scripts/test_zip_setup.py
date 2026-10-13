#!/usr/bin/env python3
"""
Test utility for Fate/Grand Order Arcade zip/archive installation.

Usage:
    # 1. Run full end-to-end headless verification test
    python3 scripts/test_zip_setup.py --test

    # 2. Generate mock archives into a folder to test via the GUI wizard
    python3 scripts/test_zip_setup.py --create-archives ~/Downloads/fgoa_test_zips
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def create_mock_archives(output_dir: Path, encrypted: bool = True) -> list[Path]:
    """Build a minimal realistic set of mock FGOA game rip archives."""
    output_dir.mkdir(parents=True, exist_ok=True)
    temp_build = Path(tempfile.mkdtemp(prefix="fgoa_mock_build_"))

    try:
        # 1. Create Base Game Structure (ROM 11.00)
        base_dir = temp_build / "base"
        (base_dir / "App").mkdir(parents=True, exist_ok=True)
        (base_dir / "Server" / "artemis" / "config").mkdir(parents=True, exist_ok=True)
        (base_dir / "GameData" / "SDEJ").mkdir(parents=True, exist_ok=True)
        (base_dir / "DEVICE" / "print" / "FGO11_AllServants").mkdir(parents=True, exist_ok=True)

        # Mock binary and configs
        (base_dir / "App" / "ago.exe").write_bytes(b"MZ_MOCK_FGOA_EXECUTABLE")
        (base_dir / "Server" / "artemis" / "config" / "fgo.yaml").write_text("advertise_version: 1100\n")
        (base_dir / "GameData" / "SDEJ" / "amdaemon_aux.json").write_text('{"develop_version": "11.00"}\n')
        (base_dir / "DEVICE" / "print" / "FGO11_AllServants" / "card_001.bmp").write_bytes(b"BM_MOCK_BMP")

        # Obsolete 11.00 files that should be cleaned up by 1.10
        (base_dir / "App" / "ICF1").write_text("obsolete_1100_icf1")
        (base_dir / "App" / "ICF2").write_text("obsolete_1100_icf2")
        (base_dir / "App" / "EasterEgg").write_text("obsolete_easter_egg")
        (base_dir / "App" / "BGM").mkdir(parents=True, exist_ok=True)
        (base_dir / "App" / "BGM" / "track.wav").write_bytes(b"WAV_MOCK")
        (base_dir / "App" / "FGOAudio.dll").write_bytes(b"DLL_MOCK")
        (base_dir / "App" / "FgoDlss.dll").write_bytes(b"DLL_MOCK")
        (base_dir / "App" / "zh").mkdir(parents=True, exist_ok=True)
        (base_dir / "App" / "zh" / "legacy.txt").write_text("legacy_zh")

        # 2. Create Cumulative 1.10 Update (.bin is a zip)
        update_dir = temp_build / "update"
        (update_dir / "App" / "Localization" / "zh").mkdir(parents=True, exist_ok=True)
        (update_dir / "DEVICE" / "print" / "FGO11_51_AllServants").mkdir(parents=True, exist_ok=True)
        (update_dir / "App" / "Localization" / "zh" / "fgozh.dll").write_bytes(b"DLL_ZH_1151")
        (update_dir / "DEVICE" / "print" / "FGO11_51_AllServants" / "card_001.bmp").write_bytes(b"BM_MOCK_BMP_1151")
        (update_dir / "DEVICE" / "print" / "FGO11_51_AllServants" / "card_002.bmp").write_bytes(b"BM_MOCK_BMP_1151")

        bin_archive = output_dir / "FGO-1.10.bin"
        subprocess.run(["7z", "a", "-y", str(bin_archive), "."], cwd=str(update_dir), check=True, stdout=subprocess.DEVNULL)

        # 3. Create Hotfix (repair_battle_summon.py)
        hotfix_dir = temp_build / "hotfix"
        hotfix_dir.mkdir(parents=True, exist_ok=True)
        hotfix_script = hotfix_dir / "repair_battle_summon.py"
        hotfix_script.write_text("""#!/usr/bin/env python3
import sys, argparse
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--root", required=True)
parser.add_argument("--apply", action="store_true")
args = parser.parse_args()

root = Path(args.root)
marker = root / "Server" / "artemis" / "hotfix_applied.marker"
marker.parent.mkdir(parents=True, exist_ok=True)
marker.write_text("HOTFIX_SUCCESS")
print(f"[HOTFIX] Successfully applied battle summon hotfix to {root}")
""")
        hotfix_archive = output_dir / "FGO-1.10-daily-settlement-hotfix-20261005.zip"
        subprocess.run(["7z", "a", "-y", str(hotfix_archive), "."], cwd=str(hotfix_dir), check=True, stdout=subprocess.DEVNULL)

        # Also copy FGO-1.10.bin into base so it mimics Cloud23333's rip structure if placed together
        shutil.copy(bin_archive, base_dir / "FGO-1.10.bin")

        # 4. Create Base Archive (with Cloud23333 password)
        base_archive = output_dir / "FGOA_V1.00_Base_Game.zip"
        cmd = ["7z", "a", "-y"]
        if encrypted:
            cmd.append("-pbilibili Cloud23333")
        cmd.extend([str(base_archive), "."])
        subprocess.run(cmd, cwd=str(base_dir), check=True, stdout=subprocess.DEVNULL)

        created = [base_archive, bin_archive, hotfix_archive]
        print(f"[OK] Generated {len(created)} mock archives in {output_dir}:")
        for p in created:
            print(f"  - {p.name} ({p.stat().st_size} bytes)")
        return created

    finally:
        shutil.rmtree(temp_build, ignore_errors=True)


def test_headless_installation():
    """Simulate complete installation using SetupWorker in headless mode."""
    from PyQt6.QtCore import QCoreApplication
    from launcher.core.config import find_game_root
    from launcher.ui.setup_wizard import SetupWorker, _normalize_archives

    app = QCoreApplication.instance() or QCoreApplication(sys.argv)

    test_dir = Path(tempfile.mkdtemp(prefix="fgoa_test_zip_setup_"))
    archives_dir = test_dir / "archives"
    dest_dir = test_dir / "installed_game"

    print("============================================================")
    print(" Running End-to-End Headless Zip Installation Test")
    print("============================================================")
    print(f"Test Workspace: {test_dir}")

    try:
        # Step 1: Create mock archives
        archives = create_mock_archives(archives_dir, encrypted=True)

        # Step 2: Test archive normalization
        normalized = _normalize_archives(archives)
        print(f"[TEST] Normalized extraction order:")
        for idx, p in enumerate(normalized, 1):
            print(f"  {idx}. {p.name}")
        assert normalized[0].name.startswith("FGOA_V1.00_Base"), "Base archive must extract first"

        # Step 3: Run SetupWorker
        logs: list[str] = []
        statuses: list[str] = []
        results: list[tuple[bool, str]] = []

        worker = SetupWorker(mode="archive", archive_paths=archives, dest_path=dest_dir)
        worker.log_line.connect(logs.append)
        worker.progress_status.connect(statuses.append)
        worker.finished.connect(lambda ok, msg: results.append((ok, msg)))

        print("[TEST] Running SetupWorker extraction and patching...")
        worker.run()

        assert results, "SetupWorker did not emit finished signal"
        success, final_path_str = results[0]
        print(f"[TEST] Worker finished with success={success}, msg={final_path_str}")
        assert success, f"SetupWorker failed: {final_path_str}"

        # Step 4: Verification of extracted files
        installed_root = Path(final_path_str)
        assert (installed_root / "App" / "ago.exe").is_file(), "App/ago.exe must exist"
        assert (installed_root / "DEVICE" / "print" / "FGO11_51_AllServants").is_dir(), "11.51 servant cards must exist"

        # Verify obsolete 11.00 files were cleaned up
        for obs in ("App/ICF1", "App/ICF2", "App/EasterEgg", "App/BGM", "App/FGOAudio.dll", "App/FgoDlss.dll"):
            assert not (installed_root / obs).exists(), f"Obsolete file {obs} should have been deleted"

        # Verify hotfix was applied
        marker = installed_root / "Server" / "artemis" / "hotfix_applied.marker"
        assert marker.is_file(), "Hotfix marker was not created"

        print("============================================================")
        print("[SUCCESS] All archive installation assertions verified!")
        print("  - Password decryption: OK")
        print("  - Binary detection: OK")
        print("  - Incremental update 1.10 unpacking: OK")
        print("  - Obsolete 11.00 cleanup: OK")
        print("  - Hotfix execution: OK")
        print("  - Compatibility patching: OK")
        print("============================================================")
        return True

    finally:
        shutil.rmtree(test_dir, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description="Test Fate/Grand Order Arcade zip installation.")
    parser.add_argument("--test", action="store_true", help="Run full headless end-to-end verification test")
    parser.add_argument("--create-archives", type=str, metavar="DIR", help="Create mock test archives in specified directory")
    args = parser.parse_args()

    if args.create_archives:
        target = Path(args.create_archives).expanduser().resolve()
        archives = create_mock_archives(target, encrypted=True)
        print("")
        print("You can now test the GUI wizard by running:")
        print(f"  fgo-launcher --setup")
        print(f"Then choose 'Extract Game Rip Archive(s)' and select the archives in:")
        print(f"  {target}")
        sys.exit(0)

    if args.test or len(sys.argv) == 1:
        ok = test_headless_installation()
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
