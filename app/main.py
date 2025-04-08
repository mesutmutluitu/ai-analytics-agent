from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from typing import Dict, Any, Callable
import uvicorn
import json
import time
from datetime import datetime

from config import settings
from app.services.trino_service import TrinoService
from app.services.schema_service import SchemaService
from app.services.ai_service import AIService
from app.logging.logger import log_api_request, log_api_response, log_error

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

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Middleware to log requests and responses"""
    # Generate request ID
    request_id = f"{datetime.now().strftime('%Y%m%d%H%M%S')}-{id(request)}"
    request.state.request_id = request_id
    
    # Log request
    log_api_request(
        route=str(request.url.path),
        method=request.method,
        params=dict(request.query_params),
    )
    
    # Time the request
    start_time = time.time()
    
    # Process request
    try:
        response = await call_next(request)
        process_time = time.time() - start_time
        
        # Log response
        log_api_response(
            route=str(request.url.path),
            status_code=response.status_code,
            response_time=process_time
        )
        
        # Add custom headers
        response.headers["X-Process-Time"] = str(process_time)
        response.headers["X-Request-ID"] = request_id
        
        return response
    except Exception as e:
        process_time = time.time() - start_time
        log_error("middleware", f"Error processing request: {str(e)}", e)
        raise

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
    start_time = time.time()
    
    try:
        # Get request body
        data = await request.json()
        question = data.get("question")
        
        # Log request body now that we have it
        log_api_request(
            route="/analyze",
            method="POST",
            body=data
        )
        
        if not question:
            raise HTTPException(status_code=400, detail="Question is required")
        
        # Get schema information
        schema_context = schema_service.format_schema_for_prompt()
        
        # Generate query with AI
        query = ai_service.generate_query(question, schema_context)
        
        # Execute query
        query_results = trino_service.execute_query(query)
        
        # Analyze results with AI
        analysis = ai_service.analyze_results(
            question, 
            schema_context, 
            query_results["results"]
        )
        
        # Calculate total processing time
        total_time = time.time() - start_time
        
        return {
            "question": question,
            "query": query,
            "results": query_results["results"],
            "analysis": analysis,
            "execution_stats": {
                "total_time": total_time,
                "query_execution_time": query_results.get("execution_time", 0)
            }
        }
    except Exception as e:
        log_error("analyze_endpoint", f"Error processing analyze request: {str(e)}", e)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0"
    }

@app.get("/logs/{log_type}")
async def view_logs(log_type: str, lines: int = 100):
    """View logs endpoint"""
    valid_log_types = ["app", "api", "trino", "ai", "prompts", "responses"]
    
    if log_type not in valid_log_types:
        raise HTTPException(status_code=400, detail=f"Invalid log type. Must be one of: {valid_log_types}")
    
    current_date = datetime.now().strftime("%Y-%m-%d")
    log_file = f"logs/{log_type}-{current_date}.log"
    
    try:
        if not os.path.exists(log_file):
            return {"logs": f"No logs found for {log_type} on {current_date}"}
            
        with open(log_file, "r") as f:
            # Get last N lines
            log_lines = f.readlines()[-lines:]
            return {"logs": "".join(log_lines)}
    except Exception as e:
        log_error("logs_endpoint", f"Error reading log file: {str(e)}", e)
        raise HTTPException(status_code=500, detail=f"Error reading log file: {str(e)}")

if __name__ == "__main__":
    uvicorn.run("app.main:app", host=settings.APP_HOST, port=settings.APP_PORT, reload=True)