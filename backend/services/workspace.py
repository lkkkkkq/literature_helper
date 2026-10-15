from pathlib import Path

from backend.core.errors import DomainError
from backend.core.schemas import GroupSuggestion, ProjectCreate, ScanConfirm, ScanSnapshot
from backend.repositories.workspace import WorkspaceRepository
from backend.services.scanner import scan_folder, source_folder


class WorkspaceService:
    def __init__(self, repository: WorkspaceRepository, data_dir: Path):
        self.repository = repository
        self.data_dir = data_dir.resolve()

    def create_project(self, request: ProjectCreate):
        folder = source_folder(request.source_path)
        if self.data_dir.is_relative_to(folder) or folder.is_relative_to(self.data_dir):
            raise DomainError("文献文件夹必须与应用数据目录分开，请选择其他目录。")
        return self.repository.create_project(request.name, str(folder))

    def scan(self, project_id):
        project = self.repository.get_project(project_id)
        folder = source_folder(project["source_path"])
        snapshot = scan_folder(folder)
        self._retain_grouping(project_id, snapshot)
        return self.repository.save_draft(project_id, project["revision"], snapshot)

    def _retain_grouping(self, project_id, snapshot):
        """Keep confirmed titles and membership; suggest groups only for new files."""
        available = {asset.relative_path for asset in snapshot.assets}
        assigned = {}
        groups = []
        for document in self.repository.list_documents(project_id):
            members = [
                asset["relative_path"]
                for asset in document["assets"]
                if asset["relative_path"] in available
            ]
            if not members:
                continue
            group = GroupSuggestion(
                key=document["id"],
                title=document["title"],
                main_path=document["main_path"] if document["main_path"] in members else None,
                asset_paths=members,
                confidence="high",
                reason="保留已确认的文献分组",
            )
            groups.append(group)
            for path in members:
                assigned[path] = group
        for suggestion in snapshot.groups:
            new_paths = [path for path in suggestion.asset_paths if path not in assigned]
            if not new_paths:
                continue
            target = assigned.get(suggestion.main_path)
            if target:
                target.asset_paths.extend(new_paths)
                target.reason = "保留原分组，并按主论文匹配新增附件"
            else:
                groups.append(
                    suggestion.model_copy(
                        update={
                            "asset_paths": new_paths,
                            "main_path": suggestion.main_path
                            if suggestion.main_path in new_paths
                            else None,
                        }
                    )
                )
        snapshot.groups = groups

    def confirm_scan(self, project_id, request: ScanConfirm):
        project = self.repository.get_project(project_id)
        draft = self.repository.get_draft(project_id)
        if not draft or draft["id"] != request.draft_id:
            raise DomainError("扫描预览已过期或已导入，请重新扫描。", "conflict")
        snapshot = ScanSnapshot.model_validate(draft["snapshot"])
        expected_paths = {asset.relative_path for asset in snapshot.assets}
        supplied = [path for group in request.groups for path in group.asset_paths]
        if len(supplied) != len(set(supplied)) or set(supplied) != expected_paths:
            raise DomainError("每个扫描文件必须且只能属于一组文献，不能遗漏或添加其他路径。")
        for group in request.groups:
            if group.main_path and group.main_path not in group.asset_paths:
                raise DomainError("主论文必须属于当前文献组。")
        current = scan_folder(source_folder(project["source_path"]))
        if current.assets != snapshot.assets or current.warnings != snapshot.warnings:
            raise DomainError("源文件自预览后发生变化，请重新扫描再确认。", "conflict")
        return self.repository.apply_scan(
            project_id, draft["id"], draft["base_revision"], request.groups, snapshot
        )

    def list_projects(self):
        return self.repository.list_projects()

    def get_project(self, project_id):
        return self.repository.get_project(project_id)

    def rename_project(self, project_id, name):
        return self.repository.rename_project(project_id, name)

    def delete_project(self, project_id):
        self.repository.delete_project(project_id)

    def documents(self, project_id):
        return self.repository.list_documents(project_id)

    def document(self, project_id, document_id):
        return self.repository.get_document(project_id, document_id)

    def sessions(self, project_id):
        return self.repository.list_sessions(project_id)

    def create_session(self, project_id, name):
        return self.repository.create_session(project_id, name)

    def rename_session(self, project_id, session_id, name):
        return self.repository.rename_session(project_id, session_id, name)

    def delete_session(self, project_id, session_id):
        self.repository.delete_session(project_id, session_id)

    def messages(self, project_id, session_id):
        return self.repository.messages(project_id, session_id)

    def add_message(self, project_id, session_id, content):
        return self.repository.add_message(project_id, session_id, content)

    def draft(self, project_id):
        return self.repository.get_draft(project_id)
