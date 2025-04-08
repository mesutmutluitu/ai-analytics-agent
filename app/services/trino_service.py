import trino
from ..config import settings

class TrinoService:
    def __init__(self):
        self.connection = None
        self.connect()
        
    def connect(self):
        """Create a connection to Trino server"""
        self.connection = trino.dbapi.connect(
            host=settings.TRINO_HOST,
            port=settings.TRINO_PORT,
            user=settings.TRINO_USER,
            catalog=settings.TRINO_DEFAULT_CATALOG,
            schema=settings.TRINO_DEFAULT_SCHEMA
        )
        return self.connection
    
    def execute_query(self, query):
        """Execute a query and return results"""
        cursor = self.connection.cursor()
        cursor.execute(query)
        
        # Get column names from cursor description
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        
        # Fetch results
        rows = cursor.fetchall()
        
        # Convert to list of dictionaries
        results = [dict(zip(columns, row)) for row in rows]
        
        return {
            "columns": columns,
            "rows": rows,
            "results": results
        }