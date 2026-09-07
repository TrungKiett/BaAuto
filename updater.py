"""
Auto-Update Module
Kiểm tra và áp dụng bản cập nhật mới từ GitHub Releases.
"""

import os
import sys
import json
import queue
import threading
import subprocess
import tempfile
import time
from typing import Optional, Callable

import requests

from version import VERSION, GITHUB_OWNER, GITHUB_REPO, ASSET_FILENAME


# ── Version comparison ──────────────────────────────────────────────────

def _parse_version(v: str) -> tuple:
    """Chuyển chuỗi version '1.2.3' thành tuple (1, 2, 3) để so sánh."""
    v = v.strip().lstrip('v')
    try:
        return tuple(int(x) for x in v.split('.'))
    except ValueError:
        return (0, 0, 0)


def is_newer(latest: str, current: str) -> bool:
    """Kiểm tra xem latest có mới hơn current không."""
    return _parse_version(latest) > _parse_version(current)


# ── GitHub API ──────────────────────────────────────────────────────────

def check_for_update(timeout: int = 8) -> dict:
    """
    Gọi GitHub Releases API để kiểm tra bản cập nhật.

    Returns:
        {
            "has_update": bool,
            "current_version": str,
            "latest_version": str,
            "download_url": str | None,
            "release_notes": str,
            "error": str | None
        }
    """
    result = {
        "has_update": False,
        "current_version": VERSION,
        "latest_version": VERSION,
        "download_url": None,
        "release_notes": "",
        "error": None
    }

    # Không auto-update khi chạy từ source code (chỉ dùng khi đóng gói)
    if not getattr(sys, 'frozen', False):
        result["error"] = "dev_mode"
        return result

    # Chưa cấu hình GitHub
    if GITHUB_OWNER == "your-username":
        result["error"] = "not_configured"
        return result

    try:
        api_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
        resp = requests.get(
            api_url,
            timeout=timeout,
            headers={
                "User-Agent": f"WebAutomatorStudio/{VERSION}",
                "Accept": "application/vnd.github.v3+json"
            }
        )
        resp.raise_for_status()
        data = resp.json()

        latest_version = data.get("tag_name", VERSION).lstrip('v')
        release_notes  = data.get("body", "")

        # Tìm file exe trong danh sách assets
        download_url = None
        for asset in data.get("assets", []):
            if asset["name"].lower() == ASSET_FILENAME.lower():
                download_url = asset["browser_download_url"]
                break

        result.update({
            "has_update":      is_newer(latest_version, VERSION),
            "latest_version":  latest_version,
            "download_url":    download_url,
            "release_notes":   release_notes,
        })

    except requests.exceptions.ConnectionError:
        result["error"] = "no_internet"
    except requests.exceptions.Timeout:
        result["error"] = "timeout"
    except Exception as e:
        result["error"] = str(e)

    return result


# ── Download + Apply Update ─────────────────────────────────────────────

def download_update(download_url: str, progress_queue: queue.Queue) -> Optional[str]:
    """
    Tải file exe mới về máy, báo cáo tiến trình qua queue.

    Args:
        download_url: URL tải về từ GitHub Releases
        progress_queue: Queue để gửi progress events

    Returns:
        Đường dẫn file mới tải về, hoặc None nếu lỗi
    """
    try:
        # Xác định thư mục lưu (cùng thư mục với exe hiện tại)
        if getattr(sys, 'frozen', False):
            exe_dir = os.path.dirname(sys.executable)
        else:
            exe_dir = os.path.dirname(os.path.abspath(__file__))

        new_exe_path = os.path.join(exe_dir, f"_update_{ASSET_FILENAME}")

        progress_queue.put({"status": "downloading", "progress": 0, "message": "Đang kết nối..."})

        resp = requests.get(
            download_url,
            stream=True,
            timeout=300,
            headers={"User-Agent": f"WebAutomatorStudio/{VERSION}"}
        )
        resp.raise_for_status()

        total_size = int(resp.headers.get('content-length', 0))
        downloaded  = 0
        chunk_size  = 65536  # 64KB chunks

        with open(new_exe_path, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)

                    if total_size > 0:
                        pct = int(downloaded / total_size * 100)
                        mb_done  = downloaded / 1024 / 1024
                        mb_total = total_size / 1024 / 1024
                        progress_queue.put({
                            "status":     "downloading",
                            "progress":   pct,
                            "downloaded": round(mb_done, 1),
                            "total":      round(mb_total, 1),
                            "message":    f"Đang tải: {mb_done:.1f} / {mb_total:.1f} MB"
                        })

        progress_queue.put({"status": "downloaded", "progress": 100, "message": "Tải xong! Đang chuẩn bị cài đặt..."})
        return new_exe_path

    except Exception as e:
        progress_queue.put({"status": "error", "message": str(e)})
        return None


