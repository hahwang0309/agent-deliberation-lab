"""
행정조사 분석을 위한 페르소나 자동 생성 서비스
"""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime
import json

from src.utils.llm_provider import LLMFactory
from src.models.personas import LLMProvider


class GeneratedPersona(BaseModel):
    """자동 생성된 페르소나"""
    role: str = Field(description="역할/직책")
    name: str = Field(description="이름")
    expertise: str = Field(description="전문 분야")
    perspective: str = Field(description="분석 관점")
    style: str = Field(description="토론 스타일")
    background: str = Field(description="배경 및 경력")
    key_concerns: List[str] = Field(description="주요 관심사")
    openness: float = Field(default=0.7, ge=0.0, le=1.0, description="의견 개방성")
    
    class Config:
        json_schema_extra = {
            "example": {
                "role": "행정법 전문가",
                "name": "김법률",
                "expertise": "행정법, 행정절차법, 정보공개",
                "perspective": "법적 근거와 절차적 적법성 중심으로 분석",
                "style": "분석적이고 논리적",
                "background": "행정법 교수 15년, 행정심판 위원 경력",
                "key_concerns": ["법적 근거의 충돌", "조사 권한의 중복", "절차적 적법성"],
                "openness": 0.7
            }
        }


class PersonaGenerationResult(BaseModel):
    """페르소나 생성 결과"""
    personas: List[GeneratedPersona]
    generation_reason: str = Field(description="페르소나 선정 이유")
    diversity_score: float = Field(description="다양성 점수", ge=0.0, le=1.0)
    quality_check: Dict[str, bool] = Field(description="품질 체크 결과")
    generated_at: datetime = Field(default_factory=datetime.utcnow)


print("=" * 80)
print("[PersonaAutoGenerator] Module loaded (latest version)")
print("=" * 80)

