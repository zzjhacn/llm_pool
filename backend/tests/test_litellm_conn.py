"""独立 LiteLLM 连通性测试类。

用途：在不依赖本网关的情况下，单独验证某个 api_url / key / model / provider 是否可用，
排查「网关能跑、直连报 403/模型不存在」等provider 选错问题。

用法一（命令行，最常用）：
    python backend/tests/test_litellm_conn.py \
        --api-url https://dashscope.aliyuncs.com/compatible-mode/v1 \
        --key sk-xxxx \
        --model deepseek-v4-flash-0731 \
        --provider openai

用法二（pytest + 环境变量，未设置则自动跳过，不影响 CI）：
    LITELLM_TEST_API_URL=https://dashscope.aliyuncs.com/compatible-mode/v1 \
    LITELLM_TEST_KEY=sk-xxxx \
    LITELLM_TEST_MODEL=deepseek-v4-flash-0731 \
    LITELLM_TEST_PROVIDER=openai \
        pytest backend/tests/test_litellm_conn.py -s
"""

import argparse
import os

try:
    import litellm
except ImportError:
    litellm = None


class LiteLLMConnectionTest:
    """对一个端点做最小连通性验证：发一条消息，打印返回内容与 usage。"""

    def __init__(self, api_url: str, api_key: str, model: str, provider: str = ""):
        self.api_url = api_url
        self.api_key = api_key
        self.model = model
        self.provider = (provider or "").strip()

    def build_model_string(self) -> str:
        """与网关 executor 一致：provider 非空且模型名未带前缀时拼成 provider/model。"""
        if self.provider and "/" not in self.model:
            return f"{self.provider}/{self.model}"
        return self.model

    def run(self, prompt: str = "你好，请用一句话介绍你自己。") -> dict:
        if litellm is None:
            raise RuntimeError("未安装 litellm，请先 pip install litellm")
        full_model = self.build_model_string()
        print(f"[LiteLLMConnectionTest] model={full_model} api_base={self.api_url}")
        resp = litellm.completion(
            model=full_model,
            api_base=self.api_url,
            api_key=self.api_key,
            messages=[{"role": "user", "content": prompt}],
            stream=False,
        )
        content = resp.choices[0].message.content
        usage = resp.usage
        print(f"[LiteLLMConnectionTest] OK -> {content!r}")
        print(
            f"[LiteLLMConnectionTest] usage: prompt={usage.prompt_tokens} "
            f"completion={usage.completion_tokens} total={usage.total_tokens}"
        )
        return {"model": full_model, "content": content, "usage": usage.model_dump()}


def _env_config():
    return dict(
        api_url=os.environ["LITELLM_TEST_API_URL"],
        api_key=os.environ["LITELLM_TEST_KEY"],
        model=os.environ["LITELLM_TEST_MODEL"],
        provider=os.environ.get("LITELLM_TEST_PROVIDER", ""),
    )


def test_litellm_connection():
    needed = ["LITELLM_TEST_API_URL", "LITELLM_TEST_KEY", "LITELLM_TEST_MODEL"]
    if not all(os.environ.get(k) for k in needed):
        import pytest

        pytest.skip("未设置 LITELLM_TEST_API_URL / LITELLM_TEST_KEY / LITELLM_TEST_MODEL，跳过连通性测试")
    LiteLLMConnectionTest(**_env_config()).run()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="LiteLLM 连通性测试")
    p.add_argument("--api-url", required=True, help="厂商 API 地址，如 https://dashscope.aliyuncs.com/compatible-mode/v1")
    p.add_argument("--key", required=True, help="API Key")
    p.add_argument("--model", required=True, help="模型名，如 deepseek-v4-flash-0731")
    p.add_argument("--provider", default="", help="LiteLLM 厂商键，如 openai / dashscope；OpenAI 兼容端点填 openai")
    args = p.parse_args()
    LiteLLMConnectionTest(args.api_url, args.key, args.model, args.provider).run()
