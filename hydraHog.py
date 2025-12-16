import tkinter as tk
from tkinter import ttk, messagebox
import multiprocessing
import time
import psutil
import os
from datetime import datetime
import math
import threading

# Worker process gets CPU-bound tasks
def hydra_worker(duty_cycle, stop_event, pause_event):
    """CPU stress worker. Loops until the Hog pulls the plug."""
    pid = os.getpid()
    iteration = 0
    
    # Map duty_cycle to how aggressive the loop gets
    busy_time = duty_cycle * 0.1 # Max busy loop duration (100ms max)
    sleep_time = 0.01 # Fixed small sleep time, or: (1.0 - duty_cycle) * 0.01 (optional)

    while not stop_event.is_set():
        if pause_event.is_set(): # Check for pause
            time.sleep(0.1)
            continue
            
        # Burn CPU with pointless math
        start = time.perf_counter()
        while (time.perf_counter() - start) < busy_time:
            # Dumb math, real heat
            _ = math.factorial(100)
            _ = sum([i**2 for i in range(1000)])
            iteration += 1
        
        # Yield to OS briefly
        time.sleep(sleep_time)

class Hog:
    def __init__(self):
        self.workers = []
        self.stop_events = [] 
        self.ram_hog = []
        
        self.is_running = False
        self.is_paused = False
        self.pause_event = multiprocessing.Event()
        self.start_time = None
        self.hydra_mode = False
        
        # Pause-aware timing
        self.pause_start_time = None
        self.accumulated_pause_time = 0.0
        
        self.respawn_counts = {}
        self.max_respawns = 5
        self.respawn_window = 10
        self.last_respawn_time = {}
        
        self.log_buffer = []
        
        # Temperature tracking
        self.temp_readings = []
        self.initial_temps = {}
        self.peak_temps = {}
        
    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = f"[{timestamp}] {message}"
        self.log_buffer.append(entry)
        print(entry)
        
    def _get_temperatures(self):
        """Grab CPU temps if psutil exposes them. Not guaranteed."""
        temps = {}
        try:
            temp_info = psutil.sensors_temperatures()
            if temp_info:
                for name, entries in temp_info.items():
                    for entry in entries:
                        if 'core' in entry.label.lower() or 'cpu' in entry.label.lower() or 'package' in entry.label.lower():
                            key = f"{name}_{entry.label}"
                            temps[key] = entry.current
            # Fallback: try coretemp specifically
            if not temps and 'coretemp' in temp_info:
                for entry in temp_info['coretemp']:
                    temps[entry.label] = entry.current
        except:
            pass
        return temps
        
    def start_stress_test(self, cpu_workers, ram_mb, duration, duty_cycle, hydra_enabled):
        if self.is_running:
            return
            
        self.is_running = True
        self.is_paused = False
        self.pause_event.clear()
        self.start_time = time.time()
        
        # Reset pause timers on start
        self.pause_start_time = None
        self.accumulated_pause_time = 0.0
        
        self.hydra_mode = hydra_enabled
        self.target_duration = duration
        self.target_ram_mb = ram_mb
        self.duty_cycle = duty_cycle
        
        # Capture initial temps
        self.initial_temps = self._get_temperatures()
        self.peak_temps = self.initial_temps.copy()
        self.temp_readings = []
        
        self.log(f"=== Hog Test Started ===")
        self.log(f"CPU Workers: {cpu_workers}, RAM Target: {ram_mb}MB, Duration: {duration}s")
        self.log(f"Hydra Mode: {'ENABLED' if hydra_enabled else 'DISABLED'}")
        
        if self.initial_temps:
            avg_temp = sum(self.initial_temps.values()) / len(self.initial_temps)
            self.log(f"Initial CPU temp: {avg_temp:.1f}°C")
        else:
            self.log("Temperature sensors not available")
        
        # Spawn CPU workers
        for i in range(cpu_workers):
            self._spawn_worker(i)
        
        # Allocate RAM gradually in a separate thread to prevent GUI lock
        ram_thread = threading.Thread(target=self._allocate_ram, args=(ram_mb,))
        ram_thread.start()
        
    def _spawn_worker(self, worker_id):
        stop_event = multiprocessing.Event()
        
        process = multiprocessing.Process(
            target=hydra_worker,
            args=(self.duty_cycle, stop_event, self.pause_event),
            daemon=False
        )
        process.start()
        self.workers.append({'id': worker_id, 'process': process, 'stop_event': stop_event})
        self.log(f"Worker {worker_id} spawned (PID {process.pid})")
        
    def _allocate_ram(self, target_mb):
        """Allocate RAM slowly so the UI doesn’t freeze."""
        available = psutil.virtual_memory().available / (1024**2)
        safe_limit = min(target_mb, available * 0.7)
        
        chunk_size = 10 * 1024 * 1024
        allocated = 0
        target_bytes = int(safe_limit * 1024 * 1024)
        
        self.log(f"Allocating {safe_limit:.0f}MB RAM...")
        
        while allocated < target_bytes and self.is_running:
            try:
                chunk = os.urandom(chunk_size)
                self.ram_hog.append(chunk)
                allocated += chunk_size
                time.sleep(0.001)
            except MemoryError:
                self.log("RAM allocation limit hit")
                break
            except Exception as e:
                self.log(f"RAM allocation error: {e}")
                break
                
        self.log(f"RAM allocated: {allocated / (1024**2):.0f}MB")
        
    def check_workers(self):
        """Keep workers alive and watch the clock."""
        if not self.is_running:
            return
            
        current_time = time.time()
        
        # Use pause-aware elapsed time instead of wall clock
        if self.is_paused:
            # While paused, time should stand still
            effective_elapsed = current_time - self.start_time - self.accumulated_pause_time
            # Don't proceed with duration check if paused, wait for resume.
        else:
            # If running, the effective elapsed time is the total duration minus accumulated pause time
            effective_elapsed = current_time - self.start_time - self.accumulated_pause_time

            # Check duration using effective elapsed time
            if effective_elapsed >= self.target_duration:
                self.log("Duration reached. Stopping test.")
                self.stop_stress_test()
                return # Exit immediately to stop further processing

        # Skip sampling while paused
        if not self.is_paused:
            # Sample temperature (unchanged)
            current_temps = self._get_temperatures()
            if current_temps:
                self.temp_readings.append({
                    'time': effective_elapsed, # Use effective elapsed time here
                    'temps': current_temps
                })
                # Track peaks
                for key, temp in current_temps.items():
                    self.peak_temps[key] = max(self.peak_temps.get(key, temp), temp)
            
            dead_workers_data = []
            
            for worker_data in self.workers:
                proc = worker_data['process']
                worker_id = worker_data['id']
                
                if not proc.is_alive():
                    self.log(f"Worker {worker_id} terminated (PID {proc.pid})")
                    
                    dead_workers_data.append(worker_data)
                    
                    if self.hydra_mode:
                        # Check respawn limits
                        self.respawn_counts.setdefault(worker_id, 0)
                        self.last_respawn_time.setdefault(worker_id, current_time)
                        
                        time_since_last = current_time - self.last_respawn_time[worker_id]
                        
                        if time_since_last > self.respawn_window:
                            self.respawn_counts[worker_id] = 0
                        
                        if self.respawn_counts[worker_id] < self.max_respawns:
                            self.log(f"Respawning worker {worker_id} (attempt {self.respawn_counts[worker_id] + 1}/{self.max_respawns})")
                            self._spawn_worker(worker_id)
                            self.respawn_counts[worker_id] += 1
                            self.last_respawn_time[worker_id] = current_time
                        else:
                            self.log(f"Worker {worker_id} exceeded respawn limit. Giving up.")
                    
            # Cleanup dead workers and their data
            for dead_data in dead_workers_data:
                self.workers.remove(dead_data)
                
    def pause_test(self):
        if not self.is_running or self.is_paused:
            return
        self.is_paused = True
        self.pause_event.set()
        
        # Remember when the pause started
        self.pause_start_time = time.time()
        
        self.log("Test PAUSED")
        
    def resume_test(self):
        if not self.is_running or not self.is_paused:
            return
        
        # Account for how long we've been paused
        if self.pause_start_time is not None:
            pause_duration = time.time() - self.pause_start_time
            self.accumulated_pause_time += pause_duration
            self.pause_start_time = None # Reset pause start time
            self.log(f"Paused for {pause_duration:.1f}s. Total paused time: {self.accumulated_pause_time:.1f}s")

        self.is_paused = False
        self.pause_event.clear()
        self.log("Test RESUMED")
        
    def stop_stress_test(self):
        if not self.is_running:
            return
            
        self.log("=== Stopping Test ===")
        
        # If stopping while paused, ensure the final pause duration is accounted for
        if self.is_paused and self.pause_start_time is not None:
            self.accumulated_pause_time += time.time() - self.pause_start_time
        
        # Kill all workers
        for worker_data in self.workers:
            worker_data['stop_event'].set()
            worker_data['process'].join(timeout=2)
            if worker_data['process'].is_alive():
                worker_data['process'].terminate()
                worker_data['process'].join()
        
        self.workers.clear()
        self.stop_events.clear()
        self.pause_event.clear()
        
        # Free RAM
        self.ram_hog.clear()
        
        # Final calculation for the report
        if self.start_time:
            self.actual_duration = (time.time() - self.start_time) - self.accumulated_pause_time
        else:
            self.actual_duration = 0.0
            
        self.is_running = False
        self.is_paused = False
        
        self._generate_report()
        
    def _generate_report(self):
        self.log("=== Test Report ===")
        
        # Use the corrected actual_duration
        actual_duration = self.actual_duration
        
        # Stability assessment
        total_respawns = sum(self.respawn_counts.values())
        stability = "STABLE" if total_respawns == 0 else "UNSTABLE" if total_respawns > 10 else "MODERATE"
        
        self.log(f"Stability: {stability}")
        self.log(f"Total respawns: {total_respawns}")
        self.log(f"Actual duration: {actual_duration:.1f}s / {self.target_duration}s")
        
        # Duration check
        completion_pct = (actual_duration / self.target_duration) * 100 if self.target_duration > 0 else 0
        if completion_pct < 50:
            self.log(f"WARNING: Test ended early ({completion_pct:.0f}% complete)")
        elif completion_pct >= 95:
            self.log(f"Test completed successfully ({completion_pct:.0f}%)")
        else:
            self.log(f"Test partially completed ({completion_pct:.0f}%)")
        
        # Temperature analysis
        if self.temp_readings and self.initial_temps:
            self.log("--- Temperature Analysis ---")
            
            avg_initial = sum(self.initial_temps.values()) / len(self.initial_temps)
            avg_peak = sum(self.peak_temps.values()) / len(self.peak_temps)
            delta = avg_peak - avg_initial
            
            self.log(f"Initial temp: {avg_initial:.1f}°C")
            self.log(f"Peak temp: {avg_peak:.1f}°C")
            self.log(f"Temperature rise: {delta:.1f}°C")
            
            # Thermal assessment
            if delta < 10:
                thermal_rating = "EXCELLENT (minimal heating)"
            elif delta < 20:
                thermal_rating = "GOOD (moderate heating)"
            elif delta < 35:
                thermal_rating = "FAIR (significant heating)"
            else:
                thermal_rating = "POOR (excessive heating)"
            
            self.log(f"Thermal performance: {thermal_rating}")
            
            # Check if temps stabilized or kept climbing
            if len(self.temp_readings) > 10:
                recent_temps = [sum(r['temps'].values())/len(r['temps']) for r in self.temp_readings[-10:]]
                temp_trend = recent_temps[-1] - recent_temps[0]
                if abs(temp_trend) < 2:
                    self.log("Temperature curve: STABILIZED")
                elif temp_trend > 0:
                    self.log("Temperature curve: STILL RISING (heat soak)")
                else:
                    self.log("Temperature curve: DECLINING")
        else:
            self.log("Temperature data not available")
        
        # Worker summary
        if self.respawn_counts:
            self.log("Worker respawn summary:")
            for wid, count in self.respawn_counts.items():
                self.log(f"  Worker {wid}: {count} respawns")
        
        # Overall score
        score = 100
        score -= min(total_respawns * 5, 50)
        if completion_pct < 95:
            score -= (100 - completion_pct) * 0.5
        if self.temp_readings and delta > 30:
            score -= 10
        
        score = max(0, int(score))
        self.log(f"--- Overall Score: {score}/100 ---")
        
        self.log("=== End Report ===")
        
    def get_stats(self):
        cpu = psutil.cpu_percent(interval=0.1)
        ram = psutil.virtual_memory().percent
        alive_workers = sum(1 for w in self.workers if w['process'].is_alive())
        
        # Calculate elapsed time correctly for display
        effective_elapsed = 0
        if self.start_time:
            # Time since start
            total_time = time.time() - self.start_time
            # Account for current pause period if paused
            current_pause_duration = 0.0
            if self.is_paused and self.pause_start_time is not None:
                current_pause_duration = time.time() - self.pause_start_time
            
            effective_elapsed = total_time - self.accumulated_pause_time - current_pause_duration
        
        # Current temp
        current_temps = self._get_temperatures()
        avg_temp = None
        temp_details = []
        if current_temps:
            avg_temp = sum(current_temps.values()) / len(current_temps)
            temp_details = [(k.split('_')[-1], v) for k, v in current_temps.items()]
        
        return {
            'cpu': cpu,
            'ram': ram,
            'workers': alive_workers,
            'elapsed': int(effective_elapsed), # Return corrected elapsed time
            'temp': avg_temp,
            'temp_details': temp_details
        }

class HydraHogGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("HydraHog - System Stress Tester")
        self.root.geometry("650x650")
        self.root.resizable(False, False)
        
        # Dark theme colors
        self.bg_primary = "#1a1a1a"
        self.bg_secondary = "#2a2a2a"
        self.bg_tertiary = "#353535"
        self.accent_color = "#ff4444"
        self.accent_hover = "#ff6666"
        self.text_primary = "#e0e0e0"
        self.text_secondary = "#a0a0a0"
        self.success_color = "#44ff88"
        self.warning_color = "#ffaa44"
        
        self.root.configure(bg=self.bg_primary)
        
        self.hog = Hog()
        
        # Title
        title_frame = tk.Frame(root, bg=self.bg_primary)
        title_frame.pack(fill=tk.X, padx=10, pady=10)
        
        title_label = tk.Label(
            title_frame,
            text="⚡ HydraHog ⚡",
            font=("Consolas", 20, "bold"),
            bg=self.bg_primary,
            fg=self.accent_color
        )
        title_label.pack()
        
        subtitle_label = tk.Label(
            title_frame,
            text="System Stress Tester",
            font=("Consolas", 10),
            bg=self.bg_primary,
            fg=self.text_secondary
        )
        subtitle_label.pack()
        
        # Config frame
        config_frame = tk.LabelFrame(
            root,
            text=" Configuration ",
            bg=self.bg_secondary,
            fg=self.text_primary,
            font=("Consolas", 10, "bold"),
            relief=tk.FLAT,
            borderwidth=2
        )
        config_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # CPU workers
        self._create_config_row(config_frame, "CPU Workers:", 0)
        self.cpu_var = tk.IntVar(value=multiprocessing.cpu_count())
        cpu_spin = tk.Spinbox(
            config_frame,
            from_=1,
            to=multiprocessing.cpu_count(),
            textvariable=self.cpu_var,
            width=12,
            bg=self.bg_tertiary,
            fg=self.text_primary,
            buttonbackground=self.bg_tertiary,
            relief=tk.FLAT
        )
        cpu_spin.grid(row=0, column=1, sticky=tk.W, padx=5, pady=3)
        
        # RAM target
        self._create_config_row(config_frame, "RAM (MB):", 1)
        self.ram_var = tk.IntVar(value=512)
        ram_spin = tk.Spinbox(
            config_frame,
            from_=0,
            to=4096,
            textvariable=self.ram_var,
            width=12,
            bg=self.bg_tertiary,
            fg=self.text_primary,
            buttonbackground=self.bg_tertiary,
            relief=tk.FLAT
        )
        ram_spin.grid(row=1, column=1, sticky=tk.W, padx=5, pady=3)
        
        # Duration
        self._create_config_row(config_frame, "Duration (s):", 2)
        self.duration_var = tk.IntVar(value=60)
        duration_spin = tk.Spinbox(
            config_frame,
            from_=10,
            to=3600,
            textvariable=self.duration_var,
            width=12,
            bg=self.bg_tertiary,
            fg=self.text_primary,
            buttonbackground=self.bg_tertiary,
            relief=tk.FLAT
        )
        duration_spin.grid(row=2, column=1, sticky=tk.W, padx=5, pady=3)
        
        # CPU intensity
        self._create_config_row(config_frame, "CPU Intensity:", 3)
        self.intensity_var = tk.DoubleVar(value=0.9)
        intensity_scale = tk.Scale(
            config_frame,
            from_=0.1,
            to=1.0,
            resolution=0.1,
            variable=self.intensity_var,
            orient=tk.HORIZONTAL,
            bg=self.bg_secondary,
            fg=self.text_primary,
            troughcolor=self.bg_tertiary,
            highlightthickness=0,
            relief=tk.FLAT
        )
        intensity_scale.grid(row=3, column=1, sticky=tk.EW, padx=5, pady=3)
        
        # Hydra mode
        self.hydra_var = tk.BooleanVar(value=False)
        hydra_check = tk.Checkbutton(
            config_frame,
            text="Enable Hydra Mode (respawn on termination)",
            variable=self.hydra_var,
            bg=self.bg_secondary,
            fg=self.text_primary,
            selectcolor=self.bg_tertiary,
            activebackground=self.bg_secondary,
            activeforeground=self.text_primary,
            font=("Consolas", 9)
        )
        hydra_check.grid(row=4, column=0, columnspan=2, sticky=tk.W, pady=5, padx=5)
        
        # Control buttons
        btn_frame = tk.Frame(root, bg=self.bg_primary)
        btn_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.start_btn = tk.Button(
            btn_frame,
            text="▶ START",
            command=self.start_test,
            bg=self.success_color,
            fg=self.bg_primary,
            font=("Consolas", 11, "bold"),
            relief=tk.FLAT,
            padx=20,
            pady=8,
            cursor="hand2"
        )
        self.start_btn.pack(side=tk.LEFT, padx=5)
        
        self.pause_btn = tk.Button(
            btn_frame,
            text="⏸ PAUSE",
            command=self.pause_test,
            bg=self.warning_color,
            fg=self.bg_primary,
            font=("Consolas", 11, "bold"),
            relief=tk.FLAT,
            padx=20,
            pady=8,
            state=tk.DISABLED,
            cursor="hand2"
        )
        self.pause_btn.pack(side=tk.LEFT, padx=5)
        
        self.stop_btn = tk.Button(
            btn_frame,
            text="⏹ STOP",
            command=self.stop_test,
            bg=self.accent_color,
            fg=self.text_primary,
            font=("Consolas", 11, "bold"),
            relief=tk.FLAT,
            padx=20,
            pady=8,
            state=tk.DISABLED,
            cursor="hand2"
        )
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        
        # Status frame
        status_frame = tk.LabelFrame(
            root,
            text=" System Status ",
            bg=self.bg_secondary,
            fg=self.text_primary,
            font=("Consolas", 10, "bold"),
            relief=tk.FLAT,
            borderwidth=2
        )
        status_frame.pack(fill=tk.BOTH, padx=10, pady=5)
        
        self.status_label = tk.Label(
            status_frame,
            text="● IDLE",
            font=("Consolas", 12, "bold"),
            bg=self.bg_secondary,
            fg=self.text_secondary
        )
        self.status_label.pack(pady=5)
        
        stats_container = tk.Frame(status_frame, bg=self.bg_secondary)
        stats_container.pack(fill=tk.BOTH, padx=10, pady=5)
        
        self.cpu_label = tk.Label(
            stats_container,
            text="CPU: 0%",
            font=("Consolas", 10),
            bg=self.bg_secondary,
            fg=self.text_primary
        )
        self.cpu_label.pack(anchor=tk.W)
        
        self.ram_label = tk.Label(
            stats_container,
            text="RAM: 0%",
            font=("Consolas", 10),
            bg=self.bg_secondary,
            fg=self.text_primary
        )
        self.ram_label.pack(anchor=tk.W)
        
        self.temp_label = tk.Label(
            stats_container,
            text="Temp: --",
            font=("Consolas", 10),
            bg=self.bg_secondary,
            fg=self.text_primary
        )
        self.temp_label.pack(anchor=tk.W)
        
        # Temperature details frame
        self.temp_details_frame = tk.Frame(stats_container, bg=self.bg_secondary)
        self.temp_details_frame.pack(fill=tk.X, pady=3)
        
        self.worker_label = tk.Label(
            stats_container,
            text="Workers: 0",
            font=("Consolas", 10),
            bg=self.bg_secondary,
            fg=self.text_primary
        )
        self.worker_label.pack(anchor=tk.W)
        
        self.elapsed_label = tk.Label(
            stats_container,
            text="Elapsed: 0s",
            font=("Consolas", 10),
            bg=self.bg_secondary,
            fg=self.text_primary
        )
        self.elapsed_label.pack(anchor=tk.W)
        
        # Log frame
        log_frame = tk.LabelFrame(
            root,
            text=" Activity Log ",
            bg=self.bg_secondary,
            fg=self.text_primary,
            font=("Consolas", 10, "bold"),
            relief=tk.FLAT,
            borderwidth=2
        )
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.log_text = tk.Text(
            log_frame,
            height=10,
            state=tk.DISABLED,
            wrap=tk.WORD,
            bg=self.bg_tertiary,
            fg=self.text_primary,
            font=("Consolas", 9),
            relief=tk.FLAT,
            insertbackground=self.text_primary
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Update loop
        self.update_ui()
        
    def _create_config_row(self, parent, label_text, row):
        label = tk.Label(
            parent,
            text=label_text,
            bg=self.bg_secondary,
            fg=self.text_primary,
            font=("Consolas", 9)
        )
        label.grid(row=row, column=0, sticky=tk.W, padx=5, pady=3)
        
    def start_test(self):
        if self.hog.is_running:
            return
            
        # Warning dialog
        response = messagebox.askokcancel(
            "⚠ Warning",
            "This will stress your system. Old hardware may freeze or crash. Continue?"
        )
        if not response:
            return
            
        self.start_btn.config(state=tk.DISABLED)
        self.pause_btn.config(state=tk.NORMAL, text="⏸ PAUSE")
        self.stop_btn.config(state=tk.NORMAL)
        
        self.hog.start_stress_test(
            cpu_workers=self.cpu_var.get(),
            ram_mb=self.ram_var.get(),
            duration=self.duration_var.get(),
            duty_cycle=self.intensity_var.get(),
            hydra_enabled=self.hydra_var.get()
        )
        
    def pause_test(self):
        if self.hog.is_paused:
            self.hog.resume_test()
            self.pause_btn.config(text="⏸ PAUSE")
        else:
            self.hog.pause_test()
            self.pause_btn.config(text="▶ RESUME")
            
    def stop_test(self):
        self.hog.stop_stress_test()
        self.start_btn.config(state=tk.NORMAL)
        self.pause_btn.config(state=tk.DISABLED, text="⏸ PAUSE")
        self.stop_btn.config(state=tk.DISABLED)
        
    def update_ui(self):
        # Check workers
        if self.hog.is_running:
            self.hog.check_workers()
            
        # Update status
        if self.hog.is_running:
            stats = self.hog.get_stats()
            
            status_text = "● RUNNING" if not self.hog.is_paused else "● PAUSED"
            status_color = self.success_color if not self.hog.is_paused else self.warning_color
            self.status_label.config(text=status_text, fg=status_color)
            
            self.cpu_label.config(text=f"CPU: {stats['cpu']:.1f}%")
            self.ram_label.config(text=f"RAM: {stats['ram']:.1f}%")
            
            if stats['temp'] is not None:
                self.temp_label.config(text=f"Temp: {stats['temp']:.1f}°C")
                
                # Clear previous temp details
                for widget in self.temp_details_frame.winfo_children():
                    widget.destroy()
                
                # Display individual core temps
                if stats['temp_details']:
                    for label, temp in stats['temp_details'][:8]:
                        temp_detail = tk.Label(
                            self.temp_details_frame,
                            text=f"  {label}: {temp:.1f}°C",
                            font=("Consolas", 8),
                            bg=self.bg_secondary,
                            fg=self.text_secondary
                        )
                        temp_detail.pack(anchor=tk.W)
            else:
                self.temp_label.config(text="Temp: N/A")
                # Clear previous temp details
                for widget in self.temp_details_frame.winfo_children():
                    widget.destroy()
            
            self.worker_label.config(text=f"Workers: {stats['workers']}")
            # Use corrected elapsed time from stats
            self.elapsed_label.config(text=f"Elapsed: {stats['elapsed']}s / {self.hog.target_duration}s")
        else:
            self.status_label.config(text="● IDLE", fg=self.text_secondary)
            # Reset button states when not running
            if not self.hog.is_running:
                self.start_btn.config(state=tk.NORMAL)
                self.pause_btn.config(state=tk.DISABLED, text="⏸ PAUSE")
                self.stop_btn.config(state=tk.DISABLED)
            
        # Update log
        while self.hog.log_buffer:
            msg = self.hog.log_buffer.pop(0)
            self.log_text.config(state=tk.NORMAL)
            self.log_text.insert(tk.END, msg + "\n")
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)
            
        self.root.after(250, self.update_ui)

def main():
    multiprocessing.freeze_support()
    
    root = tk.Tk()
    app = HydraHogGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
