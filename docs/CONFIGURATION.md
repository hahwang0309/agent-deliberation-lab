# Configuration Guide

## Overview

The system uses three main configuration files:
- `config/config.yaml` - System settings
- `config/prompts.yaml` - Agent prompts and templates
- `config/rag_prompts.yaml` - RAG system prompts
- `config/discussion_config.py` - Runtime configuration

## System Configuration (config.yaml)

### Basic Structure

```yaml
system:
  default_provider: "openai"
  language: "auto"  # auto, en, ko
  max_retries: 3
  timeout: 30

llm:
  temperature: 0.7
  max_tokens: 500
  default_models:
    openai: "gpt-4"
    anthropic: "claude-3-opus-20240229"
    google: "gemini-pro"
    mistral: "mistral-large-latest"

discussion:
  default_num_agents: 3
  max_agents: 5
  min_agents: 2
  default_max_turns: 20
  enable_moderator: true
  turn_based: false  # Natural discussion flow

personas:
  auto_generate: true
  diversity_weight: 0.8
  expertise_depth: "deep"
  evolution_enabled: true
```

### Key Settings Explained

#### Accounts & Limits

- 계정은 가입 신청 → 관리자 승인, 또는 관리자가 직접 발급(임시 비밀번호, 첫 로그인 시 변경)한다.
- 일반 사용자 제한(`config.yaml` `limits.*`): 동시 실행 `user_max_concurrent`(기본 1), 하루(UTC) 시작 수 `user_daily_starts`(기본 5), 웹검색·신념추론 허용 `user_expensive_features`(기본 false). 관리자는 제한 없음. 사용자별 값은 관리자 화면에서 덮어쓸 수 있다.
- 서버 전체 동시 실행 상한: `limits.max_global_running`.

#### LLM Settings

- `llm.timeout_seconds` (기본 60), `llm.max_retries` (기본 2): 모든 프로바이더 호출에 적용
- **temperature**: Controls randomness (0.0-1.0)
  - Lower (0.1-0.3): More focused, deterministic
  - Medium (0.5-0.7): Balanced creativity
  - Higher (0.8-1.0): More creative, diverse

- **max_tokens**: Maximum response length
  - 300-500: Concise responses
  - 500-800: Detailed responses
  - 800+: Very detailed responses

#### Discussion Settings
- **default_num_agents**: Number of discussion participants
- **enable_moderator**: Whether to include a moderator
- **turn_based**: Set to `false` for natural discussion flow

## Runtime Configuration (discussion_config.py)

### Programmatic Configuration

```python
from config.discussion_config import update_config

# Configure discussion parameters
update_config(
    # Question settings
    max_questions_per_discussion=3,
    turns_between_questions=5,
    
    # RAG settings
    enable_web_search=True,
    max_searches_per_agent=3,
    fact_check_enabled=True,
    search_trigger_probability=0.7,
    
    # Reasoning settings
    use_cot_reasoning=True,
    cot_depth=3,
    
    # Discussion dynamics
    prefer_building_over_challenging=0.6,
    require_evidence_probability=0.3
)
```

### Configuration Parameters

#### Question Management
- **max_questions_per_discussion**: Limit moderator questions (default: 3)
- **turns_between_questions**: Minimum gap between questions (default: 5)
- **agent_question_probability**: How often agents ask questions (default: 0.05)

#### Web Search & RAG
- **enable_web_search**: Enable/disable web search (default: true)
- **max_searches_per_agent**: Search limit per agent (default: 3)
- **fact_check_enabled**: Enable fact checking (default: true)
- **search_trigger_probability**: Chance of triggering search (default: 0.5)

#### Discussion Behavior
- **prefer_building_over_challenging**: Balance between agreement and disagreement (0.0-1.0)
  - 0.0: Maximum challenging/disagreement
  - 0.5: Balanced
  - 1.0: Maximum building/agreement
  
- **require_evidence_probability**: How often agents demand evidence (0.0-1.0)

#### Evolution Settings
- **evolution_openness_default**: Base openness to changing beliefs (0.0-1.0)
- **evolution_threshold**: Threshold for belief change (default: 0.5)

## Prompt Configuration (prompts.yaml)

### Structure

