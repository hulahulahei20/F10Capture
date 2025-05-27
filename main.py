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
import pystray
import tkinter as tk
from functools import partial
import sys # 导入 sys 模块
import configparser # 导入 configparser 模块
import tkinter.filedialog # 导入 filedialog 模块

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

def get_process_name_from_point(x, y):
    """
    根据屏幕坐标获取该位置上活动窗口的进程名称。
    """
    try:
        # 获取鼠标所在位置的窗口句柄
        hwnd = win32gui.WindowFromPoint((x, y))
        if hwnd:
            # 获取窗口的线程ID和进程ID
            thread_id, process_id = win32process.GetWindowThreadProcessId(hwnd)
            
            # 使用psutil获取进程名称
            try:
                process = psutil.Process(process_id)
                return process.name().replace(".exe", "") # 移除.exe后缀
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
        # 获取鼠标当前位置
        current_mouse_x, current_mouse_y = mouse.Controller().position

        # 获取当前屏幕的主进程名称 (此行保留，但其结果不再用于目录名)
        process_name = get_process_name_from_point(current_mouse_x, current_mouse_y)
        
        global CUSTOM_SCREENSHOT_DIR
        
        # 确定最终的截图保存目录
        if CUSTOM_SCREENSHOT_DIR and os.path.isdir(CUSTOM_SCREENSHOT_DIR):
            final_screenshot_base_dir = CUSTOM_SCREENSHOT_DIR
            print(f"使用自定义截图目录: {final_screenshot_base_dir}")
        else:
            final_screenshot_base_dir = BASE_SCREENSHOT_DIR
            print(f"使用默认截图根目录: {final_screenshot_base_dir}")

        # 构建截图保存目录，使用进程名称作为子目录
        screenshot_dir = os.path.join(final_screenshot_base_dir, process_name)
        
        # 确保目录存在
        os.makedirs(screenshot_dir, exist_ok=True)

        filename = os.path.join(screenshot_dir, f"{timestamp}.png")

        # 获取所有显示器信息
        monitors = get_monitors()

        target_monitor = None
        for m in monitors:
            # 判断鼠标是否在当前显示器范围内
            if m.x <= current_mouse_x < m.x + m.width and \
               m.y <= current_mouse_y < m.y + m.height:
                target_monitor = m
                break
        
        # 如果没有找到对应的显示器，则默认截取主屏幕
        if target_monitor is None and monitors:
            target_monitor = monitors[0]

        if target_monitor:
            # 获取屏幕的设备上下文
            hdesktop = win32gui.GetDesktopWindow()
            # 创建一个设备上下文
            desktop_dc = win32gui.GetWindowDC(hdesktop)
            img_dc = win32ui.CreateDCFromHandle(desktop_dc)
            
            # 创建一个内存设备上下文
            mem_dc = img_dc.CreateCompatibleDC()
            
            # 创建一个位图对象
            screenshot_bitmap = win32ui.CreateBitmap()
            screenshot_bitmap.CreateCompatibleBitmap(img_dc, target_monitor.width, target_monitor.height)
            mem_dc.SelectObject(screenshot_bitmap)
            
            # 将屏幕内容复制到位图
            mem_dc.BitBlt((0, 0), (target_monitor.width, target_monitor.height), 
                          img_dc, (target_monitor.x, target_monitor.y), win32con.SRCCOPY)
            
            # 获取位图数据并转换为PIL Image对象
            bmpinfo = screenshot_bitmap.GetInfo()
            bmpstr = screenshot_bitmap.GetBitmapBits(True)
            img = Image.frombuffer(
                'RGB',
                (bmpinfo['bmWidth'], bmpinfo['bmHeight']),
                bmpstr, 'raw', 'BGRX', 0, 1
            )
            img.save(filename)

            # 清理
            win32gui.DeleteObject(screenshot_bitmap.GetHandle())
            mem_dc.DeleteDC()
            img_dc.DeleteDC()
            win32gui.ReleaseDC(hdesktop, desktop_dc)

            print(f"截图已保存到: {filename}")
        else:
            print("未找到任何显示器信息，无法截图。")

    except Exception as e:
        print(f"截图失败: {e}")

