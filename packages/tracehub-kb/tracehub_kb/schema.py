"""Knowledge base frontmatter schemas.

Every markdown file under ``knowledge/`` starts with a YAML frontmatter block
that is validated against one of the models below. The structured fields make
filtering and matching possible; the markdown body carries the prose that the
model reads.

Schema reference: ``docs/05-KNOWLEDGE-BASE.md``.
"""

from __future__ import annotations

import re
from datetime import date
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$")

# Keep this in sync with config/environments.yaml (ADR-08).
KNOWN_ENVIRONMENTS = (
    "prod",
    "preprod",
    "test",
    "dmz-prod",
    "dmz-preprod",
    "dmz-test",
)

NonEmptyStr = Annotated[str, Field(min_length=1)]


def normalise_environment(value: str) -> str:
    """Validate an environment name against the known list (ADR-08)."""
    normalised = value.strip().casefold()
    if normalised not in KNOWN_ENVIRONMENTS:
        allowed = ", ".join(KNOWN_ENVIRONMENTS)
        raise ValueError(f"'{value}' tanımlı bir ortam değil. Tanımlı ortamlar: {allowed}")
    return normalised


class DocumentType(StrEnum):
    SERVICE = "service"
    TOPOLOGY = "topology"
    RUNBOOK = "runbook"
    CASE = "case"
    GLOSSARY = "glossary"


class Confidence(StrEnum):
    """How much the agent should trust this document.

    ``low`` documents are still used, but the report marks them as
    "doğrulanmalı".
    """

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Risk(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class BaseFrontmatter(BaseModel):
    """Fields shared by every document type."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: DocumentType
    title: NonEmptyStr
    # The bridge between how users speak and how systems are named.
    # Most commonly forgotten field, and the one search depends on most.
    aliases: list[NonEmptyStr] = Field(default_factory=list)
    tags: list[NonEmptyStr] = Field(default_factory=list)
    owner: str | None = None
    updated: date
    confidence: Confidence = Confidence.MEDIUM

    @field_validator("aliases", "tags")
    @classmethod
    def _normalise(cls, values: list[str]) -> list[str]:
        """Lowercase and de-duplicate while preserving order."""
        seen: dict[str, None] = {}
        for value in values:
            seen.setdefault(value.strip().casefold(), None)
        return list(seen)


class Repository(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    platform: Literal["azure-devops", "github", "gitlab", "other"] = "azure-devops"
    project: str | None = None
    path: NonEmptyStr
    url: str | None = None


class Deployment(BaseModel):
    """Where one service runs in one environment."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    environment: NonEmptyStr
    cluster: str | None = None
    namespace: str | None = None
    workload: str | None = None
    kind: Literal["Deployment", "StatefulSet", "DaemonSet", "CronJob", "VM", "IIS"] = "Deployment"
    hosts: list[NonEmptyStr] = Field(default_factory=list)

    @field_validator("environment")
    @classmethod
    def _known_environment(cls, value: str) -> str:
        return normalise_environment(value)


class Observability(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    elastic_indices: list[NonEmptyStr] = Field(default_factory=list)
    grafana_dashboards: list[NonEmptyStr] = Field(default_factory=list)
    log_format: Literal["json", "text", "mixed"] | None = None
    # Field that links log lines across layers - essential for chain tracing (K2).
    correlation_field: str | None = None


class Network(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    netscaler_vservers: list[NonEmptyStr] = Field(default_factory=list)
    ingress_hosts: list[NonEmptyStr] = Field(default_factory=list)


class Contact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    team: NonEmptyStr
    channel: str | None = None


class ServiceFrontmatter(BaseFrontmatter):
    """An application: where it lives, where its logs are, who owns it."""

    type: Literal[DocumentType.SERVICE] = DocumentType.SERVICE

    repository: Repository | None = None
    deployments: list[Deployment] = Field(default_factory=list)
    observability: Observability = Field(default_factory=Observability)
    network: Network = Field(default_factory=Network)
    depends_on: list[NonEmptyStr] = Field(default_factory=list)
    contacts: list[Contact] = Field(default_factory=list)

    def deployment_for(self, environment: str) -> Deployment | None:
        target = environment.strip().casefold()
        return next((d for d in self.deployments if d.environment == target), None)


class ChainLink(BaseModel):
    """One layer in a request chain."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    layer: Literal["netscaler", "ingress", "web", "integration", "backend", "database"]
    name: str | None = None
    service: str | None = None
    environment: NonEmptyStr
    # Turkish, because the agent reads this to decide what to check at this layer.
    check: NonEmptyStr

    @field_validator("environment")
    @classmethod
    def _known_environment(cls, value: str) -> str:
        return normalise_environment(value)


class TopologyFrontmatter(BaseFrontmatter):
    """An ordered request chain. Order matters: the agent walks it in sequence."""

    type: Literal[DocumentType.TOPOLOGY] = DocumentType.TOPOLOGY

    chain: list[ChainLink] = Field(min_length=1)


class RunbookFrontmatter(BaseFrontmatter):
    """A procedure. Approvals surface as warnings at the end of the report."""

    type: Literal[DocumentType.RUNBOOK] = DocumentType.RUNBOOK

    applies_to: list[NonEmptyStr] = Field(default_factory=list)
    approvals_required: list[NonEmptyStr] = Field(default_factory=list)
    risk: Risk = Risk.MEDIUM
    reversible: bool = True


class CaseFrontmatter(BaseFrontmatter):
    """A solved incident, so the next identical one is cheap."""

    type: Literal[DocumentType.CASE] = DocumentType.CASE

    symptom: NonEmptyStr
    environment: str | None = None
    services: list[NonEmptyStr] = Field(default_factory=list)
    root_cause: NonEmptyStr
    resolution: NonEmptyStr
    # Literal strings the agent can match against tool output.
    detection_signals: list[NonEmptyStr] = Field(default_factory=list)
    time_to_resolve_minutes: int | None = Field(default=None, ge=0)

    @field_validator("environment")
    @classmethod
    def _known_environment(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalise_environment(value)


class GlossaryFrontmatter(BaseFrontmatter):
    """Institutional abbreviations. Definitions live in the body."""

    type: Literal[DocumentType.GLOSSARY] = DocumentType.GLOSSARY


Frontmatter = (
    ServiceFrontmatter
    | TopologyFrontmatter
    | RunbookFrontmatter
    | CaseFrontmatter
    | GlossaryFrontmatter
)

FRONTMATTER_BY_TYPE: dict[DocumentType, type[BaseFrontmatter]] = {
    DocumentType.SERVICE: ServiceFrontmatter,
    DocumentType.TOPOLOGY: TopologyFrontmatter,
    DocumentType.RUNBOOK: RunbookFrontmatter,
    DocumentType.CASE: CaseFrontmatter,
    DocumentType.GLOSSARY: GlossaryFrontmatter,
}

# Document type -> directory it must live in.
DIRECTORY_BY_TYPE: dict[DocumentType, str] = {
    DocumentType.SERVICE: "service_catalog",
    DocumentType.TOPOLOGY: "topology",
    DocumentType.RUNBOOK: "runbooks",
    DocumentType.CASE: "cases",
    DocumentType.GLOSSARY: "glossary",
}
