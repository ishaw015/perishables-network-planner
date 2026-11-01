import os, time, json
from dotenv import load_dotenv
from google import genai
from google.genai import types
from agent.graph import Draft, SYSTEM, POLICY, _facts_text
from agent.facts import build_facts

load_dotenv()
model = os.getenv("GEMINI_MODEL")
print("model:", model)
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"],
                      http_options=types.HttpOptions(timeout=40000))
facts = build_facts(600)
prompt = f"{POLICY}\n\nFACTS:\n{_facts_text(facts)}\n\nQUESTION: Why is the order quantity what it is?"

for label, cfg in {
    "A: json mode, no schema": types.GenerateContentConfig(
        system_instruction=SYSTEM, response_mime_type="application/json", temperature=0.0),
    "B: json mode + schema": types.GenerateContentConfig(
        system_instruction=SYSTEM, response_mime_type="application/json",
        response_schema=Draft, temperature=0.0),
}.items():
    t = time.time()
    try:
        r = client.models.generate_content(model=model, contents=prompt, config=cfg)
        print(f"{label}: OK in {time.time()-t:.1f}s")
        print(r.text[:500])
    except Exception as e:
        print(f"{label}: FAILED in {time.time()-t:.1f}s -> {type(e).__name__}: {str(e)[:300]}")