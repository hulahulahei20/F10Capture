# -*- coding: utf-8 -*-
import os
import datetime
import threading
from pynput import keyboard, mouse
from screeninfo import get_monitors
from PIL import Image
import win32api
import win32gui
import win32ui
import win32con
import win32process
import psutil
import configparser
import sys

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QSystemTrayIcon, QMenu, QFileDialog,
    QMessageBox, QFrame, QSizePolicy
)
from PySide6.QtGui import QIcon, QAction, QKeySequence
from PySide6.QtCore import Qt, QThread, Signal, QSettings

# 配置文件路径
CONFIG_FILE = "config.ini"

# 截图保存根目录
BASE_SCREENSHOT_DIR = "ScreenShots"
# 用户自定义截图目录
CUSTOM_SCREENSHOT_DIR = ""

# 默认截图按键
KEYBINDING = keyboard.Key.f12 # 初始设置为F12

# 用于控制键盘监听器线程的事件
stop_listener_event = threading.Event()

class KeyboardListenerThread(QThread):
    """
    独立的线程用于监听键盘事件。
    """
    key_pressed = Signal(object)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.listener = None

    def run(self):
        with keyboard.Listener(on_press=self.on_press, on_release=self.on_release) as self.listener:
            self.listener.join()

    def on_press(self, key):
        self.key_pressed.emit(key)

    def on_release(self, key):
        if key == keyboard.Key.esc:
            print("检测到Esc键按下，键盘监听器即将停止。")
            stop_listener_event.set()
            return False # 停止监听器

    def stop(self):
        if self.listener:
            self.listener.stop()
        self.wait() # 等待线程结束

def get_process_name_from_point(x, y):
    """
    根据屏幕坐标获取该位置上活动窗口的进程名称。
    """
    try:
        hwnd = win32gui.WindowFromPoint((x, y))
        if hwnd:
            thread_id, process_id = win32process.GetWindowThreadProcessId(hwnd)
            try:
                process = psutil.Process(process_id)
                return process.name().replace(".exe", "")
            except psutil.NoSuchProcess:
                return "UnknownProcess"
        return "NoActiveWindow"
    except Exception as e:
        print(f"获取进程名称失败: {e}")
        return "ErrorProcess"

def take_screenshot_windows_api():
    """
    使用Windows API根据鼠标当前位置截取对应屏幕并保存到本地文件。
    """
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    try:
        current_mouse_x, current_mouse_y = mouse.Controller().position
        process_name = get_process_name_from_point(current_mouse_x, current_mouse_y)
        
        global CUSTOM_SCREENSHOT_DIR
        
        if CUSTOM_SCREENSHOT_DIR and os.path.isdir(CUSTOM_SCREENSHOT_DIR):
            final_screenshot_base_dir = CUSTOM_SCREENSHOT_DIR
            print(f"使用自定义截图目录: {final_screenshot_base_dir}")
        else:
            final_screenshot_base_dir = BASE_SCREENSHOT_DIR
            print(f"使用默认截图根目录: {final_screenshot_base_dir}")

        screenshot_dir = os.path.join(final_screenshot_base_dir, process_name)
        os.makedirs(screenshot_dir, exist_ok=True)

        filename = os.path.join(screenshot_dir, f"{timestamp}.png")

        monitors = get_monitors()

        target_monitor = None
        for m in monitors:
            if m.x <= current_mouse_x < m.x + m.width and \
               m.y <= current_mouse_y < m.y + m.height:
                target_monitor = m
                break
        
        if target_monitor is None and monitors:
            target_monitor = monitors[0]

        if target_monitor:
            hdesktop = win32gui.GetDesktopWindow()
            desktop_dc = win32gui.GetWindowDC(hdesktop)
            img_dc = win32ui.CreateDCFromHandle(desktop_dc)
            
            mem_dc = img_dc.CreateCompatibleDC()
            
            screenshot_bitmap = win32ui.CreateBitmap()
            screenshot_bitmap.CreateCompatibleBitmap(img_dc, target_monitor.width, target_monitor.height)
            mem_dc.SelectObject(screenshot_bitmap)
            
            mem_dc.BitBlt((0, 0), (target_monitor.width, target_monitor.height), 
                          img_dc, (target_monitor.x, target_monitor.y), win32con.SRCCOPY)
            
            bmpinfo = screenshot_bitmap.GetInfo()
            bmpstr = screenshot_bitmap.GetBitmapBits(True)
            img = Image.frombuffer(
                'RGB',
                (bmpinfo['bmWidth'], bmpinfo['bmHeight']),
                bmpstr, 'raw', 'BGRX', 0, 1
            )
            img.save(filename)

            win32gui.DeleteObject(screenshot_bitmap.GetHandle())
            mem_dc.DeleteDC()
            img_dc.DeleteDC()
            win32gui.ReleaseDC(hdesktop, desktop_dc)

            print(f"截图已保存到: {filename}")
        else:
            print("未找到任何显示器信息，无法截图。")

    except Exception as e:
        print(f"截图失败: {e}")

