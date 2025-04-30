# What Did You Get Done?

> **Designed for SmartGlasses 😎**

An AI version of **Elon** checks in with you every 15 minutes (or a time limit you choose).

It helps you:
- 🧠 Remember reminders from your AI conversations  
- ✅ Track productivity and completions  
- 🔍 Reflect on *how* you got things done  

---

## Check-In Prompts

Boils down to:

- **What did you get done in the last 15 minutes?**

To know:

- **What did you get done this week?**  
- **What did you get done today?**

So when someone asks:

> “**What did you get done this week?**”

You can ask **Elon** - *"What did I get done this week?"*.

---

## System Overview

This is a personal assistant system that runs on smart glasses, designed to track and remind users of tasks while maintaining conversation history and memory. The system has four main components:

### 1. `index.ts` – Real-time User Interface

Manages the smart glasses interface:

- Creates a server for multiple users with unique session tracking
- Listens for voice input via the `onTranscription` event
- Activates when users say the hotword `"Elon"`
- Schedules automatic check-ins every 15 minutes during work hours
- Detects inactivity and ends conversations after 60 seconds without input
- Forwards user messages to the LLM service for processing

**Session Management:**
- Each user gets an incrementing session number
- Only the most recent session is active (older ones are terminated)
- Tracks active sessions in memory and persists session numbers to disk

---

### 2. `llm.py` – LLM Processing Server

A FastAPI server handling conversation generation:

- Receives prompts from the smart glasses application
- Manages conversation context with history and memory
- Uses Google's Gemini model for generating responses
- Stores conversation data in user-specific JSONL files
- Monitors user inactivity to process conversations in the background
- Updates user activity timestamps

---

### 3. `distill.py` – Memory Extraction Engine

Processes conversation histories into structured memory:

- Extracts essential information from conversations
- Categorizes data into:
  - `task: open`
  - `task: closed`
  - `info`
- Creates sequential, unique memory nodes with timestamps
- Uses Google's Gemini model to identify important information
- Writes memory nodes to user-specific JSONL files

**Processing Flow:**
- Detects new conversation files
- Uses prompt-based distillation
- Groups related information into summaries

---

### 4. `reminder.py` – Reminder Utility

Identifies and surfaces active tasks:

- Analyzes memory nodes for open tasks
- Determines task relevancy and status
- Generates a list of active reminders
- Writes reminders to user-specific files accessed by the LLM

---

## Overall System Flow

1. User speaks to smart glasses, triggering the hotword **"Elon"**
2. `index.ts` captures speech and forwards it to `llm.py`
3. LLM server responds using relevant memory and reminders
4. Response is displayed back on the glasses
5. After inactivity, conversations are processed into memory nodes by `distill.py`
6. `reminder.py` extracts active reminders
7. Scheduled check-ins continue every 15 minutes

---

## To run this locally in your server:

Reference: https://docs.augmentos.org/getting-started

### Terminal 1: Expose Local Server via Ngrok

`ngrok http --domain=your-custom-name.ngrok-free.app 80`


Purpose: Creates a public HTTPS endpoint for your local server.

Ensure that ngrok is installed and authed.

### Terminal 2: Build and Start SmartGlasses App UI

`bun run build`

`bun run start`


Purpose: Bundles and launches your index.ts interface (real-time user interaction).


### Terminal 3: Start the LLM FastAPI Backend

`cd memory`

`uvicorn llm:app --host 0.0.0.0 --port 8000`


Purpose: Runs llm.py as a FastAPI server to handle smartglass prompts and memory processing.

---
*A Sukanth Original Design, 2025*
