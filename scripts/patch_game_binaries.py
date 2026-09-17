#!/usr/bin/env python3
"""
Fate/Grand Order Arcade - Binary Compatibility Patcher for Linux & Modern PC GPUs.

This script patches the original Sega arcade binaries for execution on Linux/Wine:
1. ago.exe:
   - Site 1 (0x27CB20): Bypasses arcade hardware touchscreen & window gesture lock (SetWindowFeedbackSetting).
   - Site 2 (0xC078F1): Hooks unsafe device context dereference and detours to code cave.
   - Site 3 (0xC1CC03): Replaces unsafe struct accessor with safe null-checked accessor.
   - Site 4 (0x12BB040): Code cave implementation providing null safety guard for graphics passes.
2. fgozh.dll:
   - Hook Loop (0x14FB0): Truncates MinHook NT file hook loop from 5 APIs to 4, bypassing
     NtQueryInformationByName which is absent in Wine's ntdll.dll and prevents DLL injection.
3. GPU Shim Verification:
   - Verifies opengl32.dll (WGL attribute stripper) and opengl32real.dll (real OpenGL proxy).

Supports --check (dry run), --patch (default), and --revert.
Zero hardcoded paths. Safe and idempotent.
"""

import argparse
import os
import shutil
import sys
from typing import Dict, List, Optional, Tuple

# ------------------------------------------------------------------------------
# Patch Definitions
# ------------------------------------------------------------------------------

AGO_PATCHES = [
    {
        "name": "Arcade Touchscreen / Window Lock Bypass",
        "offset": 0x27CB20,
        "original": b"\x48",
        "patched": b"\xC3",
        "description": "Replaces SetWindowFeedbackSetting function prologue with immediate RET (0xC3) to prevent window setup failure on non-arcade monitors.",
    },
    {
        "name": "Graphics Context Detour Jump",
        "offset": 0xC078F1,
        "original": b"\x48\x8B\x07\x8B\x4B\x1C\x8B\x50\x1C\xFF\x15\x00\x3C\x08\x01",
        "patched": b"\xE9\x4A\x37\x6B\x00" + b"\x90" * 10,
        "description": "Detours unchecked indirect call into code cave (0x12BB040) to prevent NULL pointer dereference (access violation 0x1C).",
    },
    {
        "name": "Safe Object Accessor Guard",
        "offset": 0xC1CC03,
        "original": b"\x8B\x40\x20\xC3" + b"\xCC" * 9,
        "patched": b"\x48\x85\xC0\x74\x04\x8B\x40\x20\xC3\x31\xC0\xC3\x90",
        "description": "Inserts TEST RAX, RAX check. Returns 0 if render object is NULL instead of dereferencing [rax+0x20] and crashing.",
    },
    {
        "name": "Graphics Code Cave Implementation",
        "offset": 0x12BB040,
        "original": b"\x00" * 25,
        "patched": b"\x48\x8B\x07\x48\x85\xC0\x74\x0C\x8B\x4B\x1C\x8B\x50\x1C\xFF\x15\xAC\x04\x9D\x00\xE9\xA7\xC8\x94\xFF",
        "description": "Safety routine inside .text padding: validates context pointer before dereference, then jumps back to 0xC07900.",
    },
]

FGOZH_PATCHES = [
    {
        "name": "Wine MinHook Loop Truncation",
        "offset": 0x14FB0,
        "original": b"\x48\x8D\x45\x40",  # LEA RAX, [RBP+0x40] (5 functions)
        "patched": b"\x48\x8D\x45\x20",   # LEA RAX, [RBP+0x20] (4 functions)
        "description": "Truncates NT hook loop to 4 functions. Bypasses NtQueryInformationByName which is missing in Wine ntdll.dll.",
    }
]


# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------

