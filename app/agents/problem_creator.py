"""Problem creator agent with bounded drafting and validation."""

from .ports import LLMClient
from .schemas import CodeContext, GeneratedProblem


class ProblemCreatorAgent:
    """Turn reconstructed engineering context into a self-contained challenge."""

    def __init__(self, llm: LLMClient, max_iterations: int = 3) -> None:
        if max_iterations < 1:
            raise ValueError("max_iterations must be at least 1.")
        self.llm = llm
        self.max_iterations = max_iterations

    def run(self, context: CodeContext) -> GeneratedProblem:
        problem = self.llm.draft_problem(context)
        for _ in range(self.max_iterations):
            valid, reason = self.llm.validate_problem(problem)
            if valid:
                return problem
            problem = self.llm.draft_problem(
                context.model_copy(
                    update={
                        "issue_explanation": (
                            f"{context.issue_explanation}\n\n"
                            f"Validation feedback: {reason}"
                        )
                    }
                )
            )
        raise ValueError("Generated problem did not pass self-validation.")
