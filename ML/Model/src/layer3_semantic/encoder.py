"""Layer 3 [3a] — Sentence-Transformer encoder.

Implements V1_Engineering_Spec §4.3 [3a].

The default encoder is ``BAAI/bge-small-en-v1.5``. Encoder choice is
swappable via ``config/encoder.yaml`` (spec §6.2) — downstream layers
hold no compile-time dependency on the embedding dimension.

The model is loaded lazily so unit tests that don't actually need
embeddings don't pay the ~130 MB model-download cost.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np

from ..config import EncoderConfig


class Encoder:
    """Thin wrapper around sentence-transformers.

    Produces float32 vectors in ``EncoderConfig.dimension`` dimensions.
    When ``EncoderConfig.normalize == "l2"`` the output rows are unit-norm,
    so inner-product on the output equals cosine similarity — this is what
    the FAISS index requires (spec §4.3 [3b]).
    """

    def __init__(self, config: EncoderConfig) -> None:
        self._config = config
        self._model: object | None = None    # lazy

    @property
    def dimension(self) -> int:
        return self._config.dimension

    @property
    def model_id(self) -> str:
        return self._config.model_id

    def _get_model(self) -> object:
        """Load the sentence-transformer on first use."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(
                self._config.model_id,
                device=self._config.device,
            )
            # Verify dimensionality early — a config mismatch with the
            # actual model would silently break FAISS downstream.
            get_dim = getattr(
                self._model,
                "get_embedding_dimension",                                # sentence-transformers ≥ 5
                getattr(self._model, "get_sentence_embedding_dimension"), # earlier versions
            )
            actual_dim = get_dim()
            if actual_dim != self._config.dimension:
                raise ValueError(
                    f"encoder.yaml declares dimension={self._config.dimension} but "
                    f"model {self._config.model_id!r} actually produces {actual_dim}-d "
                    "vectors. Update encoder.yaml."
                )
        return self._model

    def encode(
        self,
        texts: Sequence[str],
        batch_size: int | None = None,
        show_progress: bool = False,
    ) -> np.ndarray:
        """Encode a list of strings into a ``(N, dimension)`` float32 array.

        Args:
            texts: Sequence of strings. Empty strings are allowed and
                produce non-zero embeddings (the model has its own
                handling of empty input).
            batch_size: Override the configured batch size for this call.
            show_progress: Pass through to sentence-transformers — useful
                for the 198K-row M3a index build, off by default.

        Returns:
            ``np.ndarray`` of shape ``(len(texts), dimension)``, dtype
            float32. L2-normalized when ``config.normalize == "l2"``.
        """
        model = self._get_model()
        normalize = self._config.normalize == "l2"
        bs = batch_size if batch_size is not None else self._config.batch_size
        vectors = model.encode(                                    # type: ignore[attr-defined]
            list(texts),
            batch_size=bs,
            show_progress_bar=show_progress,
            convert_to_numpy=True,
            normalize_embeddings=normalize,
        )
        return np.asarray(vectors, dtype=np.float32)

    def encode_one(self, text: str) -> np.ndarray:
        """Convenience: encode a single string and return a 1-D vector."""
        return self.encode([text])[0]
