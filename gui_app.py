# -*- coding: utf-8 -*-
import os
import datetime
import threading
from pynput import keyboard, mouse
from screeninfo import get_monitors
from PIL import Image, ImageGrab # 导入ImageGrab
import win32api
import win32gui
import win32ui
import win32con
import win32process
import psutil
import configparser
import sys
import win32event
import winerror
from playsound import playsound # 导入playsound库
import ctypes # 导入ctypes

from ctypes.wintypes import MSG # 导入MSG结构体

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QSystemTrayIcon, QMenu, QFileDialog,
    QMessageBox, QFrame, QSizePolicy, QGridLayout, QScrollArea,
    QGraphicsScene, QGraphicsView, QGraphicsPixmapItem
)
from PySide6.QtGui import QIcon, QAction, QKeySequence, QPixmap, QImage, QPainter
from PySide6.QtCore import Qt, QThread, Signal, QSettings, QSize, QDir

# 配置文件路径
CONFIG_FILE = "config.ini"

# 互斥量名称，用于实现单例模式
MUTEX_NAME = "F10CaptureAppMutex"

# 截图保存根目录
BASE_SCREENSHOT_DIR = "ScreenShots"
# 用户自定义截图目录
CUSTOM_SCREENSHOT_DIR = ""

# 默认截图按键
KEYBINDING = keyboard.Key.f10 # 初始设置为F10


def get_foreground_process_name():
    """
    获取当前最上层（前景）窗口的进程名称。
    """
    try:
        hwnd = win32gui.GetForegroundWindow()
        if hwnd:
            thread_id, process_id = win32process.GetWindowThreadProcessId(hwnd)
            try:
                process = psutil.Process(process_id)
                return process.name().replace(".exe", "")
            except psutil.NoSuchProcess:
                return "UnknownProcess"
        return "NoActiveWindow"
    except Exception as e:
        print(f"获取前景进程名称失败: {e}")
        return "Erro  rProcess"

def save_process_icon(process_name, target_dir):
    """
    根据进程名称获取其可执行文件的图标并保存到指定目录。
    """
    icon_filename = os.path.join(target_dir, "icon.png")
    try:
        for proc in psutil.process_iter(['name', 'exe']):
            if proc.info['name'] and proc.info['name'].lower() == process_name.lower() + ".exe":
                exe_path = proc.info['exe']
                if exe_path and os.path.exists(exe_path):
                    try:
                        hicon = win32gui.ExtractIcon(0, exe_path, 0)
                        if hicon:
                            pixmap = QPixmap.fromImage(QImage.fromHICON(hicon))
                            if not pixmap.isNull():
                                pixmap.save(icon_filename, "PNG")
                                print(f"进程 '{process_name}' 的图标已保存到: {icon_filename}")
                            win32gui.DestroyIcon(hicon)
                            return True
                    except Exception as icon_e:
                        print(f"从 '{exe_path}' 提取并保存图标失败: {icon_e}")
                break
    except Exception as e:
        print(f"保存进程 '{process_name}' 图标失败: {e}")
    return False

