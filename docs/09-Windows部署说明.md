# 阶段 6：Windows 系统集成与部署

## 运行模型

- 任务计划程序以当前用户的 InteractiveToken 运行，不使用 SYSTEM、保存密码或提升权限。
- 每日 17:00 触发，并配置用户登录、会话解锁触发；17:00 后每 5 分钟补充检查，直到当日触发周期结束。
- 每次启动都是一次性检查：读取本机时间，未到配置时间则不执行；锁屏或桌面不可用则退出，等待下一次触发。
- 任务计划程序的多实例策略为 IgnoreNew；程序自身另持有 SQLite 同目录的单实例锁。
- 当天成功的游戏跳过；UNKNOWN、INTERRUPTED、RUNNING 不会被盲目重跑。
- 每次游戏启动和自动重试前都重新检查交互桌面。锁屏后不会启动下一款游戏或重试。
- 不自动解锁 Windows，不保存密码，不处理验证码，不绕过反作弊。

## 会话检测边界

system/windows_session.py 使用 Windows WTS 会话状态和当前输入桌面名称。只有当前进程会话处于活动状态且输入桌面名称为 Default 才允许启动。Winlogon、安全桌面、断开会话、API 错误及非 Windows 平台均 fail-closed。此检测是启动门禁，不是对第三方程序运行期间锁屏行为的强制终止保证；锁屏发生在第三方程序执行期间时，当前子进程可能继续运行，但程序会在下一项任务/重试前重新检查。

## 安装

在当前 Windows 用户的 PowerShell 中进入项目根目录：

~~~powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\install.ps1
~~~

首次安装会建立 .venv、安装本项目，并在缺少配置时复制示例配置。编辑 config/settings.json，填写本机已验证的可执行文件路径和参数。默认空参数不会启动第三方任务。随后重新注册任务：

~~~powershell
.\scripts\register-task.ps1
~~~

安装不启动真实游戏。任务运行在当前用户交互式登录会话中；电脑关机或用户未登录时不能保证执行。唤醒电脑后由任务计划程序补充触发。

## 检查与手动运行

~~~powershell
.\.venv\Scripts\python.exe -m game_daily_automation --config config/settings.json --check-session
.\.venv\Scripts\python.exe -m game_daily_automation --config config/settings.json
~~~

第二条命令会在已解锁且达到设定时间时执行编排流程。请勿在配置真实 CLI 参数后随意手动运行。

## 卸载

~~~powershell
.\scripts\uninstall.ps1
~~~

卸载只删除任务计划程序注册项，保留配置、SQLite 数据库、日志和虚拟环境。需要完全清理时，请在卸载后自行备份并删除这些文件。

## 故障排查

- 任务未运行：检查任务计划程序历史记录、当前用户是否登录、Python 路径和配置文件。
- 锁屏时没有运行：这是预期保护行为；解锁后由 SessionUnlock 或周期触发再次检查。
- UNKNOWN / INTERRUPTED：查看日志、SQLite 尝试记录和第三方工具状态；完成证据核验后再人工处理，禁止直接删除数据库强制重跑。
- 重复启动：检查任务计划程序的 IgnoreNew 策略和应用单实例锁文件。
- Windows API 检测失败：程序按锁屏处理，不会启动桌面任务。
