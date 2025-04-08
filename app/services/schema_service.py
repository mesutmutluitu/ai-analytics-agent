import time
from config import settings
from app.services.trino_service import TrinoService
from app.logging.logger import log_schema_update, log_error

class SchemaService:
    def __init__(self, trino_service=None):
        self.trino_service = trino_service or TrinoService()
        self.schema_cache = {}
        self.schema_cache_timestamp = 0
        
    def get_database_schema(self, force_refresh=False):
        """Get database schema with caching"""
        current_time = time.time()
        if (force_refresh or 
            not self.schema_cache or 
            current_time - self.schema_cache_timestamp > settings.SCHEMA_CACHE_TTL):
            
            self.schema_cache = self._fetch_schema()
            self.schema_cache_timestamp = current_time
            
        return self.schema_cache
    
    def _fetch_schema(self):
        """Fetch schema information from database"""
        schema_info = {}
        
        try:
            conn = self.trino_service.connection
            cursor = conn.cursor()
            
            # Get all catalogs
            cursor.execute("SHOW CATALOGS")
            catalogs = [row[0] for row in cursor.fetchall()]
            
            for catalog in catalogs:
                # Get all schemas in catalog
                cursor.execute(f"SHOW SCHEMAS FROM {catalog}")
                schemas = [row[0] for row in cursor.fetchall()]
                catalog_tables_count = 0
                
                for schema in schemas:
                    # Skip system schemas
                    if schema in ['information_schema', 'sys']:
                        continue
                        
                    # Get all tables in schema
                    try:
                        cursor.execute(f"SHOW TABLES FROM {catalog}.{schema}")
                        tables = [row[0] for row in cursor.fetchall()]
                        schema_tables_count = len(tables)
                        catalog_tables_count += schema_tables_count
                        
                        # Log schema update
                        log_schema_update(catalog, schema, schema_tables_count)
                        
                        for table in tables:
                            # Get columns and their types
                            cursor.execute(f"DESCRIBE {catalog}.{schema}.{table}")
                            columns = [(row[0], row[1], row[2] if len(row) > 2 else None) 
                                    for row in cursor.fetchall()]
                            
                            # Get basic statistics
                            table_stats = self._get_table_statistics(catalog, schema, table)
                            
                            if catalog not in schema_info:
                                schema_info[catalog] = {}
                            if schema not in schema_info[catalog]:
                                schema_info[catalog][schema] = {}
                            
                            schema_info[catalog][schema][table] = {
                                'columns': [{
                                    'name': col[0],
                                    'type': col[1],
                                    'description': col[2] if col[2] else f"Column {col[0]} in table {table}"
                                } for col in columns],
                                'statistics': table_stats
                            }
                    except Exception as e:
                        # Skip if no access or other issues
                        log_error("schema_service", f"Error fetching tables for {catalog}.{schema}", e)
                        continue
                    
                # Log catalog update
                log_schema_update(catalog, None, catalog_tables_count)
                    
        except Exception as e:
            log_error("schema_service", "Error fetching schema", e)
            
        return schema_info
    
    def _get_table_statistics(self, catalog, schema, table):
        """Get basic statistics for a table"""
        stats = {}
        
        try:
            conn = self.trino_service.connection
            cursor = conn.cursor()
            
            # Get table row count
            cursor.execute(f"SELECT count(*) FROM {catalog}.{schema}.{table}")
            row_count = cursor.fetchone()[0]
            stats["row_count"] = row_count
            
        except Exception as e:
            # If we can't get statistics, return empty dict
            log_error("schema_service", f"Error getting statistics for {catalog}.{schema}.{table}", e)
            
        return stats
    
    def format_schema_for_prompt(self):
        """Format schema info into a readable string for the prompt"""
        schema_info = self.get_database_schema()
        schema_text = []
        
        for catalog, schemas in schema_info.items():
            for schema, tables in schemas.items():
                for table, table_info in tables.items():
                    row_count = table_info.get('statistics', {}).get('row_count', 'unknown')
                    schema_text.append(f"Table: {catalog}.{schema}.{table} (Rows: {row_count})")
                    schema_text.append("Columns:")
                    for col in table_info['columns']:
                        schema_text.append(f"  - {col['name']} ({col['type']}): {col['description']}")
                    schema_text.append("")
        
        return "\n".join(schema_text)