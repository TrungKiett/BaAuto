"""Google OAuth and per-user Supabase script storage for the desktop app."""

import base64
import hashlib
import json
import os
import secrets
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, quote, urlencode, urlparse

import requests


SUPABASE_URL = os.getenv("SUPABASE_URL", "https://klsavdaeflotruknwmzx.supabase.co").rstrip("/")
# A publishable key is intentionally used in a desktop application. Access is
# restricted by the Row Level Security policies in supabase_schema.sql.
SUPABASE_PUBLISHABLE_KEY = os.getenv(
    "SUPABASE_PUBLISHABLE_KEY", "sb_publishable__qH7uM9lFoBF-BHyJcFTDw_7GqSrlLY"
)
CALLBACK_URL = "http://127.0.0.1:43899/auth/callback"


class AuthService:
    def __init__(self, app_dir: str):
        self.session_path = os.path.join(app_dir, "auth_session.json")
        self._lock = threading.Lock()
        self._session = self._read_session()
        self._login_error = None
        self._login_in_progress = False

    def _read_session(self):
        try:
            with open(self.session_path, "r", encoding="utf-8") as file:
                return json.load(file)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None

    def _save_session(self, session):
        with open(self.session_path, "w", encoding="utf-8") as file:
            json.dump(session, file, ensure_ascii=False)

    @staticmethod
    def _safe_user(user):
        if not user:
            return None
        metadata = user.get("user_metadata") or {}
        return {
            "id": user.get("id"),
            "email": user.get("email"),
            "name": metadata.get("full_name") or metadata.get("name") or user.get("email"),
            "avatar_url": metadata.get("avatar_url"),
        }

    def _headers(self):
        if not self._session or not self._session.get("access_token"):
            raise PermissionError("Bạn chưa đăng nhập Google.")
        return {
            "apikey": SUPABASE_PUBLISHABLE_KEY,
            "Authorization": f"Bearer {self._session['access_token']}",
            "Content-Type": "application/json",
        }

    def status(self):
        with self._lock:
            session = self._session
            return {
                "authenticated": bool(session and session.get("access_token")),
                "user": self._safe_user((session or {}).get("user")),
                "login_in_progress": self._login_in_progress,
                "error": self._login_error,
            }

    def start_google_login(self):
        with self._lock:
            if self._login_in_progress:
                return
            self._login_in_progress = True
            self._login_error = None

        verifier = base64.urlsafe_b64encode(secrets.token_bytes(48)).rstrip(b"=").decode("ascii")
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode("ascii")).digest()
        ).rstrip(b"=").decode("ascii")
        threading.Thread(
            target=self._run_login, args=(verifier, challenge), daemon=True
        ).start()

    def _run_login(self, verifier, challenge):
        try:
            auth_response = requests.get(
                f"{SUPABASE_URL}/auth/v1/authorize",
                params={
                    "provider": "google",
                    "redirect_to": CALLBACK_URL,
                    "code_challenge": challenge,
                    "code_challenge_method": "s256",
                },
                headers={"apikey": SUPABASE_PUBLISHABLE_KEY},
                allow_redirects=False,
                timeout=15,
            )
            if auth_response.status_code not in (301, 302, 303, 307, 308):
                raise RuntimeError("Không thể bắt đầu đăng nhập Google. Hãy kiểm tra Google Provider trên Supabase.")
            login_url = auth_response.headers.get("Location")
            if not login_url:
                raise RuntimeError("Supabase không trả về trang đăng nhập Google.")

            result = {"code": None, "error": None}
            ready = threading.Event()
            service = self

            class CallbackHandler(BaseHTTPRequestHandler):
                def do_GET(self):
                    query = parse_qs(urlparse(self.path).query)
                    result["code"] = query.get("code", [None])[0]
                    result["error"] = query.get("error_description", query.get("error", [None]))[0]
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    if result["code"]:
                        self.wfile.write("<h2>Đăng nhập thành công</h2><p>Bạn có thể đóng cửa sổ này và quay lại Web Automator Studio.</p>".encode("utf-8"))
                    else:
                        self.wfile.write("<h2>Đăng nhập chưa thành công</h2><p>Bạn có thể đóng cửa sổ này và thử lại trong ứng dụng.</p>".encode("utf-8"))
                    ready.set()

                def log_message(self, *_):
                    return

            server = HTTPServer(("127.0.0.1", 43899), CallbackHandler)
            threading.Thread(target=server.handle_request, daemon=True).start()
            webbrowser.open(login_url)

            if not ready.wait(timeout=180):
                server.server_close()
                raise TimeoutError("Đã hết thời gian chờ đăng nhập Google. Hãy thử lại.")
            server.server_close()
            if result["error"]:
                raise RuntimeError(f"Google từ chối đăng nhập: {result['error']}")
            if not result["code"]:
                raise RuntimeError("Không nhận được mã đăng nhập từ Google.")

            token_response = requests.post(
                f"{SUPABASE_URL}/auth/v1/token?grant_type=pkce",
                headers={"apikey": SUPABASE_PUBLISHABLE_KEY, "Content-Type": "application/json"},
                json={"auth_code": result["code"], "code_verifier": verifier},
                timeout=15,
            )
            if not token_response.ok:
                raise RuntimeError("Không thể hoàn tất đăng nhập Google. Hãy kiểm tra Redirect URL trên Supabase.")
            session = token_response.json()
            session["saved_at"] = int(time.time())
            with service._lock:
                service._session = session
                service._save_session(session)
        except OSError as error:
            with self._lock:
                self._login_error = "Cổng đăng nhập đang bận. Hãy đóng app rồi mở lại và thử lại."
        except Exception as error:
            with self._lock:
                self._login_error = str(error)
        finally:
            with self._lock:
                self._login_in_progress = False

    def logout(self):
        with self._lock:
            self._session = None
            self._login_error = None
            try:
                os.remove(self.session_path)
            except FileNotFoundError:
                pass

    def list_scripts(self):
        response = requests.get(
            f"{SUPABASE_URL}/rest/v1/scripts",
            headers=self._headers(),
            params={"select": "name", "order": "updated_at.desc"},
            timeout=15,
        )
        self._raise_for_storage_error(response)
        return [item["name"] for item in response.json()]

    def get_script(self, name):
        response = requests.get(
            f"{SUPABASE_URL}/rest/v1/scripts",
            headers=self._headers(),
            params={"select": "payload", "name": f"eq.{name}", "limit": 1},
            timeout=15,
        )
        self._raise_for_storage_error(response)
        rows = response.json()
        return rows[0]["payload"] if rows else None

    def save_script(self, name, payload):
        response = requests.post(
            f"{SUPABASE_URL}/rest/v1/scripts?on_conflict=user_id,name",
            headers={**self._headers(), "Prefer": "resolution=merge-duplicates,return=minimal"},
            json={"name": name, "payload": payload},
            timeout=15,
        )
        self._raise_for_storage_error(response)

    def delete_script(self, name):
        response = requests.delete(
            f"{SUPABASE_URL}/rest/v1/scripts",
            headers=self._headers(),
            params={"name": f"eq.{name}"},
            timeout=15,
        )
        self._raise_for_storage_error(response)

    @staticmethod
    def _raise_for_storage_error(response):
        if response.ok:
            return
        if response.status_code in (401, 403):
            raise PermissionError("Phiên đăng nhập đã hết hạn. Hãy đăng xuất rồi đăng nhập lại.")
        if response.status_code == 404:
            raise RuntimeError("Chưa tạo bảng dữ liệu. Hãy chạy file supabase_schema.sql trong SQL Editor của Supabase.")
        raise RuntimeError("Không thể đồng bộ dữ liệu với Supabase. Hãy kiểm tra kết nối hoặc cấu hình database.")
