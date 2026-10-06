"""
페르소나 자동 생성기 테스트
"""
import sys
from pathlib import Path

# 프로젝트 루트를 Python path에 추가
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from api.services.persona_auto_generator import PersonaAutoGenerator
from src.models.personas import LLMProvider


def test_basic_persona_generation():
    """기본 페르소나 생성 테스트"""
    
    # 샘플 행정조사 데이터
    investigation_a = {
        "name": "식품위생 정기조사",
        "purpose": "식품제조업소의 위생상태 점검 및 식품안전 확보",
        "scope": "서울시 내 전체 식품제조업소",
        "target": "식품제조·가공업 영업허가를 받은 업소",
        "methods": "현장 방문 점검, 시설 위생상태 확인, 샘플 채취",
        "period": "연 2회 (상반기, 하반기)",
        "legal_basis": "식품위생법 제22조, 식품위생법 시행규칙 제44조",
        "department": "서울시 보건환경연구원"
    }
    
    investigation_b = {
        "name": "식품안전관리인증기준(HACCP) 사후관리 조사",
        "purpose": "HACCP 인증업소의 식품안전관리 실태 점검",
        "scope": "서울시 내 HACCP 인증 식품제조업소",
        "target": "HACCP 인증을 받은 식품제조·가공업소",
        "methods": "현장 실사, 기록 검토, 위해요소 관리 확인",
        "period": "연 1회 이상",
        "legal_basis": "식품위생법 제48조, HACCP 적용업소 지정 고시",
        "department": "식품의약품안전처"
    }
    
    print("=" * 80)
    print("🤖 페르소나 자동 생성 테스트")
    print("=" * 80)
    
    # 페르소나 생성기 초기화
    generator = PersonaAutoGenerator(
        llm_provider=LLMProvider.OPENAI,
        temperature=0.8
    )
    
    print("\n📝 행정조사 A:", investigation_a["name"])
    print("📝 행정조사 B:", investigation_b["name"])
    print("\n⏳ 페르소나 생성 중...\n")
    
    try:
        # 페르소나 생성
        result = generator.generate_personas(
            investigation_a=investigation_a,
            investigation_b=investigation_b
        )
        
        print(f"✅ 생성 완료! ({len(result.personas)}명)")
        print(f"📊 다양성 점수: {result.diversity_score:.2f}")
        print(f"\n💡 선정 이유:\n{result.generation_reason}\n")
        
        # 생성된 페르소나 출력
        print("=" * 80)
        print("생성된 페르소나 목록")
        print("=" * 80)
        
        for i, persona in enumerate(result.personas, 1):
            print(f"\n[페르소나 {i}]")
            print(f"👤 이름: {persona.name}")
            print(f"💼 역할: {persona.role}")
            print(f"🎓 전문분야: {persona.expertise}")
            print(f"👁️ 관점: {persona.perspective}")
            print(f"💬 스타일: {persona.style}")
            print(f"📚 배경: {persona.background}")
            print(f"🔍 주요 관심사:")
            for concern in persona.key_concerns:
                print(f"   - {concern}")
            print(f"🌡️ 개방성: {persona.openness}")
        
        # 품질 체크 결과
        print("\n" + "=" * 80)
        print("품질 체크 결과")
        print("=" * 80)
        for check, passed in result.quality_check.items():
            status = "✅" if passed else "❌"
            print(f"{status} {check}: {passed}")
        
        return result
        
    except Exception as e:
        print(f"❌ 에러 발생: {e}")
        raise


