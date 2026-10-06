from typing import Optional, Dict, Any
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_anthropic import ChatAnthropic
from langchain_mistralai import ChatMistralAI
from src.models.personas import LLMProvider
from config.config_loader import config_loader
import os
from dotenv import load_dotenv

load_dotenv()


class LLMFactory:
    """다양한 LLM 프로바이더를 생성하는 팩토리 클래스"""
    
    @classmethod
    def _get_default_model(cls, provider: LLMProvider) -> str:
        """설정 파일에서 기본 모델 가져오기"""
        llm_config = config_loader.get_llm_config()
        provider_key = provider.value.lower()
        return llm_config.default_models.get(provider_key, {
            LLMProvider.OPENAI: "gpt-4",
            LLMProvider.GEMINI: "gemini-pro",
            LLMProvider.CLAUDE: "claude-3-opus-20240229",
            LLMProvider.MISTRAL: "mistral-large-latest"
        }.get(provider))
    
    @classmethod
    def create_llm(
        cls,
        provider: LLMProvider,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        **kwargs
    ) -> BaseChatModel:
        """지정된 프로바이더의 LLM 인스턴스를 생성"""
        
        # 설정 파일에서 기본값 가져오기
        llm_config = config_loader.get_llm_config()
        model = model or cls._get_default_model(provider)
        temperature = temperature if temperature is not None else llm_config.temperature
        max_tokens = kwargs.get('max_tokens', llm_config.max_tokens)
        
        if provider == LLMProvider.OPENAI:
            api_key = kwargs.get("api_key") or os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OpenAI API key is required")
            return ChatOpenAI(
                model=model,
                temperature=temperature,
                api_key=api_key,
                max_tokens=max_tokens
            )
            
        elif provider == LLMProvider.GEMINI:
            api_key = kwargs.get("api_key") or os.getenv("GOOGLE_API_KEY")
            if not api_key:
                raise ValueError("Google API key is required")
            return ChatGoogleGenerativeAI(
                model=model,
                temperature=temperature,
                google_api_key=api_key,
                max_output_tokens=max_tokens
            )
            
        elif provider == LLMProvider.CLAUDE:
            api_key = kwargs.get("api_key") or os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError("Anthropic API key is required")
            return ChatAnthropic(
                model=model,
                temperature=temperature,
                anthropic_api_key=api_key,
                max_tokens=max_tokens
            )
            
        elif provider == LLMProvider.MISTRAL:
            api_key = kwargs.get("api_key") or os.getenv("MISTRAL_API_KEY")
            if not api_key:
                raise ValueError("Mistral API key is required")
            return ChatMistralAI(
                model=model,
                temperature=temperature,
                mistral_api_key=api_key,
                max_tokens=max_tokens
            )
            
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")
    
    @classmethod
    def get_available_providers(cls) -> Dict[LLMProvider, bool]:
        """환경변수에서 사용 가능한 프로바이더 확인"""
        return {
            LLMProvider.OPENAI: bool(os.getenv("OPENAI_API_KEY")),
            LLMProvider.GEMINI: bool(os.getenv("GOOGLE_API_KEY")),
            LLMProvider.CLAUDE: bool(os.getenv("ANTHROPIC_API_KEY")),
            LLMProvider.MISTRAL: bool(os.getenv("MISTRAL_API_KEY"))
        }