from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import datetime
import PyPDF2
from werkzeug.utils import secure_filename
import json

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///forms.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Create uploads directory if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Registering the custom 'fromjson' filter
@app.template_filter('fromjson')
def fromjson_filter(s):
    try:
        return json.loads(s)
    except (TypeError, ValueError):
        return {}

# Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    forms = db.relationship('Form', backref='author', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Form(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    questions = db.relationship('Question', backref='form', lazy=True, cascade='all, delete-orphan')
    responses = db.relationship('Response', backref='form', lazy=True, cascade='all, delete-orphan')

class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    form_id = db.Column(db.Integer, db.ForeignKey('form.id'), nullable=False)
    question_text = db.Column(db.String(500), nullable=False)
    question_type = db.Column(db.String(20), nullable=False)  # text, multiple_choice, checkbox
    options = db.Column(db.Text)  # JSON string for multiple choice/checkbox options
    required = db.Column(db.Boolean, default=False)
    order = db.Column(db.Integer, nullable=False)

    def get_options(self):
        import json
        if self.options:
            try:
                return json.loads(self.options)
            except:
                return []
        return []

    def set_options(self, options):
        import json
        self.options = json.dumps(options)

class Response(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    form_id = db.Column(db.Integer, db.ForeignKey('form.id'), nullable=False)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    answers = db.relationship('Answer', backref='response', lazy=True, cascade='all, delete-orphan')

class Answer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    response_id = db.Column(db.Integer, db.ForeignKey('response.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('question.id'), nullable=False)
    answer_text = db.Column(db.Text, nullable=False)

class PDFUpload(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    form_id = db.Column(db.Integer, db.ForeignKey('form.id'), nullable=True)
    user = db.relationship('User', backref='pdf_uploads')
    form = db.relationship('Form', backref='pdf_upload')

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Invalid email or password')
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered')
            return redirect(url_for('signup'))
            
        user = User(email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        login_user(user)
        return redirect(url_for('dashboard'))
    return render_template('signup.html')

@app.route('/dashboard')
@login_required
def dashboard():
    forms = Form.query.filter_by(user_id=current_user.id).all()
    return render_template('dashboard.html', forms=forms)

@app.route('/terms_conditions')
@login_required
def terms_and_conditions():
    return render_template('term_conditions.html')

@app.route('/create_form', methods=['GET', 'POST'])
@login_required
def create_form():
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        form = Form(title=title, description=description, user_id=current_user.id)
        db.session.add(form)
        db.session.commit()
        return redirect(url_for('edit_form', form_id=form.id))
    return render_template('create_form.html')

@app.route('/form/<int:form_id>')
def view_form(form_id):
    form = Form.query.get_or_404(form_id)
    return render_template('view_form.html', form=form)

@app.route('/form/<int:form_id>/edit')
@login_required
def edit_form(form_id):
    form = Form.query.get_or_404(form_id)
    if form.user_id != current_user.id:
        return redirect(url_for('dashboard'))
    return render_template('edit_form.html', form=form)

@app.route('/form/<int:form_id>/update', methods=['POST'])
@login_required
def update_form(form_id):
    form = Form.query.get_or_404(form_id)
    if form.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized access'}), 403

    data = request.get_json()
    if not data or 'questions' not in data:
        return jsonify({'error': 'Invalid payload'}), 400

    questions_data = data['questions']

    # Remove existing questions
    for question in form.questions:
        db.session.delete(question)
    db.session.commit()

    # Create new questions
    for index, q in enumerate(questions_data):
        options = None
        if q['question_type'] in ['radio', 'multiple_choice', 'checkbox']:
            options = q['options']  # already a comma-separated string
        elif q['question_type'] in ['scale', 'matrix']:
            options = q['options']  # expected to be provided by the custom input fields (for matrix, a JSON string)
        new_question = Question(
            form_id=form_id,
            question_text=q['question_text'],
            question_type=q['question_type'],
            options=options,
            required=q['required'],
            order=index
        )
        db.session.add(new_question)
    db.session.commit()
    return jsonify({'message': 'Form updated successfully'}), 200


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/form/<int:form_id>/delete', methods=['POST'])
@login_required
def delete_form(form_id):
    form = Form.query.get_or_404(form_id)
    if form.user_id != current_user.id:
        flash('You do not have permission to delete this form')
        return redirect(url_for('dashboard'))
    
    try:
        # Delete associated PDF upload if exists
        pdf_upload = PDFUpload.query.filter_by(form_id=form.id).first()
        if pdf_upload:
            # Delete the PDF file
            pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], pdf_upload.filename)
            if os.path.exists(pdf_path):
                os.remove(pdf_path)
            db.session.delete(pdf_upload)
        
        # Delete the form (this will cascade delete questions and responses)
        db.session.delete(form)
        db.session.commit()
        flash('Form deleted successfully')
    except Exception as e:
        db.session.rollback()
        flash('Error deleting form')
    
    return redirect(url_for('dashboard'))

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() == 'pdf'

def extract_questions_from_pdf(pdf_path):
    questions = []
    try:
        with open(pdf_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            for page in reader.pages:
                text = page.extract_text()
                lines = text.split('\n')
                i = 0
                while i < len(lines):
                    line = lines[i].strip()
                    next_line = lines[i + 1].strip() if i + 1 < len(lines) else ""
                    
                    # Skip empty lines
                    if not line:
                        i += 1
                        continue
                    
                    # Check for multiple choice questions
                    if any(option in line for option in ['(a)', '(b)', '(c)', '(d)', '(A)', '(B)', '(C)', '(D)']):
                        question_text = line
                        options = []
                        while i + 1 < len(lines) and any(option in lines[i + 1] for option in ['(a)', '(b)', '(c)', '(d)', '(A)', '(B)', '(C)', '(D)']):
                            i += 1
                            # Clean up the option text
                            option_text = lines[i].strip()
                            # Remove the option marker (a), (b), etc.
                            option_text = option_text.split(')', 1)[1].strip() if ')' in option_text else option_text
                            # Remove brackets but keep content inside quotes
                            option_text = option_text.replace('[', '').replace(']', '')
                            # Extract content inside quotes if present
                            if '"' in option_text or "'" in option_text:
                                # Find the first and last quote
                                first_quote = option_text.find('"') if '"' in option_text else option_text.find("'")
                                last_quote = option_text.rfind('"') if '"' in option_text else option_text.rfind("'")
                                if first_quote != -1 and last_quote != -1 and first_quote != last_quote:
                                    option_text = option_text[first_quote + 1:last_quote]
                            options.append(option_text)
                        
                        questions.append({
                            'text': question_text,
                            'type': 'multiple_choice',
                            'options': options,
                            'required': True
                        })
                    
                    # Check for checkbox questions
                    elif any(checkbox in line for checkbox in ['[ ]', '[  ]', '□']):
                        question_text = line
                        options = []
                        while i + 1 < len(lines) and any(checkbox in lines[i + 1] for checkbox in ['[ ]', '[  ]', '□']):
                            i += 1
                            # Clean up the option text
                            option_text = lines[i].strip()
                            # Remove checkbox markers
                            option_text = option_text.replace('[ ]', '').replace('[  ]', '').replace('□', '')
                            # Extract content inside quotes if present
                            if '"' in option_text or "'" in option_text:
                                # Find the first and last quote
                                first_quote = option_text.find('"') if '"' in option_text else option_text.find("'")
                                last_quote = option_text.rfind('"') if '"' in option_text else option_text.rfind("'")
                                if first_quote != -1 and last_quote != -1 and first_quote != last_quote:
                                    option_text = option_text[first_quote + 1:last_quote]
                            options.append(option_text.strip())
                        
                        questions.append({
                            'text': question_text,
                            'type': 'checkbox',
                            'options': options,
                            'required': True
                        })
                    
                    # Check for text input questions (with underline)
                    elif '_' in line or '___' in line:
                        # Extract the question part before the underline
                        question_text = line.split('_')[0].strip()
                        if question_text.endswith('?'):
                            questions.append({
                                'text': question_text,
                                'type': 'text',
                                'required': True
                            })
                    
                    # Check for regular questions
                    elif line.endswith('?'):
                        # Check if it's a required question (marked with *)
                        required = '*' in line
                        question_text = line.replace('*', '').strip()
                        
                        # Check if next line has options
                        if i + 1 < len(lines) and any(option in lines[i + 1] for option in ['(a)', '(b)', '(c)', '(d)', '(A)', '(B)', '(C)', '(D)']):
                            options = []
                            while i + 1 < len(lines) and any(option in lines[i + 1] for option in ['(a)', '(b)', '(c)', '(d)', '(A)', '(B)', '(C)', '(D)']):
                                i += 1
                                # Clean up the option text
                                option_text = lines[i].strip()
                                # Remove the option marker (a), (b), etc.
                                option_text = option_text.split(')', 1)[1].strip() if ')' in option_text else option_text
                                # Remove brackets but keep content inside quotes
                                option_text = option_text.replace('[', '').replace(']', '')
                                # Extract content inside quotes if present
                                if '"' in option_text or "'" in option_text:
                                    # Find the first and last quote
                                    first_quote = option_text.find('"') if '"' in option_text else option_text.find("'")
                                    last_quote = option_text.rfind('"') if '"' in option_text else option_text.rfind("'")
                                    if first_quote != -1 and last_quote != -1 and first_quote != last_quote:
                                        option_text = option_text[first_quote + 1:last_quote]
                                options.append(option_text)
                            
                            questions.append({
                                'text': question_text,
                                'type': 'multiple_choice',
                                'options': options,
                                'required': required
                            })
                        else:
                            questions.append({
                                'text': question_text,
                                'type': 'text',
                                'required': required
                            })
                    
                    i += 1
                    
    except Exception as e:
        flash(f'Error processing PDF: {str(e)}')
    return questions

@app.route('/upload_pdf', methods=['GET', 'POST'])
@login_required
def upload_pdf():
    if request.method == 'POST':
        if 'pdf' not in request.files:
            flash('No file part')
            return redirect(request.url)
        
        file = request.files['pdf']
        if file.filename == '':
            flash('No selected file')
            return redirect(request.url)
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            unique_filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{filename}"
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            file.save(file_path)
            
            # Create PDF upload record
            pdf_upload = PDFUpload(
                filename=unique_filename,
                original_filename=filename,
                user_id=current_user.id
            )
            db.session.add(pdf_upload)
            db.session.commit()
            
            # Extract questions and create form
            questions = extract_questions_from_pdf(file_path)
            if questions:
                form = Form(
                    title=f"Form from {filename}",
                    description="Automatically generated from PDF",
                    user_id=current_user.id
                )
                db.session.add(form)
                db.session.commit()
                
                # Add questions to form
                for i, q in enumerate(questions):
                    question = Question(
                        form_id=form.id,
                        question_text=q['text'],
                        question_type=q['type'],
                        required=q['required'],
                        order=i
                    )
                    if 'options' in q:
                        question.set_options(q['options'])
                    db.session.add(question)
                
                pdf_upload.form_id = form.id
                db.session.commit()
                
                flash('Form generated successfully!')
                return redirect(url_for('edit_form', form_id=form.id))
            else:
                flash('No questions found in the PDF')
                return redirect(url_for('upload_pdf'))
    
    return render_template('upload_pdf.html')

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True) 