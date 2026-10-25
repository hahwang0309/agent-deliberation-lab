"""
연구 1 탐색 분석 그림 (논문용). 입력은 scripts/analyze_study1_exploratory.py 출력, 출력은 PNG(300dpi) + PDF.

색: 인간 기준 = 중립 회색(빗금), AI 조건은 고정 순서 (기준선 파랑, 상태 기반 주황, B 초록, C 황토). 글자는 항상 잉크색.
"""
import json
from pathlib import Path
from typing import List

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

INK, INK2, GRID = "#0b0b0b", "#52514e", "#dcdbd6"
HUMAN = "#8a8984"
COLORS = {"A-baseline": "#2a78d6", "A-stateful": "#eb6834", "B-materials": "#199e70", "C-reanswer": "#c98500"}
LABELS = {"A-baseline": "Baseline engine", "A-stateful": "Stateful engine", "B-materials": "B: materials only",
          "C-reanswer": "C: re-answer only", "human": "Human (reference)"}
MODELS = {"claude": "Claude Haiku 4.5", "gemini": "Gemini 3.5 Flash-Lite", "mistral": "Mistral Small"}
SHORT = {"claude": "Claude", "gemini": "Gemini", "mistral": "Mistral"}
MODEL_NOTE = "Claude = Claude Haiku 4.5, Gemini = Gemini 3.5 Flash-Lite, Mistral = Mistral Small (2603)."

plt.rcParams.update({"font.size": 8.5, "axes.titlesize": 9.5, "axes.labelsize": 8.5, "legend.fontsize": 7.5,
                     "axes.edgecolor": INK2, "axes.linewidth": 0.6, "xtick.color": INK2, "ytick.color": INK2,
                     "text.color": INK, "axes.labelcolor": INK, "axes.spines.top": False, "axes.spines.right": False,
                     "grid.color": GRID, "grid.linewidth": 0.5, "font.family": "sans-serif"})


def _load(path: Path) -> dict:
    return json.loads(Path(path).read_text())


def _save(fig, out: Path, name: str) -> List[Path]:
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for ext in ("png", "pdf"):
        p = out / f"{name}.{ext}"
        fig.savefig(p, dpi=300, bbox_inches="tight", facecolor="white")
        paths.append(p)
    plt.close(fig)
    return paths


def _err(est: float, ci: List[float]) -> np.ndarray:
    return np.array([[est - ci[0]], [ci[1] - est]])


def _note(fig, text: str, y: float = -0.02) -> None:
    fig.text(0.0, y, text, fontsize=6.5, color=INK2, ha="left", va="top", wrap=True)


def fig_agreement(res: Path, out: Path, models: List[str]) -> List[Path]:
    """F2: (A) 1-A 만장일치율(정답·오답 분리) (B) 1-B 합의율(사후 SD ≤ 1). 인간 기준은 회색 빗금"""
    fig, axes = plt.subplots(1, 2, figsize=(7.5, 3.0), gridspec_kw={"width_ratios": [1, 1.3], "wspace": 0.35})
    ax = axes[0]
    n2 = {m: _load(res / m / "n2a.json") for m in models}
    h = n2[models[0]]["rates"]["human"]
    width = 0.34

    def bar(ax, x, rc, rw, tot, color, hatch=None):
        ax.bar(x, rc["estimate"], width, color=color, hatch=hatch, edgecolor="white", linewidth=0.8)
        ax.bar(x, rw["estimate"], width, bottom=rc["estimate"], color=color, alpha=0.35, hatch=hatch, edgecolor="white", linewidth=0.8)
        ax.errorbar(x, tot["estimate"], yerr=_err(tot["estimate"], tot["ci"]), fmt="none", ecolor=INK, elinewidth=0.8, capsize=2)
        ax.text(x, tot["ci"][1] + 0.02, f"{tot['estimate']:.2f}", ha="center", va="bottom", fontsize=6.5, color=INK2)

    ticks, labels, x = [], [], 0.0
    bar(ax, x, h["unanimous_correct"]["all"], h["unanimous_wrong"]["all"], h["unanimous"]["all"], HUMAN, "///")
    ticks.append(x)
    labels.append("Human")
    for m in models:
        x += 1.0
        r = n2[m]["rates"]
        bar(ax, x - width / 2 - 0.02, r["base"]["unanimous_correct"]["all"], r["base"]["unanimous_wrong"]["all"], r["base"]["unanimous"]["all"], COLORS["A-baseline"])
        bar(ax, x + width / 2 + 0.02, r["state"]["unanimous_correct"]["all"], r["state"]["unanimous_wrong"]["all"], r["state"]["unanimous"]["all"], COLORS["A-stateful"])
        ticks.append(x)
        labels.append(SHORT[m])
    ax.set_xticks(ticks)
    ax.set_xticklabels(labels)
    ax.set_ylim(0, 1.12)
    ax.set_ylabel("Share of groups with a unanimous final answer")
    ax.set_title("A  Wason task (1-A): unanimity", loc="left")
    ax.yaxis.grid(True)
    ax.set_axisbelow(True)

    ax = axes[1]
    b = {m: _load(res / m / "n2b.json") for m in models}
    hum = b[models[0]]["human"]["consensus_sd"]["draw5"]
    width = 0.18
    ticks, labels, x = [], [], 0.0
    ax.bar(x, hum["estimate"], width * 2, color=HUMAN, hatch="///", edgecolor="white")
    ax.errorbar(x, hum["estimate"], yerr=_err(hum["estimate"], hum["ci"]), fmt="none", ecolor=INK, elinewidth=0.8, capsize=2)
    ax.text(x, hum["ci"][1] + 0.01, f"{hum['estimate']:.2f}", ha="center", va="bottom", fontsize=6.5, color=INK2)
    ticks.append(x)
    labels.append("Human")
    for m in models:
        x += 1.0
        for j, lab in enumerate(["A-baseline", "A-stateful", "B-materials", "C-reanswer"]):
            v = b[m]["ai"]["consensus_sd"][lab]
            xx = x + (j - 1.5) * (width + 0.02)
            ax.bar(xx, v["estimate"], width, color=COLORS[lab], edgecolor="white")
            ax.errorbar(xx, v["estimate"], yerr=_err(v["estimate"], v["ci"]), fmt="none", ecolor=INK, elinewidth=0.8, capsize=1.5)
            ax.text(xx, v["ci"][1] + 0.012, f"{v['estimate']:.2f}", ha="center", va="bottom", fontsize=5.8, color=INK2, rotation=90)
        ticks.append(x)
        labels.append(SHORT[m])
    ax.set_xticks(ticks)
    ax.set_xticklabels(labels)
    ax.set_ylim(0, 0.62)
    ax.set_ylabel("Share of group × item units with post SD ≤ 1")
    ax.set_title("B  Policy items (1-B): agreement after the session", loc="left")
    ax.yaxis.grid(True)
    ax.set_axisbelow(True)

    handles = [Patch(facecolor="white", edgecolor=INK2, hatch="///", label="Human (reference)"),
               Patch(color=COLORS["A-baseline"], label="AI, baseline engine"), Patch(color=COLORS["A-stateful"], label="AI, stateful engine"),
               Patch(color=COLORS["B-materials"], label="AI, B: materials only"), Patch(color=COLORS["C-reanswer"], label="AI, C: re-answer only"),
               Patch(facecolor=INK2, alpha=0.35, label="Lighter top segment (panel A): unanimous but wrong")]
    fig.legend(handles=handles, frameon=False, loc="upper center", bbox_to_anchor=(0.5, 0.0), ncol=3)
    _note(fig, "Point estimates with 95% bootstrap intervals (1-A: 471 DeliData groups; 1-B AI: items > blocks; 1-B human: 40 small groups). "
          "The human 1-B value draws 5 members per small group × item to standardize group size; it is not a replication of 5-person "
          "deliberation. " + MODEL_NOTE, y=-0.12)
    return _save(fig, out, "fig_agreement")


