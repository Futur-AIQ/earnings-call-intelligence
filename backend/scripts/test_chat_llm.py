"""
Phase 0: LLM Validation Script for Chatbot Agent

Tests gpt-oss:20b (or any Ollama model) for tool calling capability,
response quality, and timing. Tests both native ChatOllama tool calling
and prompt-based tool calling approaches.

Usage:
    cd backend
    python scripts/test_chat_llm.py [--run-id RUN_ID] [--model MODEL_NAME] [--num-ctx NUM_CTX]

Requirements:
    pip install langchain-ollama langchain-core
"""

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ============================================================
# Data Loading
# ============================================================

def load_run_data(run_id: str) -> dict:
    """Load all run data into memory."""
    runs_dir = Path(__file__).resolve().parent.parent / "data" / "runs"
    run_dir = runs_dir / run_id

    if not run_dir.exists():
        # Try partial match
        matches = [d for d in runs_dir.iterdir() if d.name.startswith(run_id)]
        if matches:
            run_dir = matches[0]
            run_id = run_dir.name
        else:
            raise FileNotFoundError(f"Run not found: {run_id}")

    data = {"run_id": run_id}
    file_map = {
        "metadata": "metadata.json",
        "meta": "stage_metadata_result.json",
        "speakers": "stage_speakers_result.json",
        "qa": "stage_qa_result.json",
        "strategic": "stage_strategic_result.json",
        "extraction": "stage_extraction_result.json",
    }

    for key, filename in file_map.items():
        filepath = run_dir / filename
        if filepath.exists():
            with open(filepath, "r", encoding="utf-8") as f:
                data[key] = json.load(f)
        else:
            data[key] = {}

    return data


def generate_data_summary(data: dict) -> str:
    """Generate a human-readable summary of the run data for the system prompt."""
    meta = data.get("meta", {})
    speakers_data = data.get("speakers", {})
    qa_data = data.get("qa", {})
    strategic_data = data.get("strategic", {})

    speakers = speakers_data.get("speakers", {})
    management = [s["canonical_name"] for s in speakers.values() if s.get("role") == "management"]
    analysts = [s["canonical_name"] for s in speakers.values() if s.get("role") == "analyst"]

    qa_units = qa_data.get("qa_units", [])
    follow_ups = [q for q in qa_units if q.get("is_follow_up")]

    # Extract common keywords from Q&A text for topic hints
    all_text = " ".join(q.get("question_text", "") + " " + q.get("response_text", "") for q in qa_units).lower()

    summary = f"""Company: {meta.get('company_name', 'Unknown')} ({meta.get('ticker_symbol', '?')})
Call: {meta.get('fiscal_quarter', '?')} {meta.get('fiscal_year', '?')}, Date: {meta.get('call_date', '?')}
Speakers: {len(speakers)} total
  Management: {', '.join(management) if management else 'None identified'}
  Analysts: {', '.join(analysts) if analysts else 'None identified'}
Q&A Units: {len(qa_units)} total, {len(follow_ups)} follow-ups
Strategic Statements: {strategic_data.get('total_statements', 0)}
Pages: {data.get('metadata', {}).get('page_count', '?')}"""

    return summary


# ============================================================
# Tool Definitions (for native tool calling test)
# ============================================================

TOOL_DEFINITIONS = [
    {
        "name": "get_run_metadata",
        "description": "Get basic information about this earnings call: company name, ticker, quarter, year, date, and counts of speakers/Q&As.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "search_speakers",
        "description": "Search for speakers in this earnings call by role (management/analyst/moderator) or name.",
        "parameters": {
            "type": "object",
            "properties": {
                "role": {"type": "string", "enum": ["management", "analyst", "moderator", "unknown"], "description": "Filter by speaker role"},
                "name_query": {"type": "string", "description": "Search by name (case-insensitive substring match)"},
                "company": {"type": "string", "description": "Search by company (case-insensitive substring match)"}
            },
            "required": []
        }
    },
    {
        "name": "search_qa_units",
        "description": "Search Q&A exchanges from the earnings call by speaker name, keyword in text, or follow-up status.",
        "parameters": {
            "type": "object",
            "properties": {
                "questioner_name": {"type": "string", "description": "Filter by questioner name (substring match)"},
                "responder_name": {"type": "string", "description": "Filter by responder name (substring match)"},
                "keyword": {"type": "string", "description": "Search keyword in question and response text (case-insensitive)"},
                "is_follow_up": {"type": "boolean", "description": "Filter for follow-up questions only"},
                "limit": {"type": "integer", "description": "Max results to return (default 5)", "default": 5}
            },
            "required": []
        }
    },
    {
        "name": "get_qa_detail",
        "description": "Get full details of a specific Q&A exchange by its ID (e.g., 'qa_001'). Use after search_qa_units to get complete text.",
        "parameters": {
            "type": "object",
            "properties": {
                "qa_id": {"type": "string", "description": "The Q&A unit ID (e.g., 'qa_000', 'qa_001')"}
            },
            "required": ["qa_id"]
        }
    },
    {
        "name": "get_follow_up_chain",
        "description": "Get the full chain of follow-up Q&A exchanges starting from a given Q&A ID. Returns the original question and all follow-ups in order.",
        "parameters": {
            "type": "object",
            "properties": {
                "qa_id": {"type": "string", "description": "Starting Q&A ID to trace the follow-up chain from"}
            },
            "required": ["qa_id"]
        }
    },
    {
        "name": "search_full_text",
        "description": "Search the raw transcript text for a keyword. Returns matching excerpts with page numbers. Use when structured search returns no results.",
        "parameters": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "Keyword to search for in raw transcript text"},
                "context_chars": {"type": "integer", "description": "Characters of context around match (default 300)", "default": 300}
            },
            "required": ["keyword"]
        }
    },
    {
        "name": "search_strategic_statements",
        "description": "Search strategic statements (guidance, outlook, initiatives) from the earnings call.",
        "parameters": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "Search keyword in statement text"},
                "statement_type": {"type": "string", "enum": ["guidance", "outlook", "strategic_initiative", "operational_update", "financial_highlight", "risk_disclosure"]},
                "is_forward_looking": {"type": "boolean", "description": "Filter for forward-looking statements"},
                "speaker_name": {"type": "string", "description": "Filter by speaker name"}
            },
            "required": []
        }
    },
    {
        "name": "get_raw_text_page",
        "description": "Get the raw transcript text for a specific page number.",
        "parameters": {
            "type": "object",
            "properties": {
                "page_number": {"type": "integer", "description": "Page number (1-based)"}
            },
            "required": ["page_number"]
        }
    }
]


# ============================================================
# Tool Execution (simulate real tool behavior)
# ============================================================

