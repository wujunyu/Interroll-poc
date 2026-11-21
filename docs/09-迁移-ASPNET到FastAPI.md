# 从 ASP.NET Core 迁到 FastAPI：一张对照表

> 用途：团队是 .NET 栈（我们用了 log4net），要维护/新建 Python 服务时的**心智映射**。
> 只列"你会下意识怎么写"和"这边该怎么写"的差别，不科普两边的基础语法。

## 一、先记住三个心智差异

| # | ASP.NET Core | FastAPI | 影响 |
|---|---|---|---|
| 1 | 启动时**注册**一切（DI 容器、中间件管道） | 用**函数参数**声明依赖，运行时注入 | 不用写 `services.AddXxx()` 那一大段 |
| 2 | 控制器返回 `IActionResult` / `ActionResult<T>` | 直接 `return` 对象，异常抛出去 | 错误处理从"返回码"变成"异常 + handler" |
| 3 | `async/await` 是真的异步 IO | `async def` 也是，但**同步函数会被丢到线程池** | 别在 `async def` 里调同步阻塞库 |

## 二、逐项对照

| 能力 | ASP.NET Core | FastAPI | 备注 |
|---|---|---|---|
| 项目入口 | `Program.cs` + `WebApplication.CreateBuilder` | `app = FastAPI()` | 一个文件就能起服务 |
| 路由 | `[HttpGet("/api/zones")]` | `@app.get("/api/zones")` | 装饰器，路径即约定 |
| 路由分组 | `MapGroup` / 控制器 | `APIRouter(prefix="/api")` | 等价 |
| 依赖注入 | `builder.Services.AddScoped<T>()` + 构造函数 | `def handler(dep: Annotated[T, Depends(get_t)])` | 生命周期靠 `yield` 依赖 |
| 请求模型 | `record` / `[FromBody]` | Pydantic `BaseModel` | 校验 + 文档一体 |
| 参数校验 | `[Required]` `[Range]` | `Field(gt=0)` `Query(...)` | 校验失败自动 422 |
| 响应序列化 | `System.Text.Json`（默认 camelCase） | 直接返回 dict/模型（默认保持字段名） | **命名风格要注意** |
| OpenAPI | Swashbuckle | 内置 `/docs` `/openapi.json` | 由类型自动生成 |
| 中间件 | `app.UseXxx()` 管道 | `@app.middleware("http")` / `add_middleware` | 顺序仍是从外到内 |
| 异常处理 | `UseExceptionHandler` + ProblemDetails | `@app.exception_handler(E)` | 返回结构可自定义 |
| 配置 | `appsettings.json` + `IOptions<T>` | `pydantic-settings` / `os.environ` | 容器里通常直接用环境变量 |
| 日志 | `ILogger<T>` + Serilog sink | `logging` / `structlog` | 结构化日志要自己配 Formatter |
| 健康检查 | `AddHealthChecks().AddNpgSql()` | 手写 `/healthz` 返回 JSON | 见 `code/api/main.py` |
| 后台任务 | `BackgroundService` / `IHostedService` | `asyncio.create_task` / `lifespan` | 注意取消与优雅退出 |
| 定时任务 | `PeriodicTimer` | `asyncio.sleep` 循环 | 同上 |
| WebSocket | `app.UseWebSockets()` + 循环 | `@app.websocket("/ws/live")` | FastAPI 更直接 |
| 实时推送（SingalR） | SignalR（自带重连/组） | 原生 WebSocket，重连自己写 | 这是我们选原生 WS 的原因 |
| ORM | EF Core | SQLAlchemy（或直接用 psycopg） | 我们直接写 SQL，省一层 |
| 迁移 | `dotnet ef migrations` | Alembic | 我们只有 `init.sql` |
| 测试 | xUnit + `WebApplicationFactory` | pytest + `TestClient` | 后者更轻 |
| 打包 | `dotnet publish` | 镜像 + `python main.py` | 见 `Containerfile` |

## 三、六段代码对照

### 1) 一个端点

```csharp
// ASP.NET Core
[ApiController]
[Route("api")]
public class ZonesController : ControllerBase {
    [HttpGet("zones")]
    public async Task<ActionResult<List<ZoneDto>>> Get() => await _svc.ListAsync();
}
```

```python
# FastAPI
@app.get("/api/zones")
async def zones() -> list[dict]:
    return await db.list_zones()
```

### 2) 依赖注入

```csharp
builder.Services.AddSingleton<IDb, PgDb>();
public ZonesController(IDb db) { _db = db; }
```

```python
def get_db() -> Db:          # 依赖
    return Db(DSN)

@app.get("/api/zones")
def zones(db: Annotated[Db, Depends(get_db)]): ...
```

### 3) 请求体校验

```csharp
public record SampleRequest([Required] string Zone, [Range(0, 10)] double Speed);
```

```python
class SampleRequest(BaseModel):
    zone: str
    speed: float = Field(ge=0, le=10)
```

### 4) 后台常驻任务

```csharp
public class IngestWorker : BackgroundService {
    protected override async Task ExecuteAsync(CancellationToken ct) {
        while (!ct.IsCancellationRequested) { await FlushAsync(); await Task.Delay(1000, ct); }
    }
}
```

```python
async def ingest_loop() -> None:
    while True:
        await flush()
        await asyncio.sleep(1)
# 在 lifespan 里 create_task，退出时 cancel + await
```

### 5) 健康检查

```csharp
builder.Services.AddHealthChecks().AddNpgSql(conn);
app.MapHealthChecks("/healthz");
```

```python
@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "db": db_ok(), "version": VERSION}
```

### 6) 结构化日志

```csharp
Log.Logger = new LoggerConfiguration().WriteTo.Console(new JsonFormatter()).CreateLogger();
```

```python
handler = logging.StreamHandler(); handler.setFormatter(JsonFormatter())
logging.basicConfig(handlers=[handler], level="INFO")
```

## 四、迁移时最容易踩的五个坑

| 坑 | 现象 | 解法 |
|---|---|---|
| 在 `async def` 里调同步库 | 整个事件循环被阻塞 | 用 `def`（FastAPI 自动丢线程池）或换异步驱动 |
| 依赖生命周期 | 连接被复用/泄漏 | 用 `yield` 依赖，请求结束自动关闭 |
| 字段命名 | 前端拿到 `zone_id` 而不是 `zoneId` | 明确 camelCase 输出或在 Pydantic 里配 alias |
| 异常语义 | 500 泄露堆栈 | 加 `exception_handler` + 统一错误结构 |
| 优雅退出 | 收到 SIGTERM 丢最后一批 | 见 ingest 的 `_on_sigterm` + flush |

## 五、我们这套代码里的对应

| 本项目 | 位置 | 对应 .NET 的什么 |
|---|---|---|
| 路由与服务 | `code/api/main.py` | Controller + Service |
| 后台采集循环 | `code/ingest/main.py` `main()` | `BackgroundService.ExecuteAsync` |
| 依赖获取 | `get_conn()` | `AddScoped<IDbConnection>` |
| 健康检查 | `/healthz`（api / ingest 各一个） | `MapHealthChecks` |
| 日志 | `log_setup.py` | Serilog + JsonFormatter |
| 优雅退出 | `_on_sigterm` | `IHostApplicationLifetime.ApplicationStopping` |
| 配置 | `os.environ` | `IConfiguration` |
