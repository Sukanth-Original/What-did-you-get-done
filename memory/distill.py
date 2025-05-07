# distill.py

import json
import os
from datetime import datetime
from reminder import print_active_reminders
from dotenv import load_dotenv

from google import genai
from google.genai import types

base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
dotenv_path = os.path.join(base_dir, 'mentra.env')
load_dotenv(dotenv_path=dotenv_path)

# Replace OpenRouter API key with Gemini API key
gemini_api_key = os.getenv("GOOGLE_GENAI_API_KEY3")

# Initialize the Gemini client
client = genai.Client(api_key=gemini_api_key)


def extract_jsonl_text(filepath):
    """Extract conversation data and timestamps from a single JSONL file."""
    convo_lines = []
    timestamps = []
    
    with open(filepath, 'r', encoding='utf-8') as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                prompt = entry.get("prompt", "").strip()
                response = entry.get("response", "").strip()
                
                # Extract timestamp if available
                timestamp = entry.get("timestamp", "")
                if not timestamp:
                    timestamp = entry.get("created_at", "")  # Try alternative field
                
                # Format the timestamp consistently
                if timestamp:
                    try:
                        # Attempt to parse and standardize timestamp format
                        dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                        formatted_timestamp = dt.isoformat()
                        timestamps.append(formatted_timestamp)
                    except ValueError:
                        # If timestamp parsing fails, use current time
                        timestamps.append(datetime.now().isoformat())
                else:
                    # If no timestamp found, use current time
                    timestamps.append(datetime.now().isoformat())
                
                convo_lines.append(f"User: {prompt}\nAI: {response}\n")
            except json.JSONDecodeError:
                continue
    
    convo_data = "\n".join(convo_lines)
    return convo_data, timestamps


def get_processed_files(tracker_path):
    """Get list of already processed conversation files."""
    processed_files = set()
    if os.path.exists(tracker_path):
        with open(tracker_path, 'r', encoding='utf-8') as file:
            for line in file:
                processed_files.add(line.strip())
    return processed_files


def mark_as_processed(tracker_path, file_path):
    """Mark a file as processed by adding it to the tracker file."""
    with open(tracker_path, 'a', encoding='utf-8') as file:
        file.write(f"{file_path}\n")


def get_conversation_files(folder_path):
    """Get all conversation JSONL files from a folder (relative paths)."""
    if not os.path.exists(folder_path):
        print(f"Folder not found: {folder_path}")
        return []

    files = []
    for filename in os.listdir(folder_path):
        if filename.startswith("conversation_") and filename.endswith(".jsonl"):
            files.append(filename)  # Relative filename
    return files


system_instruction = """
Prompt for Distillation Engine:
You are a memory extraction engine tasked with distilling essential information from a conversation transcript. Your goal is to create compact, high-value memory nodes that capture important tasks, reminders, and personal context. When multiple related details arise, group them together into a cohesive summary.

Memory Node Format:
Each memory node must include:

id: Unique identifier (e.g., "m001", "m002").

type: One of the following:

task: open: Tasks that are still pending or need action.

task: closed: Tasks that are completed or canceled.

info: Personal details, preferences, or status updates that are not actionable.

timestamp: The timestamp of the message.

summary: A brief, cohesive summary that distills the essence of the key information. Condense related facts into a single memory node when appropriate.

Distillation Rules:
Condense related details: If multiple facts relate to the same entity or event (e.g., a person, project, or goal), combine them into a single memory node.

Example: If "User needs to send the report by 5 PM" and "User needs to include the budget in the report" are mentioned, combine them into one task node.

Avoid redundancy: Ensure the summary is as compact as possible, avoiding separate nodes for the same core idea.

Example: Do not create multiple nodes for "Reminder: Call Anna" — merge any updates or clarifications into a single node.

Categorize appropriately: Ensure each node is categorized based on its content:

task: open: Tasks that are pending or need action.

task: closed: Tasks that are completed, canceled, or no longer need action.

info: Contextual details or preferences, which do not require action.

Minimize verbosity: Capture only the most important information in a concise format. Skip procedural details, clarifications, and repetitive content.

Example Output:
Scenario: The conversation covers a user's work tasks, preferences, and a few personal details.

Example 1:
User mentions:

"I need to send the financial report to John by 5 PM today."

"I also need to include the budget in the report."

"John prefers updates via email."

Optimized Memory Node Output:

[
  {
    "id": "m001",
    "type": "task: open",
    "timestamp": "2025-04-25T08:30:00Z",
    "summary": "Send the financial report to John by 5 PM, including the budget. John prefers updates via email."
  }
]
Example 2:
User mentions:

"I completed the marketing plan for Q3."

"I finished drafting the email to the team about the new product launch."

"The launch date is set for next Monday."

Optimized Memory Node Output:


[
  {
    "id": "m002",
    "type": "task: closed",
    "timestamp": "2025-04-25T09:00:00Z",
    "summary": "Completed the marketing plan for Q3 and drafted the email to the team about the new product launch."
  },
  {
    "id": "m003",
    "type": "info",
    "timestamp": "2025-04-25T09:00:00Z",
    "summary": "The new product launch date is set for next Monday."
  }
]
Example 3:
User mentions:

"I still need to call Tom about the design feedback."

"Also, I'll need to review the budget report tomorrow."

Optimized Memory Node Output:


[
  {
    "id": "m004",
    "type": "task: open",
    "timestamp": "2025-04-25T09:15:00Z",
    "summary": "Call Tom about the design feedback."
  },
  {
    "id": "m005",
    "type": "task: open",
    "timestamp": "2025-04-25T09:15:00Z",
    "summary": "Review the budget report tomorrow."
  }
]
Key Insights:
Condensing Related Information: When multiple tasks are tied together (e.g., "send the report by 5 PM" and "include the budget"), they are merged into one cohesive node. This reduces redundant nodes.

Proper Categorization: Tasks that are pending are categorized as task: open, tasks that are completed are categorized as task: closed, and personal information or context is categorized as info.

Minimalistic & Efficient: Redundant details (like specifying an action multiple times) are avoided, while key information (like preferences) is included succinctly.
"""


