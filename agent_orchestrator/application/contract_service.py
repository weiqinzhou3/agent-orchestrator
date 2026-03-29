from __future__ import annotations

from abc import ABC, abstractmethod

from agent_orchestrator.domain.enums import ApprovalType
from agent_orchestrator.domain.results import ContractValidationResult


class ContractService(ABC):
    @abstractmethod
    def validate(self, project_name: str, phase_name: str) -> ContractValidationResult:
        raise NotImplementedError

    @abstractmethod
    def resolve_approval_type(
        self,
        project_name: str,
        phase_name: str,
        contract_path: str,
    ) -> ApprovalType | None:
        raise NotImplementedError


class StubContractService(ContractService):
    def validate(self, project_name: str, phase_name: str) -> ContractValidationResult:
        return ContractValidationResult(valid=True, contract_path=f"/contracts/{project_name}/{phase_name}.md")

    def resolve_approval_type(
        self,
        project_name: str,
        phase_name: str,
        contract_path: str,
    ) -> ApprovalType | None:
        return None
