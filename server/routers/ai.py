import httpx
import os
from fastapi import APIRouter, Depends, HTTPException
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel
import json
from typing import List, Dict, Any, AsyncGenerator
from contextlib import contextmanager

from core.jwt_auth import get_current_user
from models.common_model import BaseResponse
from models.users_model import User
from models.applications_model import Application

router = APIRouter(
    prefix="/ai",
    tags=["AI Service"],
    responses={404: {"description": "Not found"}},
)

# --- Pydantic Models ---


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    appid: str
    messages: List[ChatMessage]
    model: str  # This is now effectively a placeholder, the real model is from db


# --- AI Service Endpoint ---

import litellm
from loguru import logger


@contextmanager
def temporary_env_vars(env_vars: Dict[str, str]):
    """Context manager to temporarily set environment variables for a request."""
    original_vars = {key: os.environ.get(key) for key in env_vars}
    os.environ.update(env_vars)
    try:
        yield
    finally:
        for key, value in original_vars.items():
            if value is None:
                if key in os.environ:
                    del os.environ[key]
            else:
                os.environ[key] = value


@router.post("/chat_completions")
async def chat_completions(
    request: ChatCompletionRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Handles chat completion requests by dynamically setting provider credentials
    based on application settings, and then streaming responses from an LLM via LiteLLM.
    """
    app = await Application.find_one(
        Application.app_id == request.appid, Application.users == current_user.username
    )
    if not app:
        raise HTTPException(
            status_code=404, detail="Application not found or permission denied"
        )

    ai_conf = app.ai_config
    if not all([ai_conf.api_key, ai_conf.provider, ai_conf.model]):
        raise HTTPException(
            status_code=400,
            detail="AI service is not fully configured for this application.",
        )

    user_messages = request.messages
    if not user_messages:
        raise HTTPException(status_code=400, detail="Messages list cannot be empty.")

    # Construct the final messages payload (RAG part is omitted for clarity, can be added back)
    final_messages = [msg.model_dump() for msg in user_messages]

    # Prepare environment variables for LiteLLM based on the provider
    # LiteLLM uses convention like OPENAI_API_KEY, ANTHROPIC_API_KEY etc.
    provider_upper = ai_conf.provider.upper().replace("-", "_")
    env_vars_to_set = {
        f"{provider_upper}_API_KEY": ai_conf.api_key,
    }
    # Some providers might need a specific API base URL
    if ai_conf.base_url:
        # Standard LiteLLM convention for custom endpoints
        env_vars_to_set[f"{provider_upper}_BASE_URL"] = ai_conf.base_url
        # Fallback for OpenAI-compatible providers
        env_vars_to_set["OPENAI_API_BASE"] = ai_conf.base_url

    # Set proxy for LiteLLM if configured
    if ai_conf.proxy:
        litellm.proxy = ai_conf.proxy
    else:
        litellm.proxy = None  # Explicitly unset if not provided

    async def stream_generator() -> AsyncGenerator[str, None]:
        """
        Streams the response from LiteLLM within a temporary environment context.
        Includes logging and a [DONE] signal for robustness.
        """
        stream_ended = False
        try:
            with temporary_env_vars(env_vars_to_set):
                # model_identifier = f"{ai_conf.provider}/{ai_conf.model}"
                model_identifier = f"{ai_conf.model}"
                api_base = ai_conf.base_url if ai_conf.base_url else None

                logger.info(
                    f"Initiating LiteLLM stream with model: {model_identifier}, "
                    f"api_base: {api_base}, messages_count: {len(final_messages)}"
                )

                response_stream = await litellm.acompletion(
                    model=model_identifier,
                    messages=final_messages,
                    stream=True,
                    api_base=api_base,
                )

                async for chunk in response_stream:
                    content = chunk.choices[0].delta.content
                    if content:
                        yield json.dumps({"content": content})

        except Exception as e:
            logger.error(f"LiteLLM streaming error: {e}")
            error_message = json.dumps(
                {"error": f"Failed to get response from AI model: {str(e)}"}
            )
            yield error_message
        finally:
            if not stream_ended:
                logger.info("Stream finished. Sending [DONE] signal.")
                yield "[DONE]"
                stream_ended = True

    return EventSourceResponse(stream_generator())
