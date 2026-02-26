"""LLM Service - Unified interface for Ollama, vLLM, MiniMax, and OpenRouter.

All LLM providers expose an OpenAI-compatible API, so we use the OpenAI
client for all of them. The provider is selected via configuration.

Fallback chain: primary LLM (Ollama/vLLM) -> OpenRouter (minimax/minimax-m2.5)
"""

import json
import logging
from typing import Any, Optional

from openai import AsyncOpenAI
from pydantic import BaseModel

from champiq_v2.utils.json_utils import extract_json_object

from champiq_v2.config import get_settings

logger = logging.getLogger(__name__)

import re

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# MiniMax M2.5 is a reasoning model -- it uses `reasoning` tokens before producing
# `content`. We need extra tokens so reasoning doesn't consume the entire budget.
REASONING_MODEL_MIN_TOKENS = 8192


class LLMResponse(BaseModel):
    """Structured response from LLM."""

    content: str
    usage: dict[str, int] = {}
    model: str = ""
    finish_reason: str = ""


def _extract_content(message) -> str:
    """Extract text from an LLM response message.

    MiniMax M2.5 is a reasoning model: it puts chain-of-thought in the
    ``reasoning`` attribute and the final answer in ``content``.  When
    ``content`` is empty (e.g. ran out of tokens before finishing
    reasoning), fall back to ``reasoning`` so callers always get text.
    """
    content = message.content or ""
    if content:
        return content
    # Fallback: reasoning field (MiniMax M2.5 specific)
    reasoning = getattr(message, "reasoning", None) or ""
    if reasoning:
        logger.debug("Using reasoning field as content (reasoning model)")
        return reasoning
    return ""


