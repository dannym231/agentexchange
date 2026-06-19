from dotenv import load_dotenv
from anthropic import Anthropic
import os

load_dotenv()

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

response = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=100,
    messages=[{"role": "user", "content": "Say hello in 5 words, you are testing an API connection for AgentMarket"}]
)

print(response.content[0].text)