def fig_truth_wins(res: Path, out: Path, models: List[str]) -> List[Path]:
    """F4: 초기 정답자 수 k별 개인 정답률 — 인간(회색) 대 AI 기준선·상태 기반, 모델별 패널"""
    fig, axes = plt.subplots(1, len(models), figsize=(7.5, 2.7), sharey=True, gridspec_kw={"wspace": 0.12})
    ks = ["0", "1", "2+"]
    nk = None
    for ax, m in zip(np.atleast_1d(axes), models):
        n0 = _load(res / m / "n0.json")
        nk = n0["blocks_by_k"]
        for arm, color, lab, marker in (("human", HUMAN, "Human (DeliData)", "s"), ("ai_baseline", COLORS["A-baseline"], "AI, baseline engine", "o"),
                                        ("ai_stateful", COLORS["A-stateful"], "AI, stateful engine", "^")):
            est = [n0["rates"][arm][k]["estimate"] for k in ks]
            lo = [n0["rates"][arm][k]["ci"][0] for k in ks]
            hi = [n0["rates"][arm][k]["ci"][1] for k in ks]
            ax.plot(range(3), est, color=color, marker=marker, markersize=4.5, linewidth=1.6, label=lab)
            ax.fill_between(range(3), lo, hi, color=color, alpha=0.15, linewidth=0)
        ax.set_xticks(range(3))
        ax.set_xticklabels(ks)
        ax.set_xlim(-0.3, 2.3)
        ax.set_xlabel("Initially correct members (k)")
        ax.set_title(MODELS[m], loc="left")
        ax.set_ylim(0, 1.05)
        ax.yaxis.grid(True)
        ax.set_axisbelow(True)
    np.atleast_1d(axes)[0].set_ylabel("Individual accuracy after discussion")
    np.atleast_1d(axes)[0].legend(frameon=False, loc="lower right")
    _note(fig, f"k = number of initially correct members in the DeliData group (groups: k=0 n={nk['0']}, k=1 n={nk['1']}, k=2+ n={nk['2+']}); "
          "the same initial answers are seeded to the AI agents. Bands = 95% bootstrap interval over groups. The human line is identical in "
          "all panels. AI baseline pools 3 replicate runs per group.", y=-0.06)
    return _save(fig, out, "fig_truth_wins")


def fig_items(res: Path, out: Path, model: str) -> List[Path]:
    """F3 초안: 문항별 인간 숙의군−통제군 차이(회색)와 AI A−C 조건 차이(기준선·상태 기반). 세 지표 별도 열"""
    hum = pd.read_csv(res / "human" / "n3_human_items.csv").set_index("item")
    ai = pd.read_csv(res / model / "n3_ai_items.csv").set_index("item")
    inds = [("sd_drop", "SD reduction (pre − post)"), ("gap_change", "Party-gap reduction |D − R|"), ("movers", "Share moving ≥ 2 points")]
    order = hum.sort_values("did_sd_drop").index.tolist()
    fig, axes = plt.subplots(1, 3, figsize=(7.5, 6.4), sharey=True, gridspec_kw={"wspace": 0.12})
    y = np.arange(len(order))
    for ax, (ind, title) in zip(axes, inds):
        h = hum.loc[order]
        ax.errorbar(h[f"did_{ind}"], y + 0.22, xerr=[h[f"did_{ind}"] - h[f"did_{ind}_lo"], h[f"did_{ind}_hi"] - h[f"did_{ind}"]],
                    fmt="s", color=HUMAN, markersize=3.5, elinewidth=0.8, capsize=0)
        for lab, dy, mk in (("A-baseline", 0.0, "o"), ("A-stateful", -0.22, "^")):
            col = f"{ind}|{lab} - C-reanswer"
            a = ai.loc[order]
            ax.errorbar(a[col], y + dy, xerr=[a[col] - a[f"{col}_lo"], a[f"{col}_hi"] - a[col]], fmt=mk, color=COLORS[lab],
                        markersize=3.5, elinewidth=0.8, capsize=0)
        ax.axvline(0, color=INK2, linewidth=0.6)
        ax.set_title(title, loc="left", fontsize=8.5)
        ax.xaxis.grid(True)
        ax.set_axisbelow(True)
        ax.set_ylim(-0.8, len(order) - 0.2)
    axes[0].set_yticks(y)
    axes[0].set_yticklabels(order, fontsize=7)
    axes[0].set_ylabel("A1R item (sorted by the human SD-reduction difference)")
    handles = [Line2D([], [], marker="s", color=HUMAN, linestyle="none", markersize=4, label="Human: deliberation − control"),
               Line2D([], [], marker="o", color=COLORS["A-baseline"], linestyle="none", markersize=4, label=f"{SHORT[model]}, baseline engine: A − C"),
               Line2D([], [], marker="^", color=COLORS["A-stateful"], linestyle="none", markersize=4, label=f"{SHORT[model]}, stateful engine: A − C")]
    fig.legend(handles=handles, frameon=False, loc="upper center", bbox_to_anchor=(0.5, 0.975), ncol=3)
    fig.suptitle(f"Per-item deliberation response: human (deliberation − control) vs {MODELS[model]} (A − C)", x=0.0, ha="left",
                 fontsize=9.5, y=1.01)
    fig.subplots_adjust(top=0.9)
    _note(fig, "Whiskers = 95% bootstrap intervals (human: small groups and control participants resampled jointly across items; "
          "AI: blocks within item). 30 items are the effective sample for item-level comparisons; draws and replicate blocks do not add items. "
          "A − C = discussion condition minus re-answer-only condition in the same block.", y=0.04)
    return _save(fig, out, f"fig_items_{model}")


