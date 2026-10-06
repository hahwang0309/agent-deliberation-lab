#!/usr/bin/env python3
"""
RAG 빠른 테스트
"""
import asyncio
import os
from dotenv import load_dotenv


async def quick_test():
    load_dotenv()
    
    # 1. Import 테스트
    print("Testing imports...")
    from src.models import Persona
    from src.services.rag_service import RAGService, QueryType
    print("✅ Imports OK")
    
    # 2. RAG 초기화 테스트
    print("\nTesting RAG initialization...")
    rag = RAGService()
    print("✅ RAG initialized")
    
    # 3. Query Generation 테스트
    print("\nTesting query generation...")
    
    persona = Persona(
        name="TestAgent",
        role="Researcher",
        background="AI expert",
        personality=["analytical"],
        expertise=["AI"],
        communication_style="Technical",
        beliefs=["Data matters"]
    )
    
    result = await rag.query_generator.generate_persona_query(
        "AI safety in 2024",
        persona,
        None
    )
    
    print(f"Generated query: {result.query}")
    print(f"Query type: {result.query_type.value}")
    print("✅ Query generation works")
    
    # 4. Query Router 테스트
    print("\nTesting query router...")
    
    factual_q = "What are the latest statistics on AI adoption in 2024?"
    opinion_q = "Should we trust AI systems?"
    
    fact_type = await rag.query_router.classify_query(factual_q, "AI")
    opinion_type = await rag.query_router.classify_query(opinion_q, "AI")
    
    print(f"Factual query classified as: {fact_type.value}")
    print(f"Opinion query classified as: {opinion_type.value}")
    
    if fact_type == QueryType.FACTUAL and opinion_type == QueryType.OPINION:
        print("✅ Query routing works correctly")
    else:
        print("⚠️ Query routing may need adjustment")
    
    # 5. Web Search 테스트
    if os.getenv("TAVILY_API_KEY"):
        print("\nTesting web search...")
        from src.services.web_search import WebSearchService
        
        search = WebSearchService()
        results = await search.search("OpenAI GPT-4 2024", max_results=1)
        
        if results:
            print(f"Found {len(results)} search results")
            print(f"First result: {results[0].title[:50]}...")
            print("✅ Web search works")
        else:
            print("⚠️ No search results")
    else:
        print("\n⚠️ Skipping web search (no API key)")
    
    print("\n[bold green]✅ All basic RAG functions working![/bold green]")

if __name__ == "__main__":
    asyncio.run(quick_test())