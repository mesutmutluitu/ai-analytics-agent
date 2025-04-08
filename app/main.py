from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from typing import Dict, Any
import uvicorn
import json

from .config import settings
from app.services.trino_service import TrinoService
from app.services.schema_service import SchemaService
from app.services.ai_service import AIService

app = FastAPI(title="AI Analytics Agent")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services
trino_service = TrinoService()
schema_service = SchemaService(trino_service)
ai_service = AIService()

@app.get("/", response_class=HTMLResponse)
async def root():
    """Simple HTML interface"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>AI Analytics Agent</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 0; padding: 20px; }
            .container { max-width: 800px; margin: 0 auto; }
            textarea { width: 100%; height: 100px; margin: 10px 0; }
            button { padding: 10px 20px; background: #4CAF50; color: white; border: none; cursor: pointer; }
            #results { white-space: pre-wrap; background: #f5f5f5; padding: 15px; margin-top: 20px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>AI Analytics Agent</h1>
            <p>Enter your question about the data:</p>
            <textarea id="question" placeholder="e.g., What are the top selling products last month?"></textarea>
            <button onclick="analyze()">Analyze</button>
            <div id="results"></div>
        </div>
        
        <script>
            async function analyze() {
                const question = document.getElementById('question').value;
                const resultsDiv = document.getElementById('results');
                
                resultsDiv.innerHTML = 'Analyzing...';
                
                try {
                    const response = await fetch('/analyze', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ question })
                    });
                    
                    const data = await response.json();
                    
                    let output = `<h3>Analysis</h3>
                                  <p>${data.analysis}</p>
                                  <h3>Query Used</h3>
                                  <pre>${data.query}</pre>`;
                                  
                    if (data.results && data.results.length > 0) {
                        output += `<h3>Results Preview</h3>
                                   <pre>${JSON.stringify(data.results.slice(0, 5), null, 2)}</pre>`;
                    }
                    
                    resultsDiv.innerHTML = output;
                } catch (error) {
                    resultsDiv.innerHTML = `Error: ${error.message}`;
                }
            }
        </script>
    </body>
    </html>
    """

@app.post("/analyze")
async def analyze_data(request: Request):
    """Analyze data based on natural language question"""
    data = await request.json()
    question = data.get("question")
    
    if not question:
        raise HTTPException(status_code=400, detail="Question is required")
    
    # Get schema information
    schema_context = schema_service.format_schema_for_prompt()
    
    # Generate query with AI
    query = ai_service.generate_query(question, schema_context)
    
    try:
        # Execute query
        query_results = trino_service.execute_query(query)
        
        # Analyze results with AI
        analysis = ai_service.analyze_results(
            question, 
            schema_context, 
            query_results["results"]
        )
        
        return {
            "question": question,
            "query": query,
            "results": query_results["results"],
            "analysis": analysis
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error executing query: {str(e)}")

if __name__ == "__main__":
    uvicorn.run("app.main:app", host=settings.APP_HOST, port=settings.APP_PORT, reload=True)