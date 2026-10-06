"""행정조사 중복 판별 API 엔드포인트"""
import uuid
import asyncio
import json as json_lib
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc

from api.schemas.investigation import (
    InvestigationAnalysisRequest,
    InvestigationAnalysisResponse,
    InvestigationAnalysisListResponse,
    InvestigationAnalysisListItem,
    PersonaInfo,
    ConsensusStatus,
    RoundSummary
)
from api.schemas.user import UserResponse as User
from api.dependencies import get_db, get_optional_user
from api.models.investigation_analysis import InvestigationAnalysis
from api.services.investigation_discussion_service import InvestigationDiscussionService
from api.utils.datetime_utils import utc_now

router = APIRouter(
    prefix="/api/v1/investigations",
    tags=["investigations"],
    responses={404: {"description": "Not found"}},
)


def _convert_to_dict(investigation_input) -> dict:
    """InvestigationInput 또는 raw string을 dict로 변환"""
    if isinstance(investigation_input, str):
        # raw text로 입력된 경우 그대로 dict로 변환
        return {"raw_text": investigation_input}
    else:
        # 구조화된 데이터인 경우
        return investigation_input.model_dump(exclude_none=True)


def _create_response_from_db_model(analysis: InvestigationAnalysis, include_report: bool = True) -> InvestigationAnalysisResponse:
    """DB 모델을 응답 스키마로 변환"""
    import json

    result_data = json.loads(analysis.result_data) if isinstance(analysis.result_data, str) else analysis.result_data

    consensus_data = result_data.get("consensus_status")
    consensus_status = ConsensusStatus(**consensus_data) if consensus_data else None

    # 보고서 포함 여부 결정 (빠른 응답을 위해 옵션)
    if include_report:
        report_preview = result_data.get("report", "")[:500]
    else:
        report_preview = None

    return InvestigationAnalysisResponse(
        analysis_id=analysis.id,
        created_at=analysis.created_at,
        status=analysis.status,
        investigation_a_name=analysis.investigation_a_name,
        investigation_b_name=analysis.investigation_b_name,
        personas=[PersonaInfo(**p) for p in result_data.get("personas", [])],
        total_rounds=result_data.get("total_rounds", 0),
        rounds=[RoundSummary(**r) for r in result_data.get("rounds", [])],
        final_verdict=result_data.get("final_verdict", "알 수 없음"),
        final_verdict_details=result_data.get("final_verdict_details"),
        consensus_status=consensus_status,
        rubric_scores=result_data.get("rubric_scores"),  # 루브릭 점수 추가
        report_preview=report_preview,
        report_url=f"/api/v1/investigations/{analysis.id}/report",
        report=result_data.get("report") if include_report else None  # 전체 보고서 포함
    )


def _extract_name(investigation_input) -> str:
    """조사명 추출 (raw text 또는 구조화된 데이터에서)"""
    if isinstance(investigation_input, str):
        # raw text에서 조사명 추출 시도
        import re
        match = re.search(r'조사명\s*[:：]\s*(.+?)(?:\n|$)', investigation_input)
        if match:
            return match.group(1).strip()
        return "행정조사 (자동추출)"
    else:
        return investigation_input.name


