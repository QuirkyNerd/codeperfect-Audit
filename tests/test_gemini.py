from utils.gemini_client import generate_with_fallback

response = generate_with_fallback("Say hello in JSON")

print("RAW RESPONSE:")
print(response)