from pathlib import Path

path = Path("backend/campaign_api.py")
text = path.read_text(encoding="utf-8")

insert_after = '''def _attach_weis_gamma_summaries(
    campaigns: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    return [_attach_weis_gamma_summary(c) for c in campaigns]


'''

helper = '''def _count_by_field(
    campaigns: List[Dict[str, Any]],
    field: str,
) -> Dict[str, int]:
    counts: Dict[str, int] = {}

    for campaign in campaigns:
        value = campaign.get(field)

        if value is None:
            key = "NONE"
        elif value == "":
            key = "EMPTY"
        else:
            key = str(value)

        counts[key] = counts.get(key, 0) + 1

    return counts


'''

if helper not in text:
    if insert_after not in text:
        raise SystemExit("Could not find insertion point for _count_by_field.")

    text = text.replace(insert_after, insert_after + helper, 1)

old_status = '''@router.get("/status")
def status():
    campaigns = _store().get_active_campaigns()

    def state(c):
        return str(c.get("current_state") or c.get("state_enum") or "").upper()

    return {
        "active_campaigns": len(campaigns),
        "birth_candidates": sum(1 for c in campaigns if state(c) == "BIRTH"),
        "expanding_campaigns": sum(1 for c in campaigns if state(c) == "EXPANDING"),
        "distribution_risk": sum(
            1 for c in campaigns if state(c) == "DISTRIBUTION_RISK"
        ),
    }
'''

new_status = '''@router.get("/status")
def status():
    campaigns = _store().get_active_campaigns()
    campaigns = _attach_weis_gamma_summaries(campaigns)

    def state(c):
        return str(c.get("current_state") or c.get("state_enum") or "").upper()

    weis_gamma_present = sum(
        1 for c in campaigns if c.get("weis_gamma_present") is True
    )

    weis_gamma_missing = sum(
        1 for c in campaigns if c.get("weis_gamma_present") is not True
    )

    weis_gamma_transition_enabled = sum(
        1 for c in campaigns if c.get("weis_gamma_transition_enabled") is True
    )

    gamma_no_option_chain = sum(
        1
        for c in campaigns
        if c.get("weis_gamma_gamma_status") == "NO_OPTION_CHAIN_INPUT"
    )

    gamma_stale_or_unconfirmed = sum(
        1
        for c in campaigns
        if (
            c.get("weis_gamma_phase") == "WEIS_ONLY_GAMMA_STALE"
            or c.get("weis_gamma_gamma_status") in {
                "NO_OPTION_CHAIN_INPUT",
                "NO_GAMMA_INPUT",
                "NOT_PRESENT",
                None,
            }
        )
    )

    return {
        "active_campaigns": len(campaigns),
        "birth_candidates": sum(1 for c in campaigns if state(c) == "BIRTH"),
        "expanding_campaigns": sum(1 for c in campaigns if state(c) == "EXPANDING"),
        "distribution_risk": sum(
            1 for c in campaigns if state(c) == "DISTRIBUTION_RISK"
        ),
        "weis_gamma_status_center": {
            "api_fields_enabled": True,
            "total_campaigns": len(campaigns),
            "weis_gamma_present": weis_gamma_present,
            "weis_gamma_missing": weis_gamma_missing,
            "transition_enabled": weis_gamma_transition_enabled,
            "transition_enabled_expected": False,
            "gamma_no_option_chain": gamma_no_option_chain,
            "gamma_stale_or_unconfirmed": gamma_stale_or_unconfirmed,
            "phase_counts": _count_by_field(campaigns, "weis_gamma_phase"),
            "rank_bucket_counts": _count_by_field(campaigns, "weis_gamma_rank_bucket"),
            "gamma_status_counts": _count_by_field(campaigns, "weis_gamma_gamma_status"),
            "fusion_state_counts": _count_by_field(campaigns, "weis_gamma_fusion_state"),
        },
    }
'''

if old_status not in text:
    raise SystemExit("status() block not found.")

text = text.replace(old_status, new_status, 1)

path.write_text(text, encoding="utf-8")
print("Patched campaign status with Weis-Gamma summary counts.")
