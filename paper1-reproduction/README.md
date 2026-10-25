# Paper 1 reproduction

The research-use license is in `LICENSE`. Original experiment and current
analysis code are separate snapshots: the experimental frozen commit is
`7a244351f3374b3e1ac4b02bf55a4f41ff9ca91c`.

The reproduction release contains `current/` source, `frozen-experiment.tar`,
`requirements-analysis.lock.txt`, environment and checksum records. It excludes
credentials, raw experiment databases, full upstream corpora and manuscript
drafts. Data are prepared separately for Hugging Face account `haha0309`.
Do not assume a planned dataset URL is accessible before a deposit is made.

## Numeric reanalysis without model APIs

Create a Python environment, install `requirements-analysis.lock.txt`, and make
R with `lme4` and `lmerTest` available on PATH. From `current/` run:

```sh
python scripts/reanalyze_public_numeric.py --source-data DATA/numeric --out output
```

This refits E1--E5 for all three participant models using published numerical
survey rows and inclusion flags, without the raw DBs or new model API calls.
The verification compares estimates and confidence intervals to archived
registered results at tolerance 1e-6. The local check passed all 15 contrasts.
It does not claim all 42 registered result rows and all exploratory models were
refit. The complete original pipeline remains in `scripts/analyze_study1.py`.

## Figure regeneration

Copy `DATA/numeric/plot-inputs/` into `current/`, preserving the directory tree,
then run `python scripts/build_manuscript_figures.py`. This recreates six figures
from preserved estimates, distinct from fitting statistical models.

## Coding checks

Original labels, source hashes, frozen rubrics and supplemental judgment routes
are preserved. `scripts/finalize_coding_adjudication.py` describes fresh initial
comparison coding and blinded GLM adjudication; network subcommands make paid
requests and must be invoked deliberately. They are not required for numeric
reanalysis or plotting. Human source annotations, automated coder agreement and
LLM adjudication are separate forms of evidence.

## Third-party material and limitations

Python/R dependencies retain their own licenses. DeliData is supplied upstream
under CC BY 4.0 and the A1R V1 dataset under CC0 1.0. The IBM argument dataset's
card has conflicting CC BY 3.0 and CC BY-SA 3.0 labels; obtain original arguments
from the provider and retain applicable notices. The code license does not
relicense datasets, model services or briefing materials.

Original API model versions may change or become unavailable. Reanalysing saved
outputs is distinct from recreating stochastic model responses. The author is
preparing a patent application concerning the stateful discussion algorithm;
it has not yet been filed. Contact: Ha Hwang, ghkdgk0309@gmail.com.
