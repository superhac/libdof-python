#!/usr/bin/env python3
"""
Play a selected frame range from a GIF in a simple on-screen window.

Examples:
  python3 gif_frame_player.py --gif pinupmenu.gif --start 0 --count 29
  python3 gif_frame_player.py --gif pinupmenu.gif --start 10 --count 21 --fps 8 --no-loop
"""

from __future__ import annotations

import argparse
import sys
import tkinter as tk
from pathlib import Path

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Play a selected frame range from a GIF."
    )
    parser.add_argument(
        "--gif",
        default="pinupmenu.gif",
        help="Path to GIF file (default: pinupmenu.gif)",
    )
    parser.add_argument(
        "--start",
        type=int,
        default=0,
        help="Starting frame index (0-based, default: 0)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=0,
        help="How many frames to play (0 = to end of GIF)",
    )
    parser.add_argument(
        "--fps",
        type=float,
        default=10.0,
        help="Playback fps (default: 10.0)",
    )
    parser.add_argument(
        "--no-loop",
        action="store_true",
        help="Play once and stop on the last selected frame",
    )
    parser.add_argument(
        "--scale",
        type=int,
        default=1,
        help="Integer display scale factor (default: 1)",
    )
    return parser.parse_args()


def load_gif_frames(gif_path: Path) -> list[tk.PhotoImage]:
    frames: list[tk.PhotoImage] = []
    idx = 0
    print("Loading GIF frames...", flush=True)
    while True:
        try:
            frame = tk.PhotoImage(file=str(gif_path), format=f"gif -index {idx}")
            frames.append(frame)
            idx += 1
            if idx % 100 == 0:
                print(f"  loaded {idx} frames...", flush=True)
        except tk.TclError:
            break
    return frames


def main() -> int:
    args = parse_args()
    gif_path = Path(args.gif).expanduser()

    if not gif_path.exists():
        print(f"GIF not found: {gif_path}")
        return 1

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        print(f"Could not open a display/window: {exc}")
        print("Run this from a desktop session (X11/Wayland), not a headless shell.")
        return 1

    root.title(f"GIF Player - {gif_path.name}")

    all_frames = load_gif_frames(gif_path)
    total_frames = len(all_frames)
    if total_frames == 0:
        print(f"Could not load GIF frames from: {gif_path}")
        root.destroy()
        return 1

    if args.start < 0 or args.start >= total_frames:
        print(f"start {args.start} out of range (0..{total_frames - 1})")
        print("Tip: use --start 0 --count 0 to play the full GIF.")
        root.destroy()
        return 1

    end_idx = total_frames if args.count <= 0 else min(total_frames, args.start + args.count)
    frames = all_frames[args.start:end_idx]
    if args.scale < 1:
        print("scale must be >= 1")
        root.destroy()
        return 1
    if args.scale > 1:
        frames = [f.zoom(args.scale, args.scale) for f in frames]

    start = args.start
    end = start + len(frames) - 1
    print(f"Loaded: {gif_path}", flush=True)
    print(f"Total GIF frames: {total_frames}", flush=True)
    print(f"Playing frame range: {start}..{end} ({len(frames)} frames)", flush=True)
    print("Opening window now. Press Esc to close.", flush=True)

    panel_w = 256 * args.scale
    panel_h = 32 * args.scale
    root.configure(bg="#111111")
    container = tk.Frame(root, bg="#111111", padx=12, pady=12)
    container.pack(fill="both", expand=True)

    panel = tk.Frame(container, width=panel_w, height=panel_h, bg="#000000", borderwidth=2, relief="solid")
    panel.pack()
    panel.pack_propagate(False)

    label = tk.Label(panel, image=frames[0], borderwidth=0, highlightthickness=0, bg="#000000")
    label.pack(anchor="center")
    root.update_idletasks()
    w = panel_w + 32
    h = panel_h + 32
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    x = max(0, (sw - w) // 2)
    y = max(0, (sh - h) // 2)
    root.geometry(f"{w}x{h}+{x}+{y}")
    try:
        root.lift()
        root.attributes("-topmost", True)
        root.after(600, lambda: root.attributes("-topmost", False))
    except tk.TclError:
        pass

    loop = not args.no_loop
    index = 0
    delay = max(1, int(1000.0 / max(args.fps, 0.001)))

    def next_frame() -> None:
        nonlocal index
        label.configure(image=frames[index])

        if index == len(frames) - 1:
            if not loop:
                return
            index = 0
        else:
            index += 1

        root.after(delay, next_frame)

    root.after(1, next_frame)
    root.bind("<Escape>", lambda _e: root.destroy())
    root.bind("q", lambda _e: root.destroy())
    root.bind("<space>", lambda _e: root.destroy())
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