def resolve_app_dir(provided_path: Optional[str] = None) -> Optional[str]:
    """Resolves the App directory containing ago.exe."""
    candidates = []
    if provided_path:
        candidates.extend([
            provided_path,
            os.path.join(provided_path, "App"),
            os.path.abspath(provided_path),
        ])

    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates.extend([
        os.getcwd(),
        os.path.join(os.getcwd(), "App"),
        os.path.abspath(os.path.join(script_dir, "..", "App")),
        os.path.abspath(os.path.join(script_dir, "App")),
    ])

    for c in candidates:
        if os.path.isdir(c) and os.path.isfile(os.path.join(c, "ago.exe")):
            return os.path.abspath(c)
        if os.path.isdir(c) and os.path.isfile(os.path.join(c, "App", "ago.exe")):
            return os.path.abspath(os.path.join(c, "App"))

    return None


def inspect_patch(file_path: str, patch_info: dict) -> str:
    """Returns 'patched', 'original', or 'mismatch' for a given patch definition."""
    offset = patch_info["offset"]
    orig = patch_info["original"]
    pat = patch_info["patched"]
    size = len(orig)

    if not os.path.isfile(file_path):
        return "missing"

    file_size = os.path.getsize(file_path)
    if offset + size > file_size:
        return "out_of_bounds"

    with open(file_path, "rb") as f:
        f.seek(offset)
        current = f.read(size)

    if current == pat:
        return "patched"
    elif current == orig:
        return "original"
    else:
        return "mismatch"


def apply_patch(file_path: str, patch_info: dict) -> bool:
    """Applies a patch to the target file at the specified offset."""
    offset = patch_info["offset"]
    pat = patch_info["patched"]
    with open(file_path, "r+b") as f:
        f.seek(offset)
        f.write(pat)
        f.flush()
    return True


def revert_patch(file_path: str, patch_info: dict) -> bool:
    """Reverts a patch to original bytes at the specified offset."""
    offset = patch_info["offset"]
    orig = patch_info["original"]
    with open(file_path, "r+b") as f:
        f.seek(offset)
        f.write(orig)
        f.flush()
    return True


# ------------------------------------------------------------------------------
# Core Actions
# ------------------------------------------------------------------------------

def process_file(file_path: str, patches: List[dict], mode: str = "patch") -> Tuple[int, int, int]:
    """
    Processes patches for a single binary.
    mode: 'check', 'patch', or 'revert'
    Returns: (count_patched, count_original, count_mismatch)
    """
    rel_name = os.path.basename(file_path)
    print(f"\n============================================================")
    print(f"Target Binary: {rel_name} ({file_path})")
    print(f"============================================================")

    if not os.path.isfile(file_path):
        print(f"  [ERROR] File not found: {file_path}")
        return 0, 0, len(patches)

    orig_backup = file_path + ".orig"

    # Analyze current patch states
    states = [inspect_patch(file_path, p) for p in patches]
    c_patched = states.count("patched")
    c_orig = states.count("original")
    c_mismatch = states.count("mismatch")

    for p, state in zip(patches, states):
        status_tag = {
            "patched": "[PATCHED] ",
            "original": "[UNPATCHED]",
            "mismatch": "[MISMATCH] ",
        }.get(state, "[UNKNOWN]  ")
        print(f"  {status_tag} 0x{p['offset']:07X}: {p['name']}")
        print(f"             -> {p['description']}")

    if mode == "check":
        return c_patched, c_orig, c_mismatch

    if mode == "patch":
        if c_mismatch > 0:
            print(f"\n  [ABORT] {c_mismatch} patch sites have unexpected bytes. File might be corrupted or an unknown revision.")
            return c_patched, c_orig, c_mismatch

        if c_patched == len(patches):
            print(f"\n  [OK] Binary is already fully patched. No changes needed.")
            return c_patched, c_orig, c_mismatch

        # Create safety backup if not exists
        if not os.path.exists(orig_backup):
            print(f"\n  [BACKUP] Creating pristine backup: {os.path.basename(orig_backup)}")
            shutil.copy2(file_path, orig_backup)
        else:
            print(f"\n  [BACKUP] Existing backup preserved: {os.path.basename(orig_backup)}")

        # Apply patches
        applied = 0
        for p, state in zip(patches, states):
            if state == "original":
                apply_patch(file_path, p)
                applied += 1
                print(f"  [APPLIED] Patch site at 0x{p['offset']:X} -> {p['name']}")

        print(f"  [SUCCESS] {applied} patch(es) successfully applied to {rel_name}.")

    elif mode == "revert":
        if os.path.exists(orig_backup):
            print(f"\n  [RESTORE] Restoring from pristine backup {os.path.basename(orig_backup)}...")
            shutil.copy2(orig_backup, file_path)
            print(f"  [SUCCESS] Restored clean original {rel_name}.")
        else:
            reverted = 0
            for p, state in zip(patches, states):
                if state == "patched":
                    revert_patch(file_path, p)
                    reverted += 1
            print(f"  [SUCCESS] {reverted} patch(es) reverted in-place.")

    # Re-verify
    new_states = [inspect_patch(file_path, p) for p in patches]
    return new_states.count("patched"), new_states.count("original"), new_states.count("mismatch")