@router.post("/stream", summary="중복 판별 분석 (SSE 스트리밍)")
async def analyze_investigations_stream(
    request: InvestigationAnalysisRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user)
):
    """
    두 행정조사의 중복 여부를 실시간 스트리밍으로 분석합니다.
    
    **입력 방식**:
    - **간편**: 엑셀에서 복사한 전체 텍스트를 그대로 입력
    - **상세**: 구조화된 필드별 데이터 입력
    
    **프로세스**:
    1. 페르소나 자동 생성
    2. 사전 중복 판별
    3. 토론 진행 (3~10 라운드)
    4. 최종 판정 및 보고서 생성
    
    **응답**: Server-Sent Events (SSE) 스트림
    """
    from api.schemas.message import SSEEvent
    from datetime import datetime
    
    user_id = current_user.id if current_user else "guest"
    analysis_id = str(uuid.uuid4())
    
    # 조사명 추출
    investigation_a_name = _extract_name(request.investigation_a)
    investigation_b_name = _extract_name(request.investigation_b)
    
    async def event_generator():
        event_id = 0
        
        # Thread-safe 큐 생성
        import queue as thread_queue
        sync_queue = thread_queue.Queue()
        
        # 이벤트 콜백 함수 (thread-safe)
        def emit_event(event_type: str, data: dict):
            nonlocal event_id
            event_id += 1
            event = SSEEvent(
                id=str(event_id),
                event=event_type,
                data=data
            )
            try:
                sync_queue.put(event, block=False)
            except Exception as e:
                print(f"Failed to emit event {event_type}: {e}")
        
        # 시작 이벤트
        yield SSEEvent(
            id="0",
            event="analysis_started",
            data={
                "analysis_id": analysis_id,
                "investigation_a": investigation_a_name,
                "investigation_b": investigation_b_name,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
        ).to_sse()
        
        # 백그라운드에서 분석 실행
        import threading
        from api.database import SessionLocal
        
        def run_analysis():
            # 새로운 DB 세션 생성 (스레드 안전성)
            db_thread = SessionLocal()
            try:
                import asyncio
                from src.models.personas import LLMProvider
                from api.services.investigation_discussion_service import InvestigationDiscussionService
                
                # TAVILY_API_KEY가 있으면 웹 검색 활성화
                import os
                tavily_key = os.getenv("TAVILY_API_KEY")
                enable_web_search = bool(tavily_key and tavily_key.strip())

                service = InvestigationDiscussionService(
                    llm_provider=LLMProvider.OPENAI,
                    model="gpt-4o-mini",
                    min_rounds=request.min_rounds or 3,
                    max_rounds=request.max_rounds or 10,
                    event_callback=emit_event,
                    enable_openness_adjustment=enable_web_search  # TAVILY_API_KEY 기반 자동 설정
                )
                
                # async 함수 실행
                result = asyncio.run(service.conduct_discussion(
                    investigation_a=_convert_to_dict(request.investigation_a),
                    investigation_b=_convert_to_dict(request.investigation_b),
                    num_personas=request.persona_count,
                    discussion_id=analysis_id
                ))
                
                # 완료 이벤트
                emit_event("analysis_complete", {
                    "analysis_id": analysis_id,
                    "verdict": result.final_verdict,
                    "total_rounds": result.total_rounds,
                    "consensus_level": result.consensus_status.consensus_level if result.consensus_status else 0,
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                })
                
                # DB 저장 (스레드 안전한 세션 사용)
                import json as json_lib
                analysis = InvestigationAnalysis(
                    id=analysis_id,
                    user_id=user_id,
                    investigation_a_name=investigation_a_name,
                    investigation_b_name=investigation_b_name,
                    investigation_a_data=_convert_to_dict(request.investigation_a),
                    investigation_b_data=_convert_to_dict(request.investigation_b),
                    status="completed",
                    result_data=json_lib.dumps(result.model_dump(mode='json'), ensure_ascii=False),
                    final_verdict=result.final_verdict,
                    confidence=result.consensus_status.consensus_level if result.consensus_status else 0.0,
                    completed_at=utc_now(),
                    created_at=utc_now()
                )
                db_thread.add(analysis)
                db_thread.commit()
                
            except Exception as e:
                import traceback
                error_msg = f"{str(e)}\n{traceback.format_exc()}"
                print(f"[ERROR] Analysis error: {error_msg}")
                emit_event("error", {
                    "message": str(e),
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                })
            finally:
                db_thread.close()
        
        # 분석 스레드 시작
        thread = threading.Thread(target=run_analysis, daemon=True)
        thread.start()
        
        # 이벤트 스트리밍 (thread-safe queue에서 가져오기)
        import asyncio
        while True:
            try:
                # Non-blocking으로 큐에서 이벤트 가져오기
                try:
                    event = sync_queue.get(block=False)
                    yield event.to_sse()
                    
                    # 완료 또는 에러 시 종료
                    if event.event in ["analysis_complete", "error"]:
                        break
                except thread_queue.Empty:
                    # 큐가 비어있으면 잠시 대기 후 하트비트
                    await asyncio.sleep(0.5)
                    yield ": heartbeat\n\n"
                    
                    # 스레드가 종료되었는지 확인
                    if not thread.is_alive():
                        # 마지막 이벤트 확인
                        try:
                            while True:
                                event = sync_queue.get(block=False)
                                yield event.to_sse()
                        except thread_queue.Empty:
                            break
                    continue
            except Exception as e:
                print(f"Stream error: {e}")
                yield SSEEvent(id=str(event_id + 1), event="error", data={"message": str(e)}).to_sse()
                break
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.post("", response_model=InvestigationAnalysisResponse, status_code=202)
async def analyze_investigations(
    request: InvestigationAnalysisRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user)
):
    """
    두 행정조사의 중복 여부를 분석합니다. (백그라운드 처리)
    
    **입력 방식**:
    - **간편**: 엑셀에서 복사한 전체 텍스트를 그대로 입력
    - **상세**: 구조화된 필드별 데이터 입력
    
    **프로세스**:
    1. 페르소나 자동 생성
    2. 사전 중복 판별
    3. 토론 진행 (3~10 라운드)
    4. 최종 판정 및 보고서 생성
    
    **시간**: 약 2~5분 소요 (토론 라운드 수에 따라 다름)
    """
    user_id = current_user.id if current_user else "guest"
    
    # 분석 ID 생성
    analysis_id = str(uuid.uuid4())
    
    # 조사명 추출
    investigation_a_name = _extract_name(request.investigation_a)
    investigation_b_name = _extract_name(request.investigation_b)
    
    # DB에 초기 레코드 생성
    analysis = InvestigationAnalysis(
        id=analysis_id,
        user_id=user_id,
        investigation_a_name=investigation_a_name,
        investigation_b_name=investigation_b_name,
        investigation_a_data=_convert_to_dict(request.investigation_a),
        investigation_b_data=_convert_to_dict(request.investigation_b),
        status="processing",
        created_at=utc_now()
    )
    db.add(analysis)
    db.commit()
    
    # 백그라운드에서 분석 실행
    background_tasks.add_task(
        _run_analysis_in_background,
        analysis_id=analysis_id,
        investigation_a=_convert_to_dict(request.investigation_a),
        investigation_b=_convert_to_dict(request.investigation_b),
        min_rounds=request.min_rounds or 3,
        max_rounds=request.max_rounds or 10,
        persona_count=request.persona_count,
        skip_discussion=request.skip_discussion or False,
        enable_openness_adjustment=request.enable_openness_adjustment or False
    )
    
    # 즉시 응답 (상태: processing)
    return InvestigationAnalysisResponse(
        analysis_id=analysis_id,
        created_at=analysis.created_at,
        status="processing",
        investigation_a_name=investigation_a_name,
        investigation_b_name=investigation_b_name,
        personas=[],
        total_rounds=0,
        rounds=[],
        final_verdict="분석 진행 중",
        final_verdict_details="페르소나 생성 및 토론을 진행하고 있습니다.",
        consensus_status=None,
        report_preview="분석이 진행 중입니다. 잠시 후 다시 조회해 주세요.",
        report_url=None
    )


