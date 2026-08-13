"""Deterministic response-closure classification."""


def classify(expected, observed):
    """Classify the relationship between an expectation and observation."""
    if expected is None or observed is None:
        return "inconclusive"
    if expected == observed:
        return "confirmed"
    return "contradicted"
