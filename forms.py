from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Length, EqualTo

# User registration form with validation
class RegistrationForm(FlaskForm):
    # First name field with length validation
    first_name = StringField(
        'First Name', 
        validators=[DataRequired(), Length(min=2, max=50)]
    )
    
    # Last name field with length validation
    last_name = StringField(
        'Last Name', 
        validators=[DataRequired(), Length(min=2, max=50)]
    )
    
    # Email field with required validation
    email = StringField(
        'Email', 
        validators=[DataRequired()]
    )
    
    # Phone number field with length validation
    phone = StringField(
        'Phone Number', 
        validators=[DataRequired(), Length(min=10, max=10)]
    )
    
    # Password field with minimum length requirement
    password = PasswordField(
        'Password', 
        validators=[DataRequired(), Length(min=6)]
    )
    
    # Confirm password field with password matching validation
    confirm_password = PasswordField(
        'Confirm Password', 
        validators=[DataRequired(), EqualTo('password')]
    )
    
    # Submit button for form
    submit = SubmitField('Create Account')