async def _run_analysis_in_background(
    analysis_id: str,
    investigation_a: dict,
    investigation_b: dict,
    min_rounds: int,
    max_rounds: int,
    persona_count: Optional[int],
    skip_discussion: bool,  # noqa: F841
    enable_openness_adjustment: bool = False
):
    """백그라운드에서 실제 분석 수행"""
    from api.database import SessionLocal
    import traceback
    
    db = SessionLocal()
    
    try:
        print(f"\n🔄 [분석 {analysis_id}] 백그라운드 작업 시작")
        
        # 서비스 초기화
        service = InvestigationDiscussionService(
            min_rounds=min_rounds,
            max_rounds=max_rounds,
            enable_openness_adjustment=enable_openness_adjustment
        )
        
        print(f"[분석 {analysis_id}] 토론 시작...")
        
        # 분석 실행
        result = await service.conduct_discussion(
            investigation_a=investigation_a,
            investigation_b=investigation_b,
            num_personas=persona_count
        )
        
        print(f"[분석 {analysis_id}] 토론 완료! 결과 저장 중...")
        
        # 결과를 JSON으로 변환
        result_data = {
            "personas": [
                {
                    "name": p.name,
                    "role": p.role,
                    "expertise": p.expertise,
                    "perspective": p.perspective,
                    "style": p.style,
                    "background": p.background,
                    "key_concerns": p.key_concerns
                }
                for p in result.personas
            ],
            "total_rounds": result.total_rounds,
            "rounds": [
                {
                    "round_number": r.round_number,
                    "phase": r.phase,
                    "key_points": r.key_points,
                    "summary": r.summary if hasattr(r, 'summary') else None,
                    # 토론 원문 추가
                    "messages": [
                        {
                            "speaker": m.speaker,
                            "content": m.content,
                            "type": m.type if hasattr(m, 'type') else None,
                            "round_number": m.round_number if hasattr(m, 'round_number') else r.round_number
                        }
                        for m in r.messages
                    ] if hasattr(r, 'messages') and r.messages else []
                }
                for r in result.rounds
            ],
            "final_verdict": result.final_verdict,
            "final_verdict_details": result.final_verdict_details,
            "consensus_status": {
                "has_consensus": result.consensus_status.has_consensus,
                "consensus_level": result.consensus_status.consensus_level,
                "areas_of_agreement": result.consensus_status.areas_of_agreement,
                "areas_of_disagreement": result.consensus_status.areas_of_disagreement,
                "key_arguments": result.consensus_status.key_arguments
            } if result.consensus_status else None,
            "rubric_scores": result.rubric_scores,
            "report": result.report
        }
        
        print(f"[분석 {analysis_id}] 저장할 데이터:")
        print(f"  - 페르소나: {len(result_data['personas'])}명")
        print(f"  - 라운드: {len(result_data['rounds'])}개")
        total_messages = sum(len(r.get('messages', [])) for r in result_data['rounds'])
        print(f"  - 토론 메시지: {total_messages}개")
        print(f"  - 보고서: {len(result_data.get('report', ''))} bytes")
        
        # DB 업데이트
        print(f"[분석 {analysis_id}] DB에서 분석 레코드 조회 중...")
        analysis = db.query(InvestigationAnalysis).filter(
            InvestigationAnalysis.id == analysis_id
        ).first()
        
        if analysis:
            print(f"[분석 {analysis_id}] 분석 레코드 발견, 업데이트 중...")
            analysis.status = "completed"
            # JSON을 한글 그대로 저장 (ensure_ascii=False)
            import json as json_module
            analysis.result_data = json_module.loads(
                json_module.dumps(result_data, ensure_ascii=False)
            )
            analysis.final_verdict = result.final_verdict
            analysis.confidence = result.consensus_status.consensus_level if result.consensus_status else 0.0
            analysis.total_rounds = result.total_rounds  # 빠른 조회를 위해 별도 컬럼에 저장
            analysis.completed_at = utc_now()
            db.commit()
            print(f"✅ [분석 {analysis_id}] DB 저장 완료!")
        else:
            print(f"❌ [분석 {analysis_id}] 분석 레코드를 찾을 수 없음!")
    
    except Exception as e:
        # 에러 처리
        error_message = f"분석 중 오류 발생: {str(e)}"
        error_detail = traceback.format_exc()
        
        print(f"\n❌ [분석 {analysis_id}] 에러 발생!")
        print(f"   에러 메시지: {error_message}")
        print(f"   상세:\n{error_detail}")
        
        analysis = db.query(InvestigationAnalysis).filter(
            InvestigationAnalysis.id == analysis_id
        ).first()
        
        if analysis:
            analysis.status = "failed"
            analysis.result_data = {
                "error": error_message,
                "detail": error_detail
            }
            db.commit()
    
    finally:
        db.close()