class LLMService:
    """Unified LLM service supporting Ollama, vLLM, MiniMax, and OpenRouter.

    All providers are accessed via OpenAI-compatible API endpoints.
    Falls back to OpenRouter (minimax-m2.5) if the primary LLM is unreachable.
    """

    def __init__(self):
        self.settings = get_settings()
        self._client: Optional[AsyncOpenAI] = None
        self._fallback_client: Optional[AsyncOpenAI] = None
        self._model_override: Optional[str] = None
        self._initialize_client()

    def _initialize_client(self) -> None:
        """Initialize the primary and fallback OpenAI-compatible clients."""
        api_key = self.settings.llm_api_key.get_secret_value()

        # For Ollama, API key can be empty or "ollama"
        if self.settings.llm_provider == "ollama" and not api_key:
            api_key = "ollama"

        self._client = AsyncOpenAI(
            base_url=self.settings.llm_base_url,
            api_key=api_key,
            timeout=self.settings.llm_timeout,
        )
        logger.info(
            "Initialized LLM client: provider=%s, model=%s, base_url=%s",
            self.settings.llm_provider,
            self.settings.llm_model,
            self.settings.llm_base_url,
        )

        # OpenRouter fallback client
        or_key = self.settings.openrouter_api_key.get_secret_value()
        if or_key:
            self._fallback_client = AsyncOpenAI(
                base_url=OPENROUTER_BASE_URL,
                api_key=or_key,
                timeout=60,
                default_headers={
                    "HTTP-Referer": "https://champiq.lakeb2b.com",
                    "X-Title": "ChampIQ",
                },
            )
            logger.info(
                "OpenRouter fallback enabled: model=%s",
                self.settings.openrouter_model,
            )
        else:
            logger.warning("No OPENROUTER_API_KEY set -- fallback disabled")

    async def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        format: Optional[str] = None,  # "json" for JSON mode
    ) -> str:
        """Generate a completion from the LLM.

        Tries the primary LLM first; falls back to OpenRouter (minimax-m2.5)
        if the primary raises any exception (connection error, timeout, etc.).

        Args:
            prompt: The user prompt
            system_prompt: Optional system prompt for context
            temperature: Override default temperature
            max_tokens: Override default max tokens
            format: "json" to request JSON output

        Returns:
            The generated text content
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        kwargs: dict[str, Any] = {
            "messages": messages,
            "temperature": temperature or self.settings.llm_temperature,
            "max_tokens": max_tokens or self.settings.llm_max_tokens,
        }
        if format == "json":
            kwargs["response_format"] = {"type": "json_object"}

        # Determine which model to use (override takes priority)
        model_to_use = self._model_override or self.settings.llm_model

        # -- Primary LLM -------------------------------------------------------
        try:
            response = await self._client.chat.completions.create(
                model=model_to_use, **kwargs
            )
            content = _extract_content(response.choices[0].message)
            logger.debug(
                "LLM completion (primary): tokens=%d, finish_reason=%s",
                response.usage.total_tokens if response.usage else 0,
                response.choices[0].finish_reason,
            )
            return content

        except Exception as primary_err:
            logger.warning(
                "Primary LLM (%s) failed: %s -- trying OpenRouter fallback",
                model_to_use,
                primary_err,
            )

        # -- OpenRouter fallback -----------------------------------------------
        if not self._fallback_client:
            raise RuntimeError(
                f"Primary LLM unreachable and no OpenRouter fallback configured. "
                f"Set OPENROUTER_API_KEY in .env."
            )

        # MiniMax M2.5 is a reasoning model -- it needs extra tokens for
        # chain-of-thought before producing the actual content.
        fallback_kwargs = dict(kwargs)
        requested_tokens = fallback_kwargs.get("max_tokens", 0) or 0
        if requested_tokens < REASONING_MODEL_MIN_TOKENS:
            fallback_kwargs["max_tokens"] = REASONING_MODEL_MIN_TOKENS

        response = await self._fallback_client.chat.completions.create(
            model=self.settings.openrouter_model, **fallback_kwargs
        )
        content = _extract_content(response.choices[0].message)
        logger.info(
            "LLM completion (OpenRouter fallback %s): tokens=%d",
            self.settings.openrouter_model,
            response.usage.total_tokens if response.usage else 0,
        )
        return content

    async def complete_structured(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> LLMResponse:
        """Generate a completion and return structured response."""
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})

        response = await self._client.chat.completions.create(
            model=self._model_override or self.settings.llm_model,
            messages=messages,
            temperature=temperature or self.settings.llm_temperature,
            max_tokens=self.settings.llm_max_tokens,
        )

        return LLMResponse(
            content=response.choices[0].message.content,
            usage={
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                "total_tokens": response.usage.total_tokens if response.usage else 0,
            },
            model=response.model,
            finish_reason=response.choices[0].finish_reason,
        )

    async def complete_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> dict[str, Any]:
        """Generate a completion and parse as JSON.

        The prompt should instruct the model to output valid JSON.
        """
        content = await self.complete(
            prompt=prompt,
            system_prompt=system_prompt,
            format="json",
        )

        # Try to parse JSON, handling potential markdown code blocks
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        try:
            result = json.loads(content)
            if result is None:
                raise ValueError("LLM returned null JSON")
            return result
        except json.JSONDecodeError as e:
            logger.error("Failed to parse LLM JSON response: %s", e)
            logger.debug("Raw content: %s", content[:500])
            raise ValueError(f"LLM returned invalid JSON: {e}") from e

    # ==================== V2: Model Override Methods ====================

    async def complete_with_model(
        self,
        model: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Generate completion using a specific model (frontend-selectable)."""
        old_override = self._model_override
        self._model_override = model
        try:
            return await self.complete(prompt, system_prompt, temperature, max_tokens)
        finally:
            self._model_override = old_override

    # ==================== V2: Transcript Summarization ====================

    async def summarize_transcript(self, transcript: str, call_type: str) -> str:
        """Summarize a call transcript into a concise paragraph."""
        prompt = f"""Summarize this {call_type} call transcript in 2-3 sentences.
Focus on the key points discussed, the prospect's level of interest,
and any next steps or action items mentioned.

Transcript: {transcript}"""
        return await self.complete(prompt, max_tokens=300, temperature=0.3)

    # ==================== V2: Email with Availability CTA ====================

    async def generate_email_with_availability(
        self,
        context: dict[str, Any],
        variant: str = "primary",
        tone: str = "consultative",
    ) -> dict[str, str]:
        """Generate email with availability CTA appended."""
        result = await self.generate_email(context, variant, tone=tone)
        cta = "\n\nWould any of these times work for a quick 15-minute call? I'm flexible and happy to adjust."
        result["body"] = result.get("body", "") + cta
        return result

    # ==================== Research Methods ====================

    async def research(
        self,
        query: str,
        system_prompt: Optional[str] = None,
    ) -> str:
        """Run a web research query via Perplexity Sonar on OpenRouter.

        Perplexity Sonar is a search-augmented LLM -- it retrieves live web
        results and synthesises them into a coherent answer.  We route it
        through the existing OpenRouter client so no additional API key is
        needed.

        Falls back to the standard ``complete()`` method (which itself
        falls back to OpenRouter minimax) if no OpenRouter key is set.

        NOTE: Perplexity Sonar does NOT support ``response_format``.
        JSON output is enforced via prompt instructions instead.
        """
        if not self._fallback_client:
            logger.warning(
                "No OpenRouter key -- falling back to standard complete() for research"
            )
            return await self.complete(query, system_prompt=system_prompt)

        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": query})

        kwargs: dict[str, Any] = {
            "messages": messages,
            "temperature": 0.1,        # low temp for factual research
            "max_tokens": 4096,
        }
        # Do NOT set response_format -- Perplexity rejects it.

        model = self.settings.perplexity_model  # e.g. "perplexity/sonar"

        try:
            response = await self._fallback_client.chat.completions.create(
                model=model, **kwargs
            )
            content = _extract_content(response.choices[0].message)
            logger.info(
                "Perplexity Sonar research: tokens=%d, model=%s",
                response.usage.total_tokens if response.usage else 0,
                model,
            )
            return content
        except Exception as e:
            logger.warning("Perplexity Sonar failed (%s), falling back to complete()", e)
            return await self.complete(query, system_prompt=system_prompt)

    async def research_json(
        self,
        query: str,
        system_prompt: Optional[str] = None,
    ) -> dict[str, Any]:
        """Run a web research query and parse the result as JSON.

        Perplexity Sonar often wraps JSON in markdown code fences or
        appends citation text after the JSON block.  This method
        extracts the first valid JSON object from the response.
        """
        content = await self.research(query, system_prompt=system_prompt)
        return self._extract_json(content, source="Perplexity")

    @staticmethod
    def _extract_json(text: str, source: str = "LLM") -> dict[str, Any]:
        """Robustly extract the first JSON object from LLM output.

        Delegates to champiq_v2.utils.json_utils.extract_json_object.
        """
        return extract_json_object(text, source=source)

    # ==================== Analysis Methods ====================

    async def analyze_sentiment(self, text: str) -> float:
        """Analyze sentiment of text.

        Returns a score from -1 (negative) to 1 (positive).
        """
        system_prompt = """You are a sentiment analysis expert. Analyze the sentiment of the given text and return a JSON object with a single "score" field containing a number from -1.0 (very negative) to 1.0 (very positive). 0 is neutral."""

        prompt = f"""Analyze the sentiment of this text:

"{text}"

Return JSON with format: {{"score": <number>}}"""

        result = await self.complete_json(prompt, system_prompt)
        return float(result.get("score", 0))

    async def extract_entities(
        self, text: str, entity_types: list[str]
    ) -> dict[str, list[str]]:
        """Extract named entities from text.

        Args:
            text: Text to analyze
            entity_types: Types to extract (e.g., ["company", "person", "pain_point"])

        Returns:
            Dict mapping entity types to lists of extracted values
        """
        system_prompt = """You are an expert entity extraction system. Extract the requested entity types from the given text and return them as a JSON object."""

        prompt = f"""Extract the following entity types from this text:
Entity types: {', '.join(entity_types)}

Text:
"{text}"

Return JSON with format: {{"entity_type": ["value1", "value2", ...], ...}}
Include only entity types that have values found in the text."""

        return await self.complete_json(prompt, system_prompt)

    async def classify_intent(
        self, text: str, categories: list[str]
    ) -> tuple[str, float]:
        """Classify the intent of text into one of the given categories.

        Returns the category and confidence score.
        """
        system_prompt = """You are an intent classification expert. Classify the given text into exactly one of the provided categories."""

        prompt = f"""Classify this text into one of these categories: {', '.join(categories)}

Text:
"{text}"

Return JSON with format: {{"category": "<category>", "confidence": <0.0-1.0>}}"""

        result = await self.complete_json(prompt, system_prompt)
        return result.get("category", categories[0]), float(result.get("confidence", 0.5))

    async def generate_email(
        self,
        prospect_context: dict[str, Any],
        variant: str = "primary",
        tone: str = "consultative",
    ) -> dict[str, str]:
        """Generate a personalized email for a prospect.

        Args:
            prospect_context: Context dict with prospect, company, pain_points
            variant: "primary", "secondary", or "nurture"
            tone: "consultative", "direct", or "friendly"

        Returns:
            Dict with "subject" and "body" keys
        """
        system_prompt = f"""You are an expert B2B sales copywriter. You write {tone}, value-focused emails that help prospects solve their business challenges.

Your emails:
- Lead with insights and value, not product pitches
- Reference specific research about their company
- Frame recommendations in terms of ROI and outcomes
- Use phrases like "Based on my research..." or "Companies like yours often..."
- Keep CTAs low-friction (quick question, share thoughts)

NEVER:
- Sound salesy or pushy
- Use "just checking in" or "circling back"
- Lead with product features
- Use aggressive CTAs (book a demo, schedule a call)"""

        variant_instructions = {
            "primary": "Focus on their top pain point with a direct solution recommendation.",
            "secondary": "Take an alternative angle, perhaps addressing a secondary concern or different stakeholder perspective.",
            "nurture": "Share thought leadership content, industry insights, or helpful resources without any direct pitch.",
        }

        prospect = prospect_context.get("prospect") or {}
        company = prospect_context.get("company") or {}
        pain_points = prospect_context.get("pain_points") or []
        campaign_context = prospect_context.get("campaign_context") or ""

        prompt = f"""Generate a {variant} email for:

Prospect: {prospect.get('name', 'Unknown')}, {prospect.get('title', 'Unknown')} at {company.get('name', 'Unknown Company')}
Industry: {company.get('industry', 'Unknown')}
Company Size: {company.get('employee_count_range', 'Unknown')}

Pain Points:
{json.dumps(pain_points, indent=2) if pain_points else 'None identified yet'}

Recent Company News:
{json.dumps(company.get('recent_news', []), indent=2) if company.get('recent_news') else 'None available'}
{f'''
Campaign Context / Goal (IMPORTANT -- use this to guide tone, angle, and CTA):
{campaign_context}
''' if campaign_context else ''}
Variant Instructions: {variant_instructions.get(variant, variant_instructions['primary'])}

Return JSON with format:
{{
    "subject": "Personalized, curiosity-inducing subject line (max 60 chars)",
    "body": "Full email body with personalized opening, value proposition, and soft CTA"
}}"""

        return await self.complete_json(prompt, system_prompt)


# Singleton instance
_llm_service: Optional[LLMService] = None


def get_llm_service() -> LLMService:
    """Get the LLM service singleton."""
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service
