# GameDailyAutomation

Windows 本地游戏每日任务自动调度器。V1.0 通过外部适配器串行调用 BetterGI（原神）和 March7th（崩坏：星穹铁道）。

## 文档
- [项目章程](docs/01-项目章程.md)
- [需求规格说明书](docs/02-需求规格说明书.md)
- [技术选型说明](docs/03-技术选型说明.md)
- [系统架构与流程](docs/04-系统架构与流程.md)
- [目录与代码规范](docs/05-目录与代码规范.md)
- [外部工具适配器说明](docs/06-外部工具适配器说明.md)
- [SQLite 状态管理说明](docs/07-SQLite状态管理说明.md)
- [AI 开发规范](AGENTS.md)

## 已确认基线
- 每天本机时间 17:00 后触发；错过后在登录/解锁时补检查。
- 顺序执行：BetterGI → March7th，不并行。
- 每个游戏最多尝试 2 次（首次 + 自动重试 1 次）。
- 锁屏时不启动依赖交互桌面的自动化；解锁后恢复检查。
- 单个游戏最终失败不阻止另一个游戏执行。
- SQLite 持久化每日状态，防止重复执行。
- 结果不明时标记 UNKNOWN，不盲目重试。

## 重要说明
第三方 CLI 参数、任务标识、日志结果识别方式必须以本机安装版本为准，接入时先查看帮助、列出任务并单独试运行。进程退出不等于游戏任务成功。V1.0 不自动解锁 Windows、不处理验证码、不保存账号凭据，也不绕过游戏安全机制。

## 开发环境

要求 Python 3.12 或更高版本。基础工程仅使用 Python 标准库，不需要安装运行时第三方依赖。

在 Windows PowerShell 中执行：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
Copy-Item config/settings.example.json config/settings.json
python -m game_daily_automation --config config/settings.json
python -m unittest discover -s tests/unit -v
```

配置文件缺失或格式错误时，程序会给出明确提示。个人配置 config/settings.json 不纳入 Git。相对运行数据路径默认使用 %LOCALAPPDATA%/GameDailyAutomation，避免将数据库和日志写入源码目录。

当前 CLI 入口只加载配置并初始化控制台/文件日志，不会启动游戏任务。阶段 2 的适配器代码可由单元测试用 FakeProcessRunner 验证；真实工具运行仍需完成 [本机验证清单](docs/06-外部工具适配器说明.md)。