def execute_tool(tool_name: str, args: dict, run_data: dict) -> str:
    """Execute a tool against run data and return the result as a string."""

    if tool_name == "get_run_metadata":
        meta = run_data.get("meta", {})
        metadata = run_data.get("metadata", {})
        qa = run_data.get("qa", {})
        speakers = run_data.get("speakers", {})
        return json.dumps({
            "company_name": meta.get("company_name"),
            "ticker_symbol": meta.get("ticker_symbol"),
            "fiscal_quarter": meta.get("fiscal_quarter"),
            "fiscal_year": meta.get("fiscal_year"),
            "call_date": meta.get("call_date"),
            "speaker_count": len(speakers.get("speakers", {})),
            "qa_count": len(qa.get("qa_units", [])),
            "page_count": metadata.get("page_count", "?"),
        }, indent=2)

    elif tool_name == "search_speakers":
        speakers = run_data.get("speakers", {}).get("speakers", {})
        results = []
        for s in speakers.values():
            if args.get("role") and s.get("role") != args["role"]:
                continue
            if args.get("name_query"):
                q = args["name_query"].lower()
                name_match = q in s.get("canonical_name", "").lower()
                alias_match = any(q in a.lower() for a in s.get("aliases", []))
                if not name_match and not alias_match:
                    continue
            if args.get("company"):
                if not s.get("company") or args["company"].lower() not in s["company"].lower():
                    continue
            results.append({
                "speaker_id": s["speaker_id"],
                "canonical_name": s["canonical_name"],
                "role": s.get("role"),
                "title": s.get("title"),
                "company": s.get("company"),
                "turn_count": s.get("turn_count"),
            })
        return json.dumps({"results": results[:20], "total": len(results)}, indent=2)

    elif tool_name == "search_qa_units":
        qa_units = run_data.get("qa", {}).get("qa_units", [])
        results = []
        for q in qa_units:
            if args.get("questioner_name"):
                if args["questioner_name"].lower() not in q.get("questioner_name", "").lower():
                    continue
            if args.get("responder_name"):
                if not any(args["responder_name"].lower() in r.lower() for r in q.get("responder_names", [])):
                    continue
            if args.get("keyword"):
                kw = args["keyword"].lower()
                text = (q.get("question_text", "") + " " + q.get("response_text", "")).lower()
                if kw not in text:
                    continue
            if args.get("is_follow_up") is not None:
                if q.get("is_follow_up") != args["is_follow_up"]:
                    continue

            limit = args.get("limit", 5)
            # Adaptive truncation
            budget = 3000
            chars_per = budget // max(limit, 1)

            results.append({
                "qa_id": q["qa_id"],
                "questioner_name": q.get("questioner_name"),
                "responder_names": q.get("responder_names", []),
                "question_text": q.get("question_text", "")[:chars_per],
                "response_text": q.get("response_text", "")[:chars_per],
                "is_follow_up": q.get("is_follow_up"),
                "follow_up_of": q.get("follow_up_of"),
                "start_page": q.get("start_page"),
                "end_page": q.get("end_page"),
            })
            if len(results) >= limit:
                break

        return json.dumps({"results": results, "total_matching": len(results)}, indent=2)

    elif tool_name == "get_qa_detail":
        qa_units = run_data.get("qa", {}).get("qa_units", [])
        qa_id = args.get("qa_id", "")
        for q in qa_units:
            if q["qa_id"] == qa_id:
                return json.dumps(q, indent=2)
        return json.dumps({"error": f"Q&A unit '{qa_id}' not found"})

    elif tool_name == "get_follow_up_chain":
        qa_units = run_data.get("qa", {}).get("qa_units", [])
        qa_map = {q["qa_id"]: q for q in qa_units}
        qa_id = args.get("qa_id", "")

        # Find root
        current = qa_map.get(qa_id)
        if not current:
            return json.dumps({"error": f"Q&A unit '{qa_id}' not found"})

        while current.get("follow_up_of") and current["follow_up_of"] in qa_map:
            current = qa_map[current["follow_up_of"]]

        # Collect chain
        chain = [current]
        visited = {current["qa_id"]}
        # Find all that follow_up_of points to items in chain
        changed = True
        while changed:
            changed = False
            for q in qa_units:
                if q["qa_id"] not in visited and q.get("follow_up_of") in visited:
                    chain.append(q)
                    visited.add(q["qa_id"])
                    changed = True

        chain.sort(key=lambda x: x.get("sequence_in_session", 0))
        return json.dumps({"chain": [{"qa_id": q["qa_id"], "questioner": q.get("questioner_name"), "question_text": q.get("question_text", "")[:500], "response_text": q.get("response_text", "")[:500]} for q in chain]}, indent=2)

    elif tool_name == "search_full_text":
        extraction = run_data.get("extraction", {})
        keyword = args.get("keyword", "").lower()
        context_chars = args.get("context_chars", 300)

        results = []
        # Check both possible structures
        pages = extraction.get("pages", [])
        if not pages and "raw_text" in extraction:
            # Single text blob - split by page markers if possible
            pages = [{"page_number": 1, "text": extraction["raw_text"]}]

        for page in pages:
            text = page.get("text", "")
            page_num = page.get("page_number", 0)
            idx = text.lower().find(keyword)
            while idx != -1:
                start = max(0, idx - context_chars // 2)
                end = min(len(text), idx + len(keyword) + context_chars // 2)
                results.append({
                    "page_number": page_num,
                    "excerpt": text[start:end],
                    "match_position": idx
                })
                idx = text.lower().find(keyword, idx + 1)

        return json.dumps({"results": results[:5], "total_matches": len(results)}, indent=2)

    elif tool_name == "search_strategic_statements":
        strategic = run_data.get("strategic", {})
        statements = strategic.get("statements", [])
        results = []
        for s in statements:
            if args.get("keyword") and args["keyword"].lower() not in s.get("text", "").lower():
                continue
            if args.get("statement_type") and s.get("statement_type") != args["statement_type"]:
                continue
            if args.get("is_forward_looking") is not None and s.get("is_forward_looking") != args["is_forward_looking"]:
                continue
            if args.get("speaker_name") and args["speaker_name"].lower() not in s.get("speaker_name", "").lower():
                continue
            results.append(s)
        return json.dumps({"results": results[:10]}, indent=2)

    elif tool_name == "get_raw_text_page":
        extraction = run_data.get("extraction", {})
        page_num = args.get("page_number", 1)
        pages = extraction.get("pages", [])
        for page in pages:
            if page.get("page_number") == page_num:
                return json.dumps({"page_number": page_num, "text": page.get("text", "")[:3000]})
        return json.dumps({"error": f"Page {page_num} not found"})

    return json.dumps({"error": f"Unknown tool: {tool_name}"})


# ============================================================
# Test Result Tracking
# ============================================================

@dataclass
class TestResult:
    test_name: str
    approach: str  # "native" or "prompt_based"
    question: str
    success: bool = False
    tool_calls: list = field(default_factory=list)
    expected_tools: list = field(default_factory=list)
    tool_selection_correct: bool = False
    params_correct: bool = False
    response_text: str = ""
    response_quality: str = ""  # "good", "partial", "bad", "hallucinated"
    time_per_call_seconds: list = field(default_factory=list)
    total_time_seconds: float = 0.0
    error: str = ""
    raw_output: str = ""


# ============================================================
# Test: Native Tool Calling (ChatOllama)
# ============================================================

def test_native_tool_calling(model_name: str, num_ctx: int, run_data: dict, data_summary: str) -> list[TestResult]:
    """Test native ChatOllama tool calling."""
    print("\n" + "=" * 70)
    print("TEST SUITE: Native Tool Calling (ChatOllama)")
    print("=" * 70)

    results = []

    try:
        from langchain_ollama import ChatOllama
        from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage
        from langchain_core.tools import tool as tool_decorator

        llm = ChatOllama(
            model=model_name,
            base_url="http://localhost:11434",
            temperature=0.1,
            num_ctx=num_ctx,
        )

        # Convert tool definitions to langchain tools
        from langchain_core.tools import StructuredTool
        from pydantic import BaseModel as PydanticBaseModel, Field as PydanticField, create_model

        # Build pydantic models for tools dynamically
        langchain_tools = []
        for td in TOOL_DEFINITIONS:
            props = td["parameters"].get("properties", {})
            fields = {}
            for pname, pdef in props.items():
                ptype = str
                if pdef.get("type") == "integer":
                    ptype = int
                elif pdef.get("type") == "boolean":
                    ptype = bool

                if pname in td["parameters"].get("required", []):
                    fields[pname] = (ptype, PydanticField(description=pdef.get("description", "")))
                else:
                    fields[pname] = (Optional[ptype], PydanticField(default=None, description=pdef.get("description", "")))

            if fields:
                args_model = create_model(f"{td['name']}_args", **fields)
            else:
                args_model = create_model(f"{td['name']}_args")

            def make_func(name):
                def func(**kwargs):
                    return execute_tool(name, kwargs, run_data)
                func.__name__ = name
                func.__doc__ = td["description"]
                return func

            st = StructuredTool.from_function(
                func=make_func(td["name"]),
                name=td["name"],
                description=td["description"],
                args_schema=args_model,
            )
            langchain_tools.append(st)

        llm_with_tools = llm.bind_tools(langchain_tools)

    except Exception as e:
        print(f"\n  FATAL: Failed to initialize ChatOllama with tools: {e}")
        result = TestResult(
            test_name="initialization",
            approach="native",
            question="N/A",
            error=str(e),
        )
        return [result]

    # System prompt
    system_prompt = f"""You are an earnings call analyst assistant. You answer questions about an earnings call by using the available tools.

DATA SUMMARY:
{data_summary}

RULES:
1. Always use tools to find data. Never fabricate information.
2. If search returns no results, try search_full_text before concluding the topic wasn't discussed.
3. When referencing transcript content, cite using [qa_XXX], [page_N] format.
4. Keep answers concise."""

    test_scenarios = [
        {
            "name": "simple_factual",
            "question": "Who are the management speakers in this call?",
            "expected_tools": ["search_speakers"],
            "validate": lambda calls: any("search_speakers" in str(c) for c in calls),
        },
        {
            "name": "keyword_search",
            "question": "What was discussed about EBITDA margins?",
            "expected_tools": ["search_qa_units"],
            "validate": lambda calls: any("search_qa_units" in str(c) for c in calls),
        },
        {
            "name": "metadata_lookup",
            "question": "What company and quarter is this call for?",
            "expected_tools": ["get_run_metadata"],
            "validate": lambda calls: any("get_run_metadata" in str(c) for c in calls),
        },
        {
            "name": "full_text_fallback",
            "question": "Was there any discussion about zinc oxide applications?",
            "expected_tools": ["search_qa_units", "search_full_text"],
            "validate": lambda calls: any("search_qa_units" in str(c) or "search_full_text" in str(c) for c in calls),
        },
        {
            "name": "multi_step",
            "question": "Give me a summary of the main topics discussed in the Q&A session.",
            "expected_tools": ["search_qa_units", "get_run_metadata"],
            "validate": lambda calls: len(calls) >= 1,
        },
    ]

    for scenario in test_scenarios:
        print(f"\n  Test: {scenario['name']}")
        print(f"  Question: {scenario['question']}")

        result = TestResult(
            test_name=scenario["name"],
            approach="native",
            question=scenario["question"],
            expected_tools=scenario["expected_tools"],
        )

        try:
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=scenario["question"]),
            ]

            all_tool_calls = []
            call_times = []
            max_iterations = 5
            iteration = 0

            while iteration < max_iterations:
                iteration += 1
                start = time.time()
                response = llm_with_tools.invoke(messages)
                elapsed = time.time() - start
                call_times.append(elapsed)

                print(f"    Iteration {iteration}: {elapsed:.1f}s")

                if not response.tool_calls:
                    # Final response
                    result.response_text = response.content
                    print(f"    Final response: {response.content[:200]}...")
                    break

                # Process tool calls
                messages.append(response)
                for tc in response.tool_calls:
                    tool_name = tc["name"]
                    tool_args = tc["args"]
                    all_tool_calls.append({"name": tool_name, "args": tool_args})
                    print(f"    Tool call: {tool_name}({json.dumps(tool_args)})")

                    # Execute tool
                    tool_result = execute_tool(tool_name, tool_args, run_data)
                    messages.append(ToolMessage(content=tool_result, tool_call_id=tc["id"]))

            result.tool_calls = all_tool_calls
            result.time_per_call_seconds = call_times
            result.total_time_seconds = sum(call_times)
            result.success = True
            result.tool_selection_correct = scenario["validate"](all_tool_calls)

            # Basic quality check
            if result.response_text:
                result.response_quality = "good" if len(result.response_text) > 50 else "partial"
            else:
                result.response_quality = "no_response"

            print(f"    Tool selection correct: {result.tool_selection_correct}")
            print(f"    Total time: {result.total_time_seconds:.1f}s")

        except Exception as e:
            result.error = str(e)
            result.response_quality = "error"
            print(f"    ERROR: {e}")

        results.append(result)

    return results


