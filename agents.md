AceProgramming: Agent Architecture & Workflow Spec

Note to AI Developer: This document outlines the agentic backend for the "AceProgramming" platform. Your task is to implement this using FastAPI, CrewAI, LangGraph, and the Google GenAI SDK (with OpenRouter as fallback).

The system uses a hybrid orchestration model:

CrewAI manages the sequential pipeline and role-based execution.

LangGraph is used inside specific CrewAI tasks/agents (Engineering Analyst and Problem Creator) that require cyclical reasoning, state management, and multi-step validation.

1. Data Structures (Pydantic Schemas)

To ensure strict data passing between agents, use the following conceptual Pydantic schemas:

RepositoryInput: Contains the target GitHub URL.

CommitData: Extracted commit hash, diff, PR description, and files changed.

CodeContext: The "before" and "after" state of the codebase.

GeneratedProblem: Title, description, constraints, starting code block, and hidden test cases.

UserSubmission: The code submitted by the user from the frontend.

ReviewReport: Feedback, score, and the actual open-source solution comparison.

2. Agent Definitions

Agent 1: Curator & Scout Agent

Framework: CrewAI

Role: Open-Source Repository Scout

Goal: Scan a given repository to find a "meaningful" commit (e.g., bug fix, algorithmic optimization, architectural change) and ignore trivial changes (typos, README updates).

Tools: github_api_tool (wrapper for fetching commits, diffs, and PRs).

Input: RepositoryInput (GitHub URL).

Output: CommitData.

Instructions: Retrieve the last 50 commits. Evaluate commit messages and file changes. Select one commit that represents a distinct logical problem. Extract the diff.

Agent 2: Engineering Analyst Agent

Framework: CrewAI (Task wrapped around a LangGraph execution).

Role: Reverse Engineering Specialist

Goal: Reconstruct the exact bug or bottleneck that existed before the commit was applied.

LangGraph Implementation:

State: Needs a state tracker holding the raw diff, the target files, and a drafted "Issue Explanation".

Node 1 (Context Fetcher): Uses GitHub API to fetch the full file contents at commit~1 (the state before the fix).

Node 2 (Analyzer): Reads the diff and the before-state to deduce why the commit was made.

Conditional Edge: If the analyzer determines the diff relies on too many missing external files, loop back to Node 1 to fetch dependencies, else proceed to end.

Input: CommitData.

Output: CodeContext (A clear explanation of the broken state and the raw before-code).

Agent 3: Problem Creator Agent

Framework: CrewAI (Task wrapped around a LangGraph execution).

Role: Technical Interview Architect

Goal: Convert the CodeContext into a structured, HackerRank-style problem.

LangGraph Implementation:

State: Holds the drafted problem, constraints, and test cases.

Node 1 (Problem Drafter): Writes the markdown description (Context, Problem Statement, Constraints).

Node 2 (Test Case Generator): Generates mock input/output scenarios based on the expected behavior of the fix.

Node 3 (Validator): Self-critique node. Checks if the problem is solvable without outside context. If it requires missing context, loops back to Node 1 to rewrite the prompt.

Input: CodeContext.

Output: GeneratedProblem (Ready to be sent to FastAPI and saved to the SQL DB).

Agent 4: Reviewer & Solutions Agent

Framework: CrewAI (On-demand execution upon user submission).

Role: Senior Code Reviewer

Goal: Evaluate the user's code against the actual open-source commit.

Input: UserSubmission, GeneratedProblem, and the original CommitData.

Output: ReviewReport.

Instructions: Do not just run unit tests. Analyze the Big-O complexity, style, and approach. Compare the user's approach to how the open-source maintainers actually solved it. Highlight where the maintainers did it better, or praise the user if their solution is more elegant.

3. Workflow Sequence (CrewAI Process)

Generation Pipeline (Async): User submits URL -> Curator Agent -> Analyst Agent (LangGraph) -> Problem Creator Agent (LangGraph) -> Save GeneratedProblem to SQL -> Return via FastAPI.

Evaluation Pipeline (Sync): User submits code -> Reviewer Agent compares with stored DB context -> Returns ReviewReport via FastAPI.

4. LLM Configuration

Default routing should go to Google Gemini for high-context tasks (like reading large file diffs).

Implement an OpenRouter fallback mechanism if the primary API rate limits or fails, preferably targeting high-coding-capability open-weight models.rea