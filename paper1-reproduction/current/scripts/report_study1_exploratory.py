"""
탐색 분석 결과를 논문용 그림과 마크다운 표로 만든다.

  python scripts/report_study1_exploratory.py --res data/study1/results/exploratory --figs docs/research/figures \
      --tables data/study1/results/exploratory/tables.md
"""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.analysis import figures  # noqa: E402

MODELS = ["claude", "gemini", "mistral"]


def f(x, d=3):
    return "—" if x is None or (isinstance(x, float) and x != x) else f"{x:.{d}f}"


def cell(s, d=3):
    return f"{f(s['estimate'], d)} [{f(s['ci'][0], d)}, {f(s['ci'][1], d)}]"


def load(res: Path, model: str, name: str) -> dict:
    return json.loads((res / model / f"{name}.json").read_text())


def tables(res: Path) -> str:
    L = []
    # N0
    L.append("## N0. 초기 정답자 수 k별 개인 정답률 (1-A 원 과제, [탐색], 집단 재표집 2,000회)\n")
    L.append("| 팔 | 모델 | 전체 | k=0 | k=1 | k=2+ | k1−k0 |\n|---|---|---|---|---|---|---|")
    n0 = {m: load(res, m, "n0") for m in MODELS}
    h = n0["claude"]["rates"]["human"]
    L.append(f"| 인간 | — | {cell(h['all'])} | {cell(h['0'])} | {cell(h['1'])} | {cell(h['2+'])} | {cell(n0['claude']['contrasts']['human: k1 - k0'])} |")
    for m in MODELS:
        for arm, name in (("ai_baseline", "AI 기준선(3회)"), ("ai_stateful", "AI 상태 기반")):
            r = n0[m]["rates"][arm]
            L.append(f"| {name} | {m} | {cell(r['all'])} | {cell(r['0'])} | {cell(r['1'])} | {cell(r['2+'])} | {cell(n0[m]['contrasts'][f'{arm}: k1 - k0'])} |")
    L.append("\n(k1−k0)의 AI − 인간 차이:\n\n| 모델 | 기준선 | 상태 기반 |\n|---|---|---|")
    for m in MODELS:
        c = n0[m]["contrasts"]
        L.append(f"| {m} | {cell(c['(ai_baseline k1-k0) - (human k1-k0)'])} | {cell(c['(ai_stateful k1-k0) - (human k1-k0)'])} |")
    L.append(f"\n집단 수: {n0['claude']['n_blocks']}, k별 {n0['claude']['blocks_by_k']}\n")
    # N2a
    L.append("## N2a. 1-A 만장일치율 (집단 단위, 집단 재표집 2,000회)\n")
    L.append("| 팔 | 모델 | 만장일치 | 정답 만장일치 | 오답 만장일치 | 과반 정답 |\n|---|---|---|---|---|---|")
    n2 = {m: load(res, m, "n2a") for m in MODELS}
    hr = n2["claude"]["rates"]["human"]
    L.append(f"| 인간 | — | {cell(hr['unanimous']['all'])} | {cell(hr['unanimous_correct']['all'])} | {cell(hr['unanimous_wrong']['all'])} | {cell(hr['majority_correct']['all'])} |")
    for m in MODELS:
        for arm, name in (("base", "AI 기준선"), ("state", "AI 상태 기반")):
            r = n2[m]["rates"][arm]
            L.append(f"| {name} | {m} | {cell(r['unanimous']['all'])} | {cell(r['unanimous_correct']['all'])} | {cell(r['unanimous_wrong']['all'])} | {cell(r['majority_correct']['all'])} |")
    L.append("\nk별 만장일치율 (정답 / 오답):\n\n| 팔 | 모델 | k=0 | k=1 | k=2+ |\n|---|---|---|---|---|")
    L.append(f"| 인간 | — | " + " | ".join(f"{f(hr['unanimous_correct'][k]['estimate'])} / {f(hr['unanimous_wrong'][k]['estimate'])}" for k in ("0", "1", "2+")) + " |")
    for m in MODELS:
        for arm, name in (("base", "AI 기준선"), ("state", "AI 상태 기반")):
            r = n2[m]["rates"][arm]
            L.append(f"| {name} | {m} | " + " | ".join(f"{f(r['unanimous_correct'][k]['estimate'])} / {f(r['unanimous_wrong'][k]['estimate'])}" for k in ("0", "1", "2+")) + " |")
    L.append("\n차이 (전체):\n\n| 모델 | 지표 | 기준선 − 인간 | 상태 − 인간 | 상태 − 기준선 |\n|---|---|---|---|---|")
    for m in MODELS:
        d = n2[m]["differences"]
        for met in ("unanimous", "unanimous_correct", "unanimous_wrong"):
            L.append(f"| {m} | {met} | {cell(d[f'{met}: base - human'])} | {cell(d[f'{met}: state - human'])} | {cell(d[f'{met}: state - base'])} |")
    # N2b
    L.append("\n## N2b. 1-B 합의율·수렴 (블록 × 조건, AI: 문항→블록 재표집, 인간: 소집단 재표집, 2,000회)\n")
    b = {m: load(res, m, "n2b") for m in MODELS}
    for met, title in (("consensus_sd", "합의율: 사후 SD ≤ 1.0 (주)"), ("consensus_range", "합의율: 사후 범위 ≤ 2 (민감도)"),
                       ("sd_drop", "SD 감소량 (모집단 SD, E3 정의)"), ("mean_abs_move", "평균 |post − pre|"), ("movers", "이동자 비율 (|Δ| ≥ 2)"),
                       ("gap_change", "정당 격차 감소 (|D − R| pre − post)")):
        L.append(f"\n### {title}\n")
        L.append("| 모델 | A-기준선 | A-상태 | B | C | 상태 − 기준선 | A−B 조건 차이 | B−C 조건 차이 |\n|---|---|---|---|---|---|---|---|")
        for m in MODELS:
            a = b[m]["ai"][met]
            L.append(f"| {m} | {cell(a['A-baseline'])} | {cell(a['A-stateful'])} | {cell(a['B-materials'])} | {cell(a['C-reanswer'])} | "
                     f"{cell(a['A-stateful - A-baseline'])} | {cell(a['A-baseline - B-materials'])} | {cell(a['B-materials - C-reanswer'])} |")
        hm = b["claude"]["human"][met]
        L.append(f"| 인간 (5명 추출 / 소집단 전원) | {cell(hm['draw5'])} / {cell(hm['full_group'])} | | | | | | |")
    L.append(f"\n블록 {b['claude']['n_blocks']}(문항 {b['claude']['n_items']}), 인간 소집단×문항 {b['claude']['n_human_units']}(소집단 {b['claude']['human_groups']}). "
             "인간 5명 추출은 집단 크기 표준화(실제 5인 숙의 아님).\n")
    # N3 human
    L.append("## N3. A1R 숙의군 − 통제군 (문항 30개 평균, 숙의군 소집단·통제군 참가자 재표집 2,000회)\n")
    hn = json.loads((res / "human" / "n3_human.json").read_text())
    mo = hn["mean_over_items"]
    L.append(f"숙의군 {hn['n_delib_participants']}명(소집단 {hn['n_delib_groups']}), 통제군 {hn['n_control_participants']}명. 통제군은 소집단이 없다.\n")
    L.append("| 지표 | 숙의군 | 통제군 | 숙의군 − 통제군 |\n|---|---|---|---|")
    for ind, name in (("sd_drop", "SD 감소 (응답자 전체)"), ("gap_change", "정당 격차 감소"), ("movers", "이동자 비율"),
                      ("direction_agree", "이동자 방향 일치"), ("mean_shift", "평균 이동"), ("mean_abs_move", "평균 |이동|"),
                      ("sd_pre", "사전 SD"), ("gap_pre", "사전 정당 격차")):
        L.append(f"| {name} | {cell(mo[f'delib_{ind}'])} | {cell(mo[f'control_{ind}'])} | {cell(mo[f'did_{ind}'])} |")
    L.append(f"| 소집단 안 SD 감소 (숙의군만) | {cell(mo['delib_group_sd_drop'])} | — | — |")
    # N3 per item table (human + claude)
    hi = pd.read_csv(res / "human" / "n3_human_items.csv").set_index("item")
    L.append("\n### 문항별: 인간 (숙의군 − 통제군) 와 AI A−C 조건 차이 (Claude)\n")
    ai = pd.read_csv(res / "claude" / "n3_ai_items.csv").set_index("item")
    L.append("| 문항 | 사전 SD(인간) | 인간 SD감소 DiD | 인간 격차감소 DiD | 인간 이동자 DiD | Claude 기준선 SD감소 A−C | Claude 상태 SD감소 A−C | Claude 기준선 격차 A−C | Claude 상태 격차 A−C |\n|---|---|---|---|---|---|---|---|---|")
    for it in hi.sort_values("did_sd_drop").index:
        r, a = hi.loc[it], ai.loc[it]
        L.append(f"| {it} | {f(r['delib_sd_pre'],2)} | {f(r['did_sd_drop'],2)} [{f(r['did_sd_drop_lo'],2)}, {f(r['did_sd_drop_hi'],2)}] | "
                 f"{f(r['did_gap_change'],2)} [{f(r['did_gap_change_lo'],2)}, {f(r['did_gap_change_hi'],2)}] | {f(r['did_movers'],2)} | "
                 f"{f(a['sd_drop|A-baseline - C-reanswer'],2)} | {f(a['sd_drop|A-stateful - C-reanswer'],2)} | "
                 f"{f(a['gap_change|A-baseline - C-reanswer'],2)} | {f(a['gap_change|A-stateful - C-reanswer'],2)} |")
    # N5
    L.append("\n## N5. 1-A 집단별 대응 (기술 통계)\n")
    for m in MODELS:
        n5 = load(res, m, "n5")
        L.append(f"\n### {m}\n")
        L.append("| k | n | 인간 과반 정답 & AI기준선 3회 모두 과반 정답 | 인간 과반 오답 & AI기준선 3회 모두 | 인간 정답 & AI 일부 | 인간 오답 & AI 일부 | 인간 정답 & AI 0회 | 인간 오답 & AI 0회 |\n|---|---|---|---|---|---|---|---|")
        for k in ("all", "0", "1", "2+"):
            ct = n5["crosstab"][k]["baseline"]
            g = lambda c, r: ct.get(c, {}).get(r, 0)  # noqa: E731
            L.append(f"| {k} | {n5['crosstab'][k]['n']} | {g('ai_base_all_reps','human_maj_correct')} | {g('ai_base_all_reps','human_maj_wrong')} | "
                     f"{g('ai_base_some','human_maj_correct')} | {g('ai_base_some','human_maj_wrong')} | {g('ai_base_none','human_maj_correct')} | {g('ai_base_none','human_maj_wrong')} |")
        L.append("\n| k | 인간 정답 & AI상태 정답 | 인간 오답 & AI상태 정답 | 인간 정답 & AI상태 오답 | 인간 오답 & AI상태 오답 |\n|---|---|---|---|---|")
        for k in ("all", "0", "1", "2+"):
            ct = n5["crosstab"][k]["stateful"]
            g = lambda c, r: ct.get(c, {}).get(r, 0)  # noqa: E731
            L.append(f"| {k} | {g('ai_state_correct','human_maj_correct')} | {g('ai_state_correct','human_maj_wrong')} | {g('ai_state_wrong','human_maj_correct')} | {g('ai_state_wrong','human_maj_wrong')} |")
        sf = n5["stateful_only_failures"]
        L.append(f"\n상태 기반에서만 실패(기준선 3회 모두 과반 정답, 상태 기반 과반 오답): {sf['n']}집단, k별 {sf['by_k']}, 크기별 {sf['by_size']}, "
                 f"평균 k {f(sf['mean_k_raw'],2)} (그 외 {f(sf['mean_k_raw_others'],2)}), 해당 집단의 인간 정답률 {f(sf['human_acc_in_these'],3)} (그 외 {f(sf['human_acc_others'],3)}).")
        c = n5["correlations"]
        L.append(f"집단 수준 Spearman(인간 정답률 대 AI): 기준선 {f(c['group_level_spearman']['human_vs_base'])}, 상태 {f(c['group_level_spearman']['human_vs_state'])}; "
                 f"카드 세트 수준({c['card_set_level_spearman']['n_card_sets']}세트, 1집단뿐인 세트 {c['card_set_level_spearman']['card_sets_with_1_group']}): "
                 f"기준선 {f(c['card_set_level_spearman']['human_vs_base'])}, 상태 {f(c['card_set_level_spearman']['human_vs_state'])}.\n")
    # N12
    L.append("## N12. 심은 입장의 유지 (재표집 2,000회)\n")
    L.append("### 1-B: |post − pre| 와 모델 기본 입장(D) 쪽 회귀\n")
    L.append("| 모델 | 조건 | |Δ| ≥ 3 비율 | |Δ| ≥ 1 비율 | 평균 |Δ| | 평균 Δ | 기울기 Δ ~ (D − pre) | 상관 |\n|---|---|---|---|---|---|---|---|")
    for m in MODELS:
        n12 = load(res, m, "n12")
        for lab in ("C-reanswer", "B-materials", "A-baseline", "A-stateful"):
            s = n12[f"1-B {lab}"]
            L.append(f"| {m} | {lab} | {cell(s['gap3'])} | {cell(s['gap1'])} | {cell(s['mean_abs'],2)} | {cell(s['mean_shift'],2)} | {cell(s['slope_toward_D'],2)} | {cell(s['corr_toward_D'],2)} |")
    L.append("\n### 1-A B(토론 없이 다시 풀기): 심은 답 유지\n")
    L.append("| 모델 | 재풀이 답 = 심은 답 | 심은 오답자가 여전히 오답 | 심은 오답자가 같은 오답 유지 | n |\n|---|---|---|---|---|")
    for m in MODELS:
        s = load(res, m, "n12")["1-A B-resolve"]
        L.append(f"| {m} | {cell(s['same_as_seed'])} | {cell(s['seeded_wrong_stay_wrong'])} | {cell(s['seeded_wrong_same_answer'])} | {s['n_agents']} |")
    L.append("\n### 1-C C(재응답): 표적 Δ (반대편 방향 +, 0~100)\n")
    L.append("| 모델 | |Δ| ≥ 10 | |Δ| ≥ 30 | 평균 |Δ| | 평균 Δ | n |\n|---|---|---|---|---|---|")
    for m in MODELS:
        s = load(res, m, "n12")["1-C C-reanswer"]
        L.append(f"| {m} | {cell(s['abs_ge_10'])} | {cell(s['abs_ge_30'])} | {cell(s['mean_abs'],2)} | {cell(s['mean_delta_toward_opposite'],2)} | {s['n_targets']} |")
    return "\n".join(L) + "\n"