# ============================================================
# Test: Prompt-Based Tool Calling (OllamaLLM)
# ============================================================

def test_prompt_based_tool_calling(model_name: str, num_ctx: int, run_data: dict, data_summary: str) -> list[TestResult]:
    """Test prompt-based tool calling using OllamaLLM with text parsing."""
    print("\n" + "=" * 70)
    print("TEST SUITE: Prompt-Based Tool Calling (OllamaLLM)")
    print("=" * 70)

    results = []

    try:
        from langchain_ollama import OllamaLLM

        llm = OllamaLLM(
            model=model_name,
            base_url="http://localhost:11434",
            temperature=0.1,
            num_ctx=num_ctx,
            num_predict=4096,
            streaming=False,
        )
    except Exception as e:
        print(f"\n  FATAL: Failed to initialize OllamaLLM: {e}")
        return [TestResult(test_name="initialization", approach="prompt_based", question="N/A", error=str(e))]

    # Build tool descriptions for the prompt
    tool_descriptions = ""
    for td in TOOL_DEFINITIONS:
        params = td["parameters"].get("properties", {})
        param_str = ", ".join(
            f"{k}: {v.get('type', 'string')}" + (f" (required)" if k in td["parameters"].get("required", []) else " (optional)")
            for k, v in params.items()
        )
        tool_descriptions += f"\n- {td['name']}({param_str}): {td['description']}"

    system_prompt = f"""You are an earnings call analyst assistant. You answer questions by calling tools and synthesizing results.

DATA SUMMARY:
{data_summary}

AVAILABLE TOOLS:
{tool_descriptions}

HOW TO CALL TOOLS:
When you need data, output a tool call in this exact format:
TOOL_CALL: tool_name(param1="value1", param2="value2")

After receiving tool results, you can call more tools or provide your final answer.
When you have enough information, provide your answer directly (without TOOL_CALL).

RULES:
1. Always use tools to find data. Never fabricate information.
2. If a search returns no results, try search_full_text before concluding the topic wasn't discussed.
3. Reference Q&A units by ID [qa_XXX] and pages [page_N].
4. Keep answers concise."""

    def parse_tool_call(text: str) -> Optional[tuple[str, dict]]:
        """Parse a TOOL_CALL from LLM output."""
        # Match TOOL_CALL: function_name(params)
        pattern = r'TOOL_CALL:\s*(\w+)\((.*?)\)'
        match = re.search(pattern, text, re.DOTALL)
        if not match:
            return None

        func_name = match.group(1)
        params_str = match.group(2).strip()

        # Parse parameters
        args = {}
        if params_str:
            # Try to parse key="value" pairs
            param_pattern = r'(\w+)\s*=\s*(?:"([^"]*?)"|\'([^\']*?)\'|(\d+)|(\w+))'
            for pm in re.finditer(param_pattern, params_str):
                key = pm.group(1)
                value = pm.group(2) or pm.group(3) or pm.group(4) or pm.group(5)
                # Convert types
                if value and value.isdigit():
                    value = int(value)
                elif value in ("true", "True"):
                    value = True
                elif value in ("false", "False"):
                    value = False
                args[key] = value

        return func_name, args

    test_scenarios = [
        {
            "name": "simple_factual",
            "question": "Who are the management speakers in this call?",
            "expected_tools": ["search_speakers"],
            "validate": lambda calls: any("search_speakers" in c.get("name", "") for c in calls),
        },
        {
            "name": "keyword_search",
            "question": "What was discussed about EBITDA margins?",
            "expected_tools": ["search_qa_units"],
            "validate": lambda calls: any("search_qa_units" in c.get("name", "") for c in calls),
        },
        {
            "name": "metadata_lookup",
            "question": "What company and quarter is this call for?",
            "expected_tools": ["get_run_metadata"],
            "validate": lambda calls: any("get_run_metadata" in c.get("name", "") for c in calls),
        },
        {
            "name": "full_text_fallback",
            "question": "Was there any discussion about zinc oxide applications?",
            "expected_tools": ["search_qa_units", "search_full_text"],
            "validate": lambda calls: any(c.get("name", "") in ("search_qa_units", "search_full_text") for c in calls),
        },
        {
            "name": "multi_step",
            "question": "Give me a summary of the main topics discussed in the Q&A session.",
            "expected_tools": ["search_qa_units", "get_run_metadata"],
            "validate": lambda calls: len(calls) >= 1,
        },
    ]

    for scenario in test_scenarios:
        print(f"\n  Test: {scenario['name']}")
        print(f"  Question: {scenario['question']}")

        result = TestResult(
            test_name=scenario["name"],
            approach="prompt_based",
            question=scenario["question"],
            expected_tools=scenario["expected_tools"],
        )

        try:
            conversation = f"{system_prompt}\n\nUser: {scenario['question']}\nAssistant:"

            all_tool_calls = []
            call_times = []
            max_iterations = 5
            iteration = 0

            while iteration < max_iterations:
                iteration += 1
                start = time.time()
                response_text = llm.invoke(conversation)
                elapsed = time.time() - start
                call_times.append(elapsed)

                print(f"    Iteration {iteration}: {elapsed:.1f}s")

                # Check for tool call
                parsed = parse_tool_call(response_text)
                if parsed:
                    tool_name, tool_args = parsed
                    all_tool_calls.append({"name": tool_name, "args": tool_args})
                    print(f"    Tool call: {tool_name}({json.dumps(tool_args)})")

                    # Execute and append to conversation
                    tool_result = execute_tool(tool_name, tool_args, run_data)
                    conversation += f" {response_text}\n\nTool Result:\n{tool_result}\n\nAssistant:"
                else:
                    # Final response
                    result.response_text = response_text.strip()
                    result.raw_output = response_text
                    # Show what the model actually returned
                    safe_preview = response_text[:400].encode('ascii', errors='replace').decode('ascii')
                    print(f"    Final response ({len(response_text)} chars):")
                    print(f"    >>> {safe_preview}")
                    break

            result.tool_calls = all_tool_calls
            result.time_per_call_seconds = call_times
            result.total_time_seconds = sum(call_times)
            result.success = True
            result.tool_selection_correct = scenario["validate"](all_tool_calls)

            if result.response_text:
                result.response_quality = "good" if len(result.response_text) > 50 else "partial"
            elif all_tool_calls:
                result.response_quality = "tools_only_no_synthesis"
            else:
                result.response_quality = "no_response"

            print(f"    Tool selection correct: {result.tool_selection_correct}")
            print(f"    Total time: {result.total_time_seconds:.1f}s")

        except Exception as e:
            result.error = str(e)
            result.response_quality = "error"
            print(f"    ERROR: {e}")

        results.append(result)

    return results


