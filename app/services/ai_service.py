import requests
import json
from app.config import settings
from app.services.memory_service import MemoryService
from app.services.error_service import ErrorService

class AIService:
    def __init__(self):
        self.api_url = f"{settings.OLLAMA_API_URL}/generate"
        self.model = settings.OLLAMA_MODEL
        self.memory_service = MemoryService()
        self.error_service = ErrorService()
        
    def check_ollama_availability(self):
        """Check if Ollama service is available"""
        try:
            response = requests.get(f"{settings.OLLAMA_API_URL}/api/tags", timeout=5)
            return response.status_code == 200
        except:
            return False
        
    def query_model(self, prompt, prompt_type="general"):
        """Query the Ollama model with a prompt"""
        if not self.check_ollama_availability():
            raise Exception("Ollama service is not available. Please make sure Ollama is running.")
            
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
            
    def validate_sql_query(self, query):
        """Validate SQL query for Trino compatibility"""
        # Remove comments
        query = query.split('--')[0].strip()
        
        # Check for invalid characters
        invalid_chars = [':', ';', '--', '/*', '*/']
        for char in invalid_chars:
            if char in query:
                return False, f"Invalid character '{char}' found in query"
        
        # Check for basic SQL structure
        if not query.upper().startswith('SELECT'):
            return False, "Query must start with SELECT"
            
        # Check for proper FROM clause
        if 'FROM' not in query.upper():
            return False, "Query must contain a FROM clause"
            
        # Check for proper JOIN syntax
        if 'JOIN' in query.upper():
            if not any(join_type in query.upper() for join_type in ['INNER JOIN', 'LEFT JOIN', 'RIGHT JOIN', 'FULL JOIN']):
                return False, "Invalid JOIN syntax"
                
        # Check for proper WHERE clause
        if 'WHERE' in query.upper():
            where_clause = query.upper().split('WHERE')[1].strip()
            if not where_clause:
                return False, "WHERE clause cannot be empty"
                
        # Check for proper GROUP BY clause
        if 'GROUP BY' in query.upper():
            group_by_clause = query.upper().split('GROUP BY')[1].strip()
            if not group_by_clause:
                return False, "GROUP BY clause cannot be empty"
                
        # Check for proper ORDER BY clause
        if 'ORDER BY' in query.upper():
            order_by_clause = query.upper().split('ORDER BY')[1].strip()
            if not order_by_clause:
                return False, "ORDER BY clause cannot be empty"
                
        return True, "Query is valid"
        
    def check_trino_availability(self):
        """Check if Trino service is available"""
        try:
            from app.services.trino_service import TrinoService
            trino = TrinoService()
            # Try to execute a simple query to check connection
            result = trino.execute_query("SELECT 1")
            return "error" not in result
        except Exception as e:
            print(f"Trino service check failed: {str(e)}")  # Log the error
            return False
            
    def generate_query(self, question, schema_context):
        """Generate a Trino query from a natural language question"""
        if not self.check_ollama_availability():
            return "SELECT 'Ollama service is not available' as message"
            
        # Check Trino availability first
        if not self.check_trino_availability():
            return "SELECT 'Trino service is not available. Please make sure Trino is running.' as error"
            
        # Get relevant memories
        memories = self.memory_service.get_relevant_memories(question)
        memory_context = self.memory_service.format_memories_for_prompt(memories)
        
        prompt = f"""
        Given the following question: "{question}"
        
        Here is the database schema information:
        {schema_context}
        
        {memory_context}
        
        Generate a valid Trino SQL query that would answer this question.
        Important rules for Trino SQL:
        1. Use standard SQL syntax
        2. NEVER use ':' character in any part of the query
        3. Use proper table aliases (e.g., t1, t2) for joins
        4. Use standard SQL operators (=, <, >, etc.)
        5. Use proper date/time functions (e.g., DATE_TRUNC, DATE_ADD)
        6. Use proper string functions (e.g., CONCAT, SUBSTRING)
        7. Use proper aggregation functions (e.g., COUNT, SUM, AVG)
        8. Use proper window functions if needed (e.g., ROW_NUMBER, RANK)
        9. Use proper JOIN syntax (INNER JOIN, LEFT JOIN, etc.)
        10. Use proper WHERE clause syntax
        11. Do not use any special characters except standard SQL operators
        12. Use proper column aliases without special characters
        13. Do not use JSON or array syntax
        14. Do not use any special formatting
        
        Return only the SQL query without any explanation or comments.
        """
        
        query = self.query_model(prompt, "sql_generation")
        print(f"Generated initial query: {query}")  # Log the initial query
        
        # Clean up the query
        query = query.strip()
        if query.startswith("```sql"):
            query = query[6:]
        if query.endswith("```"):
            query = query[:-3]
        query = query.strip()
        print(f"Cleaned query: {query}")  # Log the cleaned query
        
        # Additional validation to ensure no ':' character is present
        if ':' in query:
            print(f"Query contains invalid ':' character: {query}")  # Log the invalid query
            # Try to generate a simpler query without special characters
            retry_prompt = f"""
            The previous query contained invalid characters. Please generate a new query that:
            1. Uses only basic SELECT, FROM, WHERE clauses
            2. Uses no special characters (especially ':')
            3. Uses simple column aliases (e.g., col1, col2)
            4. Uses standard SQL operators only
            5. Does not use any JSON or array syntax
            6. Does not use any special formatting
            
            Original question: "{question}"
            Schema: {schema_context}
            """
            
            query = self.query_model(retry_prompt, "sql_generation")
            query = query.strip()
            print(f"Retry generated query: {query}")  # Log the retry query
            
            # Final check for ':' character
            if ':' in query:
                print(f"Retry query still contains ':' character: {query}")  # Log the invalid retry query
                return "SELECT 'Invalid query: Query contains unsupported characters' as error"
        
        # Try to execute the query in Trino to validate it
        try:
            from app.services.trino_service import TrinoService
            trino = TrinoService()
            
            # Execute with LIMIT 1 to test the query without fetching all results
            test_query = f"WITH test_query AS ({query}) SELECT * FROM test_query LIMIT 1"
            print(f"Test query to be executed: {test_query}")  # Log the test query
            
            try:
                result = trino.execute_query(test_query)
                
                if "error" in result:
                    print(f"Query execution failed with error: {result['error']}")  # Log the error
                    # If the query fails, try to generate a simpler query
                    retry_prompt = f"""
                    The previous query failed in Trino with error: {result['error']}
                    Please generate a simpler query that follows these rules:
                    1. Use only basic SELECT, FROM, WHERE clauses
                    2. No complex joins or subqueries
                    3. No special characters (especially ':')
                    4. No comments
                    5. Make sure all table and column names exist in the schema
                    6. Do not use any JSON or array syntax
                    7. Do not use any special formatting
                    
                    Original question: "{question}"
                    Schema: {schema_context}
                    """
                    
                    query = self.query_model(retry_prompt, "sql_generation")
                    query = query.strip()
                    print(f"Second retry generated query: {query}")  # Log the second retry query
                    
                    # Try the simpler query
                    test_query = f"WITH test_query AS ({query}) SELECT * FROM test_query LIMIT 1"
                    print(f"Second test query to be executed: {test_query}")  # Log the second test query
                    result = trino.execute_query(test_query)
                    
                    if "error" in result:
                        print(f"Second query execution failed with error: {result['error']}")  # Log the error
                        return f"SELECT 'Invalid query generated: {result['error']}' as error"
                
            except Exception as query_error:
                print(f"Query execution failed: {str(query_error)}")  # Log the error
                return f"SELECT 'Error executing query: {str(query_error)}' as error"
                
        except Exception as trino_error:
            print(f"Trino service error: {str(trino_error)}")  # Log the error
            return f"SELECT 'Trino service error: {str(trino_error)}' as error"
        
        # Store the conversation
        self.memory_service.store_conversation(
            question=question,
            response=query,
            metadata={
                "type": "sql_generation",
                "schema_context": schema_context,
                "validation_status": "valid" if "error" not in result else "invalid",
                "validation_message": result.get("error", "Query is valid")
            }
        )
        
        return query
    
    def analyze_results(self, question, schema_context, results):
        """Analyze query results with AI"""
        if not self.check_ollama_availability():
            return "Ollama service is not available. Please make sure Ollama is running and try again."
            
        # Get relevant memories
        memories = self.memory_service.get_relevant_memories(question)
        memory_context = self.memory_service.format_memories_for_prompt(memories)
        
        prompt = f"""
        Given the question: "{question}"
        The database schema: {schema_context}
        And the query results: {json.dumps(results, default=str)}
        
        {memory_context}
        
        Please provide a detailed analysis of these results in natural language.
        Consider relationships between values, patterns, outliers, and significance of the findings.
        """
        
        analysis = self.query_model(prompt, "result_analysis")
        
        # Store the conversation
        self.memory_service.store_conversation(
            question=question,
            response=analysis,
            metadata={
                "type": "result_analysis",
                "schema_context": schema_context,
                "results": results
            }
        )
        
        return analysis