def load_config():
    """
    从配置文件加载设置。
    """
    global KEYBINDING, CUSTOM_SCREENSHOT_DIR
    config = configparser.ConfigParser()
    if os.path.exists(CONFIG_FILE):
        config.read(CONFIG_FILE, encoding='utf-8')
        if 'Settings' in config:
            if 'keybinding' in config['Settings']:
                key_str = config['Settings']['keybinding']
                try:
                    # PySide6的QKeySequence不支持pynput的Key对象，需要转换为字符串或Qt::Key枚举
                    # 这里我们仍然使用pynput的Key对象来处理键盘监听，但需要一个字符串表示来显示
                    if hasattr(keyboard.Key, key_str):
                        KEYBINDING = getattr(keyboard.Key, key_str)
                    elif len(key_str) == 1:
                        KEYBINDING = keyboard.KeyCode.from_char(key_str)
                    else:
                        # 尝试从字符串解析为KeyCode，如果失败则保持默认
                        KEYBINDING = keyboard.KeyCode.from_char(key_str)
                except Exception as e:
                    print(f"加载按键绑定失败: {e}")
            if 'custom_screenshot_dir' in config['Settings']:
                CUSTOM_SCREENSHOT_DIR = config['Settings']['custom_screenshot_dir']
                print(f"加载自定义截图目录: {CUSTOM_SCREENSHOT_DIR}")

def save_config():
    """
    保存设置到配置文件。
    """
    global KEYBINDING, CUSTOM_SCREENSHOT_DIR
    config = configparser.ConfigParser()
    config['Settings'] = {}
    # 将pynput的Key对象转换为字符串保存
    config['Settings']['keybinding'] = str(KEYBINDING).replace('Key.', '').replace("'", "")
    config['Settings']['custom_screenshot_dir'] = CUSTOM_SCREENSHOT_DIR
    with open(CONFIG_FILE, 'w', encoding='utf-8') as configfile:
        config.write(configfile)
    print("配置已保存。")

