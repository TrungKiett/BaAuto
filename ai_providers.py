"""
AI Providers Abstraction Layer
Hỗ trợ Gemini, OpenAI GPT-4o, và Anthropic Claude
với interface thống nhất cho Vision-based web automation.
"""

import base64
import json
import re
from abc import ABC, abstractmethod


def encode_image_to_base64(image_bytes: bytes) -> str:
    """Chuyển ảnh bytes sang base64 string."""
    return base64.b64encode(image_bytes).decode("utf-8")


def extract_json_from_text(text: str) -> dict:
    """
    Trích xuất JSON từ response text của LLM.
    LLM đôi khi bọc JSON trong markdown code block.
    """
    # Thử parse trực tiếp
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    # Tìm JSON trong ```json ... ``` block
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Tìm bất kỳ đối tượng JSON nào trong text
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Không thể trích xuất JSON từ response:\n{text[:500]}")


SYSTEM_PROMPT = """Bạn là một AI Agent tự động hóa trình duyệt web thông minh.

Nhiệm vụ: Phân tích trạng thái hiện tại của trang web (qua ảnh chụp màn hình và nội dung DOM),
rồi quyết định CHÍNH XÁC một hành động tiếp theo để tiến gần đến mục tiêu người dùng đề ra.

QUAN TRỌNG: Bạn PHẢI trả về ĐÚNG một đối tượng JSON theo schema sau, KHÔNG có text giải thích thêm:

{
  "reasoning": "Giải thích ngắn gọn lý do chọn hành động này (tiếng Việt)",
  "action": "<tên action>",
  "params": { <tham số của action> },
  "confidence": 0.95,
  "done": false
}

Danh sách actions hợp lệ:
- navigate: { "url": "https://..." }
- click: { "selector": "css_selector" } hoặc { "description": "mô tả phần tử để AI tìm" }  
- type: { "selector": "css_selector", "text": "nội dung" }
- clear_and_type: { "selector": "css_selector", "text": "nội dung" }
- scroll: { "direction": "down|up|left|right", "amount": 300 }
- press_key: { "key": "Enter|Tab|Escape|..." }
- wait: { "seconds": 1.5 }
- get_text: { "selector": "css_selector" }
- screenshot: {} (chụp ảnh để quan sát thêm)
- done: { "summary": "Mô tả tóm tắt kết quả đạt được" }
- fail: { "reason": "Lý do thất bại" }

Nguyên tắc:
1. Ưu tiên dùng CSS selector rõ ràng (id, class cụ thể) thay vì mô tả chung chung
2. Nếu không tìm thấy selector, hãy dùng "description" để mô tả phần tử
3. Chỉ trả về "done" khi đã HOÀN TOÀN đạt được mục tiêu
4. Chỉ trả về "fail" khi không thể tiếp tục (trang bị chặn, lỗi không khắc phục được)
5. Luôn kiểm tra DOM text để xác định trạng thái trang trước khi hành động
"""


def build_agent_message(goal: str, dom_text: str, history: list, image_bytes: bytes) -> list:
    """
    Xây dựng danh sách message gửi cho LLM.
    
    Args:
        goal: Mục tiêu người dùng (tiếng Việt hoặc tiếng Anh)
        dom_text: Nội dung text của DOM (rút gọn)
        history: Danh sách các bước đã thực hiện
        image_bytes: Screenshot hiện tại dưới dạng bytes
    
    Returns:
        List of message dicts (format tuỳ provider)
    """
    history_text = ""
    if history:
        history_lines = []
        for i, h in enumerate(history[-10:], 1):  # Chỉ giữ 10 bước gần nhất
            history_lines.append(
                f"Bước {i}: action={h['action']}, params={json.dumps(h.get('params', {}), ensure_ascii=False)}, "
                f"result={h.get('result', 'ok')}, reasoning={h.get('reasoning', '')}"
            )
        history_text = "\n".join(history_lines)

    user_content = f"""MỤC TIÊU: {goal}

LỊCH SỬ CÁC BƯỚC ĐÃ THỰC HIỆN:
{history_text if history_text else 'Chưa có bước nào (đây là bước đầu tiên)'}

NỘI DUNG DOM HIỆN TẠI (rút gọn):
{dom_text[:3000]}

Hãy quan sát ảnh chụp màn hình và DOM, rồi quyết định bước tiếp theo.
Trả về JSON action duy nhất."""

    return user_content, image_bytes


