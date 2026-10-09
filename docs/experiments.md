# 실험 실행 가이드

연구용 실험(AI 에이전트 간 토의, 조건 비교)을 실행하고 분석용 데이터를 뽑는 방법입니다. 웹 화면과 같은 엔진·저장 형식을 쓰지만, 실험은 **전용 DB**에서 배치로 실행합니다.

## 흐름

1. 실험 계획(YAML)을 작성합니다. 주제 × 조건 × 반복 수를 정합니다.
2. `--dry-run`으로 실행 건수와 예상 토큰을 확인합니다.
3. 배치를 실행합니다. 중단돼도 같은 명령으로 이어서 돌릴 수 있습니다.
   - 단계별 실행: `--until-fraction 0.05`처럼 주면 실행 순서의 앞에서부터 전체의 5%까지만 돌립니다. 더 큰 값으로 다시 실행하면 이어 갑니다(중간 점검용).
4. 데이터셋을 추출합니다. 필요하면 사람 코딩용 표본도 함께 뽑습니다.

```bash
python scripts/run_experiment.py config/experiments/example.yaml --db data/experiments.db --dry-run
```

```bash
python scripts/run_experiment.py config/experiments/example.yaml --db data/experiments.db
```

```bash
python scripts/export_dataset.py --db data/experiments.db --batch example-death-penalty --out data/example --coding-sample 50 --seed 1
```

API 키와 `SECRET_KEY`는 `.env`에서 읽습니다. `--db`는 필수이며, 웹 서버 DB(`discussion_api.db`)와 섞이지 않게 별도 파일을 씁니다. 파일이 없으면 만들고 마이그레이션을 적용합니다.

## 실험 계획 (YAML)

예시는 [config/experiments/example.yaml](../config/experiments/example.yaml)입니다. 알 수 없는 키는 오류로 처리되므로, 오타 때문에 조건이 조용히 무시되는 일은 없습니다.

