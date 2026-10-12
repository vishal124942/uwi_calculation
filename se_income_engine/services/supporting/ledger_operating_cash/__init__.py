"""Economic ledger (Sections 10-12): probability-weighted rupee buckets per transaction, month and window.

Reading order:
    1. s10_operating_inflow_reconstruction.py   IN05-IN14
    2. s11_operating_outflow_reconstruction.py  OUT01-OUT14
    3. s10_s11_window_aggregation.py            economic ledger, EOC / COR / ROC per window and month
    4. s12_cash_cheque_merchant_passthrough.py  cash business probability, pass-through economics

The aggregation first runs without cash eligibility to give M5 its features; when any cash withdrawal is then found
eligible (that test uses M5's archetype) it runs again with the eligibility applied.
"""
