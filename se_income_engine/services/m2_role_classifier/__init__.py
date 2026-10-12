"""M2 Role classifier (Sections 5, 7, 8.1).

Technique: gradient-boosted model + text/sequence embeddings, or a calibrated ensemble. Responsibility: transaction
role probabilities. The first four modules build the evidence the model scores; the last two are the model itself.

Reading order:
    1. s05_identifier_extraction.py   VPA, IFSC, UTR, names, own-account markers, holder-name match
    2. s05_narration_encoder.py       hashed character-trigram narration embedding
    3. s05_entity_resolution.py       counterparty clustering and cluster statistics
    4. s08_neighbourhood_features.py  NF01-NF12, counterfactual retention, match candidates
    5. s07_role_classifier.py         priors + evidence layers + evidence gating -> P(role) per transaction
    6. s07_probability_calibrator.py  temperature calibration
"""
