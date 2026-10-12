"""M4 Flow-pair model (Sections 8.2, 17).

Technique: heuristic + graph matching / learned pair scorer. Responsibility: transfers, reversals, pass-through,
recycling.

Reading order:
    1. s08_flow_pair_graph.py              reversal / recycling / pass-through pairs and role updates
    2. s17_multi_account_consolidation.py  merged transaction stream, inter-account transfer matching, MA01-MA10

consolidate_transaction_stream runs before M2 (it builds the stream every later component reads) and
compute_multi_account_features runs with the behaviour and risk signals; the transfer matching runs with M4.
"""
