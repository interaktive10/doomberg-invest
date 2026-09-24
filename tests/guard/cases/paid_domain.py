import httpx

URL = "https://api.openai.com/v1/chat/completions"  # seeded violation: paid runtime domain
httpx.post(URL, json={})
