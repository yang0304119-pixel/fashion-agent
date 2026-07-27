"""Agent目标授权策略：在执行工具或业务节点前做系统级能力判定。"""

from dataclasses import dataclass
import re


READ_ONLY_INTENTS = frozenset({
    "knowledge_query",
    "product_query",
    "order_query",
    "refund_status_query",
    "inventory_query",
    "size_recommend",
    "composite_query",
})

FORBIDDEN_GOAL_PATTERNS = (
    r"(?:删除|清空|抹掉).{0,10}(?:所有|全部|全量).{0,10}(?:订单|用户|商品|库存|数据库|数据)",
    r"(?:所有|全部|全量).{0,10}(?:订单|用户|商品|库存|数据库|数据).{0,10}(?:删除|清空|抹掉)",
    r"(?:批量|全部|所有).{0,8}(?:退款|转账|付款|打款)",
    r"(?:绕过|跳过|关闭).{0,8}(?:权限|鉴权|审批|风控|验证)",
    r"(?:伪造|冒充|扮演).{0,8}(?:管理员|其他用户|系统)",
    r"(?:导出|泄露|发送).{0,10}(?:所有用户|全部用户|密码|token|密钥|银行卡)",
    r"(?:执行|运行).{0,8}(?:shell|命令行|系统命令|脚本)",
    r"(?:群发|批量发送).{0,8}(?:邮件|短信|通知)",
)


@dataclass(frozen=True)
class GoalBoundaryDecision:
    status: str
    action_class: str
    risk_level: str
    reason: str
    approval_required: bool = False
    blocked: bool = False


def evaluate_goal(*, message: str, intent: str) -> GoalBoundaryDecision:
    """目标边界采用默认拒绝：不在客服授权能力内的高风险目标转人工。"""
    normalized = " ".join(str(message or "").strip().lower().split())
    if any(re.search(pattern, normalized, flags=re.IGNORECASE) for pattern in FORBIDDEN_GOAL_PATTERNS):
        return GoalBoundaryDecision(
            status="blocked",
            action_class="forbidden_high_risk_action",
            risk_level="critical",
            reason="目标超出客服Agent授权范围，禁止自动执行",
            approval_required=True,
            blocked=True,
        )
    if intent == "refund_request":
        return GoalBoundaryDecision(
            status="allowed_deterministic",
            action_class="financial_workflow",
            risk_level="high",
            reason="退款只能进入服务端确定性工作流",
        )
    if intent in {"after_sales_request", "human_handoff"}:
        return GoalBoundaryDecision(
            status="approval_required",
            action_class="business_write_or_handoff",
            risk_level="high",
            reason="业务写操作必须由人工核实和审批",
            approval_required=True,
        )
    if intent in READ_ONLY_INTENTS:
        return GoalBoundaryDecision(
            status="allowed",
            action_class="read_only",
            risk_level="low",
            reason="目标属于授权的只读客服能力",
        )
    return GoalBoundaryDecision(
        status="allowed_noop",
        action_class="conversation_only",
        risk_level="low",
        reason="仅允许回复或澄清，不执行外部写操作",
    )