class SettingsWindow(QMainWindow):
    keybinding_changed = Signal(object) # 发送新的pynput Key对象
    path_changed = Signal(str) # 发送新的路径

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setFixedSize(600, 450) # 调整固定窗口大小，方便布局
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint) # 窗口置顶

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)
        self.layout.setContentsMargins(20, 20, 20, 20) # 增加边距
        self.layout.setSpacing(20) # 增加间距

        self.setStyleSheet("""
            QMainWindow {
                background-color: #f0f2f5; /* 浅灰色背景 */
            }
            QFrame {
                background-color: #ffffff; /* 白色背景 */
                border: 1px solid #e0e0e0; /* 浅边框 */
                border-radius: 8px; /* 圆角 */
                padding: 15px; /* 内部填充 */
            }
            QLabel {
                font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
                font-size: 14px;
                color: #333333; /* 深灰色字体 */
            }
            QLabel#current_key_label, QLabel#current_path_label {
                font-weight: bold;
                color: #007bff; /* 蓝色强调色 */
            }
            QLineEdit {
                border: 1px solid #cccccc; /* 浅灰色边框 */
                border-radius: 5px; /* 圆角 */
                padding: 8px; /* 内部填充 */
                font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
                font-size: 13px;
                color: #555555;
                background-color: #fdfdfd;
            }
            QLineEdit:read-only {
                background-color: #f5f5f5; /* 只读状态的背景色 */
            }
            QPushButton {
                background-color: #007bff; /* 蓝色背景 */
                color: white; /* 白色字体 */
                border: none;
                border-radius: 5px; /* 圆角 */
                padding: 8px 15px; /* 内部填充 */
                font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
                font-size: 13px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #0056b3; /* 悬停时的深蓝色 */
            }
            QPushButton:pressed {
                background-color: #004085; /* 按下时的更深蓝色 */
            }
            QPushButton#clear_button { /* 为清除按钮设置不同样式 */
                background-color: #dc3545; /* 红色 */
            }
            QPushButton#clear_button:hover {
                background-color: #c82333;
            }
            QPushButton#clear_button:pressed {
                background-color: #bd2130;
            }
        """)

        self.init_ui()

    def init_ui(self):
        # 截图按键设置
        key_frame = QFrame()
        key_frame.setObjectName("key_frame") # 添加对象名以便QSS选择器使用
        key_layout = QVBoxLayout(key_frame)
        key_layout.setContentsMargins(15, 15, 15, 15) # 调整内部边距
        key_layout.setSpacing(10) # 调整内部间距

        key_label_layout = QHBoxLayout()
        self.current_key_label = QLabel(f"当前截图按键: {str(KEYBINDING).replace('Key.', '').replace("'", "")}")
        self.current_key_label.setObjectName("current_key_label") # 添加对象名
        key_label_layout.addWidget(self.current_key_label)
        key_label_layout.addStretch()
        key_layout.addLayout(key_label_layout)

        key_input_layout = QHBoxLayout()
        self.key_entry = QLineEdit()
        self.key_entry.setPlaceholderText("按下任意键...")
        self.key_entry.setReadOnly(True) # 初始设置为只读
        self.key_entry.setText(str(KEYBINDING).replace("Key.", "").replace("'", ""))
        key_input_layout.addWidget(self.key_entry)

        self.listen_button = QPushButton("点击设置新按键")
        self.listen_button.clicked.connect(self.start_listening_for_entry)
        key_input_layout.addWidget(self.listen_button)

        self.save_key_button = QPushButton("保存按键")
        self.save_key_button.clicked.connect(self.save_keybinding_only)
        key_input_layout.addWidget(self.save_key_button)
        key_layout.addLayout(key_input_layout)
        
        self.layout.addWidget(key_frame)

        # 截图保存路径设置
        path_frame = QFrame()
        path_frame.setObjectName("path_frame") # 添加对象名
        path_layout = QVBoxLayout(path_frame)
        path_layout.setContentsMargins(15, 15, 15, 15) # 调整内部边距
        path_layout.setSpacing(10) # 调整内部间距

        path_label_layout = QHBoxLayout()
        self.current_path_label = QLabel(f"当前自定义路径: {CUSTOM_SCREENSHOT_DIR if CUSTOM_SCREENSHOT_DIR else '未设置 (使用默认)'}")
        self.current_path_label.setObjectName("current_path_label") # 添加对象名
        path_label_layout.addWidget(self.current_path_label)
        path_label_layout.addStretch()
        path_layout.addLayout(path_label_layout)

        path_input_layout = QHBoxLayout()
        self.path_entry = QLineEdit()
        self.path_entry.setReadOnly(True) # 初始设置为只读
        self.path_entry.setText(CUSTOM_SCREENSHOT_DIR if CUSTOM_SCREENSHOT_DIR else os.path.abspath(BASE_SCREENSHOT_DIR))
        path_input_layout.addWidget(self.path_entry)

        browse_button = QPushButton("浏览...")
        browse_button.clicked.connect(self.browse_directory)
        path_input_layout.addWidget(browse_button)
        path_layout.addLayout(path_input_layout)

        path_buttons_layout = QHBoxLayout()
        clear_button = QPushButton("清除自定义路径")
        clear_button.setObjectName("clear_button") # 添加对象名
        clear_button.clicked.connect(self.clear_custom_path)
        path_buttons_layout.addWidget(clear_button)

        save_path_button = QPushButton("保存路径")
        save_path_button.clicked.connect(self.save_path_only)
        path_buttons_layout.addWidget(save_path_button)
        path_layout.addLayout(path_buttons_layout)

        self.layout.addWidget(path_frame)
        self.layout.addStretch() # 填充剩余空间

        self.key_listener_for_entry = None

    def start_listening_for_entry(self):
        self.key_entry.setText("按下任意键...")
        self.key_entry.setReadOnly(False) # 允许输入
        self.key_entry.setFocus() # 聚焦输入框

        if self.key_listener_for_entry and self.key_listener_for_entry.running:
            self.key_listener_for_entry.stop()

        def on_key_press_for_entry(key):
            try:
                key_name = str(key).replace("Key.", "").replace("'", "")
                self.key_entry.setText(key_name)
                if self.key_listener_for_entry:
                    self.key_listener_for_entry.stop()
                self.key_entry.setReadOnly(True) # 恢复只读
            except AttributeError:
                key_name = str(key).replace("Key.", "").replace("'", "")
                self.key_entry.setText(key_name)
                if self.key_listener_for_entry:
                    self.key_listener_for_entry.stop()
                self.key_entry.setReadOnly(True) # 恢复只读

        self.key_listener_for_entry = keyboard.Listener(on_press=on_key_press_for_entry)
        self.key_listener_for_entry.start()

    def save_keybinding_only(self):
        global KEYBINDING
        new_key_str = self.key_entry.text().strip()
        if new_key_str:
            try:
                if hasattr(keyboard.Key, new_key_str):
                    KEYBINDING = getattr(keyboard.Key, new_key_str)
                elif len(new_key_str) == 1:
                    KEYBINDING = keyboard.KeyCode.from_char(new_key_str)
                else:
                    QMessageBox.critical(self, "错误", f"无法识别的按键: {new_key_str}")
                    print(f"无法识别的按键: {new_key_str}")
                    return
                self.current_key_label.setText(f"当前截图按键: {str(KEYBINDING).replace('Key.', '').replace("'", "")}")
                print(f"截图按键已更新为: {KEYBINDING}")
                save_config()
                self.keybinding_changed.emit(KEYBINDING) # 发送信号通知主窗口
            except Exception as e:
                QMessageBox.critical(self, "错误", f"保存按键失败: {e}")
                print(f"保存按键失败: {e}")
        else:
            QMessageBox.warning(self, "警告", "按键绑定不能为空。")

    def browse_directory(self):
        folder_selected = QFileDialog.getExistingDirectory(self, "选择截图保存目录", self.path_entry.text())
        if folder_selected:
            self.path_entry.setText(folder_selected)

    def clear_custom_path(self):
        self.path_entry.setText(os.path.abspath(BASE_SCREENSHOT_DIR))
        self.current_path_label.setText("当前自定义路径: 未设置 (使用默认)")
        global CUSTOM_SCREENSHOT_DIR
        CUSTOM_SCREENSHOT_DIR = ""
        save_config()
        print("自定义截图目录已清除，将使用默认路径。")
        self.path_changed.emit(CUSTOM_SCREENSHOT_DIR) # 发送信号通知主窗口

    def save_path_only(self):
        global CUSTOM_SCREENSHOT_DIR
        new_custom_path = self.path_entry.text().strip()
        if new_custom_path:
            if os.path.isdir(new_custom_path):
                CUSTOM_SCREENSHOT_DIR = new_custom_path
                self.current_path_label.setText(f"当前自定义路径: {CUSTOM_SCREENSHOT_DIR}")
                print(f"自定义截图目录已更新为: {CUSTOM_SCREENSHOT_DIR}")
                save_config()
                self.path_changed.emit(CUSTOM_SCREENSHOT_DIR) # 发送信号通知主窗口
            else:
                QMessageBox.critical(self, "错误", f"无效的路径: {new_custom_path}\n请选择一个有效的文件夹。")
                print(f"无效的自定义路径: {new_custom_path}，将不保存此路径。")
                self.path_entry.setText(CUSTOM_SCREENSHOT_DIR if CUSTOM_SCREENSHOT_DIR else os.path.abspath(BASE_SCREENSHOT_DIR))
        else:
            CUSTOM_SCREENSHOT_DIR = ""
            self.current_path_label.setText("当前自定义路径: 未设置 (使用默认)")
            print("自定义截图目录已清除，将使用默认路径。")
            save_config()
            self.path_changed.emit(CUSTOM_SCREENSHOT_DIR) # 发送信号通知主窗口

    def closeEvent(self, event):
        if self.key_listener_for_entry and self.key_listener_for_entry.running:
            self.key_listener_for_entry.stop()
        event.accept()

class F12CaptureApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("F12截图工具")
        self.setFixedSize(300, 150) # 主窗口可以小一点，因为主要通过托盘操作
        self.setWindowFlags(Qt.WindowStaysOnTopHint) # 主窗口也置顶

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)
        self.layout.setContentsMargins(20, 20, 20, 20) # 增加边距
        self.layout.setSpacing(15) # 增加间距
        self.layout.setAlignment(Qt.AlignCenter)

        self.setStyleSheet("""
            QMainWindow {
                background-color: #f0f2f5; /* 浅灰色背景 */
            }
            QLabel {
                font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
                font-size: 15px; /* 稍微大一点的字体 */
                color: #333333; /* 深灰色字体 */
                text-align: center;
            }
        """)

        self.status_label = QLabel("F12截图工具已启动，在后台运行。")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.status_label)

        self.keyboard_thread = None
        self.tray_icon = None
        self.settings_window = None

        self.init_tray_icon()
        self.start_keyboard_listener()
        self.hide() # 启动时隐藏主窗口，只显示托盘图标

    def init_tray_icon(self):
        self.tray_icon = QSystemTrayIcon(self)
        try:
            self.tray_icon.setIcon(QIcon("icon.png"))
        except Exception:
            print("无法加载 icon.png，使用默认图标。")
            # 创建一个默认图标，例如一个简单的蓝色方块
            pixmap = QIcon().fromTheme("applications-other") # 尝试使用系统主题图标
            if pixmap.isNull():
                # 如果系统主题图标也找不到，则创建一个空白图标
                pixmap = QIcon()
            self.tray_icon.setIcon(pixmap)

        self.tray_icon.setToolTip("F12截图工具")

        tray_menu = QMenu()

        screenshot_action = QAction("截图", self)
        screenshot_action.triggered.connect(take_screenshot_windows_api)
        # 设置快捷键，这里需要将pynput的Key对象转换为Qt的QKeySequence
        # 由于pynput的Key对象不直接对应QKeySequence，这里暂时不设置全局快捷键
        # 而是依赖pynput的监听器
        tray_menu.addAction(screenshot_action)

        settings_action = QAction("设置", self)
        settings_action.triggered.connect(self.open_settings_window)
        tray_menu.addAction(settings_action)

        exit_action = QAction("退出", self)
        exit_action.triggered.connect(self.quit_app)
        tray_menu.addAction(exit_action)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()

    def start_keyboard_listener(self):
        if self.keyboard_thread and self.keyboard_thread.isRunning():
            self.keyboard_thread.stop()
            self.keyboard_thread.wait() # 确保旧线程完全停止

        self.keyboard_thread = KeyboardListenerThread()
        self.keyboard_thread.key_pressed.connect(self.handle_key_press)
        self.keyboard_thread.start()
        print("键盘监听器已启动。")

    def handle_key_press(self, key):
        global KEYBINDING
        try:
            if key == KEYBINDING:
                print(f"检测到 {KEYBINDING} 键按下，正在截图当前屏幕...")
                take_screenshot_windows_api()
        except AttributeError:
            pass

    def open_settings_window(self):
        if self.settings_window is None:
            self.settings_window = SettingsWindow(self)
            self.settings_window.keybinding_changed.connect(self.update_keybinding)
            self.settings_window.path_changed.connect(self.update_path_display)
        self.settings_window.show()
        self.settings_window.activateWindow() # 激活窗口，使其获得焦点

    def update_keybinding(self, new_key):
        global KEYBINDING
        KEYBINDING = new_key
        # 重新启动键盘监听器以应用新的按键绑定
        self.start_keyboard_listener()
        print(f"主窗口已更新按键绑定为: {KEYBINDING}")

    def update_path_display(self, new_path):
        global CUSTOM_SCREENSHOT_DIR
        CUSTOM_SCREENSHOT_DIR = new_path
        print(f"主窗口已更新自定义路径为: {CUSTOM_SCREENSHOT_DIR}")

    def quit_app(self):
        print("正在退出应用程序...")
        if self.keyboard_thread and self.keyboard_thread.isRunning():
            self.keyboard_thread.stop()
        if self.tray_icon:
            self.tray_icon.hide()
        if self.settings_window:
            self.settings_window.close()
        QApplication.quit()

    def closeEvent(self, event):
        # 当主窗口关闭时，隐藏到托盘而不是退出
        self.hide()
        event.ignore() # 忽略关闭事件，防止程序退出

if __name__ == "__main__":
    load_config() # 在程序启动时加载配置
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False) # 即使所有窗口关闭，也不退出应用（因为有托盘图标）

    main_app = F12CaptureApp()
    sys.exit(app.exec())