# ============================================================
# Report Generation
# ============================================================

def generate_report(native_results: list[TestResult], prompt_results: list[TestResult], model_name: str, num_ctx: int):
    """Generate a detailed comparison report."""
    print("\n\n" + "=" * 70)
    print("DETAILED ANALYSIS REPORT")
    print(f"Model: {model_name} | Context: {num_ctx} tokens")
    print("=" * 70)

    for approach_name, results in [("Native Tool Calling (ChatOllama)", native_results), ("Prompt-Based Tool Calling (OllamaLLM)", prompt_results)]:
        print(f"\n{'-' * 50}")
        print(f"  {approach_name}")
        print(f"{'-' * 50}")

        if not results:
            print("  No results (initialization failed)")
            continue

        # Check for init failure
        if results[0].test_name == "initialization" and results[0].error:
            print(f"  INITIALIZATION FAILED: {results[0].error}")
            continue

        total_tests = len(results)
        successful = sum(1 for r in results if r.success)
        correct_tools = sum(1 for r in results if r.tool_selection_correct)

        all_times = []
        for r in results:
            all_times.extend(r.time_per_call_seconds)

        avg_time = sum(all_times) / len(all_times) if all_times else 0
        total_times = [r.total_time_seconds for r in results if r.total_time_seconds > 0]
        avg_total = sum(total_times) / len(total_times) if total_times else 0

        print(f"\n  Summary:")
        print(f"    Tests passed:           {successful}/{total_tests}")
        print(f"    Correct tool selection: {correct_tools}/{total_tests}")
        print(f"    Avg time per LLM call:  {avg_time:.1f}s")
        print(f"    Avg total response time: {avg_total:.1f}s")
        if all_times:
            print(f"    Min/Max call time:      {min(all_times):.1f}s / {max(all_times):.1f}s")

        print(f"\n  Per-Test Details:")
        for r in results:
            if r.test_name == "initialization":
                continue
            status = "PASS" if r.success and r.tool_selection_correct else "FAIL" if r.error else "PARTIAL"
            print(f"\n    [{status}] {r.test_name}")
            print(f"      Question: {r.question}")
            print(f"      Expected tools: {r.expected_tools}")
            print(f"      Actual tools:   {[c['name'] for c in r.tool_calls]}")
            print(f"      Tool params:    {[c.get('args', {}) for c in r.tool_calls]}")
            print(f"      Correct tools:  {r.tool_selection_correct}")
            print(f"      Response quality: {r.response_quality}")
            print(f"      Time: {r.total_time_seconds:.1f}s ({len(r.time_per_call_seconds)} calls)")
            if r.error:
                print(f"      Error: {r.error}")
            if r.response_text:
                preview = r.response_text[:300].replace('\n', ' ').encode('ascii', errors='replace').decode('ascii')
                print(f"      Response preview: {preview}...")

    # Comparison
    print(f"\n{'=' * 70}")
    print("COMPARISON & RECOMMENDATION")
    print(f"{'=' * 70}")

    native_ok = any(r.success and r.tool_selection_correct for r in native_results if r.test_name != "initialization")
    prompt_ok = any(r.success and r.tool_selection_correct for r in prompt_results if r.test_name != "initialization")

    native_init_failed = any(r.test_name == "initialization" and r.error for r in native_results)

    if native_init_failed:
        print("\n  Native tool calling: FAILED TO INITIALIZE")
        print(f"  Error: {native_results[0].error}")
    else:
        native_correct = sum(1 for r in native_results if r.tool_selection_correct and r.test_name != "initialization")
        print(f"\n  Native tool calling: {native_correct}/{len([r for r in native_results if r.test_name != 'initialization'])} tests passed")

    prompt_correct = sum(1 for r in prompt_results if r.tool_selection_correct and r.test_name != "initialization")
    prompt_total = len([r for r in prompt_results if r.test_name != "initialization"])
    print(f"  Prompt-based calling: {prompt_correct}/{prompt_total} tests passed")

    # Timing comparison
    native_times = [r.total_time_seconds for r in native_results if r.total_time_seconds > 0]
    prompt_times = [r.total_time_seconds for r in prompt_results if r.total_time_seconds > 0]

    if native_times:
        print(f"\n  Native avg response time: {sum(native_times)/len(native_times):.1f}s")
    if prompt_times:
        print(f"  Prompt avg response time: {sum(prompt_times)/len(prompt_times):.1f}s")

    print(f"\n  RECOMMENDATION:")
    if native_init_failed and prompt_ok:
        print("  → Use PROMPT-BASED approach (native tool calling not supported)")
    elif native_ok and not prompt_ok:
        print("  → Use NATIVE tool calling (prompt-based parsing unreliable)")
    elif native_ok and prompt_ok:
        n_score = sum(1 for r in native_results if r.tool_selection_correct)
        p_score = sum(1 for r in prompt_results if r.tool_selection_correct)
        if n_score >= p_score:
            print("  → Use NATIVE tool calling (both work, native is cleaner)")
        else:
            print("  → Use PROMPT-BASED approach (more reliable tool selection)")
    elif not native_ok and not prompt_ok:
        print("  → NEITHER approach works reliably with this model")
        print("  → Consider: qwen2.5:14b, llama3.1:8b, or a cloud API")

    print()


