from app.services.iam_service import IAMService
from app.core.logging import logger

def create_admin_user():
    """Create an admin user"""
    iam_service = IAMService()
    
    # Admin user credentials
    username = "admin"
    password = "admin123"  # In production, use a secure password
    role = "admin"
    
    # Create admin user
    success = iam_service.create_user(username, password, role)
    
    if success:
        print(f"Admin user '{username}' created successfully")
        print(f"Username: {username}")
        print(f"Password: {password}")
        print("Please change the password after first login")
    else:
        print("Failed to create admin user")

if __name__ == "__main__":
    create_admin_user() 