"""
PaperSignal — Clustering Pipeline
UMAP dimensionality reduction → HDBSCAN clustering → theme label generation.
Writes cluster_id and cluster_theme back to each Paper row.
All hyperparams from settings.
"""

import logging
from collections import Counter
from typing import List, Dict, Tuple

import numpy as np
import umap
from fast_hdbscan import HDBSCAN
from sqlalchemy import select

from ingestion.models import Paper, ClusterRun, get_db
from ml.embeddings import get_chroma_collection
from config.settings import settings

logger = logging.getLogger(__name__)


def _get_all_embeddings() -> Tuple[List[str], np.ndarray]:
    """
    Pull all embeddings from ChromaDB.
    Returns (list_of_paper_ids, numpy_array_of_embeddings).
    """
    collection = get_chroma_collection()
    total = collection.count()
    if total == 0:
        return [], np.array([])

    result = collection.get(include=["embeddings"], limit=total)
    ids = result["ids"]
    embeddings = np.array(result["embeddings"])
    return ids, embeddings


def _reduce_dimensions(embeddings: np.ndarray) -> np.ndarray:
    """UMAP: reduce high-dim embeddings before HDBSCAN."""
    n_neighbors = min(settings.UMAP_N_NEIGHBORS, len(embeddings) - 1)
    reducer = umap.UMAP(
        n_components=settings.UMAP_N_COMPONENTS,
        n_neighbors=n_neighbors,
        metric="cosine",
        random_state=42,
        verbose=False,
    )
    return reducer.fit_transform(embeddings)


def _cluster(reduced: np.ndarray) -> np.ndarray:
    """HDBSCAN clustering. Returns array of cluster labels (-1 = noise)."""
    clusterer = HDBSCAN(
        min_cluster_size=settings.HDBSCAN_MIN_CLUSTER_SIZE,
        min_samples=settings.HDBSCAN_MIN_SAMPLES,
        metric="euclidean",
        cluster_selection_method="eom",
    )
    return clusterer.fit_predict(reduced)


def _generate_theme_labels(
    paper_ids: List[str],
    labels: np.ndarray,
    papers_by_id: Dict[str, Paper],
) -> Dict[int, str]:
    """
    For each cluster, extract the top TF-IDF-style keywords from titles.
    Returns {cluster_id: theme_label} mapping.
    Noise cluster (-1) always maps to 'Unclustered'.
    """
    from sklearn.feature_extraction.text import TfidfVectorizer

    cluster_texts: Dict[int, List[str]] = {}
    for paper_id, label in zip(paper_ids, labels):
        label = int(label)
        if label == -1:
            continue
        paper = papers_by_id.get(paper_id)
        if paper:
            cluster_texts.setdefault(label, []).append(paper.title)

    theme_labels: Dict[int, str] = {-1: "Unclustered"}

    if not cluster_texts:
        return theme_labels

    vectorizer = TfidfVectorizer(
        stop_words="english",
        max_features=500,
        ngram_range=(1, 2),
    )

    all_cluster_ids = list(cluster_texts.keys())
    corpus = [" ".join(cluster_texts[cid]) for cid in all_cluster_ids]

    try:
        tfidf_matrix = vectorizer.fit_transform(corpus)
        feature_names = vectorizer.get_feature_names_out()

        for i, cid in enumerate(all_cluster_ids):
            row = tfidf_matrix[i].toarray().flatten()
            top_indices = row.argsort()[-4:][::-1]   # top 4 terms
            top_terms = [feature_names[j].title() for j in top_indices if row[j] > 0]
            theme_labels[cid] = " · ".join(top_terms) if top_terms else f"Cluster {cid}"

    except ValueError:
        # Fallback if corpus is too small for TF-IDF
        for cid in all_cluster_ids:
            theme_labels[cid] = f"Theme {cid}"

    return theme_labels


async def run_clustering() -> ClusterRun:
    """
    Main clustering entrypoint.
    1. Pull embeddings from ChromaDB
    2. UMAP reduce → HDBSCAN cluster
    3. Generate theme labels from TF-IDF on titles
    4. Write cluster_id + cluster_theme back to Paper rows
    Returns ClusterRun audit record.
    """
    async with get_db() as db:
        run = ClusterRun()
        db.add(run)
        await db.flush()

        try:
            paper_ids, embeddings = _get_all_embeddings()

            if len(paper_ids) < settings.HDBSCAN_MIN_CLUSTER_SIZE * 2:
                logger.warning(f"[Clustering] Not enough papers ({len(paper_ids)}) to cluster meaningfully")
                run.papers_clustered = len(paper_ids)
                run.clusters_found = 0
                run.noise_papers = len(paper_ids)
                return run

            logger.info(f"[Clustering] Running UMAP on {len(paper_ids)} embeddings...")
            reduced = _reduce_dimensions(embeddings)

            logger.info("[Clustering] Running HDBSCAN...")
            labels = _cluster(reduced)

            # Fetch all paper objects for theme generation
            result = await db.execute(select(Paper).where(Paper.id.in_(paper_ids)))
            papers_by_id: Dict[str, Paper] = {p.id: p for p in result.scalars().all()}

            theme_labels = _generate_theme_labels(paper_ids, labels, papers_by_id)

            # Write back to DB
            cluster_counts = Counter(int(l) for l in labels)
            for paper_id, label in zip(paper_ids, labels):
                label = int(label)
                paper = papers_by_id.get(paper_id)
                if paper:
                    paper.cluster_id = label
                    paper.cluster_theme = theme_labels.get(label, f"Cluster {label}")

            n_clusters = len(set(int(l) for l in labels if l != -1))
            n_noise = int(cluster_counts.get(-1, 0))

            run.papers_clustered = len(paper_ids)
            run.clusters_found = n_clusters
            run.noise_papers = n_noise

            logger.info(
                f"[Clustering] Done — {n_clusters} clusters found, "
                f"{n_noise} noise papers out of {len(paper_ids)}"
            )
            for cid, theme in sorted(theme_labels.items()):
                if cid != -1:
                    count = cluster_counts.get(cid, 0)
                    logger.info(f"  Cluster {cid:3d} ({count:3d} papers): {theme}")

        except Exception as e:
            run.noise_papers = 0
            logger.error(f"[Clustering] Failed: {e}", exc_info=True)
            raise

        return run