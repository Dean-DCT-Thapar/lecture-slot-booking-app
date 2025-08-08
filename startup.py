#!/usr/bin/env python3
"""
Production startup script for EduTube Slot Booking Application
"""

import os
import sys
import logging
from flask_migrate import upgrade
from app import app, db

def setup_logging():
    """Set up production logging"""
    if not os.path.exists('logs'):
        os.makedirs('logs')
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s: %(message)s',
        handlers=[
            logging.FileHandler('logs/startup.log'),
            logging.StreamHandler()
        ]
    )

def ensure_directories():
    """Ensure all required directories exist"""
    directories = ['logs', 'database', 'instance']
    
    for directory in directories:
        if not os.path.exists(directory):
            os.makedirs(directory)
            logging.info(f"Created directory: {directory}")

def create_database():
    """Create database tables if they don't exist"""
    try:
        # Ensure database directory exists
        from config import Config
        
        # Extract database path from URI
        db_uri = Config.SQLALCHEMY_DATABASE_URI
        if db_uri.startswith('sqlite:///'):
            # Remove sqlite:/// prefix and get the path
            db_path = db_uri[10:]  # Remove 'sqlite:///'
            db_dir = os.path.dirname(db_path)
            
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir)
                logging.info(f"Created database directory: {db_dir}")
        
        with app.app_context():
            # Check if migrations directory exists
            migrations_dir = os.path.join(os.path.dirname(__file__), 'migrations')
            
            if os.path.exists(migrations_dir):
                # Try to upgrade database with migrations
                try:
                    upgrade()
                    logging.info("Database migrated successfully")
                except Exception as migrate_error:
                    logging.warning(f"Migration failed, creating tables directly: {migrate_error}")
                    db.create_all()
                    logging.info("Database tables created successfully")
            else:
                # No migrations directory, create tables directly
                logging.info("No migrations found, creating tables directly")
                db.create_all()
                logging.info("Database tables created successfully")
            
    except Exception as e:
        logging.error(f"Database setup failed: {e}")
        sys.exit(1)

def create_admin_user():
    """Create default admin user if none exists"""
    try:
        with app.app_context():
            from application.models import User
            
            admin_user = User.query.filter_by(role='admin').first()
            if not admin_user:
                # Create default admin user
                admin = User(
                    username='admin',
                    password='admin123',  # Should be changed after first login
                    email=app.config.get('ADMIN_EMAIL', 'admin@edutube.com'),
                    first_name='System',
                    last_name='Administrator',
                    role='admin'
                )
                db.session.add(admin)
                db.session.commit()
                logging.info("Default admin user created (username: admin, password: admin123)")
                logging.warning("SECURITY: Please change the default admin password after first login!")
            else:
                logging.info("Admin user already exists")
                
    except Exception as e:
        logging.error(f"Failed to create admin user: {e}")

def check_environment():
    """Check if all required environment variables are set"""
    required_vars = ['SECRET_KEY']
    missing_vars = []
    
    for var in required_vars:
        if not os.environ.get(var) and not app.config.get(var):
            missing_vars.append(var)
    
    if missing_vars:
        logging.warning(f"Missing environment variables: {missing_vars}")
        logging.warning("Application may not work correctly without proper configuration")
    
    # Check if running with default secret key
    if app.config.get('SECRET_KEY') == 'dev-secret-key-change-in-production':
        logging.warning("SECURITY: Using default secret key! Please set SECRET_KEY environment variable")

def main():
    """Main startup function"""
    setup_logging()
    logging.info("Starting EduTube Slot Booking Application setup...")
    
    # Ensure all directories exist
    ensure_directories()
    
    # Check environment
    check_environment()
    
    # Set up database
    create_database()
    
    # Create admin user
    create_admin_user()
    
    logging.info("Application setup completed successfully!")
    logging.info("Application is ready to start")

if __name__ == '__main__':
    main()
