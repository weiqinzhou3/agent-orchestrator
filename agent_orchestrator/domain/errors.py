from __future__ import annotations


class AgentOrchestratorError(Exception):
    """Base error for the project."""


class AlreadyRunningError(AgentOrchestratorError):
    """Raised when another run already owns the requested scope."""


class InvalidProjectTransitionError(AgentOrchestratorError):
    """Raised when a project status transition is not allowed."""


class InvalidPhaseTransitionError(AgentOrchestratorError):
    """Raised when a phase status transition is not allowed."""


class BootstrapAlreadyRunningError(AlreadyRunningError):
    """Raised when bootstrap work is already active for a project."""


class PhaseAlreadyRunningError(AlreadyRunningError):
    """Raised when phase work is already active for a phase scope."""


class MissingResumeContextError(AgentOrchestratorError):
    """Raised when recovery context is missing."""


class ContractInvalidError(AgentOrchestratorError):
    """Raised when contract validation fails."""


class MissingGateDecisionError(AgentOrchestratorError):
    """Raised when a review-like path expects a gate but none is available."""


class UnsupportedOriginStageError(AgentOrchestratorError):
    """Raised when an origin stage cannot be mapped."""


class InvalidRecheckSourceError(AgentOrchestratorError):
    """Raised when fix/recheck input is inconsistent with the gate source."""


class UnsupportedApprovalTypeError(AgentOrchestratorError):
    """Raised when approval routing receives an unsupported type."""
