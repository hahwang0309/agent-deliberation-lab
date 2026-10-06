"""배치 분석 라우터"""
import uuid
import json as json_lib
import traceback
import asyncio
import io
import zipfile
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc

from api.database import get_db
from api.models.user import User
from api.models.batch_analysis import BatchAnalysis, BatchAnalysisItem
from api.models.investigation_analysis import InvestigationAnalysis
from api.schemas.batch import (
    BatchAnalysisCreateRequest,
    BatchAnalysisInfo,
    BatchAnalysisDetail,
    BatchAnalysisListResponse,
    BatchAnalysisItemInfo
)
from api.routers.users import get_optional_user
from api.utils.datetime_utils import utc_now
from src.models.personas import LLMProvider
from api.services.investigation_discussion_service import InvestigationDiscussionService

router = APIRouter(prefix="/api/v1/batch-analyses", tags=["batch-analyses"])


def _extract_name(investigation_data) -> str:
    """조사명 추출"""
    if isinstance(investigation_data, dict):
        return investigation_data.get("name", "행정조사")
    elif isinstance(investigation_data, str):
        # raw text에서 조사명 추출 시도
        import re
        match = re.search(r'조사명\s*[:：]\s*(.+?)(?:\n|$)', investigation_data)
        if match:
            return match.group(1).strip()
        return "행정조사 (자동추출)"
    return "행정조사"


def _convert_to_dict(investigation_input) -> dict:
    """텍스트 또는 dict를 dict로 변환"""
    if isinstance(investigation_input, str):
        # raw text로 입력된 경우 그대로 dict로 변환
        return {"raw_text": investigation_input}
    else:
        # 이미 dict인 경우
        return investigation_input


async def _run_batch_analysis(batch_id: str):
    """배치 분석 실행 (백그라운드)"""
    from api.database import SessionLocal
    db = SessionLocal()
    
    try:
        batch = db.query(BatchAnalysis).filter(BatchAnalysis.id == batch_id).first()
        if not batch:
            print(f"❌ 배치 {batch_id}를 찾을 수 없습니다.")
            return
        
        # 상태를 processing으로 변경
        batch.status = "processing"
        batch.started_at = utc_now()
        db.commit()
        
        print(f"[배치 {batch_id}] 분석 시작: {batch.total_count}개 항목")
        
        # pending 상태인 항목만 가져오기
        items = db.query(BatchAnalysisItem).filter(
            BatchAnalysisItem.batch_id == batch_id,
            BatchAnalysisItem.status == "pending"
        ).order_by(BatchAnalysisItem.sequence).all()
        
        config = batch.config or {}
        
        for item in items:
            # 배치 상태 확인 (paused이면 중단)
            db.refresh(batch)
            if batch.status == "paused":
                print(f"[배치 {batch_id}] 일시정지됨")
                break
            
            try:
                # 항목 상태 업데이트
                item.status = "processing"
                item.started_at = utc_now()
                db.commit()
                
                print(f"[배치 {batch_id}] [{item.sequence}/{batch.total_count}] {item.investigation_a_name} vs {item.investigation_b_name}")
                
                # InvestigationAnalysis 생성
                analysis_id = str(uuid.uuid4())
                analysis = InvestigationAnalysis(
                    id=analysis_id,
                    user_id=batch.user_id,
                    investigation_a_name=item.investigation_a_name,
                    investigation_b_name=item.investigation_b_name,
                    investigation_a_data=item.investigation_a_data,
                    investigation_b_data=item.investigation_b_data,
                    status="processing",
                    created_at=utc_now()
                )
                db.add(analysis)
                db.commit()
                
                # 분석 실행
                service = InvestigationDiscussionService(
                    llm_provider=LLMProvider.OPENAI,
                    model=config.get("model", "gpt-4o-mini"),
                    min_rounds=config.get("min_rounds", 3),
                    max_rounds=config.get("max_rounds", 10),
                    enable_openness_adjustment=config.get("enable_openness_adjustment", False)
                )
                
                result = await service.conduct_discussion(
                    investigation_a=item.investigation_a_data,
                    investigation_b=item.investigation_b_data,
                    num_personas=config.get("persona_count"),
                    discussion_id=analysis_id
                )
                
                # result_data 생성
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
                
                # InvestigationAnalysis 업데이트
                analysis.status = "completed"
                analysis.result_data = json_lib.loads(json_lib.dumps(result_data, ensure_ascii=False))
                analysis.final_verdict = result.final_verdict
                analysis.confidence = result.consensus_status.consensus_level if result.consensus_status else 0.0
                analysis.completed_at = utc_now()
                
                # BatchAnalysisItem 업데이트
                item.status = "completed"
                item.analysis_id = analysis_id
                item.final_verdict = result.final_verdict
                item.confidence = result.consensus_status.consensus_level if result.consensus_status else 0.0
                item.completed_at = utc_now()
                
                batch.completed_count += 1
                db.commit()
                
                print(f"✅ [배치 {batch_id}] [{item.sequence}] 완료: {result.final_verdict}")
                
            except Exception as e:
                error_msg = f"{str(e)}"
                print(f"❌ [배치 {batch_id}] [{item.sequence}] 실패: {error_msg}")
                
                item.status = "failed"
                item.error_message = error_msg[:500]
                item.completed_at = utc_now()
                batch.failed_count += 1
                db.commit()
        
        # 배치 완료 확인
        db.refresh(batch)
        if batch.completed_count + batch.failed_count >= batch.total_count:
            batch.status = "completed"
            batch.completed_at = utc_now()
            db.commit()
            print(f"✅ [배치 {batch_id}] 전체 완료: {batch.completed_count}개 성공, {batch.failed_count}개 실패")
        elif batch.status == "processing":
            # 중간에 멈춘 경우
            batch.status = "paused"
            batch.paused_at = utc_now()
            db.commit()
            print(f"⏸️ [배치 {batch_id}] 일시정지: {batch.completed_count}/{batch.total_count}")
    
    except Exception as e:
        print(f"❌ [배치 {batch_id}] 치명적 오류: {str(e)}\n{traceback.format_exc()}")
        batch.status = "failed"
        db.commit()
    
    finally:
        db.close()


