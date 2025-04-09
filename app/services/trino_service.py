import trino
from app.config import settings
from app.logging.logger import log_error

class TrinoService:
    def __init__(self):
        try:
            self.conn = trino.dbapi.connect(
                host=settings.TRINO_HOST,
                port=settings.TRINO_PORT,
                user=settings.TRINO_USER,
                catalog=settings.TRINO_DEFAULT_CATALOG,
                schema=settings.TRINO_DEFAULT_SCHEMA
            )
        except Exception as e:
            error_msg = f"Failed to connect to Trino server at {settings.TRINO_HOST}:{settings.TRINO_PORT}. Please check if the server is running and the connection details are correct."
            log_error("trino_service", error_msg, e)
            raise Exception(error_msg)
        
    def execute_query(self, query):
        """Execute a Trino SQL query and return results"""
        try:
            cursor = self.conn.cursor()
            cursor.execute(query)
            columns = [desc[0] for desc in cursor.description]
            results = [dict(zip(columns, row)) for row in cursor.fetchall()]
            return {"results": results, "columns": columns}
        except Exception as e:
            error_msg = f"Failed to execute query. Please check if the Trino server is running and accessible. Error details: {str(e)}"
            log_error("trino_service", error_msg, e)
            return {"error": error_msg}