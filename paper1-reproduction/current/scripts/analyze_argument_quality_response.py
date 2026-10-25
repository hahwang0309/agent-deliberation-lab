"""Compare archived quality ratings with actual discussion responses; no API calls."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/argument-quality-matplotlib")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.analysis.argument_quality_response import (
    align_ratings, response_contrasts, summarize_ratings, topic_bootstrap,
)


def read_outcomes(db, plan, model):
    topics = {t["key"]: t for t in plan["topics"]}
    connection = sqlite3.connect(f"file:{db.resolve()}?mode=ro", uri=True)
    rows = []
    for did, config, run_info in connection.execute(
        "select id, config, run_info from discussions where status='completed' "
        "and json_extract(config, '$.experiment.batch')=?", (plan["name"],)
    ):
        exp = json.loads(config)["experiment"]
        label = exp["label"].split("-")
        if len(label) != 3 or label[0] not in ("strong", "weak"):
            continue
        key = exp["topic_key"]
        topic = topics[key]
        target = next(iter(topic["seeds"]))
        actual_model = json.loads(run_info)[-1]["llm"]["participants"][target]["model"]
        if actual_model != model:
            raise ValueError(f"Rating and discussion model mismatch: {actual_model}")
        responses = list(connection.execute(
            "select phase, score, source from survey_responses "
            "where discussion_id=? and participant=? and item_id='stance'", (did, target)))
        values = {phase: score for phase, score, _ in responses}
        if len(responses) != 2 or set(values) != {"pre", "post"}:
            raise ValueError("Missing or duplicated pre/post outcome")
        if any(x is None or not 0 <= x <= 100 for x in values.values()):
            raise ValueError("Missing or out-of-range stance")
        if values["pre"] != topic["seeds"][target]["stance"]:
            raise ValueError("Initial stance does not match the plan")
        sign = -1 if key.endswith("-pro") else 1
        rows.append(dict(discussion_id=did, topic=key.rsplit("-", 1)[0], topic_key=key,
                         quality=label[0], support=label[1], engine=label[2],
                         replicate=exp["replicate"], pre=values["pre"], post=values["post"],
                         delta=sign * (values["post"] - values["pre"])))
    connection.close()
    outcomes = pd.DataFrame(rows)
    expected = len(topics) * 2 * 2 * 2 * plan["repetitions"]
    if len(outcomes) != expected:
        raise ValueError(f"Expected {expected} complete outcomes, found {len(outcomes)}")
    return outcomes


def fmt(x, digits=3):
    return f"{x['estimate']:+.{digits}f} [{x['ci'][0]:+.{digits}f}, {x['ci'][1]:+.{digits}f}]"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bootstrap", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20261019)
    args = parser.parse_args()
    paths = {"ratings": ROOT/"data/cases/argq_ratings_claude.csv",
             "plan": ROOT/"data/study1/plans/argq-claude.yaml",
             "original_plan": ROOT/"data/cases/argq.yaml",
             "db": ROOT/"data/study1/claude.db"}
    plan = yaml.safe_load(paths["plan"].read_text())
    original = yaml.safe_load(paths["original_plan"].read_text())
    ratings = align_ratings(pd.read_csv(paths["ratings"]), plan, original)
    models = ratings["model"].unique()
    if len(models) != 1:
        raise ValueError("Expected one rating model")
    outcomes = read_outcomes(paths["db"], plan, models[0])
    rs = summarize_ratings(ratings)
    response = response_contrasts(outcomes)
    wide = response.pivot(index=["topic", "topic_key"], columns="engine", values="response_gap")
    joined = rs.merge(wide.reset_index(), on=["topic", "topic_key"], validate="one_to_one")
    joined["stateful_minus_baseline"] = joined["stateful"] - joined["baseline"]
    cols = ["strong", "weak", "rating_gap", "baseline", "stateful", "stateful_minus_baseline"]
    estimates = topic_bootstrap(joined, cols, args.bootstrap, args.seed)
    summary = dict(status="Post-hoc exploratory analysis of archived pre-experiment ratings and completed trials",
                   model=str(models[0]), n_arguments=len(ratings), n_sets=len(joined),
                   n_topics=joined.topic.nunique(), n_trials=len(outcomes),
                   n_sets_strong_rated_higher=int(joined.rating_gap.gt(0).sum()),
                   bootstrap=args.bootstrap, seed=args.seed,
                   resampling_unit="16 topics, retaining both target sides and both engines together",
                   rating_scale="0-1; separate no-persona quality evaluation",
                   response_scale="0-100 points toward scripted opponents; full strong-minus-weak contrast",
                   identity_check="Exact current argument text equality across two plans; all 384 historic rows match ordered topic/quality/WA/token metadata; CSV itself has no original text/hash",
                   estimates=estimates)
    out = ROOT/"docs/research/argument-quality-response"
    for name in ["source-data", "figures", "tables"]:
        (out/name).mkdir(parents=True, exist_ok=True)
    ratings.to_csv(out/"source-data/aligned-ratings.csv", index=False)
    outcomes.to_csv(out/"source-data/discussion-outcomes.csv", index=False)
    joined.to_csv(out/"source-data/set-contrasts.csv", index=False)
    (out/"source-data/results.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2)+"\n")
    # Hash the selected read-only DB extract rather than scanning unrelated runs.
    manifest = [{"path": str(p.relative_to(ROOT)), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                for key, p in paths.items() if key != "db"]
    manifest.append({"path": str(paths["db"].relative_to(ROOT)), "mode": "read-only",
                     "selected_batch": plan["name"], "extracted_trials": len(outcomes),
                     "extract_sha256": hashlib.sha256((out/"source-data/discussion-outcomes.csv").read_bytes()).hexdigest()})
    (out/"source-data/input-manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
    table = "| 비교 | 척도 | 추정값 [95% 구간] |\n|---|---|---|\n"
    for label, scale, key in [("단독 평가: 강한 논거", "0–1", "strong"),
                              ("단독 평가: 약한 논거", "0–1", "weak"),
                              ("단독 평가: 강−약", "0–1", "rating_gap"),
                              ("토론 입장 이동: 강−약, 일반 토론", "0–100점", "baseline"),
                              ("토론 입장 이동: 강−약, 규칙 추가", "0–100점", "stateful"),
                              ("강−약 이동 효과의 규칙 추가−일반 차이", "0–100점", "stateful_minus_baseline")]:
        table += f"| {label} | {scale} | {fmt(estimates[key])} |\n"
    (out/"tables/core-comparison.md").write_text(table)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False, "pdf.fonttype": 42})
    fig, axes = plt.subplots(1, 2, figsize=(10.2, 4.8))
    for y, key, label in [(1, "strong", "Strong arguments"), (0, "weak", "Weak arguments")]:
        e = estimates[key]; x = e["estimate"]; lo, hi = e["ci"]
        axes[0].errorbar(x, y, xerr=[[x-lo], [hi-x]], fmt="o", color="#2776bd", capsize=4)
    axes[0].set(yticks=[0, 1], yticklabels=["Weak", "Strong"], ylim=(-.55, 1.55),
                xlabel="Standalone quality rating (0-1)", title="a  Quality evaluation")
    axes[0].set_xlim(0, .65)
    for y, key, color in [(1, "baseline", "#2776bd"), (0, "stateful", "#d85a24")]:
        e = estimates[key]; x = e["estimate"]; lo, hi = e["ci"]
        axes[1].errorbar(x, y, xerr=[[x-lo], [hi-x]], fmt="o", color=color, capsize=4)
    axes[1].axvline(0, ls="--", color="#666", lw=1)
    axes[1].set(yticks=[0, 1], yticklabels=["Rules added", "Baseline"], ylim=(-.55, 1.55),
                xlabel="Additional stance change: strong minus weak\n(0-100 scale points)",
                title="b  Response during discussion")
    fig.suptitle("Same model and argument sets: evaluation and response", fontsize=14)
    fig.text(.5, .025, "384 ratings; 32 sets / 16 topics; 768 trials. Lines: 95% topic-bootstrap intervals.", ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .08, 1, .92), w_pad=3)
    for ext in ["png", "pdf"]:
        fig.savefig(out/f"figures/evaluation-and-response.{ext}", dpi=220)
    plt.close(fig)
    report = f"""# 같은 모델의 논거 평가와 토론 중 반응

