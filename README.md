# Google Forms Clone

A web application that allows users to create and fill out forms, similar to Google Forms.

## Features
- User authentication (signup/login)
- Create forms with various question types
- Share forms via unique links
- View form responses
- Real-time form preview

## Setup Instructions

1. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Initialize the database:
```bash
python init_db.py
```

4. Run the application:
```bash
python app.py
```

5. Open your browser and navigate to `http://localhost:5000`

## Project Structure
- `app.py`: Main application file
- `models.py`: Database models
- `forms.py`: Form definitions
- `static/`: Static files (CSS, JavaScript)
- `templates/`: HTML templates
- `instance/`: Database and instance-specific files 