```yaml
agent:
  base_persona: |
    You are {name}, a {role} with the following background:
    {background}
    
    Your personality traits: {personality}
    Your areas of expertise: {expertise}
    Your communication style: {communication_style}
    
  belief_emphasis: |
    Your core beliefs that guide your thinking:
    {beliefs}
    
    Always reason from these beliefs and values.

moderator:
  opening: |
    Welcome to our discussion on "{topic}".
    
  probing_question: |
    {agent_name}, you mentioned {point}.
    Can you provide specific evidence or examples?
```

### Customizing Prompts

1. **Agent Personality**: Modify `base_persona` to change how agents present themselves
2. **Belief System**: Adjust `belief_emphasis` to change how strongly beliefs influence responses
3. **Moderator Style**: Customize moderator prompts for different discussion styles

## RAG Configuration (rag_prompts.yaml)

### Query Generation Settings

```yaml
query_generation:
  system: "You are generating a focused question from a specific persona's perspective."
  user_template: |
    You are {name}, a {role} with expertise in {expertise}.
    Based on YOUR expertise, generate ONE specific question...

query_classification:
  factual_keywords: ["data", "statistics", "research", ...]
  opinion_keywords: ["should", "believe", "think", ...]
```

### Customizing RAG Behavior

1. **Query Generation**: Modify how agents formulate search queries
2. **Classification**: Adjust keywords for factual vs opinion classification
3. **Evidence Extraction**: Customize how search results are summarized

## Environment Variables (.env)

### Required Variables

```bash
# Required for basic operation
OPENAI_API_KEY=sk-...

# JWT 서명 키 (필수, 32자 이상). 미설정·예시값이면 서버가 시작되지 않음.
SECRET_KEY=...
# 최초 관리자 (관리자가 없을 때만 생성, 첫 로그인 시 비밀번호 변경 강제)
ADMIN_EMAIL=admin@example.com
ADMIN_INITIAL_PASSWORD=...
# HTTPS 운영 시 true (인증 쿠키 Secure 플래그)
COOKIE_SECURE=false

# Optional for enhanced features
TAVILY_API_KEY=tvly-...
```

### Optional Variables

```bash
# Alternative LLM providers
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=...
MISTRAL_API_KEY=...

# Logging (stdout 출력)
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR
```

## Usage Examples

### Example 1: Academic Debate Configuration

```python
update_config(
    max_questions_per_discussion=5,
    use_cot_reasoning=True,
    cot_depth=4,
    prefer_building_over_challenging=0.3,  # More challenging
    require_evidence_probability=0.7,      # High evidence requirement
    enable_web_search=True,
    fact_check_enabled=True
)
```

### Example 2: Brainstorming Session

```python
update_config(
    max_questions_per_discussion=2,
    use_cot_reasoning=False,
    prefer_building_over_challenging=0.8,  # More collaborative
    require_evidence_probability=0.1,      # Low evidence requirement
    enable_web_search=False
)
```

### Example 3: Fact-Based Analysis

```python
update_config(
    max_questions_per_discussion=4,
    use_cot_reasoning=True,
    enable_web_search=True,
    max_searches_per_agent=5,
    fact_check_enabled=True,
    search_trigger_probability=0.9  # Almost always search
)
```

## Performance Tuning

### For Faster Responses
- Reduce `max_tokens`
- Lower `cot_depth`
- Disable `use_cot_reasoning`
- Use faster models (gpt-3.5-turbo instead of gpt-4)

### For Higher Quality
- Increase `max_tokens`
- Enable `use_cot_reasoning`
- Increase `cot_depth`
- Use advanced models (gpt-4, claude-3-opus)
- Enable web search

### For More Engaging Discussions
- Balance `prefer_building_over_challenging` around 0.5
- Enable evolution with higher `evolution_openness_default`
- Increase `max_questions_per_discussion`
- Enable moderator

## Troubleshooting Configuration Issues

### Issue: Agents not searching for evidence
- Check `enable_web_search` is true
- Verify TAVILY_API_KEY is set
- Increase `search_trigger_probability`

### Issue: Discussions too short
- Increase `default_max_turns`
- Reduce `max_questions_per_discussion`
- Adjust `prefer_building_over_challenging` for more debate

### Issue: Agents not evolving beliefs
- Check `evolution_enabled` is true
- Increase `evolution_openness_default`
- Lower `evolution_threshold`

## Best Practices

1. **Start with defaults**: Begin with default settings and adjust gradually
2. **Test incrementally**: Change one setting at a time to understand impacts
3. **Monitor costs**: Higher quality settings use more API tokens
4. **Save configurations**: Keep different config sets for different use cases
5. **Document changes**: Track what settings work best for your needs