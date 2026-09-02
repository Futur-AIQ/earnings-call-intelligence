"""Full-Text Single-Call Chatbot Agent.

Replaces the 2-phase tool-calling architecture with a simpler approach:
the full transcript is stuffed into the system prompt and the LLM answers
directly from it in a single call.

Pre-checks (greeting, thanks, history) are handled without LLM calls.
Empty responses trigger one retry with a simplified prompt.
"""

import json
import logging
import os
import random
import re
import time
from dataclasses import dataclass, field
from typing import Generator, Optional

from langchain_openai import ChatOpenAI

from services.chat_data_loader import generate_data_summary, load_full_transcript

logger = logging.getLogger(__name__)

# ============================================================
# Configuration
# ============================================================
# Independent of the pipeline's .env LLM settings (src/llm/client.py) —
# this chatbot has its own model/context tuning.

LLM_MODEL = os.environ.get("CHAT_LLM_MODEL", "openai/gpt-oss-20b")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
LLM_NUM_CTX = 65536  # informational — context sizing handled by OpenRouter per-model
LLM_TEMPERATURE = 0.1
MAX_HISTORY_TURNS = 5  # Number of conversation turns to include in prompt


# ============================================================
# Pre-check patterns and responses (ported from chat_agent.py)
# ============================================================

GREETING_PATTERNS = [
    re.compile(r"^(hi|hello|hey|howdy|good\s*morning|good\s*afternoon|good\s*evening)\b", re.IGNORECASE),
    re.compile(r"^how\s+are\s+you", re.IGNORECASE),
    re.compile(r"^what\s+can\s+you\s+(do|help)", re.IGNORECASE),
    re.compile(r"^who\s+are\s+you", re.IGNORECASE),
    re.compile(r"^(thanks|thank\s+you|thx)\b", re.IGNORECASE),
    re.compile(r"^help$", re.IGNORECASE),
    re.compile(r"^(ok|okay|cool|great|nice|awesome|got\s+it)\s*[.!]?$", re.IGNORECASE),
    re.compile(r"^(bye|goodbye|see\s+you)\b", re.IGNORECASE),
]

GREETING_RESPONSES = [
    (
        "Hey! I'm here to help you analyze this earnings call transcript.\n\n"
        "You can ask me about:\n"
        "- **Key topics and themes** discussed by analysts\n"
        "- **Specific analyst questions** (e.g., 'What did Nitin Gandhi ask?')\n"
        "- **Management responses** on margins, guidance, or risks\n"
        "- **Session overview** or summary\n\n"
        "What would you like to know?"
    ),
    (
        "Hi there! I can help you explore this earnings call transcript.\n\n"
        "Try asking things like:\n"
        "- \"What were the main concerns raised by analysts?\"\n"
        "- \"Summarize the Q&A session\"\n"
        "- \"What questions did [analyst name] ask?\"\n"
        "- \"Who are the management speakers?\"\n\n"
        "Go ahead!"
    ),
    (
        "Hello! Feel free to ask me about analyst questions, management responses, "
        "key themes, or anything else from this earnings call.\n\n"
        "I have access to the **full transcript** and can answer detailed questions "
        "about financials, guidance, risks, and more."
    ),
    (
        "Hey! I'm ready to dig into this earnings call with you.\n\n"
        "Some ideas to get started:\n"
        "- Ask about **recurring themes** across analyst questions\n"
        "- Look up **what a specific person asked or said**\n"
        "- Get a **high-level summary** of the session\n"
        "- Explore **financial details** like margins, revenue, or guidance"
    ),
]

THANKS_RESPONSES = [
    "You're welcome! Let me know if you have more questions about the transcript.",
    "Happy to help! Feel free to ask anything else about this earnings call.",
    "Glad I could help! I'm here if you need more analysis.",
    "Anytime! If you want to dig deeper into any topic or speaker, just ask.",
    "No problem! There's plenty more to explore in this transcript if you're curious.",
    "You're welcome! I can also help with summaries, specific speakers, or financial details.",
]

