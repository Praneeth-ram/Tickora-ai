"""In-process Qwen + LoRA model that turns a question into a query plan.
The model is loaded once at application startup (see backend/main.py lifespan)
and shared by all requests. Generation is serialized with a lock because a
single GPU can run one generation at a time.
torch and transformers are imported inside load_model(), so the backend can
start on machines that do not have the model dependencies installed.
"""
import copy
import json
import logging
import threading
from datetime import date
from pathlib import Path
from typing import Any
import time

import re as regex

from backend.services.llm_chat_service import ModelUnavailableError, PlanRejectedError
from backend.services.operation_registry import build_operation_registry

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BASE_MODEL = "Qwen/Qwen2.5-3B-Instruct"
ADAPTER_PATH = PROJECT_ROOT / "models"
DATASET_PATH = PROJECT_ROOT / "data" / "tickora_sft_expanded.jsonl"
CATALOG_PATH = PROJECT_ROOT / "data" / "model_catalog.json"
MAX_NEW_TOKENS = 128
PREFIX_CHUNK_SIZE = 128

DATE_VALUE_RE = regex.compile(r"^\d{4}-\d{2}(-\d{2})?$")

_generation_lock = threading.Lock()
_state: dict[str, Any] = {
    "tokenizer": None,
    "model": None,
    "catalog": {},
    "system_prompt": None,
    "prefix": None,
}

def is_loaded() -> bool:
    return _state["model"] is not None and _state["tokenizer"] is not None

def _load_catalog() -> dict[str, dict[str, Any]]:
    """Load the saved catalog and merge in the currently registered operations."""
    with CATALOG_PATH.open("r", encoding="utf-8") as f:
        items = json.load(f)

    catalog_items = {item["operation_id"]: item for item in items}

    # Newly registered entities become available without another fine-tune.
    runtime_registry = build_operation_registry(schema_name="public")
    for operation_id, definition in runtime_registry.items():
        catalog_items[operation_id] = {
            "operation_id": operation_id,
            "entity": definition.get("entity"),
            "operation": definition.get("operation"),
            "fields": definition.get("fields", []),
            "filters": definition.get("filters", []),
            "date_field": definition.get("date_field"),
            "date_fields": definition.get("date_fields", []),
            "aggregate_fields": definition.get("aggregate_fields", []),
            "group_by_fields": definition.get("group_by_fields", []),
        }
    return catalog_items

def _build_system_prompt(catalog: dict[str, dict[str, Any]]) -> str:
    with DATASET_PATH.open("r", encoding="utf-8") as f:
        first_example = json.loads(next(f))

    system_prompt = next(
        item["content"]
        for item in first_example["messages"]
        if item["role"] == "system"
    )

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

    prompt_catalog = [
        {
            "operation_id": operation_id,
            "entity": item.get("entity"),
            "operation": item.get("operation"),
            "fields": item.get("fields", []),
            "filters": item.get("filters", []),
            "aggregate_fields": item.get("aggregate_fields", []),
            "group_by_fields": item.get("group_by_fields", []),
            "date_fields": item.get("date_fields", []),
        }
        for operation_id, item in sorted(catalog.items())
    ]

    system_prompt += (
        "\n\nCURRENT AVAILABLE OPERATION CATALOG:\n"
        + json.dumps(prompt_catalog, ensure_ascii=False)
        + "\n\nOPERATION SELECTION RULES:\n"
        "- Select only an exact operation_id from the catalog.\n"
        "- Never invent operation IDs or database field names.\n"
        "- For salary or payroll questions, use "
        "'payroll_summary.list' if it is present in the catalog.\n"
        "- For payroll months, use ISO date ranges on the "
        "approved period_start and period_end filters.\n"
        "- Return only the JSON query plan, without explanation.\n"
    )
    return system_prompt

def _build_prefix(tokenizer, model, system_prompt: str) -> dict[str, Any]:
    """Run the fixed system prompt in chunks and keep its KV cache."""
    import torch

    device = model.get_input_embeddings().weight.device
    prefix_text = tokenizer.apply_chat_template(
        [{"role": "system", "content": system_prompt}],
        tokenize=False,
    )
    prefix_ids = tokenizer(prefix_text, return_tensors="pt").input_ids.to(device)
    with torch.inference_mode():
        cache = None
        for start in range(0, prefix_ids.shape[1], PREFIX_CHUNK_SIZE):
            end = start + PREFIX_CHUNK_SIZE
            cache = model(
                prefix_ids[:, start:end],
                past_key_values=cache,
                use_cache=True,
            ).past_key_values
    return {"ids": prefix_ids, "cache": cache, "date": date.today(), "system_prompt": system_prompt}

