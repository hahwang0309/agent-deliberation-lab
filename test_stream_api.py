"""
SSE 스트리밍 API 테스트 스크립트
"""
import requests
import json
import sys

# API 엔드포인트
API_URL = "http://localhost:8000/api/v1/investigations/stream"

# 테스트 데이터 - 문자열 형식으로 전달 (스키마가 Union[str, InvestigationInput] 지원)
test_data = {
    "investigation_a": """조사번호: TEST-001
부처: 국세청
조사명: 법인세 신고 내역 검증 조사
법령근거: 국세기본법 제81조의8
조사대상: 주식회사 ABC (사업자번호: 123-45-67890)
조사목적: 2022년 법인세 신고 내역의 정확성 검증
조사범위: 2022년 법인세 신고서, 재무제표, 장부
조사기간: 2023-01-15 ~ 2023-02-15
담당부서: 국세청 조사국""",

    "investigation_b": """조사번호: TEST-002
부처: 서울지방국세청
조사명: 부가가치세 신고 내역 검증 조사
법령근거: 부가가치세법 제5조
조사대상: 주식회사 ABC (사업자번호: 123-45-67890)
조사목적: 2022년 부가가치세 신고 내역의 정확성 검증
조사범위: 2022년 부가가치세 신고서, 매출 장부, 세금계산서
조사기간: 2023-03-01 ~ 2023-04-01
담당부서: 서울지방국세청 조사과""",

    "persona_count": 3,
    "max_rounds": 1  # 빠른 테스트를 위해 라운드 1개만
}

def test_stream_api():
    """SSE 스트리밍 API 테스트"""

    print("=" * 80)
    print("SSE 스트리밍 API 테스트 시작")
    print("=" * 80)
    print(f"URL: {API_URL}")
    print(f"페르소나 수: {test_data['persona_count']}")
    print("=" * 80)
    print()

    try:
        # SSE 스트리밍 요청
        response = requests.post(
            API_URL,
            json=test_data,
            headers={
                "Content-Type": "application/json",
                "Accept": "text/event-stream"
            },
            stream=True,
            timeout=600  # 10분 타임아웃
        )

        response.raise_for_status()

        print("[OK] 연결 성공! 이벤트 수신 중...\n")

        # 이벤트 카운터
        event_counts = {}
        search_count = 0

        # SSE 이벤트 파싱
        for line in response.iter_lines():
            if not line:
                continue

            line = line.decode('utf-8')

            # 이벤트 타입 파싱
            if line.startswith('event:'):
                event_type = line.split(':', 1)[1].strip()
                event_counts[event_type] = event_counts.get(event_type, 0) + 1

            # 데이터 파싱
            elif line.startswith('data:'):
                data_str = line.split(':', 1)[1].strip()

                try:
                    data = json.loads(data_str)

                    # 이벤트 타입별 처리
                    event_type = event_counts.get('last_event', 'unknown')

                    if 'personas_generated' in str(data):
                        print(f"\n[PERSONAS] 페르소나 생성: {data.get('count', 0)}명")
                        for p in data.get('personas', []):
                            print(f"   - {p.get('name')} ({p.get('role')})")

                    elif 'round_start' in str(data):
                        print(f"\n[ROUND] 라운드 {data.get('round')} 시작: {data.get('issue')}")

                    elif 'persona_speaking' in str(data):
                        name = data.get('name', '알 수 없음')
                        print(f"\n[SPEAKING] [{name}] 발언 중...")

                    elif 'persona_token' in str(data):
                        # 토큰은 출력하지 않음 (너무 많음)
                        pass

                    elif 'persona_statement_complete' in str(data):
                        name = data.get('name', '알 수 없음')
                        rag_meta = data.get('rag_metadata')

                        if rag_meta and rag_meta.get('rag_used'):
                            search_count += 1
                            print(f"   [SEARCH] 웹 검색 사용: {rag_meta.get('rag_query')}")
                            print(f"      소스: {len(rag_meta.get('sources', []))}개")

                    elif 'completed' in str(data):
                        print(f"\n[OK] 분석 완료!")
                        print(f"   Analysis ID: {data.get('analysis_id')}")
                        break

                    elif 'error' in str(data):
                        print(f"\n[ERROR] 오류 발생: {data.get('error')}")
                        break

                except json.JSONDecodeError:
                    # JSON이 아닌 데이터는 무시
                    pass

        print("\n" + "=" * 80)
        print("테스트 결과 요약")
        print("=" * 80)
        print(f"총 이벤트 수: {sum(event_counts.values())}")
        print(f"웹 검색 실행 횟수: {search_count}")
        print("\n이벤트 타입별 카운트:")
        for event_type, count in sorted(event_counts.items()):
            print(f"  - {event_type}: {count}")
        print("=" * 80)

        # 웹 검색이 실행되었는지 확인
        if search_count > 0:
            print(f"\n[OK] 페르소나별 개별 웹 검색 정상 동작! (총 {search_count}회)")
        else:
            print(f"\n[WARNING]  웹 검색이 실행되지 않았습니다.")

    except requests.exceptions.ConnectionError:
        print("[ERROR] 연결 실패: 서버가 실행 중인지 확인하세요.")
        print(f"   URL: {API_URL}")
        sys.exit(1)

    except requests.exceptions.Timeout:
        print("[ERROR] 타임아웃: 서버 응답이 너무 오래 걸립니다.")
        sys.exit(1)

    except Exception as e:
        print(f"[ERROR] 예상치 못한 오류: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    test_stream_api()
