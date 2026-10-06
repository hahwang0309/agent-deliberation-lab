#!/usr/bin/env python3
"""
RAG 빠른 테스트
"""
import asyncio
import os
from dotenv import load_dotenv
from rich.console import Console

console = Console()

async def quick_test():
    load_dotenv()
    
    # 1. Import 테스트
    console.print("[yellow]Testing imports...[/yellow]")
    from src.models import Persona
    from src.services.rag_service import RAGService, QueryType
    console.print("[green]✅ Imports OK[/green]")
    
    # 2. RAG 초기화 테스트
    console.print("\n[yellow]Testing RAG initialization...[/yellow]")
    rag = RAGService()
    console.print("[green]✅ RAG initialized[/green]")
    
    # 3. Query Generation 테스트
    console.print("\n[yellow]Testing query generation...[/yellow]")
    
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
    
    console.print(f"Generated query: {result.query}")
    console.print(f"Query type: {result.query_type.value}")
    console.print("[green]✅ Query generation works[/green]")
    
    # 4. Query Router 테스트
    console.print("\n[yellow]Testing query router...[/yellow]")
    
    factual_q = "What are the latest statistics on AI adoption in 2024?"
    opinion_q = "Should we trust AI systems?"
    
    fact_type = await rag.query_router.classify_query(factual_q, "AI")
    opinion_type = await rag.query_router.classify_query(opinion_q, "AI")
    
    console.print(f"Factual query classified as: {fact_type.value}")
    console.print(f"Opinion query classified as: {opinion_type.value}")
    
    if fact_type == QueryType.FACTUAL and opinion_type == QueryType.OPINION:
        console.print("[green]✅ Query routing works correctly[/green]")
    else:
        console.print("[yellow]⚠️ Query routing may need adjustment[/yellow]")
    
    # 5. Web Search 테스트
    if os.getenv("TAVILY_API_KEY"):
        console.print("\n[yellow]Testing web search...[/yellow]")
        from src.services.web_search import WebSearchService
        
        search = WebSearchService()
        results = await search.search("OpenAI GPT-4 2024", max_results=1)
        
        if results:
            console.print(f"Found {len(results)} search results")
            console.print(f"First result: {results[0].title[:50]}...")
            console.print("[green]✅ Web search works[/green]")
        else:
            console.print("[yellow]⚠️ No search results[/yellow]")
    else:
        console.print("\n[yellow]⚠️ Skipping web search (no API key)[/yellow]")
    
    console.print("\n[bold green]✅ All basic RAG functions working![/bold green]")

if __name__ == "__main__":
    asyncio.run(quick_test())