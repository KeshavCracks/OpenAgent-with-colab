"""Browser automation with a mandatory approval gate for sensitive actions.

Modeled on the capability set of the Browser Use project
(github.com/browser-use/browser-use): navigation, clicking, form filling,
screenshots, DOM inspection, console/network observation, with citations.
The actual browser backend (Playwright) is an optional dependency and is
injected so this module stays importable (and fully testable) without it.
"""
from __future__ import annotations

import dataclasses
import time
from enum import Enum
from typing import Any, Callable, Optional

from openagent.research.agent_reach import Citation


class ActionKind(str, Enum):
    NAVIGATE = "navigate"
    CLICK = "click"
    FILL_FORM = "fill_form"
    SCREENSHOT = "screenshot"
    INSPECT_DOM = "inspect_dom"
    READ_CONSOLE = "read_console"
    READ_NETWORK = "read_network"
    LOGIN = "login"
    UPLOAD = "upload"
    PAYMENT = "payment"
    ACCOUNT_ACTION = "account_action"
    DESTRUCTIVE_ACTION = "destructive_action"


SENSITIVE_ACTIONS = {
    ActionKind.LOGIN, ActionKind.UPLOAD, ActionKind.PAYMENT,
    ActionKind.ACCOUNT_ACTION, ActionKind.DESTRUCTIVE_ACTION,
}


class ApprovalRequiredError(PermissionError):
    pass


@dataclasses.dataclass
class BrowserAction:
    kind: ActionKind
    target: str              # URL, selector, or description
    payload: dict[str, Any] = dataclasses.field(default_factory=dict)
    approval_token: str | None = None


@dataclasses.dataclass
class ActionRecord:
    action: BrowserAction
    approved: bool
    result: Any
    t: float = dataclasses.field(default_factory=time.time)


Backend = Callable[[BrowserAction], Any]


def _unconfigured_backend(action: BrowserAction) -> Any:
    raise RuntimeError(
        "No browser backend configured. Install the 'browser' extra "
        "(pip install openagent-harness[browser]) and wire a Playwright-backed "
        "backend, or inject a fake backend for testing."
    )


class BrowserSession:
    def __init__(
        self,
        backend: Backend = _unconfigured_backend,
        approver: Optional[Callable[[BrowserAction], bool]] = None,
    ):
        self.backend = backend
        # `approver` lets the CLI/UI prompt the user; defaults to "never
        # approve automatically" so sensitive actions always require an
        # explicit approval_token unless a real approver is wired up.
        self.approver = approver
        self.history: list[ActionRecord] = []
        self.citations: list[Citation] = []

    def _is_approved(self, action: BrowserAction) -> bool:
        if action.approval_token:
            return True
        if self.approver is not None:
            return self.approver(action)
        return False

    def perform(self, action: BrowserAction) -> Any:
        if action.kind in SENSITIVE_ACTIONS and not self._is_approved(action):
            raise ApprovalRequiredError(
                f"Action '{action.kind.value}' on '{action.target}' requires explicit "
                "user approval (set approval_token or supply an approver)."
            )
        result = self.backend(action)
        self.history.append(ActionRecord(action=action, approved=True, result=result))
        if action.kind == ActionKind.NAVIGATE:
            self.citations.append(Citation(
                url=action.target, title=str(result.get("title", "")) if isinstance(result, dict) else "",
                snippet=str(result.get("text", ""))[:300] if isinstance(result, dict) else "",
            ))
        return result

    def citation_report(self) -> list[dict]:
        return [dataclasses.asdict(c) for c in self.citations]
