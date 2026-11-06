# Dividend Tracker

This project is a dividend tracking application with a Flask backend and a React frontend (to be implemented).

## Project Structure

- `backend/`: Contains the Flask application
- `frontend/`: Will contain the React application (to be implemented)

## Backend Setup

1. Navigate to the backend directory:

   ```
   cd backend
   ```

2. Create a virtual environment:

   ```
   python -m venv venv
   ```

3. Activate the virtual environment:

   - On Windows: `venv\Scripts\activate`
   - On macOS and Linux: `source venv/bin/activate`

4. Install the required packages:

   ```
   pip install -r requirements.txt --upgrade
   ```

   Note: It's important to use the `--upgrade` flag to ensure you're using the latest compatible versions of all packages.

5. Set up the database:

   ```
   python app.py
   ```

   This will create the database tables.

6. Run the development server:
   ```
   flask run
   ```

## Running Tests

To run the tests for the backend:

1. Ensure your virtual environment is activated.

2. From the backend directory, run:

   ```
   python -m unittest tests.py
   ```

   This command will discover and run all the tests defined in the `tests.py` file.

3. To run tests with more detailed output, use:

   ```
   python -m unittest -v tests.py
   ```

   The `-v` flag provides a more verbose output, showing the result of each individual test.

4. If you want to run a specific test, you can do so by specifying the test class and method:

   ```
   python -m unittest tests.TestApp.test_health_check
   ```

   Replace `test_health_check` with the name of the specific test you want to run.

## API Endpoints

- POST /api/auth/register: Register a new user
- POST /api/auth/login: Log in a user
- POST /api/stock/track: Track a stock for a user
- GET /api/stock/portfolio/<user_id>: Get a user's portfolio
- POST /api/analyze: Analyze a stock

For more details on how to use these endpoints, please refer to the API documentation.

## Frontend Setup

(To be implemented)

## Contributing

Please read CONTRIBUTING.md for details on our code of conduct, and the process for submitting pull requests to us.

## License

This project is licensed under the MIT License - see the LICENSE.md file for details
