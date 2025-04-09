import requests
import chromadb
from app.config import settings
from app.logging.logger import log_error
import time
import trino
from typing import Dict, Any
from datetime import datetime
from app.core.logging import logger
from app.services.trino_service import TrinoService
from app.services.memory_service import MemoryService
from app.services.ai_service import AIService

class StatusService:
    def __init__(self, trino_service: TrinoService, memory_service: MemoryService, ai_service: AIService):
        self.trino_service = trino_service
        self.memory_service = memory_service
        self.ai_service = ai_service
        self.ollama_url = settings.OLLAMA_API_URL
        
    def check_trino_status(self) -> Dict[str, Any]:
        """Check Trino service status"""
        try:
            if not self.trino_service:
                logger.log_error("status", "Trino service not initialized")
                return {
                    "status": "down",
                    "message": "Trino service not initialized"
                }
                
            # Try to execute a real query
            try:
                result = self.trino_service.execute_query("SHOW CATALOGS")
                if not result or "error" in result:
                    logger.log_error("status", "Trino query failed", result.get("error"))
                    return {
                        "status": "down",
                        "message": f"Trino query failed: {result.get('error', 'Unknown error')}"
                    }
                
                logger.log_info("status", "Trino service is running and responding to queries")
                return {
                    "status": "running",
                    "message": "Trino service is running and responding to queries"
                }
                
            except Exception as e:
                logger.log_error("status", f"Trino query execution error: {str(e)}", e)
                return {
                    "status": "down",
                    "message": f"Trino query execution error: {str(e)}"
                }
                
        except Exception as e:
            logger.log_error("status", f"Trino service check error: {str(e)}", e)
            return {
                "status": "down",
                "message": f"Trino service check error: {str(e)}"
            }
            
    def check_memory_status(self) -> Dict[str, Any]:
        """Check Memory service status"""
        try:
            if not self.memory_service:
                logger.log_error("status", "Memory service not initialized")
                return {
                    "status": "down",
                    "message": "Memory service not initialized"
                }
                
            # Try to get memory stats
            stats = self.memory_service.get_memory_stats()
            logger.log_info("status", f"Memory service is running with {stats['total_memories']} memories")
            return {
                "status": "running",
                "message": f"Memory service is running with {stats['total_memories']} memories"
            }
        except Exception as e:
            logger.log_error("status", f"Memory service is down: {str(e)}", e)
            return {
                "status": "down",
                "message": f"Memory service is down: {str(e)}"
            }
            
    def check_ollama_status(self) -> Dict[str, Any]:
        """Check Ollama service status"""
        try:
            if not self.ai_service:
                logger.log_error("status", "AI service not initialized")
                return {
                    "status": "down",
                    "message": "AI service not initialized"
                }
                
            # Check if Ollama is available
            is_available = self.ai_service.check_ollama_availability()
            if is_available:
                logger.log_info("status", "Ollama service is running")
                return {
                    "status": "running",
                    "message": "Ollama service is running"
                }
            else:
                logger.log_error("status", "Ollama service is down")
                return {
                    "status": "down",
                    "message": "Ollama service is down"
                }
        except Exception as e:
            logger.log_error("status", f"Ollama service check error: {str(e)}", e)
            return {
                "status": "down",
                "message": f"Ollama service check error: {str(e)}"
            }
            
    def get_status(self) -> Dict[str, Any]:
        """Get status of all services"""
        try:
            trino_status = self.check_trino_status()
            memory_status = self.check_memory_status()
            ollama_status = self.check_ollama_status()
            
            return {
                "trino": trino_status,
                "memory": memory_status,
                "ollama": ollama_status,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        except Exception as e:
            logger.log_error("status", f"Error getting status: {str(e)}", e)
            return {
                "trino": {"status": "unknown", "message": "Error checking status"},
                "memory": {"status": "unknown", "message": "Error checking status"},
                "ollama": {"status": "unknown", "message": "Error checking status"},
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            } 