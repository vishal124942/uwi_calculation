"""M1 Parser/normaliser (Section 3).

Technique: rules/templates + deterministic transforms. Responsibility: statement extraction and canonical transactions.

Reading order:
    1. s03_statement_parsers.py             analyser xlsx / generic csv -> AccountInput + Transaction rows
    2. s03_transaction_canonicalisation.py  narration normalisation, intraday ordering, balance_before
    3. s03_channel_family_normaliser.py     source Mode / Payment Mode columns -> channel family (UPI, NEFT, CASH, FEE, ...)
"""
