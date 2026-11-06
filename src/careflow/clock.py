import os
from datetime import date

FROZEN_TODAY = date(2026, 11, 2)


def today() -> date:
    override = os.getenv("CAREFLOW_TODAY")
    return date.fromisoformat(override) if override else FROZEN_TODAY
