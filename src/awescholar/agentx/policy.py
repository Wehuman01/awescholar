"""Tag parsing + tag policy for agent records (stored as a JSON array of strings).

Tag policy: tags carry objective proper-noun attributions only — institution
(Stanford), publication venue (Nature-Biotechnology), companion product (MCP),
named tech (LangChain). Capabilities and scenarios (multi-agent, bioinformatics,
local-first) belong in the category or the description, never in tags.

This denylist is a regression guard against re-importing generic tags from
external directories (the claw4science import carried its tag layer over
verbatim once already), not a complete ontology. Case-sensitive on purpose:
"bioinformatics" is a domain, "Bioinformatics" is a journal.
"""

from __future__ import annotations

import re
from typing import Literal

TagType = Literal["institution", "team", "venue", "tech"]

TAG_TYPE_LABEL: dict[TagType, str] = {
    "institution": "Institution",
    "team": "Team",
    "venue": "Venue",
    "tech": "Tech",
}

CATEGORIES: dict[str, str] = {
    "autonomous-research": "Autonomous Research",
    "literature-writing": "Literature & Scientific Writing",
    "bio-omics": "Bioinformatics & Omics",
    "chem-drug": "Chemistry & Drug Discovery",
    "clinical-health": "Clinical & Healthcare",
    "platforms": "Platforms & Infrastructure",
    "orchestration": "Multi-Agent Orchestration",
    "benchmarks": "Benchmarks",
    "datasets": "Datasets",
    "models": "Models & Simulation",
    "reviews": "Reviews & Surveys",
    "safety-security": "Safety & Security",
    "others": "Others",
}

CATEGORY_ORDER: list[str] = list(CATEGORIES)

NURSERY_MAX_STARS = 30
NURSERY_ARCHIVE_IDLE_DAYS = 180
ESTABLISHED_ARCHIVE_IDLE_DAYS = 3 * 365
AUTO_STABLE_MIN_STARS = 1000
ACTIVE_IDLE_DAYS = 120

