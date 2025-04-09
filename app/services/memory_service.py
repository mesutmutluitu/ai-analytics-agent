import chromadb
from chromadb.config import Settings
from app.config import settings
from app.logging.logger import log_error
import json
from datetime import datetime
import time
import os
from pathlib import Path

class MemoryService:
    def __init__(self):
        # Get the application root directory
        app_root = Path(__file__).parent.parent.parent
        
        # Set memory directory in the app root
        self.memory_dir = app_root / "memory_db"
        self.memory_dir.mkdir(exist_ok=True)
        
        print(f"Memory directory: {self.memory_dir}")  # Log the memory directory path
        
        # Initialize ChromaDB with persistence
        self.client = chromadb.PersistentClient(
            path=str(self.memory_dir),
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=False  # Prevent accidental data loss
            )
        )
        
        # Get or create the collection with proper configuration
        self.collection = self.client.get_or_create_collection(
            name="conversation_memory",
            metadata={
                "hnsw:space": "cosine",
                "description": "Stores conversation history and context"
            }
        )
        
        # Initialize memory stats
        self._update_memory_stats()
        
    def _update_memory_stats(self):
        """Update memory statistics"""
        try:
            self.memory_count = self.collection.count()
            self.last_updated = datetime.now()
        except Exception as e:
            log_error("memory_service", f"Error updating memory stats: {str(e)}", e)
            self.memory_count = 0
            self.last_updated = None
            
    def store_conversation(self, question, response, metadata=None):
        """Store a conversation in the vector database"""
        try:
            # Convert metadata to string if it's a dict
            if isinstance(metadata, dict):
                metadata = json.dumps(metadata)
                
            # Generate a unique ID with timestamp
            conversation_id = f"conv_{int(time.time())}_{self.memory_count}"
            
            # Store the conversation
            self.collection.add(
                documents=[response],
                metadatas=[{
                    "question": question,
                    "metadata": metadata or "",
                    "timestamp": str(datetime.now()),
                    "type": "conversation"
                }],
                ids=[conversation_id]
            )
            
            # Update memory stats
            self._update_memory_stats()
            
            return conversation_id
        except Exception as e:
            error_msg = f"Error storing conversation: {str(e)}"
            log_error("memory_service", error_msg, e)
            raise
            
    def get_relevant_memories(self, question, n_results=3):
        """Retrieve relevant past conversations"""
        try:
            results = self.collection.query(
                query_texts=[question],
                n_results=min(n_results, self.memory_count),  # Ensure we don't request more than available
                where={"type": "conversation"}  # Only get conversations
            )
            
            memories = []
            for i, (doc, meta) in enumerate(zip(results['documents'][0], results['metadatas'][0])):
                try:
                    memories.append({
                        "id": results['ids'][0][i],
                        "question": meta["question"],
                        "response": doc,
                        "metadata": json.loads(meta["metadata"]) if meta["metadata"] else None,
                        "timestamp": meta["timestamp"]
                    })
                except Exception as e:
                    log_error("memory_service", f"Error processing memory {i}: {str(e)}", e)
                    
            return memories
        except Exception as e:
            error_msg = f"Error retrieving memories: {str(e)}"
            log_error("memory_service", error_msg, e)
            return []
            
    def format_memories_for_prompt(self, memories):
        """Format memories for inclusion in AI prompt"""
        if not memories:
            return ""
            
        formatted = "\nRelevant past conversations:\n"
        for i, memory in enumerate(memories, 1):
            formatted += f"\n{i}. Question: {memory['question']}\n"
            formatted += f"   Response: {memory['response']}\n"
            if memory['metadata']:
                formatted += f"   Context: {json.dumps(memory['metadata'])}\n"
            formatted += f"   Time: {memory['timestamp']}\n"
                
        return formatted
        
    def get_memory_stats(self):
        """Get memory statistics"""
        return {
            "total_memories": self.memory_count,
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
            "memory_directory": str(self.memory_dir)
        }
        
    def cleanup_old_memories(self, days_to_keep=30):
        """Clean up old memories"""
        try:
            cutoff_time = time.time() - (days_to_keep * 24 * 60 * 60)
            old_memories = self.collection.get(
                where={"timestamp": {"$lt": str(datetime.fromtimestamp(cutoff_time))}}
            )
            
            if old_memories and old_memories['ids']:
                self.collection.delete(ids=old_memories['ids'])
                self._update_memory_stats()
                
            return len(old_memories['ids']) if old_memories else 0
        except Exception as e:
            error_msg = f"Error cleaning up old memories: {str(e)}"
            log_error("memory_service", error_msg, e)
            return 0 