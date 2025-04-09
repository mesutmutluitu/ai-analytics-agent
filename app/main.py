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
                detail="[Auth Layer] No credentials provided (Component: Security Middleware)"
            )
            
        token = credentials.credentials
        if not token:
            raise HTTPException(
                status_code=401,
                detail="[Auth Layer] No token provided (Component: Token Validator)"
            )
            
        user = iam_service.verify_token(token)
        if not user:
            raise HTTPException(
                status_code=401,
                detail="[Auth Layer] Invalid token (Component: IAM Service)"
            )
        return user
    except HTTPException:
        raise
    except Exception as e:
        logger.log_error("auth", f"Token verification error: {str(e)}", e)
        raise HTTPException(
            status_code=401,
            detail=f"[Auth Layer] Authentication failed (Component: {e.__class__.__name__})"
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
        response.headers["X-Component"] = "API Gateway"
        
        return response
    except Exception as e:
        process_time = time.time() - start_time
        error = error_service.handle_error(
            "request_error",
            e,
            {
                "route": str(request.url.path),
                "method": request.method,
                "process_time": process_time,
                "component": "API Gateway",
                "layer": "Middleware"
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
                detail="[Auth Layer] Username and password are required (Component: Login Handler)"
            )
            
        result = iam_service.authenticate_user(username, password)
        if not result:
            raise HTTPException(
                status_code=401,
                detail="[Auth Layer] Invalid username or password (Component: IAM Service)"
            )
            
        # Set token in response headers
        response = JSONResponse(content=result)
        response.headers["Authorization"] = f"Bearer {result['token']}"
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.log_error("auth", "Login error", e)
        raise HTTPException(
            status_code=500,
            detail=f"[Auth Layer] Internal server error (Component: Login Handler) - {str(e)}"
        )

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Dashboard page"""
    try:
        # Get token from query parameters
        token = request.query_params.get("token")
        if not token:
            # Try to get token from localStorage
            return Jinja2Templates(directory="app/templates").TemplateResponse(
                "dashboard.html",
                {
                    "request": request,
                    "token": token
                }
            )
            
        # Verify token
        user = iam_service.verify_token(token)
        if not user:
            raise HTTPException(
                status_code=401,
                detail="[Auth Layer] Invalid token (Component: IAM Service)"
            )
            
        logger.log_info("dashboard", f"Accessing dashboard for user: {user['username']}")
        
        if not iam_service.check_permission(user["role"], "ai-analytics", "view"):
            raise HTTPException(
                status_code=403,
                detail="[Auth Layer] Permission denied (Component: Permission Checker)"
            )
            
        return Jinja2Templates(directory="app/templates").TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "user": user,
                "permissions": iam_service.permissions,
                "token": token
            }
        )
    except HTTPException as e:
        logger.log_error("dashboard", f"Dashboard access error: {e.detail}")
        raise
    except Exception as e:
        logger.log_error("dashboard", f"Unexpected error in dashboard: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"[Dashboard Layer] Internal server error (Component: Dashboard Handler) - {str(e)}"
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
            logger.log_info("analyze", f"Generated SQL query: {query}")
        except Exception as e:
            logger.log_error("analyze", f"Error generating query: {str(e)}", e)
            raise HTTPException(
                status_code=500,
                detail=f"Error generating query: {str(e)}"
            )
        
        # Execute query
        try:
            result = trino_service.execute_query(query)
            logger.log_info("analyze", "Query executed successfully")
        except Exception as e:
            logger.log_error("analyze", f"Error executing query: {str(e)}", e)
            raise HTTPException(
                status_code=500,
                detail=f"Error executing query: {str(e)}"
            )
        
        # Analyze results with AI
        try:
            analysis = ai_service.analyze_results(result, question)
            logger.log_info("analyze", "Results analyzed successfully")
        except Exception as e:
            logger.log_error("analyze", f"Error analyzing results: {str(e)}", e)
            raise HTTPException(
                status_code=500,
                detail=f"Error analyzing results: {str(e)}"
            )
        
        # Calculate processing time
        process_time = time.time() - start_time
        
        # Log success
        logger.log_info("analyze", f"Analysis completed in {process_time:.2f} seconds")
        
        return {
            "result": analysis,
            "sql": query,
            "process_time": process_time
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.log_error("analyze", f"Unexpected error: {str(e)}", e)
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
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
async def get_status(request: Request):
    """Get service status"""
    try:
        # Get token from query parameters
        token = request.query_params.get("token")
        if not token:
            raise HTTPException(
                status_code=401,
                detail="[Auth Layer] No token provided (Component: Status Checker)"
            )
            
        # Verify token
        user = iam_service.verify_token(token)
        if not user:
            raise HTTPException(
                status_code=401,
                detail="[Auth Layer] Invalid token (Component: IAM Service)"
            )
            
        # Check permissions
        if not iam_service.check_permission(user["role"], "ai-analytics", "view"):
            raise HTTPException(
                status_code=403,
                detail="[Auth Layer] Permission denied (Component: Permission Checker)"
            )
            
        # Get status
        status = status_service.get_status()
        return status
        
    except HTTPException:
        raise
    except Exception as e:
        logger.log_error("status", f"Status check error: {str(e)}", e)
        raise HTTPException(
            status_code=500,
            detail=f"[Status Layer] Internal server error (Component: Status Service) - {str(e)}"
        )

if __name__ == "__main__":
    uvicorn.run("app.main:app", host=settings.APP_HOST, port=settings.APP_PORT, reload=True)