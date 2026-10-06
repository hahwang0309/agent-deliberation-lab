"""
행정조사 중복 판별 API 테스트 스크립트
"""
import time
import json
import requests
from datetime import datetime

API_BASE = "http://localhost:8000"


def print_section(title):
    """섹션 제목 출력"""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60 + "\n")


def test_health_check():
    """헬스 체크"""
    print_section("1️⃣  헬스 체크")
    
    response = requests.get(f"{API_BASE}/health")
    print(f"상태 코드: {response.status_code}")
    print(f"응답: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
    
    if response.status_code == 200:
        print("✅ 서버 정상 작동 중")
        return True
    else:
        print("❌ 서버 응답 없음")
        return False


def submit_analysis():
    """분석 요청"""
    print_section("2️⃣  분석 요청")
    
    with open("test_investigation_request.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    
    print("요청 데이터:")
    print(f"  - 조사 A: {data['investigation_a']['name']}")
    print(f"  - 조사 B: {data['investigation_b']['name']}")
    print(f"  - 라운드: {data['min_rounds']} ~ {data['max_rounds']}")
    print()
    
    response = requests.post(
        f"{API_BASE}/api/v1/investigations",
        json=data
    )
    
    print(f"상태 코드: {response.status_code}")
    
    if response.status_code == 202:
        result = response.json()
        analysis_id = result.get("analysis_id")
        print(f"✅ 분석 시작!")
        print(f"📋 Analysis ID: {analysis_id}")
        return analysis_id
    else:
        print("❌ 분석 요청 실패")
        print(response.text)
        return None


def poll_status(analysis_id, max_attempts=60, interval=5):
    """상태 폴링"""
    print_section("3️⃣  분석 진행 상태 확인")
    
    print(f"⏱️  최대 대기 시간: {max_attempts * interval // 60}분")
    print(f"🔄 확인 간격: {interval}초\n")
    
    for attempt in range(1, max_attempts + 1):
        time.sleep(interval)
        
        response = requests.get(f"{API_BASE}/api/v1/investigations/{analysis_id}")
        
        if response.status_code != 200:
            print(f"❌ 조회 실패: {response.status_code}")
            continue
        
        result = response.json()
        status = result.get("status")
        
        # 진행 상황 표시
        elapsed = attempt * interval
        print(f"[{attempt:2d}/{max_attempts}] 경과: {elapsed:3d}초 | 상태: {status}")
        
        if status == "completed":
            print("\n🎉 분석 완료!\n")
            return result
        elif status == "failed":
            print("\n❌ 분석 실패!")
            print(f"오류: {result.get('error', '알 수 없음')}")
            return None
    
    print(f"\n⏱️  타임아웃: {max_attempts * interval // 60}분 초과")
    return None


def display_result(result):
    """결과 출력"""
    print_section("4️⃣  분석 결과")
    
    # 기본 정보
    print("📊 기본 정보")
    print(f"  - 분석 ID: {result['analysis_id']}")
    print(f"  - 조사 A: {result['investigation_a_name']}")
    print(f"  - 조사 B: {result['investigation_b_name']}")
    print(f"  - 생성 시각: {result['created_at']}")
    print()
    
    # 최종 판정
    print("⚖️  최종 판정")
    print(f"  - 결과: {result['final_verdict']}")
    print(f"  - 합의도: {result['consensus_status']['consensus_level']:.1%}")
    print(f"  - 총 라운드: {result['total_rounds']}회")
    print()
    
    # 사전 분석
    prelim = result['preliminary_analysis']
    print("🔍 사전 분석 결과")
    print(f"  - 중복 여부: {'중복' if prelim['is_duplicate'] else '비중복'}")
    if prelim.get('duplication_type'):
        print(f"  - 유형: {prelim['duplication_type']} ({prelim['type_description']})")
    print(f"  - 심각도: {prelim['severity']}")
    print(f"  - 신뢰도: {prelim['confidence']:.1%}")
    print()
    
    # 유사도 점수
    scores = prelim['similarity_scores']
    print("📈 유사도 점수")
    print(f"  - 대상 유사도: {scores['target_similarity']:.1%}")
    print(f"  - 내용 유사도: {scores['content_similarity']:.1%}")
    print(f"  - 목적 유사도: {scores['purpose_similarity']:.1%}")
    print(f"  - 방법 유사도: {scores['method_similarity']:.1%}")
    print(f"  - 시기 중첩도: {scores['period_overlap']:.1%}")
    print()
    
    # 참여 페르소나
    print("👥 참여 페르소나")
    for persona in result['personas']:
        print(f"  - {persona['name']} ({persona['role']})")
        print(f"    전문분야: {persona['expertise']}")
        print(f"    관점: {persona['perspective']}")
    print()
    
    # 합의 사항
    consensus = result['consensus_status']
    if consensus['agreed_points']:
        print("✅ 합의된 사항")
        for point in consensus['agreed_points']:
            print(f"  - {point}")
        print()
    
    if consensus['disagreed_points']:
        print("⚠️  불일치 사항")
        for point in consensus['disagreed_points']:
            print(f"  - {point}")
        print()
    
    # 권고사항
    if prelim.get('recommendations'):
        print("💡 권고사항")
        for rec in prelim['recommendations']:
            print(f"  - {rec}")
        print()


def download_report(analysis_id):
    """보고서 다운로드"""
    print_section("5️⃣  보고서 다운로드")
    
    response = requests.get(f"{API_BASE}/api/v1/investigations/{analysis_id}/report")
    
    if response.status_code == 200:
        filename = f"report_{analysis_id}.md"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(response.text)
        
        print(f"✅ 보고서 저장: {filename}")
        print()
        
        # 미리보기
        lines = response.text.split("\n")
        print("📄 보고서 미리보기 (처음 30줄)")
        print("-" * 60)
        for line in lines[:30]:
            print(line)
        print("-" * 60)
        print()
        
        return filename
    else:
        print(f"❌ 보고서 다운로드 실패: {response.status_code}")
        return None


def main():
    """메인 함수"""
    print()
    print("=" * 60)
    print("  🧪 행정조사 중복 판별 API 테스트")
    print("=" * 60)
    print()
    
    start_time = time.time()
    
    try:
        # 1. 헬스 체크
        if not test_health_check():
            print("\n⚠️  서버가 실행 중인지 확인하세요:")
            print("   python -m uvicorn api.main:app --reload")
            return
        
        # 2. 분석 요청
        analysis_id = submit_analysis()
        if not analysis_id:
            return
        
        # 3. 상태 폴링
        result = poll_status(analysis_id, max_attempts=60, interval=5)
        if not result:
            return
        
        # 4. 결과 출력
        display_result(result)
        
        # 5. 보고서 다운로드
        report_file = download_report(analysis_id)
        
        # 완료
        elapsed = time.time() - start_time
        print_section("✨ 테스트 완료")
        print(f"⏱️  총 소요 시간: {elapsed:.1f}초 ({elapsed / 60:.1f}분)")
        print(f"📋 Analysis ID: {analysis_id}")
        if report_file:
            print(f"📄 보고서 파일: {report_file}")
        print()
        
    except KeyboardInterrupt:
        print("\n\n⚠️  테스트 중단됨 (Ctrl+C)")
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

