from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import datetime
import PyPDF2
from werkzeug.utils import secure_filename
from flask_migrate import Migrate

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///forms.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Create uploads directory if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)
migrate = Migrate(app, db)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

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

class Company(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    referral_code = db.Column(db.String(50), unique=True, nullable=False)
    forms = db.relationship('Form', backref='company', lazy=True)

class Form(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', name='fk_form_user'), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id', name='fk_form_company'), nullable=True)
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
    company_id = db.Column(db.Integer, db.ForeignKey('company.id', name='fk_response_company'), nullable=True)
    answers = db.relationship('Answer', backref='response', lazy=True, cascade='all, delete-orphan')
    company = db.relationship('Company', backref='responses')

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

@app.route('/create_form', methods=['GET', 'POST'])
@login_required
def create_form():
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        
        form = Form(
            title=title,
            description=description,
            user_id=current_user.id,
            company_id=session.get('referral_company_id')
        )
        db.session.add(form)
        db.session.commit()
        
        # Clear referral from session after form creation
        session.pop('referral_company_id', None)
        
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

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/form/<int:form_id>/submit', methods=['POST'])
def submit_form(form_id):
    form = Form.query.get_or_404(form_id)
    
    try:
        # Get company ID from form or session
        company_id = form.company_id or session.get('referral_company_id')
        
        # Create response
        response = Response(
            form_id=form_id,
            company_id=company_id
        )
        db.session.add(response)
        db.session.commit()
        
        # Process answers
        for question in form.questions:
            if question.question_type == 'checkbox':
                # Handle multiple checkbox selections
                answer_texts = request.form.getlist(f'question_{question.id}')
                answer_text = ', '.join(answer_texts) if answer_texts else None
            else:
                answer_text = request.form.get(f'question_{question.id}')
                
            if answer_text:
                answer = Answer(
                    response_id=response.id,
                    question_id=question.id,
                    answer_text=answer_text
                )
                db.session.add(answer)
        
        db.session.commit()
        flash('Form submitted successfully!')
        return redirect(url_for('view_form', form_id=form_id))
    except Exception as e:
        db.session.rollback()
        flash(f'Error submitting form: {str(e)}')
        return redirect(url_for('view_form', form_id=form_id))

@app.route('/form/<int:form_id>/responses')
@login_required
def view_responses(form_id):
    form = Form.query.get_or_404(form_id)
    if form.user_id != current_user.id:
        flash('You do not have permission to view these responses')
        return redirect(url_for('dashboard'))
    
    responses = Response.query.filter_by(form_id=form_id).all()
    return render_template('view_responses.html', form=form, responses=responses)

