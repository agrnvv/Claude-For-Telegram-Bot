from anthropic import AsyncAnthropic
from claudefortelegram.config import settings
from claudefortelegram.claude.prompts import SYSTEM_PROMPT
client = AsyncAnthropic(api_key=settings.anthropic_api_key)

#defining the response function
async def get_reply(messages: list[dict]) -> str:
    response = await client.messages.create(
        model = settings.claude_model,
        max_tokens = 512,
        system = SYSTEM_PROMPT,
        messages=messages,
    )
    for block in response.content:
        if block.type == "text":
            return block.text
    return ""