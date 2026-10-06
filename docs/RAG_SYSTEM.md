# RAG System Documentation

## Overview

The RAG (Retrieval-Augmented Generation) system enhances discussion quality by enabling agents to search for and incorporate real-world evidence into their arguments. Each agent generates persona-specific queries, retrieves relevant information, and seamlessly integrates findings into their responses.

## Architecture

### Components

```
RAG System
├── Query Generator      # Persona-based question generation
├── Query Router        # Classifies queries (factual vs opinion)
├── Web Search Service  # Tavily API integration
├── Evidence Extractor  # Summarizes search results
└── Response Augmenter  # Integrates evidence into responses
```

### Data Flow

```
1. Topic/Context → Query Generator
   ↓
2. Persona-specific Query
   ↓
3. Query Router (Factual? Opinion?)
   ↓
4. [If Factual] → Web Search
   ↓
5. Search Results → Evidence Extractor
   ↓
6. Summarized Evidence → Agent Response
   ↓
7. Augmented Response with Citations
```

## How It Works

### 1. Query Generation

Each agent generates queries based on their persona's perspective:

```python
# Example: Different personas, different queries
Topic: "AI Regulation in 2024"

Dr. Safety (AI Researcher):
→ "What safety incidents involving AI were reported in 2024?"

Mr. Innovation (Tech CEO):
→ "How have AI regulations impacted startup growth in 2024?"

Prof. Ethics (Philosophy):
→ "What ethical frameworks are being proposed for AI governance?"
```

### 2. Query Classification

The router uses LLM to classify queries:

```python
# Factual queries (trigger search)
- "What are the latest statistics on..."
- "Which countries have implemented..."
- "How many companies are using..."

# Opinion queries (no search needed)
- "Should we trust AI?"
- "What is the meaning of consciousness?"
- "Is regulation ethical?"
```

### 3. Evidence Search & Extraction

```python
# Search process
1. Query: "AI safety incidents 2024"
2. Tavily API returns 3-5 relevant results
3. Extractor summarizes key facts:
   - "OpenAI reported 2 minor incidents in Q1 2024"
   - "EU implemented new safety protocols in March"
   - "Study shows 15% reduction in AI errors"
```

### 4. Response Integration

Evidence is seamlessly woven into agent responses:

```
Without RAG:
"I believe AI safety is important."

With RAG:
"According to recent data from OpenAI's Q1 2024 report, 
even minor safety incidents can have cascading effects. 
The EU's March protocols, which reduced errors by 15%, 
demonstrate that proactive safety measures work."
```

## Configuration

### Basic Setup

```python
from config.discussion_config import update_config

# Enable RAG
update_config(
    enable_web_search=True,
    max_searches_per_agent=3,
    fact_check_enabled=True,
    search_trigger_probability=0.7
)
```

### Advanced Configuration

```python
# Maximum evidence usage
update_config(
    enable_web_search=True,
    search_trigger_probability=0.95,  # Almost always search
    max_searches_per_agent=10,        # Many searches allowed
    fact_check_enabled=True,          # Verify all claims
    use_cot_reasoning=True            # Deep reasoning with evidence
)

# Selective evidence usage
update_config(
    enable_web_search=True,
    search_trigger_probability=0.3,   # Occasional searches
    max_searches_per_agent=2,         # Limited searches
    fact_check_enabled=False         # No fact checking
)
```

## Query Templates

### Default Templates (rag_prompts.yaml)

```yaml
query_generation:
  user_template: |
    You are {name}, a {role} with expertise in {expertise}.
    Topic: "{topic}"
    
    Generate ONE specific question that would help support 
    your position based on YOUR expertise and beliefs.
    
    Format:
    QUESTION: [Your question]
    TYPE: [FACTUAL or OPINION]
    RATIONALE: [Why this matters to you]
```

### Customizing Query Generation

```yaml
# For more technical queries
query_generation:
  user_template: |
    As {name}, generate a highly specific, technical question
    about measurable data, statistics, or recent research...

# For broader queries
query_generation:
  user_template: |
    As {name}, what general information would help you 
    understand the current state of {topic}...
```

## Search Strategies

### 1. Persona-Aligned Search

Each agent searches for evidence that aligns with their expertise:

```python
# Scientist searches for:
- Peer-reviewed studies
- Statistical data
- Research findings

# Business leader searches for:
- Market reports
- Financial data
- Industry trends

# Activist searches for:
- Case studies
- Impact reports
- Community feedback
```

### 2. Evidence Types

```python
# Quantitative evidence
- Statistics: "75% of companies..."
- Metrics: "Reduced by 30%..."
- Rankings: "Ranked #1 in..."

# Qualitative evidence
- Expert opinions: "Dr. Smith argues..."
- Case studies: "In the Tesla case..."
- Trends: "Growing consensus that..."
```

### 3. Source Credibility

The system prioritizes credible sources:

```python
# High credibility
- Academic journals
- Government reports
- Established news outlets

# Medium credibility
- Industry reports
- Expert blogs
- Think tanks

# Lower credibility
- Opinion pieces
- Forums
- Unverified sources
```

## Display Features

### Evidence Display in Discussions

```
💡 Dr. Sarah Chen (present)
╭────────────────────────────────────────╮
│ [Agent's response incorporating         │
│ evidence from search...]                │
╰────────────────────────────────────────╯

📚 Research Query: "AI safety incidents 2024"
📊 Evidence: Found 3 incidents reported in Q1...
🔗 Sources: openai.com, ieee.org
```

### Metadata Tracking

```python
message.metadata = {
    "speaker": "Dr. Sarah Chen",
    "action": "present",
    "web_search_used": True,
    "search_query": "AI safety incidents 2024",
    "sources": ["openai.com", "ieee.org"],
    "evidence_summary": "3 incidents in Q1...",
    "confidence": 0.85
}
```

## Performance Optimization

### Caching Strategy

```python
# RAG results are cached for 5 minutes
cache = RAGCache(ttl_seconds=300)

# Duplicate queries return cached results
Query: "GPT-4 capabilities" → Search
Query: "GPT-4 capabilities" → Cache hit (no search)
```

### Rate Limiting

```python
# Prevent excessive API usage
max_searches_per_agent = 3      # Per discussion
max_searches_per_turn = 1       # Per response
search_cooldown_turns = 2       # Wait between searches
```

### Cost Management

```python
# Estimate costs
searches_per_discussion = agents * max_searches_per_agent
tavily_cost = searches * $0.001  # Example rate
llm_cost = additional_tokens * rate

# Reduce costs
- Lower search_trigger_probability
- Reduce max_searches_per_agent
- Enable caching
- Use summaries instead of full content
```

## Integration Examples

### Example 1: Always Search for Facts

```python
class FactCheckingAgent(DiscussionAgent):
    async def respond(self, prompt, context):
        # Always generate a factual query
        rag_result = await self.rag_service.process(
            prompt, 
            self.persona, 
            context
        )
        
        # Build response with evidence
        if rag_result.evidence:
            response = f"Based on {rag_result.sources[0]}, "
            response += self.generate_argument(rag_result.evidence)
        else:
            response = self.generate_opinion(prompt)
        
        return response
```

### Example 2: Selective Search

```python
# Only search when challenged
if "prove" in prompt.lower() or "evidence" in prompt.lower():
    rag_result = await self.rag_service.process(...)
    # Use evidence in response
```

### Example 3: Multi-Source Verification

```python
# Search multiple sources for controversial claims
queries = [
    "climate change scientific consensus 2024",
    "climate change economic impact studies",
    "climate change skeptic arguments"
]

results = []
for query in queries:
    result = await rag_service.search(query)
    results.extend(result)

# Synthesize multiple perspectives
```

## Troubleshooting

### Issue: No search results

```python
# Check:
1. TAVILY_API_KEY is set correctly
2. Internet connection is stable
3. Query is specific enough

# Solution:
- Broaden search terms
- Increase max_results
- Try different query formulation
```

### Issue: Irrelevant results

```python
# Check:
1. Query is too broad
2. Wrong query type classification

# Solution:
- Make queries more specific
- Add context to query
- Adjust classification prompts
```

### Issue: Too many searches

```python
# Check:
1. search_trigger_probability too high
2. max_searches_per_agent too high

# Solution:
update_config(
    search_trigger_probability=0.3,
    max_searches_per_agent=2
)
```

## API Reference

### RAGService

```python
class RAGService:
    async def process(
        topic: str,
        persona: Persona,
        context: List[Message]
    ) -> RAGResult
```

### RAGResult

```python
@dataclass
class RAGResult:
    query: str              # Generated query
    evidence: Optional[str] # Extracted evidence
    sources: List[str]      # Source URLs
    summary: str           # Evidence summary
```

### QueryGenerator

```python
class QueryGenerator:
    async def generate_persona_query(
        topic: str,
        persona: Persona,
        context: List[Message]
    ) -> QueryResult
```

## Best Practices

### 1. Query Design
- Be specific but not too narrow
- Include temporal context (2024, recent, latest)
- Align with persona expertise
- Avoid yes/no questions

### 2. Evidence Integration
- Don't just append evidence
- Weave it into natural argument flow
- Cite sources when appropriate
- Acknowledge when evidence is lacking

### 3. Performance
- Cache frequently searched topics
- Batch similar queries
- Set appropriate rate limits
- Monitor API usage and costs

### 4. Quality Control
- Verify source credibility
- Cross-reference multiple sources
- Flag contradictory evidence
- Update cache regularly

## Future Enhancements

### Planned Features
- Multi-source aggregation
- Fact verification chains
- Citation formatting
- Source credibility scoring
- Real-time news integration
- Academic paper search
- Statistical analysis tools
- Visual evidence support

### Research Directions
- Adversarial fact-checking
- Bias detection in sources
- Temporal reasoning
- Claim verification networks