"""
웹 검색 기능만 빠르게 테스트하는 스크립트
"""
import asyncio
from src.services.rag_service import RAGService
from src.models.personas import Persona, Message

async def test_web_search():
    print("=" * 80)
    print("웹 검색 기능 단독 테스트")
    print("=" * 80)

    # 테스트 페르소나
    test_persona = Persona(
        name="김법률",
        role="행정법 전문가",
        background="행정조사법 전문",
        expertise=["행정법", "중복조사 판별"],
        personality=["analytical"],
        beliefs=["법률 근거 중시"],
        communication_style="professional"
    )

    # 테스트 주제
    test_topic = "법인세 조사와 부가가치세 조사가 중복조사인지 판단"

    print(f"\n[TEST] 페르소나: {test_persona.name} ({test_persona.role})")
    print(f"[TEST] 검색 주제: {test_topic}")
    print("\n" + "=" * 80)

    try:
        # RAG 서비스 실행
        rag_service = RAGService()

        print("\n[SEARCH] 웹 검색 시작...")
        result = await rag_service.process(
            topic=test_topic,
            persona=test_persona,
            context=None
        )

        print("\n" + "=" * 80)
        print("검색 결과")
        print("=" * 80)

        if result.evidence:
            print(f"\n[OK] 검색 성공!")
            print(f"\n검색 쿼리: {result.query}")
            print(f"\n요약:\n{result.summary}")
            print(f"\n소스 개수: {len(result.sources)}개")

            if result.sources:
                print("\n소스 목록:")
                for i, source in enumerate(result.sources[:3], 1):  # 처음 3개만
                    if isinstance(source, dict):
                        print(f"\n{i}. {source.get('url', 'N/A')}")
                        print(f"   {source.get('content', '')[:200]}...")
                    else:
                        # 문자열인 경우
                        print(f"\n{i}. {str(source)[:200]}...")

            return True
        else:
            print("\n[WARNING] 검색 결과 없음")
            return False

    except Exception as e:
        print(f"\n[ERROR] 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_web_search())

    print("\n" + "=" * 80)
    if success:
        print("[OK] 웹 검색 기능 정상 동작!")
    else:
        print("[ERROR] 웹 검색 실패")
    print("=" * 80)
