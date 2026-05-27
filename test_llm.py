from crewai import LLM

llm = LLM(model="ollama_chat/qwen2.5-coder:latest")
print("Attributes of LLM:")
print(dir(llm))
print("model attribute value:", getattr(llm, "model", None))
