"""전체 플로우 테스트: 분석 요청 → 결과 확인 → DB 저장 확인"""
import requests
import time
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

API_BASE = 'http://localhost:8000'

def test_full_flow():
    print("\n" + "="*60)
    print("🧪 전체 플로우 테스트 시작")
    print("="*60)
    
    # 1. 분석 요청
    print("\n📤 1단계: 분석 요청 전송")
    payload = {
        "investigation_a": """조사번호: 7-34-1
부처: 국토부
조사명: 도시개발사업 시행 관련 보고 및 검사
법령근거: 도시개발법 제74조제1항
법령내용: 지정권자나 특별자치도지사·시장·군수 또는 구청장은 도시개발사업의 시행과 관련하여 필요하다고 인정하면 시행자에게 필요한 보고를 하게 하거나 자료를 제출하도록 명할 수 있으며, 소속 공무원에게 도시개발사업에 관한 업무와 회계에 관한 사항을 검사하게 할 수 있다.""",
        
        "investigation_b": """조사번호: 7-34-2
부처: 국토부
조사명: 민관 공동 도시개발사업 시행 관련 보고 및 검사
법령근거: 도시개발법 제74조제2항
법령내용: 국토교통부장관은 도시개발사업의 관리·감독을 위하여 필요하다고 인정하면 민간참여자 선정, 시행 및 운영실태에 대하여 지정권자에게 필요한 보고를 하게 하거나 자료를 제출하도록 명할 수 있다.""",
        
        "min_rounds": 2,
        "max_rounds": 2,
        "persona_count": 3,
        "enable_openness_adjustment": True
    }
    
    response = requests.post(f"{API_BASE}/api/v1/investigations", json=payload)
    
    if response.status_code != 202:
        print(f"❌ 분석 요청 실패: {response.status_code}")
        print(response.text)
        return
    
    result = response.json()
    analysis_id = result['analysis_id']
    print(f"✅ 분석 요청 성공! ID: {analysis_id}")
    
    # 2. 상태 폴링
    print(f"\n⏳ 2단계: 분석 진행 중 (최대 10분 대기)...")
    max_attempts = 120  # 10분
    attempt = 0
    
    while attempt < max_attempts:
        time.sleep(5)
        attempt += 1
        
        status_response = requests.get(f"{API_BASE}/api/v1/investigations/{analysis_id}")
        
        if status_response.status_code != 200:
            print(f"\n❌ 상태 조회 실패: {status_response.status_code}")
            print(status_response.text)
            return
        
        status_data = status_response.json()
        
        # 디버깅: 첫 번째 응답 출력
        if attempt == 1:
            print(f"\nAPI 응답 키: {list(status_data.keys())}")
        
        current_status = status_data.get('status', 'unknown')
        print(f"   [{attempt*5}초] 상태: {current_status}", end="\r")
        
        if status_data['status'] == 'completed':
            print(f"\n✅ 분석 완료! ({attempt*5}초 소요)")
            
            # 3. 결과 상세 확인
            print("\n" + "="*60)
            print("📊 3단계: 분석 결과 확인")
            print("="*60)
            
            print(f"\n🎯 최종 판정: {status_data['final_verdict']}")
            print(f"📈 신뢰도: {status_data['consensus_status']['consensus_level']:.1%}")
            print(f"🔢 중복도 점수: (루브릭 평가는 보고서에서 확인)")
            print(f"👥 페르소나 수: {len(status_data['personas'])}")
            print(f"🗣️ 토론 라운드: {status_data['total_rounds']}회")
            
            print("\n참여 페르소나:")
            for p in status_data['personas']:
                print(f"  - {p['name']} ({p['role']})")
            
            print("\n합의 영역:")
            for area in status_data['consensus_status']['areas_of_agreement'][:3]:
                print(f"  ✅ {area}")
            
            # 4. 보고서 다운로드
            print("\n" + "="*60)
            print("📄 4단계: 보고서 다운로드")
            print("="*60)
            
            report_response = requests.get(
                f"{API_BASE}/api/v1/investigations/{analysis_id}/report?format=markdown"
            )
            
            if report_response.status_code == 200:
                report_path = f"test_report_{analysis_id[:8]}.md"
                with open(report_path, 'w', encoding='utf-8') as f:
                    f.write(report_response.text)
                print(f"✅ 보고서 저장됨: {report_path}")
                
                # 보고서에서 루브릭 섹션 확인
                if "정량적 중복도 평가" in report_response.text:
                    print("✅ 루브릭 평가 포함됨")
                    # 점수 추출
                    lines = report_response.text.split('\n')
                    for line in lines:
                        if '총점:' in line and '/100점' in line:
                            print(f"   {line.strip()}")
                            break
                else:
                    print("⚠️ 루브릭 평가 없음")
            else:
                print(f"❌ 보고서 다운로드 실패: {report_response.status_code}")
            
            # 5. DB 저장 확인
            print("\n" + "="*60)
            print("💾 5단계: DB 저장 확인")
            print("="*60)
            
            from api.database import SessionLocal
            from api.models.investigation_analysis import InvestigationAnalysis
            
            db = SessionLocal()
            try:
                db_record = db.query(InvestigationAnalysis).filter(
                    InvestigationAnalysis.id == analysis_id
                ).first()
                
                if db_record:
                    print(f"✅ DB에 저장됨")
                    print(f"   ID: {db_record.id}")
                    print(f"   상태: {db_record.status}")
                    print(f"   최종 판정: {db_record.final_verdict}")
                    print(f"   신뢰도: {db_record.confidence:.1%}")
                    print(f"   생성: {db_record.created_at}")
                    print(f"   완료: {db_record.completed_at}")
                    
                    if db_record.result_data:
                        print(f"   result_data 크기: {len(str(db_record.result_data))} bytes")
                        print(f"   personas: {len(db_record.result_data.get('personas', []))}명")
                        print(f"   rounds: {len(db_record.result_data.get('rounds', []))}회")
                        
                        # 루브릭 점수 확인 (보고서에 있음)
                        if 'report' in db_record.result_data:
                            if '정량적 중복도 평가' in db_record.result_data['report']:
                                print("   ✅ 루브릭 평가 DB에 저장됨")
                    else:
                        print("   ⚠️ result_data가 비어있음")
                else:
                    print(f"❌ DB에 레코드 없음!")
            finally:
                db.close()
            
            print("\n" + "="*60)
            print("🎉 테스트 완료!")
            print("="*60)
            return
            
        elif status_data['status'] == 'failed':
            print(f"\n❌ 분석 실패!")
            if 'result_data' in status_data and status_data['result_data']:
                print(f"에러: {status_data['result_data'].get('error', 'Unknown')}")
            return
    
    print(f"\n⏱️ 타임아웃: {max_attempts*5}초 초과")

if __name__ == "__main__":
    try:
        test_full_flow()
    except KeyboardInterrupt:
        print("\n\n사용자가 중단했습니다.")
    except Exception as e:
        print(f"\n❌ 에러 발생: {e}")
        import traceback
        traceback.print_exc()

