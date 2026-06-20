import sys
from crewai import LLM
import inspect
print(inspect.signature(LLM.__init__))
