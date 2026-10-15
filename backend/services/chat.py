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
                self.reading.content(project_id, asset_id)
            result["warnings"] = warnings + [
                "回答基于检索到的原文片段；引用匹配不等于结论已人工核验。"
            ]
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
