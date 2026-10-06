"""
보고서 생성 테스트용 가짜 LLM (with_structured_output만 지원)
"""
import re


class _Structured:
    def __init__(self, llm, schema):
        self.llm, self.schema = llm, schema

    async def ainvoke(self, messages):
        self.llm.calls.append((self.schema.__name__, messages))
        queue = self.llm.responses.get(self.schema.__name__)
        item = queue.pop(0) if isinstance(queue, list) else queue
        data = item(messages) if callable(item) else item
        return self.schema.model_validate(data)


class StubLLM:
    model = "stub-model"

    def __init__(self, responses):
        self.responses = responses  # 스키마 이름 → 응답(dict) 목록 또는 messages를 받는 함수
        self.calls = []

    def with_structured_output(self, schema):
        return _Structured(self, schema)


def auto_issue_map(messages):
    """대화록에서 AI 발언자·seq를 읽어 첫 화자는 찬성, 나머지는 반대인 쟁점 1개를 만든다"""
    lines = re.findall(r"\[(\d+)\] (.+?) \(ai\)", messages[1].content)
    speakers = []
    for seq, name in lines:
        if name not in [s for s, _ in speakers]:
            speakers.append((name, int(seq)))
    positions = [{"participant": name, "stance": "agree" if i == 0 else "disagree",
                  "claim": f"{name} view", "evidence_seqs": [seq]} for i, (name, seq) in enumerate(speakers)]
    return {"issues": [{"title": "Proposition", "summary": "argued", "positions": positions}]}


NARRATIVE = {"executive_summary": "summary", "open_questions": ["q1"], "recommendations": ["r1"]}


def default_stub():
    return StubLLM({"IssueMap": auto_issue_map, "Narrative": NARRATIVE})
