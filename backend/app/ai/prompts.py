"""One focused prompt per stage.

Deliberate rule from the spec: a stage receives ONLY the approved output of prior stages, never a
running conversation. Tight context, no drift.
"""

import json
from typing import Any

from app.models.enums import StageType

SYSTEM_PROMPT = (
    "You are a senior distributed-systems architect. You design microservice architectures that "
    "are pragmatic and implementable, not academic. You avoid both extremes: a distributed "
    "monolith with one giant service, and nano-services split so finely that every user action "
    "needs six network hops. Every decision you make must be justifiable to an engineering team."
)

BOUNDARIES_INSTRUCTIONS = """\
Decompose the system below into microservices.

Rules you must follow:
- Split by business capability and data ownership, NOT by technical layer. "OrderService" is a
  service; "DatabaseService", "ControllerService" or "UtilService" are not.
- Each service owns its own data. If two services would both write the same entity, that is a sign
  the boundary is wrong.
- Aim for 4-8 services for a typical system. Only exceed that if the description genuinely demands it.
- Do not invent capabilities the description never mentions. Stay inside the described scope.
- In boundaries_rationale, be explicit about which splits were judgement calls and what the
  alternative was, so a human reviewer knows exactly what to push back on.
"""


def build_stage_prompt(
    stage_type: StageType, raw_description: str, prior_outputs: dict[str, Any]
) -> tuple[str, str]:
    """Returns (system_prompt, user_prompt) for a stage."""
    if stage_type is not StageType.BOUNDARIES:
        raise NotImplementedError(f"No prompt template for stage '{stage_type.value}' yet")

    sections = [
        BOUNDARIES_INSTRUCTIONS,
        "## System description\n" + raw_description.strip(),
    ]
    if prior_outputs:
        sections.append(
            "## Approved output of previous stages\n```json\n"
            + json.dumps(prior_outputs, indent=2)
            + "\n```"
        )
    return SYSTEM_PROMPT, "\n\n".join(sections)
