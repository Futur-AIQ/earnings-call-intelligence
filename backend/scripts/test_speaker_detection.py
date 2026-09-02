"""Speaker Detection Diagnostics Script.

Runs each phase of speaker detection in isolation to pinpoint exactly where
detection fails on runs e3235886-265 and b38cee51-6c4.

Usage:
    cd backend
    python scripts/test_speaker_detection.py [--run-id RUN_ID]

Expected output: per-run, per-phase diagnostics that reveal which step breaks.
"""

import json
import re
import sys
from pathlib import Path
from typing import Optional
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Path setup (follow existing script pattern)
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

RUNS_DIR = Path(__file__).resolve().parent.parent / "data" / "runs"


# ---------------------------------------------------------------------------
# ASCII-safe print helper (Windows cp1252 safe)
# ---------------------------------------------------------------------------
def p(text: str) -> None:
    safe = str(text).encode("ascii", errors="replace").decode("ascii")
    print(safe)


def hdr(title: str, char: str = "=", width: int = 72) -> None:
    p(char * width)
    p(title)
    p(char * width)


def sub(title: str) -> None:
    hdr(title, char="-", width=60)


# ---------------------------------------------------------------------------
# Section 1: Data loading
# ---------------------------------------------------------------------------

def resolve_run_dir(run_id: str) -> Path:
    """Resolve full run directory from partial ID."""
    full_path = RUNS_DIR / run_id
    if full_path.exists():
        return full_path
    matches = [d for d in RUNS_DIR.iterdir() if d.name.startswith(run_id)]
    if matches:
        return matches[0]
    raise FileNotFoundError(f"Run not found: {run_id}")


def load_run_data(run_id: str) -> dict:
    """Load all relevant JSON files for a run.

    Returns dict with keys: run_dir, boundary, extraction, metadata_stage,
    speakers_stored, full_text.
    """
    from src.pipeline_v2.models import BoundaryDetectionResult, ExtractedMetadata

    run_dir = resolve_run_dir(run_id)
    p(f"  Loading from: {run_dir.name}")

    data = {"run_id": run_dir.name, "run_dir": run_dir}

    # --- boundary result ---
    boundary_path = run_dir / "stage_boundary_result.json"
    if boundary_path.exists():
        with open(boundary_path, encoding="utf-8") as f:
            raw = json.load(f)
        data["boundary"] = BoundaryDetectionResult.model_validate(raw)
        p(f"  [OK] stage_boundary_result.json  ({data['boundary'].total_sections} sections)")
    else:
        data["boundary"] = None
        p("  [MISSING] stage_boundary_result.json")

    # --- extraction result (raw text) ---
    extraction_path = run_dir / "stage_extraction_result.json"
    if extraction_path.exists():
        with open(extraction_path, encoding="utf-8") as f:
            extraction_raw = json.load(f)
        data["extraction_raw"] = extraction_raw

        # Extract full text — try common structures
        pages = extraction_raw.get("pages", [])
        if pages:
            data["full_text"] = "\n\n".join(
                p_obj.get("text", "") for p_obj in pages
            )
        elif "raw_text" in extraction_raw:
            data["full_text"] = extraction_raw["raw_text"]
        elif "text" in extraction_raw:
            data["full_text"] = extraction_raw["text"]
        else:
            data["full_text"] = ""

        text_len = len(data["full_text"])
        p(f"  [OK] stage_extraction_result.json ({text_len:,} chars)")
    else:
        data["extraction_raw"] = {}
        data["full_text"] = ""
        p("  [MISSING] stage_extraction_result.json")

    # Also try pipeline_output.json for raw_text (more complete)
    pipeline_path = run_dir / "pipeline_output.json"
    if pipeline_path.exists() and not data["full_text"]:
        with open(pipeline_path, encoding="utf-8") as f:
            pipeline_raw = json.load(f)
        if "raw_text" in pipeline_raw:
            data["full_text"] = pipeline_raw["raw_text"]
            p(f"  [OK] pipeline_output.json (raw_text fallback, {len(data['full_text']):,} chars)")

    # --- metadata stage result ---
    meta_path = run_dir / "stage_metadata_result.json"
    if meta_path.exists():
        with open(meta_path, encoding="utf-8") as f:
            meta_raw = json.load(f)
        try:
            data["metadata_stage"] = ExtractedMetadata.model_validate(meta_raw)
            p(f"  [OK] stage_metadata_result.json  (company={meta_raw.get('company_name', '?')})")
        except Exception as e:
            data["metadata_stage"] = None
            p(f"  [WARN] stage_metadata_result.json parse failed: {e}")
    else:
        data["metadata_stage"] = None
        p("  [MISSING] stage_metadata_result.json")

    # --- stored speakers result (for comparison) ---
    speakers_path = run_dir / "stage_speakers_result.json"
    if speakers_path.exists():
        with open(speakers_path, encoding="utf-8") as f:
            data["speakers_stored"] = json.load(f)
        n = len(data["speakers_stored"].get("speakers", {}))
        mgmt = data["speakers_stored"].get("management_count", "?")
        analysts = data["speakers_stored"].get("analyst_count", "?")
        p(f"  [OK] stage_speakers_result.json  ({n} speakers, management={mgmt}, analysts={analysts})")
    else:
        data["speakers_stored"] = {}
        p("  [MISSING] stage_speakers_result.json")

    return data


