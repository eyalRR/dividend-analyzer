from flask import Flask, jsonify
from flask_cors import CORS
from config import Config
from routes.auth import auth_bp
from routes.stock import stock_bp
from dividend_analysis_api import analyze_stock
from dotenv import load_dotenv
import os
from supabase_service import get_supabase_client

load_dotenv()

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Set testing mode based on environment variable
    app.config['TESTING'] = os.environ.get('FLASK_ENV') == 'testing'

    # Print out the current configuration
    print("Current configuration:")
    print(f"TESTING: {app.config['TESTING']}")
    print(f"FLASK_ENV: {os.environ.get('FLASK_ENV')}")
    print(f"All config: {app.config}")

    # Initialize Flask extensions
    CORS(app)

    # Initialize Supabase client
    supabase = get_supabase_client()

    # Register blueprints
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(stock_bp, url_prefix='/api/stock')

    @app.route('/health')
    def health_check():
        return 'OK', 200

    @app.route('/api/analyze', methods=['POST'])
    def analyze():
        return analyze_stock()

    # Error handlers
    @app.errorhandler(404)
    def not_found_error(error):
        return jsonify({"error": "Not Found"}), 404

    @app.errorhandler(500)
    def internal_error(error):
        return jsonify({"error": "Internal Server Error"}), 500

    return app

if __name__ == '__main__':
    app = create_app()
    print(f"Running in {'TESTING' if app.config['TESTING'] else 'PRODUCTION'} mode")
    app.run(debug=True)