HISTORY_PATTERNS = [
    re.compile(r"what\s+(?:did\s+)?I\s+ask", re.IGNORECASE),
    re.compile(r"(?:my|our)\s+(previous|last|earlier)\s+question", re.IGNORECASE),
    re.compile(r"what\s+(?:did\s+)?(?:we|I)\s+(?:discuss|talk)", re.IGNORECASE),
    re.compile(r"(?:previous|last|earlier)\s+(?:question|message|conversation)", re.IGNORECASE),
    re.compile(r"what\s+(?:was|were)\s+(?:my|our)\s+(?:question|message)", re.IGNORECASE),
    re.compile(r"what\s+I\s+(?:said|asked|wrote)\s+(?:before|earlier|previously)", re.IGNORECASE),
    re.compile(r"repeat\s+(?:my|the)\s+(?:last|previous)\s+question", re.IGNORECASE),
]


# ============================================================
# Pre-check helpers
# ============================================================

def _is_greeting(question: str) -> bool:
    q = question.strip()
    return any(p.search(q) for p in GREETING_PATTERNS)


def _is_thanks(question: str) -> bool:
    q = question.strip()
    return bool(re.match(r"^(thanks|thank\s+you|thx)\b", q, re.IGNORECASE))


def _is_history_question(question: str) -> bool:
    q = question.strip()
    return any(p.search(q) for p in HISTORY_PATTERNS)


def _get_greeting_response() -> str:
    return random.choice(GREETING_RESPONSES)


def _get_thanks_response() -> str:
    return random.choice(THANKS_RESPONSES)


def _build_suggested_questions(summary: dict) -> str:
    """Build a friendly nudge when a response is weak or fails."""
    qa_count = summary.get("qa_count", 0)
    parts = []
    if qa_count > 0:
        parts.append(f"analyst Q&A exchanges ({qa_count} available)")
    parts.append("speaker information")
    parts.append("key topics and themes")
    available = ", ".join(parts)
    return (
        f"\n\nI can help you explore this earnings call transcript -- "
        f"including {available}. "
        f"Try asking about a specific topic, analyst, or request a summary!"
    )


def _answer_from_history(question: str, history: list[dict], summary: dict) -> Optional[str]:
    """Answer a meta-question from conversation history."""
    if not history:
        suggestions = _build_suggested_questions(summary)
        return (
            "This is the start of our conversation -- there are no previous messages yet."
            + suggestions
        )

    user_messages = [m for m in history if m.get("role") == "user"]
    if not user_messages:
        return "I don't see any previous questions from you in this conversation."

    recent = user_messages[-5:]
    lines = [f'{i}. "{m["content"]}"' for i, m in enumerate(recent, 1)]

    count_text = f"your last {len(recent)}" if len(recent) < len(user_messages) else "all your"
    return (
        f"Here are {count_text} questions in this conversation:\n\n"
        + "\n".join(lines)
    )


# ============================================================
# Response model
# ============================================================

@dataclass
class ChatResponse:
    """Response from the chat agent."""
    answer: str
    citations: list[dict] = field(default_factory=list)
    tool_calls: list[dict] = field(default_factory=list)
    retrieval_source: str = "none"
    total_time_seconds: float = 0.0
    model: str = LLM_MODEL
    disclaimer: str = ""


# ============================================================
# LLM and prompt helpers
# ============================================================

def _create_llm(streaming: bool = False) -> ChatOpenAI:
    """Create the OpenRouter-backed chat LLM instance."""
    if not OPENROUTER_API_KEY:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set — add it to backend/.env to use the chatbot."
        )
    return ChatOpenAI(
        model=LLM_MODEL,
        api_key=OPENROUTER_API_KEY,
        base_url=OPENROUTER_BASE_URL,
        temperature=LLM_TEMPERATURE,
        max_tokens=4096,
        streaming=streaming,
    )


