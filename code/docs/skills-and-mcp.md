根据系统提示中的信息，我来整理完整的列表：
    
    
    
    MCP 工具（系统级挂载）
    
    MCP 服务器: codegraph
    工具名: codegraph_search
    功能: 快速符号搜索
    ────────────────────────────────────────
    MCP 服务器:
    工具名: codegraph_node
    功能: 获取符号详情（位置、签名、调用链）
    ────────────────────────────────────────
    MCP 服务器:
    工具名: codegraph_context
    功能: 综合任务上下文（入口点、相关符号、关键代码）
    ────────────────────────────────────────
    MCP 服务器:
    工具名: codegraph_explore
    功能: 批量探索多个相关符号源码
    ────────────────────────────────────────
    MCP 服务器:
    工具名: codegraph_files
    功能: 项目文件结构
    ────────────────────────────────────────
    MCP 服务器:
    工具名: codegraph_impact
    功能: 变更影响分析
    ────────────────────────────────────────
    MCP 服务器:
    工具名: codegraph_trace
    功能: 调用路径追踪
    ────────────────────────────────────────
    MCP 服务器:
    工具名: codegraph_callees
    功能: 查找被调用函数
    ────────────────────────────────────────
    MCP 服务器:
    工具名: codegraph_callers
    功能: 查找调用者
    ────────────────────────────────────────
    MCP 服务器:
    工具名: codegraph_status
    功能: 索引状态
    ────────────────────────────────────────
    MCP 服务器: context7
    工具名: resolve_library_id
    功能: 解析库名到 Context7 ID
    ────────────────────────────────────────
    MCP 服务器:
    工具名: query_docs
    功能: 查询库文档和代码示例
    ────────────────────────────────────────
    MCP 服务器: fetch
    工具名: fetch
    功能: 抓取网页内容（转 markdown）
    ────────────────────────────────────────
    MCP 服务器:
    工具名: get_prompt
    功能: 获取 MCP prompt
    ────────────────────────────────────────
    MCP 服务器:
    工具名: list_prompts
    功能: 列出可用 prompts
    ────────────────────────────────────────
    MCP 服务器: holographic
    工具名: fact_store
    功能: 写入记忆（add/update/remove）
    ────────────────────────────────────────
    MCP 服务器:
    工具名: fact_query
    功能: 查询记忆（search/probe/related/reason/contradict/list）
    ────────────────────────────────────────
    MCP 服务器:
    工具名: fact_feedback
    功能: 记忆反馈（helpful/unhelpful）
    ────────────────────────────────────────
    MCP 服务器: sequential_thinking
    工具名: sequentialthinking
    功能: 多步推理思维链
    
    
    
    Skills（114 个）
    
    autonomous-ai-agents（5 个）
    | Skill             | 功能                                  |
    |-------------------|---------------------------------------|
    | claude-code       | 委派编码给 Claude Code CLI            |
    | codex             | 委派编码给 OpenAI Codex CLI           |
    | hermes-agent      | 配置、扩展 Hermes Agent               |
    | kanban-codex-lane | Kanban worker 使用 Codex 作为实现通道 |
    | opencode          | 委派编码给 OpenCode CLI               |
    
    creative（18 个）
    | Skill                     | 功能                           |
    |---------------------------|--------------------------------|
    | architecture-diagram      | 深色主题 SVG 架构图            |
    | ascii-art                 | ASCII 艺术（pyfiglet, cowsay） |
    | ascii-video               | 视频转 ASCII                   |
    | baoyu-article-illustrator | 文章插图                       |
    | baoyu-comic               | 知识漫画                       |
    | baoyu-infographic         | 信息图（21 布局 × 21 风格）    |
    | claude-design             | HTML 设计原型                  |
    | clawd-on-desk             | Clawd 桌面宠物                 |
    | comfyui                   | ComfyUI 图像/视频/音频生成     |
    | design-md                 | Google DESIGN.md 规范          |
    | excalidraw                | 手绘风格图表                   |
    | humanizer                 | 文本人性化                     |
    | ideation                  | 创意约束生成项目想法           |
    | manim-video               | Manim 数学动画                 |
    | p5js                      | p5.js 生成艺术                 |
    | pixel-art                 | 像素艺术                       |
    | popular-web-designs       | 54 种真实设计系统              |
    | pretext                   | DOM-free 文本布局              |
    | sketch                    | 快速 HTML 原型                 |
    | songwriting-and-ai-music  | 歌曲创作 + Suno AI             |
    | touchdesigner-mcp         | TouchDesigner 控制             |
    
    data-science（2 个）
    | Skill                       | 功能                        |
    |-----------------------------|-----------------------------|
    | jupyter-live-kernel         | Jupyter 实时内核迭代 Python |
    | physics-simulation-datasets | 物理仿真数据集生成          |
    
    devops（4 个）
    | Skill                   | 功能                  |
    |-------------------------|-----------------------|
    | kanban-orchestrator     | Kanban 编排           |
    | kanban-worker           | Kanban worker 指南    |
    | webhook-subscriptions   | Webhook 事件驱动      |
    | wsl-windows-environment | WSL2/Windows 环境配置 |
    
    email（1 个）
    | Skill    | 功能                  |
    |----------|-----------------------|
    | himalaya | CLI 邮件（IMAP/SMTP） |
    
    gaming（2 个）
    | Skill                    | 功能                 |
    |--------------------------|----------------------|
    | minecraft-modpack-server | Minecraft Mod 服务器 |
    | pokemon-player           | Pokemon 游戏自动化   |
    
    github（6 个）
    | Skill                  | 功能                    |
    |------------------------|-------------------------|
    | codebase-inspection    | 代码库检查（LOC、语言） |
    | github-auth            | GitHub 认证             |
    | github-code-review     | PR 代码审查             |
    | github-issues          | Issue 管理              |
    | github-pr-workflow     | PR 工作流               |
    | github-repo-management | 仓库管理                |
    
    mcp（1 个）
    | Skill      | 功能           |
    |------------|----------------|
    | native-mcp | MCP 客户端配置 |
    
    media（5 个）
    | Skill           | 功能             |
    |-----------------|------------------|
    | gif-search      | GIF 搜索下载     |
    | heartmula       | Suno 式歌曲生成  |
    | songsee         | 音频频谱分析     |
    | spotify         | Spotify 控制     |
    | youtube-content | YouTube 转录处理 |
    
    messaging（1 个）
    Skill: messaging-gateway-integrations
    功能: 消息网关集成（Telegram/Discord/WeChat）
    
    mlops（10 个）
    | Skill                       | 功能                |
    |-----------------------------|---------------------|
    | audiocraft-audio-generation | AudioCraft 音频生成 |
    | dspy                        | DSPy 声明式 LM 程序 |
    | evaluating-llms-harness     | LLM 基准测试        |
    | huggingface-hub             | HuggingFace CLI     |
    | llama-cpp                   | llama.cpp 本地推理  |
    | ml-training-workflows       | ML 训练工作流       |
    | obliteratus                 | LLM 去审查化        |
    | segment-anything-model      | SAM 图像分割        |
    | serving-llms-vllm           | vLLM 高吞吐推理     |
    | weights-and-biases          | W&B 实验追踪        |
    
    note-taking（1 个）
    | Skill    | 功能              |
    |----------|-------------------|
    | obsidian | Obsidian 笔记管理 |
    
    productivity（14 个）
    | Skill                  | 功能                |
    |------------------------|---------------------|
    | Excel                  | Excel 电子表格      |
    | PowerPoint             | PowerPoint 演示文稿 |
    | airtable               | Airtable API        |
    | google-workspace       | Google 全家桶       |
    | ielts-speaking-prep    | IELTS 口语准备      |
    | linear                 | Linear 项目管理     |
    | maps                   | 地图/路线/时区      |
    | nano-pdf               | PDF 文本编辑        |
    | notion                 | Notion API          |
    | ocr-and-documents      | OCR 文档提取        |
    | powerpoint             | PowerPoint 操作     |
    | teams-meeting-pipeline | Teams 会议摘要      |
    
    red-teaming（1 个）
    | Skill   | 功能     |
    |---------|----------|
    | godmode | LLM 越狱 |
    
    research（8 个）
    | Skill                     | 功能                         |
    |---------------------------|------------------------------|
    | arxiv                     | arXiv 论文搜索               |
    | blogwatcher               | 博客/RSS 监控                |
    | chinese-platform-research | 中国平台调研（小红书、知乎） |
    | literature-survey         | 深度文献调研                 |
    | llm-wiki                  | LLM Wiki 知识库              |
    | ml-model-evaluation       | ML 模型评估                  |
    | polymarket                | Polymarket 查询              |
    | research-paper-writing    | ML 论文写作                  |
    
    smart-home（1 个）
    | Skill   | 功能                 |
    |---------|----------------------|
    | openhue | Philips Hue 灯光控制 |
    
    social-media（1 个）
    | Skill | 功能          |
    |-------|---------------|
    | xurl  | X/Twitter CLI |
    
    software-development（16 个）
    | Skill                                 | 功能                |
    |---------------------------------------|---------------------|
    | chrome-cdp-setup                      | Chrome CDP 调试端口 |
    | debugging-hermes-tui-commands         | Hermes TUI 调试     |
    | hermes-agent-skill-authoring          | Skill 编写规范      |
    | implementation-verification-workflows | 实现验证            |
    | mcp-server-development                | MCP 服务器开发      |
    | node-inspect-debugger                 | Node.js 调试        |
    | parallel-subagent-dispatch            | 并行子代理调度      |
    | plan                                  | 计划模式            |
    | python-debugpy                        | Python 调试         |
    | requesting-code-review                | 提交前审查          |
    | spike                                 | 快速实验            |
    | subagent-driven-development           | 子代理驱动开发      |
    | systematic-debugging                  | 系统化调试          |
    | test-driven-development               | TDD                 |
    | writing-plans                         | 编写实现计划        |
    
    superpowers（10 个）
    | Skill                          | 功能                       |
    |--------------------------------|----------------------------|
    | brainstorming                  | 头脑风暴（创意工作前必用） |
    | dispatching-parallel-agents    | 并行代理调度               |
    | executing-plans                | 执行计划                   |
    | finishing-a-development-branch | 完成开发分支               |
    | receiving-code-review          | 接收代码审查反馈           |
    | using-git-worktrees            | Git worktree 隔离          |
    | using-superpowers              | 建立工作方式               |
    | verification-before-completion | 完成前验证                 |
    | writing-skills                 | 编写 Skill                 |
    
    其他（8 个）
    | Skill      | 功能                   |
    |------------|------------------------|
    | docx       | Word 文档操作          |
    | dogfood    | Web 应用 QA            |
    | pdf        | PDF 操作               |
    | playwright | 浏览器自动化           |
    | pptx       | PowerPoint 操作        |
    | web-access | 网络访问（CDP 浏览器） |
    | xlsx       | 电子表格操作           |
    | yuanbao    | 元宝群组管理           |
    
    
    
    总计：5 个 MCP 服务器，114 个 Skills