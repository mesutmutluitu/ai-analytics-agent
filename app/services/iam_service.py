import bcrypt
import jwt
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from app.core.logging import logger
from app.config import settings
import json
from pathlib import Path

class IAMService:
    def __init__(self):
        # Get the application root directory
        app_root = Path(__file__).parent.parent.parent
        
        # Set users directory
        self.users_dir = app_root / "data" / "users"
        self.users_dir.mkdir(parents=True, exist_ok=True)
        
        # Load permissions
        self._load_permissions()
        
    def _load_permissions(self):
        """Load permissions configuration"""
        self.permissions = {
            "ai-analytics": {
                "view": ["admin", "analyst"],
                "edit": ["admin"],
                "delete": ["admin"]
            },
            "users": {
                "view": ["admin"],
                "edit": ["admin"],
                "delete": ["admin"]
            },
            "settings": {
                "view": ["admin"],
                "edit": ["admin"]
            }
        }
        
    def _get_user_file(self, username: str) -> Path:
        """Get user file path"""
        return self.users_dir / f"{username}.json"
        
    def create_user(self, username: str, password: str, role: str = "user") -> bool:
        """Create a new user"""
        try:
            if self._get_user_file(username).exists():
                logger.log_error("iam", f"User {username} already exists")
                return False
                
            # Hash password
            hashed_password = bcrypt.hashpw(
                password.encode('utf-8'),
                bcrypt.gensalt()
            ).decode('utf-8')
            
            # Create user data
            user_data = {
                "username": username,
                "password": hashed_password,
                "role": role,
                "created_at": datetime.now().isoformat(),
                "last_login": None,
                "is_active": True
            }
            
            # Save user data
            with open(self._get_user_file(username), 'w') as f:
                json.dump(user_data, f)
                
            logger.log_auth(f"User {username} created with role {role}")
            return True
            
        except Exception as e:
            logger.log_error("iam", f"Error creating user {username}", e)
            return False
            
    def authenticate_user(self, username: str, password: str) -> Optional[Dict]:
        """Authenticate user and return JWT token"""
        try:
            user_file = self._get_user_file(username)
            if not user_file.exists():
                logger.log_error("iam", f"User {username} not found")
                return None
                
            # Load user data
            with open(user_file, 'r') as f:
                user_data = json.load(f)
                
            # Check password
            if not bcrypt.checkpw(
                password.encode('utf-8'),
                user_data['password'].encode('utf-8')
            ):
                logger.log_error("iam", f"Invalid password for user {username}")
                return None
                
            # Update last login
            user_data['last_login'] = datetime.now().isoformat()
            with open(user_file, 'w') as f:
                json.dump(user_data, f)
                
            # Generate JWT token
            token = jwt.encode(
                {
                    "username": username,
                    "role": user_data['role'],
                    "exp": datetime.utcnow() + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
                },
                settings.JWT_SECRET_KEY,
                algorithm=settings.JWT_ALGORITHM
            )
            
            logger.log_auth(f"User {username} authenticated successfully")
            return {
                "token": token,
                "username": username,
                "role": user_data['role']
            }
            
        except Exception as e:
            logger.log_error("iam", f"Error authenticating user {username}", e)
            return None
            
    def verify_token(self, token: str) -> Optional[Dict]:
        """Verify JWT token"""
        try:
            if not token:
                raise Exception("Token is empty")
                
            payload = jwt.decode(
                token,
                settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM]
            )
            
            # Check if token is expired
            if datetime.utcnow() > datetime.fromtimestamp(payload['exp']):
                raise Exception("Token has expired")
                
            # Get user data
            user_file = self._get_user_file(payload['username'])
            if not user_file.exists():
                raise Exception(f"User {payload['username']} not found")
                
            with open(user_file, 'r') as f:
                user_data = json.load(f)
                
            if not user_data.get('is_active', True):
                raise Exception(f"User {payload['username']} is not active")
                
            return {
                "username": payload['username'],
                "role": payload['role']
            }
            
        except jwt.ExpiredSignatureError:
            raise Exception("Token has expired")
        except jwt.InvalidTokenError as e:
            raise Exception(f"Invalid token format: {str(e)}")
        except Exception as e:
            raise Exception(f"Token verification failed: {str(e)}")
            
    def check_permission(self, user_role: str, resource: str, action: str) -> bool:
        """Check if user has permission for action on resource"""
        try:
            if resource not in self.permissions:
                logger.log_error("iam", f"Resource {resource} not found in permissions")
                return False
                
            if action not in self.permissions[resource]:
                logger.log_error("iam", f"Action {action} not found in permissions for {resource}")
                return False
                
            return user_role in self.permissions[resource][action]
            
        except Exception as e:
            logger.log_error("iam", f"Error checking permission for {user_role} on {resource}", e)
            return False
            
    def update_password(self, username: str, old_password: str, new_password: str) -> bool:
        """Update user password"""
        try:
            user_file = self._get_user_file(username)
            if not user_file.exists():
                logger.log_error("iam", f"User {username} not found")
                return False
                
            # Load user data
            with open(user_file, 'r') as f:
                user_data = json.load(f)
                
            # Verify old password
            if not bcrypt.checkpw(
                old_password.encode('utf-8'),
                user_data['password'].encode('utf-8')
            ):
                logger.log_error("iam", f"Invalid old password for user {username}")
                return False
                
            # Update password
            user_data['password'] = bcrypt.hashpw(
                new_password.encode('utf-8'),
                bcrypt.gensalt()
            ).decode('utf-8')
            
            # Save updated user data
            with open(user_file, 'w') as f:
                json.dump(user_data, f)
                
            logger.log_auth(f"Password updated for user {username}")
            return True
            
        except Exception as e:
            logger.log_error("iam", f"Error updating password for user {username}", e)
            return False
            
    def get_user(self, username: str) -> Optional[Dict]:
        """Get user data"""
        try:
            user_file = self._get_user_file(username)
            if not user_file.exists():
                logger.log_error("iam", f"User {username} not found")
                return None
                
            with open(user_file, 'r') as f:
                user_data = json.load(f)
                
            # Remove sensitive data
            user_data.pop('password', None)
            return user_data
            
        except Exception as e:
            logger.log_error("iam", f"Error getting user {username}", e)
            return None
            
    def list_users(self) -> List[Dict]:
        """List all users"""
        try:
            users = []
            for user_file in self.users_dir.glob("*.json"):
                with open(user_file, 'r') as f:
                    user_data = json.load(f)
                    # Remove sensitive data
                    user_data.pop('password', None)
                    users.append(user_data)
            return users
            
        except Exception as e:
            logger.log_error("iam", "Error listing users", e)
            return [] 