class BaseAIProvider(ABC):
    """Interface chuẩn cho tất cả AI providers."""

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    @abstractmethod
    def decide_action(self, goal: str, dom_text: str, history: list, image_bytes: bytes) -> dict:
        """
        Phân tích trạng thái trang và quyết định action tiếp theo.
        
        Returns:
            dict với schema: { reasoning, action, params, confidence, done }
        """
        pass

    def get_name(self) -> str:
        return self.__class__.__name__


class GeminiProvider(BaseAIProvider):
    """Google Gemini Vision provider (dùng google-genai SDK mới nhất)."""

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash"):
        super().__init__(api_key, model)
        self._client = None

    def _get_client(self):
        if self._client is None:
            from google import genai
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def decide_action(self, goal: str, dom_text: str, history: list, image_bytes: bytes) -> dict:
        from google import genai
        from google.genai import types

        client = self._get_client()
        user_text, img_bytes = build_agent_message(goal, dom_text, history, image_bytes)

        response = client.models.generate_content(
            model=self.model,
            contents=[
                types.Part.from_bytes(data=img_bytes, mime_type="image/png"),
                user_text,
            ],
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.2,
                max_output_tokens=1024,
            )
        )
        return extract_json_from_text(response.text)


class OpenAIProvider(BaseAIProvider):
    """OpenAI GPT-4o Vision provider."""

    def __init__(self, api_key: str, model: str = "gpt-4o"):
        super().__init__(api_key, model)
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=self.api_key)
        return self._client

    def decide_action(self, goal: str, dom_text: str, history: list, image_bytes: bytes) -> dict:
        client = self._get_client()
        user_text, img_bytes = build_agent_message(goal, dom_text, history, image_bytes)

        img_b64 = encode_image_to_base64(img_bytes)

        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{img_b64}",
                                "detail": "high"
                            }
                        },
                        {"type": "text", "text": user_text}
                    ]
                }
            ],
            max_tokens=1024,
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)


class ClaudeProvider(BaseAIProvider):
    """Anthropic Claude Vision provider."""

    def __init__(self, api_key: str, model: str = "claude-opus-4-5"):
        super().__init__(api_key, model)
        self._client = None

    def _get_client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client

    def decide_action(self, goal: str, dom_text: str, history: list, image_bytes: bytes) -> dict:
        client = self._get_client()
        user_text, img_bytes = build_agent_message(goal, dom_text, history, image_bytes)

        img_b64 = encode_image_to_base64(img_bytes)

        response = client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": img_b64
                            }
                        },
                        {"type": "text", "text": user_text}
                    ]
                }
            ]
        )
        return extract_json_from_text(response.content[0].text)


def create_provider(provider_name: str, api_key: str, model: str = None) -> BaseAIProvider:
    """
    Factory function để tạo provider theo tên.
    
    Args:
        provider_name: 'gemini', 'openai', hoặc 'claude'
        api_key: API key của provider
        model: Model name (nếu None, dùng default)
    
    Returns:
        Instance của BaseAIProvider tương ứng
    """
    defaults = {
        "gemini": ("gemini-2.0-flash", GeminiProvider),
        "openai": ("gpt-4o", OpenAIProvider),
        "claude": ("claude-opus-4-5", ClaudeProvider),
    }

    if provider_name not in defaults:
        raise ValueError(f"Provider không hợp lệ: '{provider_name}'. Chọn: {list(defaults.keys())}")

    default_model, ProviderClass = defaults[provider_name]
    return ProviderClass(api_key=api_key, model=model or default_model)
