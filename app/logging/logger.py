import logging
import sys
import os
import json
from datetime import datetime
from pathlib import Path

# Create logs directory if it doesn't exist
logs_dir = Path("logs")
logs_dir.mkdir(exist_ok=True)

# Configure logger format
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Setup file handlers
current_date = datetime.now().strftime("%Y-%m-%d")
file_handler = logging.FileHandler(f"logs/app-{current_date}.log")
file_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))

# Setup console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))

# Create specialized loggers
def get_logger(name):
    """Get a logger with the specified name"""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger

# Create specialized loggers
api_logger = get_logger("api")
trino_logger = get_logger("trino")
ai_logger = get_logger("ai")
schema_logger = get_logger("schema")
error_logger = get_logger("error")

# Log structured data
def log_api_request(route, method, params=None, body=None):
    """Log API request details"""
    api_logger.info(f"API Request: {method} {route}")
    if params:
        api_logger.info(f"Query params: {json.dumps(params)}")
    if body:
        api_logger.info(f"Request body: {json.dumps(body, default=str)}")

def log_api_response(route, status_code, response_time=None):
    """Log API response details"""
    msg = f"API Response: {route} - Status: {status_code}"
    if response_time:
        msg += f" - Time: {response_time:.2f}s"
    api_logger.info(msg)

def log_trino_query(query, params=None):
    """Log Trino query"""
    trino_logger.info(f"Executing Trino query: {query}")
    if params:
        trino_logger.info(f"Query parameters: {json.dumps(params, default=str)}")

def log_trino_result(query, row_count, execution_time=None):
    """Log Trino query result"""
    msg = f"Query result: {row_count} rows returned"
    if execution_time:
        msg += f" - Execution time: {execution_time:.2f}s"
    trino_logger.info(msg)

def log_ai_prompt(prompt_type, prompt):
    """Log AI prompt"""
    ai_logger.info(f"AI Prompt ({prompt_type}): {prompt[:200]}...")
    # Log full prompt to a separate file for debugging
    with open(f"logs/prompts-{current_date}.log", "a") as f:
        f.write(f"==== {datetime.now()} - {prompt_type} ====\n")
        f.write(prompt)
        f.write("\n\n")

def log_ai_response(prompt_type, response):
    """Log AI response"""
    ai_logger.info(f"AI Response ({prompt_type}): {response[:200]}...")
    # Log full response to a separate file for debugging
    with open(f"logs/responses-{current_date}.log", "a") as f:
        f.write(f"==== {datetime.now()} - {prompt_type} ====\n")
        f.write(response)
        f.write("\n\n")

def log_schema_update(catalog, schema=None, tables_count=None):
    """Log schema update"""
    schema_logger.info(f"Schema update: {catalog}.{schema if schema else '*'} - {tables_count} tables")

def log_error(module, error_message, exception=None):
    """Log error"""
    error_logger.error(f"Error in {module}: {error_message}")
    if exception:
        error_logger.error(f"Exception: {str(exception)}", exc_info=True)