def tables_phase_a(res: Path) -> str:
    """A단계 표: N1, S1, S2, E4, E6, E7, E9, E10, E8, N4"""
    L = []
    have = lambda m, n: (res / m / f"{n}.json").exists()  # noqa: E731
    if all(have(m, "n1") for m in MODELS):
        L.append("## N1. 이동 방향 분해 (등록 H2c 모형을 조건별 적합, [탐색])\n")
        L.append("post − pre ~ β·(D − pre) + γ·(집단 사전 평균 − pre) + (1|block) + (1|item). 민감도 = `+ (1|persona)`. 구간은 Satterthwaite 95%.\n")
        L.append("| 모델 | 조건 | β (기본 입장) | γ (집단 평균) | β (페르소나 RE) | γ (페르소나 RE) | n |\n|---|---|---|---|---|---|---|")
        for m in MODELS:
            n1 = load(res, m, "n1")
            for lab in ("A-baseline", "A-stateful"):
                r = n1["models"][lab]
                L.append(f"| {m} | {lab} | {cell(r['beta'])} | {cell(r['gamma'])} | {cell(r['persona_sensitivity']['beta'])} | {cell(r['persona_sensitivity']['gamma'])} | {r['n']} |")
        L.append("\n엔진 상호작용 (eng = +0.5 상태, −0.5 기준선):\n\n| 모델 | β × 엔진 | γ × 엔진 |\n|---|---|---|")
        for m in MODELS:
            r = load(res, m, "n1")["models"]["engine_interaction"]
            L.append(f"| {m} | {cell(r['beta_x_engine'])} (p {f(r['beta_x_engine']['p'], 4)}) | {cell(r['gamma_x_engine'])} (p {f(r['gamma_x_engine']['p'], 4)}) |")
        L.append("\n### 합의점 위치: 블록 사후 평균이 가장 가까운 기준 (문항→블록 재표집)\n")
        L.append("| 모델 | 조건 | D에 최근접 | 사전 평균에 최근접 | 인간 사후 평균에 최근접 | 평균 거리 D / 사전 / 인간 | D 쪽으로 이동한 블록 | 인간 사후 쪽으로 이동 |\n|---|---|---|---|---|---|---|---|")
        for m in MODELS:
            for lab in ("C-reanswer", "B-materials", "A-baseline", "A-stateful"):
                c = load(res, m, "n1")["consensus_location"][lab]
                L.append(f"| {m} | {lab} | {cell(c['share_nearest_D'])} | {cell(c['share_nearest_pre_mean'])} | {cell(c['share_nearest_human_post'])} | "
                         f"{f(c['mean_dist_D']['estimate'],2)} / {f(c['mean_dist_pre_mean']['estimate'],2)} / {f(c['mean_dist_human_post']['estimate'],2)} | "
                         f"{cell(c['share_moved_toward_D'])} | {cell(c['share_moved_toward_human_post'])} |")
    if all(have(m, "s1") for m in MODELS):
        L.append("\n## S1. 모델 기본 입장 D(문항 평균) 대 인간 사전·사후 평균 (문항 30, 문항 재표집)\n")
        L.append("| 모델 | ρ(D, 인간 사후) | ρ(D, 인간 사전) | 평균 \\|D − 인간 사후\\| | 평균 \\|D − 인간 사전\\| | D가 사후에 더 가까운 문항 비율 | 인간 이동 방향 = D 방향 (\\|이동\\| ≥ 0.5, n) | ρ(D, AI 상태 사후) | ρ(D, AI 기준선 사후) |\n|---|---|---|---|---|---|---|---|---|")
        for m in MODELS:
            s = load(res, m, "s1")
            L.append(f"| {m} | {cell(s['spearman_D_human_post'],2)} | {cell(s['spearman_D_human_pre'],2)} | {cell(s['mean_abs_D_minus_human_post'],2)} | {cell(s['mean_abs_D_minus_human_pre'],2)} | "
                     f"{cell(s['share_D_closer_to_human_post_than_pre'],2)} | {cell(s['sign_agreement_human_shift_vs_D_direction'],2)} ({s['n_items_human_shift_ge_0.5']}) | "
                     f"{cell(s['spearman_D_vs_post_A_stateful'],2)} | {cell(s['spearman_D_vs_post_A_baseline'],2)} |")
    if (res / "s2_cross_model.json").exists():
        s2 = json.loads((res / "s2_cross_model.json").read_text())
        L.append("\n## S2. 모델 간 기본 입장·합의점 일치 (문항 30)\n")
        L.append("| 비교 | 지표 | Spearman | Pearson | 평균 \\|차\\| |\n|---|---|---|---|---|")
        for key in ("D", "post_A-stateful", "post_A-baseline"):
            for pair, v in s2[key].items():
                L.append(f"| {pair} | {key} | {f(v['spearman'],2)} | {f(v['pearson'],2)} | {f(v['mean_abs_diff'],2)} |")
        L.append("\n모델 안에서 D 대 상태 기반 사후 평균: " + "; ".join(f"{m} ρ {f(v['spearman'],2)}, 평균 |차| {f(v['mean_abs_diff'],2)}" for m, v in s2["within_model_D_vs_post_stateful"].items()) + "\n")
    if all(have(m, "e4") for m in MODELS):
        L.append("## E4. 문항별 기본 입장 끌림과 합의율 (Spearman, 문항 30)\n")
        L.append("| 모델 | 기울기(C) vs 합의율 기준선 | 기울기(C) vs 합의율 상태 | 기울기(C) vs SD감소 기준선 | 기울기(C) vs SD감소 상태 | 기울기 범위 C | 기울기 범위 상태 |\n|---|---|---|---|---|---|---|")
        for m in MODELS:
            e = load(res, m, "e4")
            sp, rg = e["spearman"], e["item_slope_range"]
            L.append(f"| {m} | {f(sp['slope_C vs consensus_sd A-baseline'],2)} | {f(sp['slope_C vs consensus_sd A-stateful'],2)} | {f(sp['slope_C vs sd_drop A-baseline'],2)} | {f(sp['slope_C vs sd_drop A-stateful'],2)} | "
                     f"{f(rg['C-reanswer'][0],2)}~{f(rg['C-reanswer'][1],2)} | {f(rg['A-stateful'][0],2)}~{f(rg['A-stateful'][1],2)} |")
    if all(have(m, "e6") for m in MODELS):
        L.append("\n## E6. 정당 격차 감소의 분해: 민주(D)·공화(R) 각각의 이동과 상대 정당 쪽 이동 (양수 = 상대 쪽)\n")
        L.append("| 집단 | 조건 | 민주 평균 이동 | 공화 평균 이동 | 민주→공화 쪽 | 공화→민주 쪽 | n |\n|---|---|---|---|---|---|---|")
        h = load(res, MODELS[0], "e6")["human"]
        for arm in ("delib", "control", "delib - control"):
            v = h[arm]
            L.append(f"| 인간 {arm} | — | {cell(v['shift_D'],2)} | {cell(v['shift_R'],2)} | {cell(v['toward_other_D'],2)} | {cell(v['toward_other_R'],2)} | {v.get('n_units','—')} |")
        for m in MODELS:
            for lab, v in load(res, m, "e6")["ai"].items():
                L.append(f"| AI {m} | {lab} | {cell(v['shift_D'],2)} | {cell(v['shift_R'],2)} | {cell(v['toward_other_D'],2)} | {cell(v['toward_other_R'],2)} | {v['n_blocks']} |")
    if all(have(m, "e7") for m in MODELS):
        L.append("\n## E7. 이동 방향 일치 (이동자 중 최빈 방향 비율)\n")
        L.append("| 집단 | A-기준선 | A-상태 | B | C |\n|---|---|---|---|---|")
        for m in MODELS:
            a = load(res, m, "e7")["ai"]
            L.append(f"| {m} | {cell(a['A-baseline'],2)} | {cell(a['A-stateful'],2)} | {cell(a['B-materials'],2)} | {cell(a['C-reanswer'],2)} |")
        hh = load(res, MODELS[0], "e7")["human"]
        L.append(f"| 인간 (5명 추출 / 소집단 전원) | {cell(hh['draw5'],2)} / {cell(hh['full_group'],2)} | | | |")
    if all(have(m, "e9") for m in MODELS):
        L.append("\n## E9. 집단 사전 평균에서 멀어지는 이동의 비율 (\\|Δ\\| ≥ 1인 에이전트 중, 블록 재표집)\n")
        L.append("| 모델 | A-기준선 | A-상태 | B | C | 문항 평균 SD 감소 < 0 인 문항 수 (기준선 / 상태) |\n|---|---|---|---|---|---|")
        for m in MODELS:
            e = load(res, m, "e9")
            L.append(f"| {m} | " + " | ".join(cell(e[lab]["share_moving_away_from_group_mean"], 2) for lab in ("A-baseline", "A-stateful", "B-materials", "C-reanswer")) +
                     f" | {e['A-baseline']['items_with_negative_mean_sd_drop']} / {e['A-stateful']['items_with_negative_mean_sd_drop']} (문항 {e['A-baseline']['n_items']}) |")
    if all(have(m, "e10") for m in MODELS):
        L.append("\n## E10. 이름 제거(debranded) 문항 대 같은 문항의 원 버전 (3문항 × 8집단, 블록 재표집)\n")
        L.append("| 모델 | 세트 | 조건 | 합의율 | SD 감소 | 평균 \\|이동\\| | D 쪽 상관 |\n|---|---|---|---|---|---|---|")
        for m in MODELS:
            e = load(res, m, "e10")
            for setname in ("groups", "debranded"):
                for lab, v in e[setname].items():
                    L.append(f"| {m} | {setname} | {lab} | {cell(v['consensus_sd'],2)} | {cell(v['sd_drop'],2)} | {cell(v['mean_abs_move'],2)} | {cell(v['toward_D_corr'],2)} |")
        L.append(f"\n문항: {', '.join(load(res, MODELS[0], 'e10')['items'])}\n")
    if (res / "human" / "e8_weighted.json").exists():
        e8 = json.loads((res / "human" / "e8_weighted.json").read_text())
        L.append("## E8. A1R 가중치 민감도 (가중 점추정, 문항 평균)\n")
        L.append("| 팔 | SD 감소 | 정당 격차 감소 | 이동자 비율 | 평균 이동 | n |\n|---|---|---|---|---|---|")
        for arm in ("delib", "control", "delib - control"):
            v = e8[arm]
            L.append(f"| {arm} | {f(v['sd_drop'])} | {f(v['gap_change'])} | {f(v['movers'])} | {f(v['mean_shift'])} | {v.get('n','—')} |")
    if all(have(m, "n4") for m in MODELS):
        L.append("\n## N4. 문항 간 이질성 τ² (REML, 공분산 Σ 반영; 구간 = 프로파일 우도 / 복제 백분위)\n")
        for ind, name in (("sd_drop", "SD 감소"), ("gap_change", "정당 격차 감소"), ("movers", "이동자 비율")):
            L.append(f"\n### {name}\n")
            L.append("| 계열 | 팔/조건 | τ² | τ | 프로파일 95% | 복제 95% | 평균 표집 분산 | 민감도 VR 성분 |\n|---|---|---|---|---|---|---|---|")
            hd = load(res, MODELS[0], "n4")["indicators"][ind]["human"]
            for arm in ("delib", "did"):
                v = hd[arm]
                L.append(f"| 인간 | {arm} | {f(v['tau2'],4)} | {f(v['tau'],3)} | [{f(v['profile_ci'][0],4)}, {f(v['profile_ci'][1],4)}] | [{f(v['boot_ci'][0],4)}, {f(v['boot_ci'][1],4)}] | {f(v['mean_sampling_var'],4)} | {f(v['naive']['estimate'],4)} |")
            for m in MODELS:
                r = load(res, m, "n4")["indicators"][ind]
                for lab in ("A-baseline - C-reanswer", "A-stateful - C-reanswer", "A-baseline", "A-stateful"):
                    v = r["ai"][lab]
                    L.append(f"| {m} | {lab} | {f(v['tau2'],4)} | {f(v['tau'],3)} | [{f(v['profile_ci'][0],4)}, {f(v['profile_ci'][1],4)}] | [{f(v['boot_ci'][0],4)}, {f(v['boot_ci'][1],4)}] | {f(v['mean_sampling_var'],4)} | {f(v['naive']['estimate'],4)} |")
            L.append("\n분산비 τ²(AI) / τ²(인간 숙의군−통제군) [규칙 적용], 민감도 VR, 순위 상관 ρ(인간 DiD, AI):\n\n| 모델 | 조건 | 비율 | 복제 95% | 상태 | 민감도 VR | 상태 | ρ | ρ 95% |\n|---|---|---|---|---|---|---|---|---|")
            for m in MODELS:
                r = load(res, m, "n4")["indicators"][ind]
                for lab in ("A-baseline - C-reanswer", "A-stateful - C-reanswer"):
                    ra, nv, rh = r["ratio_tau2_ai_over_human_did"][lab], r["naive_vr_sensitivity"][lab], r["spearman_human_did_vs_ai"][lab]
                    L.append(f"| {m} | {lab} | {f(ra.get('ratio'),2) if ra.get('ratio') is not None else '미산출'} | "
                             f"{('[' + f(ra['ratio_boot_ci'][0],2) + ', ' + f(ra['ratio_boot_ci'][1],2) + ']') if ra.get('ratio_boot_ci') else '—'} | {ra['status']} | "
                             f"{f(nv.get('ratio'),2) if nv.get('ratio') is not None else '미산출'} | {nv['status']} | {f(rh['rho'],2)} | [{f(rh['ci'][0],2)}, {f(rh['ci'][1],2)}] |")
            L.append("\n사전 갈등 조건부 (문항 지표 ~ 인간 사전 SD, OLS 기울기 / Pearson):\n\n| 모델 | 인간 DiD | AI 기준선 A−C | AI 상태 A−C |\n|---|---|---|---|")
            for m in MODELS:
                c = load(res, m, "n4")["indicators"][ind]["conditional_on_pre_sd"]
                L.append(f"| {m} | {f(c['human_did']['slope_per_pre_sd'],2)} / {f(c['human_did']['pearson'],2)} | {f(c['ai_A-baseline - C']['slope_per_pre_sd'],2)} / {f(c['ai_A-baseline - C']['pearson'],2)} | {f(c['ai_A-stateful - C']['slope_per_pre_sd'],2)} / {f(c['ai_A-stateful - C']['pearson'],2)} |")
    return "\n".join(L) + "\n"