# ---------------------------------------------------------------------------
# Section 2: Phase A — deterministic candidate generation (use_llm=False)
# ---------------------------------------------------------------------------

def run_phase_a(run_data: dict) -> tuple:
    """Run build_speaker_registry with use_llm=False.

    Returns (registry, trace).
    """
    from src.pipeline_v2.stages.speakers import build_speaker_registry

    boundary = run_data.get("boundary")
    if not boundary:
        p("  [SKIP] No boundary result available")
        return None, None

    registry, trace = build_speaker_registry(
        boundary_result=boundary,
        metadata=run_data.get("metadata_stage"),
        full_text=run_data.get("full_text") or "",
        use_llm=False,
    )
    return registry, trace


def print_phase_a_results(registry, trace) -> None:
    """Print Phase A results with junk detection."""
    if not registry or not trace:
        p("  [N/A] Phase A returned no results")
        return

    p(f"\n  Total candidates found by regex:  {trace.total_candidates}")
    p(f"  Passed Phase A hard rules:        {trace.candidates_passed_phase_a}")
    p(f"  Rejected by Phase A hard rules:   {trace.candidates_rejected_phase_a}")

    # Categorise candidates
    passed = [c for c in trace.candidates_generated if c.is_valid]
    rejected = [c for c in trace.candidates_generated if not c.is_valid]

    # Heuristic junk checks (words that look like non-names)
    JUNK_PATTERNS = [
        r"^\d",                        # starts with digit
        r"^(mumbai|delhi|bangalore|pune|hyderabad|chennai|kolkata)$",  # city names
        r"^(january|february|march|april|may|june|july|august|september|october|november|december)$",
        r"^(monday|tuesday|wednesday|thursday|friday|saturday|sunday)$",
        r"^(scrip|isin|cin|nse|bse|pan)\b",
        r"^(so|the|a|an|in|of|on|at|by|for)$",
        r"[0-9]{4,}",                  # long digit sequence (codes)
        r"^[A-Z0-9]{4,}$",             # ALL-CAPS codes (NSE symbol etc.)
    ]

    def looks_like_junk(name: str) -> Optional[str]:
        n = name.strip().lower()
        for pat in JUNK_PATTERNS:
            if re.search(pat, n, re.IGNORECASE):
                return pat
        return None

    junk_passed = [(c, looks_like_junk(c.normalized_name)) for c in passed]
    actual_junk = [(c, reason) for c, reason in junk_passed if reason]

    p(f"\n  Speakers in Phase-A output ({len(passed)} total):")
    for c in passed:
        junk_flag = ""
        reason = looks_like_junk(c.normalized_name)
        if reason:
            junk_flag = "  <-- JUNK?"
        p(f"    - {c.normalized_name!r}{junk_flag}")

    p(f"\n  Rejected by Phase A ({len(rejected)}):")
    for c in rejected[:20]:
        p(f"    - {c.raw_name!r}  reason={c.rejection_reason}")

    if actual_junk:
        p(f"\n  [WARN] {len(actual_junk)} JUNK strings survived Phase A:")
        for c, reason in actual_junk:
            p(f"    - {c.normalized_name!r}  (matched pattern: {reason})")
    else:
        p("\n  [OK] No obvious junk survived Phase A")

    return


