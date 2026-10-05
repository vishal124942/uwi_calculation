"""Step 1 - Ingest and clean (Section 3).

Reading order:
    1. s03_statement_parsers.py             analyser xlsx / generic csv -> AccountInput + Transaction rows
    2. s03_transaction_canonicalisation.py  narration normalisation, intraday ordering, balance_before
    3. s03_channel_family_normaliser.py     narration -> channel family (UPI, NEFT, CASH, FEE, ...)
"""
