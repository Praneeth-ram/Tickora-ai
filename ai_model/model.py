import torch
import torch.nn as nn

class TickoraTransformer(nn.Module):
    def __init__(
        self,
        vocab_size: int,
        num_classes: int = 7,
        max_length: int = 64,
        d_model: int = 128,
        n_heads: int = 4,
        n_layers: int = 2,
        dropout: float = 0.1,
    ):
        super().__init__()

        if d_model % n_heads != 0:
            raise ValueError("d_model must be divisible by n_heads")

        self.token_embedding = nn.Embedding(vocab_size, d_model, padding_idx=0)
        self.position_embedding = nn.Embedding(max_length, d_model)

        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=n_heads,
            dim_feedforward=d_model * 4,
            dropout=dropout,
            batch_first=True,
            norm_first=False,
        )

        self.encoder = nn.TransformerEncoder(
            encoder_layer,
            num_layers=n_layers,
        )

        self.classifier = nn.Sequential(
            nn.LayerNorm(d_model),
            nn.Linear(d_model, num_classes),
        )

        self.max_length = max_length

    def forward(self, input_ids: torch.Tensor) -> torch.Tensor:
        # input_ids shape: (batch_size, sequence_length)
        batch_size, sequence_length = input_ids.shape

        if sequence_length > self.max_length:
            raise ValueError(
                f"Sequence length {sequence_length} exceeds "
                f"max_length {self.max_length}"
            )

        positions = torch.arange(
            sequence_length, device=input_ids.device
        ).unsqueeze(0).expand(batch_size, -1)

        x = (
            self.token_embedding(input_ids)
            + self.position_embedding(positions)
        )

        padding_mask = input_ids.eq(0)

        x = self.encoder(
            x,
            src_key_padding_mask=padding_mask,
        )

        # Average non-padding token representations.
        valid_tokens = (~padding_mask).unsqueeze(-1)
        x = x * valid_tokens
        token_counts = valid_tokens.sum(dim=1).clamp(min=1)
        pooled = x.sum(dim=1) / token_counts

        return self.classifier(pooled)
