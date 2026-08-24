# 第一次使用：在 ChatGPT App 中以 eduK12 为例运行本地 Git 工作流

本指南假设你第一次使用 ChatGPT/Codex App。默认流程只使用 ChatGPT 订阅、本地项目目录、
本地 Git、项目验证命令和 App 原生子代理；不需要 OpenAI API key、GitHub、`gh` 或 GitHub
Actions。GitHub 发布是后续可选项。

## 1. 先理解完成标准

一次任务的固定角色是：

```text
你提出需求
  -> Sol 主任务制定 Task Contract
  -> Luna 子代理在本地 feature branch 实现并 commit
  -> 本地 checkpoint 重跑项目验证并记录 base/head SHA 与 diff
  -> Sol 审查真实证据
  -> 最多进行配置数量的 Luna 修复循环
  -> INTEGRATION_READY
  -> 停止，等待你决定如何合并
```

`INTEGRATION_READY` 不代表已经 merge、push 或部署。自动化没有 merge 方法。

## 2. 准备 App 和本地仓库

1. 安装并登录 ChatGPT/Codex 桌面 App。ChatGPT Plus 与 OpenAI API 是两套独立计费；本指南
   使用登录后的 App 额度，不填写、复制或伪造 API key。
2. 确认本机已有 Git 和项目自己的运行环境（例如 Node、Python、Docker、数据库）。
3. 确认 eduK12 本地目录是 Git worktree，并且计划作为集成基线的本地分支（例如 `dev`）
   已经更新到你认可的版本。
4. 提交、暂存或妥善保存已有改动。创建任务分支前，checkpoint 要求工作树干净。

本地模式不自动 fetch。这样可以避免在没有 GitHub、离线或额度耗尽时发生隐式网络操作；
代价是你必须在开始任务前自行确认本地基线正确。

## 3. 安装项目内工作流

在 `codex-auto` 的隔离运行环境中对 eduK12 执行初始化。下面的模型 ID、基线分支和验证命令
必须按当前 App 可用模型及 eduK12 的真实脚本填写：

```text
codex-auto init-project
  --repo-path /Users/Qiang/Documents/eduK12-dev
  --repository eduk12-local
  --base-branch dev
  --production-branch main
  --sol-model <配置的 Sol 模型 ID>
  --luna-model <配置的 Luna 模型 ID>
  --verification "lint=npm run lint"
  --verification "typecheck=npm run typecheck"
  --verification "unit=npm run test"
  --verification "integration=<项目内严格集成测试命令>"
  --max-fix-cycles 2
  --execution-mode chatgpt-app
```

不要添加 `--github-repository`，即为完全本地模式。命令会生成：

```text
AGENTS.md
.agents/skills/codex-auto/
.codex/config.toml
.codex/agents/luna-implementer.toml
.codex-auto/project.yml
.codex-auto/orchestrator.yml
.codex-auto/bin/codex-auto
```

如果根目录已有 `AGENTS.md`，初始化只追加带标记的 codex-auto 区块，不删除原有规则。初始化
遇到已有受管文件内容不同会停止；先 review 差异，确认后才使用 `--force`。

## 4. 配置验证命令

打开 `.codex-auto/orchestrator.yml`，重点确认：

```yaml
repository:
  identifier: eduk12-local
  base_branch: dev
  feature_branch_prefix: codex-auto/
  verification_commands:
    lint: [npm, run, lint]
    typecheck: [npm, run, typecheck]
    unit: [npm, run, test]
    integration: [项目内严格命令的参数数组]

github: null
```

命令按参数数组直接执行，不经过 shell。不要在配置中写密钥；需要数据库等环境变量时，使用
项目原有的安全本地环境加载方式。

“测试命令退出 0，但关键集成测试被 skip”不算完整证据。eduK12 应提供一个项目内 wrapper，
当数据库/浏览器/服务未启动或必需用例被跳过时退出非 0。否则通用 checkpoint 无法从任意测试
框架的输出文本可靠判断哪些 skip 是允许的。

## 5. 配置并核对 Sol/Luna

打开 `.codex/config.toml`，确认主模型与默认子代理模型：

```toml
model = "<Sol 模型 ID>"
model_reasoning_effort = "high"

[agents]
enabled = true
max_concurrent_threads_per_session = 1
default_subagent_model = "<Luna 模型 ID>"
default_subagent_reasoning_effort = "max"
```

再打开 `.codex/agents/luna-implementer.toml`，确认 `name = "luna_implementer"`、模型 ID 和
effort 与 `.codex-auto/orchestrator.yml` 的 implementation/fix route 完全一致。

App 必须选择配置的 Sol 主模型，并且能创建名为 `luna_implementer` 的对应 Luna 子代理。
主模型、子代理、模型 ID 或 effort 任一无法确认，流程立即停止；不允许用 Sol 代替 Luna、继承
其他模型或静默降级。