def tables_phase_b(res: Path) -> str:
    """B단계 표: N1 보충, E5, S3, N6 ①③, N7, S5, E2, N8"""
    L = []
    have = lambda m, n: (res / m / f"{n}.json").exists()  # noqa: E731
    if all(have(m, "n1") for m in MODELS) and "mean_dist_human_pre" in load(res, MODELS[0], "n1")["consensus_location"]["A-baseline"]:
        L.append("## N1 보충. 합의점(블록 사후 평균)과 인간 숙의 전·후 평균의 거리 (문항→블록 재표집)\n")
        L.append("| 모델 | 조건 | 평균 거리: 인간 사전 | 인간 사후 | 사후에 더 가까운 블록 비율 |\n|---|---|---|---|---|")
        for m in MODELS:
            for lab in ("C-reanswer", "B-materials", "A-baseline", "A-stateful"):
                c = load(res, m, "n1")["consensus_location"][lab]
                L.append(f"| {m} | {lab} | {cell(c['mean_dist_human_pre'],2)} | {cell(c['mean_dist_human_post'],2)} | {cell(c['share_closer_to_human_post_than_pre'],2)} |")
    if all(have(m, "e5") for m in MODELS):
        L.append("\n## E5. 자료집 찬반 분량 균형(lean)과 B 조건 이동 (문항 30, Spearman)\n")
        L.append("| 모델 | lean vs (B−C) 이동 | lean vs B 이동 | lean vs (D − 인간 사전) | lean vs 인간 이동 | (B−C) 이동 vs (D − 인간 사전) | 부호 일치 lean·(B−C) |\n|---|---|---|---|---|---|---|")
        for m in MODELS:
            e = load(res, m, "e5")
            sp = e["spearman"]
            L.append(f"| {m} | {f(sp['lean vs B−C shift'],2)} | {f(sp['lean vs B shift'],2)} | {f(sp['lean vs D − human pre'],2)} | {f(sp['lean vs human shift'],2)} | {f(sp['B−C shift vs D − human pre'],2)} | {f(e['sign_agreement_lean_vs_B_minus_C'],2)} |")
        L.append(f"\nlean 범위 {f(e['lean_range'][0],2)}~{f(e['lean_range'][1],2)} (양수 = 찬성 논거가 더 김).\n")
    if all(have(m, "s3") for m in MODELS):
        L.append("## S3. 소수 의견자: 자기 사전 점수가 나머지 평균에서 먼 정도별 상대 쪽 이동 (평균 이동 / 상대 쪽으로 움직인 비율)\n")
        bins = load(res, MODELS[0], "s3")["bins"]
        L.append("| 집단 | 조건 | " + " | ".join(f"거리 {b}" for b in bins) + " | 기울기(거리당) | n 단위 |\n|---|---|" + "---|" * len(bins) + "---|---|")
        h = load(res, MODELS[0], "s3")["human"]["delib_small_group"]
        L.append("| 인간 소집단 | — | " + " | ".join(f"{f(h[f'toward_{b}']['estimate'],2)} / {f(h[f'share_toward_{b}']['estimate'],2)} (n {h[f'n_{b}']})" for b in bins) + f" | {cell(h['slope_toward_per_dist'],2)} | {h['n_units']} |")
        for m in MODELS:
            for lab, a in load(res, m, "s3")["ai"].items():
                L.append(f"| {m} | {lab} | " + " | ".join(f"{f(a[f'toward_{b}']['estimate'],2)} / {f(a[f'share_toward_{b}']['estimate'],2)}" for b in bins) + f" | {cell(a['slope_toward_per_dist'],2)} | {a['n_units']} |")
    if all(have(m, "n6_instructed") for m in MODELS):
        L.append("\n## N6 ①. 장치 지시: 실행당 수 (블록 재표집 2,000회)\n")
        keys = [("act_respond_challenge", "응답 의무"), ("act_mediate", "중재"), ("act_third_option", "제3안"), ("act_devils_advocate", "반대 검토"),
                ("note_moved", "\"움직였다\" 안내"), ("note_defend", "\"근거로 방어\" 안내"), ("note_switched", "\"입장 전환\" 안내"), ("note_reciprocity", "상호성 안내"),
                ("move_switch", "문턱 전환"), ("move_concession", "양보 이동"), ("challenges_created", "반박 생성"), ("challenge_resolution", "반박 해소율"), ("share_runs_with_any_switch", "전환 있는 실행 비율")]
        for study, name in (("wason", "1-A"), ("a1r", "1-B"), ("argq", "1-C")):
            L.append(f"\n### {name}\n")
            L.append("| 모델 | 모드 | " + " | ".join(n for _, n in keys) + " | 실행 |\n|---|---|" + "---|" * len(keys) + "---|")
            for m in MODELS:
                n6 = load(res, m, "n6_instructed")
                for mode in ("baseline", "stateful"):
                    k = f"{study}/{mode}"
                    if k not in n6:
                        continue
                    L.append(f"| {m} | {mode} | " + " | ".join(f(n6[k][kk]["estimate"], 2) for kk, _ in keys) + f" | {n6[k]['n_runs']} |")
        L.append("\n기준선의 문턱 전환·양보 이동은 상태 모형이 계산만 하고 보여 주지 않은 값(측정 부산물). 스케줄형 행위(rebut/undercut/agree_extend/example)는 발현 증거에서 제외.\n")
    if all(have(m, "n6_after") for m in MODELS):
        L.append("## N6 ③. 장치 발언 뒤의 변화 (연관, 인과 아님; 블록 재표집)\n")
        L.append("| 모델 | 연구 | 사건 | 해소율 (응답 의무) | 분석기: 도전자 겨냥 관계 있음 | Δ 분산 (window 뒤) | Δ 열린 반박 | 사건 수 |\n|---|---|---|---|---|---|---|---|")
        for m in MODELS:
            n6a = load(res, m, "n6_after")
            for study in ("wason", "a1r"):
                for ev, v in n6a.get(study, {}).items():
                    L.append(f"| {m} | {study} | {ev} | {cell(v['resolved'],2) if 'resolved' in v else '—'} | {cell(v['addressed_challenger_in_analysis'],2) if 'addressed_challenger_in_analysis' in v else '—'} | "
                             f"{cell(v['d_spread'],3) if 'd_spread' in v else '—'} | {cell(v['d_open'],2) if 'd_open' in v else '—'} | {v['n_events']} |")
        L.append(f"\nwindow = {load(res, MODELS[0], 'n6_after')['window']}발언. 'random' = 스케줄형·입장 발언 시점의 같은 창 변화(비교용).\n")
    if all(have(m, "n7") for m in MODELS):
        L.append("## N7. 엔진 입장값 x · 텍스트 입장(분석기) · 사후 설문 (1-B, 블록 재표집)\n")
        L.append("| 모델 | 모드 | r(x 최종, 설문) | r(텍스트 최종, 설문) | r(x, 텍스트) | r(Δx, Δ설문) | 평균 \\|x − 설문\\| | 실행 안 r(x, 텍스트) | n |\n|---|---|---|---|---|---|---|---|---|")
        for m in MODELS:
            n7 = load(res, m, "n7")
            for mode in ("baseline", "stateful"):
                p_ = n7["participants"][mode]
                w = n7["within_run_corr_x_text"].get(mode)
                L.append(f"| {m} | {mode} | {cell(p_['corr_xfinal_post'],2)} | {cell(p_['corr_textfinal_post'],2)} | {cell(p_['corr_xfinal_textfinal'],2)} | {cell(p_['corr_change_x_vs_change_post'],2)} | "
                         f"{cell(p_['mean_abs_xfinal_minus_post'],2)} | {cell(w,2) if w else '—'} | {p_['n']} |")
        L.append("\n문턱 전환 사건 (상태 기반):\n\n| 모델 | 사건 수 | 엔진 Δ (평균) | 전환자 텍스트 Δ (전환 방향) | 같은 창 다른 참가자 | 같은 방향 ≥ 0.2 비율 | 반대 방향 비율 | r(x 최종, 설문) 전환자 |\n|---|---|---|---|---|---|---|---|")
        for m in MODELS:
            s_ = load(res, m, "n7")["switch_events"]
            if not s_:
                continue
            L.append(f"| {m} | {s_['n_events']} | {cell(s_['engine_delta'],2)} | {cell(s_['text_delta_signed'],2)} | {cell(s_['others_text_delta_signed'],2)} | "
                     f"{cell(s_['share_text_moved_same_direction_ge_0.2'],2)} | {cell(s_['share_text_moved_opposite'],2)} | {cell(s_['corr_xfinal_post_switchers'],2)} |")
        L.append("\n설문은 (점수 − 5)/5로 [-1, 1]에 맞춤. 텍스트 입장은 엔진 x를 만든 같은 분석기의 판정이라 '자기 일치'이며 독립 검증은 D단계 코딩.\n")
    if all(have(m, "s5") for m in MODELS):
        L.append("## S5. 합의 시점: 입장값 분산(SD)이 0.3 아래로 처음 가는 정규화 시점 (전원 입장값이 있는 스냅숏만, 블록 재표집)\n")
        L.append("| 모델 | 연구/모드 | 시작 SD | 중간 SD | 끝 SD | 도달 비율 | 첫 도달 시점 (0~1) | 실행 |\n|---|---|---|---|---|---|---|---|")
        for m in MODELS:
            s5 = load(res, m, "s5")
            for k, v in s5.items():
                if k == "info":
                    continue
                L.append(f"| {m} | {k} | {cell(v['spread_start'],2)} | {cell(v['spread_mid'],2)} | {cell(v['spread_end'],2)} | {cell(v['reached'],2)} | {cell(v['t_first_below'],2)} | {v['n_runs']} |")
    if all(have(m, "e2") for m in MODELS):
        L.append("\n## E2. 1-A 상태 기반 실행의 과정 지표: 상태 기반 단독 실패 집단 대 k=0 성공 집단 대 그 외 (평균, 기술 통계)\n")
        L.append("| 모델 | 집단 | 실행 | 전환 수 | 전환 있음 | 응답 의무 | 중재 | 반대 검토 | 끝 분산 | 양보 이동 | 압력 이동 |\n|---|---|---|---|---|---|---|---|---|---|---|")
        for m in MODELS:
            for g, v in load(res, m, "e2").items():
                if g == "info":
                    continue
                L.append(f"| {m} | {g} | {v['n_runs']} | {f(v['n_switch'],2)} | {f(v['any_switch'],2)} | {f(v['n_respond_challenge'],2)} | {f(v['n_mediation'],2)} | {f(v['devils_advocate'],2)} | {f(v['spread_end'],3)} | {f(v['n_concession_moves'],2)} | {f(v['n_pressure_moves'],2)} |")
    if all(have(m, "n8") for m in MODELS):
        L.append("\n## N8 (부록). 장치 발생량과 결과의 연관 (상태 기반 실행 안, 혼합 모형, 인과 아님)\n")
        for m in MODELS:
            n8 = load(res, m, "n8")
            L.append(f"\n### {m}\n")
            L.append("| 결과 | 응답 의무 수 | 중재 수 | 전환 수 | 양보 이동 수 | 반대 검토 | 사전 SD / k | n |\n|---|---|---|---|---|---|---|---|")
            for k, v in n8.items():
                if k in ("info", "note"):
                    continue
                pre = v.get("sd_pre") or v.get("k_raw")
                L.append(f"| {k} | {cell(v['n_rc'],3)} | {cell(v['n_med'],3)} | {cell(v['n_switch'],3)} | {cell(v['n_conc'],3)} | {cell(v['da'],3)} | {cell(pre,3)} | {v['n']} |")
    return "\n".join(L) + "\n"


