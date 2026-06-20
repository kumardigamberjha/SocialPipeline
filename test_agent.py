from crewai import Agent
from langchain_google_genai import ChatGoogleGenerativeAI

llm = ChatGoogleGenerativeAI(model="gemini-3.5-flash", api_key="dummy")
try:
    agent = Agent(role="test", goal="test", backstory="test", llm=llm)
    print("Success")
except Exception as e:
    print(e)