# ============================================================
# Shared Helpers for Full-Text Tests
# ============================================================

def _init_full_text_llm(model_name: str, num_ctx: int):
    """Initialize OllamaLLM for full-text tests. Returns (llm, error_str)."""
    try:
        from langchain_ollama import OllamaLLM
        llm = OllamaLLM(
            model=model_name,
            base_url="http://localhost:11434",
            temperature=0.1,
            num_ctx=num_ctx,
            num_predict=4096,
            streaming=False,
        )
        return llm, None
    except Exception as e:
        return None, str(e)


def _load_full_text(run_data: dict) -> str:
    """Extract full transcript text from run data. Returns text or empty string."""
    full_text = ""

    # Source 1: pipeline_output.json has raw_text
    run_dir = Path(__file__).resolve().parent.parent / "data" / "runs"
    matches = [d for d in run_dir.iterdir() if d.name.startswith(run_data["run_id"])]
    if matches:
        pipeline_file = matches[0] / "pipeline_output.json"
        if pipeline_file.exists():
            with open(pipeline_file, "r", encoding="utf-8") as f:
                pipeline_data = json.load(f)
            if "raw_text" in pipeline_data:
                full_text = pipeline_data["raw_text"]

    # Source 2: extraction result pages
    if not full_text:
        extraction = run_data.get("extraction", {})
        pages = extraction.get("pages", [])
        if pages:
            full_text = "\n\n".join(p.get("text", "") for p in pages)
        elif "raw_text" in extraction:
            full_text = extraction["raw_text"]

    return full_text


def _build_system_prompt(full_text: str) -> str:
    """Build system prompt with full transcript."""
    return f"""You are an earnings call analyst. Below is the full transcript of an earnings call.
Answer the user's question based ONLY on the transcript content.
Cite specific quotes where possible. Keep answers concise and factual.
If the information is NOT in the transcript, say so clearly - do not make up information.

TRANSCRIPT:
{full_text}"""


def _run_single_question(llm, system_prompt: str, question: str, test_name: str, approach: str) -> TestResult:
    """Run a single question against the LLM and return TestResult."""
    result = TestResult(
        test_name=test_name,
        approach=approach,
        question=question,
    )

    try:
        prompt = f"{system_prompt}\n\nQuestion: {question}\nAnswer:"

        start = time.time()
        response_text = llm.invoke(prompt)
        elapsed = time.time() - start

        result.time_per_call_seconds = [elapsed]
        result.total_time_seconds = elapsed
        result.response_text = response_text.strip()
        result.raw_output = response_text
        result.success = True

        # Quality check
        text_len = len(response_text.strip())
        if text_len > 50:
            result.response_quality = "good"
        elif text_len > 10:
            result.response_quality = "partial"
        else:
            result.response_quality = "empty"

        safe_preview = response_text[:500].encode('ascii', errors='replace').decode('ascii')
        print(f"    Time: {elapsed:.1f}s")
        print(f"    Response ({len(response_text)} chars):")
        print(f"    >>> {safe_preview}")

    except Exception as e:
        result.error = str(e)
        result.response_quality = "error"
        print(f"    ERROR: {e}")

    return result


def _print_full_text_info(full_text: str, num_ctx: int):
    """Print transcript size info."""
    text_chars = len(full_text)
    approx_tokens = text_chars // 4
    print(f"\n  Transcript: {text_chars:,} chars (~{approx_tokens:,} tokens)")
    print(f"  Context window: {num_ctx:,} tokens")
    if approx_tokens > num_ctx * 0.7:
        print(f"  WARNING: Transcript may be too large for context window!")


# ============================================================
# Test: Full Text Direct Q&A (no tool calling) - Original 5
# ============================================================

