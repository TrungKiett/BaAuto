"""
AI Agent – Vòng lặp Observe → Think → Act
Tự động quan sát trang web và đưa ra quyết định bằng AI Vision.
"""

import json
import time
import threading
import uuid
from datetime import datetime

from playwright.sync_api import sync_playwright, Page

from ai_providers import create_provider, BaseAIProvider


def extract_dom_text(page: Page, max_length: int = 4000) -> str:
    """
    Trích xuất nội dung text có ý nghĩa từ DOM (không lấy script/style).
    Rút gọn để tiết kiệm token.
    """
    try:
        # Lấy text của body, bỏ qua whitespace thừa
        dom_text = page.evaluate("""
            () => {
                const body = document.body;
                if (!body) return '';
                
                // Lấy tất cả text nodes có nội dung
                const walker = document.createTreeWalker(
                    body,
                    NodeFilter.SHOW_TEXT,
                    {
                        acceptNode: (node) => {
                            const parent = node.parentElement;
                            if (!parent) return NodeFilter.FILTER_REJECT;
                            const tag = parent.tagName.toLowerCase();
                            if (['script', 'style', 'noscript', 'svg'].includes(tag))
                                return NodeFilter.FILTER_REJECT;
                            const text = node.textContent.trim();
                            if (text.length < 2) return NodeFilter.FILTER_REJECT;
                            return NodeFilter.FILTER_ACCEPT;
                        }
                    }
                );
                
                const texts = [];
                let node;
                while (node = walker.nextNode()) {
                    const text = node.textContent.trim();
                    if (text) texts.push(text);
                }
                
                // Cũng lấy inputs, buttons với placeholder/value
                const inputs = document.querySelectorAll('input, textarea, button, select, a[href]');
                const interactiveInfo = Array.from(inputs).map(el => {
                    const tag = el.tagName.toLowerCase();
                    const id = el.id ? `#${el.id}` : '';
                    const cls = el.className ? `.${el.className.split(' ').join('.')}` : '';
                    const placeholder = el.placeholder || '';
                    const value = el.value || '';
                    const text = el.textContent.trim() || '';
                    const href = el.href || '';
                    const type = el.type || '';
                    return `[${tag}${id}${cls}] type=${type} placeholder="${placeholder}" value="${value}" text="${text}" href="${href}"`;
                }).filter(s => s.length > 20);
                
                return '=== PAGE TEXT ===\\n' + texts.join('\\n') + 
                       '\\n\\n=== INTERACTIVE ELEMENTS ===\\n' + interactiveInfo.join('\\n');
            }
        """)
        
        url = page.url
        title = page.title()
        prefix = f"URL: {url}\nTITLE: {title}\n\n"
        
        full = prefix + (dom_text or "")
        return full[:max_length]
    except Exception as e:
        return f"Lỗi khi đọc DOM: {str(e)}"


def take_screenshot(page: Page) -> bytes:
    """Chụp screenshot trang hiện tại, trả về bytes."""
    try:
        return page.screenshot(type="png", full_page=False)
    except Exception:
        # Trang có thể đang navigate, thử lại
        time.sleep(1)
        return page.screenshot(type="png", full_page=False)


def find_element_by_description(page: Page, description: str) -> str | None:
    """
    Tìm selector phù hợp dựa trên mô tả text.
    Fallback khi AI không biết selector chính xác.
    """
    try:
        # Thử tìm button/link/input chứa text mô tả
        selector = page.evaluate(f"""
            (desc) => {{
                const lower = desc.toLowerCase();
                const candidates = document.querySelectorAll('button, a, input, [role="button"], [onclick]');
                for (const el of candidates) {{
                    const text = (el.textContent || el.value || el.placeholder || '').toLowerCase();
                    if (text.includes(lower) || lower.includes(text)) {{
                        // Tạo selector tương đối
                        if (el.id) return '#' + el.id;
                        if (el.name) return `[name="${{el.name}}"]`;
                        return null;
                    }}
                }}
                return null;
            }}
        """, description)
        return selector
    except Exception:
        return None


