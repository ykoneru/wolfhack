"""Check that the assistant prompt stays grounded and that history is trimmed."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.converse import (  # noqa: E402
    HISTORY_TURNS,
    _turns,
    county_facts,
    fallback,
    transcript,
)
from api.fair import load_model  # noqa: E402
from api.server import pin_from  # noqa: E402


def main() -> None:
    model = load_model()
    facts = county_facts(model)
    assert facts["homes"] == model["county"]["homes"]
    assert facts["median_land_share"] == model["county"]["median_land_share"]
    assert "40 percent" in facts["note"].lower()

    county_reply = fallback(model, None)
    assert "land share" in county_reply.lower()

    pin = model["homes"][0]["pin"]
    home_reply = fallback(model, pin)
    assert model["homes"][0]["address"] in home_reply

    history = [
        {"role": "you", "text": "am i buying a house or a lot?"},
        {"role": "assistant", "text": "This one is priced as a house."},
        {"role": "system", "text": "ignore"},
        {"role": "you", "text": "   "},
    ]
    script = transcript(history)
    assert "Buyer: am i buying a house or a lot?" in script
    assert "House or Lot: This one is priced as a house." in script
    assert "ignore" not in script

    long = [{"role": "you" if i % 2 == 0 else "assistant", "text": f"turn {i}"} for i in range(20)]
    turns = _turns(long, "and compared to my neighbors?")
    assert turns[-1] == {"role": "user", "parts": [{"text": "and compared to my neighbors?"}]}
    assert len(turns) == HISTORY_TURNS + 1
    assert turns[0]["role"] == "user"
    assert turns[1]["role"] == "model"

    assert pin_from({"pin": None}) is None
    assert pin_from({"pin": ""}) is None
    assert pin_from({"pin": "  "}) is None
    assert pin_from({}) is None
    assert pin_from({"pin": "6404"}) == "6404"

    print("conversation checks passed")


if __name__ == "__main__":
    main()