@router.get("/{analysis_id}", response_model=InvestigationAnalysisResponse)
async def get_analysis_result(
    analysis_id: str,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user)
):
    """
    분석 결과를 조회합니다.
    
    **상태**:
    - `processing`: 분석 진행 중
    - `completed`: 분석 완료
    - `failed`: 분석 실패
    """
    user_id = current_user.id if current_user else "guest"
    
    analysis = db.query(InvestigationAnalysis).filter(
        InvestigationAnalysis.id == analysis_id
    ).first()
    
    if not analysis:
        raise HTTPException(status_code=404, detail="분석 결과를 찾을 수 없습니다.")
    
    # 게스트는 자신이 요청한 분석만 조회 가능 (보안 강화하려면)
    # if analysis.user_id != user_id and user_id == "guest":
    #     raise HTTPException(status_code=403, detail="접근 권한이 없습니다.")
    
    # processing 상태일 때는 최소 정보만 반환 (빠른 응답)
    if analysis.status == "processing":
        return InvestigationAnalysisResponse(
            analysis_id=analysis.id,
            created_at=analysis.created_at,
            status="processing",
            investigation_a_name=analysis.investigation_a_name,
            investigation_b_name=analysis.investigation_b_name,
            personas=[],
            total_rounds=0,
            rounds=[],
            final_verdict="분석 진행 중",
            final_verdict_details="페르소나 생성 및 토론을 진행하고 있습니다.",
            consensus_status=None,
            report_preview="분석이 진행 중입니다. 잠시 후 다시 조회해 주세요.",
            report_url=None
        )
    
    elif analysis.status == "failed":
        raise HTTPException(
            status_code=500,
            detail=f"분석 실패: {analysis.result_data.get('error', '알 수 없는 오류')}"
        )
    
    return _create_response_from_db_model(analysis)


