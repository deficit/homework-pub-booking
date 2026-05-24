"""Ex5 tools. Four tools the agent uses to research an Edinburgh booking.

Each tool:
  1. Reads its fixture from sample_data/ (DO NOT modify the fixtures).
  2. Logs its arguments and output into _TOOL_CALL_LOG (see integrity.py).
  3. Returns a ToolResult with success=True/False, output=dict, summary=str.

The grader checks for:
  * Correct parallel_safe flags (reads True, generate_flyer False).
  * Every tool's results appear in _TOOL_CALL_LOG.
  * Tools fail gracefully on missing fixtures or bad inputs (ToolError,
    not RuntimeError).
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

from sovereign_agent.errors import ToolError
from sovereign_agent.session.directory import Session
from sovereign_agent.tools.registry import ToolRegistry, ToolResult, _RegisteredTool

from .integrity import _TOOL_CALL_LOG, record_tool_call

_SAMPLE_DATA = Path(__file__).parent / "sample_data"


# ---------------------------------------------------------------------------
# TODO 1 — venue_search
# ---------------------------------------------------------------------------
def venue_search(near: str, party_size: int, budget_max_gbp: int = 1000) -> ToolResult:
    """Search for Edinburgh venues near <near> that can seat the party.

    Reads sample_data/venues.json. Filters by:
      * open_now == True
      * area contains <near> (case-insensitive substring match)
      * seats_available_evening >= party_size
      * hire_fee_gbp + min_spend_gbp <= budget_max_gbp

    Returns a ToolResult with:
      output: {"near": ..., "party_size": ..., "results": [<venue dicts>], "count": int}
      summary: "venue_search(<near>, party=<N>): <count> result(s)"

    MUST call record_tool_call(...) before returning so the integrity
    check can see what data was produced.
    """
    try:
        with open(_SAMPLE_DATA / "venues.json") as f:
            venues = json.load(f)
    except FileNotFoundError as e:
        raise ToolError("SA_TOOL_DEPENDENCY_MISSING", "venues.json missing") from e

    call_count = len([r for r in _TOOL_CALL_LOG if r.tool_name == "venue_search"])

    results = []
    for v in venues:
        if v.get("open_now") and near.lower() in v.get("area", "").lower():
            if v.get("seats_available_evening", 0) >= party_size:
                if v.get("hire_fee_gbp", 0) + v.get("min_spend_gbp", 0) <= budget_max_gbp:
                    results.append(v)

    output = {"near": near, "party_size": party_size, "results": results, "count": len(results)}
    record_tool_call(
        "venue_search",
        {"near": near, "party_size": party_size, "budget_max_gbp": budget_max_gbp},
        output,
    )

    summary = f"venue_search({near}, party={party_size}): {len(results)} result(s)"

    if call_count > 3:
        return ToolResult(
            success=False,
            output={"error": "too_many_searches", "count": call_count},
            summary="STOP calling venue_search; use the results you already have.",
        )

    return ToolResult(success=True, output=output, summary=summary)


# ---------------------------------------------------------------------------
# TODO 2 — get_weather
# ---------------------------------------------------------------------------
def get_weather(city: str, date: str) -> ToolResult:
    """Look up the scripted weather for <city> on <date> (YYYY-MM-DD).

    Reads sample_data/weather.json. Returns:
      output: {"city": str, "date": str, "condition": str, "temperature_c": int, ...}
      summary: "get_weather(<city>, <date>): <condition>, <temp>C"

    If the city or date is not in the fixture, return success=False with
    a clear ToolError (SA_TOOL_INVALID_INPUT). Do NOT raise.

    MUST call record_tool_call(...) before returning.
    """
    try:
        with open(_SAMPLE_DATA / "weather.json") as f:
            weather = json.load(f)
    except FileNotFoundError as e:
        raise ToolError("SA_TOOL_DEPENDENCY_MISSING", "weather.json missing") from e

    city_data = weather.get(city.lower())
    if not city_data:
        return ToolResult(
            success=False,
            output={},
            summary=f"ToolError: SA_TOOL_INVALID_INPUT, city {city} not found",
        )

    date_data = city_data.get(date)
    if not date_data:
        return ToolResult(
            success=False,
            output={},
            summary=f"ToolError: SA_TOOL_INVALID_INPUT, date {date} not found",
        )

    output = {"city": city, "date": date, **date_data}
    record_tool_call("get_weather", {"city": city, "date": date}, output)

    condition = date_data.get("condition")
    temp = date_data.get("temperature_c")
    summary = f"get_weather({city}, {date}): {condition}, {temp}C"

    return ToolResult(success=True, output=output, summary=summary)


# ---------------------------------------------------------------------------
# TODO 3 — calculate_cost
# ---------------------------------------------------------------------------
def calculate_cost(
    venue_id: str,
    party_size: int,
    duration_hours: int,
    catering_tier: str = "bar_snacks",
) -> ToolResult:
    """Compute the total cost for a booking.

    Formula:
      base_per_head = base_rates_gbp_per_head[catering_tier]
      venue_mult    = venue_modifiers[venue_id]
      subtotal      = base_per_head * venue_mult * party_size * max(1, duration_hours)
      service       = subtotal * service_charge_percent / 100
      total         = subtotal + service + <venue's hire_fee_gbp + min_spend_gbp>
      deposit_rule  = per deposit_policy thresholds

    Returns:
      output: {
        "venue_id": str,
        "party_size": int,
        "duration_hours": int,
        "catering_tier": str,
        "subtotal_gbp": int,
        "service_gbp": int,
        "total_gbp": int,
        "deposit_required_gbp": int,
      }
      summary: "calculate_cost(<venue>, <party>): total £<N>, deposit £<M>"

    MUST call record_tool_call(...) before returning.
    """
    try:
        with open(_SAMPLE_DATA / "catering.json") as f:
            catering = json.load(f)
        with open(_SAMPLE_DATA / "venues.json") as f:
            venues = json.load(f)
    except FileNotFoundError as e:
        raise ToolError("SA_TOOL_DEPENDENCY_MISSING", "catering.json or venues.json missing") from e

    base_rates = catering["base_rates_gbp_per_head"]
    venue_modifiers = catering["venue_modifiers"]

    venue = next((v for v in venues if v["id"] == venue_id), None)
    if not venue:
        return ToolResult(
            success=False,
            output={},
            summary=f"ToolError: SA_TOOL_INVALID_INPUT, venue {venue_id} not found",
        )

    base_per_head = base_rates.get(catering_tier, 0)
    venue_mult = venue_modifiers.get(venue_id, 1.0)
    subtotal = base_per_head * venue_mult * party_size * max(1, duration_hours)
    service = subtotal * catering["service_charge_percent"] / 100
    total = max(subtotal, venue.get("min_spend_gbp", 0)) + service + venue.get("hire_fee_gbp", 0)
    total = round(total)

    if total < 300:
        deposit = 0
    elif total <= 1000:
        deposit = round(total * 0.20)
    else:
        deposit = round(total * 0.30)

    output = {
        "venue_id": venue_id,
        "party_size": party_size,
        "duration_hours": duration_hours,
        "catering_tier": catering_tier,
        "subtotal_gbp": round(subtotal),
        "service_gbp": round(service),
        "total_gbp": total,
        "deposit_required_gbp": deposit,
    }

    record_tool_call(
        "calculate_cost",
        {
            "venue_id": venue_id,
            "party_size": party_size,
            "duration_hours": duration_hours,
            "catering_tier": catering_tier,
        },
        output,
    )

    summary = f"calculate_cost({venue_id}, {party_size}): total £{total}, deposit £{deposit}"
    return ToolResult(success=True, output=output, summary=summary)


# ---------------------------------------------------------------------------
# TODO 4 — generate_flyer
# ---------------------------------------------------------------------------
def generate_flyer(session: Session, event_details: dict) -> ToolResult:
    """Produce an HTML flyer and write it to workspace/flyer.html.

    event_details is expected to contain at least:
      venue_name, venue_address, date, time, party_size, condition,
      temperature_c, total_gbp, deposit_required_gbp

    Write a self-contained HTML flyer (inline CSS, no external assets). Tag every key fact with data-testid="<n>" so the integrity check can parse it.

    Write a formatted HTML flyer with an H1 title, the event
    facts, a weather summary, and the cost breakdown.

    Returns:
      output: {"path": "workspace/flyer.html", "bytes_written": int}
      summary: "generate_flyer: wrote <path> (<N> chars)"

    MUST call record_tool_call(...) before returning — the integrity
    check compares the flyer's contents against earlier tool outputs.

    IMPORTANT: this tool MUST be registered with parallel_safe=False
    because it writes a file.
    """
    html = f"""<!DOCTYPE html>