def get_process_icon(folder_name): # 将参数名改为 folder_name 以更清晰地表示它现在是文件夹名
    """
    根据文件夹名称（通常是进程名称）获取其对应的图标。
    首先尝试从文件夹中加载预保存的图标，如果失败则尝试从实时进程中提取，
    最后回退到默认图标。
    """
    default_icon_path = "icon.png" # 默认图标路径
    if hasattr(sys, '_MEIPASS'):
        default_icon_path = os.path.join(sys._MEIPASS, default_icon_path)

    # 1. 尝试从文件夹中加载预保存的图标
    screenshot_base_dir = BASE_SCREENSHOT_DIR
    if CUSTOM_SCREENSHOT_DIR and os.path.isdir(CUSTOM_SCREENSHOT_DIR):
        screenshot_base_dir = CUSTOM_SCREENSHOT_DIR
    
    folder_full_path = os.path.join(screenshot_base_dir, folder_name)
    icon_in_folder_path = os.path.join(folder_full_path, "icon.png")

    if os.path.exists(icon_in_folder_path):
        pixmap = QPixmap(icon_in_folder_path)
        if not pixmap.isNull():
            print(f"从文件夹 '{folder_name}' 加载预保存图标。")
            return QIcon(pixmap)
        else:
            print(f"警告: 无法从 '{icon_in_folder_path}' 加载图标，尝试从实时进程获取。")

    # 2. 如果文件夹中没有预保存的图标，或者加载失败，则尝试从实时进程中提取
    process_name_for_live_lookup = folder_name # 这里的 folder_name 就是进程名
    try:
        for proc in psutil.process_iter(['name', 'exe']):
            if proc.info['name'] and proc.info['name'].lower() == process_name_for_live_lookup.lower() + ".exe":
                exe_path = proc.info['exe']
                if exe_path and os.path.exists(exe_path):
                    try:
                        hicon = win32gui.ExtractIcon(0, exe_path, 0)
                        if hicon:
                            pixmap = QPixmap.fromImage(QImage.fromHICON(hicon))
                            win32gui.DestroyIcon(hicon)
                            if not pixmap.isNull():
                                print(f"从实时进程 '{process_name_for_live_lookup}' 提取图标。")
                                return QIcon(pixmap)
                        else:
                            print(f"从 '{exe_path}' 提取图标失败: win32gui.ExtractIcon 返回空句柄。")
                    except Exception as icon_e:
                        print(f"从 '{exe_path}' 提取图标失败: {icon_e}")
                break
    except Exception as e:
        print(f"获取进程 '{process_name_for_live_lookup}' 图标失败: {e}")
    
    # 3. 如果上述方法都失败，返回默认图标
    print(f"未能为 '{folder_name}' 获取特定图标，使用默认图标。")
    return QIcon(default_icon_path)

