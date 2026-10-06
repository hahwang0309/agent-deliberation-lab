# Multi-Agent Persona Discussion System

An AI-powered discussion system where multiple personas with distinct backgrounds and beliefs engage in thoughtful, evidence-based debates using RAG (Retrieval-Augmented Generation).

## 🌟 Key Features

- **🎭 Persona-Based Discussion**: AI agents with unique backgrounds, expertise, and beliefs
- **🔍 RAG Integration**: Real-time web search for evidence-based arguments
- **🧠 Belief Evolution**: Agents can change positions based on compelling arguments
- **🌐 Multi-LLM Support**: OpenAI, Claude, Gemini, Mistral
- **📊 Consensus Tracking**: Real-time tracking of agreements and divergences
- **🌏 Multi-language**: Supports English and Korean discussions

## 🚀 Quick Start

### 방법 1: Docker로 실행 (권장)

**Prerequisites:**
- Docker & Docker Compose

**실행:**
```bash
# 1. 저장소 클론
git clone https://github.com/yourusername/multi-agents-persona-discussion-system.git
cd multi-agents-persona-discussion-system

# 2. 환경변수 설정
cp .env.example .env
# .env 파일에서 OPENAI_API_KEY 설정

# 3. Docker로 실행 (Linux/Mac)
chmod +x docker-start.sh
./docker-start.sh

# Windows
docker-start.bat
```

**접속:**
- 프론트엔드: http://localhost
- API 문서: http://localhost/docs

**자세한 내용:** [Docker 배포 가이드](docs/docker-deployment.md)

---

### 방법 2: 로컬 실행

**Prerequisites:**
- Python 3.8+
- OpenAI API key (required)
- PostgreSQL (선택 사항, SQLite 기본값)

**Installation:**
```bash
# Clone the repository
git clone https://github.com/yourusername/multi-agents-persona-discussion-system.git
cd multi-agents-persona-discussion-system

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env and add your API keys
```

### Basic Usage

```bash
# Run interactive discussion
python main.py

# Run with specific topic
python main.py discuss "Should AI be regulated?"

# Generate personas for a topic
python main.py generate "Climate change solutions"
```

## 📖 Documentation

- [Installation Guide](docs/INSTALLATION.md) - Detailed setup instructions
- [Configuration Guide](docs/CONFIGURATION.md) - System configuration options
- [Usage Guide](docs/USAGE.md) - Complete usage examples
- [Architecture](docs/ARCHITECTURE.md) - System design and components
- [RAG System](docs/RAG_SYSTEM.md) - How the RAG integration works

## 🏗️ Project Structure

```
├── config/                 # Configuration files
│   ├── config.yaml        # System settings
│   ├── prompts.yaml       # Agent prompts
│   └── rag_prompts.yaml   # RAG prompts
├── src/
│   ├── core/              # Core discussion system
│   ├── services/          # RAG, web search, reasoning
│   ├── models/            # Data models
│   ├── utils/             # Utilities
│   └── generators/        # Persona generation
├── docs/                  # Documentation
└── main.py               # Main entry point
```

## 🔧 Configuration

Edit `config/config.yaml` to customize:
- Number of agents
- Discussion parameters
- LLM settings
- RAG behavior

See [Configuration Guide](docs/CONFIGURATION.md) for details.

## 🤝 Contributing

Contributions are welcome! Please read our contributing guidelines before submitting PRs.

## 📄 License

MIT License - see LICENSE file for details.

## 🙏 Acknowledgments

- Built with LangChain and LangGraph
- Web search powered by Tavily API
- LLM providers: OpenAI, Anthropic, Google, Mistral