def fig_reanswer_default(res: Path, out: Path, model: str, blocks_csv: Path, agents_csv: Path) -> List[Path]:
    """N12: 1-B 사후 이동(post − pre) 대 모델 기본 입장까지의 거리(D − pre), 조건별 패널"""
    ag = pd.read_csv(agents_csv)
    labs = ["C-reanswer", "B-materials", "A-baseline", "A-stateful"]
    fig, axes = plt.subplots(1, 4, figsize=(7.5, 2.5), sharex=True, sharey=True, gridspec_kw={"wspace": 0.12})
    rng = np.random.default_rng(0)
    n12 = _load(res / model / "n12.json")
    for ax, lab in zip(axes, labs):
        a = ag[(ag["label"] == lab)].dropna(subset=["pre", "post", "D"])
        x, yv = (a["D"] - a["pre"]).to_numpy(), (a["post"] - a["pre"]).to_numpy()
        ax.scatter(x + rng.uniform(-0.15, 0.15, len(x)), yv + rng.uniform(-0.15, 0.15, len(x)), s=4, alpha=0.25, color=COLORS[lab], linewidths=0)
        s = n12[f"1-B {lab}"]
        slope, r = s["slope_toward_D"]["estimate"], s["corr_toward_D"]["estimate"]
        xx = np.linspace(-10, 10, 2)
        ax.plot(xx, slope * xx, color=INK, linewidth=1.2)
        ax.plot(xx, xx, color=INK2, linewidth=0.6, linestyle=":")
        ax.axhline(0, color=GRID, linewidth=0.6)
        ax.axvline(0, color=GRID, linewidth=0.6)
        ax.set_title(LABELS[lab], loc="left", fontsize=8)
        ax.text(0.04, 0.96, f"slope {slope:.2f} [{s['slope_toward_D']['ci'][0]:.2f}, {s['slope_toward_D']['ci'][1]:.2f}]\nr = {r:.2f}",
                transform=ax.transAxes, va="top", fontsize=6.5, color=INK)
        ax.set_xlim(-10, 10)
        ax.set_ylim(-10, 10)
        ax.set_xticks([-8, -4, 0, 4, 8])
        ax.set_yticks([-8, -4, 0, 4, 8])
    axes[0].set_ylabel("Post − pre")
    fig.supxlabel("Model default position − seeded prior (D − pre)", fontsize=8.5, y=-0.02)
    fig.suptitle(f"{MODELS[model]}, 1-B: change after the session vs distance to the model's default position", x=0.0, ha="left",
                 fontsize=9.5, y=1.08)
    _note(fig, "Solid line = OLS slope with block-bootstrap interval; dotted = full regression to the default (slope 1). "
          "D = the same persona answering without a seeded prior, materials or discussion. Points jittered.", y=-0.12)
    return _save(fig, out, f"fig_reanswer_default_{model}")


# ---------------- A단계 그림 ----------------

def fig_direction(res: Path, out: Path, models: List[str]) -> List[Path]:
    """F1: (A) β(기본 입장)·γ(집단 평균) 조건별·모델별 (B) 합의점이 가장 가까운 기준(D / 사전 평균 / 인간 사후 평균) 비율"""
    fig, axes = plt.subplots(1, 2, figsize=(7.5, 3.0), gridspec_kw={"width_ratios": [1.1, 1], "wspace": 0.35})
    ax = axes[0]
    n1 = {m: _load(res / m / "n1.json") for m in models}
    width = 0.17
    ticks, labels = [], []
    for i, m in enumerate(models):
        x0 = i * 1.0
        for j, (lab, coef, color, hatch) in enumerate((("A-baseline", "beta", COLORS["A-baseline"], None), ("A-baseline", "gamma", COLORS["A-baseline"], "..."),
                                                        ("A-stateful", "beta", COLORS["A-stateful"], None), ("A-stateful", "gamma", COLORS["A-stateful"], "..."))):
            v = n1[m]["models"][lab][coef]
            xx = x0 + (j - 1.5) * (width + 0.02)
            ax.bar(xx, v["estimate"], width, color=color, hatch=hatch, edgecolor="white", linewidth=0.8)
            ax.errorbar(xx, v["estimate"], yerr=_err(v["estimate"], v["ci"]), fmt="none", ecolor=INK, elinewidth=0.8, capsize=1.5)
            ax.text(xx, v["ci"][1] + 0.012, f"{v['estimate']:.2f}", ha="center", va="bottom", fontsize=5.8, color=INK2, rotation=90)
        ticks.append(x0)
        labels.append(SHORT[m])
    ax.set_xticks(ticks)
    ax.set_xticklabels(labels)
    ax.axhline(0, color=INK2, linewidth=0.6)
    ax.set_ylabel("Coefficient (post − pre per unit of distance)")
    ax.set_title("A  β: pull toward model default, γ: pull toward group mean", loc="left", fontsize=8.5)
    ax.yaxis.grid(True)
    ax.set_axisbelow(True)
    handles = [Patch(color=COLORS["A-baseline"], label="Baseline engine, β (default)"), Patch(facecolor=COLORS["A-baseline"], hatch="...", edgecolor="white", label="Baseline engine, γ (group)"),
               Patch(color=COLORS["A-stateful"], label="Stateful engine, β (default)"), Patch(facecolor=COLORS["A-stateful"], hatch="...", edgecolor="white", label="Stateful engine, γ (group)")]
    ax.legend(handles=handles, frameon=False, loc="upper left", bbox_to_anchor=(0.0, -0.16), ncol=2, fontsize=6.8)
    ax = axes[1]
    cats = [("share_nearest_D", "nearest: model default D", "#0b0b0b"), ("share_nearest_pre_mean", "nearest: group pre-mean", "#8a8984"),
            ("share_nearest_human_post", "nearest: human post-mean", "#d9d8d2")]
    labs = ["C-reanswer", "B-materials", "A-baseline", "A-stateful"]
    codes = {"C-reanswer": "C", "B-materials": "B", "A-baseline": "Ab", "A-stateful": "As"}
    ticks, labels = [], []
    for i, m in enumerate(models):
        for j, lab in enumerate(labs):
            xx = i * 1.0 + (j - 1.5) * 0.21
            bottom = 0.0
            c = n1[m]["consensus_location"][lab]
            for key, name, color in cats:
                v = c[key]["estimate"]
                ax.bar(xx, v, 0.19, bottom=bottom, color=color, edgecolor="white", linewidth=0.6)
                bottom += v
            ax.text(xx, 1.02, codes[lab], ha="center", va="bottom", fontsize=6, color=COLORS[lab])
        ticks.append(i * 1.0)
        labels.append(SHORT[m])
    ax.set_xticks(ticks)
    ax.set_xticklabels(labels)
    ax.set_ylim(0, 1.08)
    ax.set_ylabel("Share of blocks (1-B)")
    ax.set_title("B  Nearest reference to the block post-mean", loc="left", fontsize=8.5)
    ax.yaxis.grid(True)
    ax.set_axisbelow(True)
    handles = [Patch(color=c, label=n) for _, n, c in cats]
    ax.legend(handles=handles, frameon=False, loc="upper left", bbox_to_anchor=(0.0, -0.16), ncol=1, fontsize=6.8)
    _note(fig, "A: registered H2c model refit per condition (post − pre ~ β·(D − pre) + γ·(group pre-mean − pre), random intercepts for block and item); "
          "whiskers = 95% CI (Satterthwaite). B: for each block × condition, which of three references is closest to the post-session mean; "
          "condition codes above bars: C = re-answer only, B = materials only, Ab = baseline engine, As = stateful engine. " + MODEL_NOTE, y=-0.34)
    return _save(fig, out, "fig_direction")


