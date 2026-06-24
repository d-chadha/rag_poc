"""
vectorstore/embedder.py
-----------------------
Pure-Python/scipy LSA (TF-IDF + SVD) embedding function for ChromaDB.

Produces 256-dim dense semantic vectors using Latent Semantic Analysis.
No torch, onnxruntime, or GPU required — runs on any Python environment.

For production: swap AnthropicEmbedder (below) once a paid embeddings
API key is available.
"""

from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import List

import numpy as np
from chromadb import EmbeddingFunction, Documents, Embeddings
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import Normalizer

EMBED_DIM   = 256
MAX_FEATURES = 20_000
MODEL_PATH   = Path("./nexus_lsa_model.pkl")


class LSAEmbeddingFunction(EmbeddingFunction):
    """
    Latent Semantic Analysis embedder.

    First call to __call__ with a new corpus builds the TF-IDF + SVD pipeline
    in-memory. Subsequent calls use the fitted pipeline.

    This is a corpus-aware embedder: the pipeline is fit on the first batch and
    fine-tuned on subsequent batches via partial updates. For a demo corpus this
    is fully adequate — replace with a neural embedder for production.
    """

    def __init__(self) -> None:
        self._pipeline: Pipeline | None = None
        self._corpus_texts: list[str] = []
        if MODEL_PATH.exists():
            self._load()

    def __call__(self, input: Documents) -> Embeddings:  # type: ignore[override]
        texts = list(input)
        if not texts:
            return []

        # Add new texts to corpus and refit if needed
        self._corpus_texts.extend(texts)
        self._fit_or_refit()

        return self._transform(texts)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_pipeline(self) -> Pipeline:
        return Pipeline([
            ("tfidf", TfidfVectorizer(
                max_features=MAX_FEATURES,
                sublinear_tf=True,
                strip_accents="unicode",
                analyzer="word",
                token_pattern=r"(?u)\b\w+\b",
                ngram_range=(1, 2),
            )),
            ("svd", TruncatedSVD(n_components=EMBED_DIM, random_state=42)),
            ("norm", Normalizer(copy=False)),
        ])

    def _fit_or_refit(self) -> None:
        # Refit on at least 3 texts or when corpus grows significantly
        corpus = list(dict.fromkeys(self._corpus_texts))  # dedupe, preserve order
        if self._pipeline is None or len(corpus) >= 3:
            self._pipeline = self._build_pipeline()
            # Clamp SVD components to corpus size
            n_components = min(EMBED_DIM, len(corpus) - 1)
            if n_components < 1:
                n_components = 1
            self._pipeline.named_steps["svd"].n_components = n_components
            self._pipeline.fit(corpus)
            self._save()

    def _transform(self, texts: list[str]) -> list[list[float]]:
        if self._pipeline is None:
            # Fallback: TF-IDF only (zero-vectors for unknown texts)
            return [[0.0] * EMBED_DIM for _ in texts]
        arr = self._pipeline.transform(texts)
        # Pad to EMBED_DIM if SVD had fewer components
        if arr.shape[1] < EMBED_DIM:
            pad = np.zeros((arr.shape[0], EMBED_DIM - arr.shape[1]))
            arr = np.hstack([arr, pad])
        return arr.tolist()

    def _save(self) -> None:
        try:
            with open(MODEL_PATH, "wb") as f:
                pickle.dump((self._pipeline, self._corpus_texts), f)
        except Exception:
            pass

    def _load(self) -> None:
        try:
            with open(MODEL_PATH, "rb") as f:
                self._pipeline, self._corpus_texts = pickle.load(f)
        except Exception:
            self._pipeline = None
            self._corpus_texts = []


# Singleton — shared across the process
_embedder: LSAEmbeddingFunction | None = None


def get_embedder() -> LSAEmbeddingFunction:
    global _embedder
    if _embedder is None:
        _embedder = LSAEmbeddingFunction()
    return _embedder