@router.post("", response_model=BatchAnalysisInfo)
async def create_batch_analysis(
    request: BatchAnalysisCreateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user)
):
    """배치 분석 생성"""
    user_id = current_user.id if current_user else "guest"
    batch_id = str(uuid.uuid4())
    
    # 배치 생성
    batch = BatchAnalysis(
        id=batch_id,
        user_id=user_id,
        name=request.name,
        description=request.description,
        status="pending",
        total_count=len(request.items),
        completed_count=0,
        failed_count=0,
        config={
            "persona_count": request.persona_count,
            "min_rounds": request.min_rounds,
            "max_rounds": request.max_rounds,
            "enable_openness_adjustment": request.enable_openness_adjustment
        },
        created_at=utc_now()
    )
    db.add(batch)
    
    # 항목 생성
    for idx, item_input in enumerate(request.items, start=1):
        # 텍스트 또는 dict를 dict로 변환
        inv_a_dict = _convert_to_dict(item_input.investigation_a)
        inv_b_dict = _convert_to_dict(item_input.investigation_b)
        
        item = BatchAnalysisItem(
            id=str(uuid.uuid4()),
            batch_id=batch_id,
            sequence=idx,
            item_name=item_input.item_name,
            investigation_a_data=inv_a_dict,
            investigation_b_data=inv_b_dict,
            investigation_a_name=_extract_name(item_input.investigation_a),
            investigation_b_name=_extract_name(item_input.investigation_b),
            status="pending",
            created_at=utc_now()
        )
        db.add(item)
    
    db.commit()
    
    # 백그라운드에서 분석 시작
    background_tasks.add_task(_run_batch_analysis, batch_id)
    
    return BatchAnalysisInfo(
        id=batch.id,
        name=batch.name,
        description=batch.description,
        status=batch.status,
        total_count=batch.total_count,
        completed_count=batch.completed_count,
        failed_count=batch.failed_count,
        progress_percentage=batch.progress_percentage,
        created_at=batch.created_at,
        started_at=batch.started_at,
        completed_at=batch.completed_at
    )


