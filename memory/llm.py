from fastapi import FastAPI, Request, BackgroundTasks
from pydantic import BaseModel
import uvicorn
import os
import json
import time
import threading
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
from dotenv import load_dotenv
from google import genai
from google.genai import types
from distill import process_new_conversations
from supabase import create_client
import sys

# Load .env file
base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
dotenv_path = os.path.join(base_dir, 'mentra.env')
load_dotenv(dotenv_path=dotenv_path)

# Fetch API key from environment variable
api_key = os.getenv("GOOGLE_GENAI_API_KEY")
supabase_url = os.getenv("ELON_SUPABASE_URL")
supabase_service = os.getenv("ELON_SUPABASE_SERVICE")

# Configuration constants
INACTIVITY_THRESHOLD_MINUTES = 2  # Time threshold to start a new conversation
INACTIVITY_CHECK_INTERVAL = 60  # Check for inactive conversations every 60 seconds

# Initialize the Google GenAI client with the API key
client = genai.Client(api_key=api_key)
supabase = create_client(supabase_url, supabase_service)

instruction = """
You are Elon, a friendly assistant in smart glasses. 
Listen actively to what the user says they have done.
Remind the user of open tasks only if any.
Keep the conversations brief and stop when necessary to keep the user productive.
If user is working and sharing active progress, try to end the conversation to keep the user productive.
No hallucinations at all.
Answer within 40 words.
"""

app = FastAPI()

# Track active users and their last interaction time
active_users = {}  # user_id -> last_timestamp
inactivity_checker_running = False

class PromptRequest(BaseModel):
    prompt: str
    user_id: str

def sanitize_user_id(user_id: str) -> str:
    """Sanitize user ID for use in file paths"""
    return user_id.replace('@', '_').replace('.', '_')

def get_user_dir(user_id: str) -> str:
    """Generate the path to the user-specific database directory"""
    sanitized_id = sanitize_user_id(user_id)
    user_dir = os.path.join(base_dir, "memory", "database", sanitized_id)
    os.makedirs(user_dir, exist_ok=True)
    return user_dir

def get_user_memory_path(user_id: str) -> str:
    """Generate the path to the user-specific memory file"""
    sanitized_id = sanitize_user_id(user_id)
    memory_dir = os.path.join(base_dir, "memory", "summaries")
    os.makedirs(memory_dir, exist_ok=True)
    return os.path.join(memory_dir, f"{sanitized_id}.jsonl")

def get_conversation_filename(user_id: str) -> str:
    """Generate a timestamp-based filename for a new conversation"""
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return os.path.join(get_user_dir(user_id), f"conversation_{timestamp}.jsonl")

def get_all_user_ids():
    """Get a list of all user IDs from the database directory"""
    database_dir = os.path.join(base_dir, "memory", "database")
    if not os.path.exists(database_dir):
        return []
    return os.listdir(database_dir)

def clear_memory(user_id: str) -> str:
    # Get the path to the user's memory file
    memory_path = get_user_memory_path(user_id)
    
    try:
        # Open the file in write mode and clear its contents
        with open(memory_path, "w") as memory_file:
            memory_file.truncate(0)  # Clear the contents of the file
        
        return f"Memory cleared for user {user_id}"
    except Exception as e:
        return f"Error clearing memory for user {user_id}: {str(e)}"


def check_for_inactive_conversations():
    """Actively check for inactive conversations and process them"""
    global active_users
    
    # Get current time
    current_time = datetime.now()
    
    # Find inactive users and process their conversations
    inactive_users = []
    for user_id, last_timestamp in active_users.items():
        time_diff = current_time - last_timestamp
        if time_diff > timedelta(minutes=INACTIVITY_THRESHOLD_MINUTES):
            print(f"Detected inactivity for user {user_id}, processing conversations...")
            try:
                process_new_conversations(sanitize_user_id(user_id))
                clear_memory(sanitize_user_id(user_id))
                inactive_users.append(user_id)
            except Exception as e:
                print(f"Error processing conversations for user {user_id}: {e}")
    
    # Remove processed inactive users from active_users
    for user_id in inactive_users:
        if user_id in active_users:
            del active_users[user_id]

    # Also check users who might not be in active_users dict by scanning directories
    database_users = get_all_user_ids()
    for user_id in database_users:
        if user_id not in active_users:
            # Check most recent conversation file timestamp
            user_dir = os.path.join(base_dir, "memory", "database", user_id)
            if os.path.exists(user_dir):
                files = [f for f in os.listdir(user_dir) if f.endswith(".jsonl")]
                if files:
                    files.sort(reverse=True)
                    most_recent_file = os.path.join(user_dir, files[0])
                    try:
                        with open(most_recent_file, "r") as f:
                            entries = [json.loads(line) for line in f]
                            if entries:
                                last_entry_time = datetime.fromisoformat(entries[-1]["timestamp"])
                                time_diff = current_time - last_entry_time
                                if (time_diff > timedelta(minutes=INACTIVITY_THRESHOLD_MINUTES)):  # Only process recent enough conversations
                                    print(f"Processing forgotten user {user_id}...")
                                    process_new_conversations(user_id)
                                    clear_memory(user_id)
                    except Exception as e:
                        print(f"Error checking inactive user {user_id}: {e}")

def inactivity_checker_thread():
    """Background thread to periodically check for and process inactive conversations"""
    global inactivity_checker_running
    
    print("Starting inactivity checker thread...")
    while inactivity_checker_running:
        try:
            check_for_inactive_conversations()
        except Exception as e:
            print(f"Error in inactivity checker: {e}")
        
        time.sleep(INACTIVITY_CHECK_INTERVAL)
    
    print("Inactivity checker thread stopped.")

