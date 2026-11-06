from flask import Blueprint, request, jsonify
from supabase_service import sign_up_user, sign_in_user, sign_out_user, create_user_profile, get_user_profile
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    username = data.get('username')
    
    if not email or not password or not username:
        return jsonify({"error": "Email, password, and username are required"}), 400
    
    user, error = sign_up_user(email, password)
    
    if user:
        # Create user profile in the 'users' table
        profile, profile_error = create_user_profile(user['id'], email, username)
        if profile_error:
            logger.error(f"Failed to create user profile: {profile_error}")
            # You might want to handle this error, perhaps by deleting the auth user
            return jsonify({"error": f"Failed to create user profile: {profile_error}"}), 500
        
        logger.info(f"User registered successfully: {email}")
        return jsonify({"message": "User registered successfully", "user": profile}), 201
    else:
        logger.error(f"Registration failed: {error}")
        return jsonify({"error": f"Registration failed: {error}"}), 400

@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    
    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400
    
    response, error = sign_in_user(email, password)
    if response:
        user_id = response['user']['id']
        profile, profile_error = get_user_profile(user_id)
        if profile_error:
            logger.warning(f"Failed to fetch user profile: {profile_error}")
            profile = response['user']  # Fallback to auth user data
        
        logger.info(f"Login successful for {email}")
        return jsonify({
            "message": "Login successful",
            "access_token": response['session']['access_token'],
            "user": profile
        }), 200
    else:
        logger.warning(f"Login failed for {email}: {error}")
        return jsonify({"error": f"Login failed: {error}"}), 401

@auth_bp.route('/logout', methods=['POST'])
def logout():
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return jsonify({"error": "Authorization header is required"}), 400
    
    try:
        token = auth_header.split()[1]  # Assuming 'Bearer <token>'
    except IndexError:
        return jsonify({"error": "Invalid Authorization header format"}), 400

    success, error = sign_out_user(token)
    if success:
        logger.info("Logout successful")
        return jsonify({"message": "Logged out successfully"}), 200
    else:
        logger.warning(f"Logout failed: {error}")
        return jsonify({"error": f"Logout failed: {error}"}), 400

@auth_bp.route('/profile', methods=['GET'])
def get_profile():
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return jsonify({"error": "Authorization header is required"}), 400
    
    try:
        token = auth_header.split()[1]  # Assuming 'Bearer <token>'
    except IndexError:
        return jsonify({"error": "Invalid Authorization header format"}), 400

    # Here you would verify the token and get the user_id
    # For simplicity, let's assume we can get the user_id from the token
    # In a real application, you'd decode and verify the JWT token
    user_id = "example_user_id"  # Replace this with actual token verification

    profile, error = get_user_profile(user_id)
    if profile:
        return jsonify({"profile": profile}), 200
    else:
        return jsonify({"error": f"Failed to fetch profile: {error}"}), 404

# You can add more routes here as needed, such as password reset, email verification, etc.