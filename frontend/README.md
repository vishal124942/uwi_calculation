# UWI pipeline explorer

Next.js UI for the self-employed income engine. Start the API from the repository root, then the UI:

```bash
.venv/bin/uvicorn se_income_engine.api.app:app --reload
cd frontend && npm install && npm run dev
```

Open http://localhost:3000, then run a demo statement or upload `.xlsx` / `.xlsm` / `.csv` statements.
Set `NEXT_PUBLIC_API_URL` if the API is not on `http://localhost:8000`.

- `src/lib/api.ts` reads the `/v1/ui/trace` NDJSON stream; `src/lib/trace.ts` merges each step's transaction columns.
- `src/components/ComponentView.tsx` renders one page per Section 24.1 component; the code of each lives in its own
  package, `se_income_engine/services/m1_parser_normaliser/` … `m9_policy_layer/` and `services/supporting/`.
- `src/components/steps/StepNN.tsx` renders the tables of one pipeline checkpoint (`stepNN_*` in the trace); a component
  that shares a checkpoint with another renders only its part (`PART_VIEWS` in `src/lib/components.ts`).
- `src/components/TransactionDrawer.tsx` shows one transaction's journey through M1, the integrity gate, M2, M3, M4 and the economic ledger.
