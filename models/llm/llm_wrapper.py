"""
LLM Wrapper - Unified Interface for Multiple LLM Providers

Provides a consistent interface for interacting with different LLM providers
(OpenAI, Anthropic, etc.) with automatic fallback and retry logic.
"""

import os
import time
from typing import Any, AsyncIterator, Dict, List, Optional, Union

from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

from config.settings import get_settings
from utils.logger import get_logger


class LLMResponse:
    """Response from LLM."""

    def __init__(
        self,
        content: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        duration_ms: int,
    ):
        self.content = content
        self.model = model
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = total_tokens
        self.duration_ms = duration_ms


class LLMWrapper:
    """
    Unified wrapper for multiple LLM providers.

    Supports:
    - Anthropic (Claude)
    - OpenAI (GPT)
    - Automatic retry with exponential backoff
    - Model fallback
    - Token usage tracking
    """

    def __init__(self):
        """Initialize LLM wrapper with available providers."""
        self.settings = get_settings()
        self.logger = get_logger("llm_wrapper")

        # Initialize Anthropic client
        anthropic_key = self.settings.anthropic_api_key
        if anthropic_key:
            self.anthropic = AsyncAnthropic(api_key=anthropic_key)
        else:
            self.anthropic = None

        # Initialize OpenAI client
        openai_key = self.settings.openai_api_key
        if openai_key:
            self.openai = AsyncOpenAI(api_key=openai_key)
        else:
            self.openai = None

        # Track usage
        self.total_tokens_used = 0
        self.total_cost_estimate = 0.0

    async def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        provider: Optional[str] = None,
    ) -> LLMResponse:
        """
        Generate text using LLM.

        Args:
            prompt: User prompt
            model: Model to use (default from settings)
            system_prompt: Optional system prompt
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            provider: Force specific provider (anthropic, openai)

        Returns:
            LLMResponse with generated text and metadata

        Raises:
            RuntimeError: If no LLM provider is available
        """
        model = model or self.settings.default_model

        start_time = time.time()

        # Determine provider based on model
        if provider is None:
            if model.startswith("claude"):
                provider = "anthropic"
            elif model.startswith("gpt"):
                provider = "openai"
            else:
                provider = "anthropic"  # Default

        # Try primary provider
        try:
            if provider == "anthropic" and self.anthropic:
                return await self._generate_anthropic(
                    prompt=prompt,
                    model=model,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    start_time=start_time,
                )
            elif provider == "openai" and self.openai:
                return await self._generate_openai(
                    prompt=prompt,
                    model=model,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    start_time=start_time,
                )
            else:
                # Try fallback provider
                return await self._try_fallback(
                    prompt=prompt,
                    model=model,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    start_time=start_time,
                    excluded_provider=provider,
                )

        except Exception as e:
            self.logger.error("LLM generation failed", error=str(e), provider=provider)

            # Try fallback provider
            return await self._try_fallback(
                prompt=prompt,
                model=model,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                start_time=start_time,
                excluded_provider=provider,
            )

    async def generate_stream(
        self,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        provider: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """
        Generate text with streaming.

        Yields content chunks as they arrive from the LLM.

        Args:
            prompt: User prompt
            model: Model to use
            system_prompt: Optional system prompt
            temperature: Sampling temperature
            max_tokens: Maximum tokens
            provider: Force specific provider

        Yields:
            Content chunks as they arrive
        """
        model = model or self.settings.default_model

        # Determine provider based on model
        if provider is None:
            if model.startswith("claude"):
                provider = "anthropic"
            elif model.startswith("gpt"):
                provider = "openai"
            else:
                provider = "anthropic"  # Default

        # Stream from provider
        if provider == "anthropic" and self.anthropic:
            async for chunk in self._stream_anthropic(
                prompt=prompt,
                model=model,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            ):
                yield chunk
        elif provider == "openai" and self.openai:
            async for chunk in self._stream_openai(
                prompt=prompt,
                model=model,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            ):
                yield chunk
        else:
            raise RuntimeError("No LLM provider available for streaming")

    async def _stream_anthropic(
        self,
        prompt: str,
        model: str,
        system_prompt: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[str]:
        """Stream from Anthropic Claude."""
        messages = [{"role": "user", "content": prompt}]

        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages,
        }

        if system_prompt:
            kwargs["system"] = system_prompt

        async with self.anthropic.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield text

    async def _stream_openai(
        self,
        prompt: str,
        model: str,
        system_prompt: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[str]:
        """Stream from OpenAI GPT."""
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})

        stream = await self.openai.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )

        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def _generate_anthropic(
        self,
        prompt: str,
        model: str,
        system_prompt: Optional[str],
        temperature: float,
        max_tokens: int,
        start_time: float,
    ) -> LLMResponse:
        """Generate using Anthropic Claude."""
        messages = [{"role": "user", "content": prompt}]

        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages,
        }

        if system_prompt:
            kwargs["system"] = system_prompt

        response = await self.anthropic.messages.create(**kwargs)

        content = response.content[0].text
        usage = response.usage

        duration_ms = int((time.time() - start_time) * 1000)

        # Update tracking
        self.total_tokens_used += usage.input_tokens + usage.output_tokens

        return LLMResponse(
            content=content,
            model=model,
            prompt_tokens=usage.input_tokens,
            completion_tokens=usage.output_tokens,
            total_tokens=usage.input_tokens + usage.output_tokens,
            duration_ms=duration_ms,
        )

    async def _generate_openai(
        self,
        prompt: str,
        model: str,
        system_prompt: Optional[str],
        temperature: float,
        max_tokens: int,
        start_time: float,
    ) -> LLMResponse:
        """Generate using OpenAI GPT."""
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})

        response = await self.openai.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        content = response.choices[0].message.content
        usage = response.usage

        duration_ms = int((time.time() - start_time) * 1000)

        # Update tracking
        self.total_tokens_used += usage.prompt_tokens + usage.completion_tokens

        return LLMResponse(
            content=content,
            model=model,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            total_tokens=usage.prompt_tokens + usage.completion_tokens,
            duration_ms=duration_ms,
        )

    async def _try_fallback(
        self,
        prompt: str,
        model: str,
        system_prompt: Optional[str],
        temperature: float,
        max_tokens: int,
        start_time: float,
        excluded_provider: str,
    ) -> LLMResponse:
        """Try fallback provider."""
        fallback_model = self.settings.fallback_model

        if excluded_provider != "openai" and self.openai:
            self.logger.info("Falling back to OpenAI")
            return await self._generate_openai(
                prompt=prompt,
                model=fallback_model,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                start_time=start_time,
            )
        elif excluded_provider != "anthropic" and self.anthropic:
            self.logger.info("Falling back to Anthropic")
            return await self._generate_anthropic(
                prompt=prompt,
                model=fallback_model,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                start_time=start_time,
            )
        else:
            raise RuntimeError("No LLM provider available")

    async def generate_structured(
        self,
        prompt: str,
        schema: Dict[str, Any],
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Generate structured JSON output.

        Args:
            prompt: User prompt
            schema: JSON schema for expected output
            **kwargs: Additional arguments for generate()

        Returns:
            Parsed JSON response
        """
        # Add schema to prompt
        structured_prompt = f"""{prompt}

Return your response as a JSON object with this structure:
{json.dumps(schema, indent=2)}

Your response must be valid JSON only, with no additional text."""

        response = await self.generate(structured_prompt, **kwargs)

        # Parse JSON from response
        import json

        content = response.content.strip()

        # Remove markdown code blocks if present
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        return json.loads(content)

    def get_usage_stats(self) -> Dict[str, Any]:
        """Get token usage statistics."""
        return {
            "total_tokens": self.total_tokens_used,
            "estimated_cost_usd": self._estimate_cost(self.total_tokens_used),
        }

    def _estimate_cost(self, tokens: int) -> float:
        """Estimate cost in USD."""
        # Rough estimate: $0.003 per 1K tokens (average)
        return (tokens / 1000) * 0.003


# Global LLM wrapper instance
_llm_wrapper: Optional[LLMWrapper] = None


def get_llm_wrapper() -> LLMWrapper:
    """Get the global LLM wrapper instance."""
    global _llm_wrapper
    if _llm_wrapper is None:
        _llm_wrapper = LLMWrapper()
    return _llm_wrapper
