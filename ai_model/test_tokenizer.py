import json
from pathlib import Path
from ai_model.tokenizer import SimpleTokenizer

def main():
    path = Path("data/splits/train.jsonl")

    with path.open("r", encoding="utf-8") as file:
        examples = [json.loads(line) for line in file if line.strip()]

    tokenizer = SimpleTokenizer()
    tokenizer.fit([example["text"] for example in examples])

    question = "Show my attendance today"
    token_ids = tokenizer.encode(question)

    print("Vocabulary size:", tokenizer.vocab_size)
    print("Question:", question)
    print("Tokens:", tokenizer.tokenize(question))
    print("Token IDs:", token_ids)
    print("Decoded:", tokenizer.decode(token_ids))
    print("Unknown word test:", tokenizer.encode("xyzunknownword"))

    assert token_ids
    assert tokenizer.decode(token_ids) == "show my attendance today"
    assert tokenizer.encode("xyzunknownword") == [1]

    print("Tokenizer tests passed.")

if __name__ == "__main__":
    main()
