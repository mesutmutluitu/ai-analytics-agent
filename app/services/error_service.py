from fastapi import HTTPException
from app.logging.logger import log_error
import traceback
from typing import Dict, Any, Optional

class ErrorService:
    def __init__(self):
        self.error_templates = {
            "database_error": {
                "status_code": 500,
                "detail": "Database operation failed",
                "message": "An error occurred while accessing the database"
            },
            "ai_error": {
                "status_code": 500,
                "detail": "AI service error",
                "message": "An error occurred while processing your request with AI"
            },
            "memory_error": {
                "status_code": 500,
                "detail": "Memory service error",
                "message": "An error occurred while accessing conversation memory"
            },
            "validation_error": {
                "status_code": 400,
                "detail": "Validation error",
                "message": "Invalid input provided"
            }
        }
        
    def handle_error(self, 
                    error_type: str, 
                    error: Exception, 
                    context: Optional[Dict[str, Any]] = None) -> HTTPException:
        """Handle and format errors for display"""
        try:
            # Get error template
            template = self.error_templates.get(error_type, {
                "status_code": 500,
                "detail": "Unknown error",
                "message": "An unexpected error occurred"
            })
            
            # Log the error
            log_error(
                error_type,
                f"Error: {str(error)}\nContext: {context}\nTraceback: {traceback.format_exc()}",
                error
            )
            
            # Create error response
            error_response = {
                "error": {
                    "type": error_type,
                    "message": template["message"],
                    "detail": template["detail"],
                    "context": context or {}
                }
            }
            
            # Return HTTP exception
            return HTTPException(
                status_code=template["status_code"],
                detail=error_response
            )
            
        except Exception as e:
            # If error handling itself fails
            return HTTPException(
                status_code=500,
                detail={
                    "error": {
                        "type": "error_handling_failed",
                        "message": "Failed to handle the error",
                        "detail": str(e)
                    }
                }
            )
            
    def format_error_for_display(self, error: HTTPException) -> str:
        """Format error for display in the UI"""
        error_detail = error.detail
        if isinstance(error_detail, dict) and "error" in error_detail:
            error_info = error_detail["error"]
            return f"""
            <div class="error-container">
                <h3>Error: {error_info['type']}</h3>
                <p><strong>Message:</strong> {error_info['message']}</p>
                <p><strong>Details:</strong> {error_info['detail']}</p>
                {self._format_context(error_info.get('context', {}))}
            </div>
            """
        return str(error_detail)
        
    def _format_context(self, context: Dict[str, Any]) -> str:
        """Format context information for display"""
        if not context:
            return ""
            
        context_html = "<p><strong>Context:</strong></p><ul>"
        for key, value in context.items():
            context_html += f"<li><strong>{key}:</strong> {value}</li>"
        context_html += "</ul>"
        return context_html 