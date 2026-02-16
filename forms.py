from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, TelField
from wtforms.validators import DataRequired, Length, Email, EqualTo, ValidationError, Regexp
import re

class RegistrationForm(FlaskForm):
    # Personal Information
    first_name = StringField('First Name', 
                           validators=[DataRequired(), Length(min=2, max=50)])
    last_name = StringField('Last Name', 
                          validators=[DataRequired(), Length(min=2, max=50)])
    email = StringField('Email',
                      validators=[
                          DataRequired(message='Email is required'),
                          Email(message='Please enter a valid email address'),
                          Length(max=120, message='Email cannot be longer than 120 characters')
                      ])
    phone = StringField('Phone Number',
                      validators=[
                          DataRequired(message='Phone number is required'),
                          Regexp(
                              r'^\d{10}$',
                              message='Phone number must be exactly 10 digits'
                          )
                      ])
    
    # Account Information
    password = PasswordField('Password',
                           validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm Password',
                                   validators=[DataRequired(), EqualTo('password')])
    
    # Submit button
    submit = SubmitField('Create Account')

    def validate_email(self, email):
        # Check if email already exists in the database
        from config import conn
        with conn.cursor() as cursor:
            cursor.execute("SELECT user_id FROM users WHERE email = %s", (email.data,))
            if cursor.fetchone() is not None:
                raise ValidationError('This email is already registered. Please use a different email address.')
    
    def validate_phone(self, phone):
        # Clean the phone number (remove any non-digit characters)
        cleaned_phone = re.sub(r'\D', '', phone.data)
        
        # Check if the cleaned phone number matches the required format
        if not re.match(r'^\d{10}$', cleaned_phone):
            raise ValidationError('Please enter a valid 10-digit phone number')
        
        # Check if phone number already exists in the database
        from config import conn
        with conn.cursor() as cursor:
            cursor.execute("SELECT user_id FROM users WHERE phone = %s", (cleaned_phone,))
            if cursor.fetchone() is not None:
                raise ValidationError('This phone number is already registered. Please use a different number.')
