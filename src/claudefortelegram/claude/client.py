import logging

from anthropic import AsyncAnthropic

from claudefortelegram.config import settings
from claudefortelegram.claude.prompts import build_system_prompt
from claudefortelegram.claude.tools import (
    SAVE_MEMORY_TOOL,
    handle_save_memory,
    web_search_tool_for_model,
    google_docs_tools,
    handle_read_google_doc,
    handle_append_google_doc,
)
from claudefortelegram.google_docs import client as google_docs_client
from claudefortelegram.memory import postgres_store
from claudefortelegram.conversation import session
from claudefortelegram.usage import store as usage_store

logger = logging.getLogger(__name__)

client = AsyncAnthropic(api_key=settings.anthropic_api_key)

# Client-side tool dispatch table: tool name -> async handler(chat_id, tool_input) -> result text.
# Every handler shares this signature even when it doesn't need chat_id (see
# claude/tools.py), so adding a tool here never grows this into an if/elif chain.
TOOL_HANDLERS = {
    "save_memory": handle_save_memory,
    "read_google_doc": handle_read_google_doc,
    "append_to_google_doc": handle_append_google_doc,
}

# Hard ceiling on tool-loop passes within a single reply. Without this, a
# server-side tool loop that keeps returning pause_turn (or any other stuck
# state) resends the whole growing conversation forever — that's what burned
# ~900k input tokens in two days. 5 passes is generous for a personal chat.
MAX_TOOL_ITERATIONS = 5


async def get_reply(chat_id: int, messages: list[dict]):
    memories = await postgres_store.get_memories(chat_id)
    system_prompt = build_system_prompt(memories, google_docs_enabled=google_docs_client.is_configured())
    model = session.get_model(chat_id)

    conversation = list(messages)  # local copy — tool exchanges stay out of session history

    # Mark the end of the incoming history as cacheable. Every extra pass
    # through the loop below (tool_use / pause_turn) resends this same prefix
    # unchanged — with this marker, only the first pass pays full price for
    # it; every later pass in the same reply reads it from cache (~10% cost)
    # instead of paying full input price again.
    #
    # ttl="1h" instead of the 5-minute default: this is a personal assistant
    # used sporadically through the day, not a chat with continuous traffic —
    # gaps between messages regularly exceed 5 minutes, which would silently
    # evict the 5m cache and pay full price on every message. The 1h write
    # costs 2x instead of 1.25x, but breaks even at 3 reads instead of 2 —
    # trivially met across a normal back-and-forth conversation.
    if conversation:
        last = conversation[-1]
        conversation[-1] = {
            **last,
            "content": [{
                "type": "text",
                "text": last["content"],
                "cache_control": {"type": "ephemeral", "ttl": "1h"},
            }],
        }

    # Accumulated across every pass of the loop below — a single user-facing
    # reply can span several API calls (tool_use / pause_turn), and we want
    # one usage_log row for the whole reply, not one per pass.
    total_input_tokens = 0
    total_output_tokens = 0
    total_cache_read_tokens = 0
    total_cache_creation_tokens = 0
    web_search_used = False

    async def _record_usage(iterations: int) -> None:
        logger.info(
            "usage chat_id=%s model=%s input=%d output=%d cache_read=%d cache_creation=%d "
            "iterations=%d web_search=%s",
            chat_id, model, total_input_tokens, total_output_tokens,
            total_cache_read_tokens, total_cache_creation_tokens, iterations, web_search_used,
        )
        await usage_store.record_usage(
            chat_id=chat_id,
            model=model,
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
            cache_read_input_tokens=total_cache_read_tokens,
            cache_creation_input_tokens=total_cache_creation_tokens,
            iterations=iterations,
            web_search_used=web_search_used,
        )

    iterations = 0
    while True:
        iterations += 1
        if iterations > MAX_TOOL_ITERATIONS:
            yield {
                "type": "text",
                "text": "\n\n⚠️ Couldn't finish within a reasonable number of steps — try a simpler or more specific question.",
            }
            await _record_usage(iterations - 1)
            return

        async with client.messages.stream(
            model=model,
            max_tokens=1024,
            system=[{
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral", "ttl": "1h"},
            }],
            tools=[SAVE_MEMORY_TOOL, web_search_tool_for_model(model), *google_docs_tools()],
            messages=conversation,
        ) as stream:
            async for event in stream:
                if event.type == "content_block_start" and event.content_block.type == "server_tool_use":
                    web_search_used = True
                    yield {"type": "status", "text": "🔎 Searching the web…"}
                elif event.type == "content_block_delta" and event.delta.type == "text_delta":
                    yield {"type": "text", "text": event.delta.text}
            response = await stream.get_final_message()

        total_input_tokens += getattr(response.usage, "input_tokens", 0) or 0
        total_output_tokens += getattr(response.usage, "output_tokens", 0) or 0
        total_cache_read_tokens += getattr(response.usage, "cache_read_input_tokens", 0) or 0
        total_cache_creation_tokens += getattr(response.usage, "cache_creation_input_tokens", 0) or 0

        if response.stop_reason == "tool_use":
            # Claude wants to call a client-side tool — append its turn, run it, feed the result back
            conversation.append({"role": "assistant", "content": response.content})

            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                handler = TOOL_HANDLERS.get(block.name)
                if handler is None:
                    continue
                result_text = await handler(chat_id, block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result_text,
                })

            # Mark the end of this pass cacheable too — otherwise only the
            # very first pass's prefix is ever cached, and every later pass
            # re-sends this tool_use/tool_result exchange at full uncached
            # price (up to MAX_TOOL_ITERATIONS times for the same content).
            if tool_results:
                tool_results[-1] = {
                    **tool_results[-1],
                    "cache_control": {"type": "ephemeral", "ttl": "1h"},
                }

            conversation.append({"role": "user", "content": tool_results})
            continue

        if response.stop_reason == "pause_turn":
            # Server-side tool loop (e.g. web_search) hit its iteration cap mid-turn —
            # resend as-is (no extra "Continue" message) and the API picks up where it left off
            conversation.append({"role": "assistant", "content": response.content})
            continue

        await _record_usage(iterations)
        return  # end_turn or anything else — actually done
