import json
import subprocess
import sys
import threading

from backend.agent import design, router
from backend.core.errors import DomainError
from backend.core.extraction import ExtractionPlan
from backend.tools.retrieval import retrieve


class JobService:
    def __init__(self, repository, chat, data_dir, start_workers=True):
        self.repository, self.chat, self.data_dir = repository, chat, data_dir
        self.lock = threading.RLock()
        self.credentials = {}
        self.active = None
        self.plugins = None
        self.stop = threading.Event()
        self.repository.recover()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        if start_workers:
            self.thread.start()

    def profile(self, project_id, key):
        profile = self.chat.repository.profile(project_id)
        if not profile or not key:
            raise DomainError("请先配置此项目的模型和密钥。")
        return profile

    def route(self, project_id, text, key):
        return {"intent": router.route(text, self.chat.model, self.profile(project_id, key), key)}

    def design(self, project_id, session_id, body, key):
        self.chat.repository.history(project_id, session_id)
        profile = self.profile(project_id, key)
        documents = self.chat.workspace.list_documents(project_id)
        selected = [str(value) for value in body.document_ids] or [
            doc["id"] for doc in documents if doc["status"] == "active"
        ]
        if not selected:
            raise DomainError("请先导入文献。")
        sources, _ = self.chat.sources(project_id, selected)
        pins = self.plugins.pins(project_id) if self.plugins else []
        context = self.plugins.catalog.context(pins) if self.plugins else []
        plan = design.design(
            self.chat.model,
            profile,
            key,
            body.goal,
            retrieve(body.goal, sources, budget=16000),
            context,
        )
        plan.plugins = pins
        return self.repository.draft(project_id, session_id, body.goal, plan, selected)

    def template(self, project_id, session_id, plugin_id):
        self.chat.repository.history(project_id, session_id)
        pins = self.plugins.pins(project_id)
        pin = next((item for item in pins if item["id"] == plugin_id), None)
        if not pin:
            raise DomainError("请先在当前项目启用该插件。")
        template = self.plugins.catalog.context([pin])[0]["templates"][0]
        plan = ExtractionPlan.model_validate(template)
        plan.plugins = [pin]
        selected = [
            doc["id"]
            for doc in self.chat.workspace.list_documents(project_id)
            if doc["status"] == "active"
        ]
        if not selected:
            raise DomainError("请先导入文献。")
        return self.repository.draft(
            project_id, session_id, "领域模板：" + plan.name, plan, selected
        )

    def confirm(self, project_id, session_id, body, key):
        profile = self.profile(project_id, key)
        plans = self.repository.plans(project_id, session_id)
        schema = next((plan for plan in plans if plan["id"] == str(body.schema_id)), None)
        if not schema:
            raise DomainError("方案不属于此会话。", "not_found")
        body.plan.plugins = schema["plan"].get("plugins", [])
        if self.plugins:
            self.plugins.catalog.resolve(body.plan.plugins)
        fingerprints = {}
        for document_id in schema["document_ids"]:
            document = self.chat.workspace.get_document(project_id, document_id)
            if document["status"] != "active":
                raise DomainError("方案包含失效文献，请重新设计方案。")
            fingerprints[document_id] = {
                asset["id"]: asset["sha256"] for asset in document["assets"]
            }
        with self.lock:
            job = self.repository.confirm(project_id, session_id, body, fingerprints)
            if job["status"] == "pending":
                self.credentials[job["id"]] = (project_id, profile, key)
        return job

    def resume(self, project_id, job_id, key):
        profile = self.profile(project_id, key)
        with self.lock:
            self.repository.resume(project_id, job_id)
            self.credentials[job_id] = (project_id, profile, key)
        return self.repository.get(project_id, job_id)

    def cancel(self, project_id, job_id):
        with self.lock:
            self.repository.cancel(project_id, job_id)
            self.credentials.pop(job_id, None)
            if self.active and self.active[0] == job_id:
                process = self.active[2]
                if process.poll() is None:
                    process.terminate()
                process.wait(timeout=3)
                process.stdin.close()
                self.active = None
        return self.repository.get(project_id, job_id)

    def _loop(self):
        while not self.stop.wait(0.3):
            with self.lock:
                if self.active:
                    job_id, project_id, process = self.active
                    if process.poll() is None:
                        continue
                    process.wait()
                    process.stdin.close()
                    try:
                        self.repository.cancel(project_id, job_id, interrupted=True)
                    except DomainError:
                        pass
                    self.active = None
                if not self.credentials:
                    continue
                job_id = next(iter(self.credentials))
                project_id, profile, key = self.credentials.pop(job_id)
                try:
                    job = self.repository.get(project_id, job_id)
                    if job["status"] != "pending":
                        continue
                    process = subprocess.Popen(
                        [sys.executable, "-m", "backend.workers.extraction"],
                        stdin=subprocess.PIPE,
                        stdout=subprocess.DEVNULL,
                        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                        text=True,
                        encoding="utf-8",
                    )
                    process.stdin.write(
                        json.dumps(
                            dict(
                                data_dir=str(self.data_dir),
                                project_id=project_id,
                                job_id=job_id,
                                profile=profile,
                                key=key,
                            )
                        )
                        + "\n"
                    )
                    process.stdin.flush()
                    self.active = (job_id, project_id, process)
                except Exception:
                    try:
                        self.repository.cancel(project_id, job_id, interrupted=True)
                    except DomainError:
                        pass

    def close(self):
        self.stop.set()
        if self.thread.is_alive():
            self.thread.join(timeout=2)
        with self.lock:
            if self.active:
                job_id, project_id, process = self.active
                if process.poll() is None:
                    process.terminate()
                process.wait(timeout=3)
                process.stdin.close()
                try:
                    self.repository.cancel(project_id, job_id, interrupted=True)
                except DomainError:
                    pass
            self.credentials.clear()
