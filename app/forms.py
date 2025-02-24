from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, TextAreaField, DateTimeField, SubmitField, SelectField, FloatField, IntegerField, DateField
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError, Optional, NumberRange
from datetime import datetime
from flask_login import current_user
from flask_wtf.file import FileField, FileAllowed
from werkzeug.utils import secure_filename
from app.models import User

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[
        DataRequired(message="Email is required"),
        Email(message="Please enter a valid email address")
    ])
    password = PasswordField('Password', validators=[
        DataRequired(message="Password is required")
    ])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Sign In')

class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[
        DataRequired(message="Username is required"),
        Length(min=3, max=64, message="Username must be between 3 and 64 characters")
    ])
    email = StringField('Email', validators=[
        DataRequired(message="Email is required"),
        Email(message="Please enter a valid email address")
    ])
    password = PasswordField('Password', validators=[
        DataRequired(message="Password is required"),
        Length(min=6, message="Password must be at least 6 characters long")
    ])
    password2 = PasswordField('Repeat Password', validators=[
        DataRequired(message="Please confirm your password"),
        EqualTo('password', message="Passwords must match")
    ])
    submit = SubmitField('Register')

    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user is not None:
            raise ValidationError('Please use a different username.')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user is not None:
            raise ValidationError('Please use a different email address.')

class PollForm(FlaskForm):
    title = StringField('Title', validators=[
        DataRequired(message="Title is required"),
        Length(max=200, message="Title must be less than 200 characters")
    ])
    description = TextAreaField('Description', validators=[
        DataRequired(message="Description is required")
    ])
    end_date = DateTimeField('End Date (optional)', 
                            format='%Y-%m-%dT%H:%M',
                            validators=[Optional()],
                            render_kw={"type": "datetime-local"})
    poll_type = SelectField('Poll Type',
                          choices=[('general', 'General Poll'), 
                                 ('university', 'University Comparison')],
                          validators=[DataRequired()])
    submit = SubmitField('Create Poll')

    def validate_end_date(self, field):
        if field.data and field.data < datetime.now():
            raise ValidationError('End date must be in the future')

    def validate_options(self, field):
        options = [opt.strip() for opt in field.data.split('\n') if opt.strip()]
        if len(options) < 2:
            raise ValidationError('Please provide at least two options')

class CommentForm(FlaskForm):
    body = TextAreaField('Comment', validators=[DataRequired(message="Comment cannot be empty")])
    submit = SubmitField('Post Comment')

class UpdateAccountForm(FlaskForm):
    username = StringField('Username', validators=[
        DataRequired(message="Username is required"),
        Length(min=3, max=64, message="Username must be between 3 and 64 characters")
    ])
    email = StringField('Email', validators=[
        DataRequired(message="Email is required"),
        Email(message="Please enter a valid email address")
    ])
    picture = FileField('Update Profile Picture', validators=[FileAllowed(['jpg', 'png'])])
    submit = SubmitField('Update')

    def validate_username(self, username):
        if username.data != current_user.username:
            user = User.query.filter_by(username=username.data).first()
            if user is not None:
                raise ValidationError('Please use a different username.')

    def validate_email(self, email):
        if email.data != current_user.email:
            user = User.query.filter_by(email=email.data).first()
            if user is not None:
                raise ValidationError('Please use a different email address.')

    def validate_picture(self, field):
        if field.data:
            filename = secure_filename(field.data.filename)
            if filename != current_user.image_file:
                raise ValidationError('File name must be the same as the current image.')

class AdmissionResultForm(FlaskForm):
    university = StringField('University', validators=[
        DataRequired(message="University name is required"),
        Length(max=200, message="University name must be less than 200 characters")
    ])
    program = StringField('Program', validators=[
        DataRequired(message="Program name is required"),
        Length(max=200, message="Program name must be less than 200 characters")
    ])
    decision = SelectField('Decision', choices=[
        ('Accepted', 'Accepted'),
        ('Rejected', 'Rejected'),
        ('Waitlisted', 'Waitlisted'),
        ('Interview', 'Interview Scheduled')
    ], validators=[DataRequired(message="Decision is required")])
    degree_type = SelectField('Degree Type', choices=[
        ('PhD', 'PhD'),
        ('MS', 'Masters'),
        ('MEng', 'MEng'),
        ('Other', 'Other')
    ], validators=[DataRequired(message="Degree type is required")])
    term = StringField('Term (e.g., Fall 2024)', validators=[
        DataRequired(message="Term is required"),
        Length(max=50, message="Term must be less than 50 characters")
    ])
    notification_date = DateTimeField('Notification Date', 
                                    format='%Y-%m-%dT%H:%M',
                                    validators=[DataRequired(message="Notification date is required")],
                                    render_kw={"type": "datetime-local"})
    gpa = FloatField('GPA (optional)', validators=[
        Optional(),
        NumberRange(min=0, max=4.0, message="GPA must be between 0 and 4.0")
    ])
    gre_verbal = IntegerField('GRE Verbal (optional)', validators=[
        Optional(),
        NumberRange(min=130, max=170, message="GRE Verbal score must be between 130 and 170")
    ])
    gre_quant = IntegerField('GRE Quant (optional)', validators=[
        Optional(),
        NumberRange(min=130, max=170, message="GRE Quant score must be between 130 and 170")
    ])
    gre_awa = FloatField('GRE AWA (optional)', validators=[
        Optional(),
        NumberRange(min=0, max=6.0, message="GRE AWA score must be between 0 and 6.0")
    ])
    comments = TextAreaField('Additional Comments (optional)', validators=[
        Optional(),
        Length(max=1000, message="Comments must be less than 1000 characters")
    ])
    submit = SubmitField('Submit Result')

