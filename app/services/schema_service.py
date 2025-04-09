import time
import trino
from app.config import settings
from app.logging.logger import log_trino_query, log_trino_result, log_error

class SchemaService:
    def __init__(self, trino_service):
        self.trino_service = trino_service
        self.schema_cache = {}
        self.last_cache_update = 0
        
    def get_schema(self):
        """Get database schema information"""
        current_time = time.time()
        if current_time - self.last_cache_update > settings.SCHEMA_CACHE_TTL:
            self.update_schema_cache()
        return self.schema_cache
        
    def update_schema_cache(self):
        """Update the schema cache"""
        try:
            # Get all catalogs
            catalogs_query = "SHOW CATALOGS"
            catalogs_result = self.trino_service.execute_query(catalogs_query)
            
            if "error" in catalogs_result:
                raise Exception(catalogs_result["error"])
                
            catalogs = [row["Catalog"] for row in catalogs_result["results"]]
            
            # Get schemas for each catalog
            schemas = {}
            for catalog in catalogs:
                schemas_query = f"SHOW SCHEMAS FROM {catalog}"
                schemas_result = self.trino_service.execute_query(schemas_query)
                
                if "error" in schemas_result:
                    continue
                    
                schemas[catalog] = [row["Schema"] for row in schemas_result["results"]]
            
            # Get tables for each schema
            tables = {}
            for catalog, schema_list in schemas.items():
                for schema in schema_list:
                    tables_query = f"SHOW TABLES FROM {catalog}.{schema}"
                    tables_result = self.trino_service.execute_query(tables_query)
                    
                    if "error" in tables_result:
                        continue
                        
                    tables[f"{catalog}.{schema}"] = [row["Table"] for row in tables_result["results"]]
            
            # Get columns for each table
            columns = {}
            for schema_path, table_list in tables.items():
                for table in table_list:
                    columns_query = f"DESCRIBE {schema_path}.{table}"
                    columns_result = self.trino_service.execute_query(columns_query)
                    
                    if "error" in columns_result:
                        continue
                        
                    columns[f"{schema_path}.{table}"] = [
                        {
                            "name": row["Column"],
                            "type": row["Type"],
                            "extra": row["Extra"],
                            "comment": row["Comment"]
                        }
                        for row in columns_result["results"]
                    ]
            
            self.schema_cache = {
                "catalogs": catalogs,
                "schemas": schemas,
                "tables": tables,
                "columns": columns
            }
            
            self.last_cache_update = time.time()
            
        except Exception as e:
            error_msg = f"Error updating schema cache: {str(e)}"
            log_error("schema_service", error_msg, e)
            raise
            
    def format_schema_for_prompt(self):
        """Format schema information for AI prompt"""
        schema = self.get_schema()
        
        formatted_schema = "Database Schema Information:\n\n"
        
        for catalog in schema["catalogs"]:
            formatted_schema += f"Catalog: {catalog}\n"
            
            if catalog in schema["schemas"]:
                for schema_name in schema["schemas"][catalog]:
                    formatted_schema += f"  Schema: {schema_name}\n"
                    
                    schema_path = f"{catalog}.{schema_name}"
                    if schema_path in schema["tables"]:
                        for table in schema["tables"][schema_path]:
                            formatted_schema += f"    Table: {table}\n"
                            
                            table_path = f"{schema_path}.{table}"
                            if table_path in schema["columns"]:
                                for column in schema["columns"][table_path]:
                                    formatted_schema += f"      Column: {column['name']} ({column['type']})"
                                    if column["comment"]:
                                        formatted_schema += f" - {column['comment']}"
                                    formatted_schema += "\n"
        
        return formatted_schema