작성·계산: 2026-10-19. 기존 자료를 연결한 **사후 탐색 분석**이다. 새 API 호출이나 사람 검증은 수행하지 않았다.

## 핵심 결과

Claude는 별도 평가에서 강한 논거를 약한 논거보다 평균 {estimates['rating_gap']['estimate']:.3f}점 높게 평가했고, 32세트 중 {summary['n_sets_strong_rated_higher']}세트에서 강한 논거의 평균 평점이 더 높았다. 그러나 같은 논거를 사용하는 실제 집단 토론의 강−약 입장 이동 차이는 일반 토론 {fmt(estimates['baseline'])}점, 규칙 추가 토론 {fmt(estimates['stateful'])}점으로 뚜렷하지 않았다.

따라서 현재 자료는 ‘질의 차이가 평가에서는 드러나지만 그 차이에 따른 토론 중 입장 수정 효과는 뚜렷하지 않다’는 조합을 보여 준다. 두 척도를 직접 빼거나, 한쪽의 구간만 0을 제외한다는 이유로 두 효과 사이의 통계적 차이를 검정했다고 표현하지 않는다.

## 그래프와 표

![논거 평가와 실제 입장 수정 비교]({out}/figures/evaluation-and-response.png)

[벡터 PDF](figures/evaluation-and-response.pdf)