def test_full_text_qa(model_name: str, num_ctx: int, run_data: dict) -> list[TestResult]:
    """Test direct Q&A with full transcript text stuffed into the prompt."""
    print("\n" + "=" * 70)
    print("TEST SUITE: Full Text Direct Q&A (no tool calling)")
    print("=" * 70)

    llm, err = _init_full_text_llm(model_name, num_ctx)
    if err:
        print(f"\n  FATAL: Failed to initialize OllamaLLM: {err}")
        return [TestResult(test_name="initialization", approach="full_text", question="N/A", error=err)]

    full_text = _load_full_text(run_data)
    if not full_text:
        print("  ERROR: No transcript text found in run data")
        return [TestResult(test_name="no_text", approach="full_text", question="N/A", error="No transcript text")]

    _print_full_text_info(full_text, num_ctx)
    system_prompt = _build_system_prompt(full_text)

    test_scenarios = [
        ("management_speakers", "Who are the management speakers in this call? List their names and titles."),
        ("ebitda_margins", "What was discussed about EBITDA margins? Include specific numbers."),
        ("company_metadata", "What company and quarter is this call for? What is the date?"),
        ("zinc_oxide", "Was there any discussion about zinc oxide applications? What industries were mentioned?"),
        ("qa_summary", "Give me a summary of the main topics discussed in the Q&A session."),
    ]

    results = []
    for name, question in test_scenarios:
        print(f"\n  Test: {name}")
        print(f"  Question: {question}")
        result = _run_single_question(llm, system_prompt, question, name, "full_text")
        results.append(result)

    return results


# ============================================================
# Test Suite 1: Extended Edge Cases (10 questions)
# ============================================================

def test_extended_edge_cases(model_name: str, num_ctx: int, run_data: dict) -> list[TestResult]:
    """Test harder questions requiring inference, cross-referencing, or handling missing data."""
    print("\n" + "=" * 70)
    print("TEST SUITE: Extended Edge Cases (10 questions)")
    print("=" * 70)

    llm, err = _init_full_text_llm(model_name, num_ctx)
    if err:
        print(f"\n  FATAL: Failed to initialize OllamaLLM: {err}")
        return [TestResult(test_name="initialization", approach="edge_case", question="N/A", error=err)]

    full_text = _load_full_text(run_data)
    if not full_text:
        print("  ERROR: No transcript text found in run data")
        return [TestResult(test_name="no_text", approach="edge_case", question="N/A", error="No transcript text")]

    _print_full_text_info(full_text, num_ctx)
    system_prompt = _build_system_prompt(full_text)

    test_scenarios = [
        ("capacity_utilization", "What is the company's current capacity utilization and how much room for growth?"),
        ("margin_comparison", "Compare the Q2 margins with H1 margins - is the trend improving?"),
        ("dahej_analyst", "Which analyst asked about the Dahej expansion?"),
        ("risk_mentions", "What risks did management mention?"),
        ("dividend_discussion", "Did anyone ask about dividends?"),
        ("dahej_revenue", "What is the expected revenue from the Dahej plant?"),
        ("export_countries", "How many countries does the company export to?"),
        ("naidupeta_certs", "What certifications does the Naidupeta facility hold?"),
        ("moderator_closing", "What did the moderator say at the end of the call?"),
        ("competitor_discussion", "Was there any discussion about competitors?"),
    ]

    results = []
    for name, question in test_scenarios:
        print(f"\n  Test: {name}")
        print(f"  Question: {question}")
        result = _run_single_question(llm, system_prompt, question, name, "edge_case")
        results.append(result)

    return results


# ============================================================
# Test Suite 2: Multi-Turn Conversation (5-turn chain)
# ============================================================

def test_multi_turn_conversation(model_name: str, num_ctx: int, run_data: dict) -> list[TestResult]:
    """Test multi-turn conversation where each question builds on prior answers."""
    print("\n" + "=" * 70)
    print("TEST SUITE: Multi-Turn Conversation (5-turn chain)")
    print("=" * 70)

    llm, err = _init_full_text_llm(model_name, num_ctx)
    if err:
        print(f"\n  FATAL: Failed to initialize OllamaLLM: {err}")
        return [TestResult(test_name="initialization", approach="multi_turn", question="N/A", error=err)]

    full_text = _load_full_text(run_data)
    if not full_text:
        print("  ERROR: No transcript text found in run data")
        return [TestResult(test_name="no_text", approach="multi_turn", question="N/A", error="No transcript text")]

    _print_full_text_info(full_text, num_ctx)
    system_prompt = _build_system_prompt(full_text)

    turns = [
        ("turn_1_highlights", "What were the key financial highlights for Q2?"),
        ("turn_2_h1_compare", "How does that compare to the first half numbers?"),
        ("turn_3_margin_decline", "What reasons did management give for the margin decline?"),
        ("turn_4_recovery", "Are they expecting margins to recover? What's the timeline?"),
        ("turn_5_summarize", "Summarize everything we discussed about margins in 3 bullet points."),
    ]

    results = []
    # Build conversation incrementally
    conversation_history = ""

    for name, question in turns:
        print(f"\n  Turn: {name}")
        print(f"  Question: {question}")

        result = TestResult(
            test_name=name,
            approach="multi_turn",
            question=question,
        )

        try:
            # Build prompt with conversation history
            if conversation_history:
                prompt = f"{system_prompt}\n\n{conversation_history}User: {question}\nAssistant:"
            else:
                prompt = f"{system_prompt}\n\nUser: {question}\nAssistant:"

            start = time.time()
            response_text = llm.invoke(prompt)
            elapsed = time.time() - start

            result.time_per_call_seconds = [elapsed]
            result.total_time_seconds = elapsed
            result.response_text = response_text.strip()
            result.raw_output = response_text
            result.success = True

            text_len = len(response_text.strip())
            if text_len > 50:
                result.response_quality = "good"
            elif text_len > 10:
                result.response_quality = "partial"
            else:
                result.response_quality = "empty"

            safe_preview = response_text[:500].encode('ascii', errors='replace').decode('ascii')
            print(f"    Time: {elapsed:.1f}s")
            print(f"    Response ({len(response_text)} chars):")
            print(f"    >>> {safe_preview}")

            # Append to conversation history for next turn
            # Truncate long responses in history to avoid blowing up context
            history_response = response_text.strip()[:1000]
            conversation_history += f"User: {question}\nAssistant: {history_response}\n\n"

        except Exception as e:
            result.error = str(e)
            result.response_quality = "error"
            print(f"    ERROR: {e}")
            # Still add to history so subsequent turns know about the failure
            conversation_history += f"User: {question}\nAssistant: [error - no response]\n\n"

        results.append(result)

    return results


# ============================================================
# Test Suite 3: Adversarial / Hallucination Probes (5 questions)
# ============================================================