@router.get("/{analysis_id}/report", response_class=Response)
async def get_analysis_report(
    analysis_id: str,
    report_format: str = Query("markdown", regex="^(markdown|md|html|pdf)$", alias="format"),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user)  # noqa: F841
):
    """
    분석 보고서를 다운로드합니다.
    
    **형식**:
    - `markdown` 또는 `md`: Markdown 형식 (기본)
    - `html`: HTML 형식 (향후 지원)
    - `pdf`: PDF 형식 (향후 지원)
    """
    analysis = db.query(InvestigationAnalysis).filter(
        InvestigationAnalysis.id == analysis_id
    ).first()
    
    if not analysis:
        raise HTTPException(status_code=404, detail="분석 결과를 찾을 수 없습니다.")
    
    if analysis.status != "completed":
        raise HTTPException(status_code=400, detail="분석이 완료되지 않았습니다.")
    
    import json
    result_data = json.loads(analysis.result_data) if isinstance(analysis.result_data, str) else analysis.result_data
    report = result_data.get("report", "")
    
    if not report:
        raise HTTPException(status_code=404, detail="보고서를 찾을 수 없습니다.")
    
    # Markdown 형식
    if report_format in ["markdown", "md"]:
        return Response(
            content=report,
            media_type="text/markdown",
            headers={
                "Content-Disposition": f"attachment; filename=report_{analysis_id}.md"
            }
        )
    
    # TODO: HTML, PDF 형식은 향후 구현
    elif report_format == "html":
        raise HTTPException(status_code=501, detail="HTML 형식은 아직 지원하지 않습니다.")
    elif report_format == "pdf":
        raise HTTPException(status_code=501, detail="PDF 형식은 아직 지원하지 않습니다.")


