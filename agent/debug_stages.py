import time
from agent.facts import build_facts
from agent.graph import call_gemini
from agent.verify import verify

t = time.time(); facts = build_facts(600)
print(f"facts: {time.time()-t:.1f}s")

t = time.time()
d = call_gemini("Why is the order quantity what it is, and why is it short?", facts)
print(f"gemini: {time.time()-t:.1f}s")
print(d)

t = time.time(); rep = verify(d, facts)
print(f"verify: {time.time()-t:.2f}s")
print(rep)