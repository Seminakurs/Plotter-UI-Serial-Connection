"""
3D Printer Controller - Tkinter GUI
Supports: Artillery Sidewinder X1 (or any Marlin-based printer) via USB serial
Features:
 - Connect / Disconnect
 - Jog buttons for X, Y, Z (relative moves)
 - Step size and feedrate control
 - Home, Motors On/Off, Emergency Stop
 - Live position readout (polls M114)
 - Simple command console

Dependencies:
 - pyserial

Install:
 pip install pyserial

Run:
 python 3D_Printer_Controller_Tkinter.py

Safety:
 - Use with printer powered and connected via USB.
 - Home (G28) before large moves. Be careful with Z moves.
 - Emergency stop uses M112 (firmware E-STOP) and will require a reset on the printer.

"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import serial
import serial.tools.list_ports
import threading
import time
import queue

POLL_INTERVAL = 1.0  # seconds between position polls

class PrinterController:
    def __init__(self):
        self.ser = None
        self.lock = threading.Lock()
        self.alive = threading.Event()
        self.read_thread = None
        self.poll_thread = None
        self.response_q = queue.Queue()

    def list_ports(self):
        return [p.device for p in serial.tools.list_ports.comports()]

    def connect(self, port, baud=115200, timeout=1):
        with self.lock:
            if self.ser and self.ser.is_open:
                return True
            try:
                self.ser = serial.Serial(port, baud, timeout=timeout)
                # give firmware a moment to reset/uploader
                time.sleep(2)
                self.alive.set()
                self.read_thread = threading.Thread(target=self._read_loop, daemon=True)
                self.read_thread.start()
                self.poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
                self.poll_thread.start()
                return True
            except Exception as e:
                print('Connect error:', e)
                self.ser = None
                return False

    def disconnect(self):
        with self.lock:
            if self.ser:
                try:
                    self.alive.clear()
                    # Give threads a moment to stop
                    time.sleep(0.05)
                    self.ser.flush()
                    self.ser.close()
                except Exception:
                    pass
                finally:
                    self.ser = None

    def _read_loop(self):
        while self.alive.is_set() and self.ser and self.ser.is_open:
            try:
                line = self.ser.readline()
                if not line:
                    continue
                text = line.decode(errors='ignore').strip()
                # push to response queue
                self.response_q.put(text)
            except Exception:
                break

    def _poll_loop(self):
        # periodically ask printer for position (M114)
        while self.alive.is_set() and self.ser and self.ser.is_open:
            try:
                self.send_line('M114')
            except Exception:
                pass
            time.sleep(POLL_INTERVAL)

    def send_line(self, line):
        with self.lock:
            if not self.ser or not self.ser.is_open:
                raise RuntimeError('Not connected')
            # ensure newline
            self.ser.write((line + '\n').encode())
            self.ser.flush()

    def get_response_nowait(self):
        lines = []
        while True:
            try:
                lines.append(self.response_q.get_nowait())
            except queue.Empty:
                break
        return lines

    def close(self):
        self.disconnect()


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('3D Printer Control - Tkinter')
        self.geometry('780x540')
        self.controller = PrinterController()
        self.create_widgets()
        # start with disabled jog widgets until connected
        self.set_disconnected()
        self.after(200, self._periodic_ui_update)

    def create_widgets(self):
        frm_top = ttk.Frame(self)
        frm_top.pack(fill='x', padx=8, pady=6)

        ttk.Label(frm_top, text='Serial Port:').pack(side='left')
        self.port_cb = ttk.Combobox(frm_top, values=self.controller.list_ports(), width=18)
        self.port_cb.pack(side='left', padx=4)

        ttk.Button(frm_top, text='Refresh', command=self.refresh_ports).pack(side='left')
        ttk.Label(frm_top, text='Baud:').pack(side='left', padx=(8,0))
        self.baud_entry = ttk.Entry(frm_top, width=8)
        self.baud_entry.insert(0, '115200')
        self.baud_entry.pack(side='left')

        self.connect_btn = ttk.Button(frm_top, text='Connect', command=self.toggle_connect)
        self.connect_btn.pack(side='left', padx=8)

        self.status_label = ttk.Label(frm_top, text='Disconnected', foreground='red')
        self.status_label.pack(side='left', padx=8)

        # Position display
        pos_frame = ttk.LabelFrame(self, text='Position')
        pos_frame.pack(fill='x', padx=8, pady=6)
        self.pos_var = tk.StringVar(value='X: ?   Y: ?   Z: ?')
        ttk.Label(pos_frame, textvariable=self.pos_var, font=('Consolas', 12)).pack(anchor='w', padx=6, pady=6)

        # Jog controls
        jog_frame = ttk.LabelFrame(self, text='Jog Controls')
        jog_frame.pack(fill='x', padx=8, pady=6)

        step_frame = ttk.Frame(jog_frame)
        step_frame.pack(anchor='w', padx=6, pady=4)
        ttk.Label(step_frame, text='Step (mm):').pack(side='left')
        self.step_entry = ttk.Entry(step_frame, width=6)
        self.step_entry.insert(0, '10')
        self.step_entry.pack(side='left', padx=4)

        ttk.Label(step_frame, text='Feedrate (mm/min):').pack(side='left', padx=(12,0))
        self.speed_entry = ttk.Entry(step_frame, width=8)
        self.speed_entry.insert(0, '1500')
        self.speed_entry.pack(side='left', padx=4)

        # Jog buttons grid
        grid = ttk.Frame(jog_frame)
        grid.pack(padx=6, pady=6)

        btn_xp = ttk.Button(grid, text='X +', width=8, command=lambda: self.jog('X', True))
        btn_xp.grid(row=0, column=2, padx=6, pady=6)
        btn_xm = ttk.Button(grid, text='X -', width=8, command=lambda: self.jog('X', False))
        btn_xm.grid(row=0, column=0, padx=6, pady=6)

        btn_yp = ttk.Button(grid, text='Y +', width=8, command=lambda: self.jog('Y', True))
        btn_yp.grid(row=1, column=2, padx=6, pady=6)
        btn_ym = ttk.Button(grid, text='Y -', width=8, command=lambda: self.jog('Y', False))
        btn_ym.grid(row=1, column=0, padx=6, pady=6)

        btn_zp = ttk.Button(grid, text='Z +', width=8, command=lambda: self.jog('Z', True))
        btn_zp.grid(row=2, column=2, padx=6, pady=6)
        btn_zm = ttk.Button(grid, text='Z -', width=8, command=lambda: self.jog('Z', False))
        btn_zm.grid(row=2, column=0, padx=6, pady=6)

        ttk.Label(grid, text='Jog:').grid(row=0, column=1)
        ttk.Label(grid, text='').grid(row=1, column=1)
        ttk.Label(grid, text='').grid(row=2, column=1)

        # Actions
        actions = ttk.Frame(self)
        actions.pack(fill='x', padx=8, pady=6)
        ttk.Button(actions, text='Home (G28)', command=self.home).pack(side='left', padx=6)
        ttk.Button(actions, text='Motors On (M17)', command=lambda: self.send_cmd('M17')).pack(side='left', padx=6)
        ttk.Button(actions, text='Motors Off (M18)', command=lambda: self.send_cmd('M18')).pack(side='left', padx=6)
        ttk.Button(actions, text='Emergency Stop (M112)', command=self.emergency_stop).pack(side='left', padx=6)

        # Console
        console_frame = ttk.LabelFrame(self, text='Console')
        console_frame.pack(fill='both', expand=True, padx=8, pady=6)
        self.console_out = scrolledtext.ScrolledText(console_frame, height=10, state='disabled')
        self.console_out.pack(fill='both', expand=True, padx=4, pady=4)
        # Save/clear console buttons
        cbtn_frame = ttk.Frame(console_frame)
        cbtn_frame.pack(fill='x', padx=4, pady=(0,4))
        ttk.Button(cbtn_frame, text='Save Log', command=self.save_log).pack(side='left')
        ttk.Button(cbtn_frame, text='Clear Log', command=self.clear_log).pack(side='left', padx=6)

        cmd_frame = ttk.Frame(console_frame)
        cmd_frame.pack(fill='x', padx=4, pady=4)
        self.cmd_entry = ttk.Entry(cmd_frame)
        self.cmd_entry.pack(side='left', fill='x', expand=True, padx=(0,6))
        ttk.Button(cmd_frame, text='Send', command=self.send_cmd_from_entry).pack(side='left')

        # G-code input area
        gcode_frame = ttk.LabelFrame(self, text='G-code Input')
        gcode_frame.pack(fill='both', expand=True, padx=8, pady=6)
        self.gcode_in = scrolledtext.ScrolledText(gcode_frame, height=8)
        self.gcode_in.pack(fill='both', expand=True, padx=4, pady=4)

        gcode_btns = ttk.Frame(gcode_frame)
        gcode_btns.pack(fill='x', padx=4, pady=4)
        self.send_gcode_btn = ttk.Button(gcode_btns, text='Send G-code', command=self.send_gcode_from_text)
        self.send_gcode_btn.pack(side='left')
        self.clear_gcode_btn = ttk.Button(gcode_btns, text='Clear', command=lambda: self.gcode_in.delete('1.0', 'end'))
        self.clear_gcode_btn.pack(side='left', padx=6)
        self.load_gcode_btn = ttk.Button(gcode_btns, text='Load File', command=self.load_gcode_from_file)
        self.load_gcode_btn.pack(side='left', padx=6)

        # Ensure widgets references for enable/disable
        self.widgets_to_toggle = [self.step_entry, self.speed_entry, btn_xp, btn_xm, btn_yp, btn_ym, btn_zp, btn_zm]
        # add send buttons to toggled widgets so we won't allow GCode sending when disconnected
        self.widgets_to_toggle += [self.cmd_entry, self.send_gcode_btn, self.load_gcode_btn, self.gcode_in]

    def refresh_ports(self):
        ports = self.controller.list_ports()
        self.port_cb['values'] = ports
        if ports:
            self.port_cb.set(ports[0])

    def toggle_connect(self):
        if self.controller.ser and self.controller.ser.is_open:
            self.controller.disconnect()
            self.set_disconnected()
        else:
            port = self.port_cb.get()
            try:
                baud = int(self.baud_entry.get() or 115200)
            except Exception:
                baud = 115200
            if not port:
                messagebox.showwarning('No port', 'Please select a serial port first (Refresh if needed).')
                return
            ok = self.controller.connect(port, baud)
            if ok:
                self.set_connected()
                self.log(f'Connected to {port} @ {baud}')
            else:
                messagebox.showerror('Connect failed', f'Could not open {port}')

    def set_connected(self):
        self.connect_btn.config(text='Disconnect')
        self.status_label.config(text='Connected', foreground='green')
        for w in self.widgets_to_toggle:
            w.config(state='normal')

    def set_disconnected(self):
        self.connect_btn.config(text='Connect')
        self.status_label.config(text='Disconnected', foreground='red')
        for w in self.widgets_to_toggle:
            w.config(state='disabled')

    def log(self, text):
        self.console_out.config(state='normal')
        self.console_out.insert('end', f'{time.strftime("%H:%M:%S")}  {text}\n')
        self.console_out.see('end')
        self.console_out.config(state='disabled')

    def send_cmd(self, cmd):
        try:
            self.controller.send_line(cmd)
            self.log(f'>>> {cmd}')
        except Exception as e:
            self.log(f'ERROR sending: {e}')

    def send_cmd_from_entry(self):
        cmd = self.cmd_entry.get().strip()
        if not cmd:
            return
        self.send_cmd(cmd)
        self.cmd_entry.delete(0, 'end')

    def save_log(self):
        try:
            import os
            fn = f"printer_log_{time.strftime('%Y%m%d_%H%M%S')}.txt"
            p = os.path.join(os.getcwd(), fn)
            with open(p, 'w', encoding='utf-8') as f:
                f.write(self.console_out.get('1.0', 'end'))
            self.log(f'Log saved to {p}')
        except Exception as e:
            self.log(f'ERROR saving log: {e}')

    def clear_log(self):
        self.console_out.config(state='normal')
        self.console_out.delete('1.0', 'end')
        self.console_out.config(state='disabled')

    def jog(self, axis, positive=True):
        try:
            step = float(self.step_entry.get())
            if not positive:
                step = -step
            feed = float(self.speed_entry.get())
        except Exception:
            messagebox.showerror('Invalid input', 'Step and feedrate must be numbers')
            return
        # relative jog
        self.send_cmd('G91')
        self.send_cmd(f'G1 {axis}{step} F{feed}')
        self.send_cmd('G90')

    def send_gcode_from_text(self):
        if not (self.controller.ser and self.controller.ser.is_open):
            messagebox.showwarning('Not connected', 'Please connect to a serial port first.')
            return
        content = self.gcode_in.get('1.0', 'end').strip()
        if not content:
            messagebox.showinfo('No G-code', 'Please paste or type G-code into the input area.')
            return
        lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
        # send in a background thread
        t = threading.Thread(target=self._send_gcode_lines, args=(lines,), daemon=True)
        t.start()

    def _send_gcode_lines(self, lines, wait_ok=True, ok_timeout=10.0):
        # disable send UI while sending
        self.after(0, lambda: self._set_send_buttons_state('disabled'))
        for ln in lines:
            try:
                self.controller.send_line(ln)
                self.log(f'>>> {ln}')
            except Exception as e:
                self.log(f'ERROR sending {ln}: {e}')
                break
            # optionally wait for 'ok' response
            if wait_ok:
                start = time.time()
                got_ok = False
                while time.time() - start < ok_timeout:
                    # fetch available responses
                    resp = self.controller.get_response_nowait()
                    for r in resp:
                        self.log(f'<<< {r}')
                        if r.strip().lower().startswith('ok') or r.strip().lower() == 'ok':
                            got_ok = True
                    if got_ok:
                        break
                    time.sleep(0.1)
                if not got_ok:
                    self.log(f'WARNING: Timeout waiting for ok after sending: {ln}')
        self.after(0, lambda: self._set_send_buttons_state('normal'))

    def _set_send_buttons_state(self, state):
        # disable main send UI elements; re-enable after sending
        try:
            for w in [self.cmd_entry]:
                w.config(state=state)
        except Exception:
            pass

    def load_gcode_from_file(self):
        try:
            from tkinter.filedialog import askopenfilename
            fn = askopenfilename(filetypes=[('G-code files', '*.gcode;*.gc;*.txt'), ('All files', '*.*')])
            if fn:
                with open(fn, 'r', encoding='utf-8', errors='ignore') as f:
                    txt = f.read()
                self.gcode_in.delete('1.0', 'end')
                self.gcode_in.insert('1.0', txt)
        except Exception as e:
            self.log(f'ERROR loading file: {e}')

    def home(self):
        if messagebox.askyesno('Home', 'Home all axes (G28)? Make sure it is safe to do so.'):
            self.send_cmd('G28')

    def emergency_stop(self):
        if messagebox.askyesno('E-STOP', 'Send M112 emergency stop? This requires manual reset on the printer.'):
            try:
                self.controller.send_line('M112')
                self.log('>>> M112 (EMERGENCY STOP)')
            except Exception as e:
                self.log(f'ERROR sending E-STOP: {e}')

    def _periodic_ui_update(self):
        # read responses and update UI
        lines = self.controller.get_response_nowait()
        for ln in lines:
            # display in console
            self.log(f'<<< {ln}')
            # try to parse position from M114 responses (typical Marlin: "X:10.00 Y:20.00 Z:0.30 E:0.00 Count X:1000 Y:2000 Z:30")
            if ln.startswith('X:') or ('X:' in ln and 'Y:' in ln and 'Z:' in ln):
                # extract floats
                try:
                    parts = ln.replace(',', ' ').split()
                    x = y = z = '?'
                    for p in parts:
                        if p.startswith('X:'):
                            x = p[2:]
                        elif p.startswith('Y:'):
                            y = p[2:]
                        elif p.startswith('Z:'):
                            z = p[2:]
                    self.pos_var.set(f'X: {x}   Y: {y}   Z: {z}')
                except Exception:
                    pass
        # schedule next
        self.after(200, self._periodic_ui_update)

    def on_close(self):
        if messagebox.askokcancel('Quit', 'Close controller and disconnect?'):
            try:
                self.controller.close()
            except Exception:
                pass
            self.destroy()


if __name__ == '__main__':
    app = App()
    app.protocol('WM_DELETE_WINDOW', app.on_close)
    app.mainloop()