# ---------------------------------------------------------------------------
# Section 3: Raw LLM call in isolation
# ---------------------------------------------------------------------------

# Module-level storage for captured prompt/response
_captured: dict = {"prompt": None, "response": None, "error": None}


def _patched_invoke_llm(prompt: str, max_tokens: int = 200, require_json: bool = False) -> str:
    """Wrapper around _invoke_llm that captures prompt and raw response."""
    _captured["prompt"] = prompt
    _captured["response"] = None
    _captured["error"] = None

    # Call through to the real LLM (single attempt for diagnostic purposes)
    try:
        from src.llm.client import create_json_llm_client
        llm = create_json_llm_client(num_predict=max_tokens)
        raw = llm.invoke(prompt)
        raw = raw.strip() if raw else ""
        _captured["response"] = raw
        return raw
    except Exception as exc:
        _captured["error"] = str(exc)
        return ""


def run_raw_llm_call(run_data: dict) -> dict:
    """Call verify_speaker_registry_with_context directly, capturing raw I/O.

    Returns dict with: prompt_preview, raw_response, is_valid_json,
    parsed_decision, error.
    """
    from src.pipeline_v2.stages.speakers import build_speaker_registry
    from src.pipeline_v2.llm_helpers import (
        verify_speaker_registry_with_context,
        SpeakerRegistryDecision,
    )
    from src.pipeline_v2.models import SectionType

    result = {
        "prompt_preview": None,
        "raw_response": None,
        "is_valid_json": False,
        "parsed_decision": None,
        "error": None,
    }

    boundary = run_data.get("boundary")
    if not boundary:
        result["error"] = "No boundary result"
        return result

    # Build the same inputs as build_speaker_registry would
    from collections import defaultdict
    from src.pipeline_v2.stages.speakers import (
        _enforce_hard_rules_on_name,
        _normalize_name,
        _is_moderator_name,
    )

    speaker_occurrences: dict = defaultdict(list)
    for section in boundary.sections:
        for speaker_name in section.detected_speakers:
            is_valid, _ = _enforce_hard_rules_on_name(speaker_name)
            if is_valid:
                speaker_occurrences[speaker_name].append({
                    "section_id": section.section_id,
                    "section_type": section.section_type,
                    "page": section.start_page,
                    "context": section.raw_text[:500] if section.raw_text else "",
                })

    non_moderator_occurrences = {
        name: occs for name, occs in speaker_occurrences.items()
        if not _is_moderator_name(name)
    }

    all_candidates = []
    for name, occurrences in non_moderator_occurrences.items():
        turns = []
        for occ in occurrences[:5]:
            ctx = occ.get("context", "")
            if ctx:
                turns.append(ctx[:300])
        all_candidates.append({
            "name": name,
            "turns": turns,
            "occurrences": len(occurrences),
            "first_page": min(occ["page"] for occ in occurrences),
        })

    opening_remarks = ""
    qa_session = ""
    for section in boundary.sections:
        if section.section_type == SectionType.OPENING_REMARKS:
            opening_remarks = section.raw_text[:2000] if section.raw_text else ""
        elif section.section_type == SectionType.QA_SESSION:
            qa_session = section.raw_text[:3000] if section.raw_text else ""

    p(f"  Passing {len(all_candidates)} candidates to LLM...")

    # Patch _invoke_llm to capture prompt and response
    with patch("src.pipeline_v2.llm_helpers._invoke_llm", side_effect=_patched_invoke_llm):
        try:
            decision = verify_speaker_registry_with_context(
                speaker_candidates=all_candidates,
                opening_remarks_text=opening_remarks,
                qa_session_text=qa_session,
                metadata_hints=None,
            )
            result["parsed_decision"] = decision
        except Exception as exc:
            result["error"] = str(exc)

    result["prompt_preview"] = _captured.get("prompt")
    result["raw_response"] = _captured.get("response")
    if _captured.get("error"):
        result["error"] = (result.get("error") or "") + " | invoke_error: " + _captured["error"]

    # Check JSON validity
    raw = result["raw_response"] or ""
    try:
        json_match = re.search(r"\{[\s\S]*\}", raw)
        if json_match:
            json.loads(json_match.group())
            result["is_valid_json"] = True
    except (json.JSONDecodeError, TypeError):
        result["is_valid_json"] = False

    return result