def test_adversarial_probes(model_name: str, num_ctx: int, run_data: dict) -> list[TestResult]:
    """Test if the model hallucinates or makes up information not in the transcript."""
    print("\n" + "=" * 70)
    print("TEST SUITE: Adversarial / Hallucination Probes (5 questions)")
    print("=" * 70)

    llm, err = _init_full_text_llm(model_name, num_ctx)
    if err:
        print(f"\n  FATAL: Failed to initialize OllamaLLM: {err}")
        return [TestResult(test_name="initialization", approach="adversarial", question="N/A", error=err)]

    full_text = _load_full_text(run_data)
    if not full_text:
        print("  ERROR: No transcript text found in run data")
        return [TestResult(test_name="no_text", approach="adversarial", question="N/A", error="No transcript text")]

    _print_full_text_info(full_text, num_ctx)
    system_prompt = _build_system_prompt(full_text)

    # These topics should NOT be in the transcript - model should say "not discussed"
    test_scenarios = [
        ("ai_strategy", "What did the CEO say about their AI strategy?"),
        ("future_quarter", "What was the revenue for Q3 FY26?"),
        ("debt_equity", "Tell me about the company's debt-to-equity ratio."),
        ("competitor_name", "Who is the company's biggest competitor?"),
        ("stock_target", "What is the stock price target mentioned by analysts?"),
    ]

    # Keywords that indicate the model correctly refused to hallucinate
    refusal_indicators = [
        "not discussed", "not mentioned", "no mention", "not in the transcript",
        "not available", "not provided", "no information", "does not mention",
        "doesn't mention", "wasn't discussed", "was not discussed",
        "no discussion", "not covered", "not addressed", "cannot find",
        "not found", "no reference", "no data", "not present",
        "i don't see", "i cannot find", "there is no",
        "not disclosed", "does not contain", "doesn't contain",
        "did not discuss", "didn't discuss", "no figures",
        "not contain any", "does not include", "no comment",
    ]

    results = []
    for name, question in test_scenarios:
        print(f"\n  Test: {name}")
        print(f"  Question: {question}")

        result = _run_single_question(llm, system_prompt, question, name, "adversarial")

        # Override quality assessment for adversarial tests:
        # "good" = model correctly says info is not in transcript
        # "hallucinated" = model makes up an answer
        if result.response_text:
            response_lower = result.response_text.lower()
            refused = any(indicator in response_lower for indicator in refusal_indicators)
            if refused:
                result.response_quality = "good"
                print(f"    >> CORRECTLY REFUSED (no hallucination)")
            else:
                result.response_quality = "hallucinated"
                print(f"    >> WARNING: Possible hallucination - model did not refuse")

        results.append(result)

    return results


# ============================================================
# Test Suite 4: Latency Profiling (3 runs of same question)
# ============================================================

def test_latency_profiling(model_name: str, num_ctx: int, run_data: dict) -> list[TestResult]:
    """Run the same question 3 times to measure consistency and KV cache benefit."""
    print("\n" + "=" * 70)
    print("TEST SUITE: Latency Profiling (3 runs x 2 questions)")
    print("=" * 70)

    llm, err = _init_full_text_llm(model_name, num_ctx)
    if err:
        print(f"\n  FATAL: Failed to initialize OllamaLLM: {err}")
        return [TestResult(test_name="initialization", approach="latency", question="N/A", error=err)]

    full_text = _load_full_text(run_data)
    if not full_text:
        print("  ERROR: No transcript text found in run data")
        return [TestResult(test_name="no_text", approach="latency", question="N/A", error="No transcript text")]

    _print_full_text_info(full_text, num_ctx)
    system_prompt = _build_system_prompt(full_text)

    # Two different questions, each run 3 times
    questions = [
        ("latency_q1", "Who are the management speakers in this call? List their names and titles."),
        ("latency_q2", "What was discussed about EBITDA margins? Include specific numbers."),
    ]

    results = []
    for base_name, question in questions:
        print(f"\n  Profiling: {base_name}")
        print(f"  Question: {question}")
        run_times = []

        for run_num in range(1, 4):
            name = f"{base_name}_run{run_num}"
            print(f"\n    Run {run_num}/3:")
            result = _run_single_question(llm, system_prompt, question, name, "latency")
            results.append(result)
            if result.total_time_seconds > 0:
                run_times.append(result.total_time_seconds)

        if run_times:
            avg = sum(run_times) / len(run_times)
            first = run_times[0]
            subsequent = run_times[1:] if len(run_times) > 1 else run_times
            avg_subsequent = sum(subsequent) / len(subsequent)
            speedup = (first - avg_subsequent) / first * 100 if first > 0 else 0

            print(f"\n    Latency Summary for '{base_name}':")
            print(f"      Run times: {', '.join(f'{t:.1f}s' for t in run_times)}")
            print(f"      First run:      {first:.1f}s")
            print(f"      Avg subsequent: {avg_subsequent:.1f}s")
            print(f"      KV cache speedup: {speedup:+.1f}%")

    return results


# ============================================================
# Report Generation for Extended Tests
# ============================================================

def generate_full_text_report(results: list[TestResult], model_name: str, num_ctx: int,
                               title: str = "FULL TEXT Q&A REPORT"):
    """Generate report for full-text Q&A test results."""
    print("\n\n" + "=" * 70)
    print(title)
    print(f"Model: {model_name} | Context: {num_ctx} tokens")
    print("=" * 70)

    if not results:
        print("  No results")
        return

    if results[0].test_name in ("initialization", "no_text") and results[0].error:
        print(f"  FAILED: {results[0].error}")
        return

    total = len(results)
    good = sum(1 for r in results if r.response_quality == "good")
    partial = sum(1 for r in results if r.response_quality == "partial")
    empty = sum(1 for r in results if r.response_quality in ("empty", "no_response"))
    errors = sum(1 for r in results if r.response_quality == "error")
    hallucinated = sum(1 for r in results if r.response_quality == "hallucinated")

    all_times = [r.total_time_seconds for r in results if r.total_time_seconds > 0]
    avg_time = sum(all_times) / len(all_times) if all_times else 0

    print(f"\n  Summary:")
    print(f"    Good responses:    {good}/{total}")
    print(f"    Partial responses: {partial}/{total}")
    print(f"    Empty responses:   {empty}/{total}")
    if hallucinated > 0:
        print(f"    HALLUCINATED:      {hallucinated}/{total}")
    print(f"    Errors:            {errors}/{total}")
    print(f"    Avg response time: {avg_time:.1f}s")
    if all_times:
        print(f"    Min/Max time:      {min(all_times):.1f}s / {max(all_times):.1f}s")

    print(f"\n  Per-Question Details:")
    for r in results:
        if r.test_name in ("initialization", "no_text"):
            continue
        status_map = {"good": "GOOD", "partial": "PARTIAL", "empty": "EMPTY",
                      "hallucinated": "HALLUCINATED", "error": "ERROR"}
        status = status_map.get(r.response_quality, r.response_quality.upper())
        print(f"\n    [{status}] {r.test_name} ({r.total_time_seconds:.1f}s)")
        print(f"      Q: {r.question}")
        if r.response_text:
            preview = r.response_text[:400].replace('\n', '\n      ').encode('ascii', errors='replace').decode('ascii')
            print(f"      A: {preview}")
        if r.error:
            print(f"      Error: {r.error}")

    print()


