# reminder.py

import os
import json
import sys
from google import genai
from google.genai import types

from dotenv import load_dotenv

def get_active_reminders(username):
    """
    Process memory units for a specific user and return active reminders.
    
    Args:
        username (str): The username (e.g., "")
        
    Returns:
        list: List of active tasks as strings
    """
    # Construct paths based on username
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    memory_path = os.path.join(base_dir, 'memory', 'summaries', f"{username}.jsonl")
    output_path = os.path.join(base_dir, 'memory', 'reminders', username, 'open_reminders.txt')
    
    # Load environment variables
    dotenv_path = os.path.join(base_dir, 'mentra.env')
    load_dotenv(dotenv_path=dotenv_path)
    
    # Check if the memory file exists
    if not os.path.exists(memory_path):
        print(f"Error: Memory file not found for user {username}", file=sys.stderr)
        return []
    
    # Initialize Google Generative AI client
    api_key = os.getenv("GOOGLE_GENAI_API_KEY2")
    if not api_key:
        print("Error: GOOGLE_GENAI_API_KEY environment variable not set", file=sys.stderr)
        return []
        
    client = genai.Client(api_key=api_key)
    
    # Read memory units from the JSONL file
    memory_units = []
    try:
        with open(memory_path, 'r', encoding='utf-8') as file:
            for line in file:
                if line.strip():
                    memory_units.append(json.loads(line))
    except Exception as e:
        print(f"Error reading memory file: {e}", file=sys.stderr)
        return []
    
    # Check if memory units were loaded
    if not memory_units:
        print(f"Warning: No memory units found for user {username}", file=sys.stderr)
        return []
    
    # Construct the prompt
    prompt = """
    You are given a chronological log of user events, where each entry includes an id, type, timestamp, and summary. Entries can be of type "info", "task: open", or "task: closed". The log is not intelligent — it records raw events in order. Some tasks may be marked as "task: open" but later implicitly or explicitly completed via "task: closed" entries or corroborating "info" entries.

    Your job:

    Determine the final state of all tasks by analyzing the full timeline.

    If a task is marked as open but is later closed or fulfilled, mark it as closed.

    Your output should be a list of active (still open) tasks, taking into account the entire log.

    Use exact entries only — do not invent missing data.

    Input format: A list of log entries like:

    [
      {"id": "m001", "type": "info", "timestamp": "...", "summary": "..."},
      {"id": "m002", "type": "task: open", "timestamp": "...", "summary": "Call mom"},
      ...
    ]
    Output format: A JSON list of currently open tasks (after analyzing the entire log), in this structure:


    [
      {
        "id": "mXYZ",
        "summary": "Task summary"
      }
    ]
    If no tasks are still open, return an empty list: [].
    return only JSON 

    log:
    """
    
    # Convert memory units to string format for the prompt
    memory_json_str = json.dumps(memory_units, indent=2)
    full_prompt = prompt + memory_json_str
    
    try:
        # Generate content using the Google Generative AI API
        response = client.models.generate_content(
            model="gemini-2.0-flash", 
            contents=full_prompt
        )
        
        # Parse the response
        result_text = response.text.strip()
        
        # Extract JSON from the response (handling potential markdown code blocks)
        if "```json" in result_text:
            result_text = result_text.split("```json")[1].split("```")[0].strip()
        elif "```" in result_text:
            result_text = result_text.split("```")[1].strip()
        
        try:    
            # Parse the JSON response
            active_tasks = json.loads(result_text)
            
            # Extract task summaries
            task_summaries = [task['summary'] for task in active_tasks]
            
            # Write active tasks to output file - formatted as a numbered list
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # Write tasks to the file, overwriting any existing content
            with open(output_path, 'w', encoding='utf-8') as f:
                if task_summaries:
                    f.write("Reminders:\n")
                    for i, summary in enumerate(task_summaries, 1):
                        f.write(f"{i}. {summary}\n")
                # Empty file if no tasks
            
            # Return the list of task summaries
            return task_summaries
            
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON response: {e}", file=sys.stderr)
            print(f"Raw response: {result_text}", file=sys.stderr)
            return []
    
    except Exception as e:
        print(f"Error processing memory units: {e}", file=sys.stderr)
        return []

def print_active_reminders(username):
    """
    Print active reminders for a given user as a numbered list.
    
    Args:
        username (str): The username (e.g)
    """
    active_reminders = get_active_reminders(username)
    
    # Print reminders as a numbered list if there are any
    if active_reminders:
        print("Reminders:")
        for i, reminder in enumerate(active_reminders, 1):
            print(f"{i}. {reminder}")
    else:
        # Print nothing if there are no reminders
        pass

if __name__ == "__main__":
    # Default username
    default_username = ""
    
    # Get username from command line argument if provided
    username = sys.argv[1] if len(sys.argv) > 1 else default_username
    
    # Print active reminders for the user
    print_active_reminders(username)
