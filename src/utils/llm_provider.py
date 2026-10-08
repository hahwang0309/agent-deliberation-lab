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
        """프로바이더 기본 모델 (config.yaml llm.default_models, 없으면 오류)"""
        models = config_loader.get_llm_config().default_models
        if provider.value not in models:
            raise ValueError(f"config.yaml llm.default_models has no model for provider {provider.value}")
        return models[provider.value]

    @classmethod
    def fixed_sampling(cls, model: str) -> bool:
        """temperature를 기본값 외로 받지 않고 적응형 사고가 기본인 모델 (config.yaml llm.fixed_sampling_prefixes).
        이런 모델은 temperature를 빼고 호출하며(실행 기록에는 None = 모델 기본값),
        구조화 출력은 강제 도구 호출 대신 json_schema 방식을 쓴다(structured_output)."""
        return model.startswith(tuple(config_loader.get_llm_config().fixed_sampling_prefixes))

    @classmethod
    def supports_temperature(cls, provider: Optional[LLMProvider], model: Optional[str]) -> bool:
        provider = provider or cls.default_provider()
        model = model or cls._get_default_model(provider) or ""
        return not cls.fixed_sampling(model)

    @classmethod
    def effective_temperature(cls, provider: Optional[LLMProvider], model: Optional[str],
                              temperature: Optional[float]) -> Optional[float]:
        """실제로 요청에 들어가는 temperature (지원하지 않는 모델이면 None = 모델 기본값)"""
        return temperature if cls.supports_temperature(provider, model) else None

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
            # OPENAI_BASE_URL: OpenAI 호환 서버(로컬 vLLM·llama.cpp·Ollama 등). 로컬 서버는 키가 없어도 된다
            base_url = os.getenv("OPENAI_BASE_URL") or None
            api_key = kwargs.get("api_key") or os.getenv("OPENAI_API_KEY") or ("not-needed" if base_url else None)
            if not api_key:
                raise ValueError("OpenAI API key is required")
            return ChatOpenAI(
                model=model,
                temperature=temperature if cls.supports_temperature(provider, model) else None,
                api_key=api_key,
                base_url=base_url,
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
                temperature=temperature if cls.supports_temperature(provider, model) else None,
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
                temperature=temperature if cls.supports_temperature(provider, model) else None,
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
                temperature=temperature if cls.supports_temperature(provider, model) else None,
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
            LLMProvider.OPENAI: bool(os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_BASE_URL")),
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


class EmptyStructuredOutput(ValueError):
    """모델이 구조화 출력을 내지 않음 (예: Mistral이 도구 호출 없이 답함). 호출부는 실패로 처리해 재시도한다"""


def _require_output(result):
    if result is None:
        raise EmptyStructuredOutput("model returned no structured output")
    return result


class _RequireOutput:
    """구조화 출력 Runnable을 감싸 결과가 None이면 예외로 바꾼다"""

    def __init__(self, inner):
        self.inner = inner

    def invoke(self, *args, **kwargs):
        return _require_output(self.inner.invoke(*args, **kwargs))

    async def ainvoke(self, *args, **kwargs):
        return _require_output(await self.inner.ainvoke(*args, **kwargs))


def structured_output(llm: BaseChatModel, schema):
    """구조화 출력 Runnable. 사고가 기본인 모델은 강제 도구 호출이 안 되므로 json_schema 방식을 쓴다
    (실측: Sonnet 5.5·Haiku 4.5 모두 json_schema 동작, 기존 검증된 모델은 기존 방식 유지).
    결과가 없으면(None) 조용히 넘기지 않고 EmptyStructuredOutput을 낸다"""
    model = getattr(llm, "model", None) or getattr(llm, "model_name", None) or ""
    if isinstance(model, str) and model.startswith(tuple(config_loader.get_llm_config().json_schema_prefixes)):
        runnable = llm.with_structured_output(schema, method="json_schema")
    else:
        runnable = llm.with_structured_output(schema)
    return _RequireOutput(runnable)
