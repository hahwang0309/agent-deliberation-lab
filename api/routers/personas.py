"""
페르소나 API 라우터
"""
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException, status
from pydantic import ValidationError

from api.schemas.persona import (
    GeneratePersonasRequest,
    GeneratePersonasResponse,
    PersonaTemplate,
    PersonaTemplateListResponse,
)
from src.generators.persona_generator import PersonaGenerator

router = APIRouter(prefix="/api/v1/personas", tags=["Personas"])

TEMPLATES_PATH = Path(__file__).resolve().parents[2] / "config" / "persona_templates.yaml"


@router.get("/templates", response_model=PersonaTemplateListResponse, summary="페르소나 템플릿 목록")
def get_persona_templates():
    data = yaml.safe_load(TEMPLATES_PATH.read_text(encoding="utf-8")) or {}
    return PersonaTemplateListResponse(
        templates=[PersonaTemplate(id=template_id, **fields) for template_id, fields in data.items()]
    )


@router.post("/generate", response_model=GeneratePersonasResponse, summary="주제 기반 페르소나 자동 생성")
async def generate_personas(request: GeneratePersonasRequest):
    try:
        personas = await PersonaGenerator().generate_multiple_personas(
            request.topic, count=request.count, language=request.language
        )
    except ValidationError as e:  # LLM 출력이 페르소나 형식에 맞지 않음 (ValueError의 하위 클래스라 먼저 처리)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY,
                            detail={"error": {"code": "LLM_INVALID_OUTPUT",
                                              "message": f"페르소나 생성 결과가 형식에 맞지 않습니다: {e.error_count()}개 오류"}})
    except ValueError as e:  # API 키 미설정 등 (기본 프로바이더 기준)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail={"error": {"code": "LLM_UNAVAILABLE", "message": str(e)}})
    return GeneratePersonasResponse(personas=[p.model_dump() for p in personas])