def fig_default_vs_human(res: Path, out: Path, models: List[str]) -> List[Path]:
    """S1: 문항별 모델 기본 입장 D 대 인간 사전·사후 평균"""
    fig, axes = plt.subplots(1, len(models), figsize=(7.5, 2.7), sharex=True, sharey=True, gridspec_kw={"wspace": 0.12})
    for ax, m in zip(np.atleast_1d(axes), models):
        t = pd.read_csv(res / m / "s1_items.csv")
        s1 = _load(res / m / "s1.json")
        ax.plot([0, 10], [0, 10], color=GRID, linewidth=0.8)
        for i, r in t.iterrows():
            ax.annotate("", xy=(r["D"], r["human_post"]), xytext=(r["D"], r["human_pre"]), arrowprops=dict(arrowstyle="-", color=GRID, lw=0.6))
        ax.scatter(t["D"], t["human_pre"], s=12, facecolors="white", edgecolors=INK2, linewidths=0.7, label="human pre-deliberation mean", zorder=3)
        ax.scatter(t["D"], t["human_post"], s=12, color=INK, label="human post-deliberation mean", zorder=4)
        ax.set_title(MODELS[m], loc="left")
        ax.text(0.03, 0.97, f"ρ(D, human post) = {s1['spearman_D_human_post']['estimate']:.2f}\nρ(D, human pre) = {s1['spearman_D_human_pre']['estimate']:.2f}\n"
                f"mean |D − post| = {s1['mean_abs_D_minus_human_post']['estimate']:.2f}, |D − pre| = {s1['mean_abs_D_minus_human_pre']['estimate']:.2f}",
                transform=ax.transAxes, va="top", fontsize=6.3, color=INK)
        ax.set_xlim(0, 10)
        ax.set_ylim(0, 10)
        ax.xaxis.grid(True)
        ax.yaxis.grid(True)
        ax.set_axisbelow(True)
    np.atleast_1d(axes)[0].set_ylabel("Human item mean (A1R delegates)")
    np.atleast_1d(axes)[0].legend(frameon=False, loc="lower right", fontsize=6.5)
    fig.supxlabel("Model default position D (item mean, 0–10)", fontsize=8.5, y=-0.02)
    _note(fig, "Each point is one of the 30 A1R items. D = the same personas answering without seeded prior, materials or discussion. "
          "Vertical ticks join an item's human pre- and post-deliberation means. Diagonal = D equal to the human mean. ρ = Spearman over 30 items.", y=-0.12)
    return _save(fig, out, "fig_default_vs_human")


def fig_heterogeneity(res: Path, out: Path, models: List[str]) -> List[Path]:
    """N4: 문항 간 이질성 τ (표준편차 단위), 인간 숙의군−통제군 대 AI A−C, 지표별"""
    inds = [("sd_drop", "SD reduction"), ("gap_change", "Party-gap reduction"), ("movers", "Share moving ≥ 2")]
    fig, axes = plt.subplots(1, 3, figsize=(7.5, 2.6), sharey=True, gridspec_kw={"wspace": 0.15})
    for ax, (ind, title) in zip(axes, inds):
        rows = []
        h = _load(res / models[0] / "n4.json")["indicators"][ind]["human"]["did"]
        rows.append(("Human\ndelib − control", HUMAN, h))
        for m in models:
            r = _load(res / m / "n4.json")["indicators"][ind]
            rows.append((f"{SHORT[m]}\nbaseline A − C", COLORS["A-baseline"], r["ai"]["A-baseline - C-reanswer"]))
            rows.append((f"{SHORT[m]}\nstateful A − C", COLORS["A-stateful"], r["ai"]["A-stateful - C-reanswer"]))
        y = np.arange(len(rows))[::-1]
        for yi, (name, color, v) in zip(y, rows):
            tau = np.sqrt(v["tau2"])
            lo, hi = np.sqrt(max(v["profile_ci"][0], 0)), np.sqrt(v["profile_ci"][1]) if np.isfinite(v["profile_ci"][1]) else tau
            ax.errorbar(tau, yi, xerr=[[tau - lo], [hi - tau]], fmt="o", color=color, markersize=4, elinewidth=0.9, capsize=2)
        ax.set_yticks(y)
        ax.set_yticklabels([r[0] for r in rows], fontsize=6.3)
        ax.set_title(title, loc="left", fontsize=8.5)
        ax.xaxis.grid(True)
        ax.set_axisbelow(True)
        ax.set_xlim(left=0)
    fig.supxlabel("τ = between-item SD of the true effect (same units as the indicator)", fontsize=8.5, y=-0.02)
    _note(fig, "τ² estimated by REML with the item-level sampling covariance Σ from joint resampling (humans: small groups and control participants; "
          "AI: blocks within item, persona cross-item dependence not preserved). Whiskers = profile-likelihood 95% interval. 30 items.", y=-0.14)
    return _save(fig, out, "fig_heterogeneity")


# ---------------- B단계 그림 ----------------

