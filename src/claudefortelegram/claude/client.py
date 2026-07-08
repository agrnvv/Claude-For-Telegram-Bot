from anthropic import AsyncAnthropic
from claudefortelegram.config import settings
client = AsyncAnthropic(api_key=settings.anthropic_api_key)

#defining the response function
async def get_reply(message: str) -> str:
    response = await client.messages.create(
        model = settings.claude_model,
        max_tokens = 512,
        messages=[
            {"role":"user", "content": message}
        ]
    )
    return response.content[0].text