| 키 | 의미 |
|---|---|
| `name` | 배치 이름. 이어 돌리기와 추출(`--batch`)의 기준입니다 |
| `repetitions` | 주제 × 조건마다 반복할 횟수 |
| `concurrency` | 동시 실행 수 (기본 2). 웹의 사용자·서버 제한과 무관합니다 |
| `retries` | 실패한 실행을 다시 시도할 횟수 (기본 1) |
| `report` | `false`면 모든 실행에서 종합보고서를 만들지 않습니다(조건의 `experiment.report`가 우선) |
| `limits.max_total_tokens` | 입력+출력 누적 토큰 상한. 다음 실행이 상한을 넘을 것 같으면 새 실행을 시작하지 않습니다 |
| `limits.max_cost_usd` + `prices` | 비용 상한. 단가(`input_per_mtok`, `output_per_mtok`)는 사용자가 확인한 값을 넣습니다. 코드에는 단가를 두지 않습니다 |
| `topics[]` | `key`, `topic`, `language`, `max_statements`, `use_moderator`, `personas`(dict 또는 `persona_templates.yaml`의 템플릿 id), `propositions`(고정 명제), `materials` 또는 `materials_file`(배경 자료, 계획 파일 기준 상대 경로), `survey`(사전·사후 설문), `seeds`(참가자 이름 → 심을 사전 응답 `{문항 id: 점수 또는 보기 목록}`) |
| `conditions[]` | `label`, `experiment`(실험 조건, 항목은 [configuration.md](configuration.md#실험-조건-토론별)), `use_seeds`(주제의 seeds를 심을지, 기본 true), `use_materials`(주제 자료를 넣을지, 기본 true), `repetitions`(이 조건만의 반복 수) |
| `topics[].by_condition` | 조건 label → 이 주제에서만 덧붙일 실험 조건 (예: 조건별 공모자 대본). `participants`는 이름별로 합칩니다 |
| `topics[].meta` | 분석용 메모 (원자료 식별자 등). 실행에는 쓰지 않습니다 |

**측정 프로토콜:** `config/cases.yaml`의 `protocol`(심은 리커트 응답을 말로 제시, 중립 사후 설문, 중립 초기 응답 문구)이 사례 생성기로 만든 모든 계획의 조건에 들어갑니다. 조건이 직접 값을 정하면 그 값이 우선입니다.

**집단 복제(블록):** 주제 1개가 집단 1개입니다. 같은 주제의 페르소나·초기 응답·자료가 모든 조건에 그대로 복제되므로, 조건 간 차이는 조건 설정에서만 생깁니다. 예: `discuss`(토론), `alone`(`mode: survey_only`, 초기 응답을 받은 채 혼자 다시 답함), `prior`(`survey_only` + `use_seeds: false`, 모델의 사전 답).

**실행 순서:** 반복 → 주제 → 조건 순으로 교차합니다. 시간에 따른 API 변화가 한 조건에 몰리지 않게 하기 위해서입니다.

**이어 돌리기:** 같은 배치에서 이미 `completed`인 (주제, 조건, 반복)은 건너뜁니다. 실패하거나 중단된 실행은 새 토론으로 다시 실행하고, 이전 기록은 감사용으로 남깁니다. 분석할 때는 `discussions` 표의 `status`로 걸러 내세요.

**토큰 추정:** 같은 배치에 완료된 실행이 있으면 그 평균을 씁니다. 없으면 발언 수 기반 대략치를 씁니다(Haiku 4.5 실측 기준 분석·설문·보고서를 포함해 발언 1개당 입력 약 10,700, 출력 약 1,530 토큰). 토론 없는 조건(`survey_only`)은 발언 1개 분량으로 잡습니다. 같은 배치의 완료 평균은 조건을 구분하지 않으므로, 토론 조건과 토론 없는 조건을 섞은 배치에서는 평균이 실제와 다를 수 있습니다. 참가자 수, 자료집 길이, 모델에 따라 크게 달라지므로 첫 배치는 작게 돌려 평균을 얻으세요.

## 실험 조건으로 바꿀 수 있는 것

| 범주 | 항목 |
|---|---|
| 엔진 | `mode`: `stateful`(상태 기반) / `baseline`(순서대로 앞 발언에 답하는 단순 토론) / `survey_only`(토론 없이 사전 설문 후 혼자 다시 답함) |
| 진행 장치 | 발언 분석, 응답 의무, 교착 중재, 반대 검토, 종결 라운드, 수용 범위, 양보 이동 (각각 on/off) |
| 동역학 | 설득 이동량, 고집 복원력, 수용·비관여·거부 범위, 반발, 양보 이동량 |
| 참가자 | 참가자별 고집도, temperature |
| 모델 | 참가자별 모델(페르소나의 `llm_provider`·`model`), 모더레이터 temperature, 발언 분석 모델 분리 |
| 기타 | 맥락 길이, 교착 기준, 성급한 합의 기준, 명제 수 상한, 발언별 프롬프트 기록 |

## 측정

| 측정 | 출처 | 표 |
|---|---|---|
| 사전·사후 입장 | 설문 (발언과 별개의 독립 호출) | `surveys` |
| 발언 중 입장 | 발언 분석이 추정한 입장 x | `stances` |
| 입장 이동 | 설득, 양보, 반발 | `moves` |
| 양보, 반박 | 발언 분석 | `concessions`, `attacks` |
| 합의 점수 | 종합보고서(종합, AI간, 인간간, AI-인간간) | `discussions` |
| 비용 | LLM 호출 수, 토큰 | `discussions` |
| 재현성 | 코드 커밋, 프롬프트 해시, 적용 설정, 모델, 생성 파라미터(`llm_params`: max_tokens, top_p, OpenAI 호환 서버 주소), 참가자별 시스템 프롬프트 해시(`llm.system_prompts`) | `discussions`(요약), 토론 상세의 `run_info`(전체) |

**사람 코딩:** `--coding-sample N`을 주면 파일 두 개가 만들어집니다.
- `coding_blind.csv`: 코더에게 주는 파일. 발언, 직전 발언, 대상 발언, 같은 화자의 이전 발언과 빈 코딩 칸(양보, 응답 여부, 자기 논거 반복, 정당화 수준, 존중 수준)이 들어 있습니다.
- `coding_key.csv`: LLM 판정. 코더에게 주지 않고, 일치도 계산에만 씁니다.

**일치도 계산:** 코더가 채운 파일로 사람-자동 판정, 코더 간 일치도(일치율, Cohen's kappa)를 계산합니다.

```bash
python scripts/coding_agreement.py --coded coder1.csv --key data/example/coding_key.csv
```

```bash
python scripts/coding_agreement.py --coded coder1.csv --second coder2.csv
```

**논거 반복 지표:** `utterances.repeat_score`는 같은 화자의 이전 주장과의 문자 2-gram 유사도(0~1)이고, `discussions.repeat_rate`는 그 값이 0.4 이상인 AI 발언의 비율입니다. 표현을 바꿔 같은 논거를 되풀이하면 잘 잡지 못하는 **대리 지표**입니다(실측에서 바꿔 말한 반복이 0.37~0.55). 사람 코딩(`code_repeats_own_argument`)과 비교해 기준을 보정한 뒤 쓰세요.

## 사례 생성 (연구 1)

`scripts/build_cases.py`가 공개 데이터에서 실험 계획을 만듭니다. 원자료는 `data/raw/`에 두며 저장소에 포함하지 않습니다. 문구(과제, 페르소나, 자료 머리말, 공모자 동의 표현)는 `config/cases.yaml`에 있습니다. 만든 계획은 쓰기 전에 모든 (주제, 조건)을 웹과 같은 생성 검사로 확인하고, 실패하면 파일을 쓰지 않습니다(`--allow-invalid`로 강제).

| 명령 | 원자료 | 만드는 것 |
|---|---|---|
| `wason` | `data/raw/delidata/*.tsv` (DeliData, CC-BY 4.0) | 3명 집단 복제: 같은 카드, 인간의 혼자 답을 심음. 조건 A-기준선·A-상태(각 2회), B(혼자 다시 풀기), C(초기 답 없음) |
| `wason-variants --n 60 --seed S` | 같음 | 같은 논리 구조의 새 변형. 초기 답은 DeliData 혼자 답의 역할 유형 분포에서 뽑음. 조건 A 두 모드 + C |
| `a1r-briefing` | `data/raw/a1r/briefing.pdf` (`pdftotext` 필요) | 정책안별 자료 상자(찬반 논거)와 영역 배경의 **초안** (`pdftotext -layout`의 열 위치로 추출) |
| `a1r-briefing-verify --briefing <초안> --report <결과> [--mark-verified]` | 같음 | 모든 칸을 다른 방식으로 읽은 PDF 원문(`pdftotext` 기본 모드, 칸이 한 단락으로 나옴)과 대조. 본편 쪽에서 단락 일치, 이어지는 단락 일치, 또는 문장 단위(모든 문장이 순서대로 있고 해당 단락에 빠진 문장 없음)로 통과. 쪽 안내 문구가 끼면 실패. 모두 통과하면 `verified` 기록. 설문 문구와 표 문구가 크게 다른 문항(유사도 낮음)은 같은 정책인지 사람이 확인 |
| `a1r --set development\|locked\|all --seed S --briefing <확정본>` | `data/raw/a1r/{dataset,codebook}.tab` (A1R, CC0) | 문항마다 민주 2·공화 2·무당층 1 층화 집단. 실제 프로필 페르소나, 사전 점수 심기, 0~10 설문. 조건 A-기준선·A-상태·B(자료만)·C(재응답)·D(심지 않음) |
| `a1r --debranded` | 같음 | `cases.yaml`의 이름 제거 문항(Q5A, Q3A, Q6F): 정책안 교체와 자료의 이름 구절 편집. 구절이 원문에 없거나, 금지어가 남거나, 문장이 깨지면(중복 관사, 소문자 시작 등) 만들지 않음 |
| `a1r --small-groups Q5A Q3A` | 같음 | A1R 실제 소집단(GROUP) 전원 복제 |
| `argq --seed S` | `data/raw/argq/*.csv` (IBM ArgQ 30k, CC-BY 3.0) | 8주제 × 표적 입장 2. 반대 논거 강(WA 상위 25%)·약(하위 25%) 3개씩, 총 토큰 ±10%. 조건 강·약 × 소수(1명이 3개)·다수(3명이 1개씩), 공모자 대본과 고정 순서 |

- `--allow-draft`: 검토 전 자료 상자 초안으로 만들기(파일럿용). 확정본이 아니면 기본으로 거부합니다.
- 실제 소집단은 8~16명입니다. 발언 수를 비우면 1인당 3개로 잡습니다(참가자 상한 `limits.max_personas` 16, 발언 수 상한 `limits.max_statements` 60).
- DeliData의 혼자 답 일부는 `["N", "/", "A"]`(기록 없음)입니다. 무효로 보고, 그런 참가자가 있는 집단은 복제에서 뺍니다.

## 분석 (연구 1)

`scripts/analyze_study1.py`가 실험 DB와 실행한 계획 파일을 합쳐 사전 등록한 검정을 돌립니다(모듈 `src/analysis/`). 혼합 모형은 R의 lme4·lmerTest를 `Rscript`로 부르므로 R과 두 패키지가 필요합니다(macOS: `brew install nlopt pkg-config` 뒤 R에서 `install.packages(c("lme4", "lmerTest"))`).

```bash
python scripts/analyze_study1.py --db data/study1/*.db --plans data/study1/*.yaml --out data/study1/results-claude.json
python scripts/analyze_study1.py ... --model gemini-3.5-flash-lite --out ...   # 비교 모델 재현
python scripts/analyze_study1.py ... --blind --boot 50                          # 스크립트 점검: 추정치를 쓰지 않음
```

- 제외 기준: 재시도 뒤에도 실패한 조건이 있는 블록은 그 연구에서 뺍니다. 사후 설문 무응답은 그 참가자만 뺍니다. 무응답률은 결과 파일의 `missing_rates`에 조건별로 남습니다.
- 혼합 모형이 수렴하지 않으면 고정 효과 추정치 + 다수준 군집 부트스트랩 구간으로 대체하고, 결과의 `method`에 적습니다.
- 인간 기준 자료: `data/raw/delidata/`, `data/raw/a1r/dataset.tab`.

## 주의

- **temperature를 바꿀 수 없는 모델:** `claude-sonnet-5-5`, `claude-fable-5*`는 기본값 외의 temperature를 받지 않고 적응형 사고가 기본입니다. 이 모델에는 temperature를 넣지 않고 호출하며, 실행 기록에는 `temperature: null`(모델 기본값)로 남습니다. 따라서 이 모델로는 temperature 조건을 실험할 수 없고, 분석 모델로 쓰면 temperature 0이 적용되지 않습니다. 구조화 출력은 json_schema 방식을 씁니다.

- 발언 분석(입장, 양보, 반박)은 LLM 판정입니다. 결론에 쓰기 전에 사람 코딩과의 일치도를 확인하세요.
- 같은 조건에서도 실행마다 결과가 달라집니다. 조건당 반복 수를 충분히 두세요.
- 사람 참여 실험(역할, 예약 차례, 사람용 설문, 동의, 가명 처리)은 아직 지원하지 않습니다.