def _build_prompt(transcript: str, summary: dict, history: list[dict], question: str) -> str:
    """Build the full-text prompt with transcript, history, and question."""
    company = summary.get("company", "Unknown Company")
    ticker = summary.get("ticker", "?")
    quarter = summary.get("quarter", "?")
    year = summary.get("year", "?")

    system = (
        f"You are an earnings call analyst assistant for {company} ({ticker}), {quarter} {year}.\n"
        f"Below is the full transcript of the earnings call. "
        f"Answer the user's question based ONLY on this transcript.\n\n"
        f"RULES:\n"
        f"1. Answer ONLY from the transcript below. Do not use external knowledge.\n"
        f"2. Cite speakers by name and quote relevant passages where possible.\n"
        f"3. If the information is NOT in the transcript, say so clearly -- do not guess or fabricate.\n"
        f"4. Keep answers concise, factual, and well-structured.\n"
        f"5. Use markdown formatting: **bold** for key terms, bullet points for lists.\n"
        f"6. For financial figures, quote exact numbers from the transcript.\n\n"
        f"TRANSCRIPT:\n{transcript}"
    )

    # Append conversation history (last N turns)
    history_str = ""
    if history:
        recent_turns = []
        for msg in history[-(MAX_HISTORY_TURNS * 2):]:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "assistant":
                # Truncate long assistant responses in history to save context
                content = content[:1000]
            recent_turns.append(f"{'User' if role == 'user' else 'Assistant'}: {content}")
        if recent_turns:
            history_str = "\n".join(recent_turns) + "\n"

    return f"{system}\n\n{history_str}User: {question}\nAssistant:"


def _build_retry_prompt(transcript: str, summary: dict, question: str) -> str:
    """Build a simplified retry prompt (no history, force-answer instruction)."""
    company = summary.get("company", "Unknown Company")
    ticker = summary.get("ticker", "?")
    quarter = summary.get("quarter", "?")
    year = summary.get("year", "?")

    return (
        f"You are an earnings call analyst for {company} ({ticker}), {quarter} {year}.\n"
        f"Answer the question below using ONLY the transcript. "
        f"You MUST respond with at least one sentence. "
        f"If you cannot find the answer, say 'I could not find relevant information in the transcript.'\n\n"
        f"TRANSCRIPT:\n{transcript}\n\n"
        f"Question: {question}\nAnswer:"
    )


# ============================================================
# Citation extraction
# ============================================================

def _extract_citations(answer: str, run_data: dict) -> list[dict]:
    """Extract citation references from the answer text.

    Looks for patterns like [qa_000], [page_5], [speaker_002].
    Also handles fullwidth brackets.
    """
    citations = []
    seen = set()

    # Q&A citations: [qa_000] or fullwidth
    qa_pattern = re.compile(r"[\[【]qa_(\d+)[\]】]")
    for match in qa_pattern.finditer(answer):
        qa_id = f"qa_{match.group(1)}"
        if qa_id in seen:
            continue
        seen.add(qa_id)

        label = qa_id
        qa_units = run_data.get("qa", {}).get("qa_units", [])
        for q in qa_units:
            if q["qa_id"] == qa_id:
                questioner = q.get("questioner_name", "Unknown")
                label = f"Q&A #{match.group(1)} ({questioner})"
                break

        citations.append({"type": "qa", "ref_id": qa_id, "label": label})

    # Page citations: [page_5] or fullwidth
    page_pattern = re.compile(r"[\[【]page_(\d+)[\]】]")
    for match in page_pattern.finditer(answer):
        page_ref = f"page_{match.group(1)}"
        if page_ref in seen:
            continue
        seen.add(page_ref)
        citations.append({"type": "page", "ref_id": match.group(1), "label": f"Page {match.group(1)}"})

    # Speaker citations: [speaker_000] or fullwidth
    speaker_pattern = re.compile(r"[\[【]speaker_(\d+)[\]】]")
    for match in speaker_pattern.finditer(answer):
        speaker_id = f"speaker_{match.group(1)}"
        if speaker_id in seen:
            continue
        seen.add(speaker_id)

        label = speaker_id
        speakers = run_data.get("speakers", {}).get("speakers", {})
        if speaker_id in speakers:
            label = speakers[speaker_id].get("canonical_name", speaker_id)

        citations.append({"type": "speaker", "ref_id": speaker_id, "label": label})

    return citations


