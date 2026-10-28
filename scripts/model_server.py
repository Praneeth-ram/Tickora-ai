from datetime import date
import json
from pathlib import Path
from threading import Lock

import torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
)
from peft import PeftModel

BASE_MODEL = "Qwen/Qwen2.5-3B-Instruct"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
ADAPTER_PATH = PROJECT_ROOT / "models"
DATASET_PATH = PROJECT_ROOT / "data" / "tickora_sft_expanded.jsonl"
CATALOG_PATH = PROJECT_ROOT / "data" / "model_catalog.json"

app = FastAPI(title="Tickora Model Inference Service")

tokenizer = None
model = None
catalog = {}
generation_lock = Lock()
class QuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)

def load_catalog():
    with CATALOG_PATH.open("r", encoding="utf-8") as f:
        items = json.load(f)
    return {item["operation_id"]: item for item in items}

@app.on_event("startup")
def load_model():
    global tokenizer, model, catalog

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable.")

    if not (ADAPTER_PATH / "adapter_config.json").exists():
        raise FileNotFoundError(f"Adapter not found: {ADAPTER_PATH}")

    if not DATASET_PATH.exists():
        raise FileNotFoundError(f"Dataset not found: {DATASET_PATH}")

    catalog = load_catalog()

    with DATASET_PATH.open("r", encoding="utf-8") as f:
        first_example = json.loads(next(f))

    system_prompt = next(
        item["content"]
        for item in first_example["messages"]
        if item["role"] == "system"
    )

    # Add an explicit rule for relative dates and JSON-only output.
    system_prompt += (
        "\nReturn exactly one valid JSON object. Never output SQL, "
        "JavaScript, Markdown, or explanatory text. Never use code "
        "expressions such as new Date(). For relative dates such as "
        "'coming up' or 'today', use only a date or relative-date "
        "representation explicitly supported by the operation catalog. "
        "If the required date cannot be represented safely, omit that "
        "date filter rather than inventing an expression."
    )
    today_val = date.today()
    system_prompt += (
        f"\nCURRENT TEMPORAL CONTEXT:"
        f"\n- Today's date is {today_val.isoformat()} (Year: {today_val.year}, Month: {today_val.strftime('%B')})."
        f"\n- When the user refers to 'this year', the year is {today_val.year}."
        f"\n- When the user refers to 'this month', the month is {today_val.strftime('%B')} {today_val.year}."
    )
    system_prompt += (
        "\nIMPORTANT OPERATIONAL MAPPINGS:"
        "\n- For questions asking for an 'attendance summary', breakdown, or status overview, use 'attendance.group_by' with 'group_by_field': 'status' and 'aggregate_function': 'count'."
        "\n- For questions asking 'how many' or to count records (e.g. how many late days, how many leave requests), use '<entity>.count'."
        "\n- For questions asking for total worked minutes, total hours worked, or total overtime, use 'attendance.sum' with 'aggregate_field'."
        "\n- For questions asking for clock-in time, check-in time, punch-in time, or attendance records, use 'attendance.list'."
        "\n- For WFH requests, use 'wfh_request.list' (or 'wfh_request.count')."
        "\n- For leave requests, use 'leave_request.list' (or 'leave_request.count')."
        "\n- For timesheets, use 'timesheet.list' (or 'timesheet.count')."
        "\n- For holidays, use 'holiday.list' (or 'holiday.count')."
    )

    app.state.system_prompt = system_prompt

    quantization_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=True,
    )

    tokenizer = AutoTokenizer.from_pretrained(
        BASE_MODEL,
        trust_remote_code=False,
    )

    base_model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        quantization_config=quantization_config,
        torch_dtype=torch.float16,
        device_map="auto",
        low_cpu_mem_usage=True,
        trust_remote_code=False,
    )

    model = PeftModel.from_pretrained(
        base_model,
        str(ADAPTER_PATH),
        is_trainable=False,
    )
    model.eval()

    print("Tickora model loaded.")
    print("GPU:", torch.cuda.get_device_name(0))

@app.get("/health")
def health():
    return {
        "status": "ready" if model is not None else "loading",
        "model_loaded": model is not None,
    }

@app.get("/operations")
def operations():
    return {
        "operations": list(catalog.keys()),
    }

@app.post("/predict")
def predict(request: QuestionRequest):
    if model is None or tokenizer is None:
        raise HTTPException(status_code=503, detail="Model not ready")

    messages = [
        {"role": "system", "content": app.state.system_prompt},
        {"role": "user", "content": request.question},
    ]

    prompt = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )
    inputs = tokenizer(prompt, return_tensors="pt")
    input_device = model.get_input_embeddings().weight.device
    inputs = {key: value.to(input_device) for key, value in inputs.items()}

    try:
        with generation_lock, torch.inference_mode():
            output = model.generate(
                **inputs,
                max_new_tokens=128,
                do_sample=False,
                pad_token_id=tokenizer.eos_token_id,
            )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Model generation failed",
        ) from exc

    generated_tokens = output[0, inputs["input_ids"].shape[1]:]
    answer = tokenizer.decode(
        generated_tokens,
        skip_special_tokens=True,
    ).strip()

    # Parse the model output; never execute generated code or SQL.
    try:
        plan = json.loads(answer)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=422,
            detail="Model returned invalid JSON",
        )

    if not isinstance(plan, dict):
        raise HTTPException(
            status_code=422,
            detail="Model output must be a JSON object",
        )

    operation_id = plan.get("operation_id")
    filters = plan.get("filters")

    print("\n--- TICKORA MODEL DEBUG ---")
    print("Question:", request.question)
    print("Raw model output:", repr(answer))
    print("Parsed plan:", plan)
    print("Generated operation_id:", repr(operation_id))
    print("Available operations:", list(catalog.keys()))
    print("--- END DEBUG ---\n")

    if operation_id not in catalog:
        raise HTTPException(
            status_code=422,
            detail="Model returned an unknown operation",
        )

    if not isinstance(filters, dict):
        raise HTTPException(
            status_code=422,
            detail="Model filters must be a JSON object",
        )

    allowed_filters = set(catalog[operation_id].get("filters", []))
    if not set(filters).issubset(allowed_filters):
        raise HTTPException(
            status_code=422,
            detail="Model returned unsupported filters",
        )

    return {"plan": plan}
