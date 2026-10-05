"""Step 3 - Per-transaction evidence (Sections 5, 8.1).

Reading order:
    1. s05_identifier_extraction.py   VPA, IFSC, UTR, names, own-account markers, holder-name match
    2. s05_narration_encoder.py       hashed character-trigram narration embedding
    3. s05_entity_resolution.py       counterparty clustering and cluster statistics
    4. s08_neighbourhood_features.py  NF01-NF12, counterfactual retention, match candidates
"""