class ProfileForm(FlaskForm):
    # Undergraduate Details
    university = StringField('Undergraduate University', validators=[DataRequired()])
    major = StringField('Major', validators=[DataRequired()])
    gpa = FloatField('GPA', validators=[Optional(), NumberRange(min=0, max=10)])
    gpa_scale = FloatField('GPA Scale', validators=[Optional(), NumberRange(min=0, max=10)], default=4.0)
    
    # Test Scores
    toefl_score = IntegerField('TOEFL Score', validators=[Optional(), NumberRange(min=0, max=120)])
    ielts_score = FloatField('IELTS Score', validators=[Optional(), NumberRange(min=0, max=9)])
    gre_verbal = IntegerField('GRE Verbal', validators=[Optional(), NumberRange(min=130, max=170)])
    gre_quant = IntegerField('GRE Quantitative', validators=[Optional(), NumberRange(min=130, max=170)])
    gre_awa = FloatField('GRE Analytical Writing', validators=[Optional(), NumberRange(min=0, max=6)])
    
    # Work Experience
    work_experience_years = FloatField('Years of Work Experience', validators=[Optional(), NumberRange(min=0)])
    current_job = StringField('Current Job Title', validators=[Optional()])
    company = StringField('Company', validators=[Optional()])
    
    # Research Experience
    research_experience = BooleanField('Research Experience')
    publications = IntegerField('Number of Publications', validators=[Optional(), NumberRange(min=0)])
    
    # Additional Information
    target_term = StringField('Target Term (e.g., Fall 2024)', validators=[Optional()])
    target_degree = SelectField('Target Degree', choices=[
        ('', 'Select Degree'),
        ('MS', 'Master of Science (MS)'),
        ('PhD', 'Doctor of Philosophy (PhD)'),
        ('MEng', 'Master of Engineering (MEng)'),
        ('Other', 'Other')
    ], validators=[Optional()])
    target_major = StringField('Target Major', validators=[Optional()])
    
    # Bio/About
    bio = TextAreaField('About Me', validators=[Optional(), Length(max=500)])
    
    submit = SubmitField('Save Profile')

class ApplicationForm(FlaskForm):
    university = StringField('University', validators=[
        DataRequired(message="University name is required"),
        Length(max=200)
    ])
    program = StringField('Program', validators=[
        DataRequired(message="Program name is required"),
        Length(max=200)
    ])
    term = StringField('Term (e.g., Fall 2024)', validators=[
        DataRequired(message="Term is required"),
        Length(max=50)
    ])
    degree_type = SelectField('Degree Type', choices=[
        ('MS', 'Master of Science (MS)'),
        ('PhD', 'Doctor of Philosophy (PhD)'),
        ('MEng', 'Master of Engineering (MEng)'),
        ('Other', 'Other')
    ], validators=[DataRequired()])
    
    status = SelectField('Application Status', choices=[
        ('Planning', 'Planning to Apply'),
        ('Applied', 'Applied'),
        ('Interview', 'Interview Scheduled'),
        ('Accepted', 'Accepted'),
        ('Rejected', 'Rejected'),
        ('Waitlisted', 'Waitlisted'),
        ('Withdrawn', 'Withdrawn')
    ])
    
    applied_date = DateField('Application Date', validators=[Optional()])
    deadline = DateField('Application Deadline', validators=[Optional()])
    decision_date = DateField('Decision Date', validators=[Optional()])
    
    application_fee = FloatField('Application Fee ($)', validators=[Optional()])
    fee_paid = BooleanField('Application Fee Paid')
    
    transcripts_submitted = BooleanField('Transcripts Submitted')
    lors_submitted = IntegerField('Number of LORs Submitted', validators=[
        Optional(),
        NumberRange(min=0, max=10)
    ])
    sop_submitted = BooleanField('Statement of Purpose Submitted')
    resume_submitted = BooleanField('Resume/CV Submitted')
    
    notes = TextAreaField('Notes', validators=[Optional(), Length(max=1000)])
    submit = SubmitField('Save Application')

class CommunityForm(FlaskForm):
    university = StringField('University', validators=[
        DataRequired(message="University name is required")
    ])
    program = StringField('Program', validators=[
        DataRequired(message="Program name is required")
    ])
    description = TextAreaField('Description', validators=[
        Optional(),
        Length(max=500, message="Description must be less than 500 characters")
    ])
    submit = SubmitField('Create Community') 