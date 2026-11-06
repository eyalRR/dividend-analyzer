import requests
import random
import string
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BASE_URL = 'http://localhost:5000'  # Adjust if your server runs on a different port

def generate_random_string(length):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def test_register():
    random_string = generate_random_string(8)
    email = f'testuser_{random_string}@example.com'
    username = f'testuser_{random_string}'
    data = {
        'email': email,
        'password': 'TestPassword123!',
        'username': username
    }
    try:
        logger.info(f"Attempting to register user: {email}")
        response = requests.post(f'{BASE_URL}/api/auth/register', json=data)
        logger.info(f'Register response: {response.status_code} {response.text}')
        
        if response.status_code == 201:
            logger.info("Registration successful")
            return True, email, 'TestPassword123!'
        else:
            logger.error(f"Registration failed: {response.text}")
            return False, None, None
    except requests.exceptions.RequestException as e:
        logger.exception(f"Exception during registration: {str(e)}")
        return False, None, None

def test_login(email, password):
    try:
        logger.info(f"Attempting to login user: {email}")
        response = requests.post(f'{BASE_URL}/api/auth/login', json={'email': email, 'password': password})
        logger.info(f'Login response: {response.status_code} {response.text}')
        
        if response.status_code == 200:
            logger.info("Login successful")
            return True
        else:
            logger.error(f"Login failed: {response.text}")
            return False
    except requests.exceptions.RequestException as e:
        logger.exception(f"Exception during login: {str(e)}")
        return False

if __name__ == '__main__':
    # Test registration
    registration_success, email, password = test_register()
    if registration_success:
        logger.info("Registration test passed")
        
        # Test login with the newly registered user
        if test_login(email, password):
            logger.info("Login test passed")
        else:
            logger.error("Login test failed")
    else:
        logger.error("Registration test failed")