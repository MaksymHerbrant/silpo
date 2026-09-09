from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.llm import explain
from app.mcp.gateway import McpNotConnected, McpToolForbidden
from app.security.session import current_user_id
from app.services import cart_analysis

router = APIRouter(tags=["cart"])


@router.get("/cart/analysis")
async def get_cart_analysis(explain_text: bool = True, user_id: str = Depends(current_user_id)) -> dict:
    try:
        analysis = await cart_analysis.analyze_cart(user_id)
    except McpNotConnected as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except McpToolForbidden as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc

    if explain_text and not analysis.get("empty"):
        analysis["summary_text"] = await explain.summarize_cart(analysis)
    return analysis


@router.get("/cart/allergens")
async def get_allergens(user_id: str = Depends(current_user_id)) -> dict:
    analysis = await cart_analysis.analyze_cart(user_id)
    return {
        "restrictions": analysis.get("restrictions", []),
        "warnings": analysis.get("allergen_warnings", []),
    }
