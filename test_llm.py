import os
from crewai import LLM
from dotenv import load_dotenv
import time

load_dotenv("app/.env")

nvidia_key = os.environ.get("NVIDIA_API_KEY")

def test_model(model_name):
    print(f"Testing model: {model_name}")
    try:
        llm = LLM(
            model=model_name,
            api_key=nvidia_key,
            api_base="https://integrate.api.nvidia.com/v1",
            timeout=10,
        )
        t0 = time.time()
        res = llm.call(messages=[{"role": "user", "content": "Say hello."}])
        print(f"Success! Time: {time.time()-t0:.2f}s, Response: {res}")
    except Exception as e:
        print(f"Error: {e}")

test_model("qwen/qwen3.5-122b-a10b")
test_model("openai/qwen/qwen3.5-122b-a10b")
test_model("nvidia_nim/qwen/qwen3.5-122b-a10b")