@router.get("", response_model=BatchAnalysisListResponse)
async def list_batch_analyses(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user)
):
    """배치 분석 목록 조회"""
    user_id = current_user.id if current_user else "guest"
    
    query = db.query(BatchAnalysis).filter(BatchAnalysis.user_id == user_id)
    total = query.count()
    
    offset = (page - 1) * page_size
    batches = query.order_by(desc(BatchAnalysis.created_at)).offset(offset).limit(page_size).all()
    
    items = [
        BatchAnalysisInfo(
            id=b.id,
            name=b.name,
            description=b.description,
            status=b.status,
            total_count=b.total_count,
            completed_count=b.completed_count,
            failed_count=b.failed_count,
            progress_percentage=b.progress_percentage,
            created_at=b.created_at,
            started_at=b.started_at,
            completed_at=b.completed_at
        )
        for b in batches
    ]
    
    return BatchAnalysisListResponse(
        total=total,
        items=items,
        page=page,
        page_size=page_size
    )


@router.get("/{batch_id}", response_model=BatchAnalysisDetail)
async def get_batch_analysis(
    batch_id: str,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user)
):
    """배치 분석 상세 조회"""
    user_id = current_user.id if current_user else "guest"
    
    batch = db.query(BatchAnalysis).filter(
        BatchAnalysis.id == batch_id,
        BatchAnalysis.user_id == user_id
    ).first()
    
    if not batch:
        raise HTTPException(status_code=404, detail="배치를 찾을 수 없습니다.")
    
    items = [
        BatchAnalysisItemInfo(
            id=item.id,
            sequence=item.sequence,
            item_name=item.item_name,
            investigation_a_name=item.investigation_a_name,
            investigation_b_name=item.investigation_b_name,
            status=item.status,
            analysis_id=item.analysis_id,
            final_verdict=item.final_verdict,
            confidence=item.confidence,
            error_message=item.error_message,
            created_at=item.created_at,
            started_at=item.started_at,
            completed_at=item.completed_at
        )
        for item in batch.items
    ]
    
    return BatchAnalysisDetail(
        id=batch.id,
        name=batch.name,
        description=batch.description,
        status=batch.status,
        total_count=batch.total_count,
        completed_count=batch.completed_count,
        failed_count=batch.failed_count,
        progress_percentage=batch.progress_percentage,
        config=batch.config,
        items=items,
        created_at=batch.created_at,
        started_at=batch.started_at,
        paused_at=batch.paused_at,
        completed_at=batch.completed_at
    )


@router.post("/{batch_id}/resume")
async def resume_batch_analysis(
    batch_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user)
):
    """배치 분석 재개"""
    user_id = current_user.id if current_user else "guest"
    
    batch = db.query(BatchAnalysis).filter(
        BatchAnalysis.id == batch_id,
        BatchAnalysis.user_id == user_id
    ).first()
    
    if not batch:
        raise HTTPException(status_code=404, detail="배치를 찾을 수 없습니다.")
    
    if batch.status not in ["paused", "failed"]:
        raise HTTPException(status_code=400, detail=f"재개할 수 없는 상태입니다: {batch.status}")
    
    batch.status = "pending"
    batch.paused_at = None
    db.commit()
    
    # 백그라운드에서 분석 재개
    background_tasks.add_task(_run_batch_analysis, batch_id)
    
    return {"message": "배치 분석이 재개되었습니다.", "batch_id": batch_id}


@router.post("/{batch_id}/pause")
async def pause_batch_analysis(
    batch_id: str,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user)
):
    """배치 분석 일시정지"""
    user_id = current_user.id if current_user else "guest"
    
    batch = db.query(BatchAnalysis).filter(
        BatchAnalysis.id == batch_id,
        BatchAnalysis.user_id == user_id
    ).first()
    
    if not batch:
        raise HTTPException(status_code=404, detail="배치를 찾을 수 없습니다.")
    
    if batch.status != "processing":
        raise HTTPException(status_code=400, detail=f"일시정지할 수 없는 상태입니다: {batch.status}")
    
    batch.status = "paused"
    batch.paused_at = utc_now()
    db.commit()
    
    return {"message": "배치 분석이 일시정지되었습니다.", "batch_id": batch_id}


