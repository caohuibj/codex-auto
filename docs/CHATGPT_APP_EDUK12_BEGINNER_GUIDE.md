# 第一次在 ChatGPT App 中为 eduK12 配置 Sol/Luna 自动开发

本文面向第一次使用 ChatGPT 桌面 App、Codex 和子代理的用户。完成后，你只在一个 App
任务中描述需求：Sol High 负责计划和审查，项目自带的 `luna_implementer`（Luna Max）负责实现和
修复，GitHub 保存 branch、commit、PR 和 CI 证据，最终停在人工合并门禁。

本文只把 `caohuibj/eduK12-new-version` 作为配置示例。执行操作前请确认终端当前目录确实是你自己的
eduK12 checkout；安装 codex-auto 本身不会读取或修改另一个 eduK12 目录。

## 1. 先理解认证和费用边界

- ChatGPT Plus 与 OpenAI API 是两套独立产品。这里使用已登录的 ChatGPT 桌面 App，不需要
  `OPENAI_API_KEY`，也不要复制 ChatGPT cookie、OAuth token 或其他会话凭据。
- 模型调用消耗 ChatGPT 账户的 Codex allowance/credits。项目内的 checkpoint 程序只校验状态、
  Git 和 GitHub 证据，不作为模型客户端。
- 如果误用 `codex-auto run` 或把 `execution_mode` 改成 `responses-api`，程序会要求独立 API key；
  Plus 订阅不能代替它。
- App 暂不向项目内程序提供每阶段精确 token 和美元用量。实际用量以 ChatGPT Usage 页面为准，
  audit 会明确记录 `accounting unavailable`，不会编造数字。