<html>
<head>
<style>
body {{ font-family: sans-serif; }}
</style>
</head>
<body>
<h1>Event Flyer</h1>
<p>Venue: <span data-testid="venue_name">{event_details.get("venue_name")}</span></p>
<p>Address: <span data-testid="venue_address">{event_details.get("venue_address")}</span></p>
<p>Date: <span data-testid="date">{event_details.get("date")}</span></p>
<p>Time: <span data-testid="time">{event_details.get("time")}</span></p>
<p>Party Size: <span data-testid="party_size">{event_details.get("party_size")}</span></p>
<p>Weather: <span data-testid="condition">{event_details.get("condition")}</span>, <span data-testid="temperature_c">{event_details.get("temperature_c")}</span>°C</p>
<p>Total Cost: £<span data-testid="total_gbp">{event_details.get("total_gbp")}</span></p>
<p>Deposit Required: £<span data-testid="deposit_required_gbp">{event_details.get("deposit_required_gbp")}</span></p>
</body>
</html>
"""
    flyer_path = session.workspace_dir / "flyer.html"
    flyer_path.write_text(html, encoding="utf-8")

    output = {"path": "workspace/flyer.html", "bytes_written": len(html)}
    record_tool_call("generate_flyer", {"event_details": event_details}, output)

    summary = f"generate_flyer: wrote workspace/flyer.html ({len(html)} chars)"
    return ToolResult(success=True, output=output, summary=summary)


# ---------------------------------------------------------------------------
# Registry builder — DO NOT MODIFY the name, signature, or registration calls.
# The grader imports and calls this to pick up your tools.
# ---------------------------------------------------------------------------
def build_tool_registry(session: Session) -> ToolRegistry:
    """Build a session-scoped tool registry with all four Ex5 tools plus
    the sovereign-agent builtins (read_file, write_file, list_files,
    handoff_to_structured, complete_task).

    DO NOT change the tool names — the tests and grader call them by name.
    """
    from sovereign_agent.tools.builtin import make_builtin_registry

    reg = make_builtin_registry(session)

    # venue_search
    reg.register(
        _RegisteredTool(
            name="venue_search",
            description=inspect.getdoc(venue_search)
            or "Search Edinburgh venues by area, party size, and max budget.",
            fn=venue_search,
            parameters_schema={
                "type": "object",
                "properties": {
                    "near": {"type": "string"},
                    "party_size": {"type": "integer"},
                    "budget_max_gbp": {"type": "integer", "default": 1000},
                },
                "required": ["near", "party_size"],
            },
            returns_schema={"type": "object"},
            is_async=False,
            parallel_safe=True,  # read-only
            examples=[
                {
                    "input": {"near": "Haymarket", "party_size": 6, "budget_max_gbp": 800},
                    "output": {"count": 1, "results": [{"id": "haymarket_tap"}]},
                }
            ],
        )
    )

    # get_weather
    reg.register(
        _RegisteredTool(
            name="get_weather",
            description=inspect.getdoc(get_weather)
            or "Get scripted weather for a city on a YYYY-MM-DD date.",
            fn=get_weather,
            parameters_schema={
                "type": "object",
                "properties": {
                    "city": {"type": "string"},
                    "date": {"type": "string"},
                },
                "required": ["city", "date"],
            },
            returns_schema={"type": "object"},
            is_async=False,
            parallel_safe=True,  # read-only
            examples=[
                {
                    "input": {"city": "Edinburgh", "date": "2026-04-25"},
                    "output": {"condition": "cloudy", "temperature_c": 12},
                }
            ],
        )
    )

    # calculate_cost
    reg.register(
        _RegisteredTool(
            name="calculate_cost",
            description=inspect.getdoc(calculate_cost)
            or "Compute total cost and deposit for a booking.",
            fn=calculate_cost,
            parameters_schema={
                "type": "object",
                "properties": {
                    "venue_id": {"type": "string"},
                    "party_size": {"type": "integer"},
                    "duration_hours": {"type": "integer"},
                    "catering_tier": {
                        "type": "string",
                        "enum": ["drinks_only", "bar_snacks", "sit_down_meal", "three_course_meal"],
                        "default": "bar_snacks",
                    },
                },
                "required": ["venue_id", "party_size", "duration_hours"],
            },
            returns_schema={"type": "object"},
            is_async=False,
            parallel_safe=True,  # pure compute, no shared state
            examples=[
                {
                    "input": {
                        "venue_id": "haymarket_tap",
                        "party_size": 6,
                        "duration_hours": 3,
                    },
                    "output": {"total_gbp": 540, "deposit_required_gbp": 0},
                }
            ],
        )
    )

    # generate_flyer — parallel_safe=False because it writes a file
    def _flyer_adapter(event_details: dict) -> ToolResult:
        return generate_flyer(session, event_details)

    reg.register(
        _RegisteredTool(
            name="generate_flyer",
            description=inspect.getdoc(generate_flyer)
            or "Write an HTML flyer for the event to workspace/flyer.html.",
            fn=_flyer_adapter,
            parameters_schema={
                "type": "object",
                "properties": {"event_details": {"type": "object"}},
                "required": ["event_details"],
            },
            returns_schema={"type": "object"},
            is_async=False,
            parallel_safe=False,  # writes a file — MUST be False
            examples=[
                {
                    "input": {
                        "event_details": {
                            "venue_name": "Haymarket Tap",
                            "date": "2026-04-25",
                            "party_size": 6,
                        }
                    },
                    "output": {"path": "workspace/flyer.html"},
                }
            ],
        )
    )

    return reg


__all__ = [
    "build_tool_registry",
    "venue_search",
    "get_weather",
    "calculate_cost",
    "generate_flyer",
]
