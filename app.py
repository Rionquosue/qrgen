"""Run with python app.py."""
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from PIL import Image, ImageTk
from label import PRESETS, INSETS, KINDS, render, to_zpl
from printing import printers, send_raw


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('QRGen')
        from pathlib import Path
        import sys
        if sys.platform == 'win32':
            self.iconbitmap(str(Path(__file__).parent / 'assets' / 'app.ico'))
        self.geometry('700x880')
        self.minsize(650, 800)
        self.text = tk.StringVar(value='Hello Zebra')
        self.kind = tk.StringVar(value='QR')
        self.size = tk.StringVar(value=next(iter(PRESETS)))
        self.swap = tk.BooleanVar()
        self.orientation = tk.StringVar(value='Portrait')
        self.font_size = tk.StringVar(value='8')
        self.dpi = tk.StringVar(value='203')
        self.printer = tk.StringVar()
        self.copies = tk.StringVar(value='1')
        self.status = tk.StringVar()
        self.image = None
        self.busy = False
        self.events = queue.Queue()
        body = ttk.Frame(self, padding=20)
        body.pack(fill='both', expand=True)
        ttk.Label(body, text='Text / caption').pack(anchor='w')
        ttk.Entry(body, textvariable=self.text).pack(fill='x', pady=(4, 14))
        options = ttk.Frame(body)
        options.pack(fill='x')
        for title, var, values in [('Code type', self.kind, KINDS),
                                   ('Stock: width × feed length', self.size, tuple(PRESETS))]:
            box = ttk.Frame(options)
            box.pack(side='left', fill='x', expand=True)
            ttk.Label(box, text=title).pack(anchor='w')
            ttk.Combobox(box, textvariable=var, values=values, state='readonly').pack(fill='x', padx=(0, 10))
        ttk.Checkbutton(body, text='Swap physical width / feed length', variable=self.swap).pack(anchor='w', pady=(8, 2))
        ttk.Label(body, text='Match the loaded roll: width across the printhead, length along the feed.').pack(anchor='w')
        orientation_row = ttk.Frame(body)
        orientation_row.pack(fill='x', pady=8)
        ttk.Label(orientation_row, text='Artwork orientation:').pack(side='left')
        for value in ('Portrait', 'Landscape'):
            ttk.Radiobutton(orientation_row, text=value, value=value,
                            variable=self.orientation).pack(side='left', padx=8)
        typography = ttk.Frame(body)
        typography.pack(fill='x', pady=(0, 8))
        ttk.Label(typography, text='Font size (pt)').pack(side='left')
        ttk.Spinbox(typography, from_=4, to=36, increment=0.5,
                    textvariable=self.font_size, width=5).pack(side='left', padx=8)
        ttk.Label(typography, text='Printer DPI').pack(side='left')
        ttk.Combobox(typography, textvariable=self.dpi, values=('203', '300', '600'),
                     state='readonly', width=5).pack(side='left', padx=8)
        ttk.Label(body, text='GC420d: use 203 DPI. Other values require matching printer hardware.').pack(anchor='w')
        self.preview = tk.Canvas(body, bg='#dce0e4', highlightthickness=0, height=350)
        self.preview.pack(fill='both', expand=True)
        self.preview.bind('<Configure>', lambda _: self.draw_preview())
        ttk.Label(body, text='Loaded-label preview • top to bottom = feed direction').pack(pady=5)
        ttk.Label(body, text='Installed Zebra printer').pack(anchor='w')
        row = ttk.Frame(body)
        row.pack(fill='x', pady=5)
        self.printers_box = ttk.Combobox(row, textvariable=self.printer, state='readonly')
        self.printers_box.pack(side='left', fill='x', expand=True)
        ttk.Button(row, text='Refresh', command=self.refresh).pack(side='left', padx=(8, 0))
        row = ttk.Frame(body)
        row.pack(fill='x', pady=10)
        ttk.Label(row, text='Copies').pack(side='left')
        ttk.Spinbox(row, from_=1, to=999, textvariable=self.copies, width=5).pack(side='left', padx=8)
        self.print_button = ttk.Button(row, text='Print directly', command=self.print_label)
        self.print_button.pack(side='right')
        ttk.Button(row, text='Export ZPL', command=lambda: self.export('zpl')).pack(side='right', padx=5)
        ttk.Button(row, text='Save PNG', command=lambda: self.export('png')).pack(side='right')
        ttk.Label(body, textvariable=self.status, wraplength=600).pack(fill='x', pady=5)
        self.pending = None
        for var in (self.text, self.kind, self.size, self.swap, self.orientation, self.font_size, self.dpi):
            var.trace_add('write', self.schedule)
        self.refresh()
        self.update_label()
        self.after(100, self.poll)

    def refresh(self):
        try:
            names = printers()
            self.printers_box['values'] = names
            if self.printer.get() not in names:
                self.printer.set(next((n for n in names if 'gc420' in n.lower()), ''))
            if not names:
                self.status.set('No printers found. Install the Zebra Windows printer first.')
        except Exception as exc:
            self.status.set(str(exc))

    def schedule(self, *_):
        if self.pending:
            self.after_cancel(self.pending)
        self.pending = self.after(180, self.update_label)
        self.image = None
        self.print_button.state(['disabled'])

    def update_label(self):
        if self.pending:
            self.after_cancel(self.pending)
        self.pending = None
        w, h = PRESETS[self.size.get()]
        if self.swap.get():
            w, h = h, w
        try:
            inset = INSETS.get(self.size.get())
            if inset and self.swap.get():
                raise ValueError('This profile has fixed offsets; turn off Swap.')
            self.image = render(self.text.get(), self.kind.get(), w, h, self.orientation.get(),
                                font_size=float(self.font_size.get()), dpi=int(self.dpi.get()),
                                inset=inset)
            self.status.set(f'Stock: {w:g} in wide × {h:g} in feed length • {self.orientation.get()} • {self.image.width} × {self.image.height} dots')
        except Exception as exc:
            self.image = None
            self.status.set(str(exc))
        self.print_button.state(['!disabled'] if self.image and not self.busy else ['disabled'])
        self.draw_preview()

    def draw_preview(self):
        self.preview.delete('all')
        if self.image:
            cw, ch = self.preview.winfo_width(), self.preview.winfo_height()
            scale = min(max(1, cw-30)/self.image.width, max(1, ch-30)/self.image.height)
            size = (max(1, round(self.image.width*scale)), max(1, round(self.image.height*scale)))
            self.photo = ImageTk.PhotoImage(self.image.resize(size, Image.Resampling.NEAREST))
            self.preview.create_image(cw/2, ch/2, image=self.photo)

    def current_payload(self):
        self.update_label()
        if self.image is None:
            raise ValueError(self.status.get())
        try:
            copies = int(self.copies.get())
        except ValueError:
            raise ValueError('Copies must be an integer from 1 to 999.')
        return to_zpl(self.image, copies)

    def print_label(self):
        if self.busy:
            return
        try:
            payload = self.current_payload()
            name = self.printer.get()
            if not name:
                raise ValueError('Select the installed Zebra printer.')
        except Exception as exc:
            messagebox.showerror('Cannot print', str(exc))
            return
        self.busy = True
        self.print_button.state(['disabled'])
        self.status.set('Sending to printer…')
        def work():
            try:
                job = send_raw(name, payload)
                self.events.put((True, f'Sent to queue: job {job}.'))
            except Exception as exc:
                self.events.put((False, str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def poll(self):
        try:
            ok, text = self.events.get_nowait()
            self.busy = False
            self.status.set(text)
            self.print_button.state(['!disabled'] if self.image else ['disabled'])
            if not ok:
                messagebox.showerror('Print failed', text)
        except queue.Empty:
            pass
        self.after(100, self.poll)

    def export(self, kind):
        try:
            payload = self.current_payload()
            path = filedialog.asksaveasfilename(defaultextension='.'+kind,
                     filetypes=[(kind.upper(), '*.'+kind)])
            if path:
                if kind == 'png':
                    self.image.save(path, dpi=(int(self.dpi.get()), int(self.dpi.get())))
                else:
                    with open(path, 'wb') as f:
                        f.write(payload)
        except Exception as exc:
            messagebox.showerror('Cannot export', str(exc))


def self_test(destination):
    """Exercise bundled rendering, Tk and pywin32 without sending a print job."""
    import json
    from pathlib import Path
    from printing import api
    api()
    for kind, text in [('QR', 'Hello Zebra'), ('Code 128', 'ABC-123'),
                       ('UPC-A', '036000291452'), ('EAN-13', '5901234123457')]:
        image = render(text, kind, 2, 2)
        assert to_zpl(image).startswith(b'^XA')
    window = App()
    window.update()
    assert window.image is not None
    assert window.photo.width() > 0
    for swapped in (False, True):
        window.swap.set(swapped)
        for orientation in ('Portrait', 'Landscape'):
            window.orientation.set(orientation)
            payload = window.current_payload()
            expected = (304, 203) if swapped else (203, 304)
            assert window.image.size == expected
            assert f'^PW{expected[0]}^LL{expected[1]}'.encode() in payload
            window.update()
    window.destroy()
    Path(destination).write_text(json.dumps({'ok': True}), encoding='utf-8')


if __name__ == '__main__':
    import sys
    if len(sys.argv) == 3 and sys.argv[1] == '--self-test':
        self_test(sys.argv[2])
    else:
        App().mainloop()
