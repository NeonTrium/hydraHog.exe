import tkinter as tk
from tkinter import messagebox
import multiprocessing
import time
import psutil
import os
from datetime import datetime
import threading

# --- Hydra Worker Logic ---
#--- Brett Dalton will be a good one ---
def hydra_worker(duty_cycle, stop_event, pause_event):
    busy_time = duty_cycle * 0.1
    while not stop_event.is_set():
        if pause_event.is_set():
            time.sleep(0.1)
            continue
        start = time.perf_counter()
        while (time.perf_counter() - start) < busy_time:
            _ = 2**100000
        time.sleep(0.01)
        
# --- Core Logic Class ---
class Hog:
    def __init__(self):
        self.workers = []
        self.ram_hog = []
        self.is_running = False
        self.is_paused = False
        self.pause_event = multiprocessing.Event()
        self.log_buffer = []
        self.temp_history = []
        self.reset_stats()
        # self.note = "You're doing good. The PC? Debatable."

    def reset_stats(self):
        # Reset all run-specific metrics
        self.start_time = 0
        self.accumulated_pause_time = 0
        self.pause_start_time = None
        self.respawns = 0
        self.initial_temps = {}
        self.peak_temps = {}
        self.temp_history = []

    def log(self, msg):
        # Buffered logging
        self.log_buffer.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

    def get_temps(self):
        temps = {}
        try:
            raw = psutil.sensors_temperatures()
            for name, entries in raw.items():
                for entry in entries:
                    temps[entry.label or name] = entry.current
        except: pass
        return temps

    def start(self, cfg):
        self.log("Design Note: HydraHog applies user-defined stress limits without internal enforcement. Use responsibly.")
        self.reset_stats()
        self.is_running, self.is_paused = True, False
        self.cfg = cfg
        self.start_time = time.time()
        self.initial_temps = self.get_temps()
        self.peak_temps = self.initial_temps.copy()
        
        self.log(f"Test Start: {cfg['cpu']} Workers | Hydra: {cfg['hydra']}")
        for i in range(cfg['cpu']): self._spawn(i)
        # RAM allocation runs in a background thread so the UI stays responsive
        # unlike my crush
        threading.Thread(target=self._allocate_ram, daemon=True).start()

    def _spawn(self, wid):
        stop_evt = multiprocessing.Event()
        p = multiprocessing.Process(target=hydra_worker, args=(self.cfg['intensity'], stop_evt, self.pause_event))
        p.start()
        self.workers.append({'id': wid, 'proc': p, 'stop': stop_evt})

    def _allocate_ram(self):
        target_bytes = self.cfg['ram'] * 1024 * 1024
        chunk_size = 50 * 1024 * 1024
        while len(self.ram_hog) * chunk_size < target_bytes and self.is_running:
            try:
                self.ram_hog.append(b'x' * chunk_size)
                time.sleep(0.05)
            except MemoryError: break

    def toggle_pause(self):
        if not self.is_running: return
        self.is_paused = not self.is_paused
        if self.is_paused:
            self.pause_event.set()
            self.pause_start_time = time.time()
            self.log("Test PAUSED")
        else:
            self.pause_event.clear()
            self.accumulated_pause_time += (time.time() - self.pause_start_time)
            self.log("Test RESUMED")

    def update_and_check(self):
        if not self.is_running or self.is_paused: return
        
        # Hydra Logic (Optional)
        for w in self.workers[:]:
            if not w['proc'].is_alive():
                self.log(f"Worker {w['id']} terminated.")
                self.workers.remove(w)
                if self.cfg['hydra']:
                    self.log(f"Hydra: Respawning Worker {w['id']}...")
                    self._spawn(w['id'])
                    self.respawns += 1

        # Periodic Temp Sampling
        cur = self.get_temps()
        if cur:
            avg_now = sum(cur.values())/len(cur)
            self.temp_history.append(avg_now)
            for k, v in cur.items(): self.peak_temps[k] = max(self.peak_temps.get(k, v), v)

        elapsed = (time.time() - self.start_time) - self.accumulated_pause_time
        if elapsed >= self.cfg['duration']: self.stop()

    def stop(self):
        if not self.is_running: return
        self.is_running = False
        for w in self.workers:
            w['stop'].set()
            w['proc'].terminate()
        self.generate_report()
        self.workers, self.ram_hog = [], []

    def generate_report(self):
        self.log("=== FINAL DIAGNOSTIC ===")
        stability = "STABLE" if self.respawns == 0 else "VOLATILE"
        self.log(f"OS Stability: {stability} ({self.respawns} Respawns)")
        
        if self.temp_history and len(self.temp_history) > 5:
            delta = max(self.temp_history) - self.temp_history[0]
            # Check last 20% of samples for slope
            tail = self.temp_history[-int(len(self.temp_history)*0.2):]
            slope = tail[-1] - tail[0]
            
            thermal_status = "PLATEAUED" if abs(slope) < 1.5 else "RISING (Heat Soak)"
            self.log(f"Thermal Delta: +{delta:.1f}°C | State: {thermal_status}")
            
            score = 100 - (self.respawns * 15) - (max(0, slope) * 2)
        else:
            self.log("Thermal Data: Incomplete")
            score = 100 - (self.respawns * 15)
            
        self.log(f"FINAL SCORE: {max(0, int(score))}/100")
        self.log("========================")

