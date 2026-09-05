from flask import Flask, render_template, request, jsonify, Response, stream_with_context
import json
import traceback
import os
import sys
import time
import threading
import queue
import webbrowser

from automator import WebAutomator
from ai_agent import session_manager
from ai_providers import create_provider
from version import VERSION, APP_NAME

# ── PyInstaller path resolution ────────────────────────────────────────
# Khi đóng gói bằng PyInstaller:
#   sys.frozen = True
#   sys._MEIPASS = thư mục tạm chứa bundle (templates, static, ...)
#   sys.executable = đường dẫn tới .exe
# Khi chạy từ source code bình thường:
#   Tất cả đều dùng thư mục chứa app.py

if getattr(sys, 'frozen', False):
    BUNDLE_DIR = sys._MEIPASS          # Nơi chứa templates/static (read-only)
    APP_DIR    = os.path.dirname(sys.executable)  # Nơi chứa data người dùng (writable)
else:
    BUNDLE_DIR = os.path.dirname(os.path.abspath(__file__))
    APP_DIR    = BUNDLE_DIR

SCRIPTS_DIR = os.path.join(APP_DIR, 'scripts')
CONFIG_FILE = os.path.join(APP_DIR, 'config.json')

if not os.path.exists(SCRIPTS_DIR):
    os.makedirs(SCRIPTS_DIR)

# ── Flask App ──────────────────────────────────────────────────────────
app = Flask(
    __name__,
    template_folder=os.path.join(BUNDLE_DIR, 'templates'),
    static_folder=os.path.join(BUNDLE_DIR, 'static')
)

active_bots = []

# Queue toàn cục cho update progress (chỉ 1 update tại 1 thời điểm)
_update_queue: queue.Queue = None


def load_config() -> dict:
    """Đọc config.json, trả về dict."""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_config(config: dict):
    """Ghi config.json."""
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


# ── Existing Script Routes ─────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html', version=VERSION, app_name=APP_NAME)


@app.route('/run-script', methods=['POST'])
def run_script():
    data = request.json
    steps = data.get('steps', [])
    config = data.get('config', {})

    headless   = config.get('headless', False)
    slow_mo    = int(config.get('slow_mo', 50))
    browser_type = config.get('browser_type', 'chromium')
    keep_open  = config.get('keep_open', True)

    bot = WebAutomator(headless=headless, slow_mo=slow_mo, browser_type=browser_type)
    results = []

    try:
        bot.start()
        for step in steps:
            action   = step.get('action')
            selector = step.get('selector')
            value    = step.get('value')
            try:
                if action == 'navigate':
                    bot.navigate(value)
                    results.append({"step": step, "status": "success", "message": f"Navigated to {value}"})
                elif action == 'click_element':
                    bot.click_element(selector)
                    results.append({"step": step, "status": "success", "message": f"Clicked {selector}"})
                elif action == 'fill_input':
                    bot.fill_input(selector, value)
                    results.append({"step": step, "status": "success", "message": f"Filled {selector} with '{value}'"})
                elif action == 'fill_with_retry':
                    error_selector  = step.get('error_selector')
                    append_char     = step.get('append_char')
                    submit_selector = step.get('submit_selector')
                    final_text = bot.fill_with_retry(
                        selector=selector, text=value,
                        error_selector=error_selector, append_char=append_char,
                        submit_selector=submit_selector if submit_selector else None
                    )
                    results.append({"step": step, "status": "success", "message": f"Thành công nhập '{final_text}' vào {selector}"})
                elif action == 'get_text':
                    text = bot.get_text(selector)
                    results.append({"step": step, "status": "success", "message": f"Got text from {selector}: '{text}'"})
                elif action == 'drag_and_drop':
                    target = step.get('target')
                    bot.drag_and_drop(selector, target)
                    results.append({"step": step, "status": "success", "message": f"Dragged {selector} to {target}"})
                elif action == 'wait':
                    seconds = float(value)
                    bot.wait(seconds)
                    results.append({"step": step, "status": "success", "message": f"Waited {seconds} seconds"})
                else:
                    results.append({"step": step, "status": "error", "message": f"Unknown action: {action}"})
            except Exception as e:
                results.append({"step": step, "status": "error", "message": str(e)})
                break
        return jsonify({"status": "completed", "results": results})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e), "trace": traceback.format_exc()})
    finally:
        if keep_open and not headless:
            active_bots.append(bot)
        else:
            bot.stop()


