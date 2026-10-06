# Usage Guide

## Table of Contents
1. [Basic Usage](#basic-usage)
2. [Command Line Interface](#command-line-interface)
3. [Creating Personas](#creating-personas)
4. [Running Discussions](#running-discussions)
5. [Advanced Features](#advanced-features)
6. [Examples](#examples)

## Basic Usage

### Interactive Mode

The simplest way to start is using interactive mode:

```bash
python main.py
```

This will:
1. Prompt you for a discussion topic
2. Ask how many agents you want (or auto-generate)
3. Create personas if needed
4. Start the discussion

### Command Line Mode

```bash
# Start a discussion with auto-generated personas
python main.py discuss "Should we implement universal basic income?"

# Generate personas for a topic
python main.py generate "Future of renewable energy" --count 3

# Use existing personas
python main.py discuss "AI ethics" --use-saved
```

## Command Line Interface

### Main Commands

#### `discuss` - Start a discussion
```bash
python main.py discuss [TOPIC] [OPTIONS]

Options:
  --agents INTEGER      Number of agents (2-5)
  --moderator/--no-moderator  Include moderator
  --max-turns INTEGER   Maximum discussion turns
  --streaming/--no-streaming  Enable real-time output
  --language TEXT       Language (en/ko/auto)
  --provider TEXT       LLM provider (openai/anthropic/google/mistral)
```

#### `generate` - Generate personas
```bash
python main.py generate [TOPIC] [OPTIONS]

Options:
  --count INTEGER       Number of personas to generate
  --diversity TEXT      Diversity level (low/medium/high)
  --save/--no-save     Save personas for reuse
```

#### `custom` - Create custom personas
```bash
python main.py custom

# Interactive prompts will guide you through:
# - Name
# - Role/profession
# - Background
# - Expertise areas
# - Core beliefs
# - Personality traits
```

## Creating Personas

### Method 1: Auto-Generation

```python
from src.generators.persona_generator import PersonaGenerator
from src.models import LLMProvider

generator = PersonaGenerator(provider=LLMProvider.OPENAI)
personas = await generator.generate_diverse_personas(
    topic="Climate change",
    num_personas=3,
    ensure_opposing_views=True
)
```

### Method 2: Manual Creation

```python
from src.models import Persona

scientist = Persona(
    name="Dr. Sarah Chen",
    role="Climate Scientist",
    background="20 years researching atmospheric physics at NASA",
    personality=["analytical", "passionate", "data-driven"],
    expertise=["climate modeling", "atmospheric science", "data analysis"],
    communication_style="Uses scientific evidence and peer-reviewed research",
    beliefs=[
        "Climate change is an urgent crisis requiring immediate action",
        "Scientific consensus should guide policy decisions",
        "Technology and innovation can help solve environmental challenges"
    ]
)

economist = Persona(
    name="Mark Johnson",
    role="Economic Policy Advisor",
    background="Former Wall Street analyst, now policy consultant",
    personality=["pragmatic", "skeptical", "results-oriented"],
    expertise=["economic modeling", "policy analysis", "market dynamics"],
    communication_style="Focuses on cost-benefit analysis and practical implications",
    beliefs=[
        "Economic stability is essential for societal wellbeing",
        "Climate policies must be economically viable",
        "Market-based solutions are more effective than regulations"
    ]
)
```

### Method 3: Mixed Approach

```python
# Generate base personas and customize
personas = await generator.generate_diverse_personas(topic, 2)

# Modify generated personas
personas[0].beliefs.append("Local solutions are key to global problems")
personas[1].personality.append("optimistic")
```

## Running Discussions

### Basic Discussion

```python
from src.discussion import create_discussion
from src.models import LLMProvider

# Create discussion with personas
discussion = create_discussion(
    personas=personas,
    provider=LLMProvider.OPENAI,
    use_moderator=True,
    enable_web_search=True
)

# Run discussion
messages = await discussion.run(
    topic="How should society address climate change?",
    max_statements=20,
    streaming=True
)
```

### Configuring Discussion Behavior

```python
from config.discussion_config import update_config

# Academic debate style
update_config(
    use_cot_reasoning=True,           # Deep reasoning
    prefer_building_over_challenging=0.3,  # More challenging
    require_evidence_probability=0.7,  # High evidence requirement
    enable_web_search=True,           # Use web search for facts
    max_searches_per_agent=5          # Allow more searches
)

# Brainstorming style
update_config(
    use_cot_reasoning=False,          # Faster responses
    prefer_building_over_challenging=0.8,  # More collaborative
    require_evidence_probability=0.2,  # Less evidence needed
    enable_web_search=False           # Focus on ideas, not facts
)
```

### Monitoring Discussion Progress

```python
# With streaming output
async for message in discussion.run_stream(topic):
    print(f"{message.speaker}: {message.content}")
    
    # Check for web search usage
    if message.metadata.get("web_search_used"):
        print(f"  → Searched: {message.metadata['search_query']}")
    
    # Check for belief evolution
    if message.metadata.get("belief_evolved"):
        print(f"  → Position shifted on: {message.metadata['evolved_topic']}")
```

## Advanced Features

### 1. RAG (Retrieval-Augmented Generation)

The system automatically:
- Generates persona-specific search queries
- Searches for relevant evidence
- Incorporates findings into arguments

```python
# Enable maximum RAG usage
update_config(
    enable_web_search=True,
    search_trigger_probability=0.9,  # Almost always search
    max_searches_per_agent=10,       # Allow many searches
    fact_check_enabled=True          # Verify claims
)
```

### 2. Belief Evolution

Agents can change their positions based on compelling arguments:

```python
# Configure evolution sensitivity
update_config(
    evolution_openness_default=0.7,  # How open to change
    evolution_threshold=0.4          # Lower = easier to change
)

# Track evolution
for agent in discussion.agents:
    changes = agent.get_belief_changes()
    if changes:
        print(f"{agent.persona.name} changed position on:")
        for topic, shift in changes.items():
            print(f"  - {topic}: {shift['magnitude']}% shift")
```

### 3. Consensus Tracking

Monitor agreements and disagreements:

```python
from src.consensus_tracker import ConsensusTracker

tracker = discussion.consensus_tracker
consensus_items = tracker.get_consensus_items()
conflicts = tracker.get_conflict_points()

print(f"Agreements: {len(consensus_items)}")
print(f"Disagreements: {len(conflicts)}")
```

### 4. Multi-Language Support

```python
# Korean discussion
messages = await discussion.run(
    topic="인공지능 규제가 필요한가?",
    language="ko"
)

# Auto-detect language
messages = await discussion.run(
    topic="¿Debe regularse la IA?",
    language="auto"
)
```

## Examples

### Example 1: Technical Debate with Evidence

```python
# Setup for technical discussion
from src.models import Persona, LLMProvider
from src.discussion import create_discussion
from config.discussion_config import update_config

# Configure for evidence-based discussion
update_config(
    enable_web_search=True,
    use_cot_reasoning=True,
    fact_check_enabled=True,
    search_trigger_probability=0.8
)

# Create expert personas
personas = [
    Persona(
        name="Dr. AI Safety",
        role="AI Safety Researcher",
        background="PhD from MIT, 10 years at DeepMind",
        expertise=["AI safety", "machine learning", "risk assessment"],
        beliefs=["AI poses existential risks", "Safety research is underfunded"],
        personality=["cautious", "analytical"],
        communication_style="Academic, cites research papers"
    ),
    Persona(
        name="Tech Optimist",
        role="Silicon Valley Entrepreneur",
        background="Founded 3 AI startups",
        expertise=["product development", "market dynamics", "innovation"],
        beliefs=["AI will solve major problems", "Innovation shouldn't be stifled"],
        personality=["optimistic", "bold"],
        communication_style="Practical, focuses on real-world applications"
    )
]

# Run discussion
discussion = create_discussion(
    personas,
    provider=LLMProvider.OPENAI,
    use_moderator=True,
    enable_web_search=True
)

messages = await discussion.run(
    topic="Should there be a pause on AI development?",
    max_statements=15,
    streaming=True
)
```

### Example 2: Creative Brainstorming

```python
# Configure for creative collaboration
update_config(
    prefer_building_over_challenging=0.9,  # Very collaborative
    use_cot_reasoning=False,               # Faster, more intuitive
    enable_web_search=False                # Focus on creativity
)

# Create creative personas
personas = await generator.generate_diverse_personas(
    topic="Future city design",
    num_personas=4,
    diversity="high"
)

discussion = create_discussion(
    personas,
    use_moderator=False  # Free-flowing discussion
)

messages = await discussion.run(
    topic="Design a city for 2050",
    max_statements=25
)
```

### Example 3: Fact-Checking Discussion

```python
# Maximum fact-checking configuration
update_config(
    enable_web_search=True,
    fact_check_enabled=True,
    search_trigger_probability=1.0,  # Always search
    max_searches_per_agent=10
)

# Run discussion on controversial topic
messages = await discussion.run(
    topic="Effectiveness of renewable energy vs nuclear power",
    max_statements=20
)

# Analyze search usage
total_searches = sum(
    1 for msg in messages 
    if msg.metadata.get("web_search_used")
)
print(f"Total web searches performed: {total_searches}")
```

## Best Practices

### 1. Persona Design
- **Diversity**: Include 3-5 personas with different backgrounds
- **Balance**: Mix supporters and skeptics for balanced discussion
- **Expertise**: Ensure relevant expertise for the topic
- **Beliefs**: Give each persona 3-5 clear core beliefs

### 2. Topic Selection
- **Specific**: "AI regulation in healthcare" vs just "AI"
- **Debatable**: Topics with multiple valid perspectives
- **Current**: Topics where web search can find recent information
- **Scoped**: Not too broad to discuss meaningfully

### 3. Configuration
- **Start simple**: Use defaults first, then customize
- **Match intent**: Configure based on discussion goals
- **Monitor costs**: More searches and reasoning = higher API costs
- **Test small**: Try with fewer turns first

### 4. Output Processing
- **Stream for UX**: Use streaming for better user experience
- **Log searches**: Track what evidence was used
- **Save results**: Store interesting discussions for analysis
- **Extract insights**: Identify consensus and key disagreements

## Troubleshooting

### Agents not searching for evidence
```python
# Force more searches
update_config(
    enable_web_search=True,
    search_trigger_probability=0.95,
    max_searches_per_agent=10
)
# Also check TAVILY_API_KEY is set
```

### Discussions too short or superficial
```python
# Encourage depth
update_config(
    min_response_sentences=5,
    max_response_sentences=10,
    use_cot_reasoning=True,
    cot_depth=4
)
```

### Agents agreeing too much
```python
# Increase conflict
update_config(
    prefer_building_over_challenging=0.2,  # More challenging
    require_evidence_probability=0.8       # Demand proof
)
```

### High API costs
```python
# Reduce costs
update_config(
    use_cot_reasoning=False,      # Less reasoning
    max_searches_per_agent=2,     # Fewer searches
    max_response_sentences=5      # Shorter responses
)
# Use cheaper models like gpt-3.5-turbo
```