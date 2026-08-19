"""
ZenID Package Initialization & Environment Auto-Configurator.
"""

import os
import sys
import stat
import subprocess

# Import modules from your local package
try:
    from .zenid_text import embed_text, detect_text
    from .zenid_core import embed_image, detect_image
    from .zenid_audio import embed_audio, detect_audio
    from .zenid_cli import main as cli_main
except ImportError:
    # Fallback for flat layout
    try:
        from zenid_text import embed_text, detect_text
        from zenid_core import embed_image, detect_image
        from zenid_audio import embed_audio, detect_audio
        from zenid_cli import main as cli_main
    except ImportError:
        cli_main = None


def zenidmain():
    """Main CLI entrypoint function."""
    if cli_main:
        cli_main()
    else:
        print("[zenid] Error: CLI module could not be loaded.")


def env_zenid():
    """Automatically generates system launchers (.bat / shell script) and registers package to PATH."""
    package_dir = os.path.dirname(os.path.abspath(__file__))

    if sys.platform == "win32":
        # ── Windows: create .bat launcher ─────────────────────────
        launcher_path = os.path.join(package_dir, "zenid.bat")
        content = f'@echo off\n"{sys.executable}" -c "import zenid; zenid.zenidmain()" %*\n'
        try:
            with open(launcher_path, "w") as f:
                f.write(content)
        except PermissionError:
            print(f"[zenid] Could not write launcher to {launcher_path}. Try running as administrator.")

        # ── Windows: add to PATH via registry ────────────────────
        try:
            import winreg
            reg_key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Environment",
                0,
                winreg.KEY_READ | winreg.KEY_WRITE,
            )
            try:
                current_path, _ = winreg.QueryValueEx(reg_key, "PATH")
            except FileNotFoundError:
                current_path = ""
            path_entries = [p.strip() for p in current_path.split(";") if p.strip()]
            if package_dir not in path_entries:
                new_path = current_path.rstrip(";") + ";" + package_dir
                winreg.SetValueEx(reg_key, "PATH", 0, winreg.REG_EXPAND_SZ, new_path)
            winreg.CloseKey(reg_key)
            
            # Broadcast WM_SETTINGCHANGE so the new PATH takes effect immediately
            subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "Add-Type -Namespace Win32 -Name NativeMethods "
                 "-MemberDefinition '[DllImport(\"user32.dll\")]public static extern "
                 "IntPtr SendMessageTimeout(IntPtr hWnd,uint Msg,UIntPtr wParam,"
                 "string lParam,uint fuFlags,uint uTimeout,out UIntPtr lpdwResult);';"
                 "$r=[UIntPtr]::Zero;"
                 "[Win32.NativeMethods]::SendMessageTimeout([IntPtr]0xffff,0x001A,"
                 "[UIntPtr]::Zero,'Environment',2,5000,[ref]$r)|Out-Null"],
                capture_output=True,
            )
        except Exception as e:
            print(f"[zenid] Could not modify PATH automatically: {e}")
            print(f"[zenid] Add this directory to PATH manually: {package_dir}")

    else:
        # ── macOS / Linux: create shell script launcher ───────────
        launcher_path = os.path.join(package_dir, "zenid")
        content = f'#!/bin/sh\nexec "{sys.executable}" -c "import zenid; zenid.zenidmain()" "$@"\n'
        try:
            with open(launcher_path, "w") as f:
                f.write(content)
            
            st = os.stat(launcher_path)
            os.chmod(launcher_path, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        except PermissionError:
            print(f"[zenid] Could not write launcher to {launcher_path}. Try running with sudo.")
            return

        # ── macOS / Linux: add to PATH via shell rc file ─────────
        if package_dir in os.environ.get("PATH", "").split(os.pathsep):
            return

        if sys.platform == "darwin":
            rc_files = [os.path.expanduser("~/.zshrc"), os.path.expanduser("~/.bash_profile")]
        else:
            rc_files = [os.path.expanduser("~/.bashrc"), os.path.expanduser("~/.profile")]

        export_line = f'\nexport PATH="{package_dir}:$PATH"  # added by zenid\n'
        rc_file = next((f for f in rc_files if os.path.exists(f)), rc_files[0])

        try:
            with open(rc_file, "r") as f:
                existing = f.read()
            if package_dir not in existing:
                with open(rc_file, "a") as f:
                    f.write(export_line)
                print(f"[zenid] Added to PATH in {rc_file}. Restart your shell or run: source {rc_file}")
        except Exception as e:
            print(f"[zenid] Could not modify {rc_file}: {e}")
            print(f"[zenid] Add this to PATH manually: {package_dir}")

# Automatically execute PATH configuration on module import
env_zenid()
