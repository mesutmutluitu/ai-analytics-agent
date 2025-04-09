import logging
import os
from datetime import datetime
from pathlib import Path

class Logger:
    def __init__(self):
        # Get the application root directory
        app_root = Path(__file__).parent.parent.parent
        
        # Create logs directory
        self.logs_dir = app_root / "logs"
        self.logs_dir.mkdir(exist_ok=True)
        
        # Configure logging
        self._setup_logging()
        
    def _setup_logging(self):
        """Setup logging configuration"""
        # Create formatters
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        # Setup file handlers
        self._setup_file_handler('app.log', formatter)
        self._setup_file_handler('auth.log', formatter)
        self._setup_file_handler('error.log', formatter)
        
        # Setup console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        
        # Get root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        root_logger.addHandler(console_handler)
        
    def _setup_file_handler(self, filename, formatter):
        """Setup file handler for specific log file"""
        file_handler = logging.FileHandler(
            self.logs_dir / filename,
            encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        
        logger = logging.getLogger(filename.split('.')[0])
        logger.setLevel(logging.INFO)
        logger.addHandler(file_handler)
        
    def log_info(self, category, message):
        """Log info message"""
        logger = logging.getLogger(category)
        logger.info(message)
        
    def log_error(self, category, message, error=None):
        """Log error message"""
        logger = logging.getLogger('error')
        if error:
            logger.error(f"{category} - {message}: {str(error)}")
        else:
            logger.error(f"{category} - {message}")
            
    def log_auth(self, message):
        """Log authentication related message"""
        logger = logging.getLogger('auth')
        logger.info(message)
        
    def log_activity(self, user_id, action, details=None):
        """Log user activity"""
        logger = logging.getLogger('app')
        log_message = f"User {user_id} performed {action}"
        if details:
            log_message += f": {details}"
        logger.info(log_message)

# Create global logger instance
logger = Logger() 