- **핵심 관찰:** 별도 평가에서는 강한 논거의 평점이 높지만, 토론에서는 강한 논거가 더 큰 입장 이동을 만드는 차이가 두 조건 모두 뚜렷하지 않다.
- **해석:** 같은 모델과 논거를 사용해도 질을 평가하는 응답과 토론에서 입장을 바꾸는 응답은 각각 확인해야 한다.
- **a 세로축:** 강한 논거 집합(Strong)과 약한 논거 집합(Weak)이다.
- **a 가로축:** 다른 에이전트와 토론하지 않고 논거 하나의 질을 평가한 0–1 점수다. Strong과 Weak는 사람의 ArgQ 품질 점수로 구성한 두 논거 집합이다.
- **b 가로축:** 같은 조건의 강한 논거 토론에서 약한 논거 토론의 입장 이동을 뺀 점수다. 오른쪽이면 강한 논거에서 상대 주장 방향으로 더 많이 이동했다는 뜻이다.
- **b 세로축:** 일반 토론과 숙의 규칙을 추가한 토론이다. 두 조건 모두 강−약 차이를 표시한다.
- **점과 선:** 점은 16주제에 같은 가중치를 준 평균, 선은 주제별 재표집의 95% 구간이다. 한 주제의 찬성·반대 초기 입장은 함께 재표집했다.

{table}
- **표 읽는 법:** 대괄호는 95% 구간이다. 앞의 세 행은 논거 평점, 뒤의 세 행은 상대 주장 방향으로의 입장 이동 차이다. 마지막 행은 규칙을 더했을 때 강−약 이동 차이가 얼마나 바뀌는지를 나타낸다.
- **핵심 관찰:** 평점 차이는 +0.126 [0.100, 0.156]이며, 강−약 이동 효과의 규칙 추가−일반 차이도 +0.859 [−1.339, 2.802]점으로 불확실하다.
- **해석:** 규칙을 더하면 논거 강약에 따른 이동 차이가 커진다는 근거도 이번 자료에서는 뚜렷하지 않다.

## 입력을 확인한 방법

- 보관된 평가 파일은 `data/cases/argq_ratings_claude.csv`이며, 모델 ID는 본 실험 참가자와 동일하다.
- 평가 당시 생성에 사용한 `data/cases/argq.yaml`과 본 실험 `argq-claude.yaml`의 32세트 논거 원문이 현재 파일 기준으로 모두 일치한다.
- 384행의 세트·강약·사람 평점(WA)·길이 정보가 평가 스크립트의 순서와 모두 맞는다. 과거 CSV에는 원문·해시가 없으므로 과거 요청 원문 자체의 암호학적 검증과는 구분한다.
- 실제 DB의 완료된 해당 배치만 읽어 표적의 사전·사후 응답과 모델 ID를 확인했고, 32세트×2강약×2지지×2엔진×3반복 = 768실행을 연결했다.
- 각 엔진·세트에서 지지자 수와 반복을 짝지어 강−약 차이를 계산한 뒤 평균했다. 입력 파일과 추출 자료의 해시는 [manifest](source-data/input-manifest.json)에 있다.

## 등록 결과와의 관계

이번 구간은 16주제를 단위로 새로 계산한 탐색 구간이며 기존 혼합모형·Holm 보정 등록 검정을 대체하지 않는다. 평가 차이는 단독 질 평가, 반응 차이는 토론에서의 입장 변화여서 과제와 프롬프트가 다르다. 단독 평가는 인간 응답자 역할이 부여된 토론 중 판단을 직접 관측한 결과가 아니다.

평가 파일은 본 실험 전 조작 점검 자료다. 설계 문서의 29/32 기록과 일치하지만, 사후 연결·재표집 분석은 지금 추가했으므로 탐색으로 보고한다. 기존 결과 문서의 ‘조작 점검 미실시’ 표기는 보관된 평가 자료와 맞지 않아 수정한다.

## 재현과 자료

- 실행: `.venv/bin/python scripts/analyze_argument_quality_response.py`
- [세트별 연결 자료](source-data/set-contrasts.csv), [평가 행](source-data/aligned-ratings.csv), [토론 응답](source-data/discussion-outcomes.csv), [결과 JSON](source-data/results.json).
- 새 분석은 완전한 강−약 평균 차이를 사용한다. 기존 주제별 보조 CSV의 `base_q`·`state_q`는 signed mean 방식이어서 균형 설계에서 이 차이의 절반이다. 해당 보조 열을 그대로 효과 크기로 가져오지 않았고 원래 등록 분석은 변경하지 않았다.
"""
    (out/"README.md").write_text(report)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