class PersonaAutoGenerator:
    """행정조사 기반 페르소나 자동 생성기"""
    
    PERSONA_GENERATION_PROMPT = """당신은 행정조사 중복 판별을 위한 전문가 페르소나를 생성하는 AI입니다.

📚 중복조사 개념:
**중복조사**란 동일한 조사대상자에게 반복적 또는 중첩적으로 시행되어 부담을 가중시키는 경우를 의미합니다.

**판별 핵심 요소:**
1. ① 조사 대상의 중복성: 모집단과 실제 대상자가 얼마나 겹치는가?
2. ② 조사 내용의 중복성: 조사 항목과 제출 자료가 얼마나 유사한가?
⚠️ 중요: 조사대상이 다르면 내용이 같아도 중복조사로 보지 않습니다.

두 개의 행정조사 정보를 분석하여, 중복 여부를 판별하는데 가장 적합한 전문가 페르소나 3~5명을 생성해주세요.

<행정조사 A>
{investigation_a_text}

<행정조사 B>
{investigation_b_text}

페르소나 생성 기준:
1. 다양한 관점 확보: 법적, 실무적, 기술적, 정책적 등 최소 3가지 이상의 서로 다른 관점
2. 조사 특성 반영: 위 조사들의 특성(대상, 내용)을 고려한 전문성
3. 균형잡힌 구성: 이론가/실무자, 찬성/반대/중립 관점 균형
4. 실질적 기여: 루브릭 4대 평가 항목을 정확히 판단할 수 있는 전문 분야

응답은 반드시 아래 JSON 형식으로만 작성하세요. 주석이나 설명 없이 순수 JSON만 반환하세요.

```json
{{
  "personas": [
    {{
      "role": "행정법 전문가",
      "name": "김지원",
      "expertise": "행정법, 행정절차법, 개인정보보호",
      "perspective": "법적 근거와 절차적 적법성 중심",
      "style": "분석적",
      "background": "행정학 박사, 공무원 20년 경력",
      "key_concerns": ["적법성", "공정성", "투명성"],
      "openness": 0.7
    }}
  ],
  "generation_reason": "이 페르소나들을 선정한 이유를 2-3문장으로 설명",
  "diversity_analysis": "관점의 다양성에 대한 분석을 2-3문장으로 설명"
}}
```

주의사항:
- 페르소나는 3~5명으로 구성
- openness는 0.0에서 1.0 사이의 숫자
- key_concerns는 문자열 배열
- 모든 필드는 필수이며 빠짐없이 작성
- 주석, 설명, 추가 텍스트 없이 JSON만 반환"""

    QUALITY_CHECK_PROMPT = """다음 생성된 페르소나들의 품질을 평가해주세요:

{personas_json}

다음 기준으로 평가:
1. 서로 다른 전문 분야인가? (3개 이상)
2. 다양한 관점을 포함하는가? (법적/실무적/기술적 등)
3. 역할이 명확히 구분되는가?
4. 행정조사 중복 판별에 실질적으로 도움이 되는가?
5. 찬성/반대/중립 등 균형잡힌 의견 분포가 예상되는가?

다음 형식의 JSON으로만 응답:
{{
  "has_diverse_fields": true/false,
  "has_diverse_perspectives": true/false,
  "has_clear_roles": true/false,
  "is_relevant": true/false,
  "is_balanced": true/false,
  "diversity_score": 0.0~1.0,
  "issues": ["문제점이 있다면 나열"],
  "recommendations": ["개선 권장사항이 있다면 나열"]
}}"""

    def __init__(
        self,
        llm_provider: LLMProvider = LLMProvider.OPENAI,
        model: Optional[str] = None,
        temperature: float = 0.3  # JSON 생성을 위해 낮은 temperature
    ):
        """
        Args:
            llm_provider: 사용할 LLM 프로바이더
            model: 모델 이름 (None이면 기본값 사용)
            temperature: 생성 온도 (0.0~1.0, 높을수록 창의적)
        """
        self.llm_provider = llm_provider
        self.model = model
        self.temperature = temperature
        self.llm = LLMFactory.create_llm(
            provider=llm_provider,
            model=model,
            temperature=temperature,
            max_tokens=2000  # 페르소나 JSON 생성을 위해 충분한 토큰
        )
    
    def generate_personas(
        self,
        investigation_a: Dict[str, Any],
        investigation_b: Dict[str, Any],
        num_personas: Optional[int] = None,
        max_retries: int = 3
    ) -> PersonaGenerationResult:
        """
        두 행정조사 정보를 기반으로 최적의 페르소나들을 자동 생성
        
        Args:
            investigation_a: 행정조사 A 정보
            investigation_b: 행정조사 B 정보
            num_personas: 생성할 페르소나 수 (None이면 3~5개 자동)
            max_retries: 최대 재시도 횟수
            
        Returns:
            PersonaGenerationResult
        """
        print("\n" + "="*80)
        print("🚀 generate_personas() 함수 시작!")
        print(f"   max_retries: {max_retries}")
        print(f"   num_personas: {num_personas}")
        print("="*80)
        
        for attempt in range(max_retries):
            print(f"\n▶️ for 루프 시작: attempt={attempt}")
            try:
                # 1. 페르소나 생성
                prompt = self._build_generation_prompt(
                    investigation_a, 
                    investigation_b,
                    num_personas
                )
                
                print(f"\n📤 LLM 호출 중 (시도 {attempt+1}/{max_retries})...")
                response = self.llm.invoke(prompt)
                print(f"✅ LLM 응답 받음")
                
                content = response.content
                print(f"📄 응답 타입: {type(content)}")
                print(f"📏 응답 길이: {len(content)}")
                print(f"\n🤖 LLM 전체 응답:")
                print("="*80)
                print(content)
                print("="*80)
                
                # JSON 파싱
                print(f"\n🔍 JSON 파싱 시작...")
                result_json = self._extract_json(content)
                print(f"✅ JSON 파싱 성공")
                print(f"📦 파싱된 데이터 키: {list(result_json.keys())}")
                
                # 2. 페르소나 검증
                personas_data = result_json.get("personas", [])
                print(f"👥 페르소나 데이터 타입: {type(personas_data)}")
                print(f"👥 페르소나 개수: {len(personas_data) if isinstance(personas_data, list) else 'NOT A LIST'}")
                
                if not isinstance(personas_data, list):
                    raise ValueError(f"personas가 리스트가 아닙니다: {type(personas_data)}")
                
                personas = [GeneratedPersona(**p) for p in personas_data]
                
                if len(personas) < 3:
                    if attempt < max_retries - 1:
                        continue
                    raise ValueError("페르소나가 3개 미만으로 생성되었습니다.")
                
                # 3. 품질 체크
                quality_check = self._check_quality(personas)
                
                # 4. 다양성 점수 계산
                diversity_score = self._calculate_diversity_score(personas, quality_check)
                
                # 품질이 낮으면 재시도
                if diversity_score < 0.6 and attempt < max_retries - 1:
                    continue
                
                return PersonaGenerationResult(
                    personas=personas,
                    generation_reason=result_json.get("generation_reason", ""),
                    diversity_score=diversity_score,
                    quality_check=quality_check
                )
                
            except Exception as e:
                print(f"\n⚠️ 시도 {attempt+1}/{max_retries} 실패: {str(e)}")
                if attempt < max_retries - 1:
                    print(f"🔄 재시도 중...\n")
                    continue
                print(f"\n❌ 최종 실패: {str(e)}")
                raise RuntimeError(f"페르소나 생성 실패: {str(e)}")
        
        raise RuntimeError("페르소나 생성 최대 재시도 횟수 초과")
    
    def _format_investigation_text(self, investigation: Dict[str, Any]) -> str:
        """조사 정보를 텍스트로 포맷팅"""
        # raw_text가 있으면 그대로 사용
        if "raw_text" in investigation:
            return investigation["raw_text"]
        
        # 구조화된 데이터를 텍스트로 변환
        lines = []
        if investigation.get("name"):
            lines.append(f"조사명: {investigation['name']}")
        if investigation.get("purpose"):
            lines.append(f"목적: {investigation['purpose']}")
        if investigation.get("scope"):
            lines.append(f"범위: {investigation['scope']}")
        if investigation.get("target"):
            lines.append(f"대상: {investigation['target']}")
        if investigation.get("methods"):
            lines.append(f"방법: {investigation['methods']}")
        if investigation.get("period"):
            lines.append(f"주기: {investigation['period']}")
        if investigation.get("legal_basis"):
            lines.append(f"법적근거: {investigation['legal_basis']}")
        if investigation.get("department"):
            lines.append(f"주관부서: {investigation['department']}")
        
        return "\n".join(lines)
    
    def _build_generation_prompt(
        self,
        investigation_a: Dict[str, Any],
        investigation_b: Dict[str, Any],
        num_personas: Optional[int] = None
    ) -> str:
        """페르소나 생성 프롬프트 구성"""
        prompt = self.PERSONA_GENERATION_PROMPT.format(
            investigation_a_text=self._format_investigation_text(investigation_a),
            investigation_b_text=self._format_investigation_text(investigation_b)
        )
        
        if num_personas:
            prompt += f"\n\n페르소나는 정확히 {num_personas}명을 생성해주세요."
        
        return prompt
    
    def _extract_json(self, content: str) -> Dict[str, Any]:
        """LLM 응답에서 JSON 추출 (robust)"""
        import re
        
        json_str = ""
        
        # 1단계: 코드 블록에서 JSON 추출
        if "```json" in content:
            # ```json ... ``` 형태
            match = re.search(r'```json\s*\n?(.*?)\n?```', content, re.DOTALL)
            if match:
                json_str = match.group(1).strip()
        elif "```" in content:
            # ``` ... ``` 형태
            match = re.search(r'```\s*\n?(.*?)\n?```', content, re.DOTALL)
            if match:
                json_str = match.group(1).strip()
        
        # 2단계: 코드 블록이 없으면 중괄호로 추출
        if not json_str:
            # 첫 번째 { 부터 마지막 } 까지
            start = content.find("{")
            if start != -1:
                # 중괄호 매칭을 위한 카운터
                brace_count = 0
                for i in range(start, len(content)):
                    if content[i] == '{':
                        brace_count += 1
                    elif content[i] == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            json_str = content[start:i+1]
                            break
        
        if not json_str:
            raise ValueError("JSON을 찾을 수 없습니다.")
        
        # 3단계: JSON 정리
        # 주석 제거 (//로 시작하는 라인만)
        json_str = re.sub(r'^\s*//.*$', '', json_str, flags=re.MULTILINE)
        # 트레일링 콤마 제거 (배열/객체 끝의 쉼표만)
        json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
        
        # 4단계: 파싱 시도
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            print(f"\n❌ JSON 파싱 실패: {e}")
            print(f"📄 추출된 JSON (처음 500자):\n{json_str[:500]}\n")
            
            # 재시도: strict=False로 파싱
            try:
                return json.loads(json_str, strict=False)
            except Exception as e2:
                print(f"❌ strict=False로도 실패: {e2}")
                raise ValueError(f"JSON 파싱 실패: {str(e)}")
    
    def _check_quality(self, personas: List[GeneratedPersona]) -> Dict[str, bool]:
        """페르소나 품질 체크"""
        # 간단한 자동 체크
        roles = [p.role for p in personas]
        expertises = [p.expertise for p in personas]
        perspectives = [p.perspective for p in personas]
        
        quality = {
            "has_diverse_fields": len(set(expertises)) >= 3,
            "has_diverse_perspectives": len(set(perspectives)) >= 3,
            "has_clear_roles": len(set(roles)) == len(roles),  # 역할 중복 없음
            "is_relevant": len(personas) >= 3,
            "is_balanced": True  # 기본값, 실제로는 더 복잡한 로직 필요
        }
        
        return quality
    
    def _calculate_diversity_score(
        self,
        personas: List[GeneratedPersona],
        quality_check: Dict[str, bool]
    ) -> float:
        """다양성 점수 계산"""
        # 품질 체크 통과 비율
        passed_checks = sum(quality_check.values())
        total_checks = len(quality_check)
        base_score = passed_checks / total_checks
        
        # 페르소나 수에 따른 보너스
        num_bonus = min(len(personas) - 3, 2) * 0.05  # 4명=0.05, 5명=0.1
        
        # openness 다양성 (다양한 개방성 수준)
        openness_values = [p.openness for p in personas]
        openness_std = (max(openness_values) - min(openness_values)) if openness_values else 0
        openness_bonus = openness_std * 0.1  # 최대 0.1
        
        return min(base_score + num_bonus + openness_bonus, 1.0)
    
    def regenerate_with_feedback(
        self,
        investigation_a: Dict[str, Any],
        investigation_b: Dict[str, Any],
        previous_personas: List[GeneratedPersona],
        feedback: str
    ) -> PersonaGenerationResult:
        """
        피드백을 반영하여 페르소나 재생성
        
        Args:
            investigation_a: 행정조사 A
            investigation_b: 행정조사 B
            previous_personas: 이전 생성된 페르소나들
            feedback: 개선 피드백
        """
        prompt = self._build_generation_prompt(investigation_a, investigation_b)
        prompt += f"""

<이전 생성된 페르소나>
{json.dumps([p.dict() for p in previous_personas], ensure_ascii=False, indent=2)}

<개선 피드백>
{feedback}

위 피드백을 반영하여 페르소나를 재생성해주세요."""
        
        response = self.llm.invoke(prompt)
        result_json = self._extract_json(response.content)
        
        personas = [GeneratedPersona(**p) for p in result_json.get("personas", [])]
        quality_check = self._check_quality(personas)
        diversity_score = self._calculate_diversity_score(personas, quality_check)
        
        return PersonaGenerationResult(
            personas=personas,
            generation_reason=result_json.get("generation_reason", ""),
            diversity_score=diversity_score,
            quality_check=quality_check
        )

