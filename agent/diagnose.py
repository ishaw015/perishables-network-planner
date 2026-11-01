import os
from dotenv import load_dotenv
from google import genai

load_dotenv()
key = os.getenv("GEMINI_API_KEY")
print("key loaded:", bool(key), "| length:", len(key or ""))
model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
print("model:", model)

client = genai.Client(api_key=key)
try:
    r = client.models.generate_content(model=model, contents="Reply with the single word: ok")
    print("plain call OK:", r.text)
except Exception as e:
    print("plain call FAILED:", type(e).__name__, str(e)[:600].replace(key or "x", "***"))

print("\nModels your key can use:")
try:
    for m in client.models.list():
        if "generateContent" in (m.supported_actions or []):
            print(" ", m.name)
except Exception as e:
    print("list FAILED:", type(e).__name__, str(e)[:300].replace(key or "x", "***"))