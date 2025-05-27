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

# 截图保存根目录
BASE_SCREENSHOT_DIR = "F12Capture"

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

        # 获取当前屏幕的主进程名称
        process_name = get_process_name_from_point(current_mouse_x, current_mouse_y)
        
        # 构建截图保存目录
        screenshot_dir = os.path.join(BASE_SCREENSHOT_DIR, process_name)
        if not os.path.exists(screenshot_dir):
            os.makedirs(screenshot_dir)

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
    try:
        if key == keyboard.Key.f12:
            print("检测到F12键按下，正在截图当前屏幕...")
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

def setup_tray_icon(icon):
    """
    设置托盘图标和菜单。
    """
    icon.visible = True
    # 托盘图标将在 main 函数中以 detached 模式启动

def main():
    print("F12截图工具已启动，在后台运行。")
    print(f"截图将保存到 '{BASE_SCREENSHOT_DIR}/[进程名称]/[日期时间].png' 文件夹。")
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
