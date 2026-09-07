# 🤖 BaAuto – Web Automator Studio

Công cụ tự động hóa trình duyệt web tích hợp **AI Agent thông minh** (Vision + DOM + Ngôn ngữ tự nhiên).

## ✨ Tính năng

- 🖥️ **Ứng dụng desktop riêng** — Chạy trong cửa sổ Windows, không mở tab trình duyệt
- 🎯 **Kịch bản thủ công** — Tạo và chạy automation scripts bằng UI trực quan
- 🤖 **AI Agent tự chủ** — Mô tả mục tiêu bằng tiếng Việt, AI tự tìm cách thực hiện
- 📸 **Vision + DOM** — AI quan sát trang qua screenshot + nội dung DOM
- 🔄 **Auto-Update** — Tự động thông báo và cài bản mới từ GitHub

## 🚀 Cài đặt (Developer)

```bash
# Clone repo
git clone https://github.com/TrungKiett/BaAuto.git
cd BaAuto

# Tạo virtual environment
python -m venv .venv
.venv\Scripts\activate

# Cài dependencies
pip install -r requirements.txt

# Cài Playwright browsers
playwright install chromium

# Chạy app
python app.py
```

Mở trình duyệt tại: http://127.0.0.1:5000

## 📦 Build Desktop App (.exe)

```bat
build.bat
```

File `.exe` sẽ được tạo tại `dist/WebAutomatorStudio.exe` và mở trong cửa sổ ứng dụng Windows riêng. Icon ứng dụng dùng file `assets/web_automator_studio.ico`.

## 🔄 Phát hành bản cập nhật

1. Tăng `VERSION` trong `version.py`
2. Chạy `build.bat`
3. Tạo GitHub Release với tag `v{VERSION}`
4. Upload `dist/WebAutomatorStudio.exe` vào Release
5. Người dùng sẽ tự động nhận thông báo cập nhật!

## 🤖 AI Providers hỗ trợ

| Provider | Model mặc định |
|----------|---------------|
| Google Gemini | `gemini-2.0-flash` |
| OpenAI | `gpt-4o` |
| Anthropic Claude | `claude-opus-4-5` |

## 📄 License

MIT