def verify_gpu_shims(app_dir: str):
    """Verifies presence of the OpenGL WGL proxy shim."""
    print(f"\n============================================================")
    print("GPU Compatibility Stack Verification")
    print(f"============================================================")

    gl_shim = os.path.join(app_dir, "opengl32.dll")
    gl_real = os.path.join(app_dir, "opengl32real.dll")

    if os.path.isfile(gl_shim):
        sz = os.path.getsize(gl_shim)
        print(f"  [OK] opengl32.dll (WGL Attribute Stripper) present ({sz} bytes)")
    else:
        print(f"  [WARNING] opengl32.dll is missing in {app_dir}!")

    if os.path.isfile(gl_real):
        sz = os.path.getsize(gl_real)
        print(f"  [OK] opengl32real.dll (Host Driver Proxy) present ({sz} bytes)")
    else:
        print(f"  [WARNING] opengl32real.dll is missing in {app_dir}!")


# ------------------------------------------------------------------------------
# Entry Point
# ------------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Binary Compatibility Patcher for Fate/Grand Order Arcade on Linux/Wine."
    )
    parser.add_argument(
        "target_dir",
        nargs="?",
        default=None,
        help="Path to FGOA root or App directory (auto-detected if omitted).",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--patch",
        action="store_true",
        default=True,
        help="Apply compatibility patches to ago.exe and translation DLLs (default).",
    )
    group.add_argument(
        "--check",
        action="store_true",
        help="Inspect binary status without making any file modifications.",
    )
    group.add_argument(
        "--revert",
        action="store_true",
        help="Revert modified binaries back to original clean state.",
    )

    args = parser.parse_args()
    mode = "check" if args.check else ("revert" if args.revert else "patch")

    print("==================================================================")
    print("Fate/Grand Order Arcade - Binary Compatibility Patcher")
    print("==================================================================")
    print(f"Operating Mode: {mode.upper()}")

    app_dir = resolve_app_dir(args.target_dir)
    if not app_dir:
        print("\n[FATAL] Could not locate the FGOA 'App' directory.")
        print("Please provide the path as an argument, e.g.:")
        print("  python3 patch_game_binaries.py /path/to/FGOA/App")
        sys.exit(1)

    print(f"Detected App Directory: {app_dir}")

    # 1. Process ago.exe
    ago_path = os.path.join(app_dir, "ago.exe")
    process_file(ago_path, AGO_PATCHES, mode=mode)

    # 2. Process fgozh.dll (Check both App/zh/fgozh.dll and App/fgozh.dll)
    candidate_dlls = [
        os.path.join(app_dir, "zh", "fgozh.dll"),
        os.path.join(app_dir, "fgozh.dll"),
    ]
    for dll in candidate_dlls:
        if os.path.isfile(dll):
            process_file(dll, FGOZH_PATCHES, mode=mode)

    # 3. Check GPU Shims
    verify_gpu_shims(app_dir)

    print("\n[ALL DONE] Operations completed successfully.\n")


if __name__ == "__main__":
    main()
