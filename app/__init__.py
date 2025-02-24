from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from config import Config
from datetime import datetime
from flask_migrate import Migrate
import os
from flask_wtf.csrf import CSRFProtect
from flask_moment import Moment
from flask import render_template

# Create db instance
db = SQLAlchemy()
migrate = Migrate()
login = LoginManager()
csrf = CSRFProtect()
login.login_view = 'auth.login'
moment = Moment()

def create_app():
    app = Flask(__name__)
    
    # Set secret key
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-please-change-in-production')
    app.config['WTF_CSRF_ENABLED'] = True
    
    # Use PostgreSQL in production, SQLite in development
    if os.environ.get('FLASK_ENV') == 'production':
        # Get database URL from environment variable (set by hosting platform)
        app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
    else:
        # Local SQLite database for development
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///grad_polls.db'
    
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login.init_app(app)
    csrf.init_app(app)
    moment.init_app(app)
    
    # Add datetime.now to templates
    app.jinja_env.globals.update(now=datetime.utcnow)
    
    # Import blueprints here to avoid circular imports
    from app.api import api
    
    # Register blueprints
    from app.routes import main, auth
    app.register_blueprint(main)
    app.register_blueprint(auth)
    
    app.register_blueprint(api, url_prefix='/api')
    
    from app.models import User
    @login.user_loader
    def load_user(id):
        return User.query.get(int(id))
    
    # Register error handlers
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return render_template('errors/500.html'), 500
    
    return app 