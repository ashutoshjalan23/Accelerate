"""Engineering analyst agent with a bounded LangGraph evidence loop."""

from typing import TypedDict

from .ports import GitHubClient, LLMClient
from .schemas import CodeContext, CommitData


class AnalystState(TypedDict):
    commit: CommitData
    before_code: dict[str, str]
    after_code: dict[str, str]
    context: CodeContext | None
    iterations: int


class EngineeringAnalystAgent:
    """Reconstruct the bug or bottleneck addressed by a selected commit."""

    def __init__(
        self, github: GitHubClient, llm: LLMClient, max_iterations: int = 3
    ) -> None:
        if max_iterations < 1:
            raise ValueError("max_iterations must be at least 1.")
        self.github = github
        self.llm = llm
        self.max_iterations = max_iterations

    def run(self, commit: CommitData) -> CodeContext:
        graph = self._build_graph()
        state = graph.invoke(
            {
                "commit": commit,
                "before_code": {},
                "after_code": {},
                "context": None,
                "iterations": 0,
            }
        )
        context = state["context"]
        if context is None:
            raise ValueError("Engineering analysis completed without a result.")
        if context.missing_context:
            raise ValueError(
                "Unable to reconstruct the commit with available repository context: "
                + ", ".join(context.missing_context)
            )
        return context

    def _build_graph(self):
        try:
            from langgraph.graph import END, StateGraph
        except ImportError as error:
            raise RuntimeError(
                "LangGraph is required for the Engineering Analyst workflow."
            ) from error

        graph = StateGraph(AnalystState)
        graph.add_node("fetch_context", self._fetch_context)
        graph.add_node("analyze", self._analyze)
        graph.set_entry_point("fetch_context")
        graph.add_edge("fetch_context", "analyze")
        graph.add_conditional_edges(
            "analyze",
            self._next_step,
            {"fetch_context": "fetch_context", "end": END},
        )
        return graph.compile()

    def _fetch_context(self, state: AnalystState) -> AnalystState:
        commit = state["commit"]
        before_code = dict(state["before_code"])
        after_code = dict(state["after_code"])
        paths = {file.path for file in commit.files_changed}
        before_paths = {
            file.previous_path or file.path
            for file in commit.files_changed
            if file.status != "added"
        }
        paths.update(before_paths)
        missing_paths = (
            set(state["context"].missing_context) if state["context"] else set()
        )
        paths.update(missing_paths)
        for path in paths:
            is_dependency = path in missing_paths and path not in {
                file.path for file in commit.files_changed
            }
            if path not in before_code and (
                is_dependency or path in before_paths
            ):
                before_code[path] = self.github.get_file(
                    commit.repository, path, commit.parent_sha
                )
            if path not in after_code and (
                is_dependency or self._file_exists_after(commit, path)
            ):
                after_code[path] = self.github.get_file(
                    commit.repository, path, commit.commit_sha
                )
        return {**state, "before_code": before_code, "after_code": after_code}

    def _analyze(self, state: AnalystState) -> AnalystState:
        context = self.llm.explain_change(
            state["commit"], state["before_code"], state["after_code"]
        )
        return {**state, "context": context, "iterations": state["iterations"] + 1}

    def _next_step(self, state: AnalystState) -> str:
        context = state["context"]
        if context and not context.missing_context:
            return "end"
        if state["iterations"] >= self.max_iterations:
            return "end"
        return "fetch_context"

    @staticmethod
    def _file_exists_before(commit: CommitData, path: str) -> bool:
        return any(
            (file.path == path or file.previous_path == path)
            and file.status != "added"
            for file in commit.files_changed
        )

    @staticmethod
    def _file_exists_after(commit: CommitData, path: str) -> bool:
        return any(file.path == path and file.status != "removed" for file in commit.files_changed)