@router.delete("/{batch_id}")
async def delete_batch_analysis(
    batch_id: str,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user)
):
    """배치 분석 삭제"""
    user_id = current_user.id if current_user else "guest"
    
    batch = db.query(BatchAnalysis).filter(
        BatchAnalysis.id == batch_id,
        BatchAnalysis.user_id == user_id
    ).first()
    
    if not batch:
        raise HTTPException(status_code=404, detail="배치를 찾을 수 없습니다.")
    
    if batch.status == "processing":
        raise HTTPException(status_code=400, detail="진행 중인 배치는 삭제할 수 없습니다. 먼저 일시정지하세요.")
    
    db.delete(batch)
    db.commit()
    
    return {"message": "배치 분석이 삭제되었습니다.", "batch_id": batch_id}


@router.get("/{batch_id}/download-reports")
async def download_batch_reports(
    batch_id: str,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user)
):
    """배치의 모든 보고서를 ZIP 파일로 다운로드"""
    user_id = current_user.id if current_user else "guest"
    
    batch = db.query(BatchAnalysis).filter(
        BatchAnalysis.id == batch_id,
        BatchAnalysis.user_id == user_id
    ).first()
    
    if not batch:
        raise HTTPException(status_code=404, detail="배치를 찾을 수 없습니다.")
    
    # 완료된 항목만 가져오기
    items = db.query(BatchAnalysisItem).filter(
        BatchAnalysisItem.batch_id == batch_id,
        BatchAnalysisItem.status == "completed",
        BatchAnalysisItem.analysis_id.isnot(None)
    ).order_by(BatchAnalysisItem.sequence).all()
    
    if not items:
        raise HTTPException(status_code=404, detail="다운로드할 보고서가 없습니다.")
    
    # ZIP 파일 생성
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        # 배치 요약 파일 추가
        summary_lines = [
            f"# 배치 분석 보고서 요약\n\n",
            f"**배치 이름**: {batch.name}\n",
            f"**설명**: {batch.description or 'N/A'}\n",
            f"**생성일**: {batch.created_at}\n",
            f"**완료일**: {batch.completed_at or 'N/A'}\n",
            f"**전체 항목**: {batch.total_count}개\n",
            f"**완료**: {batch.completed_count}개\n",
            f"**실패**: {batch.failed_count}개\n\n",
            f"---\n\n",
            f"## 분석 결과 목록\n\n"
        ]
        
        for item in items:
            summary_lines.append(
                f"{item.sequence}. **{item.investigation_a_name}** vs **{item.investigation_b_name}**: "
                f"{item.final_verdict} (신뢰도: {(item.confidence or 0) * 100:.1f}%)\n"
            )
        
        zip_file.writestr("_SUMMARY.md", "".join(summary_lines))
        
        # 각 항목의 보고서 추가
        for item in items:
            analysis = db.query(InvestigationAnalysis).filter(
                InvestigationAnalysis.id == item.analysis_id
            ).first()
            
            if analysis and analysis.result_data:
                result_data = json_lib.loads(analysis.result_data) if isinstance(analysis.result_data, str) else analysis.result_data
                report = result_data.get("report", "")
                
                if report:
                    # 파일명: {순서}_{조사A명}_vs_{조사B명}.md
                    safe_name_a = item.investigation_a_name.replace("/", "_").replace("\\", "_")[:50]
                    safe_name_b = item.investigation_b_name.replace("/", "_").replace("\\", "_")[:50]
                    filename = f"{item.sequence:03d}_{safe_name_a}_vs_{safe_name_b}.md"
                    
                    zip_file.writestr(filename, report)
    
    zip_buffer.seek(0)
    
    return StreamingResponse(
        io.BytesIO(zip_buffer.getvalue()),
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename=batch_{batch.name}_{batch_id[:8]}_reports.zip"
        }
    )

