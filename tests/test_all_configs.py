"""
모든 새 설정값 테스트
설정값이 정상적으로 로드되고 변경되는지 확인
"""
from config.discussion_config import get_config, update_config


def test_config_changes():
    """모든 새 설정이 정상 작동하는지 확인"""
    
    print("=" * 80)
    print("설정값 테스트")
    print("=" * 80)
    
    # 1. 기본값 확인
    config = get_config()
    print("\n=== 기본 설정값 ===")
    print(f"max_turns_per_agent: {config.max_turns_per_agent}")
    print(f"depth_analysis_window: {config.depth_analysis_window}")
    print(f"recent_mention_window: {config.recent_mention_window}")
    print(f"min_messages_before_transition: {config.min_messages_before_transition}")
    print(f"max_subtopics: {config.max_subtopics}")
    print(f"evidence_score_max: {config.evidence_score_max}")
    print(f"evidence_score_weight: {config.evidence_score_weight}")
    print(f"logic_score_max: {config.logic_score_max}")
    print(f"logic_score_weight: {config.logic_score_weight}")
    print(f"specificity_bonus: {config.specificity_bonus}")
    print(f"persuasion_threshold: {config.persuasion_threshold}")
    print(f"core_belief_strength: {config.core_belief_strength}")
    print(f"core_belief_flexibility: {config.core_belief_flexibility}")
    print(f"normal_belief_strength: {config.normal_belief_strength}")
    print(f"normal_belief_flexibility: {config.normal_belief_flexibility}")
    
    # 2. 값 변경
    print("\n=== 설정값 변경 ===")
    update_config(
        max_turns_per_agent=15,
        max_subtopics=7,
        persuasion_threshold=0.1,
        core_belief_strength=0.9,
        normal_belief_flexibility=0.6
    )
    
    # 3. 변경 확인
    config = get_config()
    print("\n=== 변경된 설정값 ===")
    print(f"max_turns_per_agent: {config.max_turns_per_agent}")
    print(f"max_subtopics: {config.max_subtopics}")
    print(f"persuasion_threshold: {config.persuasion_threshold}")
    print(f"core_belief_strength: {config.core_belief_strength}")
    print(f"normal_belief_flexibility: {config.normal_belief_flexibility}")
    
    # 4. 검증
    print("\n=== 검증 ===")
    errors = []
    
    if config.max_turns_per_agent != 15:
        errors.append(f"max_turns_per_agent 변경 실패: {config.max_turns_per_agent} != 15")
    else:
        print("✓ max_turns_per_agent 변경 성공")
    
    if config.max_subtopics != 7:
        errors.append(f"max_subtopics 변경 실패: {config.max_subtopics} != 7")
    else:
        print("✓ max_subtopics 변경 성공")
    
    if config.persuasion_threshold != 0.1:
        errors.append(f"persuasion_threshold 변경 실패: {config.persuasion_threshold} != 0.1")
    else:
        print("✓ persuasion_threshold 변경 성공")
    
    if config.core_belief_strength != 0.9:
        errors.append(f"core_belief_strength 변경 실패: {config.core_belief_strength} != 0.9")
    else:
        print("✓ core_belief_strength 변경 성공")
    
    if config.normal_belief_flexibility != 0.6:
        errors.append(f"normal_belief_flexibility 변경 실패: {config.normal_belief_flexibility} != 0.6")
    else:
        print("✓ normal_belief_flexibility 변경 성공")
    
    # 결과 출력
    print("\n" + "=" * 80)
    if errors:
        print("❌ 테스트 실패!")
        for error in errors:
            print(f"  - {error}")
        return False
    else:
        print("✅ 모든 설정 테스트 통과!")
        return True


if __name__ == "__main__":
    success = test_config_changes()
    exit(0 if success else 1)

