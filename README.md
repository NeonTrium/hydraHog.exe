# HydraHog 🐗🐍  
*A Lightweight Windows System Stress-Testing Utility*

HydraHog is a Windows-only system stress-testing utility written in Python, designed to generate controlled CPU and RAM load on low-end or aging hardware. The tool was developed to study system behavior, process management, and performance limits in environments where modern benchmarking software is too resource-intensive to run reliably.

## Why HydraHog?

Modern stress-testing and benchmarking tools often assume relatively capable hardware. HydraHog was built specifically to operate on severely constrained systems (e.g., older laptops), allowing controlled experimentation without immediately destabilizing the machine.

The project focuses on:
- Process lifecycle management
- Memory pressure behavior
- CPU scheduling under sustained load
- System stability and thermal response
- Performance overhead of user-space utilities

## Key Features

- **Multi-Process CPU Stress**
  - Configurable number of worker processes
  - Adjustable CPU intensity via duty-cycle control
  - Optional "Hydra Mode" that respawns workers if they terminate unexpectedly

- **Controlled RAM Stress**
  - Gradual memory allocation to avoid sudden system freezes
  - Safety warning based on user-allocated and maximum system memory

- **Pause- and Duration-Aware Execution**
  - Pause and resume stress tests without skewing results
  - Automatic shutdown after a user-defined duration

- **System Telemetry**
  - Real-time CPU and RAM usage
  - CPU temperature monitoring (when supported by the system)
  - Peak temperature tracking and thermal trend analysis

- **Post-Test Evaluation**
  - Stability assessment based on worker terminations
  - Thermal performance summary
  - Overall system stress score

- **Minimal Dependencies**
  - Built using Python standard libraries, Tkinter, and `psutil`
  - Suitable for older Windows systems

## Technical Overview

HydraHog uses Python’s multiprocessing module to spawn independent worker processes that generate CPU load through computation-heavy loops. Memory stress is applied through controlled allocation in a background thread to prevent UI blocking.

System metrics are collected using `psutil`, which interfaces with operating system APIs to report resource usage and temperature data when available.

The application includes a Tkinter-based GUI for configuration, monitoring, and logging.

## Intended Use

HydraHog is intended for:
- Educational exploration of operating system behavior
- Studying system stability under sustained load
- Testing thermal and performance limits on older hardware
- Demonstrating practical understanding of process and memory management

**Warning:** Running stress tests may cause system slowdowns or instability, especially on older machines. Use responsibly.

## Requirements

- Windows
- Python 3.x
- `psutil`

## License

This project is provided for educational and experimental purposes.
