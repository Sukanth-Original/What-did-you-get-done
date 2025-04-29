# 🚀 what-did-you-get-done?

> *Designed for SmartGlasses – Track your time like Elon would.*

🗓 What did you get done this **week**?  
📅 What did you get done **today**?  
⏱ What did you get done in the **last 15 minutes**?

An AI version of **Elon** checks in with you every 15 minutes (or a time limit you choose).

It helps you:
- 🧠 Remember reminders from your AI conversations  
- ✅ Track productivity and completions  
- 🔍 Reflect on *how* you got things done  

---

So when someone asks:

> “**What did you get done this week?**”

You ask **Elon**

---


System Overview
This is a personal assistant system that runs on smart glasses, designed to track and remind users of tasks while maintaining conversation history and memory. The system has four main components:

1. index.ts - A Node.js server handling real-time user sessions on smart glasses
2. llm.py - A FastAPI server processing conversation requests
3. distill.py - A memory extraction engine that processes conversations
4. reminder.py - A utility to identify and present active tasks

How They Work Together
1. Real-time User Interface (index.ts)
This TypeScript file manages the smart glasses interface:

- Creates a server for multiple users with unique session tracking
- Listens for voice input via the onTranscription event
- Activates when users say the hotword "Elon"
- Schedules automatic check-ins every 15 minutes during work hours
- Detects inactivity and ends conversations after 60 seconds without input
- Forwards user messages to the LLM service for processing

The key feature is how it manages user sessions:

- Each user gets an incrementing session number
- Only the most recent session is active (older ones are terminated)
- It keeps track of active sessions in memory and persists session numbers to disk

2. LLM Processing Server (llm.py)
This Python FastAPI server handles the conversation generation:

- Receives prompts from the smart glasses application
- Manages conversation context with history and memory
- Uses Google's Gemini model for generating responses
- Stores conversation data in user-specific JSONL files
- Monitors for user inactivity to process conversations in the background
- Updates user activity timestamps

It's designed to:

- Keep track of when users were last active
- Start new conversation files after periods of inactivity
- Include memory context and active reminders in prompts

3. Memory Extraction (distill.py)
This module processes conversation histories into structured memory:

- Extracts essential information from conversations
- Categorizes data into "task: open", "task: closed", or "info" types
- Creates sequential, unique memory nodes with timestamps
- Uses Google's Gemini model to identify important information
- Maintains a record of processed conversation files
- Writes memory nodes to user-specific JSONL files

The memory extraction process:

- Processes new conversation files as they appear
- Uses a specialized prompt to distill conversations into memory nodes
- Groups related information into cohesive summaries

4. Reminder Processing (reminder.py)
- This module identifies and surfaces active tasks:

Analyzes the memory nodes for open tasks
- Determines which tasks are still relevant/open based on context
- Generates a list of active reminders
- Writes reminders to user-specific files that can be accessed by the LLM

Overall System Flow

- User speaks to their smart glasses, triggering the hotword "Elon"
- The TypeScript server captures speech and forwards it to the LLM server
- The LLM server processes the request with relevant memory and reminder context
- The response is sent back to the glasses and displayed to the user
- After inactivity, the system processes conversations into memory nodes
- Reminders are extracted from memory and made available for future interactions
- At scheduled intervals, the system proactively asks users about their progress
