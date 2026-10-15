# 架构与边界

## 依赖方向

`Frontend → preload 白名单 → Electron main → HTTP API → Services → Repositories → SQLite`

桌面主进程承担后端进程生命周期。API 只校验参数、调用服务、序列化响应；服务不依赖 HTTP。SQLite 是业务状态的唯一来源。基础表包括 projects、documents、document_assets、chat_sessions、messages、scan_drafts；问答、方案、任务、记录、修订和插件配置通过后续迁移增加。

## 启动与退出

1. Electron 获得单实例锁。
2. 使用项目虚拟环境启动 `python -m backend.runner`，绑定回环随机空闲端口。
3. Python 初始化 SQLite WAL 和 Alembic，Uvicorn 就绪后通过 stdout 发出端口通知。
4. 主进程通过健康检查，再创建隔离的窗口。
5. 关闭窗口时向子进程 stdin 发送退出指令，等待 Uvicorn 生命周期清理。超过 5 秒才强制终止本次启动的子进程。
6. 父进程异常退出时，stdin EOF 触发后端退出。

## 安全边界

- 后端仅监听 `127.0.0.1`，每次启动生成随机访问令牌，不记录到数据库或前端。
- Renderer 不启用 Node，启用 context isolation 和 sandbox；preload 仅暴露 `health()`、`chooseFolder()` 及受限 `request()`。主进程根据操作枚举生成白名单路由，不允许前端传入 URL、认证头或任意 HTTP 方法。Vue 代理数据在 IPC 边界转换为普通 JSON。
- 禁止新窗口、任意页面导航和权限请求。生产静态页面通过 CSP 限制资源；开发允许本地 Vite WebSocket。
- 不启用 CORS，Swagger/OpenAPI 公网式访问入口关闭。
- 访问令牌是本地进程隔离措施，不防御已控制同一操作系统账户的攻击者。
- 阶段 3 再引入模型密钥和 Electron safeStorage；当前没有模型密钥输入或保存逻辑。

## 扩展约束

后续 Agent、解析、提取、工具和插件模块按实际阶段创建，不提前制造空实现。Core 禁止依赖 API/Service/Frontend；Agent 禁止直接访问数据库和文件。QA、Design、Extract 独立。Schema 和证据版本化，人工复核追加版本。插件通过 Hook 扩展，不改核心数据库。

## 数据迁移

`backend/db/migrations/versions` 保存迁移。启动时使用程序化 Alembic API 和同一数据库连接升级。`0001_baseline` 为无业务表的初始版本。新增表需同时更新 ORM 模型和迁移，禁止运行时 `create_all` 绕过迁移。

`0002_workspace` 增加阶段 1 业务表及级联外键；资产与文献、消息与会话使用复合外键约束项目归属。测试包含阶段 0 升级和 ORM/迁移一致性检查。

## 扫描事务与隔离

扫描器只读取文件，采用块读取计算 SHA-256，检查读前读后元数据，并跳过目录链接和文件链接。服务保留已确认分组、生成新增文件建议。预览独立保存在 scan_drafts，不在扫描期间变更正式索引。

确认时校验文件集合完整、不重复、主论文归属正确，再重新扫描核验指纹；仓储在同一事务中检查项目修订号和预览 ID、更新索引并删除预览。重复确认、过期预览和扫描失败不会部分写入正式结果。缺失资产保留元数据，不删除源文件。

所有会话和消息查询都带项目 ID。前端请求缓存键包含项目/会话 ID，切换工作区重新挂载内容组件；不使用 localStorage 保存业务状态。当前消息类型固定为 note，问答与提取留给后续独立流程。

API 在方案基础上将会话、消息、文献详情统一嵌套在 `/api/projects/{project_id}/...`，使项目归属检查显式化。新增 PATCH 项目/会话、DELETE 会话、GET 扫描预览以及 POST 扫描确认。文件夹选择在 Electron 主进程执行。

## 当前交付边界

源码开发启动和构建预览已设计；Python 打包、安装程序、升级回滚和签名属于阶段 7。`npm run build` 不生成可分发的 Windows 安装包。

