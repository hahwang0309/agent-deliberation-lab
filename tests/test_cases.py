"""연구용 사례 생성 (src/cases, scripts/build_cases.py) - 원자료 대신 작은 합성 자료로 검사"""
import asyncio
import json
import random
from collections import Counter

import pytest

from api.runtime import persistence
from api.runtime import runtime as runtime_module
from api.services.experiment_runner import ExperimentPlan, build_request, existing_runs, plan_runs, run_batch
from scripts.build_cases import plan_dict, validate
from src.cases import a1r, argq, briefing, wason
from tests.test_runtime import FakeBundle

TSV_HEADER = "group_id\tmessage_id\tmessage_type\torigin\toriginal_text\tclean_text\tannotation_type\t" \
             "annotation_target\tannotation_additional\tteam_performance\tperformance_change\tsol_tracker_message\tsol_tracker_all"


def _tsv(path, gid, cards, solo, final):
    lines = [TSV_HEADER, "\t".join([gid, "-1", "INITIAL", "SYSTEM", ",".join(solo) + "&&" + ",".join(cards)]
                                   + [""] * 7 + [json.dumps(solo)])]
    for name, sel in final.items():
        lines.append("\t".join([gid, "m", "SUBMIT", name, ",".join(sel)] + [""] * 8))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.fixture
def delidata(tmp_path):
    _tsv(tmp_path / "g1.tsv", "aaaaaaaa-1", ["2", "7", "V", "A"],
         {"Cat": ["A", "2"], "Kiwi": ["A"], "Dog": ["A", "7"]}, {"Cat": ["A", "7"], "Kiwi": ["A", "7"], "Dog": ["A", "7"]})
    _tsv(tmp_path / "g2.tsv", "bbbbbbbb-2", ["4", "3", "E", "K"],
         {"Owl": ["N", "/", "A"], "Fox": ["E"], "Elk": ["E", "4"]}, {"Owl": ["E"], "Fox": ["E"], "Elk": ["E", "3"]})
    _tsv(tmp_path / "g3.tsv", "cccccccc-3", ["4", "3", "E", "K"], {"Bee": ["E"], "Ant": ["E"]}, {"Bee": ["E"], "Ant": ["E"]})
    return tmp_path


def test_wason_replicas_seed_human_solo_answers_and_drop_na(delidata):
    groups = wason.load_delidata(str(delidata))
    assert {g.group_id: g.solo.get("Owl", "x") for g in groups}["bbbbbbbb-2"] is None  # N/A 기록은 무효
    topics, excluded = wason.replica_topics(groups)
    assert len(topics) == 1 and excluded == {"a member has no valid solo answer (e.g. N/A)": 1}
    t = topics[0]
    item = t["survey"]["items"][0]
    assert item["options"] == ["2", "7", "V", "A"] and item["correct"] == ["7", "A"]
    assert t["seeds"] == {"Cat": {"cards": ["2", "A"]}, "Kiwi": {"cards": ["A"]}, "Dog": {"cards": ["7", "A"]}}
    assert "2, 7, V, A" in t["description"] and t["meta"]["human_final"]["Cat"] == ["A", "7"]
    assert not validate(plan_dict("w", topics, wason.CONDITIONS))


def test_wason_variants_keep_structure_and_are_reproducible(delidata):
    dist = wason.solo_role_distribution(wason.load_delidata(str(delidata)))
    assert dist[("P",)] == 4 and dist[("P", "Q")] == 2 and sum(dist.values()) == 7  # Owl(N/A) 제외
    a = wason.variant_topics(5, dist, seed=3)
    assert a == wason.variant_topics(5, dist, seed=3)
    for t in a:
        roles = t["meta"]["roles"]
        item = t["survey"]["items"][0]
        assert sorted(item["options"]) == sorted(roles.values())
        assert set(item["correct"]) == {roles["P"], roles["notQ"]}
        assert all(set(s["cards"]) <= set(item["options"]) and s["cards"] for s in t["seeds"].values())
    assert not validate(plan_dict("v", a, wason.CONDITIONS))


LAYOUT = """Taxing the Wealthy
 PROPOSALS                        ARGUMENTS FOR                                 ARGUMENTS AGAINST


 The US should impose a wealth    This tax would directly affect only           Measuring wealth can be complex
 tax on the richest taxpayers.    the very rich and would com-                  and costly.
                                  bat the deficit.




                                                                                                                                The Economy and Taxes
 The US should repeal the         People were already taxed when they           Repeal would reduce revenue and         15
 estate tax, which currently      earned the money.                             increase inequality.




                                                                                                                                AMERICA in ONE ROOM
 taxes large fortunes.            It is double taxation.
"""


