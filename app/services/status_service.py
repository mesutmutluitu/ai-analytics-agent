import requests
import chromadb
from app.config import settings
from app.logging.logger import log_error
import time
import trino

class StatusService:
    def __init__(self):
        self.trino_service = None
        self.memory_service = None
        self.ollama_url = settings.OLLAMA_API_URL
        
    def check_trino_status(self):
        """Check if Trino server is accessible"""
        try:
            if not self.trino_service:
                from app.services.trino_service import TrinoService
                self.trino_service = TrinoService()
            return {
                "status": "running",
                "message": f"Connected to Trino at {settings.TRINO_HOST}:{settings.TRINO_PORT}"
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to connect to Trino: {str(e)}"
            }
            
    def check_memory_status(self):
        """Check if ChromaDB is accessible"""
        try:
            if not self.memory_service:
                from app.services.memory_service import MemoryService
                self.memory_service = MemoryService()
            return {
                "status": "running",
                "message": "ChromaDB is accessible"
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to connect to ChromaDB: {str(e)}"
            }
            
    def check_ollama_status(self):
        """Check if Ollama service is accessible"""
        try:
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=5)
            if response.status_code == 200:
                return {
                    "status": "running",
                    "message": f"Ollama is running with model: {settings.OLLAMA_MODEL}"
                }
            return {
                "status": "error",
                "message": f"Ollama returned status code: {response.status_code}"
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to connect to Ollama: {str(e)}"
            }
            
    def get_all_statuses(self):
        """Get status of all services"""
        return {
            "trino": self.check_trino_status(),
            "memory": self.check_memory_status(),
            "ollama": self.check_ollama_status(),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        } 