"""Behaviour and risk signals (Sections 14-20): deterministic feature engines feeding M6-M9.

Reading order (execution order; M6 runs after the financing engine because it needs the financing events):
    1. s14_balance_liquidity_engine.py  BAL01-BAL12
    2. s15_financing_debt_service.py    FIN01-FIN10, debt service, financing events
    3. s16_owner_extraction.py          OWN01-OWN08
    4. s18_trend_seasonality.py         TR01-TR12, trend regime
    5. s20_coverage_observability.py    CV01-CV10, coverage risk
    6. s19_anomaly_detection.py         AN01-AN14
"""
