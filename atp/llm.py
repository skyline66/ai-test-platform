"""LLM 客户端：一个 OpenAI 兼容端点，可空。

设计原则：**没配 key 也必须能跑**。所以这里只暴露「可用/不可用」，
业务侧（起草、归因）自己带离线降级路径，绝不把平台卡死在 API 上。
"""
from __future__ import annotations

import json
from typing import Any

from atp.config import settings

SYSTEM_PROMPT = """你是一个测试开发助手，为一个 Playwright + pytest 项目写用例草稿。

硬约束（违反即视为无效输出）：
1. 定位只用 get_by_role / get_by_label / get_by_text / get_by_test_id，禁止 xpath、nth-child、#id。
2. 用例文件只写步骤与断言，禁止在用例里出现 locator()。
3. 页面对象（pages/）里禁止写断言或 expect()。
4. 不要修改 conftest.py，不要新增依赖。
5. 只输出 JSON，形如 {"files": {"tests/test_x.py": "<代码>"}, "notes": ["..."]}，不要输出解释文字。"""


class LLMUnavailable(RuntimeError):
    """没配 key、网络不通、返回不合法时统一抛这个。"""


class LLMClient:
    def __init__(
        self,
        base_url: str = "",
        api_key: str = "",
        model: str = "",
        timeout: int | None = None,
    ) -> None:
        self.base_url = (base_url or settings.llm_base_url).rstrip("/")
        self.api_key = api_key or settings.llm_api_key
        self.model = model or settings.llm_model
        self.timeout = timeout or settings.llm_timeout

    @property
    def available(self) -> bool:
        return bool(self.base_url and self.api_key)

    def describe(self) -> dict[str, Any]:
        return {
            "enabled": self.available,
            "model": self.model,
            "base_url": self.base_url,
        }

    # ---------- 基础调用 ----------
    def chat(self, user: str, *, system: str = SYSTEM_PROMPT, temperature: float = 0.2) -> str:
        if not self.available:
            raise LLMUnavailable("未配置 ATP_LLM_BASE_URL / ATP_LLM_API_KEY")

        import httpx

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
        }
        url = f"{self.base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}"}

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
        except Exception as exc:  # noqa: BLE001 - 统一转成「不可用」，由调用方降级
            raise LLMUnavailable(f"LLM 调用失败：{exc}") from exc

        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMUnavailable(f"LLM 返回结构异常：{exc}") from exc

    # ---------- 两个具体任务 ----------
    def draft_case(self, requirement: str, page_objects: str) -> dict[str, Any]:
        user = (
            f"需求：{requirement}\n\n"
            f"现有页面对象签名（照着用，别改）：\n{page_objects}\n\n"
            "请生成一条 pytest 用例草稿，加 @pytest.mark.draft 标记。"
        )
        raw = self.chat(user)
        return _loads_json(raw)

    def refine_triage(self, error_text: str, rule_class: str) -> dict[str, Any]:
        user = (
            "下面是一条 Playwright 用例的失败信息，规则引擎初步判定为 "
            f"{rule_class}。请给出更准确的中文原因与处置建议。\n"
            '只输出 JSON：{"reason": "...", "suggestion": "..."}\n\n'
            f"失败信息：\n{error_text[:4000]}"
        )
        raw = self.chat(user, temperature=0.1)
        return _loads_json(raw)


def _loads_json(raw: str) -> dict[str, Any]:
    """模型很爱包 ```json 围栏，宽容一点。"""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1] if text.count("```") >= 2 else text.strip("`")
        if text.lstrip().startswith("json"):
            text = text.lstrip()[4:]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMUnavailable(f"LLM 输出不是合法 JSON：{exc}") from exc
    if not isinstance(data, dict):
        raise LLMUnavailable("LLM 输出顶层必须是对象")
    return data


_client: LLMClient | None = None


def get_client() -> LLMClient:
    global _client
    if _client is None:
        _client = LLMClient()
    return _client