import os
import json
import sys
from google import genai
from google.genai import types
from supabase import create_client
from dotenv import load_dotenv

def init_supabase():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    dotenv_path = os.path.join(base_dir, 'mentra.env')
    load_dotenv(dotenv_path=dotenv_path)

    supabase_url = os.getenv("ELON_SUPABASE_URL")
    supabase_service = os.getenv("ELON_SUPABASE_SERVICE")
    return create_client(supabase_url, supabase_service)

def get_reminders(username):
    """
    Process memory units for a user, return open and closed tasks after deduplication and Supabase sync.
    """
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    memory_path = os.path.join(base_dir, 'memory', 'summaries', f"{username}.jsonl")
    dotenv_path = os.path.join(base_dir, 'mentra.env')
    load_dotenv(dotenv_path=dotenv_path)

    if not os.path.exists(memory_path):
        print(f"Error: Memory file not found for user {username}", file=sys.stderr)
        return [], []

    api_key = os.getenv("GOOGLE_GENAI_API_KEY2")
    if not api_key:
        print("Error: GOOGLE_GENAI_API_KEY2 not set", file=sys.stderr)
        return [], []

    client = genai.Client(api_key=api_key)
    supabase = init_supabase()

    try:
        with open(memory_path, 'r', encoding='utf-8') as f:
            memory_units = [json.loads(line) for line in f if line.strip()]
    except Exception as e:
        print(f"Error reading memory file: {e}", file=sys.stderr)
        return [], []

    if not memory_units:
        print(f"Warning: No memory units found for user {username}", file=sys.stderr)
        return [], []

    # Fetch existing reminders from Supabase
    open_existing = supabase.table("open_reminders").select("content").eq("user_id", username).execute().data
    closed_existing = supabase.table("closed_reminders").select("content").eq("user_id", username).execute().data
    #open_existing_set = set(entry['content'] for entry in open_existing if entry.get('content'))
    closed_existing_set = set(entry['content'] for entry in closed_existing if entry.get('content'))

    # Add context of existing reminders to the prompt
    prompt = """
You are given a chronological log of user events. Each entry includes an id, type, timestamp, and summary.
Your task is to determine the current state of tasks: which are still active and which are completed.

Some tasks are marked "task: open" but later implicitly or explicitly closed via "task: closed" or related "info" entries.

task: open: Tasks that are pending or need action.

task: closed: Tasks that are completed, canceled, or no longer need action.

info: Contextual details or preferences, which do not require action. (totally avoid this type of entry)


Use the full history to infer final task state.

Below is the user's task history followed by known previously recorded tasks.

Return JSON:
{
  "open_tasks": [{"id": "mXYZ", "summary": "..."}],
  "closed_tasks": [{"id": "mABC", "summary": "..."}]
}

Return only JSON. 

Previously recorded closed tasks:
""" + "\n".join(f"- {content}" for content in closed_existing_set) + """

Create new closed tasks that are not found in previously recorded closed tasks.

If no tasks are currently open or has been closed already, return: ["no active reminders"].
return only JSON 


Task log:
"""
    memory_json_str = json.dumps(memory_units, indent=2)
    full_prompt = prompt + memory_json_str
    print(full_prompt)

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash", 
            contents=full_prompt
        )
        result_text = response.text.strip()

        if "```json" in result_text:
            result_text = result_text.split("```json")[1].split("```")[0].strip()
        elif "```" in result_text:
            result_text = result_text.split("```")[1].strip()

        task_results = json.loads(result_text)
        open_task_summaries = [task['summary'] for task in task_results.get('open_tasks', [])]
        closed_task_summaries = [task['summary'] for task in task_results.get('closed_tasks', [])]

        # Deduplicate based on content
        new_open_tasks = [s for s in open_task_summaries]
        new_closed_tasks = [s for s in closed_task_summaries if s not in closed_existing_set]
        
        supabase.table("open_reminders").delete().eq("user_id", username).execute()

        # Insert into Supabase
        if new_open_tasks:           
    # Join tasks into a single string
            supabase.table("open_reminders").delete().eq("user_id", username).execute()

            combined_content = ", ".join(new_open_tasks)
            print("New Open Tasks:", new_open_tasks)
            print(combined_content)
            supabase.table("open_reminders").insert({
                "user_id": username,
                "content": combined_content
            }).execute() ################### change this 

        if new_closed_tasks:

            closed_payload = [{"user_id": username, "content": summary} for summary in new_closed_tasks]
            supabase.table("closed_reminders").insert(closed_payload).execute()

        return open_task_summaries, closed_task_summaries

    except json.JSONDecodeError as e:
        print(f"Error parsing JSON response: {e}", file=sys.stderr)
        print(f"Raw response: {result_text}", file=sys.stderr)
        return [], []

    except Exception as e:
        print(f"Error processing memory units: {e}", file=sys.stderr)
        return [], []

def print_reminders(username):
    open_reminders, closed_reminders = get_reminders(username)

    if open_reminders:
        print("Open Reminders:")
        for i, reminder in enumerate(open_reminders, 1):
            print(f"{i}. {reminder}")

    if closed_reminders:
        print("\nCompleted Reminders:")
        for i, reminder in enumerate(closed_reminders, 1):
            print(f"{i}. {reminder}")

def print_active_reminders(username):
    open_reminders, _ = get_reminders(username)
    if open_reminders:
        print("Reminders:")
        for i, reminder in enumerate(open_reminders, 1):
            print(f"{i}. {reminder}")

def print_closed_reminders(username):
    _, closed_reminders = get_reminders(username)
    if closed_reminders:
        print("\nCompleted Reminders:")
        for i, reminder in enumerate(closed_reminders, 1):
            print(f"{i}. {reminder}")

if __name__ == "__main__":
    default_username = "ontelligency_gmail_com"
    username = sys.argv[1] if len(sys.argv) > 1 else default_username
    print_reminders(username)
