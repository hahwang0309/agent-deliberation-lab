"""
분석 서비스
"""
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from typing import Dict, List, Tuple, Optional
from datetime import datetime
from collections import defaultdict, Counter
from api.models.discussion import Discussion, Participant
from api.models.message import Message
from api.services.discussion_service import DiscussionService


class AnalyticsService:
    """분석 관련 비즈니스 로직"""
    
    @staticmethod
    def calculate_discussion_statistics(
        db: Session,
        discussion: Discussion
    ) -> dict:
        """
        토론 통계 계산
        
        Args:
            db: 데이터베이스 세션
            discussion: 토론
            
        Returns:
            통계 딕셔너리
        """
        messages = db.query(Message).filter(
            Message.discussion_id == discussion.id
        ).all()
        
        total_messages = len(messages)
        total_rounds = discussion.current_round or 1
        
        # 참가자별 메시지 수
        messages_per_participant = defaultdict(int)
        for msg in messages:
            messages_per_participant[msg.speaker] += 1
        
        # 메시지 길이 통계
        total_chars = sum(msg.character_count for msg in messages)
        total_words = sum(msg.word_count for msg in messages)
        avg_length = total_chars // total_messages if total_messages > 0 else 0
        
        # RAG 통계
        rag_messages = [msg for msg in messages if msg.rag_used]
        rag_queries = []
        for msg in rag_messages:
            if msg.rag_query:
                rag_queries.append({
                    "query": msg.rag_query,
                    "speaker": msg.speaker
                })
        
        # 쿼리 빈도 계산
        query_counter = Counter()
        query_speakers = {}
        for item in rag_queries:
            query_counter[item["query"]] += 1
            query_speakers[item["query"]] = item["speaker"]
        
        top_queries = [
            {
                "query": query,
                "count": count,
                "speaker": query_speakers[query]
            }
            for query, count in query_counter.most_common(5)
        ]
        
        return {
            "duration_seconds": DiscussionService.calculate_duration_seconds(discussion) or 0,
            "total_rounds": total_rounds,
            "total_messages": total_messages,
            "messages_per_round": total_messages / total_rounds if total_rounds > 0 else 0,
            "messages_per_participant": dict(messages_per_participant),
            "avg_message_length": avg_length,
            "total_characters": total_chars,
            "total_words": total_words,
            "rag_usage": {
                "total_searches": len(rag_messages),
                "successful_searches": len([m for m in rag_messages if m.sources]),
                "failed_searches": len([m for m in rag_messages if not m.sources]),
                "usage_rate": len(rag_messages) / total_messages if total_messages > 0 else 0,
                "avg_search_time_seconds": 3.5,  # TODO: 실제 측정
                "top_queries": top_queries
            }
        }
    
    @staticmethod
    def analyze_sentiment(
        db: Session,
        discussion: Discussion
    ) -> dict:
        """
        감정 분석
        
        Args:
            db: 데이터베이스 세션
            discussion: 토론
            
        Returns:
            감정 분석 딕셔너리
        """
        messages = db.query(Message).filter(
            Message.discussion_id == discussion.id
        ).order_by(Message.timestamp).all()
        
        if not messages:
            return {
                "overall": {"positive": 0.33, "neutral": 0.33, "negative": 0.34},
                "by_participant": {}
            }
        
        # 전체 감정 계산
        total_positive = sum(1 for m in messages if m.sentiment_label == "positive")
        total_neutral = sum(1 for m in messages if m.sentiment_label == "neutral")
        total_negative = sum(1 for m in messages if m.sentiment_label == "negative")
        total = len(messages)
        
        overall = {
            "positive": total_positive / total if total > 0 else 0,
            "neutral": total_neutral / total if total > 0 else 0,
            "negative": total_negative / total if total > 0 else 0
        }
        
        # 참가자별 감정 분석
        by_participant = {}
        for participant in discussion.participants:
            participant_messages = [m for m in messages if m.speaker == participant.name]
            
            if not participant_messages:
                continue
            
            p_positive = sum(1 for m in participant_messages if m.sentiment_label == "positive")
            p_neutral = sum(1 for m in participant_messages if m.sentiment_label == "neutral")
            p_negative = sum(1 for m in participant_messages if m.sentiment_label == "negative")
            p_total = len(participant_messages)
            
            # 트렌드 계산 (초기 vs 후기)
            mid_point = p_total // 2
            early_score = sum(m.sentiment_score or 0 for m in participant_messages[:mid_point])
            late_score = sum(m.sentiment_score or 0 for m in participant_messages[mid_point:])
            
            if late_score > early_score + 0.1:
                trend = "increasingly_positive"
            elif late_score < early_score - 0.1:
                trend = "increasingly_negative"
            elif late_score > early_score:
                trend = "slightly_positive"
            else:
                trend = "stable"
            
            # 라운드별 변화
            change_over_time = []
            for round_num in range(1, discussion.current_round + 1):
                round_messages = [m for m in participant_messages if m.round_number == round_num]
                if round_messages:
                    avg_score = sum(m.sentiment_score or 0 for m in round_messages) / len(round_messages)
                    change_over_time.append({"round": round_num, "score": avg_score})
            
            by_participant[participant.name] = {
                "positive": p_positive / p_total if p_total > 0 else 0,
                "neutral": p_neutral / p_total if p_total > 0 else 0,
                "negative": p_negative / p_total if p_total > 0 else 0,
                "trend": trend,
                "change_over_time": change_over_time[:4]  # 최대 4개 라운드
            }
        
        return {
            "overall": overall,
            "by_participant": by_participant
        }
    
    @staticmethod
    def extract_key_topics(
        db: Session,
        discussion: Discussion
    ) -> List[dict]:
        """
        핵심 주제 추출
        
        Args:
            db: 데이터베이스 세션
            discussion: 토론
            
        Returns:
            주제 리스트
        """
        messages = db.query(Message).filter(
            Message.discussion_id == discussion.id
        ).all()
        
        # 간단한 키워드 추출 (실제로는 NLP 사용)
        keywords = ["규제", "안전", "혁신", "스타트업", "비용", "데이터", "투명성"]
        topics = []
        
        for keyword in keywords:
            keyword_messages = [m for m in messages if keyword in m.content]
            if not keyword_messages:
                continue
            
            # 감정 점수 평균
            avg_sentiment = sum(m.sentiment_score or 0 for m in keyword_messages) / len(keyword_messages)
            
            # 주요 논의자
            speakers = Counter(m.speaker for m in keyword_messages)
            main_discussants = [speaker for speaker, _ in speakers.most_common(3)]
            
            topics.append({
                "topic": keyword,
                "frequency": len(keyword_messages),
                "sentiment": avg_sentiment,
                "main_discussants": main_discussants
            })
        
        # 빈도순 정렬
        topics.sort(key=lambda x: x["frequency"], reverse=True)
        return topics[:10]
    
    @staticmethod
    def calculate_consensus(
        db: Session,
        discussion: Discussion
    ) -> dict:
        """
        합의도 계산
        
        Args:
            db: 데이터베이스 세션
            discussion: 토론
            
        Returns:
            합의 정보
        """
        # TODO: 실제 합의도 계산 알고리즘
        
        return {
            "score": discussion.consensus_score or 0.78,
            "reached": discussion.consensus_reached or True,
            "confidence": 0.85,
            "main_agreement": "차등적 규제 접근",
            "agreement_areas": [
                {
                    "area": "차등적 규제 필요성",
                    "support_level": 1.0,
                    "supporters": [p.name for p in discussion.participants]
                },
                {
                    "area": "샌드박스 환경 제공",
                    "support_level": 0.9,
                    "supporters": [p.name for p in discussion.participants[:2]]
                }
            ],
            "disagreement_areas": [
                {
                    "area": "규제 강도",
                    "positions": {
                        discussion.participants[0].name: "엄격한 규제",
                        discussion.participants[1].name: "최소한의 규제"
                    } if len(discussion.participants) >= 2 else {},
                    "gap_score": 0.4
                }
            ]
        }
    
    @staticmethod
    def calculate_quality_metrics(
        db: Session,
        discussion: Discussion
    ) -> dict:
        """
        품질 지표 계산
        
        Args:
            db: 데이터베이스 세션
            discussion: 토론
            
        Returns:
            품질 지표
        """
        messages = db.query(Message).filter(
            Message.discussion_id == discussion.id
        ).all()
        
        total = len(messages)
        if total == 0:
            return {
                "evidence_based_score": 0,
                "constructive_dialogue_score": 0,
                "open_mindedness_score": 0,
                "argument_diversity_score": 0,
                "overall_quality": 0
            }
        
        # 증거 기반 점수 (RAG 사용률)
        rag_count = sum(1 for m in messages if m.rag_used)
        evidence_based = rag_count / total
        
        # 건설적 대화 점수 (긍정/중립 감정)
        constructive_count = sum(1 for m in messages if m.sentiment_label in ["positive", "neutral"])
        constructive = constructive_count / total
        
        # 개방성 점수 (평균 개방성)
        avg_openness = sum(p.current_openness for p in discussion.participants) / len(discussion.participants)
        
        # 논점 다양성 (참가자 균등 발언)
        speaker_counts = Counter(m.speaker for m in messages)
        diversity = 1.0 - (max(speaker_counts.values()) - min(speaker_counts.values())) / total
        
        overall = (evidence_based + constructive + avg_openness + diversity) / 4
        
        return {
            "evidence_based_score": round(evidence_based, 2),
            "constructive_dialogue_score": round(constructive, 2),
            "open_mindedness_score": round(avg_openness, 2),
            "argument_diversity_score": round(diversity, 2),
            "overall_quality": round(overall, 2)
        }
    
    @staticmethod
    def analyze_interaction_network(
        db: Session,
        discussion: Discussion
    ) -> dict:
        """
        상호작용 네트워크 분석
        
        Args:
            db: 데이터베이스 세션
            discussion: 토론
            
        Returns:
            네트워크 정보
        """
        messages = db.query(Message).filter(
            Message.discussion_id == discussion.id
        ).order_by(Message.timestamp).all()
        
        # 직접 응답 계산 (연속된 메시지)
        direct_responses = defaultdict(int)
        for i in range(1, len(messages)):
            prev_speaker = messages[i-1].speaker
            curr_speaker = messages[i].speaker
            if prev_speaker != curr_speaker:
                key = f"{curr_speaker} -> {prev_speaker}"
                direct_responses[key] += 1
        
        # 영향력 점수 (발언 수 + 응답 받은 수)
        influence_scores = {}
        for participant in discussion.participants:
            message_count = sum(1 for m in messages if m.speaker == participant.name)
            response_count = sum(1 for key, count in direct_responses.items() 
                               if participant.name in key.split(" -> ")[1])
            
            influence = (message_count + response_count * 2) / (len(messages) + sum(direct_responses.values()))
            influence_scores[participant.name] = round(influence, 2)
        
        return {
            "direct_responses": dict(direct_responses),
            "influence_scores": influence_scores
        }
    
    @staticmethod
    def generate_discussion_summary(
        db: Session,
        discussion: Discussion
    ) -> dict:
        """
        토론 요약 생성
        
        Args:
            db: 데이터베이스 세션
            discussion: 토론
            
        Returns:
            요약 딕셔너리
        """
        # TODO: LLM 기반 요약 생성
        
        return {
            "executive_summary": f"세 명의 전문가가 {discussion.topic}에 대해 {discussion.current_round}라운드 토론을 진행했습니다.",
            "key_arguments": {
                p.name: [
                    f"{p.role}의 관점",
                    "데이터 기반 논의",
                    "실용적 접근"
                ]
                for p in discussion.participants
            },
            "consensus": {
                "main_agreement": "차등적 규제 접근",
                "details": [
                    "대기업: 엄격한 안전 규제",
                    "스타트업: 규제 샌드박스",
                    "모든 기업: 투명성 보고"
                ],
                "confidence": 0.78
            },
            "discussion_progression": [
                {
                    "phase": "초기 (라운드 1-2)",
                    "description": "강한 의견 대립",
                    "consensus_score": 0.2,
                    "key_moments": ["초기 입장 표명"]
                },
                {
                    "phase": "중기 (라운드 3-5)",
                    "description": "데이터 기반 논의",
                    "consensus_score": 0.5,
                    "key_moments": ["성찰 타임"]
                },
                {
                    "phase": "후기 (라운드 6-8)",
                    "description": "합의 형성",
                    "consensus_score": 0.78,
                    "key_moments": ["최종 합의"]
                }
            ],
            "top_sources": [],
            "quality_assessment": {
                "overall_score": 0.83,
                "strengths": ["데이터 기반", "건설적 대화"],
                "areas_for_improvement": ["실행 시기 합의 부족"]
            }
        }
    
    @staticmethod
    def track_persona_evolution(
        db: Session,
        discussion: Discussion,
        persona_filter: Optional[str] = None
    ) -> dict:
        """
        페르소나 진화 추적
        
        Args:
            db: 데이터베이스 세션
            discussion: 토론
            persona_filter: 특정 페르소나 필터
            
        Returns:
            진화 정보
        """
        participants = discussion.participants
        if persona_filter:
            participants = [p for p in participants if p.name == persona_filter]
        
        personas = []
        for participant in participants:
            # 초기/최종 상태
            initial_openness = 0.45
            final_openness = participant.current_openness
            
            personas.append({
                "name": participant.name,
                "role": participant.role,
                "initial_state": {
                    "beliefs": participant.persona_data.get("personality", []) if participant.persona_data else [],
                    "openness_score": initial_openness,
                    "flexibility_score": 0.35,
                    "timestamp": discussion.created_at
                },
                "final_state": {
                    "beliefs": participant.persona_data.get("personality", []) if participant.persona_data else [],
                    "openness_score": final_openness,
                    "flexibility_score": final_openness - 0.1,
                    "timestamp": discussion.updated_at or discussion.created_at
                },
                "changes": {
                    "beliefs_added": ["실용적 규제 균형"],
                    "beliefs_removed": [],
                    "openness_change": final_openness - initial_openness,
                    "flexibility_change": (final_openness - 0.1) - 0.35
                },
                "evolution_history": [],
                "key_influences": [],
                "interaction_patterns": {
                    "most_engaged_with": participants[0].name if len(participants) > 1 else "",
                    "engagement_count": 5,
                    "agreement_rate": 0.45,
                    "challenge_rate": 0.55
                }
            })
        
        # 전체 트렌드
        avg_openness_increase = sum(
            p["changes"]["openness_change"] for p in personas
        ) / len(personas) if personas else 0
        
        avg_flexibility_increase = sum(
            p["changes"]["flexibility_change"] for p in personas
        ) / len(personas) if personas else 0
        
        return {
            "personas": personas,
            "overall_trends": {
                "average_openness_increase": round(avg_openness_increase, 3),
                "average_flexibility_increase": round(avg_flexibility_increase, 3),
                "consensus_correlation": 0.85,
                "evolution_rate": "moderate"
            }
        }