class AgentSession:
    """
    Quản lý một session chạy AI Agent.
    Chứa trạng thái, log, và điều khiển vòng lặp.
    """

    def __init__(self, session_id: str, goal: str, start_url: str,
                 provider: BaseAIProvider, max_steps: int = 20,
                 browser_type: str = "chromium", headless: bool = False):
        self.session_id = session_id
        self.goal = goal
        self.start_url = start_url
        self.provider = provider
        self.max_steps = max_steps
        self.browser_type = browser_type
        self.headless = headless

        self.status = "idle"  # idle | running | done | failed | stopped
        self.step_count = 0
        self.history = []
        self.logs = []  # List of log events để stream về UI
        self._log_index = 0  # Con trỏ để SSE biết gửi từ đâu
        self._stop_event = threading.Event()

        # Playwright objects
        self._playwright = None
        self._browser = None
        self._page = None

    def _emit(self, event_type: str, data: dict):
        """Thêm log event vào queue."""
        event = {
            "id": len(self.logs),
            "type": event_type,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "data": data
        }
        self.logs.append(event)

    def _start_browser(self):
        """Khởi động Playwright browser."""
        self._playwright = sync_playwright().start()
        
        browser_map = {
            "chromium": self._playwright.chromium,
            "firefox": self._playwright.firefox,
            "webkit": self._playwright.webkit,
        }
        browser_launcher = browser_map.get(self.browser_type, self._playwright.chromium)
        
        self._browser = browser_launcher.launch(headless=self.headless, slow_mo=50)
        context = self._browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        self._page = context.new_page()

    def _stop_browser(self):
        """Đóng browser và dọn dẹp."""
        try:
            if self._browser:
                self._browser.close()
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass

    def _execute_action(self, action: str, params: dict) -> str:
        """
        Thực thi một action trên trang.
        Returns: thông báo kết quả
        """
        page = self._page

        if action == "navigate":
            url = params.get("url", "")
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_load_state("networkidle", timeout=10000)
            return f"Đã điều hướng đến {url}"

        elif action == "click":
            selector = params.get("selector")
            description = params.get("description")

            if not selector and description:
                selector = find_element_by_description(page, description)

            if selector:
                page.click(selector, timeout=10000)
                return f"Đã click vào '{selector}'"
            else:
                raise Exception(f"Không tìm thấy element: {description or selector}")

        elif action == "type":
            selector = params.get("selector", "")
            text = params.get("text", "")
            page.type(selector, text, timeout=10000)
            return f"Đã nhập '{text}' vào '{selector}'"

        elif action == "clear_and_type":
            selector = params.get("selector", "")
            text = params.get("text", "")
            page.fill(selector, text, timeout=10000)
            return f"Đã xóa và nhập '{text}' vào '{selector}'"

        elif action == "scroll":
            direction = params.get("direction", "down")
            amount = params.get("amount", 300)
            delta_y = amount if direction == "down" else -amount
            delta_x = amount if direction == "right" else (-amount if direction == "left" else 0)
            page.mouse.wheel(delta_x, delta_y)
            return f"Đã cuộn {direction} {amount}px"

        elif action == "press_key":
            key = params.get("key", "Enter")
            page.keyboard.press(key)
            return f"Đã nhấn phím '{key}'"

        elif action == "wait":
            seconds = float(params.get("seconds", 1))
            time.sleep(seconds)
            return f"Đã chờ {seconds} giây"

        elif action == "get_text":
            selector = params.get("selector", "body")
            text = page.locator(selector).text_content(timeout=5000)
            return f"Text từ '{selector}': {text[:200]}"

        elif action == "screenshot":
            return "Đã chụp screenshot để quan sát"

        elif action == "done":
            summary = params.get("summary", "Hoàn thành")
            return f"DONE: {summary}"

        elif action == "fail":
            reason = params.get("reason", "Không rõ lý do")
            raise Exception(f"Agent thất bại: {reason}")

        else:
            raise Exception(f"Action không hợp lệ: {action}")

    def run(self):
        """
        Vòng lặp chính: Observe → Think → Act.
        Chạy trong background thread.
        """
        self.status = "running"
        self._emit("start", {
            "goal": self.goal,
            "start_url": self.start_url,
            "provider": self.provider.get_name(),
            "max_steps": self.max_steps
        })

        try:
            self._start_browser()
            self._emit("info", {"message": "Trình duyệt đã khởi động"})

            # Điều hướng đến URL ban đầu
            self._page.goto(self.start_url, wait_until="domcontentloaded", timeout=30000)
            self._page.wait_for_load_state("networkidle", timeout=10000)
            self._emit("info", {"message": f"Đã mở: {self.start_url}"})

            # Vòng lặp chính
            while self.step_count < self.max_steps and not self._stop_event.is_set():
                self.step_count += 1
                self._emit("thinking", {"step": self.step_count, "max": self.max_steps})

                # === OBSERVE ===
                try:
                    screenshot_bytes = take_screenshot(self._page)
                    dom_text = extract_dom_text(self._page)
                except Exception as e:
                    self._emit("error", {"message": f"Lỗi quan sát trang: {str(e)}"})
                    break

                # Lưu screenshot dưới dạng base64 để stream về UI
                import base64
                screenshot_b64 = base64.b64encode(screenshot_bytes).decode()

                # === THINK ===
                try:
                    decision = self.provider.decide_action(
                        goal=self.goal,
                        dom_text=dom_text,
                        history=self.history,
                        image_bytes=screenshot_bytes
                    )
                except Exception as e:
                    self._emit("error", {"message": f"Lỗi AI: {str(e)}"})
                    break

                action = decision.get("action", "fail")
                params = decision.get("params", {})
                reasoning = decision.get("reasoning", "")
                confidence = decision.get("confidence", 0)
                is_done = decision.get("done", False)

                self._emit("decision", {
                    "step": self.step_count,
                    "reasoning": reasoning,
                    "action": action,
                    "params": params,
                    "confidence": confidence,
                    "screenshot": screenshot_b64
                })

                # Kiểm tra nếu AI báo done
                if action == "done" or is_done:
                    summary = params.get("summary", "Đã hoàn thành mục tiêu")
                    self._emit("done", {"summary": summary, "steps": self.step_count})
                    self.status = "done"
                    break

                # Kiểm tra nếu AI báo fail
                if action == "fail":
                    reason = params.get("reason", "Không rõ lý do")
                    self._emit("failed", {"reason": reason, "steps": self.step_count})
                    self.status = "failed"
                    break

                # === ACT ===
                try:
                    result_msg = self._execute_action(action, params)
                    self._emit("action_result", {
                        "step": self.step_count,
                        "action": action,
                        "params": params,
                        "result": result_msg,
                        "success": True
                    })

                    # Lưu vào lịch sử
                    self.history.append({
                        "action": action,
                        "params": params,
                        "reasoning": reasoning,
                        "result": result_msg
                    })

                    # Chờ ngắn để trang cập nhật
                    time.sleep(0.5)

                except Exception as e:
                    error_msg = str(e)
                    self._emit("action_result", {
                        "step": self.step_count,
                        "action": action,
                        "params": params,
                        "result": error_msg,
                        "success": False
                    })
                    self.history.append({
                        "action": action,
                        "params": params,
                        "reasoning": reasoning,
                        "result": f"ERROR: {error_msg}"
                    })
                    # Không dừng, để AI tự quyết định bước tiếp theo

            # Hết max steps mà chưa xong
            if self.step_count >= self.max_steps and self.status == "running":
                self._emit("failed", {
                    "reason": f"Đã đạt giới hạn {self.max_steps} bước mà chưa hoàn thành mục tiêu",
                    "steps": self.step_count
                })
                self.status = "failed"

            # Bị dừng thủ công
            if self._stop_event.is_set() and self.status == "running":
                self._emit("stopped", {"steps": self.step_count, "message": "Đã dừng theo yêu cầu"})
                self.status = "stopped"

        except Exception as e:
            import traceback
            self._emit("error", {"message": str(e), "trace": traceback.format_exc()})
            self.status = "failed"

        finally:
            self._stop_browser()
            self._emit("end", {"status": self.status})

    def stop(self):
        """Dừng agent từ bên ngoài."""
        self._stop_event.set()

    def get_new_events(self) -> list:
        """Lấy các event mới chưa gửi (dùng cho SSE)."""
        new_events = self.logs[self._log_index:]
        self._log_index = len(self.logs)
        return new_events

    def is_finished(self) -> bool:
        return self.status in ("done", "failed", "stopped")


