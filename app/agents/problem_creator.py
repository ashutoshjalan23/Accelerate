"""Problem creator agent with a bounded LangGraph workflow."""

import logging
from typing import TypedDict

from .ports import LLMClient
from .schemas import CodeContext, GeneratedProblem

logger = logging.getLogger(__name__)


class ProblemCreatorState(TypedDict):
    context: CodeContext
    problem: GeneratedProblem | None
    validation_reason: str
    validation_passed: bool
    iterations: int


class ProblemCreatorAgent:
    """Turn reconstructed engineering context into a self-contained challenge."""

    def __init__(self, llm: LLMClient, max_iterations: int = 3) -> None:
        if max_iterations < 1:
            raise ValueError("max_iterations must be at least 1.")
        self.llm = llm
        self.max_iterations = max_iterations

    def run(self, context: CodeContext) -> GeneratedProblem:
        graph = self._build_graph()
        state = graph.invoke(
            {
                "context": context,
                "problem": None,
                "validation_reason": "",
                "validation_passed": False,
                "iterations": 0,
            }
        )
        problem = state["problem"]
        if problem is None:
            raise ValueError("Problem creation completed without a generated problem.")
        if not state["validation_passed"]:
            raise ValueError(
                "Generated problem did not pass self-validation: "
                + state["validation_reason"]
            )
        return self._materialize_starter_files(problem, context)

    def _build_graph(self):
        try:
            from langgraph.graph import END, StateGraph
        except ImportError as error:
            raise RuntimeError(
                "LangGraph is required for the Problem Creator workflow."
            ) from error

        graph = StateGraph(ProblemCreatorState)
        graph.add_node("draft", self._draft)
        graph.add_node("validate", self._validate)
        graph.set_entry_point("draft")
        graph.add_edge("draft", "validate")
        graph.add_conditional_edges(
            "validate",
            self._next_step,
            {"draft": "draft", "end": END},
        )
        return graph.compile()

    def _draft(self, state: ProblemCreatorState) -> ProblemCreatorState:
        context = state["context"]
        iteration = state["iterations"] + 1
        logger.info("Problem Creator draft attempt %d/%d.", iteration, self.max_iterations)
        if state["validation_reason"]:
            context = context.model_copy(
                update={
                    "issue_explanation": (
                        f"{context.issue_explanation}\n\n"
                        f"Validation feedback: {state['validation_reason']}"
                    )
                }
            )
        return {
            **state,
            "problem": self.llm.draft_problem(context),
            "iterations": iteration,
        }

    def _validate(self, state: ProblemCreatorState) -> ProblemCreatorState:
        problem = state["problem"]
        if problem is None:
            raise ValueError("Problem validation received no generated problem.")
        logger.info("Problem Creator validating draft %d.", state["iterations"])
        valid, reason = self.llm.validate_problem(problem, state["context"])
        logger.info(
            "Problem Creator validation result: %s%s",
            "passed" if valid else "failed",
            f" ({reason})" if not valid else "",
        )
        return {
            **state,
            "validation_reason": "" if valid else reason,
            "validation_passed": valid,
        }

    def _next_step(self, state: ProblemCreatorState) -> str:
        if state["validation_passed"]:
            return "end"
        if state["iterations"] >= self.max_iterations:
            return "end"
        return "draft"

    @staticmethod
    def _materialize_starter_files(
        problem: GeneratedProblem, context: CodeContext
    ) -> GeneratedProblem:
        allowed = set(context.relevant_files or context.before_code)
        requested = problem.starter_files or {
            path: context.before_code[path]
            for path in allowed
            if path in context.before_code
        }
        invalid = set(requested) - allowed
        if invalid:
            raise ValueError(
                "Generated problem requested files not identified as relevant: "
                + ", ".join(sorted(invalid))
            )
        starter_files = {
            path: context.before_code[path]
            for path in requested
            if path in context.before_code
        }
        if not starter_files:
            raise ValueError("Generated problem has no valid starter files.")
        starting_code = problem.starting_code or "\n\n".join(
            f"# {path}\n{contents}" for path, contents in starter_files.items()
        )
        return problem.model_copy(
            update={"starter_files": starter_files, "starting_code": starting_code}
        )