def graph_memory(system_instruction: str, convo_data: str) -> str:
    """Generate memory nodes from conversation data using Gemini API."""
    try:
        # Create a combined prompt with system instruction and conversation data
        full_prompt = f"{system_instruction.strip()}\n\nPlease extract memory nodes from the following conversation:\n\n{convo_data.strip()}"
        
        # Generate content using Gemini model
        response = client.models.generate_content(
            model="gemini-2.0-flash", 
            contents=full_prompt
        )
        
        # Extract the response text
        if response and hasattr(response, 'text'):
            return response.text
        else:
            return "Gemini returned no output or malformed response."
    except Exception as e:
        return f"Error during Gemini API call: {e}"


def save_memory_graph(json_memory_data, output_path):
    """
    Takes JSON memory data (as a list or raw JSON string), parses, and appends it in JSONL format.
    Maintains sequential IDs across sessions and updates link references.
    """
    # Check if we received an error message or empty response from the LLM
    if not json_memory_data or (isinstance(json_memory_data, str) and 
                               (json_memory_data.startswith("LLM returned no output") or 
                                json_memory_data.startswith("Error"))):
        print(f"Warning: Invalid response from LLM: {json_memory_data}")
        print("No new data will be saved.")
        return 0, None  # Return 0 new entries and None for total
        
    # Process input data
    if isinstance(json_memory_data, str):
        json_memory_data = json_memory_data.strip()
        if json_memory_data.startswith("```json"):
            json_memory_data = json_memory_data.lstrip("```json").rstrip("```").strip()
        elif json_memory_data.startswith("```"):
            json_memory_data = json_memory_data.lstrip("```").rstrip("```").strip()
            
        try:
            new_data = json.loads(json_memory_data)
        except json.JSONDecodeError as e:
            print(f"Error: Could not parse JSON: {e}")
            print(f"Problematic content (first 200 chars): {json_memory_data[:200]}...")
            return 0, None  # Return instead of raising exception
    elif isinstance(json_memory_data, list):
        new_data = json_memory_data
    else:
        print(f"Error: Input must be a JSON string or a list of dictionaries, got {type(json_memory_data)}")
        return 0, None
        
    if not isinstance(new_data, list) or not all(isinstance(entry, dict) for entry in new_data):
        print("Error: Parsed data must be a list of dictionaries.")
        return 0, None
    
    if len(new_data) == 0:
        print("No valid memory nodes found to save.")
        return 0, None
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Read existing data to find highest ID
    existing_data = []
    highest_id_num = 0
    
    try:
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            with open(output_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            entry = json.loads(line)
                            existing_data.append(entry)
                            
                            # Extract numeric part of ID
                            if "id" in entry:
                                id_str = entry["id"]
                                if id_str.startswith("m") and id_str[1:].isdigit():
                                    id_num = int(id_str[1:])
                                    highest_id_num = max(highest_id_num, id_num)
                        except json.JSONDecodeError:
                            continue
    except Exception as e:
        print(f"Warning: Error reading existing data: {e}")
    
    # Create mapping of old IDs to new IDs for updating links
    id_mapping = {}
    for i, entry in enumerate(new_data):
        if "id" in entry:
            old_id = entry["id"]
            new_id_num = highest_id_num + i + 1
            new_id = f"m{new_id_num:03d}"
            id_mapping[old_id] = new_id
            entry["id"] = new_id  # Update ID
    
    # Update links within the new data
    for entry in new_data:
        if "links" in entry and isinstance(entry["links"], list):
            for link in entry["links"]:
                if "target_id" in link:
                    target_id = link["target_id"]
                    # If target refers to another new node, update with new ID
                    if target_id in id_mapping:
                        link["target_id"] = id_mapping[target_id]
                    # If target refers to a non-existent earlier node (like m002 when it should be m008),
                    # try to infer the correct existing node based on position
                    elif target_id.startswith("m") and target_id[1:].isdigit():
                        target_num = int(target_id[1:])
                        # Only fix references where the target ID is lower than expected range
                        if target_num <= len(new_data) and highest_id_num > 0:
                            # Calculate offset: if target is m002 and highest existing is m008, 
                            # we add (8-2)=6 to make it m008
                            offset = highest_id_num - len(new_data)
                            if offset > 0:
                                corrected_num = target_num + offset
                                corrected_id = f"m{corrected_num:03d}"
                                print(f"Correcting link target from {target_id} to {corrected_id}")
                                link["target_id"] = corrected_id
    
    # Append new data
    with open(output_path, "a", encoding="utf-8") as f:
        for entry in new_data:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            
    print(f"Successfully added {len(new_data)} new memory nodes. Total nodes: {len(existing_data) + len(new_data)}")
    return len(new_data), len(existing_data) + len(new_data)


def load_prev_memory(file_path: str) -> str:
    """Load previous memory nodes for reference."""
    if not os.path.exists(file_path):
        return ""
    with open(file_path, 'r', encoding='utf-8') as f:
        prev_memory = f.read()
    return prev_memory


def process_new_conversations(user_id: str):
    """Process new, unprocessed conversation files for a specific user."""
    if not user_id:
        print("Error: User ID is required.")
        return
        
    script_dir = os.path.dirname(os.path.realpath(__file__))
    
    # Define paths with user_id
    summaries_folder = os.path.normpath(os.path.join(script_dir, "..", "memory", "summaries"))
    memory_output_path = os.path.normpath(os.path.join(summaries_folder, f"{user_id}.jsonl"))
    conversations_folder = os.path.normpath(os.path.join(script_dir, "..", "memory", "database", user_id))
    tracker_path = os.path.normpath(os.path.join(script_dir, "..", "memory", "processed_files", f"{user_id}_processed.txt"))
    
    # Ensure the needed directories exist
    os.makedirs(os.path.dirname(memory_output_path), exist_ok=True)
    os.makedirs(os.path.dirname(tracker_path), exist_ok=True)
    
    # Get list of processed files
    processed_files = get_processed_files(tracker_path)
    
    # Get all conversation files
    all_files = get_conversation_files(conversations_folder)
    
    # Filter for new files
    new_files = [f for f in all_files if f not in processed_files]
    
    if not new_files:
        print(f"No new conversation files to process for user: {user_id}")
        return
    
    print(f"Found {len(new_files)} new conversation file(s) to process for user: {user_id}")
    
    # Process each new file
    for rel_path in new_files:
        file_path = os.path.join(conversations_folder, rel_path)
        
        try:
            print(f"Processing file: {os.path.basename(file_path)}")
            
            # Extract conversation text and timestamps from the file
            convo_data, timestamps = extract_jsonl_text(file_path)
            
            if not convo_data.strip():
                print(f"Warning: No valid conversation data found in {file_path}")
                mark_as_processed(tracker_path, rel_path)
                continue
            
            # Add timestamps to context for the LLM
            timestamp_context = "Available timestamps for this conversation:\n"
            for i, ts in enumerate(timestamps):
                timestamp_context += f"Message {i+1}: {ts}\n"
            
            # Combine conversation data with timestamp information
            full_context = f"{timestamp_context}\n\nConversation:\n{convo_data}"
            
            # Generate memory nodes from conversation with timestamps
            json_memory_data = graph_memory(system_instruction, full_context)
            print(json_memory_data)
            
            # Save memory nodes to graph
            new_entries, total_entries = save_memory_graph(json_memory_data, memory_output_path)
            
            if new_entries > 0:
                print(f"Processed {file_path}: Added {new_entries} memory nodes for user {user_id}")
            else:
                print(f"No new memory nodes extracted from {file_path} for user {user_id}")
            
            # Mark file as processed
            mark_as_processed(tracker_path, rel_path)
            
        except Exception as e:
            print(f"Error processing {file_path} for user {user_id}: {e}")
    
    print(f"Finished processing {len(new_files)} new conversation file(s) for user {user_id}.")

    print_active_reminders(user_id)
    print(f"Done processing active reminders")



if __name__ == "__main__":
    # Example usage:
    # process_new_conversations("user123")
    
    # For backward compatibility, you can uncomment the following line:
    
    import sys
    if len(sys.argv) > 1:
        process_new_conversations(sys.argv[1])
    else:
        print("Please provide a user ID as a command-line argument.")
        print("Example: python facts_organiser.py user123")