def fig_devices(res: Path, out: Path, models: List[str]) -> List[Path]:
    """N6 ①: 실행당 장치 지시 수 (1-A·1-B), 기준선 대 상태 기반. 주 모델만 (다른 모델은 표). 가로 막대"""
    model = models[0]
    items = [("act_respond_challenge", "Reply obligation (respond_challenge)"), ("act_mediate", "Deadlock mediation"), ("act_third_option", "Third option"),
             ("act_devils_advocate", "Devil's advocate"), ("note_moved", "\"You moved\" note in prompt"), ("note_defend", "\"Defend your grounds\" note"),
             ("note_switched", "\"Position has shifted\" note"), ("note_reciprocity", "Reciprocity note"), ("move_switch", "Threshold switch events (state model)"),
             ("move_concession", "Concession moves (state model)")]
    n6 = _load(res / model / "n6_instructed.json")
    fig, axes = plt.subplots(1, 2, figsize=(7.5, 3.4), sharey=True, gridspec_kw={"wspace": 0.12})
    y = np.arange(len(items))[::-1]
    for ax, (study, title) in zip(axes, (("wason", "1-A Wason (2–6 agents × 5 turns)"), ("a1r", "1-B policy items (5 agents × 5 turns)"))):
        for j, (mode, color) in enumerate((("baseline", COLORS["A-baseline"]), ("stateful", COLORS["A-stateful"]))):
            k = f"{study}/{mode}"
            vals = [n6[k][c]["estimate"] for c, _ in items]
            los = [n6[k][c]["ci"][0] for c, _ in items]
            his = [n6[k][c]["ci"][1] for c, _ in items]
            yy = y + (0.18 if mode == "baseline" else -0.18)
            ax.barh(yy, vals, 0.34, color=color, edgecolor="white", linewidth=0.5, label=f"{mode.capitalize()} engine")
            ax.errorbar(vals, yy, xerr=[np.array(vals) - np.array(los), np.array(his) - np.array(vals)], fmt="none", ecolor=INK, elinewidth=0.6, capsize=1)
            for v, yv in zip(vals, yy):
                ax.text(v + 0.15, yv, f"{v:.1f}", va="center", fontsize=5.8, color=INK2)
        ax.set_title(title, loc="left", fontsize=8.5)
        ax.set_xlabel("Count per run")
        ax.xaxis.grid(True)
        ax.set_axisbelow(True)
        ax.set_xlim(0, max(n6[f"{study}/stateful"][c]["ci"][1] for c, _ in items) * 1.25)
    axes[0].set_yticks(y)
    axes[0].set_yticklabels([n for _, n in items], fontsize=6.8)
    axes[1].legend(frameon=False, fontsize=7, loc="upper right")
    fig.suptitle(f"{MODELS[model]}: what the engine instructed (device layer ①)", x=0.0, ha="left", fontsize=9.5, y=1.0)
    _note(fig, "Speech acts are the engine-assigned `action`; notes are strings inserted into the agent's prompt; switch and concession moves are events in the engine's "
          "stance model. In the baseline engine the state model still runs but no directive is shown, so its moves are measurement artefacts, not instructions. "
          "Whiskers = 95% bootstrap interval over blocks.", y=-0.08)
    return _save(fig, out, "fig_devices")


def fig_engine_vs_survey(res: Path, out: Path, model: str) -> List[Path]:
    """N7: (A) 엔진 최종 입장값 대 사후 설문, 모드별 (B) 문턱 전환 전후 텍스트 입장: 전환자 대 같은 실행의 다른 참가자"""
    t = pd.read_csv(res / model / "n7_participants.csv")
    sw = pd.read_csv(res / model / "n7_switch_events.csv")
    n7 = _load(res / model / "n7.json")
    fig, axes = plt.subplots(1, 3, figsize=(7.5, 2.6), gridspec_kw={"wspace": 0.45, "width_ratios": [1, 1, 1.1]})
    rng = np.random.default_rng(0)
    for ax, mode, lab in zip(axes[:2], ("baseline", "stateful"), ("A-baseline", "A-stateful")):
        g = t[t["mode"] == mode]
        ax.scatter(g["x_final"] + rng.uniform(-0.02, 0.02, len(g)), g["post_x"] + rng.uniform(-0.03, 0.03, len(g)), s=4, alpha=0.2, color=COLORS[lab], linewidths=0)
        ax.plot([-1, 1], [-1, 1], color=INK2, linewidth=0.6, linestyle=":")
        p = n7["participants"][mode]
        ax.text(0.03, 0.97, f"r = {p['corr_xfinal_post']['estimate']:.2f}\nmean |x − survey| = {p['mean_abs_xfinal_minus_post']['estimate']:.2f}",
                transform=ax.transAxes, va="top", fontsize=6.5)
        ax.set_title(f"{LABELS[lab]}", loc="left", fontsize=8.5)
        ax.set_xlabel("Engine stance x after last turn")
        ax.set_xlim(-1.05, 1.05)
        ax.set_ylim(-1.05, 1.05)
        ax.xaxis.grid(True)
        ax.yaxis.grid(True)
        ax.set_axisbelow(True)
    axes[0].set_ylabel("Post-session survey, rescaled to [−1, 1]")
    ax = axes[2]
    if len(sw):
        s = n7["switch_events"]
        vals = [s["text_delta_signed"]["estimate"], s["others_text_delta_signed"]["estimate"]]
        cis = [s["text_delta_signed"]["ci"], s["others_text_delta_signed"]["ci"]]
        ax.bar([0, 1], vals, 0.55, color=[COLORS["A-stateful"], HUMAN], edgecolor="white")
        for i, (v, ci) in enumerate(zip(vals, cis)):
            ax.errorbar(i, v, yerr=_err(v, ci), fmt="none", ecolor=INK, elinewidth=0.8, capsize=2)
            ax.text(i, ci[1] + 0.02, f"{v:.2f}", ha="center", va="bottom", fontsize=6.5, color=INK2)
        ax.set_xticks([0, 1])
        ax.set_xticklabels(["Switched agent", "Other agents,\nsame window"], fontsize=7)
        ax.axhline(0, color=INK2, linewidth=0.6)
        ax.set_ylabel("Text-stance change in the switch direction")
        ax.set_title(f"Threshold switches (n = {s['n_events']})", loc="left", fontsize=8.5)
        ax.set_ylim(0, max(cis[0][1], 0.1) * 1.7)
        ax.text(0.98, 0.97, f"moved ≥ 0.2 in the switch direction: {s['share_text_moved_same_direction_ge_0.2']['estimate']:.0%}\nmoved opposite: {s['share_text_moved_opposite']['estimate']:.0%}",
                transform=ax.transAxes, va="top", ha="right", fontsize=6.3)
        ax.yaxis.grid(True)
        ax.set_axisbelow(True)
    fig.suptitle(f"{MODELS[model]}, 1-B: does the engine's stance model match what agents then say and report?", x=0.0, ha="left", fontsize=9.5, y=1.06)
    _note(fig, "A–B: one point per agent × run (2,080 each). Survey score mapped as (score − 5)/5. C: text stance = the analyzer's reading of the agent's own utterance "
          "(same analyzer that feeds the engine, so this is consistency, not an independent check); change = first own utterance after the switch minus the last before it, "
          "signed by the switch direction. Whiskers = 95% bootstrap interval over blocks.", y=-0.12)
    return _save(fig, out, f"fig_engine_vs_survey_{model}")