def tables_phase_c(res: Path) -> str:
    """C단계 표: N9, E1, E3, S7"""
    L = []
    have = lambda m, n: (res / m / f"{n}.json").exists()  # noqa: E731
    ms = [m for m in MODELS if have(m, "n9")]
    if ms:
        L.append("## N9. 답 변경 궤적 (1-A): 변경 시점·방향, 초기 정답자 유지 (집단 재표집 2,000회)\n")
        L.append("| 집단 | 사건 수 | 참가자 | 1사분기 | 2 | 3 | 4 | 오→정 | 정→오 | 오→오 | 참가자당 변경 | 변경한 참가자 비율 |\n|---|---|---|---|---|---|---|---|---|---|---|---|")
        n9 = load(res, ms[0], "n9")
        def row(name, s):
            return (f"| {name} | {s['n_events']} | {s['n_participants']} | " + " | ".join(cell(s[f'share_t_{b}'], 2) for b in ("0.00-0.25", "0.25-0.50", "0.50-0.75", "0.75-1.01")) +
                    f" | {cell(s['share_wrong_to_correct'],2)} | {cell(s['share_correct_to_wrong'],2)} | {cell(s['share_wrong_to_wrong'],2)} | {cell(s['changes_per_participant'],2)} | {cell(s['share_participants_changing'],2)} |")
        L.append(row("인간 (DeliData)", n9["human"]))
        for m in ms:
            for lab in ("A-baseline", "A-stateful"):
                L.append(row(f"{m} {lab}", load(res, m, "n9")["ai"][lab]))
        L.append("\n초기 정답자가 끝까지 정답인 비율 / 초기 오답자가 정답으로 끝나는 비율 (설문·최종 답 기준):\n\n| 집단 | 전체 | k=1 집단 | k=0 집단 |\n|---|---|---|---|")
        def rrow(name, r):
            return "| " + name + " | " + " | ".join(f"{cell(r[f'{k}_initially_correct_stay_correct'],2)} / {cell(r[f'{k}_initially_wrong_end_correct'],2)}" for k in ("all", "k1", "k0")) + " |"
        L.append(rrow("인간", n9["human_retention"]))
        for m in ms:
            for lab in ("A-baseline", "A-stateful"):
                L.append(rrow(f"{m} {lab}", load(res, m, "n9")["ai_retention"][lab]))
        for m in ms:
            q = load(res, m, "n9")["extraction_quality"]
            L.append(f"\n추출 품질 ({m}, {q.get('source')}): 발언 중 선택이 추출된 비율 {f(q['share_utterances_with_extraction'],2)}, 참가자 중 1회 이상 추출 {f(q['share_participants_with_any_extraction'],2)}, "
                     "마지막 추출 대 사후 설문 일치 " + ", ".join(f"{k} {f(v['share'],3)} (n {v['n']})" for k, v in q.get("last_extraction_matches_survey", {}).items()) + ".")
    if all(have(m, "e1e3") for m in MODELS):
        pats = ["P+Q", "P", "P+Q+notQ", "P+notP+Q+notQ", "P+notP", "P+notP+notQ", "notP+notQ"]
        L.append("\n## E1. 과반 오답 집단의 답 유형 (P=모음, Q=짝수, notQ=홀수, notP=자음; 정답 P+notQ; 집단 재표집)\n")
        L.append("| 집단 | n | " + " | ".join(pats) + " | 초기 오답과 같음 | 만장일치 |\n|---|---|" + "---|" * len(pats) + "---|---|")
        e = load(res, MODELS[0], "e1e3")["E1"]
        L.append(f"| 인간 | {e['human']['n_wrong_majority_groups']} | " + " | ".join(f(e['human'].get(f'share_{p}', {'estimate': 0})['estimate'], 2) for p in pats) + f" | {cell(e['human']['share_same_as_initial_wrong'],2)} | {cell(e['human']['share_unanimous'],2)} |")
        for m in MODELS:
            e = load(res, m, "e1e3")["E1"]
            for lab in ("A-baseline", "A-stateful"):
                v = e[lab]
                L.append(f"| {m} {lab} | {v['n_wrong_majority_groups']} | " + " | ".join(f(v.get(f'share_{p}', {'estimate': 0})['estimate'], 2) for p in pats) + f" | {cell(v['share_same_as_initial_wrong'],2)} | {cell(v['share_unanimous'],2)} |")
        L.append("\n## E3. k=1 집단(처음 정답자 1명): 최종 과반 답 (집단 재표집)\n")
        L.append("| 집단 | k=1 집단 수 | 과반이 정답 | 과반 없음 | 과반이 다른 오답 |\n|---|---|---|---|---|")
        e3 = load(res, MODELS[0], "e1e3")["E3"]["human"]
        L.append(f"| 인간 | {e3['n_k1_groups']} | {cell(e3['majority_is_correct'],2)} | {cell(e3['no_majority'],2)} | {cell(e3['majority_other_wrong'],2)} |")
        for m in MODELS:
            for lab in ("A-baseline", "A-stateful"):
                v = load(res, m, "e1e3")["E3"][lab]
                L.append(f"| {m} {lab} | {v['n_k1_groups']} | {cell(v['majority_is_correct'],2)} | {cell(v['no_majority'],2)} | {cell(v['majority_other_wrong'],2)} |")
    if all(have(m, "s7") for m in MODELS):
        L.append("\n## S7. 새 변형(60문항) 대 원 과제: 오답 유형과 'Wason' 언급 (기술 통계)\n")
        L.append("| 모델 | 과제/조건 | 집단 | 오답 개인 수 | 개인 오답 유형 (상위) | 과반 오답 집단 | 과반 오답 유형 |\n|---|---|---|---|---|---|---|")
        for m in MODELS:
            s7 = load(res, m, "s7")
            for k, v in s7.items():
                if k in ("info", "wason_mentions"):
                    continue
                L.append(f"| {m} | {k} | {v['n_groups']} | {v['n_wrong_individuals']} | {v['individual_wrong_patterns']} | {v['majority_wrong_groups']} | {v['majority_wrong_patterns']} |")
        L.append("\n발언에서 'Wason' 또는 'selection task' 언급:\n\n| 모델 | 과제 | 발언 비율 | 실행 비율 | 실행 수 |\n|---|---|---|---|---|")
        for m in MODELS:
            for k, v in load(res, m, "s7")["wason_mentions"].items():
                L.append(f"| {m} | {k} | {f(v['share_utterances_mentioning_wason'],3)} | {f(v['share_runs_mentioning'],3)} | {v['n_runs']} |")
    return "\n".join(L) + "\n"


