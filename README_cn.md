<div align="center">
  <img src="./logo/hero.png" alt="awescholar" width="800">
  <h1>awescholar: Scientific Literature Curator <a href="https://github.com/wehuman01/aweskill"><img src="https://raw.githubusercontent.com/wehuman01/aweskill/main/logo/aweskill-badge2.svg" alt="aweskill companion"></a></h1>
  <p><strong>AI agent 可自主执行的科学文献发现与策展。</strong></p>
  <p>搜索、标注、筛选和报告学术论文 — 告诉你的 agent 去做，或者自己跑 CLI。</p>
  <p>
    <a href="./README.md">English</a> ·
    <strong>简体中文</strong> ·
    <a href="https://we.webioinfo.top/">Webioinfo</a>
  </p>
  <p>
    <img src="https://img.shields.io/pypi/v/awescholar?style=flat-square&color=7C3AED" alt="Version">
    <img src="https://img.shields.io/badge/python-%E2%89%A53.11-0EA5E9?style=flat-square" alt="Python">
  </p>
  <p>
    <img src="https://img.shields.io/badge/status-alpha-c96a3d?style=flat-square" alt="Status">
    <img src="https://img.shields.io/badge/install-pip-22C55E?style=flat-square" alt="pip install">
    <img src="https://img.shields.io/badge/platform-cli-334155?style=flat-square" alt="Platform">
    <img src="https://img.shields.io/pypi/dm/awescholar?style=flat-square" alt="PyPI downloads">
    <img src="https://img.shields.io/github/stars/wehuman01/awescholar?style=flat-square" alt="GitHub stars">
  </p>
</div>


> 搜索、标注、筛选和报告学术论文 — 告诉你的 agent 去做，或者自己跑 CLI。

一个轻量级 CLI 工具，自动化论文策展工作流：查询 Semantic Scholar、用 LLM 标注、按质量筛选、生成 Markdown 报告，并增量合并到长期维护的项目数据 JSON。同时支持人类和 AI agent 操作 — 安装 skill 后，你的 coding agent 可以通过自然语言指令执行完整流水线。

awescholar 用一套工具服务两种项目取向 — **论文取向的 awesome 列表**（data.json 存档：crawler → updater → render → reader）和**项目取向的 AgentX 集线器**（data/agents-snapshot.json 快照：updater --agentx 命令 + verify）。同一个实体既是一条论文记录，也是一条 agent 记录；`render agentx` 负责两者之间的投影。

> **说明：** 独立的 `agentx-cli`（npm `agentx-hub-cli`）已于 awescholar 0.2.6 并入本工具。v0.3.0 引入的 `agentx` 命令别名已在 v0.3.2 移除 —— 策展直接用 awescholar 的 `--agentx` 原生命令；npm 包 v0.2.0 起重生为 Hub **运维** CLI。

## awescholar 驱动的项目

