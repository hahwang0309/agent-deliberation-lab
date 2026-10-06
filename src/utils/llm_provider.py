from typing import Optional, Dict, Any, List, Tuple
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
    def default_provider(cls) -> LLMProvider:
        """config.yaml의 llm.default_provider"""
        return LLMProvider(config_loader.get_llm_config().default_provider)

    @classmethod
    def _get_default_model(cls, provider: LLMProvider) -> str:
        """설정 파일에서 기본 모델 가져오기"""
        llm_config = config_loader.get_llm_config()
        provider_key = provider.value.lower()
        return llm_config.default_models.get(provider_key, {
            LLMProvider.OPENAI: "gpt-4",
            LLMProvider.GEMINI: "gemini-pro",
            LLMProvider.CLAUDE: "claude-haiku-4-5-20251001",
            LLMProvider.MISTRAL: "mistral-large-latest"
        }.get(provider))
    
    @classmethod
    def create_llm(
        cls,
        provider: Optional[LLMProvider] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        **kwargs
    ) -> BaseChatModel:
        """지정된 프로바이더의 LLM 인스턴스를 생성 (provider 생략 시 기본 프로바이더)"""
        provider = provider or cls.default_provider()
        
        # 설정 파일에서 기본값 가져오기
        llm_config = config_loader.get_llm_config()
        model = model or cls._get_default_model(provider)
        temperature = temperature if temperature is not None else llm_config.temperature
        max_tokens = kwargs.get('max_tokens', llm_config.max_tokens)
        timeout = kwargs.get('timeout', llm_config.timeout_seconds)
        max_retries = kwargs.get('max_retries', llm_config.max_retries)
        callbacks = kwargs.get('callbacks')
        
        if provider == LLMProvider.OPENAI:
            api_key = kwargs.get("api_key") or os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OpenAI API key is required")
            return ChatOpenAI(
                model=model,
                temperature=temperature,
                api_key=api_key,
                max_tokens=max_tokens,
                stream_usage=True,  # 스트리밍 시에도 토큰 사용량 수집
                timeout=timeout,
                max_retries=max_retries,
                callbacks=callbacks
            )
            
        elif provider == LLMProvider.GEMINI:
            api_key = kwargs.get("api_key") or os.getenv("GOOGLE_API_KEY")
            if not api_key:
                raise ValueError("Google API key is required")
            return ChatGoogleGenerativeAI(
                model=model,
                temperature=temperature,
                google_api_key=api_key,
                max_output_tokens=max_tokens,
                timeout=timeout,
                max_retries=max_retries,
                callbacks=callbacks
            )
            
        elif provider == LLMProvider.CLAUDE:
            api_key = kwargs.get("api_key") or os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError("Anthropic API key is required")
            return ChatAnthropic(
                model=model,
                temperature=temperature,
                anthropic_api_key=api_key,
                max_tokens=max_tokens,
                default_request_timeout=timeout,
                max_retries=max_retries,
                callbacks=callbacks
            )
            
        elif provider == LLMProvider.MISTRAL:
            api_key = kwargs.get("api_key") or os.getenv("MISTRAL_API_KEY")
            if not api_key:
                raise ValueError("Mistral API key is required")
            return ChatMistralAI(
                model=model,
                temperature=temperature,
                mistral_api_key=api_key,
                max_tokens=max_tokens,
                timeout=int(timeout),
                max_retries=max_retries,
                callbacks=callbacks
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


class LLMBundle:
    """토론 1건이 공유하는 LLM 클라이언트 캐시

    같은 (provider, model, temperature) 조합은 하나의 클라이언트를 재사용하고,
    모든 클라이언트에 동일한 콜백(예: 토큰 사용량 집계)을 연결한다.
    """

    def __init__(self, callbacks: Optional[List[Any]] = None):
        self.callbacks = callbacks or []
        self._cache: Dict[Tuple[LLMProvider, Optional[str], Optional[float]], BaseChatModel] = {}

    def get(self, provider: LLMProvider, model: Optional[str] = None,
            temperature: Optional[float] = None) -> BaseChatModel:
        key = (provider, model, temperature)
        if key not in self._cache:
            self._cache[key] = LLMFactory.create_llm(
                provider, model=model, temperature=temperature, callbacks=self.callbacks
            )
        return self._cache[key]
