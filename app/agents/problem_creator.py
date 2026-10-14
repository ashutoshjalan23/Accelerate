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
            raise ValueError("Problem creation failed: " + state["validation_reason"])
        if not state["validation_passed"]:
            raise ValueError(
                "Generated problem did not pass self-validation: "
                + state["validation_reason"]
            )
        return problem

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
        try:
            problem = self.llm.draft_problem(context)
            problem = self._ground_problem(problem, state["context"])
            return {**state, "problem": problem, "iterations": iteration}
        except (RuntimeError, ValueError) as error:
            return {**state, "problem": None, "iterations": iteration,
                    "validation_reason": str(error), "validation_passed": False}

    def _validate(self, state: ProblemCreatorState) -> ProblemCreatorState:
        problem = state["problem"]
        if problem is None:
            return state
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
    def _ground_problem(
        problem: GeneratedProblem, context: CodeContext
    ) -> GeneratedProblem:
        if problem.source_commit_sha != context.commit.commit_sha:
            raise ValueError("Challenge source SHA does not match the evidence.")
        allowed = set(context.before_code) | set(context.after_code)
        requested = problem.relevant_files or context.relevant_files or sorted(allowed)
        invalid = set(requested) - allowed
        if invalid:
            raise ValueError(
                "Generated problem requested files absent from repository evidence: "
                + ", ".join(sorted(invalid))
            )
        if not requested or not problem.acceptance_criteria:
            raise ValueError("Challenge requires relevant paths and acceptance criteria.")
        return problem.model_copy(
            update={"relevant_files": sorted(set(requested)),
                    "setup_notes": problem.setup_notes or [
                        "Follow the README and contribution guide at the starting revision. "
                        "Environment setup has not been verified by Accelerate."],
                    "verification_notes": problem.verification_notes or [
                        "Run the relevant repository tests or build checks locally and add regression coverage."]}
        )
