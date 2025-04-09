from typing import Dict, Any, List, Optional
import httpx
import json
from datetime import datetime
from app.config import settings
from app.services.memory_service import MemoryService
from app.services.error_service import ErrorService
from app.services.trino_service import TrinoService

class AIService:
    def __init__(self, trino_service: TrinoService, memory_service: MemoryService):
        self.trino_service = trino_service
        self.memory_service = memory_service
        self.base_url = "http://localhost:11434"
        self.model = "llama2"
        self.conversation_history = []
        self.analysis_context = {
            "user_type": None,  # "technical" or "business"
            "time_period": None,
            "scope": None,
            "metrics": [],
            "tables": [],
            "columns": [],
            "relationships": []
        }
        self.api_url = f"{settings.OLLAMA_API_URL}/generate"
        self.error_service = ErrorService()
        
    async def check_ollama_availability(self) -> bool:
        """Check if Ollama service is available"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/api/tags")
                return response.status_code == 200
        except Exception:
            return False
        
    async def get_database_schema(self) -> Dict[str, Any]:
        """Get database schema information from Trino"""
        try:
            # Get tables
            tables_query = """
                SELECT table_schema, table_name 
                FROM information_schema.tables 
                WHERE table_schema NOT IN ('information_schema', 'sys')
            """
            tables_result = await self.trino_service.execute_query(tables_query)
            
            schema_info = {}
            for table in tables_result:
                schema = table['table_schema']
                table_name = table['table_name']
                
                # Get columns for each table
                columns_query = f"""
                    SELECT column_name, data_type 
                    FROM information_schema.columns 
                    WHERE table_schema = '{schema}' 
                    AND table_name = '{table_name}'
                """
                columns_result = await self.trino_service.execute_query(columns_query)
                
                if schema not in schema_info:
                    schema_info[schema] = {}
                
                schema_info[schema][table_name] = [
                    {"name": col['column_name'], "type": col['data_type']}
                    for col in columns_result
                ]
            
            return schema_info
        except Exception as e:
            print(f"Error getting database schema: {str(e)}")
            return {}

    async def determine_user_type(self, user_input: str) -> str:
        """Determine if user is technical or business user based on their input"""
        prompt = f"""
        Analyze the following user input and determine if the user is a technical or business user.
        Technical users typically use technical terms, mention specific metrics, or ask for detailed data.
        Business users typically ask about business outcomes, trends, or general insights.
        
        User Input: {user_input}
        
        Respond with only "technical" or "business".
        """
        
        response = await self.query_model(prompt)
        return response.lower().strip()

    async def generate_follow_up_questions(self, user_input: str, schema_info: Dict[str, Any]) -> List[str]:
        """Generate relevant follow-up questions based on user input and database schema"""
        prompt = f"""
        As a data analyst, generate follow-up questions to clarify the user's analysis request.
        Consider the following context:
        
        User Input: {user_input}
        Database Schema: {json.dumps(schema_info, indent=2)}
        
        Generate 3-5 specific questions that will help:
        1. Clarify the time period of interest
        2. Identify relevant metrics
        3. Determine the scope of analysis
        4. Select appropriate tables and columns
        
        Format the response as a JSON array of questions.
        """
        
        response = await self.query_model(prompt)
        try:
            return json.loads(response)
        except:
            return ["Could you clarify the time period you're interested in?",
                   "What specific metrics would you like to analyze?",
                   "What is the scope of your analysis?"]

    async def update_analysis_context(self, user_response: str) -> None:
        """Update analysis context based on user's response"""
        prompt = f"""
        Update the analysis context based on the user's response.
        Current Context: {json.dumps(self.analysis_context, indent=2)}
        User Response: {user_response}
        
        Update the following fields if information is provided:
        - time_period
        - scope
        - metrics
        - tables
        - columns
        - relationships
        
        Respond with the updated context as JSON.
        """
        
        response = await self.query_model(prompt)
        try:
            updated_context = json.loads(response)
            self.analysis_context.update(updated_context)
        except:
            pass

    async def is_context_complete(self) -> bool:
        """Check if we have enough information to generate SQL"""
        required_fields = ['time_period', 'scope', 'metrics']
        return all(self.analysis_context.get(field) for field in required_fields)

    async def generate_sql_query(self) -> str:
        """Generate SQL query based on collected context"""
        prompt = f"""
        Generate a SQL query based on the following analysis context:
        {json.dumps(self.analysis_context, indent=2)}
        
        Consider the following:
        1. Use appropriate table joins
        2. Include necessary filters for time period
        3. Calculate requested metrics
        4. Group by relevant dimensions
        
        Respond with only the SQL query.
        """
        
        return await self.query_model(prompt)

    async def analyze_with_context(self, user_input: str) -> Dict[str, Any]:
        """Main analysis function using chain of thought approach"""
        if not await self.check_ollama_availability():
            return {
                "error": "Ollama service is not available",
                "status": "error"
            }

        try:
            # Initialize or reset context
            self.analysis_context = {
                "user_type": None,
                "time_period": None,
                "scope": None,
                "metrics": [],
                "tables": [],
                "columns": [],
                "relationships": []
            }

            # Determine user type
            user_type = await self.determine_user_type(user_input)
            self.analysis_context["user_type"] = user_type

            # Get database schema
            schema_info = await self.get_database_schema()

            # Generate initial follow-up questions
            questions = await self.generate_follow_up_questions(user_input, schema_info)

            return {
                "status": "questions",
                "questions": questions,
                "context": self.analysis_context
            }

        except Exception as e:
            return {
                "error": f"Error in analysis: {str(e)}",
                "status": "error"
            }

    async def continue_analysis(self, user_response: str) -> Dict[str, Any]:
        """Continue analysis with user's response"""
        if not await self.check_ollama_availability():
            return {
                "error": "Ollama service is not available",
                "status": "error"
            }

        try:
            # Update context with user's response
            await self.update_analysis_context(user_response)

            # Check if we have enough information
            if await self.is_context_complete():
                # Generate and execute SQL query
                sql_query = await self.generate_sql_query()
                query_result = await self.trino_service.execute_query(sql_query)

                # Analyze results
                analysis = await self.analyze_results(query_result)

                return {
                    "status": "complete",
                    "analysis": analysis,
                    "sql_query": sql_query,
                    "context": self.analysis_context
                }
            else:
                # Generate more follow-up questions
                schema_info = await self.get_database_schema()
                questions = await self.generate_follow_up_questions(
                    f"Previous context: {json.dumps(self.analysis_context)}\nUser response: {user_response}",
                    schema_info
                )

                return {
                    "status": "questions",
                    "questions": questions,
                    "context": self.analysis_context
                }

        except Exception as e:
            return {
                "error": f"Error in analysis: {str(e)}",
                "status": "error"
            }

    async def query_model(self, prompt: str) -> str:
        """Query the Ollama model"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False
                    }
                )
                if response.status_code == 200:
                    return response.json()["response"]
                else:
                    raise Exception(f"Model query failed: {response.text}")
        except Exception as e:
            raise Exception(f"Error querying model: {str(e)}")

    async def analyze_results(self, results: List[Dict[str, Any]]) -> str:
        """Analyze query results using the LLM"""
        try:
            prompt = f"""
            Analyze the following query results and provide insights:
            
            Results: {json.dumps(results, indent=2)}
            
            Context: {json.dumps(self.analysis_context, indent=2)}
            
            Provide a detailed analysis focusing on:
            1. Key findings and trends
            2. Significant patterns or anomalies
            3. Business implications
            4. Recommendations
            
            Format the response in clear sections with bullet points where appropriate.
            """
            
            return await self.query_model(prompt)
        except Exception as e:
            raise Exception(f"Error analyzing results: {str(e)}")

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
            # Try to execute a simple query to check connection
            result = self.trino_service.execute_query("SELECT 1")
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
            # Execute with LIMIT 1 to test the query without fetching all results
            test_query = f"WITH test_query AS ({query}) SELECT * FROM test_query LIMIT 1"
            print(f"Test query to be executed: {test_query}")  # Log the test query
            
            try:
                result = self.trino_service.execute_query(test_query)
                
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
                    result = self.trino_service.execute_query(test_query)
                    
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