# --- GUI Layer ---
class HydraHogGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("HydraHog v2.2")
        self.root.geometry("600x720")
        self.root.configure(bg="#1a1a1a")
        self.hog = Hog()
        self.style = {"bg": "#2a2a2a", "fg": "#e0e0e0", "font": ("Consolas", 10)}
        
        tk.Label(root, text="⚡ HYDRA HOG ⚡", font=("Consolas", 18, "bold"), bg="#1a1a1a", fg="#ff4444").pack(pady=10)
        
        cfg_frame = tk.LabelFrame(root, text=" Config ", **self.style)
        cfg_frame.pack(fill="x", padx=15, pady=5)
        
        self.inputs = {
            "cpu": tk.IntVar(value=multiprocessing.cpu_count()),
            "ram": tk.IntVar(value=1024),
            "duration": tk.IntVar(value=60),
            "intensity": tk.DoubleVar(value=0.9),
            "hydra": tk.BooleanVar(value=True)
        }
        
        # Grid Config
        rows = [("CPU Workers", "cpu"), ("RAM (MB)", "ram"), ("Duration (s)", "duration"), ("Intensity", "intensity")]
        for i, (txt, key) in enumerate(rows):
            tk.Label(cfg_frame, text=txt, **self.style).grid(row=i, column=0, sticky="w", padx=10)
            if key == "intensity":
                tk.Scale(cfg_frame, variable=self.inputs[key], from_=0.1, to=1.0, resolution=0.1, orient="horizontal", bg="#2a2a2a", fg="white", highlightthickness=0).grid(row=i, column=1, sticky="ew")
            else:
                tk.Spinbox(cfg_frame, textvariable=self.inputs[key], from_=1, to=100000, bg="#353535", fg="white").grid(row=i, column=1, pady=2)

        tk.Checkbutton(cfg_frame, text="Enable Hydra Mode (Auto-Respawn)", variable=self.inputs["hydra"], bg="#2a2a2a", fg="#44ff88", selectcolor="#1a1a1a", activebackground="#2a2a2a").grid(row=4, columnspan=2, pady=5)
        # Cut one head and two more shall rise ~ Sun Tzu (Probably)
        
        btn_frame = tk.Frame(root, bg="#1a1a1a")
        btn_frame.pack(pady=10)
        self.start_btn = tk.Button(btn_frame, text="START", command=self.run_test, bg="#44ff88", width=10, font=("Consolas", 10, "bold"))
        self.start_btn.pack(side="left", padx=5)
        self.pause_btn = tk.Button(btn_frame, text="PAUSE", command=self.hog.toggle_pause, bg="#ffaa44", width=10, font=("Consolas", 10, "bold"), state="disabled")
        self.pause_btn.pack(side="left", padx=5)
        tk.Button(btn_frame, text="STOP", command=self.hog.stop, bg="#ff4444", width=10, font=("Consolas", 10, "bold")).pack(side="left", padx=5)

        self.status_lbl = tk.Label(root, text="IDLE", font=("Consolas", 12), bg="#1a1a1a", fg="#a0a0a0")
        self.status_lbl.pack()
        self.log_box = tk.Text(root, height=18, bg="#101010", fg="#44ff88", font=("Consolas", 9))
        self.log_box.pack(fill="both", expand=True, padx=15, pady=10)

        self.update_loop()

    def run_test(self):
        total_ram = psutil.virtual_memory().total / (1024**2)
        req_ram = self.inputs["ram"].get()
        
        # Memory Safety Warning
        warn_msg = "STRESS TEST ADVISORY:\n\n1. Close all work/apps to prevent data loss.\n2. Background apps skew results."
        if req_ram > (total_ram * 0.9):
            warn_msg += f"\n\nCRITICAL: You are requesting {req_ram}MB but system has {int(total_ram)}MB. This will likely crash your OS."
            if not messagebox.askyesno("Extreme Risk", warn_msg + "\n\nProceed anyway?"): return
        elif not messagebox.askokcancel("Ready?", warn_msg): return

        self.hog.start({k: v.get() for k, v in self.inputs.items()})

    def update_loop(self):
        self.hog.update_and_check()
        if self.hog.is_running:
            self.start_btn.config(state="disabled")
            self.pause_btn.config(state="normal", text="RESUME" if self.hog.is_paused else "PAUSE")
            elapsed = int((time.time() - self.hog.start_time) - self.hog.accumulated_pause_time)
            if self.hog.is_paused: elapsed = int(self.hog.pause_start_time - self.hog.start_time - self.hog.accumulated_pause_time)
            
            cur_temps = self.hog.get_temps()
            temp_str = f" | {list(cur_temps.values())[0]}°C" if cur_temps else ""
            self.status_lbl.config(text=f"{'PAUSED' if self.hog.is_paused else 'RUNNING'}: {elapsed}s / {self.hog.cfg['duration']}s{temp_str}", fg="#44ff88" if not self.hog.is_paused else "#ffaa44")
        else:
            self.start_btn.config(state="normal")
            self.pause_btn.config(state="disabled")
            self.status_lbl.config(text="IDLE", fg="#a0a0a0")

        while self.hog.log_buffer:
            self.log_box.insert("end", self.hog.log_buffer.pop(0) + "\n")
            self.log_box.see("end")
        self.root.after(400, self.update_loop)

if __name__ == "__main__":
    multiprocessing.freeze_support()
    root = tk.Tk()
    app = HydraHogGUI(root)
    root.mainloop()

#--- Hail Hydra ---
