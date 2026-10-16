# LitExtract v2

## GitHub 第一版基线

本仓库的 `v1.0.0-beta` 标签保存应用 0.1.0 的第一版代码基线。工程内部名称仍为 LitExtract v2；当前 0.1.1 是阅读体验和提取修复的测试更新，不是前端整体改版。

此基线包含 DeepSeek 65,536 tokens 输出预算、系统元数据列生成及证据校验修复。历史安装包不包含全部热修复；需要发布安装包时应从本仓库重新构建。仓库不包含 API Key、用户数据库、论文、模型权重或安装文件；运行时模型按下文步骤准备。真实模型提取质量与尚未执行的验收边界见 `VERIFICATION.md`。

本地、证据驱动的文献工作台。从零创建的独立工程，不包含旧项目的业务代码、数据库或中间结果。

## 当前交付：v2 Beta

在阶段 0 工程基础上，已实现多项目管理、只读文件扫描、文献与附件分组确认、重新扫描、独立会话与阅读笔记。项目、索引、扫描预览及笔记持久保存在 SQLite；前端使用 TanStack Query 管理请求缓存。

新增 Docling 本地 PDF、CSV、XLSX、DOCX 解析，正文/章节/表格阅读，以及 PDF.js 页码、文字和区域定位。扫描 PDF 可启用中英文 OCR。

现已开放带原文引用的问答、可编辑方案确认、独立后台进程批量提取、取消恢复、字段证据、追加式人工修订、版本化 CSV/Excel 导出和可选微塑料插件。问答、方案设计、提取相互分离；普通提问不会创建任务。DeepSeek 是默认服务，密钥在应用内由系统加密保存。本地导入与解析不需要密钥、Docker 或 GPU。

安装与使用见 [BETA_GUIDE.md](BETA_GUIDE.md)，实际验收情况见 [VERIFICATION.md](VERIFICATION.md)。

## 使用流程

1. 点击“新建项目”，选择文献文件夹或粘贴绝对路径，填写项目名称。
2. 点击“扫描文件夹”。扫描会记录绝对路径、大小、修改时间及 SHA-256，不改动源文件。
3. 在分组预览中检查标题、主论文和附件归属。可以移动文件至其他文献组，或拆分为独立资料。全部分组统一确认后入库；歧义组标为“需要复核”。
4. 展开文献，点击“阅读正文与附件”。PDF 可直接翻页和缩放；点击“解析文档”生成正文及表格，点击“第 N 页 · 定位原文”查看证据区域。附件标签切换 CSV、XLSX、DOCX；非 PDF 不生成虚构页码。
5. 从项目树创建任意多个会话，分别保存阅读笔记。点击项目名称返回文献清单；项目树可折叠。
6. 文件变化后点击“重新扫描”。保持原文件路径时保留文献和资产标识；保留已确认的标题与分组，新增附件给出归属建议。变更和缺失会标记在清单中，不清空历史标识。
7. 项目及会话均可重命名、删除。删除项目会级联删除其索引、预览、会话和笔记，**不会删除源文件**。

扫描预览同样存入数据库，重启后可继续确认。确认前会重新核验文件；扫描失败、文件中途变化或旧预览重复提交不会覆盖现有索引。

分组当前根据目录、文件名和补充材料关键词判断，未解析 DOI 或正文标题。支持登记 PDF、CSV、XLSX/XLS、DOCX/DOC、常见图片、TXT、ZIP；仅 PDF、CSV、XLSX、DOCX 支持正文解析；其他格式可登记和分组。隐藏文件、临时文件、链接目录和链接文件不导入，其他不支持文件会显示扫描提示。

## 本机开发启动

工程路径：`D:\li\litextract-v2`。需要 Node.js 24 LTS、Python 3.12–3.14（已验证 3.13）和 Git。

首次安装，在 PowerShell 执行：

```powershell
cd D:\li\litextract-v2
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1
.venv/Scripts/python.exe scripts/prepare_models.py
```

模型准备会从上游下载布局、表格和 OCR 权重至 `.local/docling-models`，首次需要联网；完成后这些文档解析在本机 CPU 执行，不上传文献。可用 `LITEXTRACT_MODEL_DIR` 指向完整模型目录。下载失败可重复运行，已有文件复用，OCR 权重校验上游摘要。

之后只需一条命令：

```powershell
npm run dev
```

如果网络无法下载 Electron，可在安装前设置 `$env:ELECTRON_MIRROR = 'https://npmmirror.com/mirrors/electron/'` 后重试。安装器保留完整性校验，默认仍使用官方来源。

Electron 自动启动独立 Python 子进程，等待迁移和健康检查完成再展示窗口。关闭窗口时先通知后端正常退出；主进程异常结束时后端通过 stdin EOF 退出。启动失败显示错误提示，避免静默白屏。开发版本需要保留终端查看诊断。

默认数据目录为 Electron `userData` 下的 `LitExtract`；Windows 通常位于 `%APPDATA%\litextract-v2\LitExtract`。不会写入旧项目目录。可通过 `LITEXTRACT_DATA_DIR` 指定独立工作目录，该目录下的 `desktop` 子目录也隔离浏览器配置和单实例锁，避免测试干扰已打开的窗口。通过 `LITEXTRACT_PYTHON` 可指定 Python 可执行文件。源文献目录不能与应用数据目录重叠。

升级后需要关闭旧窗口并重新运行 `npm run dev`；后端启动时自动将现有数据库升级到 `0007_plugins`，不需要删除数据库。

## 验证

```powershell
powershell -ExecutionPolicy Bypass -File scripts/check.ps1
```

包含 Python Ruff 检查/格式、pytest 单元及集成测试、TypeScript 检查、ESLint、Prettier、Vue 单元测试、构建及真实 Electron E2E 测试。E2E 使用独立临时数据库和浏览器配置，无需安装 Playwright 浏览器。截图写入 `test-results/workbench.png`、`test-results/stage1-documents.png`、`test-results/stage1-sessions.png`。GitHub Actions 配置在 Windows 执行同一套检查；远程运行需另行配置仓库。验收记录见 [VERIFICATION.md](VERIFICATION.md)。

依赖精确版本在 `package-lock.json` 和 `requirements.lock`。`pyproject.toml` 声明直接依赖，安装使用锁文件。第三方来源见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

## 交付阶段与打包

1. 项目、文献分组和独立会话：已完成。
2. 文档解析与 PDF 证据阅读：已完成。
3. 带引用的正常文献问答：已完成。
4. 方案确认、批量提取与独立 Worker：已完成。
5. 字段证据、追加复核和导出：已完成。
6. 领域插件及微塑料扩展：已完成。
7. Windows 打包与 Beta：状态见 PROGRESS.md，真实服务、新机器和代码签名的限制单独记录。

构建 Windows 安装包：执行 `scripts/build-release.ps1`。它先验收，再组装运行时和安装包，最后输出 SHA-256；已有本轮通过的检查时可加 `-SkipChecks`。官方嵌入式 CPython 3.13.16 使用发行页 SHA-256 校验，模型由 models.lock.json 固定仓库提交和每个文件摘要；安装包自带运行时和模型。官方构建工具下载超时时可设置 `ELECTRON_BUILDER_BINARIES_MIRROR=https://npmmirror.com/mirrors/electron-builder-binaries/`，工具摘要校验保持启用。将 `LITEXTRACT_TEST_EXECUTABLE` 指向打包后的 exe 再执行 `npx playwright test` 可对真实发布程序运行完整桌面验收。