@app.route('/form/<int:form_id>/delete', methods=['POST'])
@login_required
def delete_form(form_id):
    form = Form.query.get_or_404(form_id)
    if form.user_id != current_user.id:
        flash('You do not have permission to delete this form')
        return redirect(url_for('dashboard'))
    
    try:
        # Step 1: Delete associated PDF file and record
        pdf_upload = PDFUpload.query.filter_by(form_id=form.id).first()
        if pdf_upload:
            pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], pdf_upload.filename)
            if os.path.exists(pdf_path):
                try:
                    os.remove(pdf_path)
                except Exception as e:
                    print(f"Error deleting PDF file: {e}")
            db.session.delete(pdf_upload)
            db.session.commit()
        
        # Step 2: Delete all answers
        answers = Answer.query.join(Response).filter(Response.form_id == form_id).all()
        for answer in answers:
            db.session.delete(answer)
        db.session.commit()
        
        # Step 3: Delete all responses
        responses = Response.query.filter_by(form_id=form_id).all()
        for response in responses:
            db.session.delete(response)
        db.session.commit()
        
        # Step 4: Delete all questions
        questions = Question.query.filter_by(form_id=form_id).all()
        for question in questions:
            db.session.delete(question)
        db.session.commit()
        
        # Step 5: Finally, delete the form
        db.session.delete(form)
        db.session.commit()
        
        flash('Form and all associated data deleted successfully')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting form: {str(e)}')
        return redirect(url_for('dashboard'))
    
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
                    
                    # Function to clean text - only keep alphabets and spaces
                    def clean_text(text):
                        # Keep only alphabets and spaces
                        text = ''.join(c for c in text if c.isalpha() or c == ' ')
                        # Remove extra spaces
                        text = ' '.join(text.split())
                        return text
                    
                    # Check for multiple choice questions
                    if any(option in line for option in ['(a)', '(b)', '(c)', '(d)', '(A)', '(B)', '(C)', '(D)']):
                        question_text = clean_text(line)
                        options = []
                        while i + 1 < len(lines) and any(option in lines[i + 1] for option in ['(a)', '(b)', '(c)', '(d)', '(A)', '(B)', '(C)', '(D)']):
                            i += 1
                            option_text = lines[i].strip()
                            # Remove option markers and clean text
                            option_text = option_text.split(')', 1)[1].strip() if ')' in option_text else option_text
                            option_text = clean_text(option_text)
                            options.append(option_text)
                        
                        questions.append({
                            'text': question_text,
                            'type': 'multiple_choice',
                            'options': options,
                            'required': True
                        })
                    
                    # Check for checkbox questions
                    elif any(checkbox in line for checkbox in ['[ ]', '[  ]', '□']):
                        question_text = clean_text(line)
                        options = []
                        while i + 1 < len(lines) and any(checkbox in lines[i + 1] for checkbox in ['[ ]', '[  ]', '□']):
                            i += 1
                            option_text = lines[i].strip()
                            # Remove checkbox markers and clean text
                            option_text = option_text.replace('[ ]', '').replace('[  ]', '').replace('□', '').strip()
                            option_text = clean_text(option_text)
                            options.append(option_text)
                        
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
                        question_text = clean_text(question_text)
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
                        question_text = clean_text(question_text)
                        
                        # Check if next line has options
                        if i + 1 < len(lines) and any(option in lines[i + 1] for option in ['(a)', '(b)', '(c)', '(d)', '(A)', '(B)', '(C)', '(D)']):
                            options = []
                            while i + 1 < len(lines) and any(option in lines[i + 1] for option in ['(a)', '(b)', '(c)', '(d)', '(A)', '(B)', '(C)', '(D)']):
                                i += 1
                                option_text = lines[i].strip()
                                # Remove option markers and clean text
                                option_text = option_text.split(')', 1)[1].strip() if ')' in option_text else option_text
                                option_text = clean_text(option_text)
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
                user_id=current_user.id,
                form_id=None  # Will be updated after form creation
            )
            db.session.add(pdf_upload)
            db.session.commit()
            
            # Extract questions and create form
            questions = extract_questions_from_pdf(file_path)
            if questions:
                form = Form(
                    title=f"Form from {filename}",
                    description="Automatically generated from PDF",
                    user_id=current_user.id,
                    company_id=session.get('referral_company_id')
                )
                db.session.add(form)
                db.session.commit()
                
                # Update PDF upload with form ID
                pdf_upload.form_id = form.id
                
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
                
                db.session.commit()
                
                # Clear referral from session after form creation
                session.pop('referral_company_id', None)
                
                flash('Form generated successfully!')
                return redirect(url_for('edit_form', form_id=form.id))
            else:
                flash('No questions found in the PDF')
                return redirect(url_for('upload_pdf'))
    
    return render_template('upload_pdf.html')

