"""Step 5 - Flow pairing and multi-account consolidation (Sections 8.2, 17).

Reading order:
    1. s08_flow_pair_graph.py              reversal / recycling / pass-through pairs and role updates
    2. s17_multi_account_consolidation.py  merged transaction stream, inter-account transfer matching, MA01-MA10

consolidate_transaction_stream runs earlier (right after step 2) and compute_multi_account_features runs later
(during step 7); the transfer matching itself runs here.
"""
