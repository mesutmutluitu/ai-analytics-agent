from fastapi import FastAPI, HTTPException, Request, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from typing import Dict, Any, Callable, Optional
import uvicorn
import json
import time
from datetime import datetime
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from pydantic import BaseModel, constr, validator
import re

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
iam_service = IAMService()

# Security middleware
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"]  # In production, replace with specific hosts
)

app.add_middleware(GZipMiddleware, minimum_size=1000)

# CORS middleware with secure defaults
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8004"],  # In production, replace with specific hosts
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
    max_age=3600
)

# Security headers middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline';"
    return response

# Initialize services
trino_service = TrinoService()
schema_service = SchemaService(trino_service)
memory_service = MemoryService()
ai_service = AIService(trino_service=trino_service, memory_service=memory_service)
status_service = StatusService(trino_service, memory_service, ai_service)

# Security
security = HTTPBearer()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get current user from JWT token"""
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{current_time}] get_current_user called")
    logger.log_info("auth", f"get_current_user called at {current_time}")
    
    try:
        if not credentials:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials"
            )
            
        token = credentials.credentials
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="No token provided"
            )
            
        if not iam_service.verify_token(token):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )
            
        return token
    except HTTPException:
        raise
    except Exception as e:
        logger.log_error("auth", f"Token verification error: {str(e)}", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
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
            if iam_service.verify_token(token):
                print('Token is valid, redirect to dashboard')
                return RedirectResponse(url="/dashboard")
        except Exception:
            print('Token is invalid, show login page')# Token is invalid, show login page
            pass
            
    return Jinja2Templates(directory="app/templates").TemplateResponse(
        "login.html",
        {"request": request}
    )

# Input validation models
class LoginRequest(BaseModel):
    username: constr(min_length=3, max_length=50, pattern=r'^[a-zA-Z0-9_]+$')
    password: constr(min_length=8, max_length=100)

class AnalyzeRequest(BaseModel):
    query: str
    response: Optional[str] = None
    
    @validator('query')
    def validate_query(cls, v):
        # Prevent SQL injection attempts
        if re.search(r'[\'";]', v):
            raise ValueError('Invalid characters in query')
        return v

@app.post("/login")
async def login(login_request: LoginRequest):
    """Login endpoint with input validation"""
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{current_time}] login called")
    logger.log_info("auth", f"login called at {current_time}")
    
    try:
        result = iam_service.authenticate_user(login_request.username, login_request.password)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password"
            )
            
        # Set token in response headers
        response = JSONResponse(content=result)
        logger.log_info("auth", f"Login response: {response}")
        response.headers["Authorization"] = f"Bearer {result['token']}"
        return response
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid input: {str(e)}"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.log_error("auth", "Login error", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"[Auth Layer] Internal server error (Component: Login Handler) - {str(e)}"
        )

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, token: str = Depends(get_current_user)):
    """Dashboard page with authentication"""
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{current_time}] dashboard called")
    logger.log_info("dashboard", f"dashboard called at {current_time}")
    
    try:
        logger.log_info("dashboard", f"Accessing dashboard for token: {token}")
        
        if not iam_service.check_permission(token, "view_status"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied"
            )
            
        return Jinja2Templates(directory="app/templates").TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "token": token
            }
        )
    except HTTPException as e:
        logger.log_error("dashboard", f"Dashboard access error: {e.detail}")
        raise
    except Exception as e:
        logger.log_error("dashboard", f"Unexpected error in dashboard: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"[Dashboard Layer] Internal server error (Component: Dashboard Handler) - {str(e)}"
        )

@app.post("/analyze")
async def analyze(request: AnalyzeRequest, token: str = Depends(get_current_user)):
    """Analyze data with input validation"""
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{current_time}] analyze called")
    logger.log_info("analyze", f"analyze called at {current_time}")
    
    if not iam_service.check_permission(token, "analyze_data"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied"
        )
        
    start_time = time.time()
    
    try:
        if request.response:
            # Continue analysis with user's response
            result = await ai_service.continue_analysis(request.response)
        else:
            # Start new analysis
            result = await ai_service.analyze_with_context(request.query)

        if result["status"] == "error":
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.get("error", "Analysis failed")
            )
        
        # Calculate processing time
        process_time = time.time() - start_time
        
        # Log success
        logger.log_info("analyze", f"Analysis completed in {process_time:.2f} seconds")
        
        return result
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid input: {str(e)}"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.log_error("analyze", f"Unexpected error: {str(e)}", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
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
async def get_status(token: str = Depends(get_current_user)):
    """Get service status"""
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{current_time}] get_status called")
    logger.log_info("status", f"get_status called at {current_time}")
    
    if not iam_service.check_permission(token, "view_status"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied"
        )
    return status_service.get_status()

if __name__ == "__main__":
    uvicorn.run("app.main:app", host=settings.APP_HOST, port=settings.APP_PORT, reload=True)