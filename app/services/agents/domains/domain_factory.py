"""Domain Agent Factory — Creates domain-specific agents from YAML configs

Template composition pattern: shared base instructions + domain-specific content
loaded from YAML at agent creation time. Zero runtime overhead.

Usage:
    from app.services.agents.domains.domain_factory import create_domain_agent, load_domain_config

    config = load_domain_config("mietrecht")
    agent_id = create_domain_agent(config)
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from app.services.agents.domains.base_instructions import (
    BASE_HANDOFF_INSTRUCTIONS,
    BASE_INTERVIEW_FRAMEWORK,
)
from app.services.agents.tools.function_schemas import LEGAL_FACTS_SCHEMA
from app.services.agents.utils import get_agent_factory

logger = logging.getLogger(__name__)

# Path to domain config YAML files
CONFIGS_DIR = Path(__file__).parent / "configs"


@dataclass
class DomainConfig:
    """Domain configuration loaded from YAML"""

    name: str  # e.g., "Mietrecht"
    name_en: str  # e.g., "Tenancy Law"
    agent_name: str  # e.g., "Mietrecht Agent"
    description: str
    intake_questions_dispute: str
    intake_questions_drafting: str
    completion_criteria: str
    domain_examples: str = ""
    extra_tools: list[dict] = field(default_factory=list)


def load_domain_config(domain_key: str) -> DomainConfig:
    """Load domain configuration from YAML file

    Args:
        domain_key: Domain identifier matching YAML filename (e.g., "mietrecht")

    Returns:
        DomainConfig with all domain-specific content

    Raises:
        FileNotFoundError: If YAML config doesn't exist
    """
    config_path = CONFIGS_DIR / f"{domain_key}.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Domain config not found: {config_path}")

    with open(config_path) as f:
        raw = yaml.safe_load(f)

    return DomainConfig(
        name=raw["name"],
        name_en=raw["name_en"],
        agent_name=raw["agent_name"],
        description=raw["description"],
        intake_questions_dispute=raw["intake_questions"]["dispute"],
        intake_questions_drafting=raw["intake_questions"]["drafting"],
        completion_criteria=raw["completion_criteria"],
        domain_examples=raw.get("examples", ""),
    )


def create_domain_agent(config: DomainConfig) -> str:
    """Create a domain-specific intake agent via template composition

    Merges shared base instructions with domain-specific content from YAML.
    The resulting agent handles the FULL intake for this domain (intake + fact-completion).

    Args:
        config: Domain configuration loaded from YAML

    Returns:
        str: Mistral agent ID
    """
    factory = get_agent_factory()

    instructions = f"""You are Sumii's {config.name} ({config.name_en}) intake specialist.

{BASE_INTERVIEW_FRAMEWORK}

<<<DOMAIN: {config.name} ({config.name_en})>>>

<<<DOMAIN-SPECIFIC QUESTIONS — DISPUTE (Concrete Case)>>>

When the user has an active legal problem or dispute in {config.name}:

{config.intake_questions_dispute}

<<<DOMAIN-SPECIFIC QUESTIONS — DRAFTING (Document Creation)>>>

When the user needs help creating a legal document related to {config.name}:

{config.intake_questions_drafting}

<<<COMPLETION CRITERIA — {config.name}>>>

Before handing off, confirm you have gathered:

{config.completion_criteria}

{config.domain_examples}

{BASE_HANDOFF_INSTRUCTIONS}
"""

    agent_id = factory.create_agent(
        model="mistral-medium-2505",
        name=config.agent_name,
        description=config.description,
        instructions=instructions,
        tools=[LEGAL_FACTS_SCHEMA],
    )

    logger.info(f"Domain agent '{config.agent_name}' ready: {agent_id}")
    return agent_id


def create_all_domain_agents(domain_keys: list[str] | None = None) -> dict[str, str]:
    """Create all domain agents from YAML configs

    Args:
        domain_keys: Specific domains to create. If None, creates all available.

    Returns:
        dict mapping domain key to agent ID
    """
    if domain_keys is None:
        domain_keys = [p.stem for p in CONFIGS_DIR.glob("*.yaml")]

    agents: dict[str, str] = {}
    for key in domain_keys:
        try:
            config = load_domain_config(key)
            agents[key] = create_domain_agent(config)
        except Exception:
            logger.exception(f"Failed to create domain agent: {key}")

    logger.info(f"Created {len(agents)}/{len(domain_keys)} domain agents: {list(agents.keys())}")
    return agents
