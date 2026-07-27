# FashionAgent Agent安全边界

FashionAgent不假设模型永远正确，而是通过目标、工具、执行和人工四层边界限制模型犯错后的影响范围。

## 1. 目标边界

工作流入口先执行`goal_guard`。批量删除、批量退款、绕过权限、冒充管理员、泄露凭证、执行系统命令和群发外部消息等目标会在Router、LLM和工具调用前被阻断。

路由完成后再次执行`boundary_guard`：

- 查询类目标允许进入只读节点。
- 退款只能进入服务端确定性退款工作流。
- 换货、取消订单等写操作必须转人工。
- 未明确授权的目标只能回复或澄清，不能执行外部写操作。

边界判定会写入Trace：`boundary_status`、`boundary_action_class`、`boundary_risk_level`、`boundary_reason`和`approval_required`。

## 2. 工具边界

每个LLM工具声明：

- `action_type`：read/write/delete/payment/external；
- `risk_level`：low/medium/high/critical；
- `approval_required`；
- `trusted_fields`。

`ToolFirewall`采用默认拒绝策略，ReAct只允许低风险只读工具。写入、删除、支付、外部发送及需要审批的工具即使被错误注册或被模型选择，也会在参数校验和handler执行前阻断。

`tenant_id`和`user_id`只能由服务端可信上下文注入，不能由模型生成或覆盖。退款不注册为LLM工具。

## 3. 执行边界

执行预算由配置统一控制：

```text
AGENT_MAX_ITERATIONS=5
AGENT_MAX_TOOL_CALLS=5
AGENT_MAX_EXECUTION_SECONDS=45
AGENT_MAX_LLM_OUTPUT_TOKENS=1000
AGENT_LLM_TIMEOUT_SECONDS=20
```

ReAct每轮和每次工具调用前检查截止时间，超过预算立即停止并转人工。工具调用还包含严格参数校验、有限自修复、临时错误退避重试、最大重试次数和熔断器。

资金写操作在数据库事务中执行，异常回滚；只有退款渠道明确成功才更新订单退款状态。

## 4. 人类边界

以下情况设置`human_required=True`：

- 目标守卫阻断的越权或危险请求；
- 换货、取消订单等未开放写操作；
- 高风险退款；
- 工具鉴权、Fatal错误、熔断或预算耗尽；
- 用户主动要求人工客服。

退款使用专用`ticket`审核/异常工单。其他人工请求写入`unresolved_case`通用人工队列，并把`handoff_case_id`写入Trace，避免只回复“已转人工”但没有后台记录。

## 5. 生产边界

- 当前熔断器是进程内状态，多实例部署应迁移到Redis等共享存储。
- 当前截止时间属于协作式停止；外部HTTP、模型和数据库驱动仍必须分别配置超时。
- `AgentState`仍是TypedDict，后续可升级为运行时校验模型。
- 新增任何写工具时不能直接加入ReAct注册表，应建立独立确定性工作流、审批记录和幂等策略。
