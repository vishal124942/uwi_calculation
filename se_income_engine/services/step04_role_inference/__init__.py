"""Step 4 - Probabilistic role inference (Section 7).

Reading order:
    1. s07_role_classifier.py         priors + evidence layers + evidence gating -> P(role) per transaction
    2. s07_probability_calibrator.py  temperature calibration
    3. s07_rule_overlay.py            versioned deterministic rules R001-R012 (SET / MULTIPLY / RESTRICT)
"""
