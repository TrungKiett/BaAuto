import json
import os
from automator import WebAutomator

def load_config(config_path="config.json"):
    """Đọc file cấu hình JSON"""
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)

def main():
    # 1. Tải cấu hình
    try:
        config = load_config("config.json")
    except Exception as e:
        print(f"Error loading config: {e}")
        return

    # Lấy các tham số cấu hình
    target_url = config.get("target_url", "https://example.com")
    headless = config.get("headless", False)
    slow_mo = config.get("slow_mo", 50)
    browser_type = config.get("browser_type", "chrome")

    # 2. Khởi tạo Automator
    bot = WebAutomator(
        headless=headless, 
        slow_mo=slow_mo, 
        browser_type=browser_type
    )

    try:
        # Bắt đầu trình duyệt
        bot.start()
        
        # 3. Kịch bản chạy (có thể tùy biến ở đây)
        bot.navigate(target_url)
        
        # Lấy tiêu đề hoặc nội dung làm ví dụ
        print("Page title:", bot.page.title())
        
        # Nếu vào example.com, lấy thẻ h1
        if "example.com" in target_url:
            heading = bot.get_text("h1")
            print(f"Heading found: {heading}")
        
        # Dừng một lát để quan sát (nếu mở giao diện)
        if not headless:
            print("Waiting 3 seconds before closing so you can observe...")
            bot.wait(3)

    except Exception as e:
        print(f"An error occurred during automation: {e}")
    finally:
        # 4. Luôn đảm bảo trình duyệt được đóng đúng cách
        bot.stop()

if __name__ == "__main__":
    main()
