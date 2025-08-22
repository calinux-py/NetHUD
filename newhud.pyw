import sys
import socket
import psutil
import speedtest
import threading
import configparser
import os
import subprocess
import re
import time
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QMenu
from PyQt6.QtCore import Qt, QTimer, QPoint, QPropertyAnimation, QEasingCurve, QRect, QSize, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QAction

class SystemMonitorHUD(QWidget):
    speed_updated = pyqtSignal(float)
    
    def __init__(self):
        super().__init__()
        self.config_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'newhud_config.ini')
        self.oldPos = None
        self.always_on_top = True
        self.horizontal_display = False
        self.small_hud = False
        self.show_storage = True
        self.show_speed = False
        self.show_connection = False
        self.show_signal = False
        self.show_uptime = False
        self.container_widget = None
        self.is_transitioning = False
        self.is_dragging = False
        self.labels = {}
        self._positioned = False
        self.disk_partitions = self.get_disk_partitions()
        self.current_speed = 0.0
        self.speed_test_running = False
        self.current_signal = "---"
        
        self.speed_updated.connect(self.on_speed_updated)
        self.load_config()
        self.init_ui()
        self.init_timers()
        
    def load_config(self):
        config = configparser.ConfigParser()
        self.saved_position = QPoint(50, 50)
        
        if os.path.exists(self.config_file):
            try:
                config.read(self.config_file)
                
                if 'Display' in config:
                    display = config['Display']
                    self.always_on_top = display.getboolean('always_on_top', True)
                    self.horizontal_display = display.getboolean('horizontal_display', False)
                    self.small_hud = display.getboolean('small_hud', False)
                    self.show_storage = display.getboolean('show_storage', True)
                    self.show_speed = display.getboolean('show_speed', False)
                    self.show_connection = display.getboolean('show_connection', False)
                    self.show_signal = display.getboolean('show_signal', False)
                    self.show_uptime = display.getboolean('show_uptime', False)
                
                if 'Window' in config:
                    window = config['Window']
                    x = window.getint('x', 50)
                    y = window.getint('y', 50)
                    self.saved_position = QPoint(x, y)
            except Exception:
                pass
    
    def save_config(self):
        config = configparser.ConfigParser()
        config['Display'] = {
            'always_on_top': str(self.always_on_top),
            'horizontal_display': str(self.horizontal_display),
            'small_hud': str(self.small_hud),
            'show_storage': str(self.show_storage),
            'show_speed': str(self.show_speed),
            'show_connection': str(self.show_connection),
            'show_signal': str(self.show_signal),
            'show_uptime': str(self.show_uptime)
        }
        config['Window'] = {'x': str(self.x()), 'y': str(self.y())}
        
        try:
            with open(self.config_file, 'w') as configfile:
                config.write(configfile)
        except Exception:
            pass
    
    def closeEvent(self, event):
        self.save_config()
        super().closeEvent(event)
        
    def init_ui(self):
        self.update_window_flags()
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setWindowOpacity(0.85)
        
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(main_layout)
        self.setup_display()
    
    def update_window_flags(self):
        flags = Qt.WindowType.FramelessWindowHint | (Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Window if self.always_on_top else Qt.WindowType.Tool)
        self.setWindowFlags(flags)
        if self.always_on_top:
            self.raise_()
        
    def setup_display(self):
        if self.container_widget:
            self.layout().removeWidget(self.container_widget)
            self.container_widget.deleteLater()
        
        self.container_widget = QWidget()
        self.container_widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        font_size = 9 if self.small_hud else 11
        padding = (6 if self.small_hud else 18) if self.horizontal_display else (8 if self.small_hud else 18)
        spacing = 3 if self.small_hud else (8 if self.horizontal_display else 7)
        
        layout = QHBoxLayout() if self.horizontal_display else QVBoxLayout()
        margin_v = (4 if self.small_hud else 14) if self.horizontal_display else (6 if self.small_hud else 14)
        layout.setContentsMargins(padding, margin_v, padding, margin_v)
        layout.setSpacing(spacing)
        
        if not self.horizontal_display and self.small_hud:
            layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        optimal_size = self.calculate_optimal_size()
        self.setFixedSize(optimal_size.width(), optimal_size.height())
        
        if not self._positioned:
            self.move(self.saved_position)
            self._positioned = True
        
        metrics = self.get_metrics_list()
        
        style = f"""QLabel {{
            color: rgba(200, 200, 200, 200);
            font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
            font-size: {font_size}px;
            font-weight: 300;
            letter-spacing: 0.5px;
        }}"""
        
        separator_style = f"""QLabel {{
            color: rgba(100, 100, 100, 150);
            font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
            font-size: {font_size}px;
            font-weight: 300;
        }}"""
        
        for i, metric in enumerate(metrics):
            label_text = self.get_initial_label_text(metric)
            label = QLabel(label_text)
            label.setStyleSheet(style)
            
            if self.small_hud and not self.horizontal_display:
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            self.labels[metric] = label
            layout.addWidget(label)
            
            if self.horizontal_display and i < len(metrics) - 1:
                separator = QLabel("|")
                separator.setStyleSheet(separator_style)
                layout.addWidget(separator)
        
        self.container_widget.setLayout(layout)
        self.layout().addWidget(self.container_widget)
    
    def get_metrics_list(self):
        metrics = ['CPU', 'GPU', 'VRM', 'RAM']
        if self.show_signal:
            metrics.append('SIG')
        if self.show_connection:
            metrics.append('CON')
        if self.show_uptime:
            metrics.append('UPT')
        if self.show_speed:
            metrics.append('SPD')
        if self.show_storage:
            metrics.extend(self.disk_partitions)
        return metrics
    
    def get_initial_label_text(self, metric):
        if metric in ['SPD', 'CON', 'SIG', 'UPT']:
            return f'{metric} ---' if self.horizontal_display else f'{metric}    ---'
        return f'{metric} ---%' if self.horizontal_display else f'{metric:<4} ----%'
    
    def format_text(self, metric, value):
        if metric in ['SPD', 'CON', 'SIG', 'UPT']:
            return f'{metric} {value}' if self.horizontal_display else f'{metric}    {value}'
        if self.horizontal_display:
            return f'{metric} {value:>3.0f}%' if value is not None else f'{metric} N/A'
        return f'{metric}  {value:>4.0f}%' if value is not None else f'{metric}   N/A'
    
    def get_uptime_display(self):
        try:
            uptime_seconds = time.time() - psutil.boot_time()
            
            if uptime_seconds < 60:
                return "UPT"
            elif uptime_seconds < 3600:
                return f"{int(uptime_seconds // 60)}MN"
            elif uptime_seconds < 86400:
                return f"{int(uptime_seconds // 3600)}HR"
            elif uptime_seconds < 604800:
                return f"{int(uptime_seconds // 86400)}DY"
            elif uptime_seconds < 2592000:
                return f"{int(uptime_seconds // 604800)}WK"
            else:
                return f"{int(uptime_seconds // 2592000)}MH"
        except Exception:
            return "UPT"
    
    def update_uptime_display(self):
        if 'UPT' in self.labels:
            uptime_text = self.get_uptime_display()
            self.labels['UPT'].setText(self.format_text('UPT', uptime_text))
    
    def check_vpn_status(self):
        try:
            if sys.platform == 'win32':
                result = subprocess.run(['ipconfig', '/all'], capture_output=True, text=True, encoding='utf-8')
                if result.returncode != 0:
                    return False
                
                lines = result.stdout.split('\n')
                current_adapter = None
                current_adapter_content = []
                
                for line in lines:
                    line_stripped = line.strip()
                    
                    if 'adapter' in line_stripped.lower() and ':' in line_stripped:
                        if current_adapter and self._is_vpn_adapter_active(current_adapter, current_adapter_content):
                            return True
                        
                        current_adapter = line_stripped
                        current_adapter_content = []
                    else:
                        if current_adapter:
                            current_adapter_content.append(line_stripped)
                
                if current_adapter and self._is_vpn_adapter_active(current_adapter, current_adapter_content):
                    return True
            
            else:
                vpn_interfaces = []
                for interface, addresses in psutil.net_if_addrs().items():
                    if any(vpn in interface.lower() for vpn in ['nordlynx', 'openvpn', 'tun', 'tap']):
                        for item in addresses:
                            if item.family == socket.AF_INET and not item.address.startswith('169.254'):
                                vpn_interfaces.append(interface)
                                break
                
                if vpn_interfaces:
                    try:
                        result = subprocess.run(['ip', 'route', 'show', 'default'], capture_output=True, text=True)
                        if result.returncode == 0:
                            return any(interface in result.stdout for interface in vpn_interfaces)
                    except:
                        return len(vpn_interfaces) > 0
            
            return False
        except Exception:
            return False
    
    def _is_vpn_adapter_active(self, adapter_line, adapter_content):
        adapter_lower = adapter_line.lower()
        
        vpn_indicators = ['tap', 'tun', 'nordlynx', 'wireguard', 'openvpn']
        has_vpn_indicator = any(ind in adapter_lower for ind in vpn_indicators)
        
        if not has_vpn_indicator:
            for line in adapter_content:
                if 'description' in line.lower():
                    line_lower = line.lower()
                    if any(ind in line_lower for ind in vpn_indicators):
                        has_vpn_indicator = True
                        break
        
        if not has_vpn_indicator:
            return False
        
        is_disconnected = False
        has_ipv4 = False
        has_gateway = False
        has_dns = False
        
        for line in adapter_content:
            lower_line = line.lower()
            
            if 'media state' in lower_line and 'disconnected' in lower_line:
                is_disconnected = True
                
            if 'ipv4 address' in lower_line and '.' in line and not '169.254' in line:
                has_ipv4 = True
                
            if 'default gateway' in lower_line and ':' in line:
                has_gateway = True
                
            if 'dns servers' in lower_line and ':' in line:
                has_dns = True
        
        return not is_disconnected and has_ipv4 and has_gateway and has_dns
    
    def get_disk_partitions(self):
        partitions = []
        for partition in psutil.disk_partitions():
            if partition.device and not partition.mountpoint.startswith('/snap'):
                if sys.platform == 'win32':
                    partitions.append(partition.device.replace('\\', '/'))
                elif partition.mountpoint in ['/', '/home'] or partition.mountpoint.startswith('/mnt'):
                    name = partition.mountpoint if partition.mountpoint == '/' else partition.mountpoint.split('/')[-1]
                    partitions.append((name if name else 'mnt')[:4])
        return partitions[:4]
        
    def init_timers(self):
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_stats)
        self.timer.start(2000)
        self.update_stats()
        
        self.top_check_timer = QTimer()
        self.top_check_timer.timeout.connect(self.ensure_on_top)
        self.top_check_timer.start(500)
        
        self.speed_timer = QTimer()
        self.speed_timer.timeout.connect(self.test_speed)
        
        self.position_save_timer = QTimer()
        self.position_save_timer.timeout.connect(self.save_config)
        self.position_save_timer.start(30000)
        
        if self.show_speed:
            self.speed_timer.start(60000)
            QTimer.singleShot(2000, self.test_speed)
        
    def update_stats(self):
        if self.is_dragging:
            return
            
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            self.update_label('CPU', cpu_percent)
            
            gpu_percent = self.get_gpu_usage()
            self.update_label('GPU', gpu_percent)
            
            vram_percent = self.get_vram_usage()
            self.update_label('VRM', vram_percent)
            
            mem = psutil.virtual_memory()
            self.update_label('RAM', mem.percent)
            
            if self.show_connection:
                self.update_connection_status()
            
            if self.show_signal:
                self.update_signal_strength()
            
            if self.show_storage:
                self.update_disk_stats()
                
            if self.show_speed and 'SPD' in self.labels:
                self.update_speed_label()
                
            if self.show_uptime:
                self.update_uptime_display()
                
        except Exception:
            pass
    
    def update_connection_status(self):
        if 'CON' in self.labels:
            status_text = 'VPN' if self.check_vpn_status() else 'ISP'
            self.labels['CON'].setText(self.format_text('CON', status_text))
    
    def update_label(self, metric, value):
        if metric in self.labels:
            self.labels[metric].setText(self.format_text(metric, value))
    
    def update_speed_label(self):
        if 'SPD' in self.labels:
            if self.current_speed == 0:
                value = 'TST'
                self.labels['SPD'].setText(self.format_text('SPD', value))
            else:
                value = self.format_speed(self.current_speed)
                if not self.horizontal_display:
                    value = f"{value:>6}"
                formatted_value = f'SPD {value}' if self.horizontal_display else f'SPD {value}'
                self.labels['SPD'].setText(formatted_value)
    
    def format_speed(self, speed_mbps):
        if speed_mbps >= 1000:
            gb_speed = speed_mbps / 1000
            return f"{gb_speed:2.0f}GB" if gb_speed >= 10 else f"{gb_speed:3.1f}GB"
        return f"{speed_mbps:03.0f}"
    
    def test_speed(self):
        if not self.speed_test_running and self.show_speed:
            self.speed_test_running = True
            self.update_speed_label()
            thread = threading.Thread(target=self._run_speed_test)
            thread.daemon = True
            thread.start()
    
    def _run_speed_test(self):
        try:
            st = speedtest.Speedtest()
            st.get_best_server()
            download_speed = st.download() / 1_000_000
            self.speed_updated.emit(download_speed)
        except Exception:
            self.speed_updated.emit(0.0)
    
    def on_speed_updated(self, speed):
        self.current_speed = speed
        self.speed_test_running = False
        self.update_speed_label()
    
    def get_gpu_usage(self):
        try:
            import GPUtil
            gpus = GPUtil.getGPUs()
            return gpus[0].load * 100 if gpus else None
        except ImportError:
            try:
                result = subprocess.run(['nvidia-smi', '--query-gpu=utilization.gpu', '--format=csv,noheader,nounits'], capture_output=True, text=True)
                return float(result.stdout.strip()) if result.returncode == 0 else None
            except:
                return None
    
    def get_vram_usage(self):
        try:
            import GPUtil
            gpus = GPUtil.getGPUs()
            return (gpus[0].memoryUsed / gpus[0].memoryTotal) * 100 if gpus else None
        except ImportError:
            try:
                result = subprocess.run(['nvidia-smi', '--query-gpu=memory.used,memory.total', '--format=csv,noheader,nounits'], capture_output=True, text=True)
                if result.returncode == 0:
                    memory_info = result.stdout.strip().split(', ')
                    if len(memory_info) == 2:
                        return (float(memory_info[0]) / float(memory_info[1])) * 100
                return None
            except:
                return None
    
    def update_disk_stats(self):
        for partition in psutil.disk_partitions():
            key = self.get_partition_key(partition)
            
            if key and key in self.labels:
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    self.labels[key].setText(self.format_text(key, usage.percent))
                except:
                    text = f'{key} LKD' if self.horizontal_display else f'{key:<4}   LKD'
                    self.labels[key].setText(text)
    
    def get_partition_key(self, partition):
        if sys.platform == 'win32':
            return partition.device.replace('\\', '/')
        elif partition.mountpoint == '/':
            return '/'
        elif partition.mountpoint == '/home':
            return 'home'
        elif partition.mountpoint.startswith('/mnt'):
            return partition.mountpoint.split('/')[-1][:4]
        return None
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(15, 15, 18, 240))
        painter.drawRoundedRect(self.rect(), 6, 6)
        painter.setPen(QColor(40, 40, 45, 120))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 6, 6)
        
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.oldPos = event.globalPosition().toPoint()
            self.is_dragging = True
            self.timer.stop()
    
    def mouseMoveEvent(self, event):
        if self.oldPos and event.buttons() == Qt.MouseButton.LeftButton:
            delta = event.globalPosition().toPoint() - self.oldPos
            self.move(self.pos() + delta)
            self.oldPos = event.globalPosition().toPoint()
            
    def mouseReleaseEvent(self, event):
        if self.is_dragging:
            self.is_dragging = False
            self.oldPos = None
            self.save_config()
            QTimer.singleShot(100, lambda: (self.timer.start(2000), self.update_stats()))
    
    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: rgba(15, 15, 18, 240);
                color: rgba(200, 200, 200, 200);
                border: 1px solid rgba(40, 40, 45, 120);
                border-radius: 6px;
                font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
                font-size: 11px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 12px;
                border-radius: 3px;
                margin: 1px;
            }
            QMenu::item:selected {
                background-color: rgba(60, 60, 65, 180);
            }
            QMenu::item:checked {
                color: rgba(100, 180, 255, 255);
            }
        """)
        
        menu_items = [
            ("Always on Top", self.always_on_top, self.toggle_always_on_top),
            ("Horizontal Display", self.horizontal_display, self.toggle_display_mode),
            ("Small HUD", self.small_hud, self.toggle_small_hud),
            ("Connection", self.show_connection, self.toggle_connection_display),
            ("Signal", self.show_signal, self.toggle_signal_display),
            ("Storage", self.show_storage, self.toggle_storage_display),
            ("Speed", self.show_speed, self.toggle_speed_display),
            ("Uptime", self.show_uptime, self.toggle_uptime_display)
        ]
        
        for text, checked, handler in menu_items:
            action = QAction(text, self)
            action.setCheckable(True)
            action.setChecked(checked)
            action.triggered.connect(handler)
            menu.addAction(action)
        
        menu.addSeparator()
        
        close_action = QAction("Close", self)
        close_action.triggered.connect(QApplication.instance().quit)
        menu.addAction(close_action)
        
        menu.exec(event.globalPos())
    
    def toggle_always_on_top(self):
        self.always_on_top = not self.always_on_top
        self.update_window_flags()
        self.show()
        self.save_config()
        
    def animate_transition(self, callback):
        if self.is_transitioning:
            return
            
        self.is_transitioning = True
        current_rect = self.geometry()
        callback()
        new_size = self.calculate_optimal_size()
        new_rect = QRect(current_rect.x(), current_rect.y(), new_size.width(), new_size.height())
        
        self.fade_out = QPropertyAnimation(self, b"windowOpacity")
        self.fade_out.setDuration(150)
        self.fade_out.setStartValue(0.85)
        self.fade_out.setEndValue(0.0)
        self.fade_out.setEasingCurve(QEasingCurve.Type.OutQuad)
        
        self.resize_anim = QPropertyAnimation(self, b"geometry")
        self.resize_anim.setDuration(200)
        self.resize_anim.setStartValue(current_rect)
        self.resize_anim.setEndValue(new_rect)
        self.resize_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        self.fade_in = QPropertyAnimation(self, b"windowOpacity")
        self.fade_in.setDuration(150)
        self.fade_in.setStartValue(0.0)
        self.fade_in.setEndValue(0.85)
        self.fade_in.setEasingCurve(QEasingCurve.Type.InQuad)
        
        self.fade_out.finished.connect(lambda: self.resize_anim.start())
        self.resize_anim.finished.connect(lambda: (self.setup_display(), self.update_stats(), self.fade_in.start()))
        self.fade_in.finished.connect(lambda: setattr(self, 'is_transitioning', False))
        
        self.fade_out.start()
    
    def create_toggle_method(self, attr_name, timer_attr=None, interval=None, initial_delay=None, update_method_name=None):
        def toggle():
            value = not getattr(self, attr_name)
            setattr(self, attr_name, value)
            if value:
                if timer_attr and interval:
                    timer = getattr(self, timer_attr)
                    timer.start(interval)
                if update_method_name:
                    update_method = getattr(self, update_method_name)
                    if initial_delay is not None:
                        QTimer.singleShot(initial_delay, update_method)
                    else:
                        update_method()
            else:
                if timer_attr and interval:
                    timer = getattr(self, timer_attr)
                    timer.stop()
            self.save_config()
        return toggle
    
    def toggle_display_mode(self):
        self.animate_transition(self.create_toggle_method('horizontal_display'))
    
    def toggle_small_hud(self):
        self.animate_transition(self.create_toggle_method('small_hud'))
    
    def toggle_connection_display(self):
        self.animate_transition(self.create_toggle_method('show_connection', update_method_name='update_connection_status', initial_delay=None))
    
    def toggle_storage_display(self):
        self.animate_transition(self.create_toggle_method('show_storage', update_method_name='update_disk_stats', initial_delay=None))
    
    def toggle_speed_display(self):
        self.animate_transition(self.create_toggle_method('show_speed', timer_attr='speed_timer', interval=60000, initial_delay=None, update_method_name='test_speed'))
    
    def toggle_signal_display(self):
        self.animate_transition(self.create_toggle_method('show_signal', update_method_name='update_signal_strength', initial_delay=None))
    
    def toggle_uptime_display(self):
        self.animate_transition(self.create_toggle_method('show_uptime', update_method_name='update_uptime_display', initial_delay=None))
    
    def update_signal_status(self):
        if 'SIG' in self.labels:
            signal_text = self.current_signal
            if signal_text == "---":
                display_text = " ---"
                self.labels['SIG'].setText(self.format_text('SIG', display_text))
            else:
                display_text = f"{signal_text}%" if signal_text.strip().isdigit() else signal_text
                formatted_value = f'SIG {display_text}' if self.horizontal_display else f'SIG   {display_text}'
                self.labels['SIG'].setText(formatted_value)
    
    def update_signal_strength(self):
        self.current_signal = self.get_signal_strength()
        self.update_signal_status()
    
    def get_signal_strength(self):
        try:
            if sys.platform == 'win32':
                result = subprocess.run(['netsh', 'wlan', 'show', 'interfaces'], capture_output=True, text=True, encoding='utf-8')
                if result.returncode == 0:
                    for line in result.stdout.split('\n'):
                        if 'Signal' in line and '%' in line:
                            match = re.search(r'(\d+)%', line)
                            if match:
                                return f"{int(match.group(1)):3d}"
                    return "ETH" if self._has_ethernet_connection() else "---"
                return "ETH" if self._has_ethernet_connection() else "---"
            else:
                wireless_interfaces = [interface for interface, _ in psutil.net_if_addrs().items() if interface.startswith(('wlan', 'wifi'))]
                
                if wireless_interfaces:
                    try:
                        result = subprocess.run(['iwconfig', wireless_interfaces[0]], capture_output=True, text=True)
                        if result.returncode == 0:
                            match = re.search(r'Link Quality=(\d+)/(\d+)', result.stdout)
                            if match:
                                quality = int(match.group(1))
                                max_quality = int(match.group(2))
                                signal_percent = int((quality / max_quality) * 100)
                                return f"{signal_percent:3d}"
                    except:
                        pass
                
                return "ETH" if self._has_ethernet_connection() else "---"
        except Exception:
            return "---"
    
    def _has_ethernet_connection(self):
        try:
            for interface, addresses in psutil.net_if_addrs().items():
                if any(wireless in interface.lower() for wireless in ['wlan', 'wifi', 'wireless']):
                    continue
                
                for item in addresses:
                    if item.family == socket.AF_INET and not item.address.startswith('169.254'):
                        return True
            return False
        except:
            return False
    
    def calculate_optimal_size(self):
        font_size = 9 if self.small_hud else 11
        test_label = QLabel("RAM  100%")
        test_label.setStyleSheet(f"font-family: 'Consolas', 'Monaco', 'Courier New', monospace; font-size: {font_size}px; font-weight: 300; letter-spacing: 0.5px;")
        font_metrics = test_label.fontMetrics()
        
        metrics = self.get_metrics_list()
        
        if self.horizontal_display:
            text_width = sum(self.get_metric_width(m, font_metrics) for m in metrics)
            separator_width = font_metrics.horizontalAdvance("|" if self.small_hud else " | ")
            num_separators = len(metrics) - 1
            spacing = 3 if self.small_hud else 8
            padding = 6 if self.small_hud else 18
            
            width = text_width + (separator_width * num_separators) + (spacing * (len(metrics) + num_separators - 1)) + (padding * 2) + 10
            height = 28 if self.small_hud else 50
        else:
            text_width = max(self.get_metric_width(m, font_metrics) for m in metrics)
            padding = 8 if self.small_hud else 18
            width = text_width + 8 + (padding * 2)
            
            line_height = 14 if self.small_hud else 20
            height = 24 + (len(metrics) * line_height)
        
        return QSize(width, height)
    
    def get_metric_width(self, metric, font_metrics):
        if metric == 'SPD':
            return font_metrics.horizontalAdvance("SPD 10GB")
        elif metric == 'CON':
            return font_metrics.horizontalAdvance("CON VPN")
        elif metric == 'SIG':
            return font_metrics.horizontalAdvance("SIG 100%")
        elif metric == 'UPT':
            return font_metrics.horizontalAdvance("UPT 3MN")
        else:
            return font_metrics.horizontalAdvance(f"{metric} 100%")
    
    def ensure_on_top(self):
        if self.always_on_top and self.isVisible() and not self.is_dragging:
            if self.windowState() & Qt.WindowState.WindowMinimized:
                self.showNormal()
            if not self.isActiveWindow():
                self.raise_()
                QTimer.singleShot(100, lambda: self.raise_() if self.always_on_top else None)
        
    def enterEvent(self, event):
        self.setWindowOpacity(0.95)
        
    def leaveEvent(self, event):
        self.setWindowOpacity(0.85)
        
    def focusOutEvent(self, event):
        if self.always_on_top:
            QTimer.singleShot(100, self.raise_)
        super().focusOutEvent(event)
        
    def changeEvent(self, event):
        if event.type() == event.Type.WindowStateChange and self.always_on_top:
            if self.windowState() & Qt.WindowState.WindowMinimized:
                self.showNormal()
                self.raise_()
        super().changeEvent(event)

def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    hud = SystemMonitorHUD()
    hud.show()
    
    app.aboutToQuit.connect(hud.save_config)
    
    sys.exit(app.exec())

if __name__ == '__main__':
    main()