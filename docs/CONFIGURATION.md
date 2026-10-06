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

# 관리자 인증 (필수). 미설정 시 서버가 시작되지 않음.
# API·프론트엔드·SSE 전체가 HTTP Basic 인증으로 보호됨 (/health 제외).
# Basic 인증은 비밀번호를 평문에 가깝게 전송하므로 외부 공개 시 HTTPS 필수.
ADMIN_USERNAME=admin
ADMIN_PASSWORD=change-me

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