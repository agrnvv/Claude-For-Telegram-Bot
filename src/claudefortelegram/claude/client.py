from anthropic import AsyncAnthropic

from claudefortelegram.config import settings
from claudefortelegram.claude.prompts import build_system_prompt
from claudefortelegram.claude.tools import SAVE_MEMORY_TOOL, handle_save_memory, web_search_tool_for_model
from claudefortelegram.memory import postgres_store
from claudefortelegram.conversation import session

client = AsyncAnthropic(api_key=settings.anthropic_api_key)


async def get_reply(chat_id: int, messages: list[dict]):
    memories = await postgres_store.get_memories(chat_id)
    system_prompt = build_system_prompt(memories)
    model = session.get_model(chat_id)

    conversation = list(messages)  # local copy — tool exchanges stay out of session history

    while True:
        async with client.messages.stream(
            model=model,
            max_tokens=1024,
            system=system_prompt,
            tools=[SAVE_MEMORY_TOOL, web_search_tool_for_model(model)],
            messages=conversation,
        ) as stream:
            async for event in stream:
                if event.type == "content_block_start" and event.content_block.type == "server_tool_use":
                    yield {"type": "status", "text": "🔎 Searching the web…"}
                elif event.type == "content_block_delta" and event.delta.type == "text_delta":
                    yield {"type": "text", "text": event.delta.text}
            response = await stream.get_final_message()

        if response.stop_reason == "tool_use":
            # Claude wants to call a client-side tool — append its turn, run it, feed the result back
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
            continue

        if response.stop_reason == "pause_turn":
            # Server-side tool loop (e.g. web_search) hit its iteration cap mid-turn —
            # resend as-is (no extra "Continue" message) and the API picks up where it left off
            conversation.append({"role": "assistant", "content": response.content})
            continue

        return  # end_turn or anything else — actually done
