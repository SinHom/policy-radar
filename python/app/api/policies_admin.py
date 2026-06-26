"""政策库管理 API（管理后台用）。

端点：
- PATCH  /api/policies/{id}    修改政策（summary_text / summary_type / amount / deadline）
- DELETE /api/policies/{id}    删除政策（级联删 push_logs + matches）
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from python.app.api.auth import require_admin
from python.models.base import get_session
from python.models.policy import Policy

router = APIRouter(prefix="/api/policies", tags=["policies"])


class PolicyUpdate(BaseModel):
    """修改政策字段（全部可选）。"""
    summary_text: Optional[str] = None
    summary_type: Optional[str] = None
    amount: Optional[str] = None
    deadline: Optional[str] = None


@router.patch("/{policy_id}")
async def update_policy(
    policy_id: int,
    body: PolicyUpdate,
    _user: str = Depends(require_admin),
) -> dict:
    """修改政策字段。运营人员可以：
    - 修正 AI 摘要
    - 调整政策类型（补贴/贷款/税收/...）
    - 补充金额/截止日期
    """
    async with get_session() as session:
        pol = await session.get(Policy, policy_id)
        if not pol:
            raise HTTPException(status_code=404, detail="policy not found")
        if body.summary_text is not None:
            pol.summary_text = body.summary_text
        if body.summary_type is not None:
            pol.summary_type = body.summary_type
        if body.amount is not None:
            pol.amount = body.amount or None
        if body.deadline is not None:
            pol.deadline = body.deadline or None
        await session.commit()
    return {"ok": True, "policy_id": policy_id}


@router.delete("/{policy_id}")
async def delete_policy(policy_id: int, _user: str = Depends(require_admin)) -> dict:
    """删除政策。关联 push_logs 和 matches 走 DB CASCADE。"""
    async with get_session() as session:
        pol = await session.get(Policy, policy_id)
        if not pol:
            raise HTTPException(status_code=404, detail="policy not found")
        await session.delete(pol)
        await session.commit()
    return {"ok": True, "policy_id": policy_id, "deleted": True}