def parse_mindmap_to_form(mindmap_text):
    form_data = {
        "title": "",
        "sections": []
    }
    
    current_section = None
    current_field = None
    
    lines = mindmap_text.split('\n')
    for line in lines:
        # Skip empty lines
        if not line.strip():
            continue
            
        # Count indentation level (number of spaces at start)
        indent_level = len(line) - len(line.lstrip())
        
        # Root level - Form title
        if indent_level == 0:
            form_data["title"] = line.strip()
            
        # First level - Sections
        elif indent_level == 2:  # Two spaces for sections
            # Remove "Section X:" prefix if present
            section_name = line.strip()
            if ":" in section_name:
                section_name = section_name.split(":", 1)[1].strip()
            
            current_section = {
                "name": section_name,
                "fields": []
            }
            form_data["sections"].append(current_section)
            
        # Second level - Fields
        elif indent_level == 4:  # Four spaces for fields
            field_parts = line.strip().split('|')
            field_label = field_parts[0].strip()
            field_type = "text"  # default type
            
            if len(field_parts) > 1:
                type_spec = field_parts[1].strip().lower()
                if type_spec in ['text', 'dropdown', 'checkbox', 'radio', 'email']:
                    field_type = type_spec
            
            current_field = {
                "label": field_label,
                "type": field_type,
                "options": []
            }
            current_section["fields"].append(current_field)
            
        # Third level - Options (for dropdown/checkbox/radio)
        elif indent_level == 6 and current_field:  # Six spaces for options
            if current_field["type"] in ['dropdown', 'checkbox', 'radio']:
                current_field["options"].append(line.strip())
    
    return form_data

@app.route('/upload_mindmap', methods=['GET', 'POST'])
@login_required
def upload_mindmap():
    if request.method == 'POST':
        mindmap_text = request.form.get('mindmap_text')
        if not mindmap_text:
            flash('No mindmap text provided')
            return redirect(request.url)
            
        try:
            form_data = parse_mindmap_to_form(mindmap_text)
            
            form = Form(
                title=form_data["title"],
                description="Generated from mindmap",
                user_id=current_user.id,
                company_id=session.get('referral_company_id')
            )
            db.session.add(form)
            db.session.commit()
            
            order = 0
            for section in form_data["sections"]:
                for field in section["fields"]:
                    type_mapping = {
                        'text': 'text',
                        'email': 'email',
                        'dropdown': 'multiple_choice',
                        'checkbox': 'checkbox',
                        'radio': 'radio'
                    }
                    
                    question_type = type_mapping.get(field["type"], 'text')
                    
                    question = Question(
                        form_id=form.id,
                        question_text=field["label"],
                        question_type=question_type,
                        required=True,
                        order=order
                    )
                    
                    if question_type in ['multiple_choice', 'checkbox', 'radio'] and field["options"]:
                        question.set_options(field["options"])
                    
                    db.session.add(question)
                    order += 1
            
            db.session.commit()
            
            # Clear referral from session after form creation
            session.pop('referral_company_id', None)
            
            flash('Form generated successfully from mindmap!')
            return redirect(url_for('edit_form', form_id=form.id))
            
        except Exception as e:
            flash(f'Error processing mindmap: {str(e)}')
            return redirect(url_for('upload_mindmap'))
    
    return render_template('upload_mindmap.html')

@app.route('/manage_companies', methods=['GET', 'POST'])
@login_required
def manage_companies():
    if request.method == 'POST':
        name = request.form.get('name')
        referral_code = request.form.get('referral_code')
        
        if not name or not referral_code:
            flash('Company name and referral code are required')
            return redirect(url_for('manage_companies'))
            
        company = Company(name=name, referral_code=referral_code)
        db.session.add(company)
        db.session.commit()
        flash('Company added successfully')
        return redirect(url_for('manage_companies'))
        
    companies = Company.query.all()
    return render_template('manage_companies.html', companies=companies)

@app.route('/referral/<referral_code>')
def handle_referral(referral_code):
    company = Company.query.filter_by(referral_code=referral_code).first()
    if not company:
        flash('Invalid referral link')
        return redirect(url_for('index'))
        
    # Store company_id in session for form creation
    session['referral_company_id'] = company.id
    return redirect(url_for('create_form'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)