def load_model() -> None:
    """Load the tokenizer, base model, and LoRA adapter. Raises on failure."""
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable; the model requires a CUDA GPU.")
    if not (ADAPTER_PATH / "adapter_config.json").exists():
        raise FileNotFoundError(f"Adapter not found: {ADAPTER_PATH}")
    if not DATASET_PATH.exists():
        raise FileNotFoundError(f"Dataset not found: {DATASET_PATH}")

    catalog = _load_catalog()
    system_prompt = _build_system_prompt(catalog)

    quantization_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=True,
    )
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=False)
    base_model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        quantization_config=quantization_config,
        torch_dtype=torch.float16,
        device_map="auto",
        low_cpu_mem_usage=True,
        trust_remote_code=False,
    )
    model = PeftModel.from_pretrained(base_model, str(ADAPTER_PATH), is_trainable=False)
    model.eval()

    prefix = _build_prefix(tokenizer, model, system_prompt)
    _state.update(tokenizer=tokenizer, model=model, catalog=catalog,
                  system_prompt=system_prompt, prefix=prefix)

    logger.info("Tickora model loaded on %s", torch.cuda.get_device_name(0))

def generate_plan(question: str) -> dict[str, Any]:
    """Return a validated query plan for the question.
    Raises ModelUnavailableError when the model is not loaded or generation fails,
    and PlanRejectedError when the output is not a plan from the catalog.
    """
    if not is_loaded():
        raise ModelUnavailableError("The Tickora language model is temporarily unavailable.")

    import torch

    tokenizer = _state["tokenizer"]
    model = _state["model"]
    catalog = _state["catalog"]
    device = model.get_input_embeddings().weight.device

    started = time.perf_counter()
    with _generation_lock, torch.inference_mode():
        # The system prompt contains today's date, so rebuild it when the day changes.
        if _state["prefix"]["date"] != date.today():
            _state["system_prompt"] = _build_system_prompt(catalog)
            _state["prefix"] = _build_prefix(tokenizer, model, _state["system_prompt"])
        prefix = _state["prefix"]

        messages = [
            {"role": "system", "content": _state["system_prompt"]},
            {"role": "user", "content": question},
        ]
        full_text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        full_ids = tokenizer(full_text, return_tensors="pt").input_ids.to(device)
        prefix_len = prefix["ids"].shape[1]

        # Reuse the cached prefix only if the prompt really starts with it.
        same_prefix = torch.equal(full_ids[:, :prefix_len], prefix["ids"])
        cache = copy.deepcopy(prefix["cache"]) if same_prefix else None

        try:
            output = model.generate(
                input_ids=full_ids,
                attention_mask=torch.ones_like(full_ids),
                past_key_values=cache,
                max_new_tokens=MAX_NEW_TOKENS,
                do_sample=False,
                pad_token_id=tokenizer.eos_token_id,
            )
        except Exception as exc:
            logger.exception("Model generation failed")
            raise ModelUnavailableError("The Tickora language model is temporarily unavailable.") from exc

    inputs = {"input_ids": full_ids}
    generated_tokens = output[0, inputs["input_ids"].shape[1]:]
    answer = tokenizer.decode(generated_tokens, skip_special_tokens=True).strip()
    elapsed = time.perf_counter() - started
    logger.debug(
        "plan in %.2fs | prompt_tokens=%d | new_tokens=%d | answer=%r",
        elapsed,
        inputs["input_ids"].shape[1],
        generated_tokens.shape[0],
        answer,
    )

    rejected = "I couldn't turn that question into a supported query."
    try:
        plan = json.loads(answer)
    except json.JSONDecodeError as exc:
        logger.debug("Model returned invalid JSON: %r", answer)
        raise PlanRejectedError(rejected) from exc

    if not isinstance(plan, dict):
        raise PlanRejectedError(rejected)

    operation_id = plan.get("operation_id")
    filters = plan.get("filters")
    if operation_id not in catalog:
        logger.debug("Model returned unknown operation %r", operation_id)
        raise PlanRejectedError(rejected)
    if not isinstance(filters, dict):
        raise PlanRejectedError(rejected)

    allowed_filters = set(catalog[operation_id].get("filters", []))
    if not set(filters).issubset(allowed_filters):
        rejected_filters = sorted(set(filters) - allowed_filters)
        logger.warning(
            "Model returned unsupported filters for %s: %s",
            operation_id, rejected_filters,
        )
        raise PlanRejectedError(rejected)

    for name, value in filters.items():
        if not any(token in name for token in ("date", "month", "period")):
            continue
        values = value.values() if isinstance(value, dict) else [value]
        for item in values:
            if item is None:
                continue
            if not isinstance(item, str) or not DATE_VALUE_RE.match(item):
                logger.warning("Model returned invalid date value for %s.%s", operation_id, name)
                raise PlanRejectedError(rejected)

    return plan