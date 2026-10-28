import pytest
from unittest.mock import AsyncMock, MagicMock
from backend.risk_assessment import assess_run

@pytest.mark.asyncio
async def test_empty_run_is_low():
    db = AsyncMock()
    scalar_result = MagicMock()
    scalar_result.all.return_value = []
    db.scalars.return_value = scalar_result
    db.scalar.return_value = None
    score, rationale = await assess_run(db, "missing")
    assert score == "LOW"
    assert "approval" in rationale