def take_screenshot_windows_api():
    """
    使用Windows API根据鼠标当前位置截取对应屏幕并保存到本地文件。
    如果Windows API截图失败，则尝试使用ImageGrab进行全屏截图。
    """
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    current_mouse_x, current_mouse_y = mouse.Controller().position
    process_name = get_foreground_process_name() # 获取最上层窗口的进程名称
    
    global CUSTOM_SCREENSHOT_DIR
    
    if CUSTOM_SCREENSHOT_DIR and os.path.isdir(CUSTOM_SCREENSHOT_DIR):
        final_screenshot_base_dir = CUSTOM_SCREENSHOT_DIR
        print(f"使用自定义截图目录: {final_screenshot_base_dir}")
    else:
        final_screenshot_base_dir = BASE_SCREENSHOT_DIR
        print(f"使用默认截图根目录: {final_screenshot_base_dir}")

    screenshot_dir = os.path.join(final_screenshot_base_dir, process_name)
    os.makedirs(screenshot_dir, exist_ok=True)

    # 在保存截图之前，尝试保存进程图标
    save_process_icon(process_name, screenshot_dir)

    filename = os.path.join(screenshot_dir, f"{timestamp}.png")

    img = None
    try:
        monitors = get_monitors()
        target_monitor = None
        for m in monitors:
            if m.x <= current_mouse_x < m.x + m.width and \
               m.y <= current_mouse_y < m.y + m.height:
                target_monitor = m
                break
        
        if target_monitor is None and monitors:
            target_monitor = monitors[0] # 如果鼠标不在任何已知显示器上，则默认截取主显示器

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

            win32gui.DeleteObject(screenshot_bitmap.GetHandle())
            mem_dc.DeleteDC()
            img_dc.DeleteDC()
            win32gui.ReleaseDC(hdesktop, desktop_dc)
            print("使用Windows API成功截图。")
        else:
            print("未找到任何显示器信息，尝试使用ImageGrab进行全屏截图。")
            img = ImageGrab.grab() # 回退到ImageGrab进行全屏截图
            print("使用ImageGrab进行全屏截图。")

    except Exception as e:
        print(f"Windows API截图失败: {e}，尝试使用ImageGrab进行全屏截图。")
        try:
            img = ImageGrab.grab() # 回退到ImageGrab进行全屏截图
            print("使用ImageGrab进行全屏截图。")
        except Exception as grab_e:
            print(f"ImageGrab截图也失败: {grab_e}")
            img = None

    if img:
        try:
            img.save(filename)
            print(f"截图已保存到: {filename}")
            # 播放截图音效
            try:
                playsound('screenshot_sound.wav')
                print("截图音效已播放。")
            except Exception as sound_e:
                print(f"播放截图音效失败: {sound_e}")
        except Exception as save_e:
            print(f"保存截图文件失败: {save_e}")
    else:
        print("未能成功截图。")

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
                    # 尝试从字符串解析为pynput Key对象（如'f12' -> keyboard.Key.f12）
                    if hasattr(keyboard.Key, key_str.lower()):
                        KEYBINDING = getattr(keyboard.Key, key_str.lower())
                    elif len(key_str) == 1: # 尝试解析单个字符
                        KEYBINDING = keyboard.KeyCode.from_char(key_str)
                    else:
                        # 如果都不是，则尝试作为KeyCode处理，如果失败则保持默认
                        # 这一步可能需要更健壮的解析，但目前先这样
                        KEYBINDING = keyboard.KeyCode.from_char(key_str)
                        print(f"警告: 无法完全识别的按键字符串 '{key_str}'，尝试作为KeyCode处理。")
                except Exception as e:
                    print(f"加载按键绑定失败: {e}，将使用默认按键F10。")
                    KEYBINDING = keyboard.Key.f10 # 加载失败时恢复默认F10
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
        # 移除 setFixedSize 以允许窗口最大化和调整大小
        self.setWindowFlags(Qt.Window) # 确保窗口显示在任务栏并可最小化

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
            QLineEdit:focus {
                border: 1px solid #007bff; /* 聚焦时边框变为蓝色 */
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

from PySide6.QtWidgets import QStackedWidget # 导入QStackedWidget

class ViewScreenshotsWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("查看截图")
        self.resize(800, 600) # 设置默认大小，但允许用户调整和最大化
        self.setWindowFlags(Qt.Window)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.main_layout.setSpacing(15)

        self.setStyleSheet("""
            QMainWindow {
                background-color: #f0f2f5; /* 浅灰色背景 */
            }
            QFrame#itemFrame { /* 为项目容器定义样式 */
                background-color: #ffffff; /* 白色背景 */
                border: 1px solid #e0e0e0; /* 浅边框 */
                border-radius: 8px; /* 圆角 */
                padding: 10px; /* 内部填充 */
            }
            QFrame#itemFrame:hover { /* 鼠标悬停时背景变蓝 */
                background-color: #e0f2ff; /* 浅蓝色 */
                border: 1px solid #007bff; /* 蓝色边框 */
            }
            QLabel {
                font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
                font-size: 14px;
                color: #333333; /* 深灰色字体 */
            }
            QLabel#folder_name_label, QLabel#image_name_label {
                font-weight: bold;
                color: #007bff; /* 蓝色强调色 */
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
            QScrollArea {
                border: none; /* 移除滚动区域的边框 */
            }
            QGraphicsView {
                border: none; /* 移除图片查看器的边框 */
            }
            /* 调整网格布局中项目的对齐方式 */
            QGridLayout {
                alignment: Qt.AlignLeft | Qt.AlignTop;
            }
        """)

        self.stacked_widget = QStackedWidget(self)
        self.main_layout.addWidget(self.stacked_widget)

        # 文件夹视图
        self.folders_view_widget = QWidget()
        self.folders_view_layout = QVBoxLayout(self.folders_view_widget)
        self.folders_view_layout.setContentsMargins(0, 0, 0, 0)
        self.folders_view_layout.setSpacing(10)

        self.folders_scroll_area = QScrollArea(self)
        self.folders_scroll_area.setWidgetResizable(True)
        self.folders_content = QWidget()
        self.folders_scroll_area.setWidget(self.folders_content)
        self.folders_grid_layout = QGridLayout(self.folders_content)
        self.folders_grid_layout.setAlignment(Qt.AlignLeft | Qt.AlignTop) # 显式设置对齐方式
        self.folders_view_layout.addWidget(self.folders_scroll_area)
        self.stacked_widget.addWidget(self.folders_view_widget)

        # 图片视图
        self.images_view_widget = QWidget()
        self.images_view_layout = QVBoxLayout(self.images_view_widget)
        self.images_view_layout.setContentsMargins(0, 0, 0, 0)
        self.images_view_layout.setSpacing(10)

        self.back_button_layout = QHBoxLayout()
        self.back_button = QPushButton("返回文件夹列表")
        self.back_button.clicked.connect(self.show_folders_view)
        self.back_button_layout.addWidget(self.back_button)
        self.back_button_layout.addStretch()
        self.images_view_layout.addLayout(self.back_button_layout)

        self.images_scroll_area = QScrollArea(self)
        self.images_scroll_area.setWidgetResizable(True)
        self.images_content = QWidget()
        self.images_scroll_area.setWidget(self.images_content)
        self.images_grid_layout = QGridLayout(self.images_content)
        self.images_grid_layout.setAlignment(Qt.AlignLeft | Qt.AlignTop) # 显式设置对齐方式
        self.images_view_layout.addWidget(self.images_scroll_area)
        self.stacked_widget.addWidget(self.images_view_widget)

        # 全屏图片视图
        self.fullscreen_image_view_widget = QWidget()
        self.fullscreen_image_view_layout = QVBoxLayout(self.fullscreen_image_view_widget)
        self.fullscreen_image_view_layout.setContentsMargins(0, 0, 0, 0)
        self.fullscreen_image_view_layout.setSpacing(10)

        self.fullscreen_back_button_layout = QHBoxLayout()
        self.fullscreen_back_button = QPushButton("返回图片列表")
        self.fullscreen_back_button.clicked.connect(self.show_images_view_from_fullscreen)
        self.fullscreen_back_button_layout.addWidget(self.fullscreen_back_button)
        self.fullscreen_back_button_layout.addStretch()
        self.fullscreen_image_view_layout.addLayout(self.fullscreen_back_button_layout)

        self.fullscreen_graphics_scene = QGraphicsScene()
        self.fullscreen_graphics_view = QGraphicsView(self.fullscreen_graphics_scene)
        self.fullscreen_graphics_view.setRenderHint(QPainter.Antialiasing)
        self.fullscreen_graphics_view.setRenderHint(QPainter.SmoothPixmapTransform)
        # 移除QPainter.HighQualityAntialiasing，因为它在PySide6中不存在
        self.fullscreen_graphics_view.setDragMode(QGraphicsView.ScrollHandDrag) # 允许拖动
        self.fullscreen_graphics_view.setTransformationAnchor(QGraphicsView.AnchorUnderMouse) # 鼠标下缩放
        self.fullscreen_graphics_view.setResizeAnchor(QGraphicsView.AnchorUnderMouse) # 鼠标下调整大小

        self.fullscreen_image_view_layout.addWidget(self.fullscreen_graphics_view)
        self.stacked_widget.addWidget(self.fullscreen_image_view_widget)

        self.current_image_pixmap_item = None # 用于存储当前显示的QGraphicsPixmapItem

        self.load_screenshot_folders() # 初始加载文件夹视图
        self.show_folders_view() # 默认显示文件夹视图

    def show_folders_view(self):
        self.setWindowTitle("查看截图")
        self.stacked_widget.setCurrentWidget(self.folders_view_widget)
        self.load_screenshot_folders() # 每次返回时刷新文件夹列表

    def show_images_view_from_fullscreen(self):
        # 从全屏图片视图返回到图片列表视图
        self.setWindowTitle(f"查看截图 - {os.path.basename(self.current_folder_path)}")
        self.stacked_widget.setCurrentWidget(self.images_view_widget)
        # 不需要重新加载图片，因为current_folder_path已经设置，并且图片列表应该还在

    def load_screenshot_folders(self):
        # 清除现有内容
        while self.folders_grid_layout.count():
            item = self.folders_grid_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        screenshot_base_dir = BASE_SCREENSHOT_DIR
        if CUSTOM_SCREENSHOT_DIR and os.path.isdir(CUSTOM_SCREENSHOT_DIR):
            screenshot_base_dir = CUSTOM_SCREENSHOT_DIR

        print(f"DEBUG: 截图根目录: {screenshot_base_dir}")
        folders = [f for f in os.listdir(screenshot_base_dir) if os.path.isdir(os.path.join(screenshot_base_dir, f))]
        print(f"DEBUG: 识别到的截图文件夹: {folders}")
        
        row = 0
        col = 0
        for folder_name in sorted(folders):
            folder_path = os.path.join(screenshot_base_dir, folder_name)
            
            # 创建一个垂直布局来放置图标和文本
            item_layout = QVBoxLayout()
            item_layout.setAlignment(Qt.AlignCenter)

            # 获取进程图标
            process_icon = get_process_icon(folder_name)
            icon_label = QLabel()
            icon_label.setFixedSize(64, 64) # 图标大小
            icon_label.setAlignment(Qt.AlignCenter)
            icon_label.setPixmap(process_icon.pixmap(QSize(64, 64)))
            item_layout.addWidget(icon_label)

            name_label = QLabel(folder_name)
            name_label.setObjectName("folder_name_label") # 添加对象名
            name_label.setAlignment(Qt.AlignCenter)
            item_layout.addWidget(name_label)

            # 将布局添加到网格布局中
            container_widget = QFrame() # 使用QFrame作为容器
            container_widget.setObjectName("itemFrame") # 设置对象名以便QSS选择器使用
            container_widget.setLayout(item_layout)
            container_widget.setCursor(Qt.PointingHandCursor) # 设置手型光标
            container_widget.mousePressEvent = lambda event, path=folder_path: self.show_images_view(path)

            container_widget.setFixedSize(120, 120) # 设置固定大小，模拟大图标
            self.folders_grid_layout.addWidget(container_widget, row, col)
            
            col += 1
            if col >= 4: # 每行显示4个文件夹
                col = 0
                row += 1
        
        # 确保内容顶部对齐
        self.folders_grid_layout.setRowStretch(row, 1)
        # 将所有剩余的水平空间推到最右侧，确保内容靠左排列
        self.folders_grid_layout.setColumnStretch(self.folders_grid_layout.columnCount(), 1)

    def show_images_view(self, folder_path):
        self.current_folder_path = folder_path
        self.setWindowTitle(f"查看截图 - {os.path.basename(folder_path)}")
        self.stacked_widget.setCurrentWidget(self.images_view_widget)
        self.load_images_for_folder(folder_path)

    def load_images_for_folder(self, folder_path):
        # 清除现有内容
        while self.images_grid_layout.count():
            item = self.images_grid_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        print(f"DEBUG: 当前图片文件夹路径: {folder_path}")
        image_files = [f for f in os.listdir(folder_path) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')) and f.lower() != 'icon.png']
        print(f"DEBUG: 识别到的图片文件: {image_files}")
        
        row = 0
        col = 0
        for image_name in sorted(image_files):
            image_path = os.path.join(folder_path, image_name)
            
            # 创建一个垂直布局来放置图片和文件名
            item_layout = QVBoxLayout()
            item_layout.setAlignment(Qt.AlignCenter)
            item_layout.setSpacing(5) # 增加图片和名称之间的间距

            image_label = QLabel()
            image_label.setFixedSize(200, 150) # 预览图大小
            image_label.setAlignment(Qt.AlignCenter)
            # 移除这里的内联样式，使用QFrame的样式
            # image_label.setStyleSheet("border: 1px solid #e0e0e0; border-radius: 5px;") 

            try:
                pixmap = QPixmap(image_path)
                if not pixmap.isNull():
                    pixmap = pixmap.scaled(image_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    image_label.setPixmap(pixmap)
                else:
                    image_label.setText("无法加载图片")
            except Exception as e:
                image_label.setText(f"加载失败: {e}")
                print(f"加载图片 {image_path} 失败: {e}")

            name_label = QLabel(image_name)
            name_label.setObjectName("image_name_label") # 添加对象名
            name_label.setAlignment(Qt.AlignCenter)
            name_label.setWordWrap(True) # 自动换行
            item_layout.addWidget(image_label)
            item_layout.addWidget(name_label)

            # 将布局添加到网格布局中
            container_widget = QFrame() # 使用QFrame作为容器
            container_widget.setObjectName("itemFrame") # 设置对象名以便QSS选择器使用
            container_widget.setLayout(item_layout)
            container_widget.setCursor(Qt.PointingHandCursor) # 设置手型光标
            container_widget.mousePressEvent = lambda event, path=image_path: self.open_image_fullscreen(path)

            container_widget.setFixedSize(220, 200) # 增加高度以适应更大的间距和名称
            self.images_grid_layout.addWidget(container_widget, row, col)
            
            col += 1
            if col >= 4: # 每行显示4张图片
                col = 0
                row += 1
        
        # 确保内容顶部对齐
        self.images_grid_layout.setRowStretch(row, 1)
        # 将所有剩余的水平空间推到最右侧，确保内容靠左排列
        self.images_grid_layout.setColumnStretch(self.images_grid_layout.columnCount(), 1)

    def open_image_fullscreen(self, image_path):
        # 清除旧的图片
        self.fullscreen_graphics_scene.clear()
        self.current_image_pixmap_item = None

        pixmap = QPixmap(image_path)
        if not pixmap.isNull():
            self.current_image_pixmap_item = self.fullscreen_graphics_scene.addPixmap(pixmap)
            # 明确设置QGraphicsPixmapItem的变换模式为平滑
            self.current_image_pixmap_item.setTransformationMode(Qt.SmoothTransformation)
            self.fullscreen_graphics_view.fitInView(self.current_image_pixmap_item, Qt.KeepAspectRatio) # 适应视图大小
            self.setWindowTitle(f"查看截图 - {os.path.basename(image_path)}")
            self.stacked_widget.setCurrentWidget(self.fullscreen_image_view_widget)
        else:
            # 如果图片加载失败，显示错误信息并返回到图片列表
            QMessageBox.warning(self, "加载图片失败", f"无法加载图片: {os.path.basename(image_path)}")
            print(f"全屏显示图片 {image_path} 失败：无法加载。")
            self.show_images_view(self.current_folder_path) # 返回到图片列表

    def wheelEvent(self, event):
        # 仅在全屏图片视图激活时处理滚轮事件
        if self.stacked_widget.currentWidget() == self.fullscreen_image_view_widget:
            zoom_factor = 1.15 # 每次缩放的因子
            if event.angleDelta().y() > 0:
                # 向上滚动，放大
                self.fullscreen_graphics_view.scale(zoom_factor, zoom_factor)
            else:
                # 向下滚动，缩小
                self.fullscreen_graphics_view.scale(1 / zoom_factor, 1 / zoom_factor)
        else:
            super().wheelEvent(event) # 如果不在全屏视图，将事件传递给父类

class F10CaptureApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("F10截图工具")
        self.setFixedSize(300, 150) # 主窗口可以小一点，因为主要通过托盘操作
        # self.setWindowFlags(Qt.Window)
        # self.setWindowFlags(Qt.WindowStaysOnTopHint) # 主窗口也置顶

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

        self.status_label = QLabel(f"F10截图工具 (热键: {str(KEYBINDING).replace('Key.', '').replace("'", "")}) 已启动，在后台运行。")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.status_label)

        self.tray_icon = None
        self.settings_window = None
        self.view_screenshots_window = None # 新增：查看截图窗口实例
        self.HOTKEY_ID = 100 # 定义热键ID

        self.init_tray_icon()
        self.register_hotkey() # 注册全局热键
        self.hide() # 启动时隐藏主窗口，只显示托盘图标

    def init_tray_icon(self):
        self.tray_icon = QSystemTrayIcon(self)
        # 尝试从打包路径或当前目录加载图标
        icon_path = "icon.png"
        if hasattr(sys, '_MEIPASS'):
            icon_path = os.path.join(sys._MEIPASS, icon_path)
            print(f"从 _MEIPASS 加载图标: {icon_path}")
        else:
            print(f"从当前目录加载图标: {icon_path}")

        try:
            self.tray_icon.setIcon(QIcon(icon_path))
        except Exception as e:
            print(f"无法加载图标 {icon_path}: {e}，使用默认图标。")
            pixmap = QIcon().fromTheme("applications-other") # 尝试使用系统主题图标
            if pixmap.isNull():
                # 如果系统主题图标也找不到，则创建一个空白图标
                pixmap = QIcon()
            self.tray_icon.setIcon(pixmap)

        self.tray_icon.setToolTip("F10截图工具")

        tray_menu = QMenu()
        # 美化托盘菜单样式
        tray_menu.setStyleSheet("""
            QMenu {
                background-color: #ffffff; /* 白色背景 */
                border: 1px solid #e0e0e0; /* 浅灰色边框 */
                border-radius: 6px; /* 圆角 */
                padding: 5px; /* 内部填充 */
            }
            QMenu::item {
                padding: 8px 25px 8px 20px; /* 增加内边距 */
                background-color: transparent;
                color: #333333; /* 深灰色字体 */
                font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
                font-size: 13px;
            }
            QMenu::item:selected {
                background-color: #e0f2ff; /* 选中时的浅蓝色背景 */
                color: #007bff; /* 选中时的蓝色字体 */
                border-radius: 4px; /* 选中项圆角 */
            }
            QMenu::separator {
                height: 1px;
                background-color: #f0f0f0; /* 分隔线颜色 */
                margin: 5px 0px; /* 分隔线上下间距 */
            }
        """)

        screenshot_action = QAction("截图", self)
        screenshot_action.triggered.connect(take_screenshot_windows_api)
        tray_menu.addAction(screenshot_action)

        settings_action = QAction("设置", self)
        settings_action.triggered.connect(self.open_settings_window)
        tray_menu.addAction(settings_action)

        view_screenshots_action = QAction("查看", self)
        view_screenshots_action.triggered.connect(self.open_view_screenshots_window)
        tray_menu.addAction(view_screenshots_action)

        # 添加一个分隔线
        tray_menu.addSeparator()

        exit_action = QAction("退出", self)
        exit_action.triggered.connect(self.quit_app)
        tray_menu.addAction(exit_action)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()

    def get_vk_code(self, key_obj):
        """
        将pynput Key对象或字符串转换为Windows虚拟键码。
        """
        if isinstance(key_obj, keyboard.Key):
            if key_obj == keyboard.Key.f1: return win32con.VK_F1
            if key_obj == keyboard.Key.f2: return win32con.VK_F2
            if key_obj == keyboard.Key.f3: return win32con.VK_F3
            if key_obj == keyboard.Key.f4: return win32con.VK_F4
            if key_obj == keyboard.Key.f5: return win32con.VK_F5
            if key_obj == keyboard.Key.f6: return win32con.VK_F6
            if key_obj == keyboard.Key.f7: return win32con.VK_F7
            if key_obj == keyboard.Key.f8: return win32con.VK_F8
            if key_obj == keyboard.Key.f9: return win32con.VK_F9
            if key_obj == keyboard.Key.f10: return win32con.VK_F10
            if key_obj == keyboard.Key.f11: return win32con.VK_F11
            if key_obj == keyboard.Key.f12: return win32con.VK_F12
            # 可以根据需要添加其他特殊键的映射
        elif isinstance(key_obj, keyboard.KeyCode) and key_obj.char:
            return ord(key_obj.char.upper()) # 对于普通字符，转换为大写字母的ASCII值
        elif isinstance(key_obj, str):
            if len(key_obj) == 1:
                return ord(key_obj.upper())
            elif key_obj.lower() == 'f10': # 兼容字符串'f10'
                return win32con.VK_F10
            # 可以添加其他字符串到VK_CODE的映射
        return None

    def register_hotkey(self):
        """
        注册全局热键。
        """
        # 注销旧热键（如果存在）
        try:
            win32gui.UnregisterHotKey(self.winId().__int__(), self.HOTKEY_ID)
            print("旧热键已注销。")
        except Exception as e:
            # 1419 是 ERROR_HOTKEY_NOT_REGISTERED，表示热键未注册，这是正常情况
            if e.args[0] == 1419:
                print("信息: 热键未注册，无需注销。")
            else:
                print(f"注销旧热键时发生未知错误: {e}")

        # 注册新热键
        try:
            vk_code = self.get_vk_code(KEYBINDING)
            if vk_code is not None:
                # MOD_NOREPEAT 标志可以防止热键重复触发
                win32gui.RegisterHotKey(self.winId().__int__(), self.HOTKEY_ID, win32con.MOD_NOREPEAT, vk_code)
                print(f"全局热键 {str(KEYBINDING).replace('Key.', '').replace("'", "")} (VK_CODE: {vk_code}) 已注册。")
            else:
                QMessageBox.critical(self, "错误", f"无法注册热键: {str(KEYBINDING).replace('Key.', '').replace("'", "")}\n未找到对应的虚拟键码。")
                print(f"无法注册热键: {KEYBINDING}，未找到对应的虚拟键码。")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"注册全局热键失败: {e}\n请尝试以管理员身份运行程序。")
            print(f"注册全局热键失败: {e}")

    def unregister_hotkey(self):
        """
        注销全局热键。
        """
        try:
            win32gui.UnregisterHotKey(self.winId().__int__(), self.HOTKEY_ID)
            print("全局热键已注销。")
        except Exception as e:
            print(f"注销全局热键失败: {e}")

    def nativeEvent(self, eventType, message):
        """
        处理Windows原生消息，包括热键消息。
        """
        if eventType == "windows_generic_MSG":
            # message 是一个指向 MSG 结构体的指针
            # 将 message 转换为 ctypes 的指针
            msg_ptr = ctypes.cast(message.__int__(), ctypes.POINTER(MSG))
            msg = msg_ptr.contents # 获取 MSG 结构体的内容

            if msg.message == win32con.WM_HOTKEY:
                hotkey_id = win32api.LOWORD(msg.wParam)
                if hotkey_id == self.HOTKEY_ID:
                    print("检测到全局热键按下！正在截图...")
                    take_screenshot_windows_api()
                    return True, 0 # 消息已处理
        return False, 0 # 消息未处理

    def open_settings_window(self):
        if self.settings_window is None:
            self.settings_window = SettingsWindow() # 移除父窗口，使其成为独立的顶级窗口
            self.settings_window.keybinding_changed.connect(self.update_keybinding)
            self.settings_window.path_changed.connect(self.update_path_display)
        self.settings_window.show()
        self.settings_window.activateWindow() # 激活窗口，使其获得焦点

    def update_keybinding(self, new_key):
        global KEYBINDING
        KEYBINDING = new_key
        # 重新注册全局热键以应用新的按键绑定
        self.register_hotkey()
        print(f"主窗口已更新按键绑定为: {KEYBINDING}")

    def update_path_display(self, new_path):
        global CUSTOM_SCREENSHOT_DIR
        CUSTOM_SCREENSHOT_DIR = new_path
        print(f"主窗口已更新自定义路径为: {CUSTOM_SCREENSHOT_DIR}")

    def open_view_screenshots_window(self):
        if self.view_screenshots_window is None:
            self.view_screenshots_window = ViewScreenshotsWindow()
        self.view_screenshots_window.show()
        self.view_screenshots_window.activateWindow()

    def quit_app(self):
        print("正在退出应用程序...")
        self.unregister_hotkey() # 退出前注销热键
        if self.tray_icon:
            self.tray_icon.hide()
        if self.settings_window:
            self.settings_window.close()
        if self.view_screenshots_window: # 关闭查看截图窗口
            self.view_screenshots_window.close()
        QApplication.quit()

    def closeEvent(self, event):
        # 当主窗口关闭时，隐藏到托盘而不是退出
        self.hide()
        event.ignore() # 忽略关闭事件，防止程序退出

if __name__ == "__main__":
    # 尝试创建命名互斥量，不立即拥有
    mutex = win32event.CreateMutex(None, 0, MUTEX_NAME)
    last_error = win32api.GetLastError()

    # 尝试获取互斥量，0毫秒等待，立即返回
    wait_result = win32event.WaitForSingleObject(mutex, 0)

    if wait_result == win32con.WAIT_OBJECT_0:
        # 成功获取互斥量，表示当前是唯一实例
        # 如果 last_error 是 ERROR_ALREADY_EXISTS，说明互斥量之前存在但现在可以获取了（可能之前的实例异常退出）
        if last_error == winerror.ERROR_ALREADY_EXISTS:
            print("信息: 互斥量已存在，但成功获取。可能之前的实例异常退出。")
        
        # 程序首次运行或之前的实例异常退出
        load_config() # 在程序启动时加载配置
        app = QApplication(sys.argv) # 确保只在这里创建 QApplication 实例
        app.setQuitOnLastWindowClosed(False) # 即使所有窗口关闭，也不退出应用（因为有托盘图标）

        main_app = F10CaptureApp()
        exit_code = app.exec()

        # 释放互斥量
        win32event.ReleaseMutex(mutex)
        win32api.CloseHandle(mutex)
        sys.exit(exit_code)
    else:
        # 无法获取互斥量，说明有其他实例正在运行
        print("警告: 无法获取互斥量，程序已在运行。")
        app_instance = QApplication.instance()
        if app_instance is None:
            app_instance = QApplication(sys.argv) # 仅在没有实例时创建

        msg_box = QMessageBox()
        msg_box.setIcon(QMessageBox.Warning)
        msg_box.setWindowTitle("F10截图工具")
        msg_box.setText("F10截图工具已在运行。")
        msg_box.setInformativeText("请勿重复启动。")
        msg_box.setStandardButtons(QMessageBox.Ok)
        msg_box.exec()
        sys.exit(0) # 退出当前实例