def on_press(key):
    """
    处理键盘按下事件。
    """
    global KEYBINDING
    try:
        if key == KEYBINDING:
            print(f"检测到 {KEYBINDING} 键按下，正在截图当前屏幕...")
            take_screenshot_windows_api()
    except AttributeError:
        pass

def on_release(key): # 移除 injected 和 quit_callback 参数
    """
    处理键盘释放事件。
    """
    if key == keyboard.Key.esc:
        print("检测到Esc键按下，键盘监听器即将停止。")
        stop_listener_event.set() # 设置事件，通知监听器停止
        return False # 停止监听器

def start_keyboard_listener(): # 移除 quit_callback 参数
    """
    启动键盘监听器。
    """
    with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
        listener.join()

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
                    if hasattr(keyboard.Key, key_str):
                        KEYBINDING = getattr(keyboard.Key, key_str)
                    elif len(key_str) == 1:
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
    config['Settings']['keybinding'] = str(KEYBINDING).replace('Key.', '').replace("'", "")
    config['Settings']['custom_screenshot_dir'] = CUSTOM_SCREENSHOT_DIR
    with open(CONFIG_FILE, 'w', encoding='utf-8') as configfile:
        config.write(configfile)
    print("配置已保存。")

def setup_tray_icon(icon):
    """
    设置托盘图标和菜单。
    """
    icon.visible = True
    # 托盘图标将在 main 函数中以 detached 模式启动

