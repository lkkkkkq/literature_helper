# 开发约定

使用独立虚拟环境和锁文件，新增依赖必须更新第三方声明。禁止复制旧业务代码、导入旧数据库或复用旧结果状态。

修改前明确所属层。路由不包含 SQL、文件操作或 Prompt；服务不返回 HTTP 响应；前端不存储业务状态。所有原始文献默认只读引用。

提交前运行 `scripts/check.ps1`。新模块配套测试，优先覆盖隔离、错误路径、取消、版本与证据完整性，避免只验证实现细节。测试禁止依赖真实 API Key 或旧项目数据。

格式化：`npm run format` 和 `.venv/Scripts/python.exe -m ruff format .`。Python 静态检查：`.venv/Scripts/python.exe -m ruff check .`。

更新依赖后重新生成 `requirements.lock` 和 `package-lock.json`，使用干净环境确认可复现。Python 锁文件不包含本机 editable 路径。不得提交密钥、原始论文、数据库、日志和缓存。

逐阶段验收，不把后续阶段未实现的功能写成已完成。阶段 0 不复制任何第三方仓库源码，仅通过包管理器集成库。
