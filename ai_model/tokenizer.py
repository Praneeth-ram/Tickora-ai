import re
from collections import Counter

class SimpleTokenizer:
    PAD = "<PAD>"
    UNK = "<UNK>"

    def __init__(self):
        self.token_to_id = {
            self.PAD: 0,
            self.UNK: 1,
        }
        self.id_to_token = {
            0: self.PAD,
            1: self.UNK,
        }

    @staticmethod
    def tokenize(text: str) -> list[str]:
        return re.findall(r"\w+|[^\w\s]", text.lower())

    def fit(self, texts: list[str]) -> None:
        counts = Counter(
            token
            for text in texts
            for token in self.tokenize(text)
        )

        # Stable ordering makes vocabulary IDs reproducible.
        for token, _ in sorted(counts.items()):
            if token not in self.token_to_id:
                token_id = len(self.token_to_id)
                self.token_to_id[token] = token_id
                self.id_to_token[token_id] = token

    def encode(self, text: str) -> list[int]:
        return [
            self.token_to_id.get(token, self.token_to_id[self.UNK])
            for token in self.tokenize(text)
        ]

    def decode(self, token_ids: list[int]) -> str:
        tokens = [
            self.id_to_token.get(token_id, self.UNK)
            for token_id in token_ids
            if token_id != self.token_to_id[self.PAD]
        ]
        return " ".join(tokens)

    @property
    def vocab_size(self) -> int:
        return len(self.token_to_id)