def fig_minority(res: Path, out: Path, models: List[str]) -> List[Path]:
    """S3: 집단에서 먼 구성원일수록 상대 쪽으로 얼마나 움직이는가 (평균 이동, 상대 쪽 이동 비율), 인간 소집단 대 AI 조건"""
    bins = ["0-1", "1-3", "3-5", "5-11"]
    fig, axes = plt.subplots(1, 2, figsize=(7.5, 2.7), gridspec_kw={"wspace": 0.3})
    labs = [("A-baseline", "o"), ("A-stateful", "^"), ("C-reanswer", "s")]
    for ax, metric, ylabel in zip(axes, ("toward", "share_toward"), ("Mean movement toward the others (points)", "Share moving toward the others")):
        s3 = _load(res / models[0] / "s3.json")
        h = s3["human"]["delib_small_group"]
        ax.errorbar(range(4), [h[f"{metric}_{b}"]["estimate"] for b in bins],
                    yerr=[[h[f"{metric}_{b}"]["estimate"] - h[f"{metric}_{b}"]["ci"][0] for b in bins], [h[f"{metric}_{b}"]["ci"][1] - h[f"{metric}_{b}"]["estimate"] for b in bins]],
                    fmt="s-", color=HUMAN, markersize=4.5, linewidth=1.6, capsize=2, label="Human small groups (A1R)")
        for lab, mk in labs:
            a = s3["ai"][lab]
            ax.errorbar(np.arange(4) + {"A-baseline": -0.08, "A-stateful": 0.08, "C-reanswer": 0.16}[lab], [a[f"{metric}_{b}"]["estimate"] for b in bins],
                        yerr=[[a[f"{metric}_{b}"]["estimate"] - a[f"{metric}_{b}"]["ci"][0] for b in bins], [a[f"{metric}_{b}"]["ci"][1] - a[f"{metric}_{b}"]["estimate"] for b in bins]],
                        fmt=mk + "-", color=COLORS[lab], markersize=4, linewidth=1.2, capsize=2, label=f"{SHORT[models[0]]}, {LABELS[lab]}")
        ax.set_xticks(range(4))
        ax.set_xticklabels(["0–1", "1–3", "3–5", "5+"])
        ax.set_ylabel(ylabel, fontsize=7.5)
        ax.yaxis.grid(True)
        ax.set_axisbelow(True)
        if metric == "share_toward":
            ax.axhline(0.5, color=INK2, linewidth=0.6, linestyle=":")
    axes[0].legend(frameon=False, fontsize=6.5, loc="upper left")
    fig.supxlabel("Distance of own prior from the others' mean (0–10 scale)", fontsize=8.5, y=-0.02)
    _note(fig, f"Movement toward = (post − pre) × sign(others' pre-mean − own pre). Humans: real small groups (~13 members) per item, resampled by group; AI: 5-agent blocks, "
          f"resampled by block. Only {MODELS[models[0]]} shown; other models in the tables.", y=-0.14)
    return _save(fig, out, "fig_minority")


def fig_spread_trajectory(res: Path, out: Path, model: str) -> List[Path]:
    """S5 보조: 1-B 실행 안에서 입장값 분산(표준편차)의 궤적, 정규화 시점별 평균, 모드별"""
    utt = pd.read_csv(res / model / "utterances.csv", low_memory=False, usecols=["discussion_id", "study", "mode", "topic_key", "seq", "speaker_type", "spread", "stances"])
    utt = utt[(utt["speaker_type"] != "moderator") & (utt["study"] == "a1r") & ~utt["topic_key"].str.contains("debranded")]
    fig, ax = plt.subplots(figsize=(4.2, 2.6))
    for mode, lab in (("baseline", "A-baseline"), ("stateful", "A-stateful")):
        g = utt[utt["mode"] == mode].sort_values(["discussion_id", "seq"]).copy()
        g["t"] = g.groupby("discussion_id").cumcount() / (g.groupby("discussion_id")["seq"].transform("count") - 1)
        g["bin"] = (g["t"] * 10).round() / 10
        m = g.groupby("bin")["spread"].agg(["mean", "sem"])
        ax.plot(m.index, m["mean"], color=COLORS[lab], linewidth=1.6, label=LABELS[lab])
        ax.fill_between(m.index, m["mean"] - 1.96 * m["sem"], m["mean"] + 1.96 * m["sem"], color=COLORS[lab], alpha=0.15, linewidth=0)
    ax.axhline(0.3, color=INK2, linewidth=0.6, linestyle=":")
    ax.text(0.01, 0.31, "premature-consensus threshold (0.3)", fontsize=6, color=INK2, va="bottom")
    ax.set_xlabel("Position in the discussion (0 = first turn, 1 = last)")
    ax.set_ylabel("SD of engine stance values x across agents")
    ax.set_title(f"{MODELS[model]}, 1-B: how fast do positions converge?", loc="left", fontsize=8.5)
    ax.legend(frameon=False, fontsize=6.8)
    ax.yaxis.grid(True)
    ax.set_axisbelow(True)
    _note(fig, "Mean ± 1.96 SEM across runs at each tenth of the discussion. x is the engine's stance value; in the baseline engine it is computed but never shown to agents.", y=-0.12)
    return _save(fig, out, f"fig_spread_trajectory_{model}")


# ---------------- C단계 그림 ----------------

PATTERN_LABELS = [("P+Q", "vowel + even\n(confirm)"), ("P", "vowel only"), ("P+Q+notQ", "vowel + both\nnumbers"), ("P+notP+Q+notQ", "all four"),
                  ("P+notP", "both letters"), ("P+notP+notQ", "both letters\n+ odd"), ("notP+notQ", "consonant\n+ odd")]


def fig_wrong_types(res: Path, out: Path, model: str) -> List[Path]:
    """E1: 과반 오답으로 모인 집단의 답 유형 분포, 사람 대 AI 기준선·상태 기반"""
    e = _load(res / model / "e1e3.json")["E1"]
    fig, ax = plt.subplots(figsize=(7.5, 2.8))
    x = np.arange(len(PATTERN_LABELS))
    width = 0.26
    for j, (arm, color, name) in enumerate((("human", HUMAN, "Human (DeliData)"), ("A-baseline", COLORS["A-baseline"], f"{SHORT[model]}, baseline engine"),
                                            ("A-stateful", COLORS["A-stateful"], f"{SHORT[model]}, stateful engine"))):
        v = e[arm]
        vals = [v.get(f"share_{p}", {"estimate": 0})["estimate"] for p, _ in PATTERN_LABELS]
        los = [v.get(f"share_{p}", {"ci": [0, 0]})["ci"][0] for p, _ in PATTERN_LABELS]
        his = [v.get(f"share_{p}", {"ci": [0, 0]})["ci"][1] for p, _ in PATTERN_LABELS]
        xx = x + (j - 1) * width
        ax.bar(xx, vals, width, color=color, edgecolor="white", label=f"{name} (n = {v['n_wrong_majority_groups']})")
        ax.errorbar(xx, vals, yerr=[np.array(vals) - np.array(los), np.array(his) - np.array(vals)], fmt="none", ecolor=INK, elinewidth=0.7, capsize=1.5)
    ax.set_xticks(x)
    ax.set_xticklabels([n for _, n in PATTERN_LABELS], fontsize=6.8)
    ax.set_ylabel("Share of wrong-majority groups")
    ax.set_title("Which wrong answer do groups agree on? (correct = vowel + odd)", loc="left", fontsize=9)
    ax.legend(frameon=False, fontsize=6.8)
    ax.yaxis.grid(True)
    ax.set_axisbelow(True)
    _note(fig, "Groups whose majority final answer is wrong, by the logical role of the chosen cards (P = vowel, Q = even, not-Q = odd, not-P = consonant). "
          "Whiskers = 95% bootstrap interval over groups. AI baseline uses the first replicate.", y=-0.12)
    return _save(fig, out, f"fig_wrong_types_{model}")