def test_specific_number_personas():
    """특정 개수의 페르소나 생성 테스트"""
    
    investigation_a = {
        "name": "개인정보보호 실태조사",
        "purpose": "개인정보 처리 및 보호 실태 점검",
        "scope": "서울시 전체 공공기관",
        "target": "100인 이상 개인정보를 처리하는 공공기관",
        "methods": "온라인 설문조사, 현장 실사, 보안점검",
        "period": "연 1회",
        "legal_basis": "개인정보보호법 제58조",
        "department": "행정안전부"
    }
    
    investigation_b = {
        "name": "정보시스템 보안취약점 점검",
        "purpose": "정보시스템의 보안취약점 진단 및 개선",
        "scope": "서울시 공공기관 정보시스템",
        "target": "주요 정보시스템을 운영하는 공공기관",
        "methods": "시스템 취약점 스캐닝, 모의해킹, 보안설정 점검",
        "period": "연 1회",
        "legal_basis": "정보통신망법 제45조",
        "department": "한국인터넷진흥원"
    }
    
    print("\n" + "=" * 80)
    print("🎯 정확히 4명의 페르소나 생성 테스트")
    print("=" * 80)
    
    generator = PersonaAutoGenerator()
    
    print("\n⏳ 4명의 페르소나 생성 중...\n")
    
    result = generator.generate_personas(
        investigation_a=investigation_a,
        investigation_b=investigation_b,
        num_personas=4
    )
    
    print(f"✅ 생성 완료! (요청: 4명, 생성: {len(result.personas)}명)")
    
    for i, persona in enumerate(result.personas, 1):
        print(f"{i}. {persona.name} ({persona.role})")
    
    return result


def test_regeneration_with_feedback():
    """피드백 기반 재생성 테스트"""
    
    investigation_a = {
        "name": "소상공인 경영실태조사",
        "purpose": "소상공인의 경영 현황 및 애로사항 파악",
        "scope": "전국 소상공인",
        "target": "매출액 10억원 이하 소상공인",
        "methods": "설문조사, 면접조사",
        "period": "연 1회",
        "legal_basis": "소상공인 보호 및 지원에 관한 법률",
        "department": "중소벤처기업부"
    }
    
    investigation_b = {
        "name": "전통시장 상인 실태조사",
        "purpose": "전통시장 상인의 경영 및 생활실태 조사",
        "scope": "전국 전통시장",
        "target": "전통시장 상인",
        "methods": "설문조사, 현장조사",
        "period": "격년 1회",
        "legal_basis": "전통시장 및 상점가 육성을 위한 특별법",
        "department": "중소벤처기업부"
    }
    
    print("\n" + "=" * 80)
    print("🔄 피드백 기반 재생성 테스트")
    print("=" * 80)
    
    generator = PersonaAutoGenerator()
    
    # 첫 번째 생성
    print("\n[1차 생성]")
    result1 = generator.generate_personas(
        investigation_a=investigation_a,
        investigation_b=investigation_b
    )
    
    print(f"생성된 페르소나:")
    for p in result1.personas:
        print(f"  - {p.name} ({p.role})")
    
    # 피드백으로 재생성
    feedback = """
    좋은 페르소나들이지만, 다음을 개선해주세요:
    1. 전통시장 상인 대표를 추가해주세요 (현장의 목소리 반영)
    2. 경제학자보다는 실무 중심 전문가가 더 필요합니다
    3. 중복 판별에 더 집중할 수 있는 감사/평가 전문가를 포함해주세요
    """
    
    print(f"\n[피드백]\n{feedback}")
    print("\n[2차 생성 (피드백 반영)]")
    
    result2 = generator.regenerate_with_feedback(
        investigation_a=investigation_a,
        investigation_b=investigation_b,
        previous_personas=result1.personas,
        feedback=feedback
    )
    
    print(f"재생성된 페르소나:")
    for p in result2.personas:
        print(f"  - {p.name} ({p.role})")
    
    print(f"\n다양성 점수 변화: {result1.diversity_score:.2f} → {result2.diversity_score:.2f}")
    
    return result2


if __name__ == "__main__":
    print("""
╔═══════════════════════════════════════════════════════════╗
║     페르소나 자동 생성기 테스트                            ║
║     행정조사 중복 판별을 위한 AI 페르소나 생성             ║
╚═══════════════════════════════════════════════════════════╝
    """)
    
    # 환경 변수 확인
    import os
    if not os.getenv("OPENAI_API_KEY"):
        print("⚠️  경고: OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")
        print("   .env 파일에 API 키를 설정해주세요.\n")
    else:
        print("✅ OpenAI API 키 확인됨\n")
    
    try:
        # 테스트 1: 기본 생성
        result1 = test_basic_persona_generation()
        
        # 테스트 2: 특정 개수 생성
        input("\n계속하려면 Enter를 누르세요...")
        result2 = test_specific_number_personas()
        
        # 테스트 3: 피드백 재생성
        input("\n계속하려면 Enter를 누르세요...")
        result3 = test_regeneration_with_feedback()
        
        print("\n" + "=" * 80)
        print("✅ 모든 테스트 완료!")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()