- **[Awesome AI Meets Biology](https://github.com/Webioinfo01/Awesome-AI-Meets-Biology)** — AI × 生物学论文策展，由 awescholar 驱动自动发现、筛选和 README 更新。

## 安装

### 让 AI agent 安装

如果你在 Claude Code、Codex、Cursor 等 coding agent 中工作，直接告诉它：

```text
Read https://github.com/wehuman01/awescholar/blob/main/README.ai.md and follow it to install awescholar for this agent.
```

Agent 会先安装 `awescholar` CLI，然后在下面两种 awescholar skill 管理方式中选择一种：

1. **通过 [aweskill](https://aweskill.wehuman.top/)** — 从 GitHub 安装和管理 skill，支持更新、投影和备份。需要 Node.js。由 [aweskill](https://aweskill.wehuman.top/) 驱动 — AI 编程 Agent 的通用 skill 管理器。
2. **直接复制** — 将 `SKILL.md` 下载到 agent 的 skill 目录。除 Python 外无需额外依赖，但后续更新需要手动重新复制。

### pip

```bash
pip install awescholar
```

## aweskill 支持

awescholar 由 [aweskill](https://github.com/wehuman01/aweskill) 驱动 — 一个以 CLI 为核心的 Skill 包管理器，AI agent 也能自己调用和维护。aweskill 负责 skill 的安装、更新、投影和备份，支持 47+ 编程 agent，包括 Claude Code、Codex、Cursor、Gemini CLI 等。

## 使用

### AI Agent

安装 awescholar skill（见上方[安装](#安装)），然后直接告诉你的 agent 做什么 — 无需手动操作 CLI。如果 agent 还没有配置好 `config.json` 或需要修改模型/搜索设置，参考下方[详细配置](#详细配置)。

**AI agent 能做什么：**

- 一键执行完整发现流水线：搜索、标注、筛选、报告
- 将新结果合并到项目数据 JSON 并重新生成 README
- 按标题或 DOI 搜索 Semantic Scholar 并添加论文到存档
- 只读问答策展存档、不改动数据：关键词检索、为粘贴的摘要找相关论文、按领域生成必读清单（`reader query / related / recommend`）
- 处理合并时被拦下的疑似预印本/正式版重复论文
- 与你的 Zotero 文献库互通：把阅读 collection 拉进流水线，或把筛选出的论文推入 Zotero collection（先干跑预览）
- 为策展集合生成 RSS 订阅
- 独立重新运行任意流水线步骤，支持自定义输入

**你可以这样告诉你的 agent：**

> "搜索最近关于 AI agents in biology 的论文，筛选 top 20，更新 README。"

> "用我的 config 跑 awescholar 流水线，然后把结果合并到 docs/data.json。"

> "按 DOI 找到这篇论文，添加到项目数据 JSON 里。"

Agent 通过 [SKILL.md](resources/skills/awescholar/SKILL.md) 理解所有可用命令、配置选项和工作流。

### 人类使用

```bash
# 把 API key 一次性存进用户 keyring（推荐 — agent 和 cron 也能读到，
# 它们的 shell 不会 source ~/.zshrc）：
mkdir -p ~/.config/awescholar
cat >> ~/.config/awescholar/.env <<'EOF'
GLM_API_KEY=sk-...
SEMANTIC_SCHOLAR_API_KEY=your-key   # 可选，不设则使用免费 tier
GITHUB_TOKEN=ghp-...                 # 可选，用于 repo enrichment
EOF

# 运行完整流水线
awescholar --config config.json crawler run

# 或直接传入搜索词
awescholar --config config.json crawler run "perturbation prediction|single cell" --date 2025-01-01:2025-05-30

# 月报：--month 自动推导日期区间、输出目录（month_reports/YYMM）和报告文件名
awescholar --config config.json crawler run --month 2026-05
```

在 `~/.zshrc` / `~/.bashrc` 里 export 同名变量也可以，且优先级高于 `.env` 文件；但当 awescholar 从非交互 shell 调用时 rc 文件不会被加载，所以 `.env` keyring 才是可靠选项。

Semantic Scholar API key 按以下顺序读取：`--ss-api-key` 命令行参数 > 项目 config.json 中的 `semantic_scholar.api_key` > `~/.config/awescholar/config.json` 中的 `semantic_scholar.api_key` > 环境变量 `SEMANTIC_SCHOLAR_API_KEY`（兼容旧名 `SEMANTICSCHOLAR_API_KEY`）> `.env` 文件（项目 `.env` > `~/.config/awescholar/.env`）。任何地方都找不到 key 时，awescholar 会向 stderr 输出警告并回退到匿名免费 tier。

```bash
awescholar --ss-api-key "your-key" crawler search "AI agent" --limit 10
```

Zotero API key 走同样的模式：`--zotero-api-key` 命令行参数 > config.json 的 `zotero.api_key` > 环境变量 `ZOTERO_API_KEY` > `.env` 文件。在 https://www.zotero.org/settings/keys 创建一个允许读写的 key（`zotero push` 需要）。个人库无需配置 id（key 自带归属）；群组库需设置 `zotero.library_id`。写入走 api.zotero.org 云端，桌面版 Zotero 在下次同步后可见。

完整命令参考见下方[命令](#命令)。

## 详细配置

配置分两层解析，按 key 深度合并，项目文件只需覆盖它真正要改的部分：

1. `~/.config/awescholar/config.json` — 全局默认值。把共享的 `model_profiles`、`semantic_scholar`、`github` 条目放这里一次即可。
2. `--config` 传入的项目配置文件（如 `month_reports/config.json`）— 按项目覆盖：搜索词和日期、filter 设置、输出路径、分类，以及 `model.profile`/`model.name` 的选择。

从 [repo 根目录](https://github.com/wehuman01/awescholar/blob/main/config.example.json) 复制 `config.example.json` 到上面任一位置并填入你的值 — 或直接设置环境变量，跳过配置文件。不带 `--config` 运行的命令只使用全局文件，因此 `enrich`、`render agentx` 这类只依赖 key 的命令可以开箱即用。

```json
{
    "model_profiles": {
        "glm": {
            "api_key": "${GLM_API_KEY}",
            "base_url": "https://open.bigmodel.cn/api/paas/v4"
        },
        "deepseek": {
            "api_key": "${DEEPSEEK_API_KEY}",
            "base_url": null
        }
    },
    "model": {
        "profile": "glm",
        "name": "glm-5.1"
    },
    "agent_models": null,
    "semantic_scholar": {
        "api_key": "${SEMANTIC_SCHOLAR_API_KEY}"
    },
    "github": {
        "token": "${GITHUB_TOKEN}"
    },
    "zotero": {
        "api_key": "${ZOTERO_API_KEY}",
        "library_type": "user",
        "library_id": null
    },
    "search": {
        "query": "AI agent|large language model|foundation model",
        "fields_of_study": ["Biology", "Medicine", "Computer Science"],
        "publication_date": "2025-01-01:2025-05-30",
        "limit": 100,
        "include_abstracts": true
    },
    "filter": {
        "limit": 20,
        "research_interests": null
    },
    "output": {
        "db_path": "output",
        "report_filename": null
    },
    "pipeline": {
        "skip_search": false,
        "use_updater_json": false,
        "use_filtered_json": false,
        "existing_json_path": null,
        "merge_new_to_old": false,
        "data_json_path": null
    },
    "categories": ["Foundation Models", "Drug Discovery", "Perturbation Study"]
}
```

`${VAR}` 模式在加载时从环境变量展开。

**`model.name`** — 只写模型名称，如 `glm-5.1`、`deepseek-chat`、`gpt-4o`。`openai/` 前缀会自动添加，不要手动写。

**`model_profiles`** — 可复用的 profile 映射。每个 profile 定义 `api_key` 和 `base_url`，通过 `model.profile` 或 `agent_models.*.profile` 引用，避免重复填写凭证。

**`agent_models`** — 按 agent 覆盖模型（annotator, filterer, reporter）。每个条目可用 `profile` 引用 `model_profiles`，或直接设置 `name`/`api_key`/`base_url`：
```json
"agent_models": {
    "annotator": { "profile": "deepseek", "name": "deepseek-chat" },
    "filterer":  { "profile": "glm", "name": "glm-5.1" },
    "reporter":  { "profile": "glm", "name": "glm-5.1" }
}
```

**`filter.research_interests`** — 可选字符串，描述研究兴趣，传给 filterer 做相关性加权。

**`pipeline`** — 控制流水线跳过/复用中间结果：
- `skip_search`: 从数据库加载论文而不是搜索
- `use_updater_json`: 复用已有的 `updater.json`（跳过搜索+标注）
- `use_filtered_json`: 复用已有的 `updater_filter.json`（直接生成报告）
- `existing_json_path`: 自定义 updater JSON 路径
- `merge_new_to_old`: 流水线结束后将筛选结果自动合并到项目数据 JSON
- `data_json_path`: `merge_new_to_old` 使用的项目数据 JSON 路径；当 `merge_new_to_old` 为 `true` 时必须设置

`existing_json_path` 和 `data_json_path` 是两个不同文件。`existing_json_path` 指向标注阶段的中间文件（`updater.json`），用于复用或写入 annotate 结果。`data_json_path` 指向长期维护的项目数据 JSON，在启用 `merge_new_to_old` 后接收筛选后的论文。

**`search.query`** — 如果设置了，`crawler run` 可以不传 CLI query 参数。

**`archive.stars_style`** — 项目数据 JSON 里 `githubStars` 的形状：`numeric`（默认，裸整数，由 `updater enrich` 刷新）或 `badge`（shields.io URL；enrich 写入 badge URL 且绝不降级成数字）。

支持的 LLM 提供商：任何 OpenAI 兼容 API（通过 `base_url`），如 GLM、DeepSeek、Gemini、Mistral、本地端点。

## 命令

```bash
awescholar -v                                         # 显示版本

# 脚手架：一键生成新的精选论文列表仓库
awescholar init                                       # 在当前目录生成 website-first 仓库（默认 Awesome-AI-Meets-Biology 身份）
awescholar init awesome-ai-foo                        # 生成到子目录
awescholar init --template vt                         # Awesome-AI-Virtual-Tumor 风格网站（默认 bio）
awescholar init --title "Awesome AI Foo" --github-repo Webioinfo01/Awesome-AI-Foo \
                 --website http://foo.webioinfo.top/ --category "AI Agents" --category Reviews
awescholar init --no-zh --no-branding                 # 仅英文 README、不含生态/赞赏区块
awescholar init --tables                              # 经典模式：同时内嵌 README 表格 marker
awescholar init --no-serve                            # 跳过本地预览服务器（脚本场景）
awescholar init --port 8123                           # 换预览端口（默认 8000）
awescholar init --force                               # 目标目录非空时也继续

# 论文发现流水线
awescholar crawler search "query"                     # 搜索 Semantic Scholar
awescholar crawler annotate                           # 标注数据库中的论文
awescholar crawler annotate --input papers.json       # 从 JSON 标注（跳过 DB）
awescholar crawler filter --limit 20                  # 选择 top 论文
awescholar crawler filter --input updater.json        # 从自定义 JSON 筛选
awescholar crawler report                             # 生成报告（输出到 stdout）
awescholar crawler report updater_filter.json -o report.md  # 从自定义 JSON 生成报告
awescholar crawler run ["query"]                      # 完整流水线（如 config 已设 query 则可省略）
awescholar crawler run --month 2026-05                # 某个月的完整流水线 -> month_reports/2605/report.md
awescholar crawler run --period 2026-06-1             # 半月：P=1 为 01–15，P=2 为 16–月末 -> month_reports/2606_1/report.md

# 存档管理
awescholar updater update --direction new2old --input X --archive data.json  # 合并到项目数据 JSON（疑似重复会被拦下）
awescholar updater update --direction new2old --input X --archive data.json --no-dedupe  # 全部合入，跳过重复检测
awescholar updater dedupe --review output/dedupe_review.json --archive data.json --keep published  # 处理被拦下的重复对
awescholar updater publish-scan --archive data.json   # 扫描库内预印本是否已正式发表（默认 dry run -> publish_review.json）
awescholar updater publish-scan --archive data.json --apply  # 扫描并原地升级（venue/DOI/paperUrl/引用切换，策展字段保留）
awescholar updater publish-scan --archive data.json --review publish_review.json --apply  # 只应用已审阅的队列，不重新扫描
awescholar updater publish-scan --archive data.json --only XunZi --limit 5   # 按 DOI/标题子串限定，限制扫描数量
awescholar updater publish-scan --archive data.json --pair 10.48550/arXiv.2508.10492 10.1038/x  # 手工配对：改题发表、数据库无关联的预印本/正式版
awescholar updater search --json-file papers.json --by title   # 搜索并保存待审阅
awescholar updater search --archive data.json --by title       # 搜索并直接添加
awescholar updater search --archive data.json --category "AI Agents"  # 添加到指定分类
awescholar updater search --archive data.json --by doi 10.1038/s41467-025-59628-y  # 非交互：DOI 直接作为参数
awescholar updater search --archive data.json --by doi 10.1038/x --code-url owner/repo --annotate  # 已知 repo + LLM 补写 domain 一句话
awescholar updater add --archive data.json            # 交互式添加单条记录到项目数据 JSON
awescholar updater backfill --archive data.json       # 补齐缺失的机构/团队/引用数字（Semantic Scholar + Crossref + OpenAlex）
awescholar updater backfill --archive data.json --only XunZi   # 只处理 DOI 等于该值或标题含该子串的条目（可重复）
awescholar updater backfill --archive data.json --fields citations  # 只回填引用数字
awescholar updater enrich --archive data.json         # 从 GitHub 检索补空 codeUrl + 刷新数字 githubStars
awescholar updater enrich --archive data.json --limit 20 --no-llm  # 最多解析 20 篇，仅启发式匹配
awescholar updater enrich --archive data.json --only XunZi   # 只解析/刷新匹配的条目
awescholar updater enrich --archive data.json --since 2026-09-01  # 只处理该日及之后 addedAt 的条目
awescholar updater enrich --archive agents-snapshot.json --agentx  # 刷新 AgentX registry 快照（stars/pushedAt 等；status 等字段严格保留）

# 产物渲染（render）——从项目数据 JSON 派生输出，绝不修改存档
awescholar render readme --archive data.json         # 生成 README 表格（自动备份）
awescholar render readme --archive data.json --no-backup  # 生成 README 不备份
awescholar render counts --archive data.json         # 刷新 website-first README 的论文计数
awescholar render rss --archive data.json            # 生成 RSS 订阅
awescholar render digest --archive data.json --month 2026-05   # 当月入库论文摘要 -> month_reports/2605/digest.md
awescholar render digest --archive data.json --month 2026-05 --no-llm   # 仅表格，无需模型 key
awescholar render agentx --archive data.json -o candidates.json  # 有 GitHub repo 的论文导出为 AgentX 候选 agent
awescholar render agentx --archive data.json -o c.json --category-map map.json --default-category platforms
awescholar render agentx --archive data.json -o c.json --exclude-snapshot agents-snapshot.json --llm-category  # 由 LLM 从 snapshot 实有分类中挑选 category

# 只读查询（reader）——无需 config，绝不修改数据
awescholar reader query --archive data.json "single cell perturbation"   # 库内关键词检索
awescholar reader query --archive data.json "LLM agent" --category "AI Agents" --top 5 --json
awescholar reader related --archive data.json --doi 10.1/x   # 与某篇种子论文相关的库内论文（外部论文可用 --input）
awescholar reader related --archive data.json --title "Some paper title" --top 5 --json  # 按标题喂外部种子
awescholar reader recommend --archive data.json --field "AI for biology" --top 10   # 领域必读排名（离线）
awescholar --config config.json reader recommend --archive data.json --field "..." --llm   # LLM 排名并给出理由
awescholar reader stats --archive data.json           # 存档统计
awescholar reader stats --archive data.json --category "AI Agents"   # 单分类统计（可重复）

# Zotero 文献库交换 —— 个人阅读库作为流水线的输入/输出
awescholar zotero pull --collection "Reading List"    # collection -> zotero_papers.json，喂给 `updater update`（只读）
awescholar zotero pull --collection "DROMA" -o papers.json --category "AI Agents"   # 自定义输出文件和分类
awescholar zotero push --archive data.json --collection "2605 月报"     # 干跑：分类防重 + 写 zotero_review.json
awescholar zotero push --archive data.json --collection "2605 月报" --apply    # 把 to-add 条目真正写入 Zotero
awescholar zotero push --archive data.json --collection "2605" --category "AI Agents" --tag must-read --apply
```

每个子命令都支持 `--input`（report 用位置参数）指定输入文件，无需重跑完整流水线即可独立执行任意步骤。

## AgentX 集线器

典型的 hub 维护流程（原生命令；策展永远直接走 `awescholar` 本体）：

```text
render agentx → updater add --agentx --from-json → updater enrich --agentx → verify --agentx → commit
```

```bash
awescholar updater add --agentx owner/repo --category <slug> [--tags "A,B"] [--paper URL]
awescholar updater enrich --agentx
awescholar updater backfill --agentx [--fields paper-meta,venue-tags,citations]
awescholar verify --agentx
```

> v0.3.0 的 `agentx` 命令别名（上述命令的短写）已于 v0.3.2 移除 —— 一个命令名只有一个归属。Hub **运维**（快照落库、评价审核、镜像到公共 hub）在独立的
> [`agentx-hub-cli`](https://github.com/Webioinfo01/agentx-hub-cli) npm 包（v0.2.0+），它包装 hub 网站自己的脚本和 workflow。

命令映射（旧 `agentx-cli` v0.1.x → `awescholar`）：

| 旧 `agentx-cli` | 新 `awescholar` |
|---|---|
| `agentx add owner/repo --category X --tags A,B` | `awescholar updater add --agentx owner/repo --category X [--tags "A,B"] [--name] [--paper] [--homepage] [--description]` |
| `agentx add --from-json F` | `awescholar updater add --agentx --from-json F`（批量，all-or-nothing） |
| `agentx snapshot` | `awescholar updater enrich --agentx [--archive data/agents-snapshot.json]`（指标 + 生命周期：404→gone、状态推导、retirement 冻结、license 回退；`--agentx` 模式下 `--archive` 缺省 `data/agents-snapshot.json`） |
| `agentx enrich-papers` | `awescholar updater backfill --agentx --fields paper-meta [--refresh] [--only slug 子串]`（同时同步已注册的 venue 标签） |
| `agentx refresh-citations` | `awescholar updater backfill --agentx --fields citations` |
| — | `awescholar updater backfill --agentx --fields venue-tags [--only slug 子串]`（将论文 venue 同步为已注册标签） |
| `agentx validate` | `awescholar verify --agentx`（离线不变量门禁；CI 运行的就是它） |

环境变量：`GITHUB_TOKEN`（建议配置）、`SEMANTIC_SCHOLAR_API_KEY` 或 `SEMANTICSCHOLAR_API_KEY`（backfill 建议配置）。

`crawler run --month 2026-05` 取代"每月复制一份 config"的做法：一个参数自动推导搜索日期（`2026-05-01:2026-05-31`，闰年自动处理）、输出目录（`month_reports/2605`）和报告文件名（`report.md`），一份入库的基础 config 可服务所有月份。`--period 2026-06-1` 是同一套机制的半月粒度（`P=1` 为 01–15，`P=2` 为 16–月末；输出目录 `month_reports/YYMM_P`）。`--month`、`--period` 与 `--date` 互斥。报告默认写到 `{db_path}/report.md` —— 模型名不再进入文件名，改为写在报告开头的溯源注释里（记录 awescholar 版本、模型、日期范围）。`render digest --month 2026-05` 是月报的另一面：按 `year` 字段总结 `data.json` 里当月已策展的论文，配置了模型就生成 LLM 叙述，加 `--no-llm` 则输出结构化表格 —— 适合发布与主库实际内容始终一致的月度摘要。

筛选步骤先看选题契合、再看质量：主题落在研究兴趣之外的论文（只是共用 LLM 这类技术、应用在无关领域）无论发表在什么期刊都会被排除；`filter.limit` 是上限不是配额，合格论文不足时就少收。

`updater enrich` 把论文关联到官方 GitHub 仓库。没有 `codeUrl` 的论文会在 GitHub 上分轮检索（先 arXiv ID、再系统名、最后完整标题；一轮候选全部被拒时继续下一轮）；启发式打分只接受有交叉印证的匹配 — repo 名可由论文标题推出、且 repo 自身引用了该 arXiv ID — 难分高下的候选举交配置的 LLM 裁决（`--no-llm` 只用启发式）。星数形状是 config 约定而非命令开关：`archive.stars_style: "badge"`（如 [Awesome-AI-Meets-Biology](https://github.com/Webioinfo01/Awesome-AI-Meets-Biology)）时 enrich 往 `githubStars` 写 `https://img.shields.io/github/stars/owner/repo`，且绝不把已有 badge URL 改写成数字；默认 `numeric` 刷新裸整数并迁移旧 badge 值。`--only "DOI 或标题子串"`（可重复）把本次运行限定在匹配的条目 —— `updater backfill` 也有同一面旗 —— 单条补齐不必惊动整个存档。强烈建议配置 `GITHUB_TOKEN`（config `github.token`、`GITHUB_TOKEN` 环境变量或 `--github-token`）：匿名限额只有每分钟 10 次搜索、每小时 60 次 repo 读取。

`render agentx` 把带 github.com repo 的论文导出为 [AgentX](https://github.com/Webioinfo01/agentx-hub) 风格 registry 的候选 agent：输出符合 agentx snapshot 条目结构（slug/name/repo/paperMeta/category + 有 token 时的实时指标），slug 按 agentx 规则生成。用 `--category-map` JSON 文件把存档分类映射到 agentx 分类 slug，未映射的论文落入 `--default-category`；`--categories` 可限定导出的存档分类，`--exclude-snapshot` 跳过已注册的 repo。这里不硬编码任何分类表：指向 agentx snapshot 时以该文件中实际存在的分类为准，映射或默认 slug 缺失会告警（没有 snapshot 就不校验）。输出是给 agentx 录入审阅的队列，不是可直接落地的 snapshot — `--source`/`--source-url` 在每个导出 agent 上记录来源。录入由维护者在 hub checkout 里执行 `awescholar updater add --agentx --from-json <file>`（取代原 agentx-cli 的 `agentx add --from-json`），分类校验和实时指标拉取都在这一侧重做（标签刻意不导出，标签注册表属于目标仓库）。`--llm-category`（需配合 `--exclude-snapshot` 以获得分类表）让配置的标注模型为每个候选挑选 agentx 分类，而不是全部落到 `--default-category`；只有 slug 在目标 snapshot 中真实存在时才会保留。

`updater search` 写规范链接、也能直接携带已知事实：`paperUrl` 优先用 DOI 链接（`https://doi.org/…`）而非 Semantic Scholar 页面；`--code-url owner/repo` 把已知的仓库写进 `codeUrl`（`archive.stars_style: "badge"` 时同时写入 shields.io badge 到 `githubStars`）；`--annotate` 用配置的标注 LLM 为新增论文补写一句话 `domain` —— 与爬虫流水线同一个标注器，只跑新增的几条。论文落库后，`updater search --archive` 和 `updater update --direction new2old` 会打印下一步（`render counts` / `render rss`），README 计数和 RSS 不再悄悄过期。

`reader` 命令是策展存档的只读查询面：关键词检索（`query`）、为种子论文找相关工作（`related`，支持 `--input` 喂入粘贴的摘要）、按研究领域生成必读清单（`recommend`，离线或 `--llm`）、存档统计（`stats`）。它们不修改数据、不需要 config，AI agent 可以即时回答"我的库里有哪些关于 X 的论文"。`updater update` 合并时，标题与库内已有条目高度相似的论文（预印本/正式版的典型特征）会被拦到输入文件旁的 `dedupe_review.json`；彻底改题、躲过标题门槛的配对，只要作者名单几乎完全重合同样会被拦下，用 `updater dedupe --keep newer|published|both` 处理，`--no-dedupe` 可跳过检测。

`render readme` 只更新 `<!-- AWESCHOLAR:START -->` 和 `<!-- AWESCHOLAR:END -->` 之间的自动生成区域。这个区域包含 awescholar 生成的目录和分类表格。自定义标题、引用和项目介绍应放在 marker 外。已有 README 如果没有这些 marker，会直接报错，避免整文件覆盖。如果 README 还不存在，`--title` 用来控制生成文件的一级标题。

`updater publish-scan` 是合并期去重的主动镜像：不等正式版作为新数据撞进来，而是主动扫描库内的预印本（按预印本服务器 DOI 前缀或 venue 识别 —— 新旧 bioRxiv/medRxiv、arXiv、ChemRxiv、Research Square、Preprints.org、Authorea、SSRN），逐条经四通道查证 —— Semantic Scholar 按 DOI、S2 模糊标题检索、Crossref `query.title`、再走作者轨迹轮（预印本与正式版标题漂移是常态："AlphaFold3" vs "AlphaFold 3"；彻底改题则击穿一切标题信号 —— 数据库极少关联两个 DOI，但作者名单不变，扫描改挖预印本第一/末位作者自己的论文列表，找作者名单高度重合的已发表工作，以重合度加弱标题或摘要佐证为门）—— 标题匹配的候选需同时过相似度门槛和非空 venue 门槛（挡掉复用原题的 ResearchHub 之类转载副本）—— 把可升级项排进存档旁的 `publish_review.json`。默认 dry run；`--apply` 原地升级 —— venue、DOI、paperUrl、年份、作者、引用切换为正式版，分类、codeUrl、githubStars、domain、affiliation 原样保留 —— `--review <file> --apply` 只应用已审阅队列不重扫，归档在扫描后若有变动会按 DOI 重新定位条目。`--pair 预印本 正式版` 为扫描无法证明的改题孪生手工排队升级。同一套修正后的预印本识别，也让 `updater dedupe --keep published` 在裁决时能正确让期刊版压过 bioRxiv 预印本。

`zotero` 命令组把策展流水线和你的个人 Zotero 文献库接通（走 api.zotero.org 云端 API，无需本机运行 Zotero）。`zotero pull` 把一个 collection 映射为流水线记录格式（`--category` 指定归类，默认 `Zotero`），直接喂给 `updater update --direction new2old`；collection 里同时存在预印本和正式版时，由 updater 现成的去重机制拦下，pull 自身不需要重复造。`zotero push` 是月末的镜像：把存档（或 `--category` 子集）逐条对照整个文献库按 DOI → 规范化标题防重 —— `already-in-collection`（已在目标 collection，跳过）、`in-library`（在库内别处，只报告、绝不强行拉入 collection）、`to-add`（待新增）—— 分类结果写入存档旁的 `zotero_review.json`，只有 `--apply` 才真正创建缺失条目（collection 不存在时一并创建；每条打上 `awescholar` + 存档分类 + `--tag` 额外标签；预印本 venue 映射为 Zotero `preprint` 类型，其余为 `journalArticle`；作者按单字段 creator 原样写入，不做拆名臆测）。写入使用一次性 `Zotero-Write-Token` 单发请求，重复执行 `--apply` 幂等 —— 已创建的条目会归类为 already-in-collection；写入都在云端，桌面版 Zotero 下次同步即可见。

当不指定 `--readme` 时，`render readme` 会自动发现当前工作目录下所有包含 `<!-- AWESCHOLAR:START -->` 标记的 `README*.md` / `readme*.md` 文件并逐一更新。这适用于维护多语言 README（如 `readme.md` + `README.zh-CN.md`）— 表格内容自动保持同步。

`awescholar init` 一条命令生成完整的 website-first 仓库（类似 [Awesome-AI-Meets-Biology](https://github.com/Webioinfo01/Awesome-AI-Meets-Biology)）：中英双语落地页 README、带搜索和统计的网站（`--template bio` 或 `--template vt`）、接入 `config.json` 的空 `docs/data.json`、RSS 订阅、MPL-2.0 `LICENSE`、`CONTRIBUTING.md` 和 `.gitignore`。`--website` 传入自定义域名时会额外写入 `docs/CNAME`（GitHub Pages 用）。所有选项都可省略：在空目录里裸跑 `awescholar init` 即使用 Awesome-AI-Meets-Biology 的身份和默认值。生成完毕后 init 会默认把 `docs/` 挂到 `http://127.0.0.1:8000/` 供推送前本地检查（页面通过 `fetch` 读取 `data.json`，直接双击打开会因 CORS 加载失败），Ctrl+C 停止，`--no-serve` 跳过，`--port` 换端口。对于论文数据只上网站（README 不内嵌表格）的仓库，合并新论文后运行 `awescholar render counts --archive docs/data.json`，会刷新 `readme.md` / `README.zh-CN.md` / `README.md`（存在哪个刷哪个，`--readme` 可指定其他文件）里的分类计数、总数和 badge。

## 开发

详见 [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) 了解开发环境搭建、架构、测试和代码风格。

```bash
pip install -e ".[dev]"
pytest
```

## 工作流

```
crawler search -> crawler annotate -> crawler filter -> crawler report
                                                        |
                                                        v
                                              updater_filter.json
                                    （或 merge_new_to_old=true 时自动合并）
                                                        |
                                  +---------------------+---------------------+
                                  |                                         |
                          updater update new2old                  updater search --json-file
                                  |                                         |
                                  v                                         v
                            data.json                               papers.json（审阅）
                                  |                                         |
                          render readme / rss                    updater update new2old
                                                                          |
                                                                          v
                                                                    data.json
```

每个步骤生成一个 JSON 中间文件。你可以独立重新运行任何步骤。

## Awesome 软件生态

awescholar 是一个不断壮大的 "awesome" 工具家族中的一员 — 围绕 AI 编程 agent 打造，local-first、可被 agent 直接操作。

### CLI 工具

- **[aweskill](https://aweskill.wehuman.top/)** — CLI 优先的技能包管理器，支持 47+ AI 编程 agent。
- **[aweswitch](https://github.com/wehuman01/aweswitch)** — Claude Code、Codex、OpenCode 的 agent 配置切换器。
- **[awerouter](https://github.com/wehuman01/awerouter)** — 智能路由器，用结构信号把请求分给 Flash 或 Pro 模型，减少不必要的模型开销。
- **[aweshelf](https://github.com/wehuman01/aweshelf)** — 收藏、分类、恢复 AI 编程会话，还能搭配 aweswitch 实现保存配置，一键启动。
- **[aweshare](https://github.com/wehuman01/aweshare)** — 通过自建 Hub 共享本地 Ollama/vLLM，或国产厂商 coding plan，或已授权的 OpenAI/Anthropic 帐号订阅，实现 token 的共享经济。
- **[awewarm](https://github.com/wehuman01/awewarm)** — 订阅窗口保持器，让 AI 编程套餐的窗口持续激活，无论是本地设置，还是通过远程连接的服务器。
- **[awescholar](https://github.com/wehuman01/awescholar)** — AI agent 可自主执行的科学文献发现与策展，搜索、标注、筛选和报告学术论文。
- **[awecontrib](https://github.com/wehuman01/awecontrib)** — 每个仓库一条 verify 入口：写入一个小的 verify 脚本和最小 CI，本地和 CI 跑的是同一条命令。

### 桌面应用

- **[awefork](https://github.com/wehuman01/awefork)** — 把 AI 编程 agent 的会话变成一棵树的桌面工作台：任意一轮，随时分叉，每条分支都留着；搭配 aweswitch 用更顺手 — 用 profile 启动会话，再回来分叉它的历史。
- **[awedot](https://awedot.wehuman.top/)** — 悬浮球驻留屏幕边缘，实时追踪当前 AI 会话；一键收藏、随时恢复，并可搭配 aweswitch 固定 agent 配置（比如用 GLM 模型启动）。

### Project Collections

- **[Awesome AI Meets Biology](https://github.com/Webioinfo01/Awesome-AI-Meets-Biology)** — AI 在生物学、生物信息学和生物医学研究中应用的精选综述。由 awescholar 驱动。
- **[Awesome AI Virtual Tumor](https://github.com/Webioinfo01/Awesome-AI-Virtual-Tumor)** — 面向虚拟肿瘤建模与仿真的前沿 AI 系统精选合集：静态模型、动态模型、agent、基准与综述。

## 赞助与支持

如果 awescholar 帮到了你，欢迎支持一下：

- ⭐ 给项目点个 Star — 让更多人看到它。
- ☕ [Ko-fi](https://ko-fi.com/mugpeng) — 请我喝杯咖啡。
- 💬 微信 — 扫描下方收款码。

<p align="center">
  <img src="assets/images/wechat-pay.jpg" alt="微信收款码" width="240">
</p>

> 你的支持让项目持续维护下去 — 谢谢。