def print_raw_llm_results(raw_result: dict) -> None:
    """Print raw LLM call diagnostics."""
    # Prompt preview (first 600 chars)
    prompt = raw_result.get("prompt_preview") or ""
    if prompt:
        p(f"\n  PROMPT SENT TO LLM ({len(prompt):,} chars, first 600):")
        p("  " + "-" * 56)
        preview = prompt[:600].encode("ascii", errors="replace").decode("ascii")
        for line in preview.splitlines():
            p(f"    {line}")
        p("  " + "-" * 56)
    else:
        p("\n  [WARN] Prompt not captured — patch may not have triggered")

    # Raw response
    raw = raw_result.get("raw_response")
    if raw is None:
        p("\n  RAW LLM RESPONSE: <None — LLM returned nothing>")
    elif raw == "":
        p("\n  RAW LLM RESPONSE: <empty string>")
    else:
        p(f"\n  RAW LLM RESPONSE ({len(raw):,} chars, first 800):")
        p("  " + "-" * 56)
        preview = raw[:800].encode("ascii", errors="replace").decode("ascii")
        for line in preview.splitlines():
            p(f"    {line}")
        p("  " + "-" * 56)

    # JSON validity
    is_valid = raw_result.get("is_valid_json", False)
    p(f"\n  Is raw response valid JSON?  {'YES' if is_valid else 'NO'}")

    # Invoke error
    if raw_result.get("error"):
        p(f"  Error during invocation: {raw_result['error']}")

    # Parsed decision
    decision = raw_result.get("parsed_decision")
    if decision:
        p(f"\n  Parsed SpeakerRegistryDecision:")
        p(f"    confidence:          {decision.confidence}")
        p(f"    verified_speakers:   {len(decision.verified_speakers)}")
        p(f"    rejected_candidates: {len(decision.rejected_candidates)}")
        p(f"    merge_decisions:     {len(decision.merge_decisions)}")

        if decision.verified_speakers:
            p(f"\n    Verified speakers:")
            for vs in decision.verified_speakers:
                p(f"      - {vs.canonical_name!r}  role={vs.role}  title={vs.title!r}")
                p(f"        aliases={vs.aliases}")
                just = (vs.justification or "")[:120].encode("ascii", errors="replace").decode("ascii")
                p(f"        justification: {just}")

        if decision.rejected_candidates:
            p(f"\n    Rejected candidates:")
            for rc in decision.rejected_candidates:
                p(f"      - {rc.get('name', '?')!r}  reason={rc.get('reason', '?')!r}")

        if decision.merge_decisions:
            p(f"\n    Merge decisions:")
            for md in decision.merge_decisions:
                p(f"      - {md.get('merged', [])} -> {md.get('into', '?')!r}  reason={md.get('reason', '?')!r}")
    else:
        p("\n  [FAIL] No parsed decision returned (fallback path was triggered)")


