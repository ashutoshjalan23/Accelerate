"""Top-level LangGraph orchestration for challenge generation."""

from dataclasses import dataclass
from typing import TypedDict

from ..agents.curator import CuratorScoutAgent
from ..agents.engineering_analyst import EngineeringAnalystAgent
from ..agents.llm import CuratorLLMClient
from ..agents.problem_creator import ProblemCreatorAgent
from ..agents.schemas import (
    CodeContext,
    CommitData,
    GeneratedProblem,
    RepositoryInput,
)
from ..cache import find_analyst_context, load_analyst_context, save_analyst_context
from ..integrations.github import GitHubClientAdapter


class GenerationState(TypedDict):
    repository: RepositoryInput
    selected_commit: CommitData | None
    context: CodeContext | None
    problem: GeneratedProblem | None
    use_cache: bool


@dataclass(frozen=True)
class GenerationResult:
    """Typed result returned by the top-level generation graph."""

    context: CodeContext
    problem: GeneratedProblem


class LangGraphGenerationWorkflow:
    """Compose the existing Curator, Analyst, and Problem Creator agents."""

    def __init__(
        self,
        *,
        github: GitHubClientAdapter | None = None,
        llm: CuratorLLMClient | None = None,
        analyst_iterations: int = 3,
        problem_iterations: int = 3,
    ) -> None:
        self.github = github or GitHubClientAdapter()
        self.llm = llm or CuratorLLMClient()
        analyst = EngineeringAnalystAgent(
            github=self.github,
            llm=self.llm,
            max_iterations=analyst_iterations,
        )
        self.curator = CuratorScoutAgent(
            github=self.github,
            llm=self.llm,
            analyst=analyst,
        )
        self.analyst = analyst
        self.problem_creator = ProblemCreatorAgent(
            llm=self.llm,
            max_iterations=problem_iterations,
        )

    def run(
        self, repository: RepositoryInput, *, use_cache: bool = True
    ) -> GenerationResult:
        """Run Curator -> Analyst -> Problem Creator through LangGraph."""

        graph = self._build_graph()
        state = graph.invoke(
            {
                "repository": repository,
                "selected_commit": None,
                "context": None,
                "problem": None,
                "use_cache": use_cache,
            }
        )
        return self._result(state)

    def run_from_cached_context(self, context: CodeContext) -> GeneratedProblem:
        """Run only the Problem Creator node using an existing CodeContext."""

        return self.problem_creator.run(context)

    def _build_graph(self):
        try:
            from langgraph.graph import END, StateGraph
        except ImportError as error:
            raise RuntimeError(
                "LangGraph is required for generation orchestration."
            ) from error

        graph = StateGraph(GenerationState)
        graph.add_node("select_commit", self._select_commit)
        graph.add_node("load_context", self._load_context)
        graph.add_node("create_problem", self._create_problem)
        graph.set_entry_point("select_commit")
        graph.add_edge("select_commit", "load_context")
        graph.add_edge("load_context", "create_problem")
        graph.add_edge("create_problem", END)
        return graph.compile()

    def _select_commit(self, state: GenerationState) -> GenerationState:
        if state["use_cache"]:
            context = find_analyst_context(state["repository"].repository)
            if context:
                return {**state, "selected_commit": context.commit, "context": context}
        selected = self.curator.select_commit_with_assessment(state["repository"])
        return {**state, "selected_commit": selected.commit}

    def _load_context(self, state: GenerationState) -> GenerationState:
        if state["context"] is not None:
            return state
        commit = state["selected_commit"]
        if commit is None:
            raise ValueError("Analyst context requested before commit selection.")
        context = (
            load_analyst_context(commit.repository, commit.commit_sha)
            if state["use_cache"]
            else None
        )
        if context is None:
            context = self.analyst.run(commit)
            if state["use_cache"]:
                save_analyst_context(context)
        return {**state, "context": context}

    def _create_problem(self, state: GenerationState) -> GenerationState:
        context = state["context"]
        if context is None:
            raise ValueError("Problem creation requested without analyst context.")
        return {**state, "problem": self.problem_creator.run(context)}

    @staticmethod
    def _result(state: GenerationState) -> GenerationResult:
        context = state["context"]
        problem = state["problem"]
        if context is None or problem is None:
            raise RuntimeError(
                "Generation graph completed without typed context and problem."
            )
        return GenerationResult(context=context, problem=problem)
