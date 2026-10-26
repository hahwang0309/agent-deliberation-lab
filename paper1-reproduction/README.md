# Paper 1 — curated reproducibility package (v2)

This package reproduces selected numerical analyses and all six main figures without model API calls. It is separate from the general Agent Deliberation Lab web platform. The older `paper1-reproduction-2026-10-26` release remains available unchanged.

## 1. Environment

Use Python 3.12 and R with `lme4`, `lmerTest`, and `jsonlite`. The tested versions are in `environment.json`; exact Python dependencies are in the complete lock.

```sh
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-analysis.complete.lock.txt
Rscript -e 'install.packages(c("lme4", "lmerTest", "jsonlite"), repos="https://cloud.r-project.org")'
```

R must be on PATH. The R command installs available packages, rather than restoring exact historical R versions. Use the recorded versions when comparing at the strict tolerance below.

## 2. Public inputs

The fixed dataset is [haha0309/agent-deliberation-study1 at c13fd45](https://huggingface.co/datasets/haha0309/agent-deliberation-study1/tree/c13fd45abfafc9f0bcc5b8157d8ea73038138ae8). No login, database or API key is required.

```sh
python analysis/scripts/prepare_public_inputs.py --download data-public
```

This downloads the files listed in that revision's manifest, checks their SHA-256 hashes, and stages only `data/` and `docs/` figure inputs into `analysis/`. It never copies the dataset's archived scripts over this package. To use an existing exact dataset snapshot instead:

```sh
python analysis/scripts/prepare_public_inputs.py --data /absolute/path/to/dataset
```

The commands below assume `data-public/`; substitute your existing dataset path when using `--data`.

## 3. Refit the numerical contrasts

```sh
python analysis/scripts/reanalyze_public_numeric.py --source-data data-public/numeric --out output/refits
```

Expected: 15 E1–E5 contrasts across three models. `output/refits/verification.json` reports estimate and confidence-interval differences below 1e-6 against the archived records. These are 15 of the 42 registered result rows, not a full refit of every paper analysis.

## 4. Regenerate figures

```sh
python analysis/scripts/build_manuscript_figures.py
```

Expected: `analysis/docs/research/manuscript-figures/figure1` through `figure6`, each as PNG and PDF, plus source-data and input hashes. This renders archived estimates; it does not rerun all fits behind those estimates. `MethodsDraft.md` in the staged inputs is a provenance placeholder, not manuscript prose.

## 5. Audit the released coding merge

```sh
python analysis/scripts/audit_public_coding.py --data data-public --out output/coding-audit.json
```

Expected: 2,440 utterances, 1,500 rule-performance records and 600 post-discussion explanations. The script checks that complete coder agreements were retained and disagreements used the recorded judge labels, then compares all condition-specific label counts with the archived summaries. This does not validate a label against a human gold standard.

## Source, optional tools, and rights

- `analysis/`: minimal runnable code for the commands above.
- `experiment/`: unchanged original experimental source archive and its provenance.
- `optional-coding-reference/`: initial and later paid coding implementations, for inspection/adaptation only. These require author-side paths to be replaced and are not part of the offline quick start.
- `CURATION.md`: inclusions, exclusions, and verification boundaries.
- `manifest.json`: hashes of packaged files; `verification/v2-check.json`: actual package test results.

The code uses the Ha Hwang Research Use License 1.0 in `LICENSE` (noncommercial research/education/reproduction; not an OSI open-source license). It grants no patent license. A patent application concerning the stateful discussion algorithm is being prepared; it is not described as already filed. Third-party material retains its own terms; see `THIRD_PARTY.md` and the dataset's notices. No new model calls or charges occur in the offline commands above.
