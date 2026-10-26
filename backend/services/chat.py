from backend.agent import qa
from backend.agent.model_adapter import CompatibleModel
from backend.core.errors import DomainError
from backend.services.context import DocumentContext
from backend.tools.retrieval import retrieve


class ChatService:
    def __init__(self, repository, workspace, reading, model=None):
        self.repository, self.workspace, self.reading = repository, workspace, reading
        self.model = model or CompatibleModel()
        self.repository.recover()

    def sources(self, project_id, document_ids):
        return DocumentContext(self.workspace, self.reading).sources(project_id, document_ids)

    def ask(self, project_id, session_id, question, key):
        history = self.repository.history(project_id, session_id)
        profile = self.repository.profile(project_id)
        if not profile or not key:
            raise DomainError("请先配置此项目的模型接口和 API Key。")
        sources, warnings = self.sources(
            project_id, [str(value) for value in question.document_ids]
        )
        if not sources:
            raise DomainError("当前范围没有可用原文，请先在文献清单解析正文与附件。")
        fulltext = any(source.parse_version for source in sources)
        coverage = None
        if fulltext:
            from backend.parsing_next.context import evidence_batches

            batches = evidence_batches(sources)
            if len(batches) > 1 and question.fulltext_batch is None:
                raise DomainError(
                    f"全文超过单次输入预算，共 {len(batches)} 批。"
                    "请指定全文批次逐批提问；未调用模型，也未静默裁剪。"
                )
            batch = question.fulltext_batch or 1
            if batch > len(batches):
                raise DomainError(f"全文只有 {len(batches)} 批。")
            coverage = {
                "batch": batch,
                "total_batches": len(batches),
                "complete": len(batches) == 1,
                "source_ids": [source.block_id for source in batches[batch - 1]],
            }
            sources = batches[batch - 1]
            warnings.append(
                f"全文第 {batch}/{len(batches)} 批；本次仅覆盖此批，不代表其余批已阅读。"
            )
        else:
            sources = retrieve(question.question, sources)
        run, claimed = self.repository.begin(project_id, session_id, question)
        if not claimed:
            return run
        try:
            prior = [
                {"question": row["question"], "answer": row["answer"]["parts"]}
                for row in history[-6:]
                if row["status"] == "complete"
            ]
            result = qa.answer(self.model, profile, key, question.question, sources, prior)
            # Do not attach now-stale source locations to a newly completed answer.
            for asset_id in {source.asset_id for source in sources}:
                if any(s.parse_version for s in sources if s.asset_id == asset_id):
                    self.reading._read_source(self.reading.repository.asset(project_id, asset_id))
                else:
                    self.reading.content(project_id, asset_id)
            result["warnings"] = warnings + ["引用匹配不等于结论已人工核验。"]
            if coverage:
                result["coverage"] = coverage
            return self.repository.finish(run["id"], answer=result)
        except Exception as error:
            message = str(error) if isinstance(error, DomainError) else "回答生成失败，请重试。"
            return self.repository.finish(run["id"], error=message)

    def test(self, project_id, key):
        profile = self.repository.profile(project_id)
        if not profile:
            raise DomainError("请先保存模型配置。")
        self.model.complete(profile, key, [{"role": "user", "content": 'Return JSON {"ok":true}.'}])
        return {"ok": True}
