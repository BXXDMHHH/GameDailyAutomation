# GameDailyAutomation

Windows 本地游戏每日任务自动调度器。通过外部适配器串行调用用户已安装的 BetterGI（原神）和 March7th（崩坏：星穹铁道）。

## 文档
- [项目章程](docs/01-项目章程.md)
- [需求规格说明书](docs/02-需求规格说明书.md)
- [技术选型说明](docs/03-技术选型说明.md)
- [系统架构与流程](docs/04-系统架构与流程.md)
- [目录与代码规范](docs/05-目录与代码规范.md)
- [外部工具适配器说明](docs/06-外部工具适配器说明.md)
- [SQLite 状态管理说明](docs/07-SQLite状态管理说明.md)
- [每日任务编排与重试](docs/08-每日任务编排与重试.md)
- [Windows 系统集成与部署](docs/09-Windows部署说明.md)
- [AI 开发规范](AGENTS.md)

## 已确认基线
- 每天本机时间 17:00 后触发；错过后在登录/解锁时补检查。
- 顺序执行：BetterGI → March7th，不并行。
- 每个游戏最多尝试 2 次（首次 + 自动重试 1 次）。
- 锁屏或交互桌面不可用时不启动桌面自动化；每个游戏启动和重试前重新检查。
- SQLite 持久化每日状态，防止重复执行。
- 结果不明时标记 UNKNOWN，不盲目重试。

## 重要说明
Windows 计划任务以当前用户 InteractiveToken 运行，不使用 SYSTEM、不保存 Windows 密码。锁屏检测失败时按锁屏处理。锁屏发生在第三方子进程已经运行期间时，程序不会保证强制终止该进程，但会阻止启动后续游戏或重试。V1.0 不自动解锁 Windows、不处理验证码、不保存账号凭据，也不绕过游戏安全机制。

## 开发环境
要求 Python 3.12 或更高版本。在 Windows PowerShell 中执行：

~~~powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\install.ps1
~~~

安装后编辑 config/settings.json，填写本机已验证的工具路径和参数，再运行：

~~~powershell
.\scripts\register-task.ps1
.\.venv\Scripts\python.exe -m game_daily_automation --config config/settings.json --check-session
python -m unittest discover -s tests/unit -v
~~~

安装脚本不会启动真实游戏。任务计划程序定时、登录和解锁触发；程序只在达到配置时间且交互桌面可用时进入编排。更多安装、卸载、故障排查和安全边界见 [Windows 部署说明](docs/09-Windows部署说明.md)。
