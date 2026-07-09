from anthropic import AsyncAnthropic

from claudefortelegram.config import settings
from claudefortelegram.claude.prompts import build_system_prompt
from claudefortelegram.claude.tools import SAVE_MEMORY_TOOL, handle_save_memory
from claudefortelegram.memory import postgres_store

client = AsyncAnthropic(api_key=settings.anthropic_api_key)


async def get_reply(chat_id: int, messages: list[dict]):
    memories = await postgres_store.get_memories(chat_id)
    system_prompt = build_system_prompt(memories)

    conversation = list(messages)  # local copy — tool exchanges stay out of session history

    while True:
        async with client.messages.stream(
            model=settings.claude_model,
            max_tokens=1024,
            system=system_prompt,
            tools=[SAVE_MEMORY_TOOL],
            messages=conversation,
        ) as stream:
            async for text in stream.text_stream:
                yield text
            response = await stream.get_final_message()

        if response.stop_reason != "tool_use":
            return  # done — an async generator ends with a bare `return`, no value

        # Claude wants to call a tool — append its turn, run the tool, feed the result back
        conversation.append({"role": "assistant", "content": response.content})

        tool_results = []
        for block in response.content:
            if block.type == "tool_use" and block.name == "save_memory":
                result_text = await handle_save_memory(chat_id, block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result_text,
                })

        conversation.append({"role": "user", "content": tool_results})
