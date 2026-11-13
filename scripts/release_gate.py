import json, sys
from backend.services.model_inference import load_model, generate_plan

golden = json.load(open("tests/fixtures/golden_plans.json", encoding="utf-8"))
load_model()
changed = [q for q, plan in golden.items() if generate_plan(q) != plan]
print(f"{len(changed)} of {len(golden)} plans changed")
for q in changed:
    print(" -", q)
sys.exit(1 if changed else 0)