@app.route('/api/scripts', methods=['GET'])
def list_scripts():
    scripts = []
    if os.path.exists(SCRIPTS_DIR):
        for f in os.listdir(SCRIPTS_DIR):
            if f.endswith('.json'):
                scripts.append(f[:-5])
    return jsonify(scripts)


@app.route('/api/scripts/<name>', methods=['GET'])
def get_script(name):
    path = os.path.join(SCRIPTS_DIR, f"{name}.json")
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return jsonify(json.load(f))
    return jsonify({"error": "Not found"}), 404


@app.route('/api/scripts/<name>', methods=['POST'])
def save_script(name):
    path = os.path.join(SCRIPTS_DIR, f"{name}.json")
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(request.json, f, indent=4)
    return jsonify({"status": "success"})


@app.route('/api/scripts/<name>', methods=['DELETE'])
def delete_script(name):
    path = os.path.join(SCRIPTS_DIR, f"{name}.json")
    if os.path.exists(path):
        os.remove(path)
        return jsonify({"status": "success"})
    return jsonify({"error": "Not found"}), 404


# ── AI Agent Routes ────────────────────────────────────────────────────

@app.route('/ai/start', methods=['POST'])
def ai_start():
    try:
        data         = request.json or {}
        goal         = data.get('goal', '').strip()
        start_url    = data.get('start_url', '').strip()
        provider_name= data.get('provider', 'gemini')
        api_key      = data.get('api_key', '').strip()
        model        = data.get('model') or None
        max_steps    = int(data.get('max_steps', 20))
        browser_type = data.get('browser_type', 'chromium')
        headless     = data.get('headless', False)

        if not goal:     return jsonify({"error": "Thiếu mục tiêu (goal)"}), 400
        if not start_url:return jsonify({"error": "Thiếu URL bắt đầu (start_url)"}), 400
        if not api_key:
            cfg     = load_config()
            api_key = cfg.get('ai_config', {}).get('providers', {}).get(provider_name, {}).get('api_key', '')
            if not api_key:
                return jsonify({"error": f"Thiếu API Key cho provider '{provider_name}'"}), 400

        provider   = create_provider(provider_name, api_key, model)
        session_id = session_manager.create_session(
            goal=goal, start_url=start_url, provider=provider,
            max_steps=max_steps, browser_type=browser_type, headless=headless
        )
        session_manager.start_session(session_id)
        return jsonify({"status": "started", "session_id": session_id, "stream_url": f"/ai/stream/{session_id}"})
    except Exception as e:
        return jsonify({"error": str(e), "trace": traceback.format_exc()}), 500


@app.route('/ai/stream/<session_id>', methods=['GET'])
def ai_stream(session_id):
    session = session_manager.get_session(session_id)
    if not session:
        return jsonify({"error": "Session không tồn tại"}), 404

    def generate():
        while True:
            new_events = session.get_new_events()
            for event in new_events:
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            if session.is_finished() and not session.get_new_events():
                yield 'data: {"type": "stream_end"}\n\n'
                break
            time.sleep(0.3)

    return Response(stream_with_context(generate()), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@app.route('/ai/stop/<session_id>', methods=['POST'])
def ai_stop(session_id):
    session = session_manager.get_session(session_id)
    if not session:
        return jsonify({"error": "Session không tồn tại"}), 404
    session_manager.stop_session(session_id)
    return jsonify({"status": "stopping", "session_id": session_id})


@app.route('/api/config', methods=['GET'])
def get_app_config():
    cfg = load_config()
    for p in cfg.get('ai_config', {}).get('providers', {}).values():
        if p.get('api_key'):
            p['api_key'] = '***'
    return jsonify(cfg)


@app.route('/api/config/ai', methods=['POST'])
def save_ai_config():
    data = request.json or {}
    cfg  = load_config()
    if 'ai_config' not in cfg:
        cfg['ai_config'] = {}
    if 'providers' not in cfg['ai_config']:
        cfg['ai_config']['providers'] = {}

    provider_name = data.get('provider')
    api_key       = data.get('api_key', '')
    model         = data.get('model', '')

    if provider_name:
        if provider_name not in cfg['ai_config']['providers']:
            cfg['ai_config']['providers'][provider_name] = {}
        if api_key:
            cfg['ai_config']['providers'][provider_name]['api_key'] = api_key
        if model:
            cfg['ai_config']['providers'][provider_name]['model'] = model

    cfg['ai_config']['default_provider'] = data.get('default_provider', provider_name)
    cfg['ai_config']['max_steps']        = int(data.get('max_steps', 20))
    save_config(cfg)
    return jsonify({"status": "saved"})


# ── Update Routes ──────────────────────────────────────────────────────

@app.route('/api/version', methods=['GET'])
def api_version():
    """Trả về thông tin version hiện tại của app."""
    is_frozen = getattr(sys, 'frozen', False)
    return jsonify({
        "version":    VERSION,
        "app_name":   APP_NAME,
        "is_packaged": is_frozen
    })


@app.route('/api/check-update', methods=['GET'])
def api_check_update():
    """Gọi GitHub API để kiểm tra bản cập nhật."""
    try:
        from updater import check_for_update
        result = check_for_update()
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e), "has_update": False}), 500


