"""Tests for agentx/policy.py — categories, tag registry, and policy guards."""

from awescholar.agentx import policy

# --- find_tag_policy_violations ---------------------------------------------

def test_find_tag_policy_violations_flags_marketing_counts():
    assert policy.find_tag_policy_violations(["10x-faster"]) == [
        "10x-faster — count-based marketing (no leading digits)",
    ]


def test_find_tag_policy_violations_flags_generic_descriptors():
    assert policy.find_tag_policy_violations(["multi-agent"]) == [
        "multi-agent — generic descriptor, belongs in category/description",
    ]


def test_find_tag_policy_violations_returns_empty_for_registered_tag():
    assert policy.find_tag_policy_violations(["Stanford"]) == []


def test_find_tag_policy_violations_is_case_sensitive():
    assert len(policy.find_tag_policy_violations(["bioinformatics"])) == 1
    assert policy.tag_type("Bioinformatics") == "venue"


# --- tagType -----------------------------------------------------------------

def test_tag_type_registered_tags():
    assert policy.tag_type("Stanford") == "institution"
    assert policy.tag_type("Karpathy") == "team"
    assert policy.tag_type("NeurIPS") == "venue"
    assert policy.tag_type("MCP") == "tech"


def test_tag_type_rejects_unknown():
    assert policy.tag_type("Not-A-Tag") is None


# --- canonicalVenue ----------------------------------------------------------

def test_canonical_venue_folds_alias_spellings():
    assert policy.canonical_venue("NeurIPS 2025") == "NeurIPS"
    assert policy.canonical_venue("The Lancet Digital Health") == \
        "Lancet-Digital-Health"
    assert policy.canonical_venue("The Innovation") == "Innovation"
    assert policy.canonical_venue("Innovation (Cambridge (Mass.))") == \
        "Innovation"


def test_canonical_venue_folds_nlp_and_ml_conference_proceedings():
    assert policy.canonical_venue(
        "Conference on Empirical Methods in Natural Language Processing"
    ) == "EMNLP"
    assert policy.canonical_venue(
        "Proceedings of the 2025 Conference on Empirical Methods in"
        " Natural Language Processing"
    ) == "EMNLP"
    assert policy.canonical_venue(
        "Proceedings of the 63rd Annual Meeting of the Association for"
        " Computational Linguistics (Volume 1: Long Papers)"
    ) == "ACL"
    assert policy.canonical_venue(
        "Annual Meeting of the Association for Computational Linguistics"
    ) == "ACL"
    assert policy.canonical_venue(
        "International Conference on Machine Learning"
    ) == "ICML"


def test_canonical_venue_folds_punctuation_stripped_case_insensitive():
    assert policy.canonical_venue("arxiv.org") == "arXiv"
    assert policy.canonical_venue("  Methods and Protocols ") == \
        "Methods-and-Protocols"


def test_canonical_venue_passes_unknown_through():
    assert policy.canonical_venue(
        "Some Unknown Workshop Series"
    ) == "Some Unknown Workshop Series"


def test_canonical_venue_keeps_every_venue_resolvable():
    for tag in policy.registered_tags():
        if policy.tag_type(tag) == "venue":
            assert policy.canonical_venue(tag) == tag


# --- registeredTags ----------------------------------------------------------

def test_registered_tags_non_empty():
    assert len(policy.registered_tags()) > 0


# --- categories / lifecycle --------------------------------------------------

def test_categories_has_thirteen_entries():
    assert len(policy.CATEGORIES) == 13


def test_category_order_matches_categories_keys():
    assert policy.CATEGORY_ORDER == list(policy.CATEGORIES)


def test_lifecycle_constants():
    assert policy.NURSERY_MAX_STARS == 30
    assert policy.NURSERY_ARCHIVE_IDLE_DAYS == 180
    assert policy.ESTABLISHED_ARCHIVE_IDLE_DAYS == 3 * 365
    assert policy.AUTO_STABLE_MIN_STARS == 1000
