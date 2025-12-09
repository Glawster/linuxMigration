#!/usr/bin/env python3

import tkinter as tk
from tkinter import ttk
from tkinter import font as tkfont
import platform

fonts_to_test = [
    ("TkDefaultFont", "Default Tkinter Font"),
    ("Arial", "Arial (common)"),
    ("DejaVu Sans", "DejaVu Sans"),
    ("Liberation Sans", "Liberation Sans"),
    ("Ubuntu", "Ubuntu"),
    ("Helvetica", "Helvetica"),
    ("Sans", "Sans (generic)"),
]

def main():
    root = tk.Tk()
    root.title("Tk font debug")

    print("\n============================================")
    print("TKINTER FONT DEBUG")
    print("============================================")
    print(f"Platform: {platform.system()}")
    print(f"Tk version: {root.tk.eval('info patchlevel')}")
    print("")

    # Show how many font families Tk sees
    families = sorted(tkfont.families())
    print(f"Tk sees {len(families)} font families.")
    print("Example families:", ", ".join(families[:20]), "...")
    print("")

    for name, desc in fonts_to_test:
        f = tkfont.Font(root, family=name, size=10)
        actual = f.actual()
        print(f"Requested: {name:15s} -> actual: {actual}")

    print("============================================\n")

    # simple GUI just to have something on screen
    frame = tk.Frame(root, padx=20, pady=20)
    frame.pack(fill=tk.BOTH, expand=True)

    tk.Label(frame, text="Check terminal output for font resolution info").pack()

    for name, desc in fonts_to_test:
        tk.Button(frame,
                  text=f"The quick brown fox - {desc}",
                  font=(name, 10),
                  width=50,
                  anchor="w").pack(fill=tk.X, pady=2)

    root.mainloop()

if __name__ == "__main__":
    main()

