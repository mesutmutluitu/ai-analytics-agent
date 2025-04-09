import requests
import chromadb
from app.config import settings
from app.logging.logger import log_error
import time
import trino
from typing import Dict, Any
from datetime import datetime
from app.core.logging import logger

class StatusService:
    def __init__(self):
        self.trino_service = None
        self.memory_service = None
        self.ai_service = None
        self.ollama_url = settings.OLLAMA_API_URL
        self.initialize_services()
        
    def initialize_services(self):
        """Initialize all services"""
        try:
            from app.services.trino_service import TrinoService
            from app.services.memory_service import MemoryService
            from app.services.ai_service import AIService
            
            self.trino_service = TrinoService()
            self.memory_service = MemoryService()
            self.ai_service = AIService()
            
            logger.log_info("status", "Services initialized successfully")
        except Exception as e:
            logger.log_error("status", f"Error initializing services: {str(e)}", e)
            
    def check_trino_status(self) -> Dict[str, Any]:
        """Check Trino service status"""
        try:
            if not self.trino_service:
                self.initialize_services()
                if not self.trino_service:
                    logger.log_error("status", "Trino service not initialized")
                    return {
                        "status": "down",
                        "message": "Trino service not initialized"
                    }
                
            # Try to execute a simple query
            result = self.trino_service.execute_query("SELECT 1")
            logger.log_info("status", "Trino service is running")
            return {
                "status": "running",
                "message": "Trino service is running"
            }
        except Exception as e:
            logger.log_error("status", f"Trino service is down: {str(e)}", e)
            return {
                "status": "down",
                "message": f"Trino service is down: {str(e)}"
            }
            
    def check_memory_status(self) -> Dict[str, Any]:
        """Check Memory service status"""
        try:
            if not self.memory_service:
                self.initialize_services()
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
                self.initialize_services()
                if not self.ai_service:
                    logger.log_error("status", "AI service not initialized")
                    return {
                        "status": "down",
                        "message": "AI service not initialized"
                    }
                
            # Try to check Ollama availability
            if self.ai_service.check_ollama_availability():
                logger.log_info("status", "Ollama service is running")
                return {
                    "status": "running",
                    "message": "Ollama service is running"
                }
            else:
                logger.log_error("status", "Ollama service is not available")
                return {
                    "status": "down",
                    "message": "Ollama service is not available"
                }
        except Exception as e:
            logger.log_error("status", f"Ollama service is down: {str(e)}", e)
            return {
                "status": "down",
                "message": f"Ollama service is down: {str(e)}"
            }
            
    def get_status(self) -> Dict[str, Any]:
        """Get all service statuses"""
        logger.log_info("status", "Checking all service statuses")
        status = {
            "trino": self.check_trino_status(),
            "memory": self.check_memory_status(),
            "ollama": self.check_ollama_status(),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        logger.log_info("status", f"Service status check completed: {status}")
        return status 