# ---------------------------------------------------------------------------
# Section 4: Full pipeline stage with LLM + diff vs stored
# ---------------------------------------------------------------------------

def run_full_stage(run_data: dict) -> tuple:
    """Call build_speaker_registry(use_llm=True) and return (registry, trace)."""
    from src.pipeline_v2.stages.speakers import build_speaker_registry

    boundary = run_data.get("boundary")
    if not boundary:
        p("  [SKIP] No boundary result")
        return None, None

    p("  Calling build_speaker_registry(use_llm=True) ...")
    registry, trace = build_speaker_registry(
        boundary_result=boundary,
        metadata=run_data.get("metadata_stage"),
        full_text=run_data.get("full_text") or "",
        use_llm=True,
    )
    return registry, trace


def print_full_stage_diff(registry, trace, stored_raw: dict) -> None:
    """Print new registry and diff against stored result."""
    from src.pipeline_v2.models import SpeakerRole

    if not registry:
        p("  [N/A] No registry returned")
        return

    # New result summary
    p(f"\n  NEW result:    total={registry.total_speakers}  "
      f"management={registry.management_count}  "
      f"analysts={registry.analyst_count}")
    p(f"  LLM calls:     {trace.llm_calls_made}")
    p(f"  Verified by LLM:  {trace.speakers_verified_by_llm}")
    p(f"  Rejected by LLM:  {trace.speakers_rejected_by_llm}")

    # Fallback path detection
    fallback_triggered = any(
        "LLM failed" in (vr.reasoning or "") or "heuristic" in (vr.reasoning or "").lower()
        for vr in trace.verification_decisions
    )
    if fallback_triggered:
        p("\n  [WARN] Fallback path was triggered (LLM failed / parse failed)")
    else:
        p("\n  [OK] LLM path appears to have been used (no fallback signal)")

    # New speaker list
    p(f"\n  New speaker list:")
    for sid, sp in registry.speakers.items():
        role_str = sp.role.value if hasattr(sp.role, "value") else str(sp.role)
        p(f"    {sid}: {sp.canonical_name!r}  role={role_str}  title={sp.title!r}")

    # Stored result for comparison
    stored_speakers = stored_raw.get("speakers", {})
    p(f"\n  STORED result: total={stored_raw.get('total_speakers', '?')}  "
      f"management={stored_raw.get('management_count', '?')}  "
      f"analysts={stored_raw.get('analyst_count', '?')}")

    p(f"\n  Stored speaker list:")
    for sid, sp in stored_speakers.items():
        role_str = sp.get("role", "?")
        p(f"    {sid}: {sp.get('canonical_name', '?')!r}  role={role_str}  title={sp.get('title', None)!r}")

    # Diff
    new_names = {sp.canonical_name.lower() for sp in registry.speakers.values()}
    stored_names = {
        sp.get("canonical_name", "").lower()
        for sp in stored_speakers.values()
    }

    added = new_names - stored_names
    removed = stored_names - new_names

    if added:
        p(f"\n  ADDED in new run:")
        for n in sorted(added):
            p(f"    + {n!r}")
    if removed:
        p(f"\n  MISSING from new run (were in stored):")
        for n in sorted(removed):
            p(f"    - {n!r}")
    if not added and not removed:
        p(f"\n  [=] Speaker lists match exactly")

    # Role diff
    new_roles = {sp.canonical_name.lower(): sp.role.value
                 if hasattr(sp.role, "value") else str(sp.role)
                 for sp in registry.speakers.values()}
    stored_roles = {
        sp.get("canonical_name", "").lower(): sp.get("role", "unknown")
        for sp in stored_speakers.values()
    }

    role_changes = []
    for name in new_names & stored_names:
        nr = new_roles.get(name, "?")
        sr = stored_roles.get(name, "?")
        if nr != sr:
            role_changes.append((name, sr, nr))

    if role_changes:
        p(f"\n  Role changes:")
        for name, old, new in role_changes:
            p(f"    {name!r}: {old} -> {new}")
    else:
        p(f"\n  [=] All shared roles match")


