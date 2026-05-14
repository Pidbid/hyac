# API 函数

API 函数 (Endpoint Function) 是您业务逻辑的入口，可以通过唯一的 URL 直接从外部访问。每个 API 函数都必须定义一个名为 `handler` 的异步函数。

`handler` 函数的参数非常灵活，但 `context` 是必需的第一个参数。

```python
async def handler(context, request):
    """
    一个基本的 API 函数，返回固定的 JSON 数据。
    """
    # 通过 context.request 同样可以访问请求对象
    # print(context.request.headers)
    return {"code": 0, "msg":"success", "data":[1,2,3]}
```

-   `context`: **(必需)** 上下文对象，包含了数据库连接、公共函数模块以及请求对象 (`context.request`) 等环境信息。
-   `request`: **(可选)** FastAPI 的请求对象。您可以直接在 `handler` 函数中注入它，也可以通过 `context.request` 来访问，两者效果相同。它包含了请求的详细信息，如请求头、查询参数等。

您还可以为 `handler` 函数定义额外的参数，这些参数会自动从请求的查询参数或请求体中获取，这依赖于 FastAPI 的依赖注入功能。

```python
# 省略 request 参数的写法
async def handler(context, name: str = "World"):
    """
    一个接收参数的 API 函数。
    如果请求中包含 'name' 参数 (如 ?name=Hyac)，它将被自动注入。
    """
    return {"hello": name}