def tables_phase_d(res: Path) -> str:
    """D단계 표: S6 (코딩 결과는 scripts/code_utterances.py 의 보고를 따로 붙인다)"""
    L = []
    ms = [m for m in MODELS if (res / m / "s6.json").exists()]
    if ms:
        L.append("## S6. 사후 이유 텍스트의 어휘 언급 비율 (1-B, 블록 재표집): 동료 이름 / 자료 어휘 / 토론 어휘 (언급이지 근거 사용 판정이 아님)\n")
        L.append("| 모델 | 조건 | n (빈 이유) | 동료 이름 | 자료 어휘 | 토론 어휘 | 평균 단어 수 |\n|---|---|---|---|---|---|---|")
        for m in ms:
            s6 = load(res, m, "s6")["by_condition"]
            for lab, v in s6.items():
                L.append(f"| {m} | {lab} | {v['mention_peer']['n']} ({v['n_empty']}) | {cell(v['mention_peer'],2)} | {cell(v['mention_materials'],2)} | {cell(v['mention_discussion'],2)} | {cell(v['n_words'],1)} |")
        L.append("")
    if (res / "claude" / "n10.json").exists():
        n10 = load(res, "claude", "n10")
        T = n10["targets"]
        L.append("## N10. 발언 유형 구성비 (DeliData 체계; 집단 평균 비율, 집단 재표집). 사람 = DeliData 사람 주석(같은 집단), AI = GLM 5.3 코딩. solution·reasoning은 해석 제한(합친 값으로 추론)\n")
        L.append("| 표본 | 집단 | 집단 수 | probing | " + " | ".join(T) + " | solution+reasoning |\n|---|---|---|---|" + "---|" * len(T) + "---|")
        def row(name, grp, c, n):
            sr = c["solution"]["estimate"] + c["reasoning"]["estimate"]
            return f"| {name} | {grp} | {n} | {cell(c['probing'],2)} | " + " | ".join(cell(c[t], 2) for t in T) + f" | {sr:.2f} |"
        for sample, v in n10["by_sample"].items():
            L.append(row(sample, "사람 (같은 집단)", v["human_same_groups"], v["human_same_groups"]["n_groups"]))
            for lab, c in v["conditions"].items():
                L.append(row(sample, lab, c, c["probing"]["n"]))
        L.append("\n쌍 차이 (같은 집단, AI − 사람 / 상태 − 기준선; 집단 쌍 재표집):\n")
        L.append("| 표본 | 차이 | 쌍 수 | probing | " + " | ".join(T) + " |\n|---|---|---|---|" + "---|" * len(T))
        for sample, v in n10["by_sample"].items():
            for lab, c in v["conditions"].items():
                d = c["ai_minus_human_paired"]
                L.append(f"| {sample} | {lab} − 사람 | {d['n_pairs']} | {cell(d['probing'],2)} | " + " | ".join(cell(d[t], 2) for t in T) + " |")
            if "stateful_minus_baseline_paired" in v:
                d = v["stateful_minus_baseline_paired"]
                L.append(f"| {sample} | 상태 − 기준선 | {d['n_pairs']} | {cell(d['probing'],2)} | " + " | ".join(cell(d[t], 2) for t in T) + " |")
        if "coder_agreement" in n10:
            a = n10["coder_agreement"]
            L.append(f"\n코더 간 일관성 (GLM 5.3 대 Mistral Large 3, 같은 발언 {a['n']}건; 정확성 아님): type 일치 {a['type']['exact']:.3f} (κ {a['type']['kappa']:.2f}), target 일치 {a['target']['exact']:.3f} (κ {a['target']['kappa']:.2f}); target 라벨별 일치 " + ", ".join(f"{k} {v:.2f}" for k, v in a["target"]["per_label_exact"].items()) + "\n")
        L.append("")
    if (res / "claude" / "n6b.json").exists():
        n6 = load(res, "claude", "n6b")
        L.append("## N6 ②. 장치 수행 판정 (Claude A-상태 장치 발언 각 300건 + A-기준선 대조 300건; 코더 비율, 재표집 없음)\n")
        for cname, c in n6["coders"].items():
            L.append(f"### 코더 {c['model']} (실패율 {c['fail_rate']:.3f})\n")
            items = ["addresses_specific_claim", "concedes_part", "names_disagreement_between_others", "proposes_third_option", "objects_to_shared_view", "states_position_change"]
            L.append("| 장치 | n | 지시 수행 yes / partial / no | " + " | ".join(items) + " |\n|---|---|---|" + "---|" * len(items))
            for dev, d in c["by_device"].items():
                inst = d.get("instruction_followed")
                ic = f"{inst['yes']:.2f} / {inst['partial']:.2f} / {inst['no']:.2f}" if inst else "(지시 없음)"
                L.append(f"| {dev} | {d['n']} | {ic} | " + " | ".join(f"{d['items'][i]['yes']:.2f} (+{d['items'][i]['partial']:.2f})" for i in items) + " |")
            L.append("\n셀 = yes 비율 (+partial 비율). 장치별 해당 항목: respond_challenge → addresses_specific_claim, mediate → names_disagreement_between_others, devils_advocate → objects_to_shared_view, switched → states_position_change.\n")
        if n6.get("agreement"):
            a = n6["agreement"]
            L.append(f"코더 간 일관성 ({' 대 '.join(a['coders'])}, {a['n']}건): " + "; ".join(f"{k} 일치 {v['exact']:.2f} (κ {v['kappa']:.2f}; yes 대 아님 κ {v['kappa_yes_vs_not']:.2f})" for k, v in a["items"].items()) + "\n")
        L.append("")
    if (res / "claude" / "l3.json").exists():
        l3 = load(res, "claude", "l3")
        L.append("## 층 3. 근거–결론 연결 (1-B Claude, 문항 30 × 엔진 2 × 블록 2 × 에이전트 5 = 600; 코더별 비율, 1차 코더는 블록 재표집 구간)\n")
        for cname, c in l3["coders"].items():
            L.append(f"### 코더 {c['model']} (n {c['n']}, 실패율 {c['fail_rate']:.3f})\n")
            L.append("| 조건 | n | 이유가 토론 논거를 참조 | 참조한 것 중 동료 논거 | 참조한 것 중 결론을 지지 | 참조한 것 중 반박됨 | 반박 해소(반박된 것 중) |\n|---|---|---|---|---|---|---|")
            for lab, d in c["by_label"].items():
                k = d["key"]
                rr = d["items"]["rebuttal_resolved"]
                res_share = rr.get("yes", 0) / max(rr.get("yes", 0) + rr.get("no", 0), 1e-9)
                L.append(f"| {lab} | {d['n']} | {cell(k['references'],2)} | {cell(k['peer_given_ref'],2)} | {cell(k['supports_given_ref'],2)} | {cell(k['rebutted_given_ref'],2)} | {res_share:.2f} |")
            L.append("")
        if l3.get("agreement"):
            a = l3["agreement"]
            L.append(f"코더 간 일관성 ({' 대 '.join(a['coders'])}, {a['n']}건): " + "; ".join(f"{k} 일치 {v['exact']:.2f} (κ {v['kappa']:.2f})" for k, v in a["items"].items()) + "\n")
        L.append("")
    return "\n".join(L) + "\n"


def tables_phase_e(res: Path) -> str:
    """E단계 표: S8 (분석기 신뢰도, 연결망), S4"""
    L = []
    if (res / "claude" / "s8.json").exists():
        s8 = load(res, "claude", "s8")
        if "analyzer_vs_coders" in s8:
            a = s8["analyzer_vs_coders"]
            L.append(f"## S8 전제. 분석기(meta.analysis) 대 N6 ② 코더(Mistral Large 3) 일치, 같은 발언 {a['n']}건 (분석기 신뢰도 점검; 코더도 사람 기준은 아님)\n")
            L.append("| 쌍 (코더 항목 ~ 분석기 필드) | 일치 | κ | 코더 yes | 분석기 yes | 분석기 yes, 코더 yes일 때 | 분석기 yes, 코더 no일 때 |\n|---|---|---|---|---|---|---|")
            for k, v in a["pairs"].items():
                L.append(f"| {k} | {v['agreement']:.2f} | {v['kappa']:.2f} | {v['coder_yes']:.2f} | {v['analyzer_yes']:.2f} | {v['analyzer_yes_given_coder_yes']:.2f} | {v['analyzer_yes_given_coder_no']:.2f} |")
            L.append("")
        n = s8["network"]
        L.append(f"## S8. 설득 연결망 (1-A 원 과제 k=1 집단 {n['n_groups']}개, 실행 {n['n_runs']}; 분석기 targets·influence; 발언당 횟수; 집단 재표집)\n")
        cols = ["recv_support_per_utt", "recv_attack_per_utt", "recv_concede_per_utt", "recv_question_per_utt", "recv_influence_quality", "sent_support_per_utt", "sent_attack_per_utt", "sent_concede_per_utt"]
        L.append("| 조건 | 대상 | " + " | ".join(c.replace("_per_utt", "") for c in cols) + " |\n|---|---|" + "---|" * len(cols))
        for lab, v in n["by_label"].items():
            for who in ("solver", "others"):
                L.append(f"| {lab} | {'처음 정답자' if who == 'solver' else '다른 구성원'} (n {v[who][cols[0]]['n']}) | " + " | ".join(cell(v[who][c], 2) for c in cols) + " |")
            L.append(f"| {lab} | 차이 (정답자 − 다른) | " + " | ".join(cell(v["solver_minus_others"][c], 2) for c in cols) + " |")
        L.append("\n결과별 (과반 정답 여부; 정답자 / 다른 구성원 평균):\n\n| 조건 | 결과 | 실행 수 | 받은 지지 | 받은 반박 | 받은 양보 |\n|---|---|---|---|---|---|")
        for lab, v in n["by_label"].items():
            for oc, w in v["by_outcome"].items():
                L.append(f"| {lab} | {oc} | {w['n_runs']} | {w['recv_support_per_utt']['solver']:.2f} / {w['recv_support_per_utt']['others']:.2f} | {w['recv_attack_per_utt']['solver']:.2f} / {w['recv_attack_per_utt']['others']:.2f} | {w['recv_concede_per_utt']['solver']:.2f} / {w['recv_concede_per_utt']['others']:.2f} |")
        L.append("")
    if (res / "claude" / "s4.json").exists():
        s4 = load(res, "claude", "s4")
        L.append(f"## S4. 1-C 세트를 공모자 논거 방향이 D와 같은지로 나눠 재추정 (D = 사후 측정 D-prior 평균; Δc = Δ − 세트별 C-재응답 평균 Δ; 세트 {s4['n_sets']}개)\n")
        L.append("주제별 D̂: " + ", ".join(f"{k} {v:.0f}" for k, v in sorted(s4["d_hat"].items())) + f"\n\nD와 같은 방향 세트 {len(s4['sets_with_D'])}개, 비정렬 세트 {len(s4['sets_against_D'])}개. 비정렬은 반대 방향과 중립 기본 입장(D=50)을 포함하며, 기존 against_D 키가 이 집합을 가리킨다.\n")
        L.append("| 분할 | 세트 | n | 평균 Δ | 평균 Δc | q (질) | sup (지지) | eng | q:eng | sup:eng |\n|---|---|---|---|---|---|---|---|---|---|")
        for name, v in s4["by_split"].items():
            if "model_delta_c" not in v:
                L.append(f"| {name} | {v['n_sets']} | — | — | — | {v.get('note','')} | | | | |")
                continue
            m = v["model_delta_c"]
            def term(k):
                if "error" in m:
                    return "오류"
                x = m.get(k, {})
                return f"{x.get('estimate', float('nan')):.2f} [{x.get('ci', [float('nan')]*2)[0]:.2f}, {x.get('ci', [float('nan')]*2)[1]:.2f}]" if "estimate" in x else "—"
            L.append(f"| {name} | {v['n_sets']} | {v['n']} | {v['mean_delta']:.2f} | {v['mean_delta_c']:.2f} | {term('q')} | {term('sup')} | {term('eng')} | {term('q:eng')} | {term('sup:eng')} |")
        L.append("\n셀 평균 Δc (분할 × q × sup × eng):\n")
        for name, v in s4["by_split"].items():
            if "cell_means_delta_c" in v:
                L.append(f"- {name}: " + "; ".join(f"{k} {x:.1f}" for k, x in v["cell_means_delta_c"].items()))
        L.append("")
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--res", required=True)
    p.add_argument("--figs", required=True)
    p.add_argument("--tables", required=True)
    args = p.parse_args(argv)
    res, figs = Path(args.res), Path(args.figs)
    made = []
    made += figures.fig_agreement(res, figs, MODELS)
    made += figures.fig_truth_wins(res, figs, MODELS)
    for fn in (figures.fig_direction, figures.fig_default_vs_human, figures.fig_heterogeneity, figures.fig_devices, figures.fig_minority):
        try:
            made += fn(res, figs, MODELS)
        except FileNotFoundError as e:
            print('skip', fn.__name__, e)
    for m in MODELS:
        made += figures.fig_items(res, figs, m)
        made += figures.fig_reanswer_default(res, figs, m, res / m / "a1r_blocks.csv", res / m / "a1r_agents.csv")
        for fn in (figures.fig_engine_vs_survey, figures.fig_spread_trajectory, figures.fig_wrong_types, figures.fig_change_timing):
            try:
                made += fn(res, figs, m)
            except FileNotFoundError as e:
                print('skip', fn.__name__, e)
    for fn in (figures.fig_composition, figures.fig_device_observed, figures.fig_network_solver):
        try:
            made += fn(res, figs, "claude")
        except FileNotFoundError as e:
            print('skip', fn.__name__, e)
    Path(args.tables).write_text(tables(res), encoding="utf-8")
    Path(args.tables).with_name("tables_phase_a.md").write_text(tables_phase_a(res), encoding="utf-8")
    Path(args.tables).with_name("tables_phase_b.md").write_text(tables_phase_b(res), encoding="utf-8")
    Path(args.tables).with_name("tables_phase_c.md").write_text(tables_phase_c(res), encoding="utf-8")
    Path(args.tables).with_name("tables_phase_d.md").write_text(tables_phase_d(res), encoding="utf-8")
    Path(args.tables).with_name("tables_phase_e.md").write_text(tables_phase_e(res), encoding="utf-8")
    print("\n".join(str(p) for p in made))
    return 0


if __name__ == "__main__":
    sys.exit(main())
