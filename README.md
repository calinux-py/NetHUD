# NetHUD

A lightweight system monitoring HUD (Heads-Up Display) that shows real-time system metrics in an always-on-top overlay.

## Features

- **Real-time monitoring**: CPU, GPU, VRAM, RAM usage
- **Network speed testing**: Internet download/upload speeds
- **Storage monitoring**: Disk space usage for all partitions
- **System info**: Connection status, signal strength, uptime
- **Customizable display**: Horizontal/vertical layout, small/regular size
- **Draggable overlay**: Click and drag to reposition
- **Always on top**: Stays visible over other applications
- **Configurable**: Settings saved between sessions

## Installation

1. Install Python 3.8+ if not already installed
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

### Quick Start
```bash
python newhud.pyw
```

### Configuration

Right-click the HUD to access the context menu:
- Toggle display options (storage, speed, connection, etc.)
- Switch between horizontal/vertical layout
- Enable/disable small HUD mode
- Toggle always-on-top behavior

## Requirements

- Python 3.8+
- Windows 10/11

## Dependencies

- `psutil` - System monitoring
- `speedtest-cli` - Network speed testing
- `PyQt6` - GUI framework
- `GPUtil` - GPU monitoring

