#!/usr/bin/env python3
"""
zenid_cli.py
------------
Interactive Terminal UI for ZenID Watermarking Engine.
"""

import curses
import os
import sys

# Dynamic import handling for package mode vs standalone execution
try:
    from .zenid_core import embed as embed_img, detect as detect_img
    from .zenid_text import embed_text, detect_text
    from .zenid_audio import embed_audio, detect_audio
except ImportError:
    try:
        from zenid.zenid_core import embed as embed_img, detect as detect_img
        from zenid.zenid_text import embed_text, detect_text
        from zenid.zenid_audio import embed_audio, detect_audio
    except ImportError:
        from zenid_core import embed as embed_img, detect as detect_img
        from zenid_text import embed_text, detect_text
        from zenid_audio import embed_audio, detect_audio


def draw_menu(stdscr, title: str, options: list[str], selected_idx: int) -> None:
    stdscr.clear()
    h, w = stdscr.getmaxyx()
    
    # Header Banner
    banner = f"=== {title} ==="
    stdscr.addstr(1, max(0, (w - len(banner)) // 2), banner, curses.A_BOLD | curses.color_pair(1))
    stdscr.addstr(2, max(0, (w - 38) // 2), "Use UP/DOWN Arrows to Navigate, ENTER to Select", curses.A_DIM)
    
    for idx, option in enumerate(options):
        x = max(2, (w - len(option) - 4) // 2)
        y = 4 + idx
        if idx == selected_idx:
            stdscr.addstr(y, x, f"> {option} <", curses.A_REVERSE | curses.color_pair(2))
        else:
            stdscr.addstr(y, x, f"  {option}  ")
            
    stdscr.refresh()


def prompt_input(stdscr, prompt_text: str) -> str:
    stdscr.clear()
    stdscr.addstr(2, 2, prompt_text, curses.A_BOLD)
    stdscr.addstr(4, 2, "> ")
    curses.echo()
    curses.curs_set(1)
    inp = stdscr.getstr(4, 4, 256).decode('utf-8').strip(' \t\n\r')
    curses.noecho()
    curses.curs_set(0)
    return inp


def show_result(stdscr, title: str, details: list[str]) -> None:
    stdscr.clear()
    stdscr.addstr(1, 2, f"=== {title} ===", curses.A_BOLD | curses.color_pair(1))
    for i, line in enumerate(details):
        stdscr.addstr(3 + i, 4, line)
    stdscr.addstr(5 + len(details), 2, "Press any key to continue...", curses.A_DIM)
    stdscr.refresh()
    stdscr.getch()


def run_menu(stdscr, title: str, options: list[str]) -> int:
    selected = 0
    while True:
        draw_menu(stdscr, title, options, selected)
        key = stdscr.getch()
        if key == curses.KEY_UP:
            selected = (selected - 1) % len(options)
        elif key == curses.KEY_DOWN:
            selected = (selected + 1) % len(options)
        elif key in (10, 13):  # Enter key
            return selected


def main_curses(stdscr) -> None:
    curses.curs_set(0)
    curses.start_color()
    curses.init_pair(1, curses.COLOR_CYAN, curses.COLOR_BLACK)
    curses.init_pair(2, curses.COLOR_GREEN, curses.COLOR_BLACK)
    
    while True:
        domain_idx = run_menu(stdscr, "ZENID MULTI-MODAL SUITE", ["Image Watermarking", "Text Watermarking", "Audio Watermarking", "Exit"])
        
        if domain_idx == 3:  # Exit
            break
            
        action_idx = run_menu(stdscr, "SELECT ACTION", ["Embed Watermark", "Detect / Verify Watermark", "Back"])
        if action_idx == 2:
            continue
            
        # Image Mode
        if domain_idx == 0:
            if action_idx == 0:
                inp = prompt_input(stdscr, "Enter path to INPUT image (e.g. input/1.jpg):")
                out = prompt_input(stdscr, "Enter path for OUTPUT image (e.g. output/2.jpg):")
                key = prompt_input(stdscr, "Enter secret encryption key:")
                author = prompt_input(stdscr, "Enter author name:")
                try:
                    embed_img(inp, out, key, author)
                    show_result(stdscr, "SUCCESS", [f"Image watermarked and saved to: {out}"])
                except Exception as e:
                    show_result(stdscr, "ERROR", [str(e)])
            else:
                img_path = prompt_input(stdscr, "Enter path to image to verify:")
                key = prompt_input(stdscr, "Enter secret key:")
                try:
                    res = detect_img(img_path, key)
                    show_result(stdscr, "DETECTION RESULT", [
                        f"Status: {res['message']}",
                        f"Author: {res.get('author', 'N/A')}",
                        f"Fingerprint: {res.get('fingerprint', 'N/A')}"
                    ])
                except Exception as e:
                    show_result(stdscr, "ERROR", [str(e)])

        # Text Mode
        elif domain_idx == 1:
            if action_idx == 0:
                txt_input = prompt_input(stdscr, "Enter plain text OR text file path (e.g. input.txt):")
                key = prompt_input(stdscr, "Enter secret encryption key:")
                author = prompt_input(stdscr, "Enter author name:")
                out_path = prompt_input(stdscr, "Enter output file path to save (e.g. output.txt or ENTER to display):")
                try:
                    wm_txt = embed_text(txt_input, key, author)
                    if out_path.strip():
                        with open(out_path.strip(), "w", encoding="utf-8") as f:
                            f.write(wm_txt)
                        show_result(stdscr, "SUCCESS", [f"Watermarked text saved to: {out_path}"])
                    else:
                        show_result(stdscr, "WATERMARKED TEXT OUTPUT", [wm_txt, "", "(Invisible payload attached)"])
                except Exception as e:
                    show_result(stdscr, "ERROR", [str(e)])
            else:
                txt_input = prompt_input(stdscr, "Enter text file path (e.g. output.txt) OR paste text:")
                key = prompt_input(stdscr, "Enter secret key:")
                try:
                    res = detect_text(txt_input, key)
                    show_result(stdscr, "TEXT VERIFICATION RESULT", [
                        f"Status: {res['message']}",
                        f"Author: {res.get('author', 'N/A')}"
                    ])
                except Exception as e:
                    show_result(stdscr, "ERROR", [str(e)])

        # Audio Mode
        elif domain_idx == 2:
            if action_idx == 0:
                inp = prompt_input(stdscr, "Enter INPUT .wav file path:")
                out = prompt_input(stdscr, "Enter OUTPUT .wav file path:")
                key = prompt_input(stdscr, "Enter secret encryption key:")
                author = prompt_input(stdscr, "Enter author name:")
                try:
                    embed_audio(inp, out, key, author)
                    show_result(stdscr, "SUCCESS", [f"Audio watermarked and saved to: {out}"])
                except Exception as e:
                    show_result(stdscr, "ERROR", [str(e)])
            else:
                inp = prompt_input(stdscr, "Enter .wav file path to inspect:")
                key = prompt_input(stdscr, "Enter secret key:")
                try:
                    res = detect_audio(inp, key)
                    show_result(stdscr, "AUDIO VERIFICATION RESULT", [
                        f"Status: {res['message']}",
                        f"Author: {res.get('author', 'N/A')}"
                    ])
                except Exception as e:
                    show_result(stdscr, "ERROR", [str(e)])


def main() -> None:
    """Public launcher function called by __init__.py or CLI entrypoint."""
    try:
        curses.wrapper(main_curses)
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()