def fig_change_timing(res: Path, out: Path, model: str) -> List[Path]:
    """N9: (A) 답 변경이 토론의 어느 시점에 일어나는가 (B) 변경의 방향 (C) 초기 정답자의 유지·초기 오답자의 전환"""
    n9 = _load(res / model / "n9.json")
    arms = (("human", HUMAN, "Human (DeliData)", "s"), ("A-baseline", COLORS["A-baseline"], f"{SHORT[model]}, baseline engine", "o"),
            ("A-stateful", COLORS["A-stateful"], f"{SHORT[model]}, stateful engine", "^"))
    fig, axes = plt.subplots(1, 3, figsize=(7.5, 2.7), gridspec_kw={"wspace": 0.4, "width_ratios": [1.1, 1, 1]})
    ax = axes[0]
    bins = [("0.00-0.25", "1st\nquarter"), ("0.25-0.50", "2nd"), ("0.50-0.75", "3rd"), ("0.75-1.01", "4th")]
    for arm, color, name, mk in arms:
        s = n9["human"] if arm == "human" else n9["ai"][arm]
        vals = [s[f"share_t_{b}"]["estimate"] for b, _ in bins]
        los = [s[f"share_t_{b}"]["ci"][0] for b, _ in bins]
        his = [s[f"share_t_{b}"]["ci"][1] for b, _ in bins]
        ax.errorbar(range(4), vals, yerr=[np.array(vals) - np.array(los), np.array(his) - np.array(vals)], fmt=mk + "-", color=color, markersize=4, linewidth=1.3, capsize=2, label=name)
    ax.set_xticks(range(4))
    ax.set_xticklabels([n for _, n in bins], fontsize=7)
    ax.set_ylabel("Share of answer changes")
    ax.set_title("A  When do answers change?", loc="left", fontsize=8.5)
    ax.legend(frameon=False, fontsize=6.2, loc="upper right")
    ax.yaxis.grid(True)
    ax.set_axisbelow(True)
    ax = axes[1]
    kinds = [("wrong_to_correct", "wrong →\ncorrect"), ("correct_to_wrong", "correct →\nwrong"), ("wrong_to_wrong", "wrong →\nother wrong")]
    width = 0.26
    for j, (arm, color, name, mk) in enumerate(arms):
        s = n9["human"] if arm == "human" else n9["ai"][arm]
        vals = [s[f"share_{k}"]["estimate"] for k, _ in kinds]
        los = [s[f"share_{k}"]["ci"][0] for k, _ in kinds]
        his = [s[f"share_{k}"]["ci"][1] for k, _ in kinds]
        xx = np.arange(3) + (j - 1) * width
        ax.bar(xx, vals, width, color=color, edgecolor="white")
        ax.errorbar(xx, vals, yerr=[np.array(vals) - np.array(los), np.array(his) - np.array(vals)], fmt="none", ecolor=INK, elinewidth=0.7, capsize=1.5)
    ax.set_xticks(range(3))
    ax.set_xticklabels([n for _, n in kinds], fontsize=7)
    ax.set_ylabel("Share of answer changes")
    ax.set_title("B  Direction of changes", loc="left", fontsize=8.5)
    ax.yaxis.grid(True)
    ax.set_axisbelow(True)
    ax = axes[2]
    keys = [("all_initially_correct_stay_correct", "started correct,\nended correct"), ("all_initially_wrong_end_correct", "started wrong,\nended correct")]
    for j, (arm, color, name, mk) in enumerate(arms):
        r = n9["human_retention"] if arm == "human" else n9["ai_retention"][arm]
        vals = [r[k]["estimate"] for k, _ in keys]
        los = [r[k]["ci"][0] for k, _ in keys]
        his = [r[k]["ci"][1] for k, _ in keys]
        xx = np.arange(2) + (j - 1) * width
        ax.bar(xx, vals, width, color=color, edgecolor="white")
        ax.errorbar(xx, vals, yerr=[np.array(vals) - np.array(los), np.array(his) - np.array(vals)], fmt="none", ecolor=INK, elinewidth=0.7, capsize=1.5)
    ax.set_xticks(range(2))
    ax.set_xticklabels([n for _, n in keys], fontsize=6.6)
    ax.set_ylabel("Share of participants")
    ax.set_ylim(0, 1.05)
    ax.set_title("C  Who ends up correct?", loc="left", fontsize=8.5)
    ax.yaxis.grid(True)
    ax.set_axisbelow(True)
    q = n9["extraction_quality"]
    _note(fig, f"A–B: answer-change events (humans: DeliData answer tracker after each message; AI: card selection extracted from each utterance by an LLM, "
          f"source = {q.get('source')}; last-utterance extraction matched the final survey in "
          + ", ".join(f"{k} {v['share']:.0%}" for k, v in q.get("last_extraction_matches_survey", {}).items()) +
          "). Time = position of the message among the group's messages (0 = first, 1 = last). C: final survey (AI) or final submission (humans). "
          "Whiskers = 95% bootstrap interval over groups.", y=-0.12)
    return _save(fig, out, f"fig_change_timing_{model}")