@app.route('/api/apply-update', methods=['POST'])
def api_apply_update():
    """
    Bắt đầu download + apply update.
    Stream progress về client qua SSE.
    """
    global _update_queue

    data         = request.json or {}
    download_url = data.get('download_url', '')
    if not download_url:
        return jsonify({"error": "Thiếu download_url"}), 400

    try:
        from updater import start_update_thread
        _update_queue = start_update_thread(download_url)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    def generate():
        while True:
            try:
                item = _update_queue.get(timeout=60)
                yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
                if item.get('status') in ('done', 'error'):
                    break
            except queue.Empty:
                # Heartbeat để giữ kết nối
                yield 'data: {"status":"waiting"}\n\n'

    return Response(stream_with_context(generate()), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@app.route('/api/install-browsers', methods=['POST'])
def api_install_browsers():
    """
    Cài đặt Playwright Chromium browser (lần đầu).
    Stream log ra client.
    """
    from updater import install_playwright_browsers

    browser_queue = queue.Queue()
    thread = threading.Thread(
        target=install_playwright_browsers,
        args=(browser_queue,),
        daemon=True
    )
    thread.start()

    def generate():
        while True:
            try:
                item = browser_queue.get(timeout=300)
                yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
                if item.get('status') in ('done', 'error'):
                    break
            except queue.Empty:
                yield 'data: {"status":"waiting"}\n\n'

    return Response(stream_with_context(generate()), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@app.route('/api/check-browsers', methods=['GET'])
def api_check_browsers():
    """Kiểm tra xem Playwright Chromium đã được cài chưa."""
    try:
        from updater import check_playwright_browsers
        installed = check_playwright_browsers()
        return jsonify({"installed": installed})
    except Exception as e:
        return jsonify({"installed": False, "error": str(e)})


# ── App Entry Point ────────────────────────────────────────────────────

def find_free_port(start: int = 5000) -> int:
    """Tìm port trống bắt đầu từ `start`."""
    import socket
    for port in range(start, start + 20):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('127.0.0.1', port))
                return port
        except OSError:
            continue
    return start  # fallback


def open_browser_delayed(url: str, delay: float = 1.5):
    """Mở trình duyệt sau một khoảng delay (để Flask khởi động xong)."""
    def _open():
        time.sleep(delay)
        webbrowser.open(url)
    threading.Thread(target=_open, daemon=True).start()


if __name__ == '__main__':
    is_packaged = getattr(sys, 'frozen', False)
    port = find_free_port(5000)
    url  = f"http://127.0.0.1:{port}"

    if is_packaged:
        # Chạy từ .exe: tự mở trình duyệt, không debug
        print(f"[Web Automator Studio v{VERSION}] Starting on {url}")
        open_browser_delayed(url)
        app.run(host='127.0.0.1', port=port, debug=False, threaded=True)
    else:
        # Chạy từ source: debug mode
        app.run(host='127.0.0.1', port=port, debug=True, threaded=True)