# ============================================================
# SSE helper
# ============================================================

def _sse_event(event: str, data: dict) -> str:
    """Format a Server-Sent Event string."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


# ============================================================
# Main entry point (non-streaming)
# ============================================================

def chat(question: str, run_data: dict, history: Optional[list[dict]] = None) -> ChatResponse:
    """Process a user question against run data using full-text approach.

    Single LLM call with the full transcript in the prompt.
    Pre-checks handle greetings, thanks, and history questions without LLM.
    """
    start_time = time.time()
    summary = generate_data_summary(run_data)
    run_id = run_data.get("run_id", "unknown")

    # Pre-check: Thanks
    if _is_thanks(question):
        logger.info("Thanks detected")
        return ChatResponse(
            answer=_get_thanks_response(),
            retrieval_source="none",
            total_time_seconds=round(time.time() - start_time, 2),
        )

    # Pre-check: Greeting
    if _is_greeting(question):
        logger.info("Greeting detected")
        return ChatResponse(
            answer=_get_greeting_response(),
            retrieval_source="none",
            total_time_seconds=round(time.time() - start_time, 2),
        )

    # Pre-check: History question
    if _is_history_question(question):
        logger.info("History question detected")
        answer = _answer_from_history(question, history or [], summary)
        return ChatResponse(
            answer=answer,
            retrieval_source="none",
            total_time_seconds=round(time.time() - start_time, 2),
        )

    # Load full transcript
    transcript = load_full_transcript(run_id)
    if not transcript:
        logger.error(f"No transcript found for run {run_id}")
        return ChatResponse(
            answer="No transcript text found for this run. The analysis may be incomplete.",
            retrieval_source="none",
            total_time_seconds=round(time.time() - start_time, 2),
        )

    approx_tokens = len(transcript) // 4
    if approx_tokens > LLM_NUM_CTX * 0.7:
        logger.warning(f"Transcript is large: ~{approx_tokens:,} tokens vs {LLM_NUM_CTX:,} context")

    # Build prompt and call LLM
    llm = _create_llm(streaming=False)
    prompt = _build_prompt(transcript, summary, history or [], question)

    logger.info(f"Full-text query: {question[:100]}")
    try:
        answer = llm.invoke(prompt).content.strip()
    except Exception as e:
        logger.error(f"LLM error: {e}")
        return ChatResponse(
            answer=f"An error occurred while processing your question: {str(e)}",
            retrieval_source="full_text",
            total_time_seconds=round(time.time() - start_time, 2),
        )

    # Empty response retry
    if not answer:
        logger.warning("Empty response, retrying with simplified prompt")
        retry_prompt = _build_retry_prompt(transcript, summary, question)
        try:
            answer = llm.invoke(retry_prompt).content.strip()
        except Exception as e:
            logger.error(f"Retry LLM error: {e}")

    if not answer:
        logger.warning("Still empty after retry")
        suggestions = _build_suggested_questions(summary)
        answer = (
            "I was unable to generate a response for this question. "
            "Please try rephrasing it or asking about a different topic."
            + suggestions
        )

    citations = _extract_citations(answer, run_data)
    total_time = time.time() - start_time
    logger.info(f"Chat completed in {total_time:.1f}s: {len(citations)} citations")

    return ChatResponse(
        answer=answer,
        citations=citations,
        tool_calls=[],
        retrieval_source="full_text",
        total_time_seconds=round(total_time, 2),
        model=LLM_MODEL,
        disclaimer="Answer based on the full earnings call transcript.",
    )


# ============================================================
# Streaming entry point (SSE)
# ============================================================

def chat_stream(question: str, run_data: dict, history: Optional[list[dict]] = None) -> Generator[str, None, None]:
    """Stream a chat response as SSE events.

    Yields SSE-formatted strings:
      event: metadata  -- tool_calls, retrieval_source
      event: token     -- incremental text chunks
      event: done      -- citations, timing, disclaimer
    """
    start_time = time.time()
    summary = generate_data_summary(run_data)
    run_id = run_data.get("run_id", "unknown")

    # --- Thanks ---
    if _is_thanks(question):
        yield _sse_event("metadata", {"tool_calls": [], "retrieval_source": "none"})
        yield _sse_event("token", {"text": _get_thanks_response()})
        yield _sse_event("done", {
            "citations": [],
            "total_time_seconds": round(time.time() - start_time, 2),
            "disclaimer": "",
            "model": LLM_MODEL,
        })
        return

    # --- Greeting ---
    if _is_greeting(question):
        yield _sse_event("metadata", {"tool_calls": [], "retrieval_source": "none"})
        yield _sse_event("token", {"text": _get_greeting_response()})
        yield _sse_event("done", {
            "citations": [],
            "total_time_seconds": round(time.time() - start_time, 2),
            "disclaimer": "",
            "model": LLM_MODEL,
        })
        return

    # --- History question ---
    if _is_history_question(question):
        answer = _answer_from_history(question, history or [], summary)
        yield _sse_event("metadata", {"tool_calls": [], "retrieval_source": "none"})
        yield _sse_event("token", {"text": answer})
        yield _sse_event("done", {
            "citations": [],
            "total_time_seconds": round(time.time() - start_time, 2),
            "disclaimer": "",
            "model": LLM_MODEL,
        })
        return

    # --- Load transcript ---
    transcript = load_full_transcript(run_id)
    if not transcript:
        logger.error(f"No transcript found for run {run_id}")
        yield _sse_event("metadata", {"tool_calls": [], "retrieval_source": "none"})
        yield _sse_event("token", {"text": "No transcript text found for this run. The analysis may be incomplete."})
        yield _sse_event("done", {
            "citations": [],
            "total_time_seconds": round(time.time() - start_time, 2),
            "disclaimer": "",
            "model": LLM_MODEL,
        })
        return

    approx_tokens = len(transcript) // 4
    if approx_tokens > LLM_NUM_CTX * 0.7:
        logger.warning(f"Transcript is large: ~{approx_tokens:,} tokens vs {LLM_NUM_CTX:,} context")

    # --- Build prompt and stream LLM response ---
    yield _sse_event("metadata", {"tool_calls": [], "retrieval_source": "full_text"})

    llm = _create_llm(streaming=True)
    prompt = _build_prompt(transcript, summary, history or [], question)

    logger.info(f"[stream] Full-text query: {question[:100]}")

    full_answer = ""
    try:
        for chunk in llm.stream(prompt):
            text = chunk.content if hasattr(chunk, "content") else str(chunk)
            if text:
                full_answer += text
                yield _sse_event("token", {"text": text})
    except Exception as e:
        logger.error(f"[stream] LLM error: {e}")
        full_answer = f"An error occurred while processing your question: {str(e)}"
        yield _sse_event("token", {"text": full_answer})

    # Empty response retry (non-streaming for retry - simpler and more reliable)
    if not full_answer.strip():
        logger.warning("[stream] Empty response, retrying with simplified prompt")
        retry_prompt = _build_retry_prompt(transcript, summary, question)
        try:
            retry_llm = _create_llm(streaming=False)
            retry_answer = retry_llm.invoke(retry_prompt).content.strip()
            if retry_answer:
                full_answer = retry_answer
                yield _sse_event("token", {"text": retry_answer})
        except Exception as e:
            logger.error(f"[stream] Retry error: {e}")

    if not full_answer.strip():
        suggestions = _build_suggested_questions(summary)
        fallback = (
            "I was unable to generate a response for this question. "
            "Please try rephrasing it or asking about a different topic."
            + suggestions
        )
        full_answer = fallback
        yield _sse_event("token", {"text": fallback})

    # Extract citations and send done event
    citations = _extract_citations(full_answer, run_data)
    total_time = time.time() - start_time
    logger.info(f"[stream] Chat completed in {total_time:.1f}s: {len(citations)} citations")

    yield _sse_event("done", {
        "citations": citations,
        "total_time_seconds": round(total_time, 2),
        "disclaimer": "Answer based on the full earnings call transcript.",
        "model": LLM_MODEL,
    })
