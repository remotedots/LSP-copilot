from .constants import (
    PACKAGE_NAME,
    PHANTOM_KEY,
    REQ_CHECK_STATUS,
    REQ_SIGN_IN_CONFIRM,
    REQ_SIGN_IN_INITIATE,
    REQ_SIGN_OUT,
)
from .plugin import CopilotPlugin
from .types import (
    CopilotPayloadCompletion,
    CopilotPayloadSignInConfirm,
    CopilotPayloadSignInInitiate,
    CopilotPayloadSignOut,
)
from .utils import clear_completion_preview
from abc import ABCMeta
from LSP.plugin import Request
from LSP.plugin.core.registry import LspTextCommand
from LSP.plugin.core.typing import List, Union
import functools
import mdpopups
import sublime


class CopilotTextCommand(LspTextCommand, metaclass=ABCMeta):
    session_name = PACKAGE_NAME


class CopilotPreviewCompletionsCommand(CopilotTextCommand):
    def run(self, _: sublime.Edit, completions: List[CopilotPayloadCompletion], cycle: int = 0) -> None:
        syntax = self.view.syntax()
        if not (syntax and completions):
            return
        cycle = cycle % len(completions)
        syntax_id = syntax.scope.rpartition(".")[2]
        content = '<a href="{}">Accept Suggestion</a>\n```{}\n{}\n```'.format(
            cycle, syntax_id, completions[cycle]["displayText"]
        )
        clear_completion_preview(self.view)
        # This currently doesn't care about where the completion is actually supposed to be
        mdpopups.add_phantom(
            view=self.view,
            key=PHANTOM_KEY,
            region=self.view.sel()[0],
            content=content,
            md=True,
            layout=sublime.LAYOUT_BELOW,
            on_navigate=functools.partial(self._insert_completion, completions=completions),
        )

    def _insert_completion(self, index: str, completions: List[CopilotPayloadCompletion]) -> None:
        idx = int(index)
        if not (0 <= idx < len(completions)):
            return
        completion = completions[idx]
        mdpopups.erase_phantoms(view=self.view, key=PHANTOM_KEY)
        self.view.run_command("insert", {"characters": completion["displayText"]})


class CopilotSignInCommand(CopilotTextCommand):
    def run(self, _: sublime.Edit) -> None:
        session = self.session_by_name(self.session_name)
        if not session:
            return
        session.send_request(
            Request(REQ_SIGN_IN_INITIATE, {}),
            self._on_result_sign_in_initiate,
        )

    def _on_result_sign_in_initiate(
        self,
        payload: Union[CopilotPayloadSignInConfirm, CopilotPayloadSignInInitiate],
    ) -> None:
        CopilotPlugin.set_has_signed_in(False)
        if payload.get("status") == "AlreadySignedIn":
            CopilotPlugin.set_has_signed_in(True)
            return
        user_code = payload.get("userCode")
        verification_uri = payload.get("verificationUri")
        if not (user_code and verification_uri):
            return
        sublime.set_clipboard(user_code)
        sublime.run_command("open_url", {"url": verification_uri})
        if not sublime.ok_cancel_dialog(
            "[Copilot] The device activation code has been copied."
            + " Please paste it in the popup GitHub page. Press OK when completed."
        ):
            return
        session = self.session_by_name(self.session_name)
        if not session:
            return
        session.send_request(
            Request(REQ_SIGN_IN_CONFIRM, {"userCode": user_code}),
            self._on_result_sign_in_confirm,
        )

    def _on_result_sign_in_confirm(self, payload: CopilotPayloadSignInConfirm) -> None:
        if payload.get("status") == "OK":
            CopilotPlugin.set_has_signed_in(True)
            sublime.message_dialog('[Copilot] Sign in OK with user "{}".'.format(payload.get("user")))


class CopilotSignOutCommand(CopilotTextCommand):
    def run(self, _: sublime.Edit) -> None:
        session = self.session_by_name(self.session_name)
        if not session:
            return
        session.send_request(
            Request(REQ_SIGN_OUT, {}),
            self._on_result_sign_out,
        )

    def _on_result_sign_out(self, payload: CopilotPayloadSignOut) -> None:
        if payload.get("status") == "NotSignedIn":
            CopilotPlugin.set_has_signed_in(False)
            sublime.message_dialog("[Copilot] Sign out OK. Bye!")


class CopilotCheckStatusCommand(CopilotTextCommand):
    def run(self, _: sublime.Edit) -> None:
        session = self.session_by_name(self.session_name)
        if not session:
            return
        session.send_request(
            Request(REQ_CHECK_STATUS, {}),
            self._on_result_check_status,
        )

    def _on_result_check_status(self, payload: Union[CopilotPayloadSignInConfirm, CopilotPayloadSignOut]) -> None:
        if payload.get("status") == "OK":
            CopilotPlugin.set_has_signed_in(True)
            sublime.message_dialog('[Copilot] Sign in OK with user "{}".'.format(payload.get("user")))
        else:
            CopilotPlugin.set_has_signed_in(False)
            sublime.message_dialog("[Copilot] You haven't signed in yet.")
