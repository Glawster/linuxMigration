import tkinter as tk
from tkinter import font

root = tk.Tk()
root.title("Tkinter font test")

# IMPORTANT: change the default font *before* creating widgets
default_font = font.nametofont("TkDefaultFont")
default_font.configure(family="DejaVu Sans Mono", size=18)

tk.Label(root, text="This should be DejaVu Sans Mono 18").pack(padx=20, pady=20)
tk.Button(root, text="Button text should match label").pack(pady=10)

root.mainloop()

