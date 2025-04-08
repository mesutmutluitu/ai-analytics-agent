import requests
import json
from ..config import settings

class AIService:
    def __init__(self):
        self.api_url = f"{settings.OLLAMA_API_URL}/generate"
        self.model = settings.OLLAMA_MODEL
        
    def query_model(self, prompt):
        """Query the Ollama model with a prompt"""
        try:
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
                return json.loads(response.text)["response"]
            else:
                return f"Error: Received status code {response.status_code}"
                
        except Exception as e:
            return f"Error querying model: {str(e)}"
            
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
        
        return self.query_model(prompt)
    
    def analyze_results(self, question, schema_context, results):
        """Analyze query results with AI"""
        prompt = f"""
        Given the question: "{question}"
        The database schema: {schema_context}
        And the query results: {json.dumps(results, default=str)}
        
        Please provide a detailed analysis of these results in natural language.
        Consider relationships between values, patterns, outliers, and significance of the findings.
        """
        
        return self.query_model(prompt)