# 실험 실행 가이드

연구용 실험(AI 에이전트 간 토의, 조건 비교)을 실행하고 분석용 데이터를 뽑는 방법입니다. 웹 화면과 같은 엔진·저장 형식을 쓰지만, 실험은 **전용 DB**에서 배치로 실행합니다.

## 흐름

1. 실험 계획(YAML)을 작성합니다. 주제 × 조건 × 반복 수를 정합니다.
2. `--dry-run`으로 실행 건수와 예상 토큰을 확인합니다.
3. 배치를 실행합니다. 중단돼도 같은 명령으로 이어서 돌릴 수 있습니다.
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
| `limits.max_total_tokens` | 입력+출력 누적 토큰 상한. 다음 실행이 상한을 넘을 것 같으면 새 실행을 시작하지 않습니다 |
| `limits.max_cost_usd` + `prices` | 비용 상한. 단가(`input_per_mtok`, `output_per_mtok`)는 사용자가 확인한 값을 넣습니다. 코드에는 단가를 두지 않습니다 |
| `topics[]` | `key`, `topic`, `language`, `max_statements`, `use_moderator`, `personas`(dict 또는 `persona_templates.yaml`의 템플릿 id), `propositions`(고정 명제), `materials` 또는 `materials_file`(배경 자료, 계획 파일 기준 상대 경로), `survey`(사전·사후 설문) |
| `conditions[]` | `label`과 `experiment`(실험 조건). 항목은 [configuration.md](configuration.md#실험-조건-토론별)를 참고하세요 |

**실행 순서:** 반복 → 주제 → 조건 순으로 교차합니다. 시간에 따른 API 변화가 한 조건에 몰리지 않게 하기 위해서입니다.

**이어 돌리기:** 같은 배치에서 이미 `completed`인 (주제, 조건, 반복)은 건너뜁니다. 실패하거나 중단된 실행은 새 토론으로 다시 실행하고, 이전 기록은 감사용으로 남깁니다. 분석할 때는 `discussions` 표의 `status`로 걸러 내세요.

**토큰 추정:** 같은 배치에 완료된 실행이 있으면 그 평균을 씁니다. 없으면 발언 수 기반 대략치를 씁니다(Haiku 4.5 실측 기준 분석·설문·보고서를 포함해 발언 1개당 입력 약 10,700, 출력 약 1,530 토큰). 참가자 수, 자료집 길이, 모델에 따라 크게 달라지므로 첫 배치는 작게 돌려 평균을 얻으세요.

## 실험 조건으로 바꿀 수 있는 것

| 범주 | 항목 |
|---|---|
| 엔진 | `mode`: `stateful`(상태 기반) / `baseline`(순서대로 앞 발언에 답하는 단순 토론) |
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
| 재현성 | 코드 커밋, 프롬프트 해시, 적용 설정, 모델 | `discussions`(요약), 토론 상세의 `run_info`(전체) |

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

## 주의

- **temperature를 바꿀 수 없는 모델:** `claude-sonnet-5-5`, `claude-fable-5*`는 기본값 외의 temperature를 받지 않고 적응형 사고가 기본입니다. 이 모델에는 temperature를 넣지 않고 호출하며, 실행 기록에는 `temperature: null`(모델 기본값)로 남습니다. 따라서 이 모델로는 temperature 조건을 실험할 수 없고, 분석 모델로 쓰면 temperature 0이 적용되지 않습니다. 구조화 출력은 json_schema 방식을 씁니다.

- 발언 분석(입장, 양보, 반박)은 LLM 판정입니다. 결론에 쓰기 전에 사람 코딩과의 일치도를 확인하세요.
- 같은 조건에서도 실행마다 결과가 달라집니다. 조건당 반복 수를 충분히 두세요.
- 사람 참여 실험(역할, 예약 차례, 사람용 설문, 동의, 가명 처리)은 아직 지원하지 않습니다.
