"""
Forms for supervisor management
"""
from flask_wtf import FlaskForm
from wtforms import SelectField, HiddenField, SubmitField
from wtforms.validators import DataRequired

class SupervisorAssignmentForm(FlaskForm):
    """Form for assigning a new supervisor to a department"""
    department = SelectField('Department', validators=[DataRequired()], coerce=str)
    new_supervisor = SelectField('New Supervisor', validators=[DataRequired()], coerce=str)
    submit = SubmitField('Assign Supervisor')
    
    def __init__(self, *args, **kwargs):
        super(SupervisorAssignmentForm, self).__init__(*args, **kwargs)
        # Initialize with empty choices - will be populated in the route
        self.department.choices = []
        self.new_supervisor.choices = []