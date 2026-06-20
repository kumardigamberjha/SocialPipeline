import os
import sys
from dotenv import load_dotenv
from crewai import LLM

# Load .env file from the app directory
load_dotenv("app/.env")

api_key = os.getenv("GEMMA_API_KEY")

print(f"Testing Gemma model with API key: {api_key}")

if not api_key:
    print("Error: GEMMA_API_KEY is not set in app/.env")
    sys.exit(1)

try:
    print("Initializing LLM via Native Ollama Local Provider...")
    llm = LLM(
        # Use native 'ollama/' prefix so CrewAI handles the parsing directly
        model="ollama/gemma4:31b-cloud", 
        
        # Point to the root local Ollama API server endpoint
        base_url="http://localhost:11434", 
        
        temperature=0.7
    )
    
    print("Sending test prompt: 'Hi, are you working?'...")
    response = llm.call("Hi, are you working?")
    
    print("\n✅ Success! The model responded:")
    print("-" * 40)
    print(response)
    print("-" * 40)
    
except Exception as e:
    print("\n❌ Failed to connect or authenticate.")
    print("Error details:")
    print(str(e))