def test_briefing_table_rows_survive_page_breaks_and_margins():
    rows = briefing.parse_tables(LAYOUT)
    assert [r["proposal"] for r in rows] == [
        "The US should impose a wealth tax on the richest taxpayers.",
        "The US should repeal the estate tax, which currently taxes large fortunes."]
    assert rows[0]["arguments_for"] == "This tax would directly affect only the very rich and would combat the deficit."
    assert rows[1]["arguments_against"] == "Repeal would reduce revenue and increase inequality."
    assert rows[1]["arguments_for"].endswith("It is double taxation.")
    matched = briefing.match_items(rows, {"Q4C": "The US should repeal the estate tax.", "Q4B": "Impose a wealth tax."})
    assert matched["Q4C"]["proposal"].startswith("The US should repeal") and 0 < matched["Q4C"]["match_score"] <= 1
    issue = "HEALTH CARE\nThe Issue\n\nMost people have insurance.\nSome want more.\nBelow are examples of policy proposals"
    assert briefing.parse_issues(issue, ["Health"]) == {"Health": "Most people have insurance. Some want more."}


def _a1r_files(tmp_path):
    codebook = tmp_path / "codebook.tab"
    codebook.write_text('variable\tlabel\tvalue\tvalue_label\n"Q5A"\t"[The Affordable Care Act should be repealed.] Rate"\t\t\n'
                        '"Q3A"\t"[Commit to the Paris Agreement.] Rate"\t\t\n', encoding="utf-8")
    cols = ["CONDITION", "POST", "GROUP", "PARTYID3", "GENDER", "AGE4", "RACETHNICITY", "EDUC4", "LIBCONV",
            "Q5A", "T2Q5A", "Q3A", "T2Q3A"]
    rng = random.Random(0)
    rows = []
    for i in range(30):
        party = "123"[i % 3]
        rows.append(["1", "1", str(1 + i % 2), party, "2", "3", "1", "4", "4",
                     str(rng.randint(0, 10)), str(rng.randint(0, 10)), "77" if i == 0 else "5", "6"])
    rows.append(["0", "1", "", "1", "1", "1", "1", "1", "1", "3", "3", "3", "3"])  # 통제집단
    dataset = tmp_path / "dataset.tab"
    dataset.write_text("\t".join(cols) + "\n" + "\n".join("\t".join(r) for r in rows) + "\n", encoding="utf-8")
    return str(codebook), str(dataset)


BRIEF = {"issues": {"Health": "Coverage background.", "Environment": "Climate background."},
         "items": {"Q5A": {"arguments_for": "The Affordable Care Act (ACA) raised costs.",
                           "arguments_against": "Obamacare expanded coverage."},
                   "Q3A": {"arguments_for": "Cuts emissions.", "arguments_against": "Costs jobs."}}}


def test_a1r_stratified_groups_personas_seeds_and_materials(tmp_path):
    codebook, dataset = _a1r_files(tmp_path)
    items = a1r.load_items(codebook)
    assert items == {"Q5A": "The Affordable Care Act should be repealed.", "Q3A": "Commit to the Paris Agreement."}
    delegates = a1r.load_delegates(dataset, list(items))
    assert len(delegates) == 30 and delegates[0].pre["Q3A"] is None  # 77(모름)은 점수 아님
    topics = a1r.sampled_topics(delegates, items, ["Q5A", "Q3A"], 3, seed=1, briefing=BRIEF)
    assert len(topics) == 6
    rows = {d.row: d for d in delegates}
    for t in topics:
        item = t["meta"]["item"]
        parties = Counter(a1r.PARTIES[rows[r].party] for r in t["meta"]["respondent_rows"].values())
        assert parties == Counter({"D": 2, "R": 2, "I": 1})
        assert all(rows[t["meta"]["respondent_rows"][n]].pre[item] == s[item] for n, s in t["seeds"].items())
        assert t["survey"] == {"scale": 10, "scale_min": 0, "items": [{"id": item, "text": f"Proposal: {items[item]}"}]}
    persona = topics[0]["personas"][0]["background"]
    assert persona.startswith("It is September 2019.") and "45-59 year old woman" in persona and "bachelor" in persona
    assert "Base your judgment only on the briefing materials" in topics[0]["materials"]
    assert topics == a1r.sampled_topics(delegates, items, ["Q5A", "Q3A"], 3, seed=1, briefing=BRIEF)
    assert not validate(plan_dict("a", topics, a1r.CONDITIONS))

    debranded = a1r.sampled_topics(delegates, items, ["Q5A"], 1, seed=1, briefing=BRIEF, debranded=True)[0]
    assert "Affordable" not in debranded["materials"] + debranded["description"]
    assert "Obamacare" not in debranded["materials"] and "ACA" not in debranded["materials"]

    groups = a1r.small_group_topics(delegates, items, ["Q5A"], seed=1)
    assert sorted(len(t["personas"]) for t in groups) == [15, 15] and "materials" not in groups[0]


