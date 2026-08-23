# 在 ChatGPT/Codex Project 中按项目安装

## 目标

每个开发项目拥有独立的 codex-auto：

- 独立 Sol/Luna 模型路由、验证命令、CI 门禁和修复次数；
- 独立 Python runtime 和 OpenAI API key；
- 只在该项目中被 ChatGPT 桌面版/Codex 自动发现；
- 不写入 `~/.codex`、`~/.agents`、系统 Python 或全局 plugin 目录。

这使用 repo-scoped skill，而不是全局 plugin。OpenAI 官方文档说明 Codex 会从当前目录到 repository
root 扫描 `.agents/skills`，而 local project 只从 primary folder 自动发现 skill 和项目配置。参见
[Build skills](https://learn.chatgpt.com/docs/build-skills) 和
[Projects and chats](https://learn.chatgpt.com/docs/projects)。安装结果全部位于目标仓库：

```text
target-repository/
├── .agents/skills/codex-auto/
│   ├── SKILL.md
│   └── agents/openai.yaml
└── .codex-auto/
    ├── bin/codex-auto
    ├── project.yml
    ├── orchestrator.yml
    ├── .env.example
    └── runtime/                 # ignored, project-local virtual environment
```

## ChatGPT Project 类型要求

开发代码时使用 ChatGPT 桌面版的 **local project**，并把目标代码仓库设为 primary
folder。普通 ChatGPT project 只有上传文件、project instructions 和 connected sources，不能直接执行
目标仓库中的本地 runtime。

如果一个 local project 附加了多个 folder，必须把实际开发仓库设为 primary。Codex 只会从 primary
folder 自动发现 `.agents/skills`、`AGENTS.md` 和项目配置；secondary folder 仍可读取，但不会自动发现
这些入口。

## 前置条件

- 目标目录是 Git repository/worktree，且已配置正确的 GitHub remote；
- 已安装 `uv`、`git` 和 `gh`，并完成 `gh auth login`；
- 有可调用所配置模型的 OpenAI API key；
- Python 3.11 或更高版本。

## 安装：完全隔离在目标项目

以下命令全部在目标仓库执行。

### 1. 创建项目内 runtime

```bash
cd /path/to/target-repository
uv venv .codex-auto/runtime --python 3.12
```

### 2. 安装 codex-auto

当前本地开发/评估可直接从 codex-auto checkout 安装：

```bash
uv pip install \
  --python .codex-auto/runtime/bin/python \
  /absolute/path/to/codex-auto
```

有正式 release/tag 后应固定到 tag 或 commit，避免项目无意跟随 `main`：

```bash
uv pip install \
  --python .codex-auto/runtime/bin/python \
  "git+https://github.com/caohuibj/codex-auto.git@<tag-or-commit>"
```

这些命令不会创建全局 `codex-auto` 命令；可执行文件只存在于
`.codex-auto/runtime/bin/`。

### 3. 初始化项目配置和 repo-scoped skill

下面是 Python 项目示例。`--verification` 可重复，格式为 `NAME=COMMAND`；名称将进入 Task
Contract allowlist，模型不能自行增加任意命令。

```bash
.codex-auto/runtime/bin/codex-auto init-project \
  --repo-path . \
  --repository owner/repository \
  --base-branch main \
  --production-branch main \
  --verification "lint=uv run ruff check ." \
  --verification "typecheck=uv run mypy" \
  --verification "unit=uv run pytest -q" \
  --required-ci-check quality \
  --max-fix-cycles 2
```

Node 项目可以改为：

```bash
--verification "lint=npm run lint" \
--verification "typecheck=npm run typecheck" \
--verification "unit=npm test"
```

初始化器会拒绝覆盖已有的 managed file。只有明确希望按当前参数重建所有 managed file 时才使用
`--force`。

### 4. 提交项目级集成文件

orchestrator 只在 clean worktree 上创建 feature branch。先检查生成的模型、命令和路径策略，然后把
项目级集成提交到目标仓库：

```bash
git add .agents/skills/codex-auto .codex-auto .gitignore
git commit -m "chore: install project-local codex-auto"
```

`runtime/`、task、audit 和 `.env` 已被忽略，不会进入这个 commit。

### 5. 设置本项目 API key

```bash
cp .codex-auto/.env.example .codex-auto/.env
chmod 600 .codex-auto/.env
```

编辑 `.codex-auto/.env`：

```text
OPENAI_API_KEY=your_project_key
```

`.codex-auto/.env` 和 runtime 会自动加入目标仓库 `.gitignore`。项目 launcher 只在运行时读取这个
文件，不会修改 shell profile 或用户级环境变量。

### 6. 验证安装

先创建一个真实 TaskRequest，例如 `.codex-auto/tasks/TASK-001.yml`：

```yaml
task_id: TASK-001
title: Add one bounded feature
objective: Add the requested behavior with deterministic tests and no unrelated changes.
in_scope:
  - Implement the requested behavior in the named module.
out_of_scope:
  - Do not change deployment or authentication architecture.
context_paths:
  - README.md
  - src/**/*.py
  - tests/**/*.py
constraints:
  - Preserve existing public interfaces.
required_verification:
  - lint
  - typecheck
  - unit
```

验证命令：

```bash
./.codex-auto/bin/codex-auto validate \
  --config .codex-auto/orchestrator.yml \
  --task .codex-auto/tasks/TASK-001.yml
```

返回 `"valid": true` 即表示项目内 runtime、入口和配置可用；该命令不会调用模型或修改代码。

## 在 ChatGPT/Codex 中直接使用

1. 在 ChatGPT 桌面版打开或创建 local project；
2. 将目标仓库设为 primary folder；
3. 新建 Codex task；
4. 直接提出开发目标，例如：

```text
使用 codex-auto 实现登录限流，保留现有 API，并补充 unit 与 integration tests。
```

repo-scoped skill 默认允许 implicit invocation，因此实现、修复或重构请求会匹配 codex-auto；
review-only、解释性问题和明确要求 direct manual editing 的任务不会匹配。也可以显式使用：

- Codex：`$codex-auto 实现……`
- ChatGPT 中能看到该 standalone skill 时：`@codex-auto 实现……`

实际修改本地代码、运行 Git 和创建 PR 时仍应使用这个 local project 中的 Codex task；在普通
ChatGPT Chat/Work 中选择 skill 本身不会额外授予本地文件或 terminal 权限。

skill 会创建项目内 TaskRequest、先执行 `validate`，然后调用：

```bash
./.codex-auto/bin/codex-auto run \
  --config .codex-auto/orchestrator.yml \
  --task <generated-task-file> \
  --repo-path .
```

最终停在 GitHub PR 的 human merge gate，不会 merge。

## 多个 Project 如何保持互不影响

为每个仓库分别执行安装。每个 project 可以使用不同配置：

```text
project-a/.codex-auto/orchestrator.yml  -> Sol High + Luna Max, 3 fix cycles
project-b/.codex-auto/orchestrator.yml  -> different model IDs, 1 fix cycle
```

repo-scoped skill 只从当前/父级仓库的 `.agents/skills` 被发现。不要把它安装到
`$HOME/.agents/skills`，也不要把 runtime 安装到系统 Python，即可保证其他 project 不受影响。

## 更新与移除

更新 runtime 不需要改全局环境：

```bash
uv pip install --upgrade \
  --python .codex-auto/runtime/bin/python \
  "git+https://github.com/caohuibj/codex-auto.git@<new-tag-or-commit>"
```

移除时，删除目标仓库内的 `.agents/skills/codex-auto` 和 `.codex-auto`，再移除 `.gitignore`
中的 `# codex-auto project-local runtime` 区块即可。其他 project 和用户级 Codex 配置不会改变。

## 当前真实边界

- 项目 launcher 当前面向 macOS/Linux；Windows 可直接调用
  `.codex-auto\\runtime\\Scripts\\codex-auto.exe`。
- 普通、非 local 的 ChatGPT project 不能运行本地 Git/GitHub adapter；应使用带 primary folder 的
  local project/Codex task。
- 初始化不会替你选择正确的验证命令或 CI check name；这些必须与目标仓库真实命令一致。
- API 调用、branch、push 和 PR 创建仍受项目 credentials、sandbox 和网络权限约束。