def fig_composition(res: Path, out: Path, model: str = "claude") -> List[Path]:
    """N10: 발언 유형 구성비 (DeliData 체계), 사람 대 기준선 대 상태 기반, 표본(비교용·설명용 층)별 가로 누적 막대"""
    n10 = _load(res / model / "n10.json")
    targets = n10["targets"]
    tcol = {"solution": "#2a4d8f", "reasoning": "#6f9ae0", "agree": "#199e70", "disagree": "#c0392b", "moderation": "#c98500", "none": "#bdbbb5"}
    samples = [("comparison", "Comparison sample\n(k × group size strata)"), ("stateful_only_failure", "Explanatory: stateful-only\nfailure groups"),
               ("human_wrong_k0_ai_correct", "Explanatory: humans wrong,\nno initial solver, AI correct")]
    samples = [s for s in samples if s[0] in n10["by_sample"]]
    fig, axes = plt.subplots(len(samples), 1, figsize=(7.5, 1.05 * len(samples) + 1.2), sharex=True, gridspec_kw={"hspace": 0.5})
    axes = np.atleast_1d(axes)
    for ax, (key, title) in zip(axes, samples):
        v = n10["by_sample"][key]
        rows = [("Human (DeliData annotation)", v["human_same_groups"], HUMAN), ("Baseline engine", v["conditions"].get("A-baseline"), COLORS["A-baseline"]),
                ("Stateful engine", v["conditions"].get("A-stateful"), COLORS["A-stateful"])]
        rows = [r for r in rows if r[1]]
        for i, (name, c, edge) in enumerate(rows):
            left = 0.0
            for t in targets:
                w = c[t]["estimate"]
                ax.barh(i, w, left=left, color=tcol[t], edgecolor="white", linewidth=0.5, height=0.65)
                if w >= 0.08:
                    ax.text(left + w / 2, i, f"{w:.0%}", ha="center", va="center", fontsize=6.5, color="white" if t in ("solution", "disagree", "reasoning") else INK)
                left += w
            ax.text(-0.01, i, name, ha="right", va="center", fontsize=7.5, color=edge)
        ax.set_yticks([])
        ax.set_ylim(-0.6, len(rows) - 0.4)
        ax.set_xlim(0, 1)
        ax.set_title(f"{title}  (n = {v['human_same_groups']['n_groups']} groups)", loc="left", fontsize=8)
        ax.spines["left"].set_visible(False)
        ax.text(1.0, len(rows) - 0.45, f"probing: human {v['human_same_groups']['probing']['estimate']:.0%}, "
                + ", ".join(f"{LABELS[l].split()[0].lower()} {v['conditions'][l]['probing']['estimate']:.0%}" for l in ("A-baseline", "A-stateful") if l in v["conditions"]),
                ha="right", va="bottom", fontsize=6.5, color=INK2)
    axes[-1].set_xlabel("Share of utterances by main target (group mean)")
    handles = [Patch(facecolor=tcol[t], label=t) for t in targets]
    axes[0].legend(handles=handles, ncol=6, loc="lower left", bbox_to_anchor=(0.0, 1.75), frameon=False, handlelength=1.0, columnspacing=1.0)
    _note(fig, "Humans: DeliData human annotations of the same groups. AI: GLM 5.3 coding of Claude utterances (validated against DeliData annotations; "
          "solution and reasoning are reported merged for inference because each alone missed the recall criterion). Whiskers omitted; 95% intervals are in the tables.", y=-0.04)
    return _save(fig, out, f"fig_composition_{model}")


def fig_device_observed(res: Path, out: Path, model: str = "claude") -> List[Path]:
    """N6 ②: 장치 발언 대 대조(기준선) 발언에서 장치가 요구한 행동이 텍스트에 나타난 비율 (1차 코더; 제2 코더는 점으로)"""
    n6 = _load(res / model / "n6b.json")
    coders = list(n6["coders"])
    devices = [("respond_challenge", "addresses_specific_claim", "Respond to challenge\nobserved: addresses\nthe specific claim"),
               ("mediate", "names_disagreement_between_others", "Mediate / third option\nobserved: names where\ntwo others disagree"),
               ("devils_advocate", "objects_to_shared_view", "Devil's advocate\nobserved: objects to\nthe shared view"),
               ("switched", "states_position_change", "Switch notice\nobserved: states own\nposition change")]
    fig, ax = plt.subplots(figsize=(7.5, 3.0))
    x = np.arange(len(devices))
    w = 0.36
    first = n6["coders"][coders[0]]["by_device"]
    for j, (dev, item, _) in enumerate(devices):
        for k, (grp, color, lab) in enumerate((("control", HUMAN, "Baseline utterances (no instruction)"), (dev, COLORS["A-stateful"], "Stateful utterances given the instruction"))):
            d = first.get(grp)
            if not d:
                continue
            yes, part = d["items"][item]["yes"], d["items"][item]["partial"]
            ax.bar(x[j] + (k - 0.5) * w, yes, w, color=color, label=lab if j == 0 else None)
            ax.bar(x[j] + (k - 0.5) * w, part, w, bottom=yes, color=color, alpha=0.35, label=("partial (lighter)" if j == 0 and k == 1 else None))
            if len(coders) > 1 and grp in n6["coders"][coders[1]]["by_device"]:
                y2 = n6["coders"][coders[1]]["by_device"][grp]["items"][item]["yes"]
                ax.plot(x[j] + (k - 0.5) * w, y2, marker="D", color=INK, markersize=3.5, linestyle="none", label="second coder (yes)" if j == 0 and k == 1 else None)
    ax.set_xticks(x)
    ax.set_xticklabels([d[2] for d in devices], fontsize=7.5)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Share of utterances showing the behaviour")
    ax.grid(axis="y")
    ax.legend(loc="upper left", bbox_to_anchor=(0.0, 1.18), ncol=2, frameon=False)
    _note(fig, "Each device: 300 stateful-engine utterances (Claude) that received the instruction, vs 300 baseline-engine utterances that received none, judged on the same observable item "
          "by Mistral Large 3 (bars; lighter = partial) and Mistral Small 4 (diamonds = yes). Coders see the utterance, three previous utterances and, for device utterances, the instruction; "
          "they are told to judge only what the utterance's text does.", y=-0.22)
    return _save(fig, out, f"fig_device_observed_{model}")


def fig_network_solver(res: Path, out: Path, model: str = "claude") -> List[Path]:
    """S8: k=1 집단에서 처음 정답자가 발언당 받은 지지·반박·양보 대 다른 구성원 (분석기 targets), 엔진별"""
    s8 = _load(res / model / "s8.json")["network"]
    kinds = [("recv_support_per_utt", "support\nreceived"), ("recv_attack_per_utt", "attack\nreceived"), ("recv_concede_per_utt", "concession\nreceived"),
             ("sent_attack_per_utt", "attack\nsent")]
    fig, axes = plt.subplots(1, 2, figsize=(7.5, 2.8), sharey=True, gridspec_kw={"wspace": 0.12})
    for ax, lab in zip(axes, ("A-baseline", "A-stateful")):
        v = s8["by_label"][lab]
        x = np.arange(len(kinds))
        for k, (who, color, name) in enumerate((("solver", COLORS[lab], "initial solver"), ("others", HUMAN, "other members"))):
            est = [v[who][c]["estimate"] for c, _ in kinds]
            err = np.array([[v[who][c]["estimate"] - v[who][c]["ci"][0] for c, _ in kinds], [v[who][c]["ci"][1] - v[who][c]["estimate"] for c, _ in kinds]])
            ax.bar(x + (k - 0.5) * 0.36, est, 0.36, color=color, yerr=err, error_kw={"elinewidth": 0.7, "capsize": 2}, label=name)
        ax.set_xticks(x)
        ax.set_xticklabels([n for _, n in kinds], fontsize=7.5)
        ax.set_title(f"{LABELS[lab]} ({v['n_runs']} runs)", loc="left")
        ax.grid(axis="y")
        ax.legend(frameon=False, loc="upper right")
    axes[0].set_ylabel("Analyzer-recorded links per utterance")
    _note(fig, f"Claude, Wason groups with exactly one initially correct member (k = 1; {s8['n_groups']} groups). Links come from the engine's analyzer (meta.analysis targets), "
          "which agreed only moderately with independent coders (κ 0.40 for attacks, 0.25 for concessions). Whiskers = 95% bootstrap interval over groups.", y=-0.12)
    return _save(fig, out, f"fig_network_solver_{model}")
