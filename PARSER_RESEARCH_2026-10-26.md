# 解析工具调研与开工决定

日期：2026-10-26（北京时间）。已完成官方文档、GitHub 元数据及代表性用户反馈调查；尚未安装新引擎或对论文做准确率测试。

## 1. 开工决定

| 工作 | 首选 | 备选／补充 |
|---|---|---|
| PDF 综合解析 | MinerU，先验证 4.0.12 发行版 | Docling 2.142.1，仅首选遇到明确问题时对照 |
| Word、LaTeX 源文档转换 | Pandoc，保留数学表达与图片资源 | 自写原生结构检查、缺失资源处理、复杂内容保留；不将所有文件先转 PDF |
| Markdown | 直接读取与组织资源 | 自写标题、证据标记和图片依赖处理 |
| XLSX／CSV 原始数据 | openpyxl／Python csv | 自写单位、格式、公式值状态和附件关联处理 |
| PDF 原文展示 | PDF.js | 我们实现来源映射与高亮 |
| 图表数值提取 | 参考 WebPlotDigitizer 的标定与提取流程 | 按许可决定是否复用代码，自己实现应用交互和记录关联 |

这是可直接启动开发的工程选择，不是宣称 MinerU 的准确率已实测第一。先做好独立解析出口，再用两三篇实际文献确认；不继续无期限调研。

## 2. GitHub 关注度与维护

下表来自本次 GitHub REST API 查询，星数会变化；最近发布不是实际安装版本。仓库星数覆盖整个项目，尤其 PaddleOCR，不能等同于某个解析模型的口碑。