# ---------------------------------------------------------------------------
# Section 5: Summary diagnosis
# ---------------------------------------------------------------------------

def print_summary(
    run_id: str,
    phase_a_registry,
    phase_a_trace,
    raw_llm_result: dict,
    full_registry,
    full_trace,
) -> None:
    """Print a clear per-run verdict."""
    from src.pipeline_v2.models import SpeakerRole

    p("")
    hdr(f"DIAGNOSIS SUMMARY: {run_id}")

    # 1. Junk through Phase A?
    if phase_a_trace:
        JUNK_PATTERNS = [
            r"^\d",
            r"^(mumbai|delhi|bangalore|pune|hyderabad|chennai|kolkata)$",
            r"^(january|february|march|april|may|june|july|august|september|october|november|december)$",
            r"^(monday|tuesday|wednesday|thursday|friday|saturday|sunday)$",
            r"^(scrip|isin|cin|nse|bse|pan)\b",
            r"^(so|the|a|an|in|of|on|at|by|for)$",
            r"[0-9]{4,}",
            r"^[A-Z0-9]{4,}$",
        ]
        passed = [c for c in phase_a_trace.candidates_generated if c.is_valid]
        junk = [c for c in passed if any(
            re.search(pat, c.normalized_name.strip(), re.IGNORECASE)
            for pat in JUNK_PATTERNS
        )]
        if junk:
            p(f"  [FAIL] Phase A junk survivors: {[c.normalized_name for c in junk]}")
        else:
            p(f"  [OK]   Phase A: no obvious junk passed ({len(passed)} valid candidates)")
    else:
        p("  [N/A] Phase A not run")

    # 2. LLM call succeeded?
    raw_resp = raw_llm_result.get("raw_response")
    is_json = raw_llm_result.get("is_valid_json", False)
    decision = raw_llm_result.get("parsed_decision")

    if raw_resp is None or raw_resp == "":
        p("  [FAIL] LLM returned EMPTY response (root cause: model returned nothing)")
    elif not is_json:
        p("  [FAIL] LLM response is NOT valid JSON (root cause: parse failure)")
        snippet = (raw_resp or "")[:120].encode("ascii", errors="replace").decode("ascii")
        p(f"         First 120 chars: {snippet!r}")
    else:
        p("  [OK]   LLM returned valid JSON")

    # 3. Merges happened?
    if decision:
        merge_count = len(decision.merge_decisions)
        if merge_count == 0:
            p("  [WARN] LLM made ZERO merge decisions (duplicates may persist)")
        else:
            p(f"  [OK]   LLM made {merge_count} merge decision(s)")
    else:
        p("  [N/A] No LLM decision parsed")

    # 4. Roles assigned?
    if decision and decision.verified_speakers:
        mgmt = sum(1 for vs in decision.verified_speakers if vs.role == "management")
        analyst = sum(1 for vs in decision.verified_speakers if vs.role == "analyst")
        unknown = sum(1 for vs in decision.verified_speakers if vs.role == "unknown")
        p(f"  [INFO] LLM role assignment: management={mgmt}  analyst={analyst}  unknown={unknown}")
        if mgmt == 0 and analyst == 0:
            p("  [FAIL] LLM assigned NO management or analyst roles")
        else:
            p("  [OK]   LLM assigned non-zero management/analyst roles")
    elif full_registry:
        mgmt = full_registry.management_count
        analyst = full_registry.analyst_count
        p(f"  [INFO] Final registry: management={mgmt}  analyst={analyst}")
        if mgmt == 0 and analyst == 0:
            p("  [FAIL] Final registry has NO management or analyst roles")
    else:
        p("  [N/A] No role data")

    # 5. Fallback path triggered?
    if full_trace:
        fallback = any(
            "LLM failed" in (vr.reasoning or "") or "heuristic" in (vr.reasoning or "").lower()
            for vr in full_trace.verification_decisions
        )
        if fallback:
            p("  [FAIL] Fallback path was triggered (LLM output unusable)")
        else:
            p("  [OK]   Fallback path NOT triggered (LLM output used)")
    else:
        p("  [N/A] Full trace not available")

    # Root cause verdict — prioritise Section 4 (full pipeline) result
    p("")
    p("  ROOT CAUSE VERDICT:")
    # Check if Section 4 succeeded (fallback NOT triggered + roles assigned)
    sec4_ok = False
    if full_trace and full_registry:
        fallback_triggered = any(
            "LLM failed" in (vr.reasoning or "") or "heuristic" in (vr.reasoning or "").lower()
            for vr in full_trace.verification_decisions
        )
        if not fallback_triggered and (full_registry.management_count > 0 or full_registry.analyst_count > 0):
            sec4_ok = True

    if sec4_ok:
        p("  -> [PASS] Full pipeline (Section 4) works correctly. Speaker roles assigned.")
    elif raw_resp is None or raw_resp == "":
        p("  -> LLM returned empty response. Check Ollama is running and model loaded.")
        p("     Try: curl http://localhost:11434/api/tags")
    elif not is_json:
        p("  -> LLM output is not JSON. Prompt engineering fix needed.")
        p("     The model may be returning markdown fences or plain text instead of JSON.")
    elif decision and len(decision.verified_speakers) == 0:
        p("  -> LLM returned valid JSON but verified ZERO speakers.")
        p("     Likely over-aggressive rejection rules in the prompt.")
    else:
        p("  -> LLM appears functional. Check hard-rule enforcement or fallback logic.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

TARGET_RUNS = ["e3235886-265", "b38cee51-6c4"]


def run_diagnostics_for(run_id: str) -> None:
    """Run all 5 diagnostic sections for one run."""
    hdr(f"RUN: {run_id}")

    # --- Section 1: Load data ---
    hdr("SECTION 1: Load Run Data", char="-", width=60)
    try:
        run_data = load_run_data(run_id)
    except FileNotFoundError as exc:
        p(f"  [ERROR] {exc}")
        return

    # --- Section 2: Phase A ---
    hdr("SECTION 2: Phase A - Deterministic Candidate Generation (use_llm=False)", char="-", width=60)
    phase_a_registry, phase_a_trace = run_phase_a(run_data)
    print_phase_a_results(phase_a_registry, phase_a_trace)

    # --- Section 3: Raw LLM call ---
    hdr("SECTION 3: Raw LLM Call in Isolation", char="-", width=60)
    raw_llm_result = run_raw_llm_call(run_data)
    print_raw_llm_results(raw_llm_result)

    # --- Section 4: Full pipeline stage ---
    hdr("SECTION 4: Full Pipeline Stage (use_llm=True) vs Stored", char="-", width=60)
    full_registry, full_trace = run_full_stage(run_data)
    print_full_stage_diff(full_registry, full_trace, run_data.get("speakers_stored", {}))

    # --- Section 5: Summary ---
    print_summary(run_id, phase_a_registry, phase_a_trace, raw_llm_result, full_registry, full_trace)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Speaker detection diagnostics")
    parser.add_argument(
        "--run-id",
        nargs="+",
        default=TARGET_RUNS,
        help="Run ID(s) to diagnose (partial match supported). Default: both failing runs.",
    )
    args = parser.parse_args()

    hdr("SPEAKER DETECTION DIAGNOSTICS", char="=", width=72)
    p(f"Testing {len(args.run_id)} run(s): {', '.join(args.run_id)}")
    p("")

    for rid in args.run_id:
        run_diagnostics_for(rid)
        p("")


if __name__ == "__main__":
    main()
