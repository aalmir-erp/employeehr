"""
AI Assistant for Test Data Manager

This module provides functionality to interact with OpenAI to process
natural language commands for test data generation and deletion.
"""
import os
import json
import logging
from datetime import datetime, timedelta
from flask import current_app

logger = logging.getLogger(__name__)

class AIAssistant:
    """
    AI Assistant class that handles processing of natural language commands
    and translates them into specific test data operations.
    """
    
    def __init__(self, api_key=None):
        """Initialize with optional API key"""
        self.api_key = api_key
        self.openai_client = None
    
    def initialize_client(self, api_key=None):
        """Initialize the OpenAI client with the provided API key"""
        if api_key:
            self.api_key = api_key
            
        if not self.api_key:
            logger.warning("No OpenAI API key provided")
            return False
            
        try:
            from openai import OpenAI
            self.openai_client = OpenAI(api_key=self.api_key)
            return True
        except Exception as e:
            logger.error(f"Error initializing OpenAI client: {e}")
            return False
    
    def is_ready(self):
        """Check if the assistant is ready to process requests"""
        return self.openai_client is not None
    
    def process_command(self, command_text):
        """
        Process a natural language command and determine the intended action
        
        Args:
            command_text: String containing the user's command
            
        Returns:
            Dict containing the parsed command details including:
            - action: 'create' or 'delete'
            - entity_type: The type of entity to operate on (employees, logs, etc.)
            - parameters: Additional parameters for the operation
            - clarification_needed: Boolean indicating if clarification is needed
            - clarification_question: Question to ask for clarification if needed
        """
        if not self.is_ready():
            return {
                'success': False,
                'error': 'OpenAI client not initialized. Please configure API key.'
            }
        
        # Define system prompt for precise command understanding
        system_prompt = """
        You are an AI assistant that interprets commands for a test data manager. 
        Your task is to extract specific information from user commands about creating or deleting test data.
        
        Output format must be valid JSON with these fields:
        {
            "action": "create" or "delete",
            "entity_type": "employees", "attendance_logs", "shifts", "all",
            "parameters": {
                "count": number of items (for create),
                "start_date": YYYY-MM-DD format (optional),
                "end_date": YYYY-MM-DD format (optional),
                "filters": additional filters like department or shift type
            },
            "clarification_needed": boolean,
            "clarification_question": question to ask if clarification is needed
        }
        
        For example:
        - Command: "Create test data for 5 employees with night shifts in June 2025"
        - Output: {"action": "create", "entity_type": "employees", "parameters": {"count": 5, "start_date": "2025-06-01", "end_date": "2025-06-30", "filters": {"shift_type": "night"}}, "clarification_needed": false}
        
        - Command: "Delete all test data"
        - Output: {"action": "delete", "entity_type": "all", "parameters": {}, "clarification_needed": true, "clarification_question": "Are you sure you want to delete ALL test data? This will remove all employees, attendance logs, and shift assignments."}
        
        Limit your response to extracting intent and needed parameters only. Don't explain your reasoning.
        """
        
        try:
            # Call OpenAI to interpret the command
            response = self.openai_client.chat.completions.create(
                model="gpt-4o", # the newest OpenAI model is "gpt-4o" which was released May 13, 2024
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": command_text}
                ],
                response_format={"type": "json_object"}
            )
            
            # Parse the response
            try:
                result = json.loads(response.choices[0].message.content)
                return {
                    'success': True,
                    'parsed_command': result
                }
            except json.JSONDecodeError:
                logger.error("Failed to parse JSON from OpenAI response")
                return {
                    'success': False,
                    'error': 'Failed to parse command. Please try again with more specific instructions.'
                }
                
        except Exception as e:
            logger.error(f"Error processing command with OpenAI: {e}")
            return {
                'success': False,
                'error': f'Error processing command: {str(e)}'
            }
    
    def execute_command(self, parsed_command, confirmation=False, test_data_manager=None):
        """
        Execute a parsed command using the test data manager
        
        Args:
            parsed_command: Dict containing the parsed command details
            confirmation: Boolean indicating if user confirmed the action
            test_data_manager: TestDataManager instance to use for execution
            
        Returns:
            Dict containing the execution result
        """
        if not test_data_manager:
            return {
                'success': False,
                'error': 'Test data manager not provided'
            }
            
        command = parsed_command.get('parsed_command', {})
        
        # Check if clarification is needed and confirmation not provided
        if command.get('clarification_needed', False) and not confirmation:
            return {
                'success': False,
                'needs_confirmation': True,
                'confirmation_message': command.get('clarification_question', 'Are you sure you want to proceed?')
            }
            
        # Execute the command based on action and entity type
        action = command.get('action')
        entity_type = command.get('entity_type')
        parameters = command.get('parameters', {})
        
        try:
            if action == 'create':
                # Handle creation commands
                if entity_type == 'all' or entity_type == 'employees':
                    # Get date parameters if provided
                    start_date = parameters.get('start_date')
                    end_date = parameters.get('end_date')
                    
                    if start_date:
                        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
                    if end_date:
                        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
                    
                    # Generate test data
                    results = test_data_manager.setup_complete_test_scenario(
                        start_date=start_date, 
                        end_date=end_date
                    )
                    
                    return {
                        'success': results.get('success', False),
                        'message': f"Created {results.get('employees_created', 0)} employees, " +
                                  f"{results.get('logs_created', 0)} logs, " +
                                  f"{results.get('records_processed', 0)} records",
                        'details': results
                    }
                    
                # Add more specific creation logic for other entity types
                
            elif action == 'delete':
                # Handle deletion commands
                if entity_type == 'all':
                    # Delete all test data
                    results = test_data_manager.reset_database(
                        preserve_admin=True,
                        preserve_config=True
                    )
                    
                    return {
                        'success': results,
                        'message': "All test data has been deleted successfully",
                    }
                    
                # Add more specific deletion logic for other entity types
                
            return {
                'success': False,
                'error': f"Unsupported action '{action}' or entity type '{entity_type}'"
            }
                
        except Exception as e:
            logger.error(f"Error executing command: {e}")
            return {
                'success': False,
                'error': f"Error executing command: {str(e)}"
            }
    
    def transcribe_audio(self, audio_file_path):
        """
        Transcribe audio file to text using OpenAI Whisper
        
        Args:
            audio_file_path: Path to the audio file
            
        Returns:
            Dict containing the transcription result
        """
        if not self.is_ready():
            return {
                'success': False,
                'error': 'OpenAI client not initialized. Please configure API key.'
            }
            
        try:
            with open(audio_file_path, "rb") as audio_file:
                response = self.openai_client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file
                )
            
            transcribed_text = response.text
            return {
                'success': True,
                'transcription': transcribed_text
            }
                
        except Exception as e:
            logger.error(f"Error transcribing audio: {e}")
            return {
                'success': False,
                'error': f'Error transcribing audio: {str(e)}'
            }


# Create singleton instance
ai_assistant = AIAssistant()

def get_ai_assistant():
    """Get the singleton AI assistant instance"""
    return ai_assistant