## 阶段 2：解析与证据阅读

`backend/parsers/docling_adapter.py` 是 Docling 的唯一适配边界，外部类型不进入 Core。统一输出 `ParsedContent`（版本 1），保存章节、段落、表格单元格及来源位置；PDF bbox 转为左上角原点、0–1 归一化坐标，非 PDF 不使用虚构的物理页码。

`0003_parsed_assets` 保存资产级解析状态、运行标识、源 SHA-256、解析器版本与 OCR 设置。API 验证项目归属和源文件指纹，解析前后复核源文件；结果原子写入 `projects/{project_id}/parsed/{asset_id}/{run_id}.json`。重复提交复用正在运行的任务，过期运行不能覆盖新结果；重启将 queued/running 标为 interrupted。当前单线程执行器串行解析，独立 Worker、进度和取消留到阶段 4。

原文通过受限 IPC 获取二进制 PDF，不给 Renderer 任意文件路径访问或后端令牌。PDF.js worker、字体、CMap 与 WASM 由构建脚本复制为本地资源。Reader 支持文字层、页码、缩放及 bbox 叠加；缓存键包含项目、资产、源指纹或解析运行标识。文档内容仅作文本呈现，不注入 HTML。后台窗口继续轮询解析状态。

默认 CPU，禁用 Docling 外部插件与远程服务；PDF 布局/TableFormer 权重及 EasyOCR 中英文权重由 `scripts/prepare_models.py` 准备。Docling 2.135.0 的 RapidOCR 下载器与已发布的 RapidOCR 3.10.0 API 不兼容，故使用 Docling 支持的 EasyOCR 路径，不修改第三方源码。

Windows 子进程在启动服务和 stdin 监听前，由解析适配层预初始化 NumPy/SciPy BLAS 原生库，避免后台第一次导入停滞。Docling 转换器和模型仍在首次解析时惰性创建。

## 问答、任务与复核

普通 QA 通过 DocumentContext/检索工具选择有指纹的原文块，模型只能引用服务提供的证据 ID。模型返回的引用须验证，再由服务附加真实文件、页码、bbox；Markdown 禁用 HTML 并经过 DOMPurify。API Key 仅由 Electron safeStorage 加密文件读取，临时作为请求头传给本地服务，不写入业务数据库。

Design 保存可编辑草稿；Confirm 创建新的不可变 Schema 版本和 SQLite Job。任务进程用 subprocess 启动，启动参数经匿名 stdin 管道发送，不写入命令行或环境变量；凭据只在内存。保留管道监测父进程退出。Worker 按文献事务提交、多记录保留，独立文献失败隔离；SSE 经主进程转发进度。取消终止所属 Worker，恢复只重试未完成文献。Windows multiprocessing 在此嵌入启动链中停滞，因此使用可打包的显式子进程入口。

LangGraph 仅编排生成和校验节点，不保存密钥到状态或启用追踪；Agent 不直接访问数据库或文件系统。兼容模型接口只接受 HTTPS（本机调试可 HTTP），不跟随重定向，不把上游响应/认证内容写入错误信息。

ReviewRevision 按 Job 追加版本，用 SQLite 写锁和 base_version 拒绝过期提交。自动 Record 永不被修订覆盖；读取和导出按选中版本重放修改，校验字段类型、缺失原因和证据。Excel 包含数据、证据、元数据及分块保存的修订历史；用户文本防公式执行，超长单元格拒绝而非截断。

pluggy Hook 仅接收纯数据。宿主维护 project_plugins，插件自身不能迁移表或访问存储。微塑料插件提供模板/术语/规则及归一化建议，原始字段保持不变。启用的版本随 Schema 固定；缺失版本拒绝继续旧任务，不能静默替换。历史结果无需安装原插件即可查看和导出；再次人工修订需要相应规则版本。

Beta 的 Docling PDF 解码使用其 PDFium 后端，避开默认 threaded docling-parse 在本机回归中出现的访问异常；解析版本随适配变化升级，旧缓存不冒充新解析结果。安装模式使用独立官方 CPython 和只读 resources/models，不依赖开发虚拟环境。
