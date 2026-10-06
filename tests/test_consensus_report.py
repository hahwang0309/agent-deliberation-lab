"""
종합보고서 엔진 테스트 (점수 계산·검증 재시도·마크다운)
"""
import pytest

from src.services.consensus_report import (
    ConsensusReportGenerator, ReportGenerationError, TranscriptMessage,
    agreement, direction, label_for, score_issues, to_markdown,
)
from tests.report_stubs import NARRATIVE, StubLLM


def pos(name, stance, kind="ai"):
    return {"participant": name, "stance": stance, "participant_type": kind, "claim": "c", "evidence_seqs": []}


def test_agreement_measures_convergence_on_either_side():
    assert agreement([pos("a", "agree"), pos("b", "agree")]) == 1.0
    assert agreement([pos("a", "disagree"), pos("b", "disagree")]) == 1.0       # 반대로 합의
    assert agreement([pos("a", "agree"), pos("b", "disagree")]) == 0.5
    assert agreement([pos("a", "agree"), pos("b", "agree"), pos("c", "disagree")]) == pytest.approx(0.6667)
    assert agreement([pos("a", "agree"), pos("b", "partially_agree")]) == 0.85
    assert agreement([pos("a", "partially_agree"), pos("b", "partially_agree")]) == 0.7
    assert agreement([pos("a", "agree"), pos("b", "no_position")]) is None      # 입장 2개 미만
    assert agreement([]) is None


def test_partial_agreement_does_not_count_toward_opposition():
    # 실제 Claude 실행에서 [반대, 부분찬성]이 0.75(부분 합의)로 나오던 회귀 방지
    opposed = [pos("a", "disagree"), pos("b", "partially_agree")]
    assert agreement(opposed) == 0.5
    assert label_for(agreement(opposed), 0.8, 0.6) == "disagreed"
    assert direction(opposed) == "oppose"


def test_single_stance_issue_is_insufficient_and_excluded_from_score():
    issues = [{"title": "lonely", "positions": [pos("A", "agree")]},
              {"title": "real", "positions": [pos("A", "agree"), pos("B", "agree")]}]
    summary = score_issues(issues, 0.8, 0.6)
    assert issues[0]["label"] == "insufficient" and issues[0]["scores"]["overall"] is None
    assert summary["scores"]["overall"] == 1.0


def test_score_issues_splits_ai_and_human_and_labels():
    issues = [
        {"title": "i1", "positions": [pos("A", "agree"), pos("B", "agree"), pos("H", "disagree", "human"),
                                      pos("H2", "disagree", "human")]},
        {"title": "i2", "positions": [pos("A", "agree"), pos("B", "disagree")]},
    ]
    summary = score_issues(issues, agreed_threshold=0.8, partial_threshold=0.6)
    assert issues[0]["scores"] == {"overall": 0.5, "ai": 1.0, "human": 1.0}
    assert issues[0]["label"] == "disagreed" and issues[0]["direction"] == "split"
    assert issues[1]["scores"] == {"overall": 0.5, "ai": 0.5, "human": None}
    # 종합: (0.5*4 + 0.5*2)/6, AI: (1.0*2 + 0.5*2)/4, 사람: 1.0 (i1만)
    assert summary["scores"] == {"overall": 0.5, "ai": 0.75, "human": 1.0}
    assert summary["label"] == "disagreed"


TRANSCRIPT = [TranscriptMessage(1, "Alice", "ai", "x"), TranscriptMessage(2, "Moderator", "moderator", "q"),
              TranscriptMessage(3, "Bob", "ai", "y")]
PARTICIPANTS = {"Alice": "ai", "Bob": "ai"}
GOOD = {"issues": [{"title": "T", "summary": "s", "positions": [
    {"participant": "Alice", "stance": "agree", "claim": "a", "evidence_seqs": [1]},
    {"participant": "Bob", "stance": "agree", "claim": "b", "evidence_seqs": [3]}]}]}
BAD = {"issues": [{"title": "T", "summary": "s", "positions": [
    {"participant": "Carol", "stance": "agree", "claim": "a", "evidence_seqs": [1]},
    {"participant": "Bob", "stance": "agree", "claim": "b", "evidence_seqs": [99]}]}]}


@pytest.mark.asyncio
async def test_invalid_participants_and_seqs_are_rejected_then_retried():
    llm = StubLLM({"IssueMap": [BAD, GOOD], "Narrative": NARRATIVE})
    report = await ConsensusReportGenerator(llm).generate("topic", TRANSCRIPT, PARTICIPANTS, language="en")

    issue_calls = [m for name, m in llm.calls if name == "IssueMap"]
    assert len(issue_calls) == 2
    feedback = issue_calls[1][-1].content
    assert "'Carol' is not a listed participant" in feedback and "[99] not in transcript" in feedback
    assert report["scores"]["overall"] == 1.0 and report["label"] == "agreed"
    assert report["agreed"] == ["T"] and report["disagreed"] == []
    assert report["narrative"]["executive_summary"] == "summary"


@pytest.mark.asyncio
async def test_schema_violation_retries_and_gives_up_after_max_attempts():
    llm = StubLLM({"IssueMap": [{"issues": [{"title": "T"}]}] * 3, "Narrative": NARRATIVE})
    with pytest.raises(ReportGenerationError):
        await ConsensusReportGenerator(llm, max_attempts=3).generate("t", TRANSCRIPT, PARTICIPANTS, "en")
    assert len(llm.calls) == 3


@pytest.mark.asyncio
async def test_markdown_contains_sections_and_scores():
    llm = StubLLM({"IssueMap": [GOOD], "Narrative": NARRATIVE})
    report = await ConsensusReportGenerator(llm).generate("topic", TRANSCRIPT, PARTICIPANTS, "en")
    md = to_markdown(report)
    for heading in ("# 종합보고서: topic", "## 합의된 내용", "## 합의되지 않은 내용", "## 열린 질문", "## 제언"):
        assert heading in md
    assert "종합 100% (합의)" in md and "**Alice** (찬성)" in md
