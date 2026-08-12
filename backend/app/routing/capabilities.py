"""从请求内容解析所需能力集合，并估算 prompt token 数。"""

from typing import Any, Iterable


def _content_to_text(content: Any) -> tuple[str, bool]:
    """返回 (文本, 是否含图像)。支持 string 与 OpenAI 多模态 content 列表。"""
    if isinstance(content, str):
        return content, False
    if isinstance(content, list):
        texts = []
        has_image = False
        for part in content:
            if isinstance(part, dict):
                t = part.get("text")
                if t:
                    texts.append(t)
                if part.get("type") == "image_url" or "image" in part:
                    has_image = True
        return "\n".join(texts), has_image
    return str(content), False


_CODE_MARKERS = [
    "def ", "function ", "import ", "class ", "```", "代码", "编程",
    "算法", "sql", "select ", "select\n",
]
_VISION_HINTS = ["图", "image", "画", "描述这张", "识别", "ocr", "截图"]


def detect_capabilities(messages: Iterable[dict]) -> set[str]:
    caps: set[str] = {"chat"}
    blob = ""
    has_image = False
    for m in messages:
        if not isinstance(m, dict):
            continue
        text, img = _content_to_text(m.get("content"))
        blob += text + "\n"
        if img:
            has_image = True

    low = blob.lower()
    if has_image or any(h in blob for h in _VISION_HINTS):
        caps.add("vision")
    if any(mk in blob for mk in _CODE_MARKERS):
        caps.add("code")
    if len(blob) > 4000:
        caps.add("long_context")
    if "tool" in low or "function_call" in low or "调用" in blob or "工具" in blob:
        caps.add("function_calling")
    return caps


def estimate_prompt_tokens(messages: Iterable[dict]) -> int:
    """粗略估算 prompt token：英文≈4 字符/token，中文≈1.5 字符/token。"""
    chars = 0
    for m in messages:
        if not isinstance(m, dict):
            continue
        text, _ = _content_to_text(m.get("content"))
        chars += len(text)
    # 中文占比高时更接近 1.5 字符/token，这里取平均 3 字符/token
    return max(1, int(chars / 3))
