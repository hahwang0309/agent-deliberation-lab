# Installation Guide

## System Requirements

### Minimum Requirements
- Python 3.8 or higher
- 4GB RAM
- 1GB free disk space
- Internet connection for API calls

### Recommended Requirements
- Python 3.10+
- 8GB RAM
- SSD storage
- Stable internet connection

## Step-by-Step Installation

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/multi-agents-persona-discussion-system.git
cd multi-agents-persona-discussion-system
```

### 2. Set Up Python Virtual Environment

#### On macOS/Linux:
```bash
python3 -m venv venv
source venv/bin/activate
```

#### On Windows:
```bash
python -m venv venv
venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

If you encounter issues, try installing packages individually:
```bash
pip install langchain>=0.1.0
pip install langchain-openai>=0.0.5
pip install langchain-google-genai>=0.0.5
pip install langchain-anthropic>=0.0.5
pip install langchain-mistralai>=0.0.1
pip install python-dotenv>=1.0.0
pip install pydantic>=2.0.0
pip install rich>=13.0.0
pip install typer>=0.9.0
pip install aiohttp>=3.8.0
pip install pyyaml>=6.0
```

### 4. Set Up API Keys

#### Create .env file:
```bash
cp .env.example .env
```

#### Edit .env and add your API keys:
```bash
# Required
OPENAI_API_KEY=your_openai_api_key_here

# Optional (for web search)
TAVILY_API_KEY=your_tavily_api_key_here

# Optional (for other LLM providers)
ANTHROPIC_API_KEY=your_anthropic_api_key_here
GOOGLE_API_KEY=your_google_api_key_here
MISTRAL_API_KEY=your_mistral_api_key_here
```

### 5. Getting API Keys

#### OpenAI API Key (Required)
1. Go to [OpenAI Platform](https://platform.openai.com/)
2. Sign up or log in
3. Navigate to API Keys section
4. Create new secret key
5. Copy and paste into .env file

#### Tavily API Key (Optional, for web search)
1. Visit [Tavily.com](https://tavily.com/)
2. Sign up for free account
3. Go to API Keys section
4. Copy your API key
5. Add to .env file

See [Tavily Setup Guide](TAVILY_SETUP.md) for detailed instructions.

#### Other LLM Providers (Optional)
- **Anthropic**: Visit [console.anthropic.com](https://console.anthropic.com/)
- **Google**: Visit [makersuite.google.com](https://makersuite.google.com/)
- **Mistral**: Visit [console.mistral.ai](https://console.mistral.ai/)

### 6. Verify Installation

Run the test script to verify everything is working:

```bash
python test_rag_quick.py
```

You should see:
```
✅ Imports OK
✅ RAG initialized
✅ Query generation works
✅ Query routing works correctly
✅ Web search works (if Tavily API key is set)
✅ All basic RAG functions working!
```

### 7. First Run

Start an interactive discussion:
```bash
python main.py
```

## Troubleshooting

### Common Issues

#### ImportError: No module named 'langchain'
- Make sure virtual environment is activated
- Reinstall requirements: `pip install -r requirements.txt`

#### OpenAI API Error
- Check if OPENAI_API_KEY is correctly set in .env
- Verify API key is valid and has credits
- Check internet connection

#### Web Search Not Working
- Verify TAVILY_API_KEY is set in .env
- Check if Tavily API key is valid
- Web search is optional; system works without it

#### Memory Issues
- Reduce max_statements in discussions
- Use fewer agents (2-3 instead of 4-5)
- Close other applications

### Getting Help

If you encounter issues:
1. Check the [troubleshooting section](TROUBLESHOOTING.md)
2. Search existing [GitHub issues](https://github.com/yourusername/repo/issues)
3. Create a new issue with:
   - Error message
   - Python version (`python --version`)
   - OS information
   - Steps to reproduce

## Next Steps

- Read the [Usage Guide](USAGE.md) to learn how to use the system
- Check the [Configuration Guide](CONFIGURATION.md) to customize settings
- Explore the [RAG System Documentation](RAG_SYSTEM.md) to understand the evidence-based discussion features