def generate_latency_report(results: list[TestResult], model_name: str, num_ctx: int):
    """Generate specialized latency profiling report."""
    print("\n\n" + "=" * 70)
    print("LATENCY PROFILING REPORT")
    print(f"Model: {model_name} | Context: {num_ctx} tokens")
    print("=" * 70)

    if not results:
        print("  No results")
        return

    if results[0].test_name in ("initialization", "no_text") and results[0].error:
        print(f"  FAILED: {results[0].error}")
        return

    # Group by base question name (strip _runN suffix)
    groups: dict[str, list[TestResult]] = {}
    for r in results:
        base = re.sub(r'_run\d+$', '', r.test_name)
        groups.setdefault(base, []).append(r)

    all_times = [r.total_time_seconds for r in results if r.total_time_seconds > 0]

    print(f"\n  Overall:")
    if all_times:
        print(f"    Total questions:  {len(all_times)}")
        print(f"    Avg time:         {sum(all_times)/len(all_times):.1f}s")
        print(f"    Min/Max:          {min(all_times):.1f}s / {max(all_times):.1f}s")

    print(f"\n  Per-Question Breakdown:")
    for base_name, group_results in groups.items():
        times = [r.total_time_seconds for r in group_results if r.total_time_seconds > 0]
        if not times:
            continue

        print(f"\n    {base_name}:")
        print(f"      Runs:           {', '.join(f'{t:.1f}s' for t in times)}")
        if len(times) >= 2:
            first = times[0]
            subsequent = times[1:]
            avg_sub = sum(subsequent) / len(subsequent)
            speedup = (first - avg_sub) / first * 100 if first > 0 else 0
            print(f"      First run:      {first:.1f}s")
            print(f"      Avg subsequent: {avg_sub:.1f}s")
            print(f"      KV cache effect: {speedup:+.1f}%")

        # Check response consistency
        responses = [r.response_text for r in group_results if r.response_text]
        if len(responses) >= 2:
            # Simple consistency: compare lengths
            lengths = [len(r) for r in responses]
            len_variance = max(lengths) - min(lengths)
            avg_len = sum(lengths) / len(lengths)
            consistency = 100 - (len_variance / avg_len * 100) if avg_len > 0 else 0
            print(f"      Response lengths: {', '.join(str(l) for l in lengths)}")
            print(f"      Length consistency: {consistency:.0f}%")

    print()


def generate_extended_summary(
    base_results: list[TestResult],
    edge_results: list[TestResult],
    multi_results: list[TestResult],
    adversarial_results: list[TestResult],
    latency_results: list[TestResult],
    model_name: str,
    num_ctx: int,
):
    """Generate a combined summary across all extended test suites."""
    print("\n" + "=" * 70)
    print("EXTENDED TEST SUMMARY")
    print(f"Model: {model_name} | Context: {num_ctx} tokens")
    print("=" * 70)

    suites = [
        ("Base (5 Q)", base_results),
        ("Edge Cases (10 Q)", edge_results),
        ("Multi-Turn (5 turns)", multi_results),
        ("Adversarial (5 Q)", adversarial_results),
        ("Latency (6 runs)", latency_results),
    ]

    total_good = 0
    total_all = 0
    total_hallucinated = 0

    for suite_name, results in suites:
        if not results or (results[0].test_name in ("initialization", "no_text") and results[0].error):
            print(f"\n  {suite_name}: SKIPPED/FAILED")
            continue

        good = sum(1 for r in results if r.response_quality == "good")
        total = len(results)
        hallucinated = sum(1 for r in results if r.response_quality == "hallucinated")
        times = [r.total_time_seconds for r in results if r.total_time_seconds > 0]
        avg_t = sum(times) / len(times) if times else 0

        total_good += good
        total_all += total
        total_hallucinated += hallucinated

        status = "PASS" if good == total else "MIXED" if good > total // 2 else "FAIL"
        hall_warn = f" [{hallucinated} HALLUCINATED]" if hallucinated else ""
        print(f"\n  [{status}] {suite_name}: {good}/{total} good, avg {avg_t:.1f}s{hall_warn}")

    print(f"\n  {'=' * 50}")
    print(f"  OVERALL: {total_good}/{total_all} good responses")
    if total_hallucinated > 0:
        print(f"  HALLUCINATIONS: {total_hallucinated} detected")
    print(f"  Accuracy rate: {total_good/total_all*100:.0f}%" if total_all > 0 else "  No tests run")
    print()


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Test LLM tool calling for chatbot agent")
    parser.add_argument("--run-id", default="20e9f23c-744", help="Run ID to test against (partial match supported)")
    parser.add_argument("--model", default="gpt-oss:20b", help="Ollama model name")
    parser.add_argument("--num-ctx", type=int, default=16384, help="Context window size")
    parser.add_argument("--skip-native", action="store_true", help="Skip native tool calling test")
    parser.add_argument("--skip-prompt", action="store_true", help="Skip prompt-based test")
    parser.add_argument("--test-full-text", action="store_true", help="Test full-text direct Q&A (no tool calling)")
    parser.add_argument("--extended", action="store_true", help="Run extended test suites (edge cases, multi-turn, adversarial, latency)")
    parser.add_argument("--only-edge", action="store_true", help="Only run edge case tests")
    parser.add_argument("--only-multi", action="store_true", help="Only run multi-turn tests")
    parser.add_argument("--only-adversarial", action="store_true", help="Only run adversarial tests")
    parser.add_argument("--only-latency", action="store_true", help="Only run latency profiling")
    args = parser.parse_args()

    print(f"Loading run data: {args.run_id}")
    run_data = load_run_data(args.run_id)
    data_summary = generate_data_summary(run_data)

    print(f"\nData Summary:\n{data_summary}")
    print(f"\nModel: {args.model}")
    print(f"Context window: {args.num_ctx}")

    # Individual suite selectors
    if args.only_edge:
        results = test_extended_edge_cases(args.model, args.num_ctx, run_data)
        generate_full_text_report(results, args.model, args.num_ctx, title="EDGE CASE REPORT")
        return

    if args.only_multi:
        results = test_multi_turn_conversation(args.model, args.num_ctx, run_data)
        generate_full_text_report(results, args.model, args.num_ctx, title="MULTI-TURN CONVERSATION REPORT")
        return

    if args.only_adversarial:
        results = test_adversarial_probes(args.model, args.num_ctx, run_data)
        generate_full_text_report(results, args.model, args.num_ctx, title="ADVERSARIAL / HALLUCINATION REPORT")
        return

    if args.only_latency:
        results = test_latency_profiling(args.model, args.num_ctx, run_data)
        generate_latency_report(results, args.model, args.num_ctx)
        return

    # Full-text mode with optional extended suites
    if args.test_full_text:
        base_results = test_full_text_qa(args.model, args.num_ctx, run_data)
        generate_full_text_report(base_results, args.model, args.num_ctx)

        if args.extended:
            edge_results = test_extended_edge_cases(args.model, args.num_ctx, run_data)
            generate_full_text_report(edge_results, args.model, args.num_ctx, title="EDGE CASE REPORT")

            multi_results = test_multi_turn_conversation(args.model, args.num_ctx, run_data)
            generate_full_text_report(multi_results, args.model, args.num_ctx, title="MULTI-TURN CONVERSATION REPORT")

            adversarial_results = test_adversarial_probes(args.model, args.num_ctx, run_data)
            generate_full_text_report(adversarial_results, args.model, args.num_ctx, title="ADVERSARIAL / HALLUCINATION REPORT")

            latency_results = test_latency_profiling(args.model, args.num_ctx, run_data)
            generate_latency_report(latency_results, args.model, args.num_ctx)

            generate_extended_summary(
                base_results, edge_results, multi_results,
                adversarial_results, latency_results,
                args.model, args.num_ctx,
            )
        return

    native_results = []
    prompt_results = []

    if not args.skip_native:
        native_results = test_native_tool_calling(args.model, args.num_ctx, run_data, data_summary)

    if not args.skip_prompt:
        prompt_results = test_prompt_based_tool_calling(args.model, args.num_ctx, run_data, data_summary)

    generate_report(native_results, prompt_results, args.model, args.num_ctx)


if __name__ == "__main__":
    main()
