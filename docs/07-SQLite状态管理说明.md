# SQLite 状态管理说明（阶段 4）

## 1. 文件与职责

- `infrastructure/state_store.py`：SQLite schema 初始化、状态查询、事务写入、尝试次数控制和重启恢复。
- `infrastructure/single_instance.py`：使用操作系统 advisory lock 防止同一应用被并发启动。
- `tests/unit/test_state_store.py`、`tests/unit/test_single_instance.py`：只使用临时目录和 SQLite 测试库，不启动游戏程序。

数据库位置由配置中的 `storage.database_path` 决定；默认示例为 `%LOCALAPPDATA%/GameDailyAutomation/data.sqlite3`。模块会创建数据库父目录，不在代码中写入用户专属绝对路径。

## 2. 数据库结构

### daily_tasks

每个本地执行日期一条记录，主键为 `execution_date`。

| 字段 | 类型 | 用途 |
|---|---|---|
| execution_date | TEXT PRIMARY KEY | ISO 日期（YYYY-MM-DD） |
| status | TEXT | 当日总状态：pending/running/success/failed/unknown/interrupted |
| created_at | TEXT | 创建时间（UTC ISO-8601） |
| updated_at | TEXT | 最近更新时间（UTC ISO-8601） |
| error_message | TEXT NULL | 最近的总任务错误/恢复说明 |

### game_executions

每次游戏执行一条记录，按 `execution_date + game_name + attempt_number` 唯一约束。

| 字段 | 类型 | 用途 |
|---|---|---|
| id | INTEGER PRIMARY KEY | 记录 ID |
| execution_date | TEXT | 关联 daily_tasks |
| game_name | TEXT | bettergi / march7th |
| attempt_number | INTEGER | 第 1 或第 2 次尝试 |
| status | TEXT | pending/running/success/failed/unknown/interrupted |
| started_at | TEXT NULL | 启动时间 |
| finished_at | TEXT NULL | 结束/恢复时间 |
| error_message | TEXT NULL | 失败或不确定原因 |
| process_id | INTEGER NULL | 外部进程 PID |
| return_code | INTEGER NULL | 进程退出码（仅证据之一） |

数据库启用外键、WAL 和 `synchronous=FULL`；写入使用 `BEGIN IMMEDIATE`，避免两个实例同时分配同一尝试序号。schema 使用 `PRAGMA user_version=1` 标记版本。

## 3. 推荐调用顺序

```python
from datetime import date

from game_daily_automation.domain.enums import ExecutionStatus
from game_daily_automation.infrastructure.state_store import SQLiteStateStore
from game_daily_automation.infrastructure.single_instance import SingleInstanceLock

store = SQLiteStateStore(config.storage.database_file_path)
store.initialize()

# 程序启动后先处理遗留 RUNNING；恢复结果为 UNKNOWN，不能自动重试。
store.recover_interrupted()

with SingleInstanceLock(config.storage.log_directory_path / "app.lock"):
    day = date.today()
    store.ensure_daily_task(day)

    # 必须先持久化 RUNNING，再调用 ProcessRunner / 外部游戏程序。
    attempt = store.start_attempt(day, "bettergi")
    result = bettergi_adapter.execute_daily()
    store.finish_attempt(
        day, "bettergi", map_result(result.status),
        error_message=result.detail,
        process_id=result.process_id,
        return_code=result.return_code,
    )

    # March7th 依照相同模式执行。两款游戏记录彼此独立。
    # 两款游戏均 SUCCESS 后才允许完成当天总任务：
    store.complete_daily_task(day)
```

示例中的 `map_result` 是调用方映射逻辑占位说明，并非项目已提供的函数；实际集成必须显式把适配器结果映射到 `ExecutionStatus`。

## 4. 防重复与恢复规则

- 每款游戏每日最多两次尝试；数据库唯一约束和事务共同防止并发分配重复 attempt。
- 同一游戏当天已有 SUCCESS 时，后续启动会被拒绝。
- 第二次尝试必须同时满足：上次状态明确为 FAILED、调用方传入 `safe_to_retry=True`、未超过两次上限。
- UNKNOWN、INTERRUPTED、RUNNING 均拒绝自动重试。UNKNOWN/INTERRUPTED 需要人工检查日志和工具运行记录。
- 应用重启时，遗留 RUNNING 尝试被更新为 UNKNOWN，并附加恢复说明；不假设外部进程一定已退出或任务一定失败。
- 一款游戏成功不会自动把 daily_tasks 标记为 SUCCESS。只有 `complete_daily_task` 检查所有必需游戏的最新尝试均成功后，才会标记当天总任务成功。
- 数据库初始化/事务提交失败会抛出 `StatePersistenceError`。调用方必须在数据库写入成功前禁止启动外部进程；不能吞掉异常并继续执行。

## 5. 单实例保护

`SingleInstanceLock` 对锁文件持有 OS 级非阻塞锁：Windows 使用 `msvcrt.locking`，POSIX 使用 `fcntl.flock`。锁在进程崩溃/退出后由操作系统释放；锁文件本身可保留。锁文件应放在本地用户数据目录，不应放到网络共享盘。

## 6. 当前验收边界

本阶段已提交 SQLite 模块、单实例锁、表结构说明和单元测试代码。当前尚未在用户的 Windows/Python 3.12 环境执行测试，也未将 StateStore 接入主调度器。验收仍需执行完整单元测试，并验证目标环境的 Windows 文件锁行为及数据库异常时“写入失败即不启动游戏”的集成路径。