def apply_update(new_exe_path: str, progress_queue: queue.Queue):
    """
    Áp dụng bản cập nhật đã tải về:
    1. Tạo script batch để swap file
    2. Chạy script trong nền
    3. Thoát app hiện tại

    Args:
        new_exe_path: Đường dẫn file exe mới
        progress_queue: Queue để gửi status cuối cùng
    """
    try:
        if getattr(sys, 'frozen', False):
            current_exe = sys.executable
        else:
            # Dev mode - không thực sự swap
            progress_queue.put({"status": "error", "message": "Không thể cập nhật khi chạy ở chế độ development"})
            return

        exe_dir  = os.path.dirname(current_exe)
        bat_path = os.path.join(exe_dir, f"_update_swap_{os.getpid()}.cmd")
        log_path = os.path.join(exe_dir, "_update_result.log")

        # Tạo batch script để swap file
        bat_content = f"""@echo off
setlocal EnableExtensions
set "NEW_EXE={new_exe_path}"
set "CURRENT_EXE={current_exe}"
set "UPDATE_LOG={log_path}"
:wait_for_app_exit
tasklist /FI "PID eq {os.getpid()}" /NH | findstr /R /C:"\\<{os.getpid()}\\>" >nul
if not errorlevel 1 (
    timeout /t 1 /nobreak >nul
    goto wait_for_app_exit
)
move /Y "%NEW_EXE%" "%CURRENT_EXE%" >nul
if errorlevel 1 (
    >"%UPDATE_LOG%" echo Khong the thay the file app. Hay dong tat ca cua so Web Automator Studio va thu lai.
    del "%~f0"
    exit /b 1
)
>"%UPDATE_LOG%" echo Cap nhat thanh cong. Dang khoi dong lai app.
start "" "%CURRENT_EXE%"
del "%~f0"
"""
        # Nội dung chỉ có ASCII để cmd.exe luôn đọc đúng trên Windows.
        with open(bat_path, 'w', encoding='ascii') as f:
            f.write(bat_content)

        progress_queue.put({"status": "applying", "progress": 100, "message": "Đang áp dụng cập nhật..."})
        time.sleep(0.5)

        # Chạy batch script độc lập (không chờ)
        subprocess.Popen(
            ['cmd.exe', '/d', '/c', bat_path],
            # Tách process thay file khỏi app hiện tại để nó vẫn sống sau os._exit().
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP,
            close_fds=True
        )

        progress_queue.put({"status": "done", "message": "Cập nhật xong! App sẽ tự khởi động lại..."})
        time.sleep(1.5)

        # Thoát app hiện tại để batch script có thể swap file
        os._exit(0)

    except Exception as e:
        progress_queue.put({"status": "error", "message": f"Lỗi khi áp dụng: {str(e)}"})


def start_update_thread(download_url: str) -> queue.Queue:
    """
    Bắt đầu download + apply trong background thread.
    Trả về queue để theo dõi progress.
    """
    progress_queue = queue.Queue()

    def _worker():
        new_exe = download_update(download_url, progress_queue)
        if new_exe:
            apply_update(new_exe, progress_queue)

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    return progress_queue


# ── Playwright Browser Check ────────────────────────────────────────────

def check_playwright_browsers() -> bool:
    """Kiểm tra xem Playwright Chromium đã được cài chưa."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
        return True
    except Exception:
        return False


def install_playwright_browsers(progress_queue: queue.Queue):
    """Cài đặt Playwright browsers (Chromium) trong background."""
    try:
        progress_queue.put({"status": "installing", "message": "Đang cài đặt trình duyệt Chromium (~150MB)..."})

        # Tìm playwright driver
        try:
            from playwright._impl._driver import compute_driver_executable
            driver_path = compute_driver_executable()
            cmd = [str(driver_path), "install", "chromium"]
        except Exception:
            # Fallback: dùng subprocess
            cmd = [sys.executable, "-m", "playwright", "install", "chromium"]

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        )

        for line in process.stdout:
            line = line.strip()
            if line:
                progress_queue.put({"status": "installing", "message": line})

        process.wait()

        if process.returncode == 0:
            progress_queue.put({"status": "done", "message": "Cài đặt trình duyệt thành công!"})
        else:
            progress_queue.put({"status": "error", "message": "Cài đặt thất bại. Hãy thử lại."})

    except Exception as e:
        progress_queue.put({"status": "error", "message": str(e)})
