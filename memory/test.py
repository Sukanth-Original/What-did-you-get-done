
from groq import Groq
import os
from dotenv import load_dotenv

# Load .env file
base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
dotenv_path = os.path.join(base_dir, 'mentra.env')
load_dotenv(dotenv_path=dotenv_path)

# Fetch API key
api_key = os.getenv("AUGMENT_GROQ_API_KEY")
if not api_key:
    raise ValueError("AUGMENT_GROQ_API_KEY not found in environment variables.")

# Create client with explicit API key
client = Groq(api_key=api_key)

# Make chat completion call
chat_completion = client.chat.completions.create(
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Explain the importance of fast language models"},
    ],
    model="llama-3.3-70b-versatile"  # Correct model name
)

# Output result
print(chat_completion.choices[0].message.content)