# ── Session Manager (singleton) ────────────────────────────────────────────────

class SessionManager:
    """Quản lý các agent sessions đang chạy."""

    def __init__(self):
        self._sessions: dict[str, AgentSession] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._lock = threading.Lock()

    def create_session(self, goal: str, start_url: str, provider: BaseAIProvider,
                       max_steps: int = 20, browser_type: str = "chromium",
                       headless: bool = False) -> str:
        """Tạo session mới và trả về session_id."""
        session_id = str(uuid.uuid4())[:8]
        session = AgentSession(
            session_id=session_id,
            goal=goal,
            start_url=start_url,
            provider=provider,
            max_steps=max_steps,
            browser_type=browser_type,
            headless=headless
        )
        with self._lock:
            self._sessions[session_id] = session
        return session_id

    def start_session(self, session_id: str):
        """Chạy session trong background thread."""
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session không tồn tại: {session_id}")

        thread = threading.Thread(target=session.run, daemon=True)
        thread.start()
        self._threads[session_id] = thread

    def get_session(self, session_id: str) -> AgentSession | None:
        return self._sessions.get(session_id)

    def stop_session(self, session_id: str):
        session = self._sessions.get(session_id)
        if session:
            session.stop()

    def cleanup_session(self, session_id: str):
        """Xóa session đã kết thúc."""
        with self._lock:
            self._sessions.pop(session_id, None)
            self._threads.pop(session_id, None)


# Singleton instance
session_manager = SessionManager()
