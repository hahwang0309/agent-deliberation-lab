"""
커스텀 설정 테스트
설정값을 변경하여 토론이 올바르게 작동하는지 확인
"""
import asyncio
from config.discussion_config import update_config, get_config
from src.generators.persona_generator import PersonaGenerator
from src.discussion import create_discussion


async def test_custom_settings():
    """커스텀 설정 테스트"""
    
    print("=" * 80)
    print("커스텀 설정 테스트 시작")
    print("=" * 80)
    
    # 1. 설정 변경
    print("\n1. 설정 변경 중...")
    update_config(
        max_turns_per_agent=5,  # 기본 10 → 5로 변경
        max_subtopics=3,        # 기본 5 → 3으로 변경
        min_depth_per_subtopic=2,  # 기본 3 → 2로 변경
        persuasion_threshold=0.15  # 기본 0.25 → 0.15로 변경 (더 쉽게 설득)
    )
    
    config = get_config()
    print(f"   ✓ max_turns_per_agent: {config.max_turns_per_agent}")
    print(f"   ✓ max_subtopics: {config.max_subtopics}")
    print(f"   ✓ min_depth_per_subtopic: {config.min_depth_per_subtopic}")
    print(f"   ✓ persuasion_threshold: {config.persuasion_threshold}")
    
    # 2. 페르소나 생성
    print("\n2. 페르소나 생성 중...")
    generator = PersonaGenerator()
    personas = await generator.generate_multiple_personas("AI Ethics", 3)
    print(f"   ✓ {len(personas)}개 페르소나 생성 완료")
    for persona in personas:
        print(f"      - {persona.name}: {persona.role}")
    
    # 3. 토론 실행
    print("\n3. 토론 실행 중...")
    discussion = create_discussion(personas, use_moderator=True)
    messages = await discussion.run(
        topic="AI Ethics",
        max_statements=10,
        streaming=False
    )
    
    # 4. 결과 확인
    print("\n" + "=" * 80)
    print("테스트 결과")
    print("=" * 80)
    print(f"✅ 총 메시지 수: {len(messages)}")
    print(f"✅ 에이전트별 발언 횟수:")
    
    agent_counts = {}
    for msg in messages:
        if hasattr(msg, 'agent_name') and msg.agent_name:
            agent_counts[msg.agent_name] = agent_counts.get(msg.agent_name, 0) + 1
    
    for agent_name, count in agent_counts.items():
        print(f"   - {agent_name}: {count}번 발언")
        if agent_name != "Moderator" and count > config.max_turns_per_agent:
            print(f"      ❌ 경고: max_turns_per_agent({config.max_turns_per_agent})를 초과했습니다!")
    
    print(f"\n✅ 테스트 완료!")


if __name__ == "__main__":
    asyncio.run(test_custom_settings())

