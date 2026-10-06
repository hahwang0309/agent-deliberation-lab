"""
모더레이터 에이전트 테스트
"""
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from api.services.moderator_agent import ModeratorAgent, DiscussionPhase


def test_opening_statement():
    """개회사 생성 테스트"""
    print("\n" + "=" * 80)
    print("TEST 1: 개회사 생성")
    print("=" * 80)
    
    investigation_a = {
        "name": "식품위생 정기조사",
        "purpose": "식품제조업소의 위생상태 점검",
        "scope": "서울시 내 식품제조업소",
        "target": "식품제조·가공업 영업허가를 받은 업소",
        "department": "서울시 보건환경연구원"
    }
    
    investigation_b = {
        "name": "HACCP 사후관리 조사",
        "purpose": "HACCP 인증업소 실태 점검",
        "scope": "서울시 내 HACCP 인증 업소",
        "target": "HACCP 인증을 받은 식품제조업소",
        "department": "식품의약품안전처"
    }
    
    personas = [
        {"name": "김법률", "role": "행정법 전문가"},
        {"name": "이실무", "role": "식품안전 실무자"},
        {"name": "박데이터", "role": "조사 분석가"}
    ]
    
    moderator = ModeratorAgent(min_rounds=3, max_rounds=10)
    
    print("\n⏳ 개회사 생성 중...")
    opening = moderator.start_discussion(
        investigation_a=investigation_a,
        investigation_b=investigation_b,
        personas=personas
    )
    
    print("\n" + "-" * 80)
    print("📢 모더레이터 개회사")
    print("-" * 80)
    print(opening)
    print("-" * 80)
    
    assert len(opening) > 100, "개회사가 너무 짧습니다"
    print("\n✅ 개회사 생성 완료")
    
    return moderator


def test_round_guidance():
    """라운드 가이드 생성 테스트"""
    print("\n" + "=" * 80)
    print("TEST 2: 라운드 가이드 생성")
    print("=" * 80)
    
    moderator = ModeratorAgent()
    
    discussion_summary = """
    라운드 1-2에서 각 페르소나가 초기 입장을 밝혔습니다.
    - 김법률: 법적 근거가 다르므로 부분 중복
    - 이실무: 실무적으로 대상이 거의 겹쳐 중복 의심
    - 박데이터: 조사 항목 분석 필요
    """
    
    persona_positions = {
        "김법률": "법적 근거는 다르지만 대상이 일부 중복",
        "이실무": "실무상 명확한 중복, 통합 필요",
        "박데이터": "데이터 분석 결과 60% 중복"
    }
    
    print("\n⏳ 라운드 3 가이드 생성 중...")
    guidance = moderator.guide_next_round(
        current_round=3,
        discussion_summary=discussion_summary,
        persona_positions=persona_positions
    )
    
    print("\n" + "-" * 80)
    print("🎯 라운드 3 가이드")
    print("-" * 80)
    print(f"단계: {guidance.get('phase')}")
    print(f"요약: {guidance.get('summary')}")
    print(f"\n합의사항:")
    for item in guidance.get('agreements', []):
        print(f"  ✓ {item}")
    print(f"\n논쟁사항:")
    for item in guidance.get('disagreements', []):
        print(f"  ⚠ {item}")
    print(f"\n다음 초점: {guidance.get('next_focus')}")
    print("-" * 80)
    
    assert 'summary' in guidance, "요약이 없습니다"
    print("\n✅ 라운드 가이드 생성 완료")
    
    return guidance


def test_consensus_check():
    """합의 확인 테스트"""
    print("\n" + "=" * 80)
    print("TEST 3: 합의 상태 확인")
    print("=" * 80)
    
    moderator = ModeratorAgent()
    
    discussion_summary = """
    5라운드에 걸친 토론 결과:
    - 대상 동일성: 모든 페르소나 동의 (HACCP 업소는 식품제조업소의 부분집합)
    - 내용 유사성: 위생점검 항목 80% 중복 확인
    - 기관: 서로 다른 기관 (다기관 중복)
    - 결론: C-2 유형 중복으로 합의
    """
    
    final_positions = {
        "김법률": "법적으로 C-2 유형 다기관 중복에 해당. 통합 또는 조정 필요",
        "이실무": "실무적으로 명확한 중복. 조사대상자 부담 과중",
        "박데이터": "데이터 분석 결과 85% 중복. 통합 권고"
    }
    
    print("\n⏳ 합의 상태 확인 중...")
    consensus = moderator.check_consensus(
        discussion_summary=discussion_summary,
        final_positions=final_positions
    )
    
    print("\n" + "-" * 80)
    print("📊 합의 상태")
    print("-" * 80)
    print(f"합의 도달: {'✅ 예' if consensus.has_consensus else '❌ 아니오'}")
    print(f"합의도: {consensus.consensus_level:.1%}")
    print(f"\n합의 영역:")
    for area in consensus.areas_of_agreement:
        print(f"  ✓ {area}")
    
    if consensus.areas_of_disagreement:
        print(f"\n불일치 영역:")
        for area in consensus.areas_of_disagreement:
            print(f"  ⚠ {area}")
    
    print(f"\n핵심 주장:")
    for persona, arguments in consensus.key_arguments.items():
        print(f"  [{persona}]")
        for arg in arguments:
            print(f"    - {arg}")
    print("-" * 80)
    
    print(f"\n✅ 합의 상태 확인 완료 (합의도: {consensus.consensus_level:.1%})")
    
    return consensus


def test_should_continue():
    """토론 계속 여부 판단 테스트"""
    print("\n" + "=" * 80)
    print("TEST 4: 토론 계속 여부 판단")
    print("=" * 80)
    
    moderator = ModeratorAgent(min_rounds=3, max_rounds=10)
    
    # 시나리오 1: 라운드 2 (최소 미달)
    print("\n[시나리오 1] 라운드 2 (최소 3라운드 미달)")
    decision1 = moderator.should_continue(
        current_round=2,
        recent_discussion="초기 의견 교환 중"
    )
    print(f"  계속 진행: {'✅ 예' if decision1.should_continue else '❌ 아니오'}")
    print(f"  이유: {decision1.reason}")
    print(f"  예상 남은 라운드: {decision1.estimated_remaining_rounds}")
    
    # 시나리오 2: 라운드 5 (진행 중)
    print("\n[시나리오 2] 라운드 5 (진행 중)")
    decision2 = moderator.should_continue(
        current_round=5,
        recent_discussion="심화 토론 중, 일부 합의 도출"
    )
    print(f"  계속 진행: {'✅ 예' if decision2.should_continue else '❌ 아니오'}")
    print(f"  이유: {decision2.reason}")
    print(f"  가이드: {decision2.guidance}")
    
    # 시나리오 3: 라운드 10 (최대 도달)
    print("\n[시나리오 3] 라운드 10 (최대 도달)")
    decision3 = moderator.should_continue(
        current_round=10,
        recent_discussion="최종 합의 도출 중"
    )
    print(f"  계속 진행: {'✅ 예' if decision3.should_continue else '❌ 아니오'}")
    print(f"  이유: {decision3.reason}")
    
    print("\n✅ 토론 제어 로직 정상 작동")
    
    return decision1, decision2, decision3


def test_full_flow():
    """전체 플로우 통합 테스트"""
    print("\n" + "=" * 80)
    print("TEST 5: 전체 플로우 통합")
    print("=" * 80)
    
    # 1. 설정
    investigation_a = {
        "name": "개인정보보호 실태조사",
        "purpose": "개인정보 처리 및 보호 실태 점검",
        "target": "공공기관",
        "department": "행정안전부"
    }
    
    investigation_b = {
        "name": "정보보안 점검",
        "purpose": "정보시스템 보안 취약점 점검",
        "target": "공공기관 정보시스템",
        "department": "한국인터넷진흥원"
    }
    
    personas = [
        {"name": "김보안", "role": "정보보안 전문가"},
        {"name": "이개인", "role": "개인정보보호 전문가"}
    ]
    
    moderator = ModeratorAgent(min_rounds=3, max_rounds=5)
    
    # 2. 개회
    print("\n[1단계] 개회")
    opening = moderator.start_discussion(
        investigation_a, investigation_b, personas
    )
    print(f"✓ 개회사 생성 ({len(opening)}자)")
    
    # 3. 라운드 진행 시뮬레이션
    for round_num in range(1, 6):
        print(f"\n[{round_num + 1}단계] 라운드 {round_num}")
        
        # 가이드 생성
        guidance = moderator.guide_next_round(
            current_round=round_num,
            discussion_summary=f"라운드 {round_num} 진행 중",
            persona_positions={
                "김보안": f"라운드 {round_num} 의견",
                "이개인": f"라운드 {round_num} 의견"
            }
        )
        print(f"✓ 가이드 생성 (단계: {guidance.get('phase')})")
        
        # 계속 여부 판단
        decision = moderator.should_continue(
            current_round=round_num,
            recent_discussion=f"라운드 {round_num} 토론 내용"
        )
        
        if not decision.should_continue:
            print(f"✓ 토론 종료 결정: {decision.reason}")
            break
        
        print(f"✓ 다음 라운드 계속 진행")
    
    # 4. 합의 확인
    print(f"\n[최종단계] 합의 확인")
    consensus = moderator.check_consensus(
        discussion_summary="전체 토론 요약",
        final_positions={
            "김보안": "부분 중복 판단",
            "이개인": "중복 판단"
        }
    )
    print(f"✓ 합의도: {consensus.consensus_level:.1%}")
    
    # 5. 폐회
    print(f"\n[종료단계] 폐회")
    closing = moderator.generate_closing_statement(
        consensus_status=consensus,
        final_verdict="부분 중복"
    )
    print(f"✓ 폐회사 생성 ({len(closing)}자)")
    
    print("\n✅ 전체 플로우 테스트 완료")


def run_all_tests():
    """모든 테스트 실행"""
    print("""
╔═══════════════════════════════════════════════════════════╗
║            모더레이터 에이전트 테스트                      ║
║            토론 진행 및 제어 시스템                        ║
╚═══════════════════════════════════════════════════════════╝
    """)
    
    import os
    if not os.getenv("OPENAI_API_KEY"):
        print("⚠️  경고: OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")
        return
    print("✅ OpenAI API 키 확인됨\n")
    
    try:
        # Test 1
        moderator = test_opening_statement()
        input("\n계속하려면 Enter...")
        
        # Test 2
        test_round_guidance()
        input("\n계속하려면 Enter...")
        
        # Test 3
        test_consensus_check()
        input("\n계속하려면 Enter...")
        
        # Test 4
        test_should_continue()
        input("\n계속하려면 Enter...")
        
        # Test 5
        test_full_flow()
        
        print("\n" + "=" * 80)
        print("✅ 모든 테스트 완료!")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    run_all_tests()

