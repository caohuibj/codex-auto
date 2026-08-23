# ChatGPT App 原生 Sol/Luna 编排

## 结论

ChatGPT Plus 与 OpenAI API 是不同的认证和计费系统。Plus 不会生成可供 Responses API 使用的
`OPENAI_API_KEY`。本模式因此不让 Python 服务调用模型，而让已经登录 Plus 的 ChatGPT 桌面 App
成为模型运行时：Sol 主任务负责 planning/review，App 原生 Luna 子代理负责 implementation/fix。

仓库中的 Python 程序只处理确定性工作：状态转换、Task Contract 校验、分支基线、验证命令、PR
diff/CI 证据、修复次数、审计日志和人工 merge 门禁。它不会读取或复制 ChatGPT 登录 token，也不会
把 Codex CLI、SDK 或 App Server 当作隐藏模型后端。

官方说明：Codex 包含在 ChatGPT 计划中，桌面 App 支持并行代理、skills、git 和自动化；API 使用则
单独计费。参见 [Using Codex with your ChatGPT plan](https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan)、
[ChatGPT desktop app](https://learn.chatgpt.com/docs/app) 和
[ChatGPT Plus](https://help.openai.com/en/articles/6950777-what-is-chatgpt-plus)。

## 运行边界

```text
ChatGPT desktop App
└── Sol primary task
    ├── planning -> PlanProposal
    ├── native delegation -> Luna implementation
    ├── PR/CI evidence -> Sol review
    ├── native delegation -> Luna bounded fix (0..N)
    └── MERGE_READY -> human merge only

repository-local validator
├── AppSession JSON
├── Task Contract validation
├── state transition validation
├── GitHub evidence collection
├── append-only JSONL audit
└── no model authentication or model call
```

## 结构化文件

### PlanProposal

```yaml
objective: Implement one bounded behavior with tests and no unrelated changes.
in_scope:
  - Preserve every human-requested in-scope item.
out_of_scope:
  - Preserve every human-requested exclusion.
architecture_constraints:
  - Keep existing public interfaces stable.
implementation_requirements:
  - Add the behavior and regression tests.
acceptance_criteria:
  - id: AC-01
    condition: The requested behavior works for the named scenario.
    evidence_required: Named unit test passes.
verification:
  - unit
expected_deliverables:
  - Implementation and tests in one PR.
escalation_conditions:
  - Stop on an unexpected authentication or public API change.
```

### ReviewResult

```yaml
decision: APPROVED
task_id: TASK-001
base_sha: 0000000000000000000000000000000000000000
head_sha: 1111111111111111111111111111111111111111
criteria:
  - criterion_id: AC-01
    status: PASS
    evidence: The named test and PR diff demonstrate the condition.
findings: []
merge_recommendation: Ready for human merge after repository gates are confirmed.
```

`base_sha`、`head_sha` 和 criteria 必须来自最新 packet，不能凭摘要填写。`APPROVED` 要求所有
criteria 为 `PASS`、所有合同验证通过、所有 required CI checks 成功、PR diff 非空且 merge base
仍与合同一致。

## Checkpoint 顺序

所有命令由 ChatGPT App task 在项目 terminal 中执行；它们不是模型客户端。

```text
app-start
  -> app-accept-plan
  -> app-begin-implementation
  -> [App native Luna delegation]
  -> app-record-pr
  -> app-begin-review
  -> app-submit-review
       ├─ MERGE_READY -> stop for human
       ├─ BLOCKED -> stop
       └─ CHANGES_REQUESTED
            -> app-begin-fix
            -> [App native Luna delegation]
            -> app-record-fix
            -> app-submit-review ...
```

每个 checkpoint 都持久化 `.codex-auto/results/<task-id>/session.json` 并追加
`.codex-auto/audit/<task-id>.jsonl`。这些运行态文件默认不提交 Git。

## 用量与成本

App-native 调用消耗登录账户的 ChatGPT/Codex allowance；达到计划额度后，以 App 中显示的重置、
升级或 credits 选项为准。仓库程序目前拿不到每个 App 主任务/子代理的精确 token 和美元成本，因此：

- audit 明确记录 `accounting.unavailable`；
- 结果中的 API token 列表为空；
- `estimated_cost_usd` 返回 `null`，明确表示无法生成 API 账单估算；
- 用户在 ChatGPT/Codex 的 Usage 页面查看实际 allowance/credits。

这是当前 App 模式的真实限制，不通过抓取本地 OAuth token 或非公开接口绕过。
