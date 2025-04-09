from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from typing import Dict, Any, Callable
import uvicorn
import json
import time
from datetime import datetime
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.config import settings
from app.services.trino_service import TrinoService
from app.services.schema_service import SchemaService
from app.services.ai_service import AIService
from app.services.error_service import ErrorService
from app.logging.logger import log_api_request, log_api_response, log_error
from app.services.status_service import StatusService
from app.services.memory_service import MemoryService
from app.services.iam_service import IAMService
from app.core.logging import logger

app = FastAPI(title="AI Analytics Agent")
error_service = ErrorService()
status_service = StatusService()
iam_service = IAMService()

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
memory_service = MemoryService()

# Security
security = HTTPBearer()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get current user from JWT token"""
    try:
        if not credentials:
            raise HTTPException(
                status_code=401,
                detail="No credentials provided (Source: Missing Authorization header)"
            )
            
        token = credentials.credentials
        if not token:
            raise HTTPException(
                status_code=401,
                detail="No token provided (Source: Empty token)"
            )
            
        user = iam_service.verify_token(token)
        if not user:
            raise HTTPException(
                status_code=401,
                detail="Invalid token (Source: Token verification failed)"
            )
        return user
    except HTTPException:
        raise
    except Exception as e:
        logger.log_error("auth", f"Token verification error: {str(e)}", e)
        raise HTTPException(
            status_code=401,
            detail=f"Authentication failed (Source: {str(e)})"
        )

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
        error = error_service.handle_error(
            "request_error",
            e,
            {
                "route": str(request.url.path),
                "method": request.method,
                "process_time": process_time
            }
        )
        raise error

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Login page"""
    # Check if Authorization header exists
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        try:
            token = auth_header.split(" ")[1]
            # Verify token
            user = iam_service.verify_token(token)
            if user:
                # Token is valid, redirect to dashboard
                return RedirectResponse(url="/dashboard")
        except Exception:
            # Token is invalid, show login page
            pass
            
    return Jinja2Templates(directory="app/templates").TemplateResponse(
        "login.html",
        {"request": request}
    )

@app.post("/login")
async def login(request: Request):
    """Login endpoint"""
    try:
        data = await request.json()
        username = data.get("username")
        password = data.get("password")
        
        if not username or not password:
            raise HTTPException(
                status_code=400,
                detail="Username and password are required"
            )
            
        result = iam_service.authenticate_user(username, password)
        if not result:
            raise HTTPException(
                status_code=401,
                detail="Invalid username or password"
            )
            
        return JSONResponse(content=result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.log_error("auth", "Login error", e)
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, user: dict = Depends(get_current_user)):
    """Dashboard page"""
    if not iam_service.check_permission(user["role"], "ai-analytics", "view"):
        raise HTTPException(
            status_code=403,
            detail="You don't have permission to access this resource"
        )
        
    return Jinja2Templates(directory="app/templates").TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "permissions": iam_service.permissions
        }
    )

@app.post("/analyze")
async def analyze_data(
    request: Request,
    user: dict = Depends(get_current_user)
):
    """Analyze data based on natural language question"""
    if not iam_service.check_permission(user["role"], "ai-analytics", "view"):
        raise HTTPException(
            status_code=403,
            detail="You don't have permission to access this resource"
        )
        
    start_time = time.time()
    
    try:
        # Get request body
        data = await request.json()
        question = data.get("question")
        
        # Log request
        logger.log_activity(user["username"], "analyze", {"question": question})
        
        if not question:
            raise HTTPException(
                status_code=400,
                detail="Question is required"
            )
        
        # Get schema information
        schema_context = trino_service.get_schema_context()
        
        # Generate query with AI
        try:
            query = ai_service.generate_query(question, schema_context)
        except Exception as e:
            return {
                "question": question,
                "error": {
                    "type": "ai_service_error",
                    "message": str(e),
                    "suggestion": "Please make sure Ollama service is running and try again."
                }
            }
        
        # Execute query
        query_results = trino_service.execute_query(query)
        
        if "error" in query_results:
            raise HTTPException(
                status_code=500,
                detail=query_results["error"]
            )
        
        # Analyze results with AI
        try:
            analysis = ai_service.analyze_results(
                question, 
                schema_context, 
                query_results["results"]
            )
        except Exception as e:
            return {
                "question": question,
                "query": query,
                "results": query_results["results"],
                "error": {
                    "type": "ai_service_error",
                    "message": str(e),
                    "suggestion": "Please make sure Ollama service is running and try again."
                }
            }
        
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
    except HTTPException:
        raise
    except Exception as e:
        logger.log_error("analysis", "Analysis error", e)
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )

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
        raise error_service.handle_error(
            "validation_error",
            ValueError(f"Invalid log type. Must be one of: {', '.join(valid_log_types)}"),
            {"log_type": log_type}
        )
        
    try:
        # Log viewing logic here
        return {"message": f"Viewing {lines} lines of {log_type} logs"}
    except Exception as e:
        raise error_service.handle_error(
            "log_error",
            e,
            {"log_type": log_type, "lines": lines}
        )

@app.get("/status")
async def get_status(user: dict = Depends(get_current_user)):
    """Get service status"""
    if not iam_service.check_permission(user["role"], "ai-analytics", "view"):
        raise HTTPException(
            status_code=403,
            detail="You don't have permission to access this resource"
        )
        
    try:
        # Check Trino status
        trino_status = "running" if trino_service.check_connection() else "down"
        
        # Check Memory status
        memory_stats = memory_service.get_memory_stats()
        memory_status = "running" if memory_stats["total_memories"] >= 0 else "down"
        
        # Check Ollama status
        ollama_status = "running" if ai_service.check_ollama_availability() else "down"
        
        return {
            "trino": {
                "status": trino_status,
                "message": f"Trino service is {trino_status}"
            },
            "memory": {
                "status": memory_status,
                "message": f"Memory service is {memory_status} with {memory_stats['total_memories']} memories"
            },
            "ollama": {
                "status": ollama_status,
                "message": f"Ollama service is {ollama_status}"
            },
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
    except Exception as e:
        logger.log_error("status", "Status check error", e)
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )

if __name__ == "__main__":
    uvicorn.run("app.main:app", host=settings.APP_HOST, port=settings.APP_PORT, reload=True)