def open_settings_window():
    """
    打开截图按键和保存路径设置窗口。
    """
    global KEYBINDING, CUSTOM_SCREENSHOT_DIR
    settings_window = tk.Toplevel()
    settings_window.title("设置")
    settings_window.geometry("450x350") # 调整窗口大小以适应更多内容和更好的布局
    settings_window.resizable(False, False)

    # 确保窗口在最上层
    settings_window.attributes("-topmost", True)

    # 截图按键设置
    key_frame = tk.LabelFrame(settings_window, text="截图按键设置")
    key_frame.pack(pady=10, padx=15, fill="x") # 使用pack，但增加padx

    current_key_label = tk.Label(key_frame, text=f"当前截图按键: {str(KEYBINDING).replace('Key.', '').replace("'", "")}")
    current_key_label.grid(row=0, column=0, columnspan=3, pady=5, padx=5, sticky="w")

    key_entry = tk.Entry(key_frame, width=30)
    key_entry.grid(row=1, column=0, pady=2, padx=5, sticky="ew")
    key_entry.insert(0, str(KEYBINDING).replace("Key.", "").replace("'", "")) # 显示当前按键

    # 监听按键输入，将第一个按下的键显示在输入框中
    listener_for_entry = None
    def on_key_press_for_entry(key):
        nonlocal listener_for_entry
        try:
            key_name = str(key).replace("Key.", "").replace("'", "")
            key_entry.delete(0, tk.END)
            key_entry.insert(0, key_name)
            if listener_for_entry:
                listener_for_entry.stop() # 停止监听
        except AttributeError:
            # 处理特殊键，如Shift, Ctrl等
            key_name = str(key).replace("Key.", "").replace("'", "")
            key_entry.delete(0, tk.END)
            key_entry.insert(0, key_name)
            if listener_for_entry:
                listener_for_entry.stop() # 停止监听

    def start_listening_for_entry():
        nonlocal listener_for_entry
        key_entry.delete(0, tk.END) # 清空输入框
        key_entry.insert(0, "按下任意键...")
        # 确保旧的监听器已停止
        if listener_for_entry and listener_for_entry.running:
            listener_for_entry.stop()
        listener_for_entry = keyboard.Listener(on_press=on_key_press_for_entry)
        listener_for_entry.start()

    listen_button = tk.Button(key_frame, text="点击设置新按键", command=start_listening_for_entry)
    listen_button.grid(row=1, column=1, pady=2, padx=5, sticky="ew")

    def save_keybinding_only():
        global KEYBINDING
        new_key_str = key_entry.get().strip()
        if new_key_str:
            try:
                if hasattr(keyboard.Key, new_key_str):
                    KEYBINDING = getattr(keyboard.Key, new_key_str)
                elif len(new_key_str) == 1:
                    KEYBINDING = keyboard.KeyCode.from_char(new_key_str)
                else:
                    tk.messagebox.showerror("错误", f"无法识别的按键: {new_key_str}")
                    print(f"无法识别的按键: {new_key_str}")
                    return
                current_key_label.config(text=f"当前截图按键: {str(KEYBINDING).replace('Key.', '').replace("'", "")}")
                print(f"截图按键已更新为: {KEYBINDING}")
                save_config() # 保存配置
            except Exception as e:
                tk.messagebox.showerror("错误", f"保存按键失败: {e}")
                print(f"保存按键失败: {e}")
        else:
            tk.messagebox.showwarning("警告", "按键绑定不能为空。")

    save_key_button = tk.Button(key_frame, text="保存按键", command=save_keybinding_only)
    save_key_button.grid(row=1, column=2, pady=2, padx=5, sticky="ew")

    key_frame.grid_columnconfigure(0, weight=1) # 让输入框可以扩展

    # 截图保存路径设置
    path_frame = tk.LabelFrame(settings_window, text="截图保存路径设置")
    path_frame.pack(pady=10, padx=15, fill="x") # 使用pack，但增加padx

    current_path_label = tk.Label(path_frame, text=f"当前自定义路径: {CUSTOM_SCREENSHOT_DIR if CUSTOM_SCREENSHOT_DIR else '未设置 (使用默认)'}")
    current_path_label.grid(row=0, column=0, columnspan=3, pady=5, padx=5, sticky="w")

    path_entry = tk.Entry(path_frame, width=40)
    path_entry.grid(row=1, column=0, pady=2, padx=5, sticky="ew")
    # 确保文本框显示当前实际使用的路径，如果自定义路径为空，则显示默认根目录
    path_entry.insert(0, CUSTOM_SCREENSHOT_DIR if CUSTOM_SCREENSHOT_DIR else os.path.abspath(BASE_SCREENSHOT_DIR))

    def browse_directory():
        folder_selected = tk.filedialog.askdirectory()
        if folder_selected:
            path_entry.delete(0, tk.END)
            path_entry.insert(0, folder_selected)

    browse_button = tk.Button(path_frame, text="浏览...", command=browse_directory)
    browse_button.grid(row=1, column=1, pady=2, padx=5, sticky="ew")

    def clear_custom_path():
        path_entry.delete(0, tk.END)
        path_entry.insert(0, os.path.abspath(BASE_SCREENSHOT_DIR)) # 清空时显示默认根目录的绝对路径
        current_path_label.config(text="当前自定义路径: 未设置 (使用默认)")
        global CUSTOM_SCREENSHOT_DIR
        CUSTOM_SCREENSHOT_DIR = "" # 清空全局变量
        save_config() # 保存配置
        print("自定义截图目录已清除，将使用默认路径。")

    clear_button = tk.Button(path_frame, text="清除自定义路径", command=clear_custom_path)
    clear_button.grid(row=2, column=0, pady=2, padx=5, sticky="ew")

    def save_path_only():
        global CUSTOM_SCREENSHOT_DIR
        new_custom_path = path_entry.get().strip()
        if new_custom_path:
            if os.path.isdir(new_custom_path):
                CUSTOM_SCREENSHOT_DIR = new_custom_path
                current_path_label.config(text=f"当前自定义路径: {CUSTOM_SCREENSHOT_DIR}")
                print(f"自定义截图目录已更新为: {CUSTOM_SCREENSHOT_DIR}")
                save_config() # 保存配置
            else:
                tk.messagebox.showerror("错误", f"无效的路径: {new_custom_path}\n请选择一个有效的文件夹。")
                print(f"无效的自定义路径: {new_custom_path}，将不保存此路径。")
                # 恢复显示旧的路径，或者清空如果之前就没有
                path_entry.delete(0, tk.END)
                path_entry.insert(0, CUSTOM_SCREENSHOT_DIR if CUSTOM_SCREENSHOT_DIR else BASE_SCREENSHOT_DIR)
        else: # 用户清空了路径，但没有点击“清除”按钮
            CUSTOM_SCREENSHOT_DIR = ""
            current_path_label.config(text="当前自定义路径: 未设置 (使用默认)")
            print("自定义截图目录已清除，将使用默认路径。")
            save_config() # 保存配置

    save_path_button = tk.Button(path_frame, text="保存路径", command=save_path_only)
    save_path_button.grid(row=2, column=1, pady=2, padx=5, sticky="ew")

    path_frame.grid_columnconfigure(0, weight=1) # 让路径输入框可以扩展

    # 当窗口关闭时，停止监听器
    def on_settings_window_close():
        if listener_for_entry and listener_for_entry.running:
            listener_for_entry.stop()
        settings_window.destroy()

    settings_window.protocol("WM_DELETE_WINDOW", on_settings_window_close)

    # 保持窗口在最上层，直到关闭
    settings_window.grab_set() # 模态窗口
    settings_window.wait_window() # 等待窗口关闭

def main():
    load_config() # 在程序启动时加载配置

    print("F12截图工具已启动，在后台运行。")
    print(f"截图将保存到 '自定义目录/[进程名称]/[日期时间].png' 或 '{BASE_SCREENSHOT_DIR}/[进程名称]/[日期时间].png' 文件夹。")
    print("程序将显示在系统托盘中。")
    # print("注意：请使用 'python start.bat' 命令运行此脚本。")

    # 尝试创建一个隐藏的Tkinter根窗口，以提供GUI事件循环
    root = tk.Tk()
    root.withdraw() # 隐藏窗口

    # 定义退出函数，它现在可以访问到 icon 和 root
    def quit_app(icon_obj, root_obj):
        icon_obj.stop() # 停止托盘图标
        stop_listener_event.set() # 设置事件，通知键盘监听器停止
        root_obj.quit() # 停止Tkinter主循环
        os._exit(0) # 强制终止程序，包括控制台

    # 创建托盘图标的 Image 对象
    try:
        image = Image.open("icon.png") # 尝试加载用户提供的图标
    except Exception:
        print("无法加载 icon.png，使用默认图标。")
        image = Image.new('RGB', (16, 16), (0, 0, 255)) # 创建一个蓝色方块作为默认图标

    # 创建 pystray.Icon 实例 (初始时不传入菜单)
    icon = pystray.Icon("F12Capture", image, "F12截图工具")

    # 将 icon 和 root 绑定到 quit_app 函数
    bound_quit_app = partial(quit_app, icon_obj=icon, root_obj=root)

    # 创建菜单，并使用 bound_quit_app 作为退出回调
    menu = (pystray.MenuItem('截图 (F12)', take_screenshot_windows_api),
            pystray.MenuItem('设置', open_settings_window), # 添加新的菜单项
            pystray.MenuItem('退出', lambda icon_param, item: bound_quit_app()))

    # 更新 icon 的菜单
    icon.menu = menu

    # 启动托盘图标 (detached 模式)
    icon.run_detached()

    # 启动键盘监听器在一个单独的线程中
    keyboard_thread = threading.Thread(target=start_keyboard_listener)
    keyboard_thread.daemon = True # 设置为守护线程
    keyboard_thread.start()

    # 启动Tkinter事件循环，保持程序运行
    root.mainloop()

if __name__ == "__main__":
    main()