| 项目 | 星数 | API 返回的最新正式发布 | 最近推送（UTC） | 判断 |
|---|---:|---|---|---|
| [MinerU](https://github.com/opendatalab/MinerU) | 82,471 | mineru-4.0.12-released，10-11 | 10-25 | 作为 PDF 首选，理由是综合转换与来源输出相符，不只因为星数 |
| [Docling](https://github.com/docling-project/docling) | 69,584 | v2.142.1，10-23 | 10-25 | 结构化文档与定位能力适合作为备选；不是因为第一版已用它 |
| [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) | 91,661 | v3.7.0，06-11 | 09-16 | OCR 和专用文档模型的重要候选，但暂不叠加第二套推理环境 |
| [Marker](https://github.com/datalab-to/marker) | 40,642 | v2.0.0，07-20 | 10-22 | 功能相关，保留候选；公开比较存在配置争议，暂不据其排名改选型 |

发布入口：各仓库 `/releases`。API 查询中部分后续搜索触发限流，已使用公开页面补查；没有据此编造用户满意度或已解决比例。

## 3. 为什么先用 MinerU

官方文档描述的 4.0 路线包含正文、OCR、公式、表格和多种输出；具有 Markdown、结构化结果及页面／块定位，适合连接我们需要的阅读与核对流程。

- 首跑使用本地 Standard 档，保留公式和表格处理；Flash 仅用于快速预览，不作为完整科研解析的验收结果。
- Standard 使用专用组件与视觉语言模型；并非完全不使用模型。Basic 是不要求本地 VLM 的另一档位，不能静默降档后称结果等价。
- 先采用独立进程／环境，不将全部推理依赖塞入现有后端。
- 首先取 Markdown、图片及中间位置数据，转换成我们自己的来源索引；引擎 JSON 可以作为调试缓存，不作为重复全文的应用主数据。

依据：[运行档位](https://opendatalab.github.io/MinerU/usage/tiers/)、[输出格式](https://opendatalab.github.io/MinerU/reference/output_files/)。在线文档随主分支更新；安装后必须以固定版本的 `--help` 和实际输出确认参数，不把不同版本的命令混用。

## 4. 用户反馈：具体问题与处理意义

Issues 是用户报告，不能代表全体用户，也不能把“关闭”直接当作所有版本均已修复。

| 项目／反馈 | 已看到的情况 | 我们采取的措施 |
|---|---|---|
| [MinerU #5311](https://github.com/opendatalab/MinerU/issues/5311) | 旧 3.4.4、macOS pipeline 有完成阶段失败报告，用户报告换后端可绕过，后续已关闭 | 不推断当前 Windows 版本有同样错误；验证整篇结束、产物落盘及取消，记录退出码 |
| [Docling #4619](https://github.com/docling-project/docling/issues/4619) | 有 Excel 数字格式和公式丢失报告，当前开放 | XLSX 优先原生读取，区分公式与缓存值，不只取转换后的文本 |
| [PaddleOCR #18397](https://github.com/PaddlePaddle/PaddleOCR/issues/18397) | Windows 特定竖排批量页面、方向设置下有文字遗漏报告 | 不能推断所有论文都有问题；若后续采用，加入整篇与单页一致性检查 |
| [Marker #1066](https://github.com/datalab-to/marker/issues/1066) | 用户质疑比较中 MinerU 后端配置不一致 | 不把仓库宣传的优胜分数直接作为本项目准确率结论 |

## 5. Word／LaTeX 源文件优先规则

选择 Pandoc 是因为它直接读取文档结构并转换，不需要把原生公式和文字先变图片。官方支持 DOCX、LaTeX、Markdown 等，但也明确转换可能丢失复杂结构。

执行规则：
1. 主论文和附件先分清；DOCX 附件不替代 PDF 主论文。
2. 同一版本存在完整源文件时优先读源文件；版本不明或内容冲突时保留两份、标注差异，不覆盖正式版。
3. LaTeX 从主文件及依赖读取；自定义宏、缺失图片、TikZ 等不能转换的内容单独记录与补处理。
4. Pandoc 转换不能自动提供可靠的原 PDF 坐标；我们自己做内容匹配，无法匹配就返回源位置。
5. 复杂 Word 表格、原生图表和公式需要对照结构；不能认为成功退出就代表全部转换。

依据：[Pandoc 官方手册](https://pandoc.org/MANUAL.html)。此次没有发现本机 PATH 中已安装 Pandoc，开工时在独立工具目录安装并记录版本。XLSX 读取库不负责重新计算 Excel 公式；缓存缺失要提示，不编造值。

## 6. 本机与测试资料

- 内存：33,752,997,888 字节，约 31.4 GiB。
- GPU：NVIDIA GeForce RTX 5060 Laptop GPU，`nvidia-smi` 报告 8,151 MiB 显存；驱动 592.01。
- 系统为 Windows。具备本地验证条件，但尚未确认推理依赖兼容性、实测速度和峰值内存。
- 测试目录实际为 `D:\literature-test`，不是旧文字中的 `literature_test`。
- 当前文件：16 个 PDF、5 个 DOCX、6 个 CSV、1 个 XLSX。没有发现 TEX／MD 源文件；后续需自制明确标注的格式测试样例，不能冒充真实论文验收。
- 首轮资料：`single-paper/2026-9101-main-paper.pdf` 及其 CSV；`batch/2026-9203` 的 PDF＋XLSX；`batch/2026-9205` 的 PDF＋DOCX。内容是否包含公式密集页需开工后查看，不凭文件名认定覆盖。

## 7. 许可与分发检查

这里只记录公开文件，不作整套产品已获许可的结论。

- [MinerU LICENSE.md](https://github.com/opendatalab/MinerU/blob/master/LICENSE.md)：当前主分支是 Apache-2.0 加附加条件，不能只写“纯 Apache”。打包时核对固定版本和所下载权重的许可并保存声明。
- Docling 仓库标注 MIT；PaddleOCR 标注 Apache-2.0。各自权重和依赖仍单独记录。
- [Marker README](https://github.com/datalab-to/marker)：区分代码 Apache-2.0 与模型 OpenRAIL-M，不将代码许可套用到全部资源。
- Pandoc、PDF.js、图表复用代码在打包前按实际版本登记许可证。网页公开代码不等于可不署名或无条件复制。

## 8. 可以直接执行的开工清单

1. 检查工作区改动并建立回退点；开发环境和测试数据目录隔离。
2. 创建独立 Python 3.12 环境，安装并固定 MinerU 4.0.12；记录依赖、模型与校验信息。若发布包版本不对应，先核对发行标签，不自动换成未记录版本。
3. 读取安装版本帮助与示例，用单个真实 PDF 确认整篇解析、图片及坐标输出；先串行运行，不一开始并发多文献。
4. 连续处理上述三组资料；对照关键页面记录小数点、表头、公式、图注和定位问题。
5. 主路径可用就开发 Markdown、来源索引、图片和报告的保存；若出现阻塞质量或运行问题，再用 Docling 固定版本比较相同页面。
6. 安装固定版 Pandoc，开发 DOCX／LaTeX 原生读取与依赖处理；用已有 DOCX 附件及专门构造的公式样例检查。
7. 完成应用内全文查看、源文件／PDF 定位和修正；接着实现计划书中的常见图表数字化。

本次已完成：网上调研、硬件和样本清点、首选／备选决定、实施计划更新。未做：新引擎安装、模型下载、论文解析实测、云端上传和应用代码修改。
