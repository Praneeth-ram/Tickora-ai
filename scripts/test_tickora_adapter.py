import torch
from pathlib import Path
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
)
from peft import PeftModel
import json

BASE_MODEL = "Qwen/Qwen2.5-3B-Instruct"
ADAPTER_PATH = Path(__file__).resolve().parents[1] / "models"

def main():
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable. Check the model environment.")

    print("GPU:", torch.cuda.get_device_name(0))
    print("Adapter:", ADAPTER_PATH)

    if not (ADAPTER_PATH / "adapter_config.json").exists():
        raise FileNotFoundError(f"Adapter config not found: {ADAPTER_PATH}")

    quantization_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=True,
    )

    print("Loading tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(
        BASE_MODEL,
        trust_remote_code=False,
    )

    print("Loading quantized base model...")
    base_model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        quantization_config=quantization_config,
        torch_dtype=torch.float16,
        device_map="auto",
        low_cpu_mem_usage=True,
        trust_remote_code=False,
    )

    print("Loading Tickora LoRA adapter...")
    model = PeftModel.from_pretrained(
        base_model,
        str(ADAPTER_PATH),
        is_trainable=False,
    )
    model.eval()

        # Load the exact system prompt used in the training dataset
    dataset_path = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "tickora_sft_expanded.jsonl"
    )

    if not dataset_path.exists():
        raise FileNotFoundError(
            f"Training dataset not found: {dataset_path}"
        )

    with dataset_path.open("r", encoding="utf-8") as f:
        first_example = json.loads(next(f))

    system_prompt = next(
        message["content"]
        for message in first_example["messages"]
        if message["role"] == "system"
    )

    messages = [
        {
            "role": "system",
            "content": system_prompt,
        },
        {
            "role": "user",
            "content": "Show my timesheet records for October 2026"
        },
    ]

    prompt = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )
    inputs = tokenizer(prompt, return_tensors="pt")
    input_device = model.get_input_embeddings().weight.device
    inputs = {key: value.to(input_device) for key, value in inputs.items()}

    print("Generating prediction...")
    with torch.inference_mode():
        output = model.generate(
            **inputs,
            max_new_tokens=128,
            do_sample=False,
            pad_token_id=tokenizer.eos_token_id,
        )

    generated_tokens = output[0, inputs["input_ids"].shape[1]:]
    answer = tokenizer.decode(generated_tokens, skip_special_tokens=True)

    print("\n--- TICKORA MODEL OUTPUT ---")
    print(answer)
    print("\nGPU memory allocated:",
          round(torch.cuda.memory_allocated(0) / 1024**3, 2), "GiB")

if __name__ == "__main__":
    main()