def test_argq_matched_strong_weak_sets_and_support_scripts():
    rng = random.Random(0)
    rows = [{"argument": " ".join(["word"] * rng.randint(8, 14)) + f" {i}.", "topic": topic, "wa": rng.random(),
             "stance": stance} for topic in argq.texts()["argq"]["topics"] for stance in (1, -1) for i in range(40)]
    topics, conditions = argq.topics_and_conditions(rows, seed=2)
    assert len(topics) == 16 and [c["label"] for c in conditions] == [
        "strong-minority", "strong-majority", "weak-minority", "weak-majority"]
    t = topics[0]
    strong, weak = t["meta"]["arguments"]["strong"], t["meta"]["arguments"]["weak"]
    ts, tw = sum(a["tokens"] for a in strong), sum(a["tokens"] for a in weak)
    assert abs(ts - tw) <= 0.1 * min(ts, tw) and min(a["wa"] for a in strong) > max(a["wa"] for a in weak)
    majority = t["by_condition"]["strong-majority"]["participants"]
    minority = t["by_condition"]["strong-minority"]["participants"]
    assert [majority[n]["script"][0] for n in ("Riley", "Sam", "Tess")] == [a["argument"] for a in strong]
    assert minority["Riley"]["script"][0] == "\n".join(a["argument"] for a in strong)
    assert minority["Sam"]["script"] == minority["Tess"]["script"] == ["I'm with Jordan on this one. I support it."]
    assert t["seeds"] == {"Jordan": {"stance": 5}} and topics[1]["seeds"] == {"Jordan": {"stance": 3}}
    assert not validate(plan_dict("q", topics, conditions))


def test_plan_condition_repetitions_and_topic_overrides():
    plan = ExperimentPlan(**plan_dict("p", [{
        "key": "t", "topic": "Topic here", "personas": [{"name": "A", "role": "r"}, {"name": "B", "role": "r"}],
        "by_condition": {"x": {"participants": {"B": {"script": ["hi"]}}, "turn_order": ["B", "A"]}}}],
        [{"label": "x", "experiment": {"mode": "baseline", "participants": {"A": {"temperature": 0.2}}}, "repetitions": 2},
         {"label": "y", "experiment": {"mode": "baseline"}}]))
    runs = plan_runs(plan)
    assert Counter(r.condition.label for r in runs) == {"x": 2, "y": 1}
    x = build_request(plan, runs[0]).experiment
    assert x.participants["B"].script == ["hi"] and x.participants["A"].temperature == 0.2 and x.turn_order == ["B", "A"]
    assert x.report is False and build_request(plan, runs[1]).experiment.participants == {}
    with pytest.raises(Exception):
        ExperimentPlan(**plan_dict("p", [{"key": "t", "topic": "Topic here", "by_condition": {"zzz": {}},
                                          "personas": [{"name": "A", "role": "r"}, {"name": "B", "role": "r"}]}],
                                   [{"label": "x"}]))


@pytest.mark.asyncio
async def test_argq_case_runs_end_to_end_with_scripted_confederates(monkeypatch):
    monkeypatch.setattr(runtime_module, "LLMBundle", FakeBundle)
    rows = [{"argument": f"argument number {i} about this.", "topic": t, "wa": i / 40, "stance": s}
            for t in argq.texts()["argq"]["topics"] for s in (1, -1) for i in range(40)]
    topics, conditions = argq.topics_and_conditions(rows, seed=1)
    plan = ExperimentPlan(**plan_dict("argq-e2e", topics[:1], conditions))
    result = await run_batch(plan, on_progress=lambda _: None)
    assert len(result.completed) == 4 and not result.failed
    done = existing_runs("argq-e2e")
    did = done[("argq0-pro", "strong-minority", 0)]["id"]
    speakers = [m["speaker"] for m in persistence.list_messages_after(did) if m["speaker_type"] == "ai"]
    assert speakers == ["Jordan", "Riley", "Sam", "Tess", "Jordan"]
    assert {r["participant"] for r in persistence.list_survey(did)} == {"Jordan"}