def start_inactivity_checker():
    """Start the background inactivity checker thread if not already running"""
    global inactivity_checker_running
    
    if not inactivity_checker_running:
        inactivity_checker_running = True
        thread = threading.Thread(target=inactivity_checker_thread, daemon=True)
        thread.start()
        print("Inactivity checker started successfully")

def stop_inactivity_checker():
    """Stop the background inactivity checker thread"""
    global inactivity_checker_running
    inactivity_checker_running = False

def load_conversation_history(user_id: str):
    """
    Load both the user-specific conversation history and concise memory interactions.
    Returns:
        - Current conversation filename (if any).
        - Boolean indicating whether to start a new conversation.
        - Previous conversation content for context
    """
    user_dir = get_user_dir(user_id)
    
    
    # Get list of conversation files sorted by timestamp (most recent first)
    files = []
    if os.path.exists(user_dir):
        files = [f for f in os.listdir(user_dir) if f.endswith(".jsonl")]
        files.sort(reverse=True)
    
    # Check if we need to start a new conversation
    start_new_conversation = True
    current_file = None
    last_timestamp = None
    conversation_history = ""
    
    # Load the most recent conversation if needed
    if files:
        current_file = files[0]
        file_path = os.path.join(user_dir, current_file)
        entries = []
        
        with open(file_path, "r") as f:
            for line in f:
                entry = json.loads(line)
                entries.append(entry)
                conversation_history += f"User: {entry['prompt']}\nAssistant: {entry['response']}\n\n"
        
        # Check if the conversation is recent enough
        if entries:
            last_timestamp = datetime.fromisoformat(entries[-1]["timestamp"])
            time_difference = datetime.now() - last_timestamp
            start_new_conversation = time_difference > timedelta(minutes=INACTIVITY_THRESHOLD_MINUTES)
    
    return current_file, start_new_conversation, conversation_history



def fetch_reminders_from_supabase(user_id: str) -> Tuple[str, str]:
    """
    Fetch open and closed reminders for a specific user from Supabase.

    Args:
        user_id (str): The ID of the user to fetch reminders for.

    Returns:
        Tuple[str, str]: A tuple containing two strings:
            - A numbered list of open reminders.
            - A numbered list of closed reminders.
    """
    try:
        # Fetch open reminders
        open_reminders_data = supabase.table("open_reminders").select("content").eq("user_id", user_id).execute().data
        open_reminders = [entry['content'] for entry in open_reminders_data if entry.get('content')]

        # Fetch closed reminders
        closed_reminders_data = supabase.table("closed_reminders").select("content").eq("user_id", user_id).execute().data
        closed_reminders = [entry['content'] for entry in closed_reminders_data if entry.get('content')]

        # Format as numbered lists
        open_reminders_str = "\n".join([f"{i+1}. {reminder}" for i, reminder in enumerate(open_reminders)])
        closed_reminders_str = "\n".join([f"{i+1}. {reminder}" for i, reminder in enumerate(closed_reminders)])

        return open_reminders_str, closed_reminders_str

    except Exception as e:
        print(f"Error fetching reminders from Supabase: {e}", file=sys.stderr)
        return "", ""


def store_conversation(user_id: str, prompt: str, response: str, current_file=None, start_new=False):
    """Store conversation in the current timestamp file or create a new one"""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "prompt": prompt,
        "response": response
    }
    
    if current_file is None or start_new:
        conversation_file = get_conversation_filename(user_id)
    else:
        conversation_file = os.path.join(get_user_dir(user_id), current_file)
    
    with open(conversation_file, "a") as f:
        f.write(json.dumps(entry) + "\n")
    
    return os.path.basename(conversation_file)

def update_user_activity(user_id: str):
    """Update the last activity timestamp for a user"""
    global active_users
    active_users[user_id] = datetime.now()



@app.post("/generate")
async def generate_text(data: PromptRequest, background_tasks: BackgroundTasks):
    # Update user activity timestamp
    update_user_activity(data.user_id)
    
    # Load conversation history and determine if this is a new conversation
    current_file, start_new_conversation, conversation_history = load_conversation_history(data.user_id)
    
    open_reminders = ""
    completed_reminders = ""
    sanitize_id = sanitize_user_id(data.user_id)
    open_reminders, completed_reminders = fetch_reminders_from_supabase(sanitize_id)

    if open_reminders is None:
        open_reminders = "No active reminders"

    if completed_reminders is None:
        completed_reminders = "No completed tasks"

    if start_new_conversation:
    # Fetch open and closed reminders directly from Supabase
        print(f"New conversation detected for {sanitize_id}")


    
    # Define the content generation configuration
    config = types.GenerateContentConfig(
        system_instruction=instruction,
        max_output_tokens=150,
        temperature=0.7,
    )
    
    # Format a full prompt with just the reminders and conversation history
    full_prompt = f"""
Completed Tasks:
{completed_reminders}

Active Reminders:
{open_reminders}

Previous Conversation:
{conversation_history}

Current User Message:
{data.prompt}
"""
    
    # Generate a response from the model
    response = client.models.generate_content(
        model='gemini-2.0-flash-001',
        contents=full_prompt,
        config=config
    )
    
    # Extract the response text
    response_text = response.text
    print(full_prompt)
    
    # Store conversation in current file or create a new one
    current_file = store_conversation(data.user_id, data.prompt, response_text, 
                                     current_file, start_new_conversation)
    
    return {"response": response_text}

@app.on_event("startup")
def startup_event():
    """Start background tasks when the FastAPI app starts"""
    start_inactivity_checker()

@app.on_event("shutdown")
def shutdown_event():
    """Stop background tasks when the FastAPI app shuts down"""
    stop_inactivity_checker()

if __name__ == "__main__":
    uvicorn.run("proactive_llm:app", host="0.0.0.0", port=8000, reload=True)