## 6. 在 App 中打开项目

1. 在 ChatGPT/Codex App 新建本地项目任务。
2. 将 `/Users/Qiang/Documents/eduK12-dev` 选为 primary folder。
3. 确认 App 已发现根 `AGENTS.md`、`.agents/skills/codex-auto/SKILL.md` 和项目代理配置。
4. 选择配置的 Sol 主模型。
5. 先给一个只读配置探针：要求报告主模型、`luna_implementer` 名称与模型，不修改文件。
6. 任一结果不一致，停止并修正配置，不开始真实任务。

## 7. 发起一个任务

对 Sol 输入清晰需求，例如：

```text
按项目内 codex-auto 工作流实现“学生列表筛选条件持久化”。
范围仅限前端筛选状态和对应测试；不修改认证、数据库 schema、部署和工作流配置。
必须运行 lint、typecheck、unit；若触及数据访问层还必须运行 integration。
本次为 local-git 模式，不 push、不创建 PR、不调用 GitHub。
```

Sol 会在 `.codex-auto/tasks/<task-id>.yml` 写 TaskRequest，并通过本地 launcher 建立：

```text
.codex-auto/results/<task-id>/session.json
.codex-auto/results/<task-id>/packet.json
.codex-auto/audit/<task-id>.jsonl
```

这些是忽略的运行数据，不应提交。

## 8. 检查每个阶段

### Planning

Sol 读取项目、TaskRequest 和配置，生成 PlanProposal。`app-accept-plan` 会拒绝丢失的人类范围、
模型擅自添加的验证名、缺失的必需验证或无效结构。通过后 Contract 固定本地 base branch 与
40 位 base SHA。

### Implementation

`app-begin-implementation` 从固定 base SHA 创建 `codex-auto/<task-id>`。Sol 必须把 Contract
委派给一个 `luna_implementer`。Luna 只做约定范围、运行命名检查并本地 commit；local-git
模式不得 push。

### Evidence

Luna 完成后运行 `app-record-change`。checkpoint 会重跑 Contract 中的命令，并要求：

- 当前分支就是任务分支；
- 工作树干净；
- HEAD 是 Contract base SHA 的后代；
- diff 非空；
- 每个必需验证都有结果。

记录包中应能看到 `change_evidence.base_sha`、`head_sha`、`diff`、`local_verification`，且
`remote` 为 `null`。

### Review and fix

`app-begin-review` 后由 Sol 根据最新 packet 独立审查。`APPROVED` 必须覆盖全部 Acceptance
Criteria，且 head SHA 必须等于最新证据。若为 `CHANGES_REQUESTED`，运行 `app-begin-fix`，
只把 blocking findings 交给同一个角色的 Luna 修复；Luna commit 后运行 `app-record-fix`。

达到 `max_fix_cycles` 仍未通过会进入终态 `BLOCKED`，不会无限重试。

## 9. 到达 INTEGRATION_READY 后

你应人工查看：

1. Task Contract 的范围和排除项；
2. base/head SHA 与本地分支；
3. 实际 diff；
4. 每条本地验证命令、退出码与输出；
5. Sol 的 criteria 和 findings；
6. audit 中是否存在绕过、缺失检查或模型替换。

确认后由你决定 merge、rebase、cherry-pick、导出 patch，或者放弃该分支。codex-auto 不执行
这些动作。

## 10. 常见停止原因

| 现象 | 含义与处理 |
|---|---|
| primary route mismatch | App 当前 Sol 与项目配置不一致；选择正确模型后重试 |
| luna route missing/unavailable | 命名子代理不能按精确配置创建；不要用其他模型替代 |
| local base branch does not exist | 先人工建立/更新本地 `dev` 等基线分支 |
| worktree must be clean | 提交或保存现有改动；验证产生的文件也要清理或正确忽略 |
| required verification is FAIL/NOT_RUN | 修复命令/环境/代码；不能把 skip 或未运行解释为 PASS |
| change no longer descends from contract base | Git 历史已变化；停止该 session，重新规划新任务 |
| maximum fix cycles reached | 人工评估或创建新的更小 Task Contract |

## 11. 日后可选启用 GitHub

只有项目确实需要发布 PR/远程 checks 时，重新初始化并明确添加：

```text
--github-repository caohuibj/eduK12-new-version
--remote origin
--required-ci-check quality
```

此时 GitHub adapter 会验证 remote 身份、push、创建/更新 PR，并把远程 checks 加到相同的
`ChangeEvidence`。GitHub Actions 额度耗尽会阻止显式启用远程必需 checks 的流程，但不会影响
未配置 `github` section 的纯本地项目。
