import math
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from langchain_core.documents import Document


TOKEN_PATTERN = re.compile(
    r"[a-zA-Z]+(?:-[a-zA-Z0-9]+)+"
    r"|[a-zA-Z0-9]+"
    r"|[\u4e00-\u9fff]+"
)


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []

    for match in TOKEN_PATTERN.findall(text.lower()):
        if re.fullmatch(r"[\u4e00-\u9fff]+", match):
            if len(match) == 1:
                tokens.append(match)
            else:
                tokens.extend(
                    match[index:index + 2]
                    for index in range(len(match) - 1)
                )
        else:
            tokens.append(match)

    return tokens


@dataclass(frozen=True)
class BM25Result:
    document: Document
    score: float


def search_bm25(
    query: str,
    documents: Sequence[Document],
    *,
    top_k: int,
    k1: float = 1.5,
    b: float = 0.75,
) -> list[BM25Result]:
    if not documents or top_k <= 0:
        return []

    query_tokens = set(tokenize(query))

    if not query_tokens:
        return []

    corpus_tokens = [
        tokenize(document.page_content)
        for document in documents
    ]
    document_count = len(documents)
    average_length = (
        sum(len(tokens) for tokens in corpus_tokens)
        / document_count
    ) or 1.0
    document_frequency: Counter[str] = Counter()

    for tokens in corpus_tokens:
        document_frequency.update(set(tokens))

    results: list[BM25Result] = []

    for document, tokens in zip(
        documents,
        corpus_tokens,
        strict=True,
    ):
        frequencies = Counter(tokens)
        document_length = len(tokens)
        score = 0.0

        for token in query_tokens:
            frequency = frequencies.get(token, 0)

            if frequency == 0:
                continue

            frequency_in_documents = (
                document_frequency[token]
            )
            inverse_document_frequency = math.log(
                1
                + (
                    document_count
                    - frequency_in_documents
                    + 0.5
                )
                / (frequency_in_documents + 0.5)
            )
            denominator = frequency + k1 * (
                1
                - b
                + b
                * document_length
                / average_length
            )
            score += (
                inverse_document_frequency
                * frequency
                * (k1 + 1)
                / denominator
            )

        if score > 0:
            results.append(
                BM25Result(
                    document=document,
                    score=score,
                )
            )

    results.sort(
        key=lambda result: result.score,
        reverse=True,
    )
    return results[:top_k]