官方入口：[ChatGPT desktop app](https://learn.chatgpt.com/docs/app)、
[Models](https://learn.chatgpt.com/docs/models)、
[Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents)。

## 2. 准备 ChatGPT App、GitHub 和本地仓库

### 2.1 安装并登录 ChatGPT 桌面 App

1. 从 OpenAI 官方页面下载安装 ChatGPT desktop app。
2. 用拥有 Plus 和 Codex 使用权限的同一个 ChatGPT 账户登录。
3. 打开 App，确认左上角可以进入 Codex，并且新任务输入框下方能看到模型/推理强度控制。
4. 如果看不到 Codex、Sol 或 Luna，先更新 App，再检查账户的 Usage/plan 状态。不要先换成相似模型。

### 2.2 准备本机工具

需要安装：

- Git；
- GitHub CLI `gh`，并完成 `gh auth login`；
- `uv`；
- Python 3.11 或更高版本。

在终端检查：

```bash
git --version
gh auth status
uv --version
python3 --version
```

### 2.3 准备 eduK12 checkout

以下示例假设本地路径是 `/Users/your-name/Projects/eduK12-new-version`。请替换成你的真实路径：

```bash
cd /Users/your-name/Projects/eduK12-new-version
git remote -v
git status --short --branch
```

确认远端指向 `caohuibj/eduK12-new-version`，当前工作区没有不希望混入安装提交的改动。不要把
codex-auto 仓库和 eduK12 仓库放进同一个 Git worktree。

从最新 `main` 建一个安装分支，不要直接向 `main` 推送：

```bash
git switch main
git pull --ff-only origin main
git switch -c chore/install-codex-auto
```

## 3. 在 eduK12 内安装项目专用 codex-auto

这些命令会在 eduK12 checkout 内创建 `.codex-auto/runtime`，不会安装全局 Python package。

### 3.1 创建项目内 runtime

```bash
cd /Users/your-name/Projects/eduK12-new-version
uv venv .codex-auto/runtime --python 3.12
```

### 3.2 安装固定版本

把 `<release-tag-or-commit-sha>` 替换为你决定采用的 codex-auto release tag 或 commit SHA：

```bash
uv pip install \
  --python .codex-auto/runtime/bin/python \
  "git+https://github.com/caohuibj/codex-auto.git@<release-tag-or-commit-sha>"
```

生产使用不要长期跟随未固定的 `main`，否则不同任务可能在不知情的情况下使用不同协议版本。

### 3.3 先确认 eduK12 的真实验证命令

初始化参数必须来自 eduK12 自己的 package scripts、构建文档和 GitHub Actions。下面只是 Node 项目的
格式示例，不能假设 eduK12 一定存在这些脚本：

```text
lint      -> npm run lint
typecheck -> npm run typecheck
unit      -> npm test
CI check  -> quality
```

如果真实命令或 GitHub check 名称不同，必须替换后再初始化。错误的名称会让流程在验证/CI 门禁处停止，
不会被自动跳过。

### 3.4 生成项目配置

确认示例命令后执行；`quality` 也要替换成 GitHub PR 页面真实显示的 required check 名称：

```bash
.codex-auto/runtime/bin/codex-auto init-project \
  --repo-path . \
  --repository caohuibj/eduK12-new-version \
  --base-branch main \
  --production-branch main \
  --sol-model gpt-5.6-sol \
  --luna-model gpt-5.6-luna \
  --verification "lint=npm run lint" \
  --verification "typecheck=npm run typecheck" \
  --verification "unit=npm test" \
  --required-ci-check quality \
  --max-fix-cycles 2 \
  --execution-mode chatgpt-app
```

如果项目已有 `.codex/config.toml` 或其他受管理文件，初始化器会停止，避免覆盖现有配置。先人工合并
配置；只有你已经备份并确定要重建全部受管理文件时才使用 `--force`。

### 3.5 检查生成结果

应看到以下结构：

```text
eduK12-new-version/
├── .agents/skills/codex-auto/
│   ├── SKILL.md
│   ├── agents/openai.yaml
│   └── references/app-workflow.md
├── .codex/
│   ├── config.toml
│   └── agents/luna-implementer.toml
└── .codex-auto/
    ├── bin/codex-auto
    ├── project.yml
    ├── orchestrator.yml
    ├── .env.example
    └── runtime/                 # Git ignored
```

`.codex/config.toml` 应把主任务和默认子代理固定为：

```toml
model = "gpt-5.6-sol"
model_reasoning_effort = "high"

[agents]
enabled = true
max_concurrent_threads_per_session = 1
default_subagent_model = "gpt-5.6-luna"
default_subagent_reasoning_effort = "max"
```

`.codex/agents/luna-implementer.toml` 应包含：

```toml
name = "luna_implementer"
model = "gpt-5.6-luna"
model_reasoning_effort = "max"
```

同时检查 `.codex-auto/orchestrator.yml`：planning/review 必须是同一个 Sol High；
implementation/fix 必须是同一个 Luna Max。App checkpoint 会比较这三处配置，任何漂移都会拒绝继续。

### 3.6 提交安装文件

先暂存明确列出的安装文件，再审查 staged diff。不要提交 `.codex-auto/runtime`、`.env`、task
results 或 audit：

```bash
git status --short
git add .gitignore .agents/skills/codex-auto .codex .codex-auto
git diff --cached
git commit -m "chore: install project-local codex-auto"
git push -u origin chore/install-codex-auto
gh pr create \
  --base main \
  --head chore/install-codex-auto \
  --title "chore: install project-local codex-auto" \
  --body "Add the project-scoped Sol/Luna workflow and local checkpoint runtime."
```

Review 并合并这个安装 PR 后，回到本地更新 `main`，再创建 App project：

```bash
git switch main
git pull --ff-only origin main
```

## 4. 在 ChatGPT App 中建立正确的本地项目

OpenAI 的 local project 会把本地 folder 交给 Codex。Primary folder 是默认 Git 工作目录，也是
`AGENTS.md`、`.agents/skills` 和 `.codex/config.toml` 自动发现的起点。参见
[Projects and chats](https://learn.chatgpt.com/docs/projects) 与
[Build skills](https://learn.chatgpt.com/docs/build-skills)。

1. 打开 ChatGPT desktop app，进入 Codex。
2. 创建一个 local project，名称可设为 `eduK12`。
3. 打开项目设置（Edit project），选择 Add folder。
4. 添加 `/Users/your-name/Projects/eduK12-new-version`。
5. 对这个 folder 选择 Make primary。
6. 本项目不要再添加另一个业务仓库；尤其不要添加或设为 primary 的 `codex-auto` checkout。
7. 新建一个全新的 Codex task，让 App 重新加载项目配置和 skill。

若 `$codex-auto` 没有出现，先确认 primary folder，再重启 App 并新建 task。Codex 通常能检测 skill
变化，但重启可排除旧任务未刷新配置的问题。

## 5. 精确选择 Sol 主模型并启用 Luna 子代理

### 5.1 选择主模型

在新 task 的输入框下方打开模型/推理强度控制：

1. 进入 Advanced 模型选择；
2. 选择 `gpt-5.6-sol`（界面可能显示为 `5.6 Sol`）；
3. 推理强度选择 High；
4. 不要选择 Auto、其他 Sol 版本、Luna 或“最快”模式。

项目文件已经设置默认值，但发起任务前仍要看一眼界面。若 App 不提供指定 Sol，停止并报告：
`configured Sol route unavailable`。不要让 App 自动替换，也不要开始实现。

### 5.2 确认子代理能力

当前 Codex App 默认支持子代理，并会在任务中显示子代理活动。项目通过
`.codex/agents/luna-implementer.toml` 注册一个精确代理；skill 会直接请求这个代理，而不是使用一个
继承 Sol 模型的匿名 worker。

在 App Settings 的 Configuration 中确认子代理功能可用。如果账户/App 对 Max 强度另有开关，先
启用它并新建 task。若 `gpt-5.6-luna`、Max 或 `luna_implementer` 不可用，流程必须停止并报告：
`configured Luna route unavailable`。

### 5.3 选择权限模式

子代理继承主任务的权限边界，且不能扩大它。发起任务前，在输入框下方选择允许修改当前 eduK12
工作区的权限模式；网络访问、push 和创建 PR 如果需要批准，App 会在对应步骤请求。不要授予其他
目录的写权限。

## 6. 第一次使用前做只读冒烟检查

在一个新 task 中发送：

```text
$codex-auto
只做配置冒烟检查，不修改文件、不创建分支、不提交、不 push。
确认当前 primary folder 是 caohuibj/eduK12-new-version；
确认主任务是配置中的 gpt-5.6-sol / high；
确认能够按项目配置创建 luna_implementer，且它是 gpt-5.6-luna / max。
让该子代理只报告 agent name、配置模型和 effort，然后结束。
任一项不能确认就返回 BLOCKED，不得替换模型。
```

你应在 App 中看到一个子代理活动项，并能打开查看。只有它显示 `luna_implementer` 且路由与配置一致
才通过。由于 App 不把实际模型身份提供给项目内 Python 程序，这一步依赖 App 的可见代理信息和
Sol 的确认；本地 checkpoint 能校验配置一致性，但不能绕过平台验证账户可用性。

## 7. 发起第一个 eduK12 开发任务

把下面的需求、路径和验收条件替换为真实内容：

```text
$codex-auto
只在 caohuibj/eduK12-new-version 中完成这个任务：

目标：<一句话描述用户可观察的结果>
范围：<允许修改的模块或目录>
范围外：不改认证架构、不改部署配置、不做无关重构。
验收：<列出可客观验证的行为和边界情况>
验证：使用项目配置中的 lint、typecheck、unit，并等待 required CI。

必须使用已配置的 gpt-5.6-sol / high 做 planning 和 review；
实现与修复只能委派给 luna_implementer（gpt-5.6-luna / max）。
若任一路由不可用或身份不匹配，立即 BLOCKED，不得静默替换模型，Sol 不得代写实现。
创建 feature branch、commit、push 和 GitHub PR；最多修复 2 轮；最终停在人工 merge gate。
```

正常流程中会依次发生：

1. Sol 读取请求和有限仓库上下文，生成 Task Contract；
2. checkpoint 固定 base SHA、范围、验证命令与 feature branch；
3. Sol 创建 `luna_implementer`；
4. Luna 实现、测试、commit、push 并创建 PR；
5. checkpoint 收集真实 diff、verification 与 CI 证据；
6. Sol 独立 review；
7. 若有 blocking finding，最多两次委派 Luna 修复并重新 review；
8. 全部通过后状态变为 `MERGE_READY`，等待人类决定是否 merge。

Sol 的完成摘要不是证据。你应能在 GitHub PR 中看到 branch、commit、diff、checks，以及 App/audit
中对应的状态变化。

## 8. 人工检查和合并

当任务报告 `MERGE_READY` 后：

1. 打开它给出的 GitHub PR 链接；
2. 确认 base 是 `main`，head 是本任务的 `codex-auto/*` feature branch；
3. 查看 changed files，确认没有 `.codex/**`、`.codex-auto/**`、`.agents/skills/**`、workflow、密钥或
   范围外文件被实现代理修改；
4. 确认 required checks 全部通过，Sol review 的 head SHA 与 PR 最新 SHA 相同；
5. 由你本人点击 Merge，或明确要求一个有权限的操作者合并。

默认策略不会让 Luna 或 Sol 自行合并。`MERGE_READY` 只表示证据满足合并条件，不等于已经合并。

## 9. 常见问题

| 现象 | 原因与处理 |
|---|---|
| 要求 `OPENAI_API_KEY` | 使用了 `responses-api` 或 `run`。重新以 `chatgpt-app` 初始化，并使用 App task 与 `app-*` checkpoints。 |
| 找不到 `$codex-auto` | eduK12 不是 primary folder，skill 未提交，或旧 task 未刷新。修正 primary、重启 App、新建 task。 |
| 主模型不是 Sol High | 在输入框下方手动选 `5.6 Sol` + High；仍不可选则 BLOCKED。 |
| 子代理继承成 Sol | 没有直接选择 `luna_implementer`，或项目 agent 配置未加载。停止任务，检查 `.codex/agents/luna-implementer.toml`，重启 App。 |
| Luna/Max 不可用 | 更新 App、检查 Settings/Usage/plan；恢复前保持 BLOCKED，不能降级或换模型。 |
| checkpoint 报 route mismatch | `.codex/config.toml`、Luna agent 文件与 `orchestrator.yml` 不一致。按同一模型/effort 修正后重新开始。 |
| 初始化拒绝覆盖文件 | 仓库已有同名配置。人工合并；不要直接用 `--force` 覆盖未知设置。 |
| 不能 push/建 PR | 检查 `gh auth status`、Git remote、App 网络批准与 GitHub 权限。 |
| 工作区不干净 | 先处理你自己的未提交改动；orchestrator 不应把它们混进 feature branch。 |
| CI 一直等待或找不到 | `--required-ci-check` 名称与 GitHub 实际 check 名不一致，或 workflow 未触发。修正项目配置，不能假装 PASS。 |
| 达到两轮修复上限 | 状态变为 `BLOCKED`；需要人类调整 contract、范围或 `max_fix_cycles` 后开启新任务。 |
| 达到 ChatGPT allowance | 等待额度恢复或按账户规则增加 credits；API key 不是 Plus 额度的替代方案。 |

## 10. 更新和移除

更新时仍固定到新 tag 或 commit：

```bash
uv pip install --upgrade \
  --python .codex-auto/runtime/bin/python \
  "git+https://github.com/caohuibj/codex-auto.git@<new-tag-or-commit-sha>"
```

升级后先在单独 branch 重新运行 `init-project` 并 review 配置 diff。移除时删除 eduK12 内的
`.agents/skills/codex-auto`、`.codex/agents/luna-implementer.toml` 和 `.codex-auto`，再人工清理
`.codex/config.toml` 中由本工具管理的设置；不要删除其他工具或用户已有的 Codex 配置。
