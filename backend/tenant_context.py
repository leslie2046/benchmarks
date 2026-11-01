from contextvars import ContextVar


workspace_context = ContextVar("workspace_context", default=None)


def workspace_id():
    access = workspace_context.get()
    return access[1]["id"] if access else "legacy"


def can_manage_workspace():
    access = workspace_context.get()
    return access is None or access[1]["role"] in {"owner", "admin"}


class WorkspaceProxy:
    def __init__(self, manager, attribute):
        self.manager = manager
        self.attribute = attribute

    def __getattr__(self, name):
        access = workspace_context.get()
        if access is None:
            if self.manager.enabled:
                raise RuntimeError("Workspace context is required")
            runtime = self.manager.runtime("legacy")
        else:
            runtime = access[0]
        return getattr(getattr(runtime, self.attribute), name)
