import asyncio
import logging
from collections.abc import AsyncGenerator

import numpy as np
from openai import AsyncOpenAI

from model import Document

logger = logging.getLogger(__name__)


class EmbeddingClient:
    MODEL_NAME = "text-embedding-3-small"

    def __init__(
        self, client: AsyncOpenAI | None = None, model_name: str | None = None
    ):
        self.client = client if client else AsyncOpenAI()
        self.model_name = model_name if model_name else EmbeddingClient.MODEL_NAME

    async def get_embedding(
        self, text: str, model: str | None = None
    ) -> list[float] | None:
        """Generates an embedding for the given text using the specified OpenAI model."""
        model_to_use = model if model else self.model_name
        text = text.replace("\n", " ")
        response = await self.client.embeddings.create(input=[text], model=model_to_use)
        return response.data[0].embedding

    async def embed_documents(
        self, documents: list[Document], model: str | None = None
    ) -> AsyncGenerator[Document]:
        """
        Embeds the text of each segment in a list of Document objects.
        Updates the 'embedding' field of each DocumentSegment.
        Only embeds segments that do not already have an embedding.
        Yields each document after its segments have been processed.
        """
        model_to_use = model if model else self.model_name
        if not self.client:
            logger.error("OpenAI client not initialized. Cannot embed documents.")
            # Yield documents as they are if client not initialized
            for doc in documents:
                yield doc
            return

        for doc in documents:  # Iterate through documents one by one
            segments_to_embed = []
            for segment in doc.segments:
                # Check if embedding is None or an empty array
                if segment.text and (
                    segment.embedding is None or segment.embedding.size == 0
                ):
                    segments_to_embed.append(segment)

            if not segments_to_embed:
                yield doc  # Yield doc if no segments to embed
                continue

            # Process segments_to_embed in batches for the current document
            batch_size = 10  # OpenAI API batch limit or your preference
            for i in range(0, len(segments_to_embed), batch_size):
                batch_segments = segments_to_embed[i : i + batch_size]
                tasks = [
                    self.get_embedding(segment.text, model=model_to_use)
                    for segment in batch_segments
                ]
                embedding_vectors = await asyncio.gather(*tasks)
                for segment, embedding_vector in zip(
                    batch_segments, embedding_vectors, strict=False
                ):
                    if embedding_vector is not None:
                        segment.embedding = np.array(embedding_vector)
            yield doc  # Yield the processed document
