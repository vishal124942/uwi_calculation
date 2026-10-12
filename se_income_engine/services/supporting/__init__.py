"""Supporting stages: pipeline stages the Section 24.1 component table does not number as M components.

    dq_integrity_gate        gate      Section 4            runs after M1; stops the analysis before any model
    ledger_operating_cash    features  Sections 10-12       turns M2-M4 role probabilities into rupee buckets
    signals_behaviour_risk   features  Sections 14-20       inputs to M6-M9
    audit_explainability     output    Sections 23, 25, 28  explains and records the finished decision
"""
