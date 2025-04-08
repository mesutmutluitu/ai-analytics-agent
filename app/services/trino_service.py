import time
import requests
import json
from config import settings
from app.logging.logger import log_ai_prompt, log_ai_response, log_error

class AIService:
    def __init__(self):
        self.api_url = f"{settings.OLLAMA_API_URL}/generate"
        self.model = settings.OLLAMA_MODEL
        
    def query_model(self, prompt, prompt_type="general"):
        """Query the Ollama model with a prompt"""
        start_time = time.time()
        
        try:
            log_ai_prompt(prompt_type, prompt)
            
            response = requests.post(
                self.api_url, 
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False
                },
                timeout=120  # Allow up to 2 minutes for complex queries
            )
            
            if response.status_code == 200:
                ai_response = json.loads(response.text)["response"]
                execution_time = time.time() - start_time
                log_ai_response(prompt_type, ai_response)
                return ai_response
            else:
                error_msg = f"Error: Received status code {response.status_code}"
                log_error("ai_service", error_msg)
                return error_msg
                
        except Exception as e:
            error_msg = f"Error querying model: {str(e)}"
            log_error("ai_service", error_msg, e)
            return error_msg
            
    def generate_query(self, question, schema_context):
        """Generate a Trino query from a natural language question"""
        prompt = f"""
        Given the following question: "{question}"
        
        Here is the database schema information:
        {schema_context}
        
        Generate a valid Trino SQL query that would answer this question.
        Ensure the query is optimized and includes proper join conditions if joining tables.
        Consider relationships between tables based on column names and data types.
        Return only the SQL query without any explanation.
        """
        
        return self.query_model(prompt, "sql_generation")
    
    def analyze_results(self, question, schema_context, results):
        """Analyze query results with AI"""
        prompt = f"""
        Given the question: "{question}"
        The database schema: {schema_context}
        And the query results: {json.dumps(results, default=str)}
        
        Please provide a detailed analysis of these results in natural language.
        Consider relationships between values, patterns, outliers, and significance of the findings.
        """
        
        return self.query_model(prompt, "result_analysis")