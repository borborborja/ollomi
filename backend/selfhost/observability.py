import logging


logger = logging.getLogger(__name__)


def record_fallback(*, purpose, from_profile, to_profile, reason, outcome):
    """Emit bounded provider-fallback telemetry without credentials or prompts."""
    logger.warning(
        "ollomi_provider_fallback purpose=%s from=%s to=%s reason=%s outcome=%s",
        purpose,
        from_profile or "none",
        to_profile or "none",
        reason,
        outcome,
    )