GENERIC_TAGS: frozenset[str] = frozenset([
    # capability / architecture
    "multi-agent", "autonomous", "self-evolving", "self-evolution",
    "self-improving", "self-configuring", "self-debugging", "self-hosted",
    "multimodal", "multi-modal", "multi-llm", "multi-model",
    "multi-provider", "multi-provider-llm", "multi-domain",
    "multi-discipline", "multi-platform", "multi-mode", "multilingual",
    "bilingual", "cross-model", "end-to-end", "end-to-end-research",
    "full-lifecycle", "full-stack", "full-process", "human-in-the-loop",
    "tool-use", "rag", "llm", "llm-agent", "llm-training", "sub-agents",
    "agent-swarm", "swarm", "orchestrator", "agent-orchestration",
    "agent-harness", "agent-management", "agent-infrastructure",
    "agent-skill", "agent-skills", "coding-agent", "ai-assistant",
    "research-assistant", "workflow-assistant", "expert-agent", "copilot",
    "general-purpose", "generalist", "universal-llm", "long-horizon",
    "parallel-execution", "distributed", "co-discovery",
    "crowdsourced-discovery", "collective-evolution", "supervisor",
    "watchdog", "observability", "devops", "deployment", "container",
    "sandbox", "sandboxed", "isolated-execution", "runtime", "harness",
    "framework", "platform", "infrastructure", "dashboard",
    "web-dashboard", "web-ui", "gui", "desktop", "desktop-app",
    "desktop-workbench", "pwa", "voice", "conversational", "chat-based",
    "chat-integration", "canvas", "email", "monorepo", "local-models",
    "local-first", "local+cloud", "edge", "edge-cloud", "embedded", "iot",
    # domain / discipline
    "bioinformatics", "computational-biology", "biology", "biomedical",
    "biomedicine", "bioinformatics-mcp", "single-cell",
    "cell-type-annotation", "scrna-seq", "rna-seq", "multi-omics", "omics",
    "genomics", "metagenomics", "spatial-transcriptomics", "spatial-biology",
    "annotation", "multi-dataset-integration", "population-genetics",
    "drug-discovery", "drug-repurposing", "drug-target",
    "target-identification", "target-discovery", "pharma",
    "cheminformatics", "chemistry", "computational-chemistry", "molecular",
    "molecular-docking", "molecular-dynamics", "molecular-visualization",
    "protein-design", "protein-folding", "protein-engineering",
    "nanobody-design", "structural-biology", "therapeutic-reasoning",
    "precision-medicine", "clinical", "medical", "health", "wearable",
    "epidemiology", "neuroscience", "materials", "materials-science",
    "mathematics", "statistics", "remote-sensing", "tcm",
    "network-pharmacology", "disease-mechanism", "genetic-mutation",
    "genetic-perturbation", "gene-editing", "guide-rna", "nucleome",
    "scientific-research", "scientific-computing", "ai4science", "sciml",
    "education", "classroom", "pbl", "sleep-research", "real-world",
    "real-world-data", "sensitive-data", "autonomous-research",
    "autonomous-discovery", "autonomous-analysis", "auto-research",
    "deep-research", "research-agents", "research-ide", "research-studio",
    "lab-automation", "r&d-automation", "automation", "data-analysis",
    "data-driven", "simulation", "optimization", "optimization-loop",
    "learning-loop", "hypothesis", "hypothesis-generation",
    "hypothesis-testing", "hypothesis-evolution", "experiment-design",
    "equation-discovery", "symbolic-regression", "discovery", "innovation",
    "impact",
    # literature / writing
    "literature-analysis", "paper-generation", "paper-writing",
    "paper-review", "paper-reading", "paper-digest", "multi-paper",
    "idea-to-paper", "citation-analysis", "citation-verification",
    "peer-review", "report-generation", "report-writing", "daily-digest",
    "deadlines", "diagrams", "posters", "videos", "latex",
    "knowledge-graph", "knowledge-bases", "knowledge-management",
    "memory", "persistent-memory", "cross-session-memory",
    "memory-evolution", "skill-library", "skill", "skills",
    "markdown-skills", "skill-evolution", "blueprint", "vault",
    "task-management", "teams", "coordination", "command-center",
    "control-plane", "cluster-management", "github-issues", "web-tasks",
    "multi-day", "24/7-research",
    # evaluation / safety
    "benchmark", "benchmark-sota", "evaluation", "agentic-eval",
    "leaderboard", "security", "safety", "adversarial", "vulnerability",
    "prompt-injection", "audit", "audit-trail", "auditable", "scanner",
    "privacy", "hardening", "secure", "zero-hallucination",
    "validation-gated", "evidence-grading", "traceable", "transparent",
    "explainable", "reproducible", "reproducible-research",
    # qualities / marketing
    "open-source", "lightweight", "extensible", "customizable",
    "cost-efficient", "cost-saving", "low-cost", "high-performance",
    "performance", "fast", "fastest", "smallest", "tiny", "award-winning",
    "pioneer", "popular", "early-stage", "industrial", "enterprise",
    "alternative", "reimplementation", "beyond-openclaw", "claw-like",
    "indie", "one-person-company", "pi-for-everyone",
    # lineage / family (claw4science editorial grouping) — both casings, the
    # historical import used the CamelCase forms verbatim
    "fork-family", "fork", "openclaw", "openclaw-compatible",
    "openclaw-fork", "openclaw-native", "nanoclaw-fork", "nanobot-based",
    "picoclaw-compatible", "successor-coreagent", "OpenClaw",
    "OpenClaw-compatible", "OpenClaw-fork", "OpenClaw-native",
    "NanoClaw-fork", "NanoBot-based", "PicoClaw-compatible",
    "successor-CoreAgent", "beyond-OpenClaw", "Prism-alternative",
    # languages — they duplicate the language field
    "rust", "Rust", "go", "Go", "typescript", "TypeScript",
    "javascript", "JavaScript", "python", "Python", "zig", "Zig",
    "shell", "Shell", "pure-python", "python-r",
    # status words — they belong in the status field, not tags
    "stable", "active", "stale", "archived", "graveyard", "gone",
    "dormant", "removed", "account-deleted", "no-repo",
])

# --- tag-type registry ------------------------------------------------------

#: Full tag-type registry; null for unregistered tags.
TAG_TYPE: dict[str, str] = {
    # institution — who is behind it
    "Stanford": "institution",
    "HKUDS": "institution",
    "Alibaba": "institution",
    "Princeton": "institution",
    "SJTU": "institution",
    "Tsinghua": "institution",
    "Harvard": "institution",
    "Microsoft": "institution",
    "NIH": "institution",
    "NVIDIA": "institution",
    "Sakana-AI": "institution",
    "Argonne": "institution",
    "Cambridge": "institution",
    "CUHK": "institution",
    "DeepMind": "institution",
    "EPFL": "institution",
    "Genentech": "institution",
    "HUST-BGI": "institution",
    "MIT": "institution",
    "MIT-LAMM": "institution",
    "Recursion": "institution",
    "Renmin-University": "institution",
    "SNAP-Lab": "institution",
    "Technion": "institution",
    "TIGER-AI-Lab": "institution",
    "UChicago": "institution",
    "University-of-Michigan": "institution",
    "ur-whitelab": "institution",
    "ZJUNLP": "institution",
    "OpenBMB": "institution",
    "Allen-AI": "institution",
    "dynamo-team": "institution",
    "NUS-MIT-Berkeley": "institution",
    "InternScience": "institution",
    "GBA-BI": "institution",
    "Nous-Research": "institution",
    "Medical-University-of-Vienna": "institution",
    "GENTEL-Lab": "institution",
    "KAUST": "institution",
    "HKUST": "institution",
    "Peking-University": "institution",
    "UW-Madison": "institution",
    "Candiolo-Cancer-Institute": "institution",
    "Texas-A&M": "institution",
    "Mayo-Clinic": "institution",
    "University-of-Macau": "institution",
    "Vanderbilt": "institution",
    "Anthropic": "institution",
    "GAIR": "institution",
    "NCBI": "institution",
    # team — the person behind it
    "Karpathy": "team",
    "Christoph-Bock": "team",
    "James-Zou": "team",
    "Jure-Leskovec": "team",
    "Mengdi-Wang": "team",
    "David-Ha": "team",
    "Aviv-Regev": "team",
    "Marinka-Zitnik": "team",
    "Rachel-Caspi": "team",
    "Wenbin-Hu": "team",
    "Shuangjia-Zheng": "team",
    "Fuchou-Tang": "team",
    "Yanlin-Zhang": "team",
    "Huajun-Chen": "team",
    "Jun-Chen": "team",
    "Christina-Kendziorski": "team",
    "Xin-Gao": "team",
    "Le-Cong": "team",
    "Markus-Buehler": "team",
    "Christopher-Heeschen": "team",
    "Edwin-Cheung": "team",
    "Zifeng-Wang": "team",
    # venue — where it was published
    "ICLR": "venue",
    "NeurIPS": "venue",
    "arXiv": "venue",
    "bioRxiv": "venue",
    "Nature-Methods": "venue",
    "Nature-Biotechnology": "venue",
    "Nature-BME": "venue",
    "Nature-Communications": "venue",
    "Nature-Computational-Science": "venue",
    "Bioinformatics": "venue",
    "Bioinformatics-Advances": "venue",
    "Briefings-in-Bioinformatics": "venue",
    "Cell-Reports-Methods": "venue",
    "Communications-Biology": "venue",
    "Digital-Discovery": "venue",
    "Genome-Biology": "venue",
    "AgentRxiv": "venue",
    "Nature": "venue",
    "Science": "venue",
    "Advanced-Science": "venue",
    "Methods-and-Protocols": "venue",
    "Analytical-Chemistry": "venue",
    "Advanced-Intelligent-Systems": "venue",
    "ICDMW": "venue",
    "IEEE-TBME": "venue",
    "JCIM": "venue",
    "Plant-Communications": "venue",
    "Lancet-Digital-Health": "venue",
    "Cell": "venue",
    "Nature-Medicine": "venue",
    "NEJM-AI": "venue",
    "JCST": "venue",
    "Advanced-Materials": "venue",
    "ACL-Findings": "venue",
    "EMNLP-Findings": "venue",
    "Innovation": "venue",
    "EMNLP": "venue",
    "ACL": "venue",
    "ICML": "venue",
    # tech — agent-relevant framework/protocol it builds on
    "MCP": "tech",
    "A2A": "tech",
    "LangGraph": "tech",
    "LangChain": "tech",
    "Claude-Code": "tech",
}

VENUE_ALIASES: dict[str, str] = {
    # preprint servers
    "ArXiv": "arXiv",
    "arXiv.org": "arXiv",
    # conferences — full names and year-suffixed spellings
    "International Conference on Learning Representations": "ICLR",
    "ICLR 2026": "ICLR",
    "ICLR-2026": "ICLR",
    "Neural Information Processing Systems": "NeurIPS",
    "NeurIPS 2025": "NeurIPS",
    "NeurIPS-2025": "NeurIPS",
    "2024 IEEE International Conference on Data Mining Workshops (ICDMW)":
        "ICDMW",
    "ICDMW-2024": "ICDMW",
    "International Conference on Machine Learning": "ICML",
    # NLP conferences — S2/ACL Anthology full-proceedings spellings
    "Conference on Empirical Methods in Natural Language Processing": "EMNLP",
    "Proceedings of the 2025 Conference on Empirical Methods in Natural Language Processing": "EMNLP",
    "Proceedings of the 63rd Annual Meeting of the Association for Computational Linguistics (Volume 1: Long Papers)": "ACL",
    "Annual Meeting of the Association for Computational Linguistics": "ACL",
    # journals — abbreviations and full names
    "Nature Biomedical Engineering": "Nature-BME",
    "The Lancet Digital Health": "Lancet-Digital-Health",
    # Cell-partner journal "The Innovation"; S2 carries "Innovation (Cambridge (Mass.))"
    "The Innovation": "Innovation",
    "Innovation (Cambridge (Mass.))": "Innovation",
    "Journal of chemical information and modeling": "JCIM",
    "IEEE transactions on bio-medical engineering": "IEEE-TBME",
    "Bioinform.": "Bioinformatics",
    "Journal of Computational Science and Technology": "JCST",
    # S2's misspelling of Advanced Materials (DOI prefix 10.1002/adma)
    "Advances in Materials": "Advanced-Materials",
    # conference findings tracks
    "Findings of ACL 2026": "ACL-Findings",
    "Findings of the Association for Computational Linguistics: ACL 2026":
        "ACL-Findings",
    "Findings of EMNLP 2025": "EMNLP-Findings",
    "Findings of the Association for Computational Linguistics: EMNLP 2025":
        "EMNLP-Findings",
}

def _canonical_fold(s: str) -> str:
    """Lower-case and strip non-alphanumeric characters for venue matching."""
    return re.sub(r"[^a-z0-9]", "", s.lower())


#: Lower-case, punctuation-stripped fold of every canonical venue + alias.
_VENUE_FOLD: dict[str, str] = {}
for _tag, _type in TAG_TYPE.items():
    if _type == "venue":
        _VENUE_FOLD[_canonical_fold(_tag)] = _tag
for _alias, _canonical in VENUE_ALIASES.items():
    _VENUE_FOLD[_canonical_fold(_alias)] = _canonical

#: Canonical display order of tag types.
TAG_TYPES: tuple[TagType, ...] = ("institution", "team", "venue", "tech")


def find_tag_policy_violations(tags: list[str]) -> list[str]:
    """Return tags that violate the objective-attribution policy, with reasons.

    Empty list = policy clean.
    """
    problems: list[str] = []
    for t in tags:
        if re.match(r"^[0-9]", t):
            problems.append(f"{t} — count-based marketing (no leading digits)")
        elif t in GENERIC_TAGS:
            problems.append(f"{t} — generic descriptor, belongs in category/description")
    return problems


def tag_type(tag: str) -> str | None:
    """Typed lookup; None for unregistered tags."""
    return TAG_TYPE.get(tag)


def canonical_venue(venue: str) -> str:
    """Canonical venue tag for a free-text venue string.

    Unknown input is returned unchanged.
    """
    return _VENUE_FOLD.get(_canonical_fold(venue.strip()), venue)


def registered_venue_tag(venue: str) -> str | None:
    """Registered venue tag for a paper venue, or None when it is unknown."""
    tag = canonical_venue(venue)
    return tag if tag_type(tag) == "venue" else None


def registered_tags() -> list[str]:
    """Registry contents, for tests that keep data and registry in sync."""
    return list(TAG_TYPE.keys())
