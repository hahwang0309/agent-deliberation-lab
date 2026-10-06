"""
Discussion Report Generator Service
토론 결과를 전문적인 보고서 형식으로 생성
"""
from typing import List, Dict, Optional
from dataclasses import dataclass
from datetime import datetime
from src.models.personas import Message, Persona, LLMProvider
from src.models.persona_evolution import EvolvingPersona
from langchain_core.messages import HumanMessage
from langchain_core.language_models import BaseChatModel
from src.utils.llm_provider import LLMFactory


@dataclass
class DiscussionReport:
    """토론 보고서 구조"""
    topic: str
    date: str
    participants: List[Dict]
    executive_summary: str
    main_discussion_points: List[Dict]
    consensus_items: List[str]
    divergent_views: List[Dict]
    belief_evolution: List[Dict]
    subtopics_covered: List[str]
    subtopics_remaining: List[str]
    key_facts_cited: List[str]
    recommendations: List[str]
    conclusion: str


class ReportGenerator:
    """토론 보고서 생성기"""
    
    def __init__(self, llm: Optional[BaseChatModel] = None, provider: LLMProvider = LLMProvider.OPENAI):
        """보고서 생성기 초기화"""
        if llm:
            self.llm = llm
        else:
            self.llm = LLMFactory.create_llm(provider, temperature=0.3)
    
    async def generate_report(
        self,
        topic: str,
        messages: List[Message],
        agents: List,
        moderator: Optional = None,
        subtopics_planned: List[str] = None,
        subtopics_discussed: List[str] = None
    ) -> DiscussionReport:
        """토론 보고서 생성"""
        
        # 1. 참가자 정보 수집
        participants = self._extract_participants(agents)
        
        # 2. 주요 논의 내용 추출
        main_points = await self._extract_main_points(messages, topic)
        
        # 3. 합의 사항 도출
        consensus = await self._identify_consensus(messages, topic)
        
        # 4. 이견 사항 정리
        divergent = await self._identify_divergent_views(messages, topic)
        
        # 5. 신념 변화 추적
        belief_changes = self._track_belief_evolution(agents)
        
        # 6. 주제 커버리지 분석
        covered = subtopics_discussed or []
        remaining = [t for t in (subtopics_planned or []) if t not in covered]
        
        # 7. 핵심 사실/증거 추출
        key_facts = await self._extract_key_facts(messages)
        
        # 8. 요약 및 결론 생성
        executive_summary = await self._generate_executive_summary(
            topic, main_points, consensus, divergent
        )
        
        # 9. 권고사항 도출
        recommendations = await self._generate_recommendations(
            topic, consensus, divergent, remaining
        )
        
        # 10. 결론 작성
        conclusion = await self._generate_conclusion(
            topic, consensus, divergent, recommendations
        )
        
        return DiscussionReport(
            topic=topic,
            date=datetime.now().strftime("%Y-%m-%d %H:%M"),
            participants=participants,
            executive_summary=executive_summary,
            main_discussion_points=main_points,
            consensus_items=consensus,
            divergent_views=divergent,
            belief_evolution=belief_changes,
            subtopics_covered=covered,
            subtopics_remaining=remaining,
            key_facts_cited=key_facts,
            recommendations=recommendations,
            conclusion=conclusion
        )
    
    def _extract_participants(self, agents) -> List[Dict]:
        """참가자 정보 추출"""
        participants = []
        for agent in agents:
            persona = agent.persona
            participants.append({
                "name": persona.name,
                "role": persona.role,
                "expertise": ", ".join(persona.expertise[:2]),
                "total_statements": agent.statement_count,
                "position_shifts": agent.total_position_shifts if hasattr(agent, 'total_position_shifts') else 0
            })
        return participants
    
    async def _extract_main_points(self, messages: List[Message], topic: str) -> List[Dict]:
        """주요 논의 사항 추출"""
        if not messages:
            return []
        
        # 메시지를 청크로 분할
        chunk_size = 5
        main_points = []
        
        for i in range(0, len(messages), chunk_size):
            chunk = messages[i:i+chunk_size]
            chunk_text = "\n".join([f"{m.agent_name}: {m.content[:200]}" for m in chunk])
            
            prompt = f"""
Analyze this discussion segment about "{topic}":

{chunk_text}

Extract the MAIN ARGUMENT or KEY POINT being discussed.
Format as JSON:
{{
    "argument": "Brief description of the main point",
    "proponents": ["List of speakers supporting this"],
    "evidence": "Key evidence or reasoning provided"
}}

Return ONLY valid JSON.
"""
            response = await self.llm.ainvoke([HumanMessage(content=prompt)])
            try:
                import json
                point = json.loads(response.content)
                main_points.append(point)
            except:
                continue
        
        return main_points[:5]  # 상위 5개 주요 논점
    
    async def _identify_consensus(self, messages: List[Message], topic: str) -> List[str]:
        """합의 사항 도출"""
        if len(messages) < 3:
            return []
        
        discussion_text = "\n".join([f"{m.agent_name}: {m.content[:150]}" for m in messages[-10:]])
        
        prompt = f"""
Analyze this discussion about "{topic}":

{discussion_text}

Identify points of CONSENSUS or AGREEMENT among participants.
List 3-5 specific items where participants seem to agree.
Format as a JSON array of strings.

Example: ["All agreed that X is important", "Consensus on need for Y"]

Return ONLY valid JSON array.
"""
        response = await self.llm.ainvoke([HumanMessage(content=prompt)])
        try:
            import json
            consensus = json.loads(response.content)
            return consensus if isinstance(consensus, list) else []
        except:
            return []
    
    async def _identify_divergent_views(self, messages: List[Message], topic: str) -> List[Dict]:
        """이견 사항 정리"""
        if len(messages) < 3:
            return []
        
        discussion_text = "\n".join([f"{m.agent_name}: {m.content[:150]}" for m in messages])
        
        prompt = f"""
Analyze this discussion about "{topic}":

{discussion_text}

Identify DIVERGENT VIEWS or DISAGREEMENTS.
Format as JSON array:
[
    {{
        "issue": "The contested point",
        "position_a": "First position",
        "position_b": "Alternative position",
        "advocates_a": ["Supporters of position A"],
        "advocates_b": ["Supporters of position B"]
    }}
]

Return ONLY valid JSON.
"""
        response = await self.llm.ainvoke([HumanMessage(content=prompt)])
        try:
            import json
            divergent = json.loads(response.content)
            return divergent if isinstance(divergent, list) else []
        except:
            return []
    
    def _track_belief_evolution(self, agents) -> List[Dict]:
        """신념 변화 추적"""
        evolution_data = []
        
        for agent in agents:
            if hasattr(agent, 'evolving_persona') and agent.evolving_persona:
                shifts = agent.evolving_persona.position_shifts
                if shifts:
                    evolution_data.append({
                        "agent": agent.persona.name,
                        "total_shifts": len(shifts),
                        "major_changes": [
                            {
                                "topic": shift.get('topic', 'Unknown'),
                                "direction": shift.get('direction', 'Modified view'),
                                "reason": shift.get('influenced_by', 'Discussion')[:100]
                            }
                            for shift in shifts[-2:]  # 최근 2개 변화
                        ]
                    })
        
        return evolution_data
    
    async def _extract_key_facts(self, messages: List[Message]) -> List[str]:
        """핵심 사실/증거 추출"""
        facts = []
        
        for msg in messages:
            # 숫자, 퍼센트, 연구, 데이터 등이 포함된 문장 찾기
            import re
            
            # 패턴: 숫자%, 연구/study, 데이터/data, 증거/evidence
            patterns = [
                r'\d+%',
                r'\d+\s*(million|billion|thousand)',
                r'(research|study|survey|report)\s+shows',
                r'according to\s+\w+',
                r'data (indicates|suggests|shows)',
                r'evidence (suggests|shows|indicates)'
            ]
            
            for pattern in patterns:
                if re.search(pattern, msg.content, re.IGNORECASE):
                    # 해당 문장 추출
                    sentences = msg.content.split('.')
                    for sent in sentences:
                        if re.search(pattern, sent, re.IGNORECASE):
                            fact = f"{msg.agent_name}: {sent.strip()}"
                            if len(fact) < 200 and fact not in facts:
                                facts.append(fact)
                                break
                    break
        
        return facts[:7]  # 상위 7개 사실
    
    async def _generate_executive_summary(
        self, topic: str, main_points: List[Dict], 
        consensus: List[str], divergent: List[Dict]
    ) -> str:
        """요약문 생성"""
        prompt = f"""
Write an executive summary for a discussion about: "{topic}"

Key points discussed: {len(main_points)}
Consensus items: {len(consensus)}
Divergent views: {len(divergent)}

Create a professional 3-4 sentence summary that captures:
1. The main focus of the discussion
2. Level of agreement/disagreement
3. Key insights or conclusions

Be concise and professional.
"""
        response = await self.llm.ainvoke([HumanMessage(content=prompt)])
        return response.content
    
    async def _generate_recommendations(
        self, topic: str, consensus: List[str], 
        divergent: List[Dict], remaining: List[str]
    ) -> List[str]:
        """권고사항 도출"""
        prompt = f"""
Based on a discussion about "{topic}":

Consensus reached on: {', '.join(consensus[:3]) if consensus else 'Limited consensus'}
Unresolved issues: {len(divergent)} divergent views
Topics not fully explored: {', '.join(remaining[:3]) if remaining else 'All topics covered'}

Generate 3-5 specific, actionable recommendations for:
1. Moving forward with agreed points
2. Addressing unresolved issues
3. Future discussion priorities

Format as JSON array of strings.
"""
        response = await self.llm.ainvoke([HumanMessage(content=prompt)])
        try:
            import json
            recs = json.loads(response.content)
            return recs if isinstance(recs, list) else []
        except:
            return ["Continue exploring divergent viewpoints", 
                   "Gather more evidence on contested issues",
                   "Focus on implementation of consensus items"]
    
    async def _generate_conclusion(
        self, topic: str, consensus: List[str], 
        divergent: List[Dict], recommendations: List[str]
    ) -> str:
        """결론 작성"""
        prompt = f"""
Write a brief conclusion for a discussion report about: "{topic}"

The discussion resulted in {len(consensus)} consensus items and {len(divergent)} areas of disagreement.
{len(recommendations)} recommendations were made.

Write 2-3 sentences that:
1. Summarize the overall outcome
2. Highlight the value of the discussion
3. Point toward next steps

Be professional and balanced.
"""
        response = await self.llm.ainvoke([HumanMessage(content=prompt)])
        return response.content
    
    def format_report(self, report: DiscussionReport) -> str:
        """보고서 포맷팅"""
        formatted = f"""
================================================================================
                            DISCUSSION REPORT
================================================================================

TOPIC: {report.topic}
DATE: {report.date}

--------------------------------------------------------------------------------
EXECUTIVE SUMMARY
--------------------------------------------------------------------------------
{report.executive_summary}

--------------------------------------------------------------------------------
PARTICIPANTS
--------------------------------------------------------------------------------
"""
        for p in report.participants:
            formatted += f"• {p['name']} ({p['role']})\n"
            formatted += f"  - Expertise: {p['expertise']}\n"
            formatted += f"  - Contributions: {p['total_statements']} statements"
            if p['position_shifts'] > 0:
                formatted += f", {p['position_shifts']} position shifts"
            formatted += "\n\n"
        
        formatted += """
--------------------------------------------------------------------------------
MAIN DISCUSSION POINTS
--------------------------------------------------------------------------------
"""
        for i, point in enumerate(report.main_discussion_points, 1):
            formatted += f"{i}. {point.get('argument', 'N/A')}\n"
            if point.get('proponents'):
                formatted += f"   Discussed by: {', '.join(point['proponents'])}\n"
            if point.get('evidence'):
                formatted += f"   Key evidence: {point['evidence']}\n"
            formatted += "\n"
        
        formatted += """
--------------------------------------------------------------------------------
CONSENSUS ITEMS
--------------------------------------------------------------------------------
"""
        if report.consensus_items:
            for item in report.consensus_items:
                formatted += f"✓ {item}\n"
        else:
            formatted += "No clear consensus reached.\n"
        
        formatted += """
--------------------------------------------------------------------------------
DIVERGENT VIEWS
--------------------------------------------------------------------------------
"""
        if report.divergent_views:
            for div in report.divergent_views:
                formatted += f"Issue: {div.get('issue', 'N/A')}\n"
                formatted += f"  Position A: {div.get('position_a', 'N/A')}\n"
                if div.get('advocates_a'):
                    formatted += f"    Supported by: {', '.join(div['advocates_a'])}\n"
                formatted += f"  Position B: {div.get('position_b', 'N/A')}\n"
                if div.get('advocates_b'):
                    formatted += f"    Supported by: {', '.join(div['advocates_b'])}\n"
                formatted += "\n"
        else:
            formatted += "No significant divergent views identified.\n"
        
        if report.belief_evolution:
            formatted += """
--------------------------------------------------------------------------------
BELIEF EVOLUTION
--------------------------------------------------------------------------------
"""
            for evo in report.belief_evolution:
                formatted += f"{evo['agent']}: {evo['total_shifts']} position shifts\n"
                for change in evo.get('major_changes', []):
                    formatted += f"  • {change.get('direction', 'Changed view')} on {change.get('topic', 'topic')}\n"
        
        formatted += """
--------------------------------------------------------------------------------
TOPIC COVERAGE
--------------------------------------------------------------------------------
"""
        if report.subtopics_covered:
            formatted += "Covered:\n"
            for topic in report.subtopics_covered:
                formatted += f"  ✓ {topic}\n"
        
        if report.subtopics_remaining:
            formatted += "\nRemaining:\n"
            for topic in report.subtopics_remaining:
                formatted += f"  ○ {topic}\n"
        
        if report.key_facts_cited:
            formatted += """
--------------------------------------------------------------------------------
KEY FACTS & EVIDENCE CITED
--------------------------------------------------------------------------------
"""
            for fact in report.key_facts_cited:
                formatted += f"• {fact}\n"
        
        formatted += """
--------------------------------------------------------------------------------
RECOMMENDATIONS
--------------------------------------------------------------------------------
"""
        for i, rec in enumerate(report.recommendations, 1):
            formatted += f"{i}. {rec}\n"
        
        formatted += f"""
--------------------------------------------------------------------------------
CONCLUSION
--------------------------------------------------------------------------------
{report.conclusion}

================================================================================
                              END OF REPORT
================================================================================
"""
        return formatted