@router.get("", response_model=InvestigationAnalysisListResponse)
async def list_analyses(
    page: int = Query(1, ge=1, description="페이지 번호"),
    page_size: int = Query(20, ge=1, le=100, description="페이지 크기"),
    status: Optional[str] = Query(None, regex="^(processing|completed|failed)$", description="상태 필터"),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user)  # noqa: F841
):
    """
    분석 목록을 조회합니다.
    """
    
    # 게스트는 자신의 분석만 조회
    user_id = current_user.id if current_user else "guest"

    # 🚀 성능 최적화: 필요한 컬럼만 SELECT (큰 JSON 컬럼 제외)
    query = db.query(
        InvestigationAnalysis.id,
        InvestigationAnalysis.created_at,
        InvestigationAnalysis.investigation_a_name,
        InvestigationAnalysis.investigation_b_name,
        InvestigationAnalysis.final_verdict,
        InvestigationAnalysis.confidence,
        InvestigationAnalysis.total_rounds,
        InvestigationAnalysis.status
    )

    if user_id == "guest":
        query = query.filter(InvestigationAnalysis.user_id == user_id)

    # 상태 필터
    if status:
        query = query.filter(InvestigationAnalysis.status == status)

    # 전체 개수
    total = query.count()

    # 페이징
    offset = (page - 1) * page_size
    results = query.order_by(desc(InvestigationAnalysis.created_at)).offset(offset).limit(page_size).all()

    # 응답 생성 (튜플 결과를 언팩)
    items = [
        InvestigationAnalysisListItem(
            analysis_id=row[0],  # id
            created_at=row[1],  # created_at
            investigation_a_name=row[2],  # investigation_a_name
            investigation_b_name=row[3],  # investigation_b_name
            final_verdict=row[4] or "분석 진행 중",  # final_verdict
            confidence=row[5] if row[5] else 0.0,  # confidence
            total_rounds=row[6] if row[6] else 0  # total_rounds
        )
        for row in results
    ]
    
    return InvestigationAnalysisListResponse(
        total=total,
        items=items,
        page=page,
        page_size=page_size
    )


@router.delete("/{analysis_id}")
async def delete_analysis(
    analysis_id: str,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user)
):
    """
    분석 결과를 삭제합니다.
    """
    user_id = current_user.id if current_user else "guest"
    
    analysis = db.query(InvestigationAnalysis).filter(
        InvestigationAnalysis.id == analysis_id
    ).first()
    
    if not analysis:
        raise HTTPException(status_code=404, detail="분석 결과를 찾을 수 없습니다.")
    
    # 권한 확인 (자신의 분석만 삭제 가능)
    if analysis.user_id != user_id:
        raise HTTPException(status_code=403, detail="삭제 권한이 없습니다.")
    
    db.delete(analysis)
    db.commit()
    
    return {"message": "분석 결과가 삭제되었습니다.", "analysis_id": analysis_id}


@router.get("/{analysis_id}/stream")
async def stream_investigation_analysis(
    analysis_id: str,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user)
):
    """
    행정조사 분석 실시간 스트리밍 (SSE)
    
    실시간으로 분석 진행 상황을 스트리밍합니다.
    """
    user_id = current_user.id if current_user else "guest"
    
    # 분석 조회
    analysis = db.query(InvestigationAnalysis).filter(
        InvestigationAnalysis.id == analysis_id
    ).first()
    
    if not analysis:
        raise HTTPException(status_code=404, detail="분석을 찾을 수 없습니다.")
    
    # 권한 확인
    if analysis.user_id != user_id:
        raise HTTPException(status_code=403, detail="조회 권한이 없습니다.")
    
    async def event_generator():
        """SSE 이벤트 생성기"""
        try:
            # 초기 상태 전송
            yield f"data: {json_lib.dumps({'type': 'init', 'status': analysis.status})}\n\n"
            
            # 이미 완료된 경우
            if analysis.status in ["completed", "failed"]:
                yield f"data: {json_lib.dumps({'type': 'done', 'status': analysis.status})}\n\n"
                return
            
            # 진행 중인 경우 주기적으로 상태 확인
            while True:
                await asyncio.sleep(1)
                
                # DB에서 최신 상태 조회
                db.refresh(analysis)
                
                # 상태 변경 이벤트 전송
                yield f"data: {json_lib.dumps({'type': 'status', 'status': analysis.status})}\n\n"
                
                # 완료되면 종료
                if analysis.status in ["completed", "failed"]:
                    result_data = json_lib.loads(analysis.result_data) if analysis.result_data else {}
                    yield f"data: {json_lib.dumps({'type': 'done', 'status': analysis.status, 'result': result_data})}\n\n"
                    break
                    
        except asyncio.CancelledError:
            yield f"data: {json_lib.dumps({'type': 'error', 'message': 'Stream cancelled'})}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

