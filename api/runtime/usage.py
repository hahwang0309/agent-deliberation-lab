"""
LLM 토큰 사용량·호출 횟수 집계 콜백
"""
from typing import Dict

from langchain_core.callbacks import UsageMetadataCallbackHandler


class UsageCounter(UsageMetadataCallbackHandler):
    """토큰 사용량 + LLM 호출 횟수 집계"""

    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    def on_llm_end(self, response, **kwargs) -> None:
        self.calls += 1
        super().on_llm_end(response, **kwargs)

    def totals(self) -> Dict[str, int]:
        prompt = sum(u.get("input_tokens", 0) for u in self.usage_metadata.values())
        completion = sum(u.get("output_tokens", 0) for u in self.usage_metadata.values())
        by_model = {model: {"input_tokens": u.get("input_tokens", 0), "output_tokens": u.get("output_tokens", 0)}
                    for model, u in self.usage_metadata.items()}
        return {"prompt_tokens": prompt, "completion_tokens": completion, "llm_calls": self.calls, "by_model": by_model}
