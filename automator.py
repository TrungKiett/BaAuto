from playwright.sync_api import sync_playwright
import re
import time

class WebAutomator:
    def __init__(self, headless=False, slow_mo=50, browser_type="chromium"):
        self.headless = headless
        self.slow_mo = slow_mo
        self.browser_type_name = browser_type
        
        # Sẽ được khởi tạo khi gọi start()
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    def start(self):
        """Khởi động trình duyệt"""
        self.playwright = sync_playwright().start()
        
        # Chọn loại trình duyệt dựa trên cấu hình
        if self.browser_type_name == "firefox":
            browser_type = self.playwright.firefox
        elif self.browser_type_name == "webkit":
            browser_type = self.playwright.webkit
        else:
            browser_type = self.playwright.chromium

        self.browser = browser_type.launch(
            headless=self.headless,
            slow_mo=self.slow_mo
        )
        self.context = self.browser.new_context()
        self.page = self.context.new_page()
        print(f"[{self.browser_type_name}] Browser started. Headless: {self.headless}")

    def stop(self):
        """Đóng trình duyệt và dọn dẹp tài nguyên"""
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()
        print("Browser closed.")

    def navigate(self, url):
        """Điều hướng tới một URL"""
        print(f"Navigating to {url}...")
        self.page.goto(url)
        self.page.wait_for_load_state("networkidle")

    def click_element(self, selector):
        """Click vào một phần tử trên trang"""
        print(f"Clicking element: {selector}")
        self.page.click(selector)

    def fill_input(self, selector, text):
        """Điền text vào một ô input"""
        print(f"Filling input: {selector} with '{text}'")
        self.page.fill(selector, text)
        
    def fill_with_retry(self, selector, text, error_selector, append_char, submit_selector=None, max_retries=5):
        """Điền text có kiểm tra lỗi trùng lặp"""
        current_text = text
        for i in range(max_retries):
            print(f"Attempt {i+1}: Filling {selector} with '{current_text}'")
            self.page.fill(selector, current_text)
            
            # Nếu cần bấm nút xác nhận để kiểm tra lỗi
            if submit_selector:
                self.page.click(submit_selector)
            
            # Chờ một lát để web xử lý và hiện lỗi (nếu có)
            time.sleep(1.5)
            
            try:
                # Kiểm tra xem selector lỗi có hiển thị trên màn hình không
                error_locator = self.page.locator(error_selector)
                if error_locator.is_visible():
                    print(f"Error detected at {error_selector}. Appending '{append_char}'.")
                    current_text += append_char
                    continue
            except Exception as e:
                pass # Bỏ qua nếu có lỗi tìm element
                
            # Nếu không thấy lỗi hiển thị, có nghĩa là đã thành công
            print("No error detected. Proceeding.")
            break
        
        return current_text

    def get_text(self, selector):
        """Lấy text của một phần tử"""
        return self.page.locator(selector).text_content()

    @staticmethod
    def _normalise_occurrence(occurrence, label):
        """Chuyển số thứ tự người dùng nhập thành index 1-based hợp lệ."""
        if occurrence is None or str(occurrence).strip() == "":
            return 1

        try:
            index = int(str(occurrence).strip())
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Số thứ tự {label} phải là số nguyên bắt đầu từ 1.") from exc

        if index < 1:
            raise ValueError(f"Số thứ tự {label} phải lớn hơn hoặc bằng 1.")
        return index

    def _locator_at_occurrence(
        self, selector, occurrence, label, match_text=None, exact_text=False
    ):
        """Lấy phần tử thứ N của selector; có thể lọc theo nội dung hiển thị."""
        index = self._normalise_occurrence(occurrence, label)
        locator = self.page.locator(selector)
        selector_description = f"'{selector}'"
        if match_text is not None and str(match_text).strip():
            match_text = str(match_text).strip()
            text_matcher = (
                re.compile(rf"^\s*{re.escape(match_text)}\s*$")
                if exact_text else match_text
            )
            locator = locator.filter(has_text=text_matcher)
            selector_description += f" có nội dung '{match_text}'"

        # Chờ phần tử đầu tiên xuất hiện để các trang tải động vẫn hoạt động.
        locator.first.wait_for(state="attached")
        count = locator.count()
        if index > count:
            raise ValueError(
                f"Selector {label} {selector_description} chỉ tìm thấy {count} phần tử, "
                f"không có phần tử thứ {index}."
            )

        return locator.nth(index - 1), index, count

    def drag_and_drop(
        self,
        source_selector,
        target_selector,
        source_index=1,
        target_index=1,
        source_text=None,
        target_text=None,
    ):
        """Kéo thả theo nội dung hiển thị hoặc số thứ tự khi các selector bị trùng."""
        source, source_index, source_count = self._locator_at_occurrence(
            source_selector, source_index, "nguồn", source_text, exact_text=True
        )
        target, target_index, target_count = self._locator_at_occurrence(
            target_selector, target_index, "đích", target_text
        )

        print(
            f"Dragging source #{source_index}/{source_count} ({source_selector}) "
            f"to target #{target_index}/{target_count} ({target_selector})"
        )
        source.drag_to(target)
        return {
            "source_index": source_index,
            "source_count": source_count,
            "target_index": target_index,
            "target_count": target_count,
        }

    def _wait_for_newest_element(self, selector, previous_count, timeout_seconds=10):
        """Chờ phần tử mới xuất hiện sau thao tác kéo thả rồi trả về phần tử mới nhất."""
        deadline = time.monotonic() + timeout_seconds
        locator = self.page.locator(selector)
        while time.monotonic() < deadline:
            count = locator.count()
            if count > previous_count:
                return locator.nth(count - 1), count
            time.sleep(0.1)

        raise TimeoutError(
            f"Không thấy ô nhập mới với selector '{selector}' sau {timeout_seconds} giây. "
            "Hãy dùng selector chỉ áp dụng cho ô tên field trong vùng thiết kế."
        )

    def create_field(
        self,
        source_selector,
        source_text,
        target_selector,
        field_input_selector,
        field_name,
        save_selector,
    ):
        """Kéo một field theo tên, điền tên vào ô mới tạo và lưu trong một bước."""
        initial_input_count = self.page.locator(field_input_selector).count()
        drag_result = self.drag_and_drop(
            source_selector,
            target_selector,
            source_text=source_text,
        )
        new_input, total_inputs = self._wait_for_newest_element(
            field_input_selector, initial_input_count
        )
        new_input.fill(field_name)
        self.click_element(save_selector)
        return {
            **drag_result,
            "field_name": field_name,
            "total_inputs": total_inputs,
        }

    def wait(self, seconds):
        """Dừng một khoảng thời gian (tính bằng giây)"""
        time.sleep(seconds)
