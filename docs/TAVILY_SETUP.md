# Tavily Web Search Integration Setup

## Overview
The discussion system now supports real-time web search capabilities through Tavily API, allowing agents to:
- Search for supporting evidence and data
- Fact-check claims made during discussions
- Find real-world examples and case studies
- Access current statistics and research

## Setup Instructions

### 1. Get Tavily API Key
1. Sign up at [Tavily.com](https://tavily.com)
2. Navigate to API Keys section
3. Copy your API key

### 2. Configure Environment
Add to your `.env` file:
```
TAVILY_API_KEY=your_api_key_here
```

### 3. Usage in Discussions

#### Enable/Disable Web Search
```python
# Enable web search (default)
discussion = create_discussion(
    personas, 
    enable_web_search=True
)

# Disable web search
discussion = create_discussion(
    personas,
    enable_web_search=False
)
```

#### Configure Search Behavior
```python
from config.discussion_config import update_config

update_config(
    enable_web_search=True,
    max_searches_per_agent=3,  # Max searches per agent
    fact_check_enabled=True,   # Enable fact-checking
    search_trigger_probability=0.2  # Random search probability
)
```

## Features

### 1. Automatic Evidence Search
Agents automatically search for evidence when:
- Moderator asks for specific data or examples
- Discussion mentions "research", "statistics", "evidence"
- Making claims that need support
- Random probability (20% by default)

### 2. Fact Checking
- Agents can fact-check each other's claims
- Moderator performs fact-checking on key assertions
- Sources are cited when available

### 3. Concrete Examples
When discussions become abstract, agents search for:
- Real-world case studies
- Specific implementation examples
- Historical precedents
- Current events related to the topic

## Search Triggers

Agents will search when encountering keywords:
- English: "data", "statistics", "research", "study", "evidence", "fact", "example", "case", "specifically", "exactly"
- Korean: "데이터", "통계", "연구", "사례", "증거", "구체적"

## Limitations

- Maximum 3 searches per agent per discussion (configurable)
- Search results are cached for 5 minutes
- Fact-checking focuses on reputable sources
- API rate limits apply based on your Tavily plan

## Example Output

When agents use web search, you'll see:
```
According to [Source Title]: [Specific data or fact]... (Source: URL)
```

Or for fact-checking:
```
🔍 FACT CHECK: Statement appears to be accurate based on 3 supporting sources.
```

## Troubleshooting

### No Search Results
- Check TAVILY_API_KEY is set correctly
- Verify API key is valid and has remaining credits
- Check internet connectivity

### Search Not Triggering
- Verify enable_web_search=True
- Check discussion contains search trigger keywords
- Increase search_trigger_probability if needed

### Rate Limiting
- Reduce max_searches_per_agent
- Implement longer cache duration
- Upgrade Tavily plan if needed