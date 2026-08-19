#!/usr/bin/env python3
"""
zenid_cli.py
------------
Dual-Mode (TUI / Headless CLI) and Multiprocessing Launcher for ZenID.
"""

import argparse
import concurrent.futures
import curses
import os
import sys

# Dynamic import handling for package mode vs standalone execution
try:
    from .zenid_core import embed as embed_img, detect as detect_img
    from .zenid_text import embed_text, detect_text
    from .zenid_audio import embed_audio, detect_audio
except ImportError:
    from zenid_core import embed as embed_img, detect as detect_img
    from zenid_text import embed_text, detect_text
    from zenid_audio import embed_audio, detect_audio


# ==========================================
# MULTIPROCESSING BATCH ENGINE
# ==========================================

def _batch_worker(task: tuple) -> tuple[str, bool, str]:
    """Worker function for parallel folder processing."""
    mode, domain, in_path, out_path, key, author = task
    try:
        if domain == "image":
            if mode == "embed":
                embed_img(in_path, out_path, key, author)
            else:
                return in_path, True, str(detect_img(in_path, key))
        elif domain == "text":
            if mode == "embed":
                wm_txt = embed_text(in_path, key, author)
                if out_path:
                    with open(out_path, "w", encoding="utf-8") as f:
                        f.write(wm_txt)
            else:
                return in_path, True, str(detect_text(in_path, key))
        elif domain == "audio":
            if mode == "embed":
                embed_audio(in_path, out_path, key, author)
            else:
                return in_path, True, str(detect_audio(in_path, key))
        return in_path, True, "Success"
    except Exception as e:
        return in_path, False, str(e)


def run_batch(domain: str, mode: str, input_dir: str, output_dir: str, key: str, author: str) -> None:
    """Parallel processing for media directories."""
    if not os.path.exists(input_dir):
        print(f"[Error] Input directory '{input_dir}' does not exist.")
        return

    if mode == "embed" and output_dir:
        os.makedirs(output_dir, exist_ok=True)

    files = [os.path.join(input_dir, f) for f in os.listdir(input_dir) if os.path.isfile(os.path.join(input_dir, f))]
    tasks = []

    for f in files:
        out_f = os.path.join(output_dir, os.path.basename(f)) if output_dir else ""
        tasks.append((mode, domain, f, out_f, key, author))

    print(f"[*] Processing {len(tasks)} files using multiprocessing pool...")
    with concurrent.futures.ProcessPoolExecutor() as executor:
        results = list(executor.map(_batch_worker, tasks))

    for path, success, msg in results:
        status = "SUCCESS" if success else "FAILED"
        print(f"[{status}] {os.path.basename(path)} -> {msg}")


# ==========================================
# CURSES TUI IMPLEMENTATION
# ==========================================

def draw_menu(stdscr, title: str, options: list[str], selected_idx: int) -> None:
    stdscr.clear()
    h, w = stdscr.getmaxyx()
    banner = f"=== {title} ==="
    stdscr.addstr(1, max(0, (w - len(banner)) // 2), banner, curses.A_BOLD | curses.color_pair(1))
    stdscr.addstr(2, max(0, (w - 44) // 2), "Use UP/DOWN Arrows to Navigate, ENTER to Select", curses.A_DIM)

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
        elif key in (10, 13):
            return selected


def main_curses(stdscr) -> None:
    curses.curs_set(0)
    curses.start_color()
    curses.init_pair(1, curses.COLOR_CYAN, curses.COLOR_BLACK)
    curses.init_pair(2, curses.COLOR_GREEN, curses.COLOR_BLACK)

    while True:
        domain_idx = run_menu(stdscr, "ZENID MULTI-MODAL SUITE v8.0", ["Image Watermarking", "Text Watermarking", "Audio Watermarking", "Exit"])
        if domain_idx == 3:
            break

        action_idx = run_menu(stdscr, "SELECT ACTION", ["Embed Watermark", "Detect / Verify Watermark", "Back"])
        if action_idx == 2:
            continue

        if domain_idx == 0:
            if action_idx == 0:
                inp = prompt_input(stdscr, "Enter path to INPUT image:")
                out = prompt_input(stdscr, "Enter path for OUTPUT image:")
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
                    show_result(stdscr, "DETECTION RESULT", [f"Status: {res['message']}", f"Author: {res.get('author', 'N/A')}", f"Fingerprint: {res.get('fingerprint', 'N/A')}"])
                except Exception as e:
                    show_result(stdscr, "ERROR", [str(e)])

        elif domain_idx == 1:
            if action_idx == 0:
                txt_input = prompt_input(stdscr, "Enter plain text OR text file path:")
                key = prompt_input(stdscr, "Enter secret encryption key:")
                author = prompt_input(stdscr, "Enter author name:")
                out_path = prompt_input(stdscr, "Enter output file path (or ENTER for raw output):")
                try:
                    wm_txt = embed_text(txt_input, key, author)
                    if out_path.strip():
                        with open(out_path.strip(), "w", encoding="utf-8") as f:
                            f.write(wm_txt)
                        show_result(stdscr, "SUCCESS", [f"Watermarked text saved to: {out_path}"])
                    else:
                        show_result(stdscr, "WATERMARKED TEXT OUTPUT", [wm_txt])
                except Exception as e:
                    show_result(stdscr, "ERROR", [str(e)])
            else:
                txt_input = prompt_input(stdscr, "Enter text file path OR paste text:")
                key = prompt_input(stdscr, "Enter secret key:")
                try:
                    res = detect_text(txt_input, key)
                    show_result(stdscr, "TEXT VERIFICATION RESULT", [f"Status: {res['message']}", f"Author: {res.get('author', 'N/A')}"])
                except Exception as e:
                    show_result(stdscr, "ERROR", [str(e)])

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
                    show_result(stdscr, "AUDIO VERIFICATION RESULT", [f"Status: {res['message']}", f"Author: {res.get('author', 'N/A')}"])
                except Exception as e:
                    show_result(stdscr, "ERROR", [str(e)])


# ==========================================
# HEADLESS CLI ARGUMENT PARSER
# ==========================================

def main() -> None:
    """Main CLI entrypoint handling interactive TUI and headless commands."""
    if len(sys.argv) == 1:
        try:
            curses.wrapper(main_curses)
        except KeyboardInterrupt:
            sys.exit(0)
        return

    parser = argparse.ArgumentParser(description="ZenID Multi-Modal Watermarking Engine")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Embed subcommand
    embed_p = subparsers.add_parser("embed", help="Embed a watermark into a file")
    embed_p.add_argument("-t", "--type", choices=["image", "text", "audio"], required=True, help="Media domain")
    embed_p.add_argument("-i", "--input", required=True, help="Input file path")
    embed_p.add_argument("-o", "--output", required=True, help="Output file path")
    embed_p.add_argument("-k", "--key", required=True, help="Secret key")
    embed_p.add_argument("-a", "--author", required=True, help="Author payload")

    # Detect subcommand
    detect_p = subparsers.add_parser("detect", help="Detect watermark from a file")
    detect_p.add_argument("-t", "--type", choices=["image", "text", "audio"], required=True, help="Media domain")
    detect_p.add_argument("-i", "--input", required=True, help="Input file path")
    detect_p.add_argument("-k", "--key", required=True, help="Secret key")

    # Batch subcommand
    batch_p = subparsers.add_parser("batch", help="Run parallel batch processing on a directory")
    batch_p.add_argument("-m", "--mode", choices=["embed", "detect"], required=True)
    batch_p.add_argument("-t", "--type", choices=["image", "text", "audio"], required=True)
    batch_p.add_argument("-i", "--input-dir", required=True, help="Input directory")
    batch_p.add_argument("-o", "--output-dir", help="Output directory (required for embed)")
    batch_p.add_argument("-k", "--key", required=True, help="Secret key")
    batch_p.add_argument("-a", "--author", default="Unknown", help="Author payload")

    args = parser.parse_args()

    if args.command == "embed":
        if args.type == "image":
            embed_img(args.input, args.output, args.key, args.author)
        elif args.type == "text":
            res = embed_text(args.input, args.key, args.author)
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(res)
        elif args.type == "audio":
            embed_audio(args.input, args.output, args.key, args.author)
        print(f"[+] Successfully embedded {args.type} watermark into: {args.output}")

    elif args.command == "detect":
        if args.type == "image":
            print(detect_img(args.input, args.key))
        elif args.type == "text":
            print(detect_text(args.input, args.key))
        elif args.type == "audio":
            print(detect_audio(args.input, args.key))

    elif args.command == "batch":
        run_batch(args.type, args.mode, args.input_dir, args.output_dir, args.key, args.author)


if __name__ == "__main__":
    main()