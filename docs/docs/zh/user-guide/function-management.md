# 函数管理

函数管理页是编写、测试、发布和排查函数的主要工作区。Hyac 当前面向 Python 函数，函数代码运行在应用专属的 Docker 运行时容器内。

![函数管理](../../assets/user-guide/function-management.png)

函数管理页采用三栏布局：左侧是函数列表，中间是函数代码编辑器和实时日志，右侧是函数测试与定时任务面板。

## 函数类型

Hyac 中常见的函数包括：

- 端点函数：可以通过外部 URL 调用，是业务入口。
- 公共函数：供其他函数复用，不能直接作为外部入口调用。

端点函数的外部调用格式为：

```text
https://<app_id>.<DOMAIN_NAME>/<function_id>
```

## 创建函数

进入“函数管理”页面后，选择当前应用，再创建函数。

建议填写：

- 函数名称：给人看的名称，便于列表识别。
- 函数 ID：用于访问路径，应保持稳定。
- 函数类型：端点函数或公共函数。
- 描述和标签：用于后续筛选、维护和交接。
- 函数代码：必须包含入口函数。

端点函数通常使用 `async def handler(ctx, request)` 作为入口：

```python
async def handler(ctx, request):
    return {"code": 0, "msg": "success", "data": {"app": ctx.app_id}}
```

`ctx` 是 Hyac 注入的运行上下文，包含数据库、对象存储、环境变量、公共函数、通知和日志能力。新函数推荐通过稳定门面 `ctx.cloud` 访问这些资源；旧的 `ctx.db`、`ctx.s3`、`ctx.env`、`ctx.logger`、`ctx.common` 等入口仍保持兼容。

常用入口：

| 能力 | 推荐入口 | 兼容入口 |
|------|----------|----------|
| 异步数据库 | `ctx.cloud.database()` | `ctx.db`, `ctx.async_db` |
| 同步数据库 | `ctx.cloud.database(sync=True)` | `ctx.sync_db`, `ctx.pymongo_db` |
| 对象存储 | `ctx.cloud.storage()` | `ctx.s3` |
| 环境变量 | `ctx.cloud.env()` | `ctx.env` |
| 日志 | `ctx.cloud.logger()` | `ctx.logger` |
| 通知 | `ctx.cloud.notification()` | `ctx.notification` |
| 公共函数 | `ctx.cloud.common()` | `ctx.common` |

## 编辑和保存

函数详情页左侧为函数列表，中间为代码编辑区，右侧为测试和任务相关面板。

编辑代码后需要保存。保存后，运行时会通过缓存监听加载最新函数代码。多数情况下不需要重启整个系统。

如果依赖或运行时状态发生变化，建议重启当前应用运行时再测试。环境变量会由运行时监听器动态加载，不需要重启。

## 调用和测试

开发阶段推荐先使用函数详情页的测试功能。测试面板会帮助你发起一次函数调用，并展示响应结果。

外部集成时使用标准域名：

```bash
curl -X POST "https://<app_id>.<DOMAIN_NAME>/<function_id>"
```

如果使用开发环境，默认访问地址通常是：

```text
https://console.localhost
https://server.localhost
https://<app_id>.localhost/<function_id>
```

## 日志

函数详情页的日志区域展示当前应用运行时容器的实时输出。实时日志来自 Docker runtime stdout/stderr，而历史记录来自系统保存的函数调用数据。

调试时建议同时看控制台日志和容器日志：

```bash
docker logs -f hyac-app-runtime-<app_id小写>
```

在函数代码中可以使用：

```python
async def handler(ctx, request):
    logger = ctx.cloud.logger()
    logger.info("function started")
    return {"ok": True}
```

## 依赖管理

应用可以配置 Python 依赖。运行时容器启动时会安装当前应用需要的依赖。

使用建议：

- 优先添加明确包名和版本，避免未来版本变化导致函数行为漂移。
- 新增依赖后，如果当前应用运行时已经启动，重启应用运行时再测试。
- 避免在函数执行过程中动态安装依赖。

## 环境变量

应用环境变量会注入到运行时进程中。函数内推荐通过 `ctx.cloud.env()` 读取或更新：

```python
async def handler(ctx, request):
    env = ctx.cloud.env()
    api_key = env.get("API_KEY")
    return {"configured": bool(api_key)}
```

更新环境变量：

```python
async def handler(ctx, request):
    env = ctx.cloud.env()
    await env.set("FEATURE_FLAG", "enabled")
    return {"ok": True}
```

注意：环境变量属于应用级配置。不要把不同应用或不同环境的密钥混用。

控制台或函数代码更新环境变量后，当前应用运行时会动态刷新环境，不需要重启应用。

## 公共函数

公共函数适合放置可复用逻辑，例如签名校验、数据转换、第三方服务封装。

示例公共函数 `math_utils`：

```python
def add(a, b):
    return a + b
```

端点函数中调用：

```python
async def handler(ctx, request):
    common = ctx.cloud.common()
    value = common.math_utils.add(1, 2)
    return {"value": value}
```

## 定时任务

函数管理页包含定时任务相关面板。适合把函数作为周期任务执行，例如同步数据、清理临时文件、生成报表。

配置定时任务前，先确认函数可以手动测试通过。定时任务失败时，优先查看函数日志和运行时容器日志。

## 历史版本

函数历史用于回看代码变更。修改重要函数前，建议确认当前版本已经保存，并为变更添加清晰描述。

如果新版本出现问题，可以参考历史版本恢复代码。

## AI 助手

函数编辑区可能包含 AI 助手入口。AI 生成的代码仍需要人工检查和测试，尤其是数据库写入、外部请求、密钥处理和异常处理逻辑。

## 常见问题

### 保存后调用的还是旧逻辑

检查是否保存成功，再查看运行时容器是否已经加载最新代码。必要时重启当前应用运行时。

### 日志面板没有输出

确认函数是否真的被执行。实时日志来自运行时容器，容器未启动或函数未触发时不会有输出。

### 外部调用 404

检查 `app_id`、`DOMAIN_NAME` 和 `function_id`。应用子域名和函数路径都必须正确。
