"""
내보내기 서비스
"""
from datetime import datetime
from sqlalchemy.orm import Session

from api.models.discussion import Discussion
from api.models.message import Message
from api.services.analytics_service import AnalyticsService
from api.schemas.export import (
    JSONExportResponse,
    ExportDiscussionInfo,
    ExportParticipant,
    ExportConfig,
    ExportMessage,
    ExportSource
)
from api.schemas.analytics import (
    DiscussionAnalyticsResponse,
    PersonaEvolutionResponse
)


class ExportService:
    """내보내기 서비스"""
    
    @staticmethod
    def export_json(db: Session, discussion_id: str) -> JSONExportResponse:
        """
        토론을 JSON 형식으로 내보내기
        
        Args:
            db: 데이터베이스 세션
            discussion_id: 토론 ID
            
        Returns:
            JSONExportResponse: JSON 내보내기 응답
        """
        # 토론 정보 조회
        discussion = db.query(Discussion).filter(Discussion.id == discussion_id).first()
        if not discussion:
            raise ValueError("토론을 찾을 수 없습니다.")
        
        # 메시지 조회
        messages = db.query(Message).filter(
            Message.discussion_id == discussion_id
        ).order_by(Message.created_at).all()
        
        # 분석 데이터 조회 (analytics 라우터와 동일한 방식)
        statistics = AnalyticsService.calculate_discussion_statistics(db, discussion)
        sentiment_analysis = AnalyticsService.analyze_sentiment(db, discussion)
        key_topics = AnalyticsService.extract_key_topics(db, discussion)
        consensus = AnalyticsService.calculate_consensus(db, discussion)
        quality_metrics = AnalyticsService.calculate_quality_metrics(db, discussion)
        interaction_network = AnalyticsService.analyze_interaction_network(db, discussion)
        
        analytics_response = DiscussionAnalyticsResponse(
            discussion_id=discussion.id,
            topic=discussion.topic,
            status=discussion.status,
            statistics=statistics,
            sentiment_analysis=sentiment_analysis,
            key_topics=key_topics,
            consensus=consensus,
            quality_metrics=quality_metrics,
            interaction_network=interaction_network,
            generated_at=datetime.utcnow()
        )
        
        # 페르소나 진화 데이터 조회
        persona_evolution_data = AnalyticsService.analyze_persona_evolution(db, discussion)
        persona_evolution_response = PersonaEvolutionResponse(
            discussion_id=discussion.id,
            personas=persona_evolution_data.get("personas", {}),
            overall_trends=persona_evolution_data.get("overall_trends", {}),
            generated_at=datetime.utcnow()
        )
        
        # 토론 정보
        duration_seconds = None
        if discussion.started_at and discussion.completed_at:
            duration_seconds = int((discussion.completed_at - discussion.started_at).total_seconds())
        
        discussion_info = ExportDiscussionInfo(
            id=discussion.id,
            topic=discussion.topic,
            description=discussion.description,
            status=discussion.status,
            created_at=discussion.created_at,
            started_at=discussion.started_at,
            completed_at=discussion.completed_at,
            duration_seconds=duration_seconds,
            created_by=discussion.user_id
        )
        
        # 참가자 정보
        participants = [
            ExportParticipant(
                id=p.id,
                name=p.name,
                role=p.role,
                template_id=p.template_id,
                llm_provider=p.llm_provider,
                model=p.model
            )
            for p in discussion.participants
        ]
        
        # 설정 정보
        config = ExportConfig(
            max_rounds=discussion.max_rounds,
            min_rounds=discussion.min_rounds,
            enable_rag=discussion.enable_rag,
            enable_subtopics=discussion.enable_subtopics,
            enable_reflection=discussion.enable_reflection,
            reflection_interval=discussion.reflection_interval,
            enable_persona_evolution=discussion.enable_persona_evolution
        )
        
        # 메시지 정보
        export_messages = []
        for msg in messages:
            sources = []
            if msg.rag_sources:
                for source in msg.rag_sources:
                    sources.append(ExportSource(
                        url=source.get("url", ""),
                        title=source.get("title", "")
                    ))
            
            export_messages.append(ExportMessage(
                id=msg.id,
                speaker=msg.speaker_name,
                content=msg.content,
                timestamp=msg.created_at,
                round=msg.round_number,
                rag_used=msg.rag_used,
                rag_query=msg.rag_query,
                sources=sources
            ))
        
        # JSON 응답 생성
        return JSONExportResponse(
            discussion=discussion_info,
            participants=participants,
            config=config,
            messages=export_messages,
            analytics=analytics_response.dict(),
            persona_evolution=persona_evolution_response.dict(),
            exported_at=datetime.utcnow(),
            export_version="1.0"
        )
    
    @staticmethod
    def export_markdown(db: Session, discussion_id: str) -> str:
        """
        토론을 Markdown 형식으로 내보내기
        
        Args:
            db: 데이터베이스 세션
            discussion_id: 토론 ID
            
        Returns:
            str: Markdown 문자열
        """
        # JSON 데이터 먼저 생성
        json_export = ExportService.export_json(db, discussion_id)
        
        # Markdown 생성
        md = []
        
        # 제목
        md.append(f"# {json_export.discussion.topic}\n")
        
        # 토론 정보
        md.append(f"**토론 ID**: {json_export.discussion.id}  ")
        md.append(f"**상태**: {ExportService._translate_status(json_export.discussion.status)}  ")
        
        # 일시 및 소요 시간
        if json_export.discussion.started_at and json_export.discussion.completed_at:
            start = json_export.discussion.started_at.strftime("%Y-%m-%d %H:%M:%S")
            end = json_export.discussion.completed_at.strftime("%H:%M:%S")
            duration_min = json_export.discussion.duration_seconds // 60 if json_export.discussion.duration_seconds else 0
            md.append(f"**일시**: {start} - {end} ({duration_min}분)  ")
        
        # 참가자 이름
        participant_names = ", ".join([p.name for p in json_export.participants])
        md.append(f"**참가자**: {participant_names}  ")
        
        # 라운드 및 메시지 수
        total_rounds = json_export.analytics.get("statistics", {}).get("total_rounds", 0)
        total_messages = json_export.analytics.get("statistics", {}).get("total_messages", 0)
        md.append(f"**라운드**: {total_rounds}/{json_export.config.max_rounds} | **메시지**: {total_messages}개\n")
        
        md.append("---\n")
        
        # 요약
        md.append("## 📊 요약\n")
        summary_data = json_export.analytics.get("summary", {})
        if summary_data:
            executive_summary = summary_data.get("executive_summary", "")
            md.append(f"{executive_summary}\n")
        
        # 합의 사항
        consensus_areas = json_export.analytics.get("consensus", {}).get("consensus_areas", [])
        if consensus_areas:
            md.append("### 🤝 합의 사항\n")
            for area in consensus_areas:
                md.append(f"- **주요 합의**: {area.get('topic', '')}")
                md.append(f"- **세부 내용**:")
                supporters = area.get("supporters", [])
                for supporter in supporters:
                    md.append(f"  - {supporter}")
                md.append("")
        
        md.append("---\n")
        
        # 참가자 상세 정보
        md.append("## 👥 참가자\n")
        persona_evol = json_export.persona_evolution.get("personas", {})
        
        for participant in json_export.participants:
            md.append(f"### {participant.name}")
            md.append(f"- **역할**: {participant.role}")
            md.append(f"- **LLM**: {ExportService._format_llm(participant.llm_provider, participant.model)}")
            
            # 페르소나 진화 정보
            if participant.name in persona_evol:
                evol_data = persona_evol[participant.name]
                initial_state = evol_data.get("initial_state", {})
                final_state = evol_data.get("final_state", {})
                
                initial_beliefs = initial_state.get("beliefs", [])
                final_beliefs = final_state.get("beliefs", [])
                
                md.append(f"- **초기 신념**: {', '.join(initial_beliefs)}")
                md.append(f"- **최종 신념**: {', '.join(final_beliefs)}")
                
                initial_openness = initial_state.get("openness", 0.5)
                final_openness = final_state.get("openness", 0.5)
                openness_change = final_openness - initial_openness
                sign = "+" if openness_change >= 0 else ""
                md.append(f"- **개방성**: {int(initial_openness * 100)}% → {int(final_openness * 100)}% ({sign}{int(openness_change * 100)}%p)")
            
            md.append("")
        
        md.append("---\n")
        
        # 토론 내용
        md.append("## 💬 토론 내용\n")
        
        # 라운드별 그룹핑
        messages_by_round = {}
        for msg in json_export.messages:
            if msg.round not in messages_by_round:
                messages_by_round[msg.round] = []
            messages_by_round[msg.round].append(msg)
        
        for round_num in sorted(messages_by_round.keys()):
            round_messages = messages_by_round[round_num]
            
            # 라운드 헤더
            md.append(f"### 라운드 {round_num}\n")
            
            # 메시지
            for msg in round_messages:
                timestamp = msg.timestamp.strftime("%H:%M:%S")
                md.append(f"#### 💬 {msg.speaker} ({timestamp})")
                md.append(f"{msg.content}\n")
                
                # 출처
                if msg.sources:
                    md.append("**출처**:")
                    for source in msg.sources:
                        md.append(f"- [{source.title}]({source.url})")
                    md.append("")
        
        md.append("---\n")
        
        # 성찰 타임 (있는 경우)
        if json_export.config.enable_reflection:
            md.append("## 💭 성찰 타임\n")
            md.append("_참가자들이 자신의 견해를 재평가하고 다른 관점을 고려했습니다._\n")
            md.append("---\n")
        
        # 통계
        md.append("## 📊 통계\n")
        stats = json_export.analytics.get("statistics", {})
        
        md.append(f"- **총 라운드**: {stats.get('total_rounds', 0)}/{json_export.config.max_rounds}")
        md.append(f"- **총 메시지**: {stats.get('total_messages', 0)}개")
        md.append(f"- **소요 시간**: {json_export.discussion.duration_seconds // 60 if json_export.discussion.duration_seconds else 0}분 ({json_export.discussion.duration_seconds or 0}초)")
        
        rag_count = stats.get("rag_usage", {}).get("total_searches", 0)
        rag_rate = stats.get("rag_usage", {}).get("usage_rate", 0)
        md.append(f"- **RAG 검색**: {rag_count}회 ({int(rag_rate * 100)}%)")
        
        consensus_score = json_export.analytics.get("consensus", {}).get("consensus_score", 0)
        md.append(f"- **합의 수준**: {int(consensus_score * 100)}%\n")
        
        # 참가자별 메시지 수
        md.append("### 메시지 수 (참가자별)")
        participant_stats = stats.get("by_participant", {})
        for participant in json_export.participants:
            p_stats = participant_stats.get(participant.name, {})
            msg_count = p_stats.get("message_count", 0)
            md.append(f"- {participant.name}: {msg_count}개")
        md.append("")
        
        # 주요 토픽
        key_topics = json_export.analytics.get("key_topics", [])
        if key_topics:
            md.append("### 주요 토픽")
            for i, topic in enumerate(key_topics[:5], 1):
                topic_name = topic.get("topic", "")
                frequency = topic.get("frequency", 0)
                md.append(f"{i}. {topic_name} ({frequency}회)")
            md.append("")
        
        md.append("---\n")
        
        # 참고 자료
        md.append("## 🔗 참고 자료\n")
        # 모든 출처 수집
        all_sources = {}
        for msg in json_export.messages:
            for source in msg.sources:
                if source.url not in all_sources:
                    all_sources[source.url] = {"title": source.title, "count": 0}
                all_sources[source.url]["count"] += 1
        
        # 인용 횟수별 정렬
        sorted_sources = sorted(all_sources.items(), key=lambda x: x[1]["count"], reverse=True)
        for i, (url, data) in enumerate(sorted_sources[:10], 1):
            md.append(f"{i}. [{data['title']}]({url}) (인용 {data['count']}회)")
        
        md.append("\n---\n")
        
        # 메타데이터
        exported_time = json_export.exported_at.strftime("%Y-%m-%d %H:%M:%S")
        md.append(f"**내보내기 일시**: {exported_time}  ")
        md.append(f"**버전**: {json_export.export_version}\n")
        
        return "\n".join(md)
    
    @staticmethod
    def _translate_status(status: str) -> str:
        """상태를 한글로 번역"""
        status_map = {
            "created": "생성됨",
            "in_progress": "진행 중",
            "paused": "일시정지",
            "completed": "완료",
            "stopped": "중단됨",
            "error": "오류"
        }
        return status_map.get(status, status)
    
    @staticmethod
    def _format_llm(provider: str, model: str) -> str:
        """LLM 정보를 포맷팅"""
        provider_names = {
            "openai": "OpenAI",
            "claude": "Claude",
            "anthropic": "Anthropic"
        }
        provider_name = provider_names.get(provider, provider)
        
        # 모델명 간소화
        model_short = model.replace("claude-3-", "Claude 3 ").replace("-20240229", "")
        model_short = model_short.replace("gpt-", "GPT-")
        
        return f"{provider_name} {model_short}"

