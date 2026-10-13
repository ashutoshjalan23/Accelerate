"""Reviewer and solutions agent."""

from .ports import LLMClient
from .schemas import CommitData, GeneratedProblem, ReviewReport, UserSubmission


class ReviewerSolutionsAgent:
    """Review a learner submission against the challenge and source commit."""

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def run(
        self,
        submission: UserSubmission,
        problem: GeneratedProblem,
        commit: CommitData,
    ) -> ReviewReport:
        return self.llm.review_submission(submission, problem, commit)
