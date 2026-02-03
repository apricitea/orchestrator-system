"""
Embeddings Service

Provides text embeddings for semantic search in long-term memory.
"""

from typing import List

from openai import AsyncOpenAI

from config.settings import get_settings
from utils.logger import get_logger


class EmbeddingsService:
    """
    Service for generating text embeddings.

    Supports multiple providers:
    - OpenAI (text-embedding-3-small/large)
    - Can be extended for Cohere, HuggingFace, etc.
    """

    def __init__(self):
        """Initialize embeddings service."""
        self.settings = get_settings()
        self.logger = get_logger("embeddings")

        # Initialize OpenAI client
        api_key = self.settings.openai_api_key
        if api_key:
            self.openai = AsyncOpenAI(api_key=api_key)
        else:
            self.openai = None

        # Default model
        self.model = "text-embedding-3-small"  # Cost-effective
        self.dimension = 1536  # OpenAI small embedding dimension

    async def embed(self, text: str) -> List[float]:
        """
        Generate embeddings for text.

        Args:
            text: Text to embed

        Returns:
            Embedding vector
        """
        if not self.openai:
            self.logger.warning("No OpenAI API key - returning zero vector")
            return [0.0] * self.dimension

        try:
            response = await self.openai.embeddings.create(
                model=self.model,
                input=text,
            )

            embedding = response.data[0].embedding

            self.logger.debug(
                "Generated embedding",
                model=self.model,
                dimension=len(embedding),
            )

            return embedding

        except Exception as e:
            self.logger.error("Embedding generation failed", error=str(e))
            return [0.0] * self.dimension

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        if not self.openai:
            return [[0.0] * self.dimension] * len(texts)

        try:
            response = await self.openai.embeddings.create(
                model=self.model,
                input=texts,
            )

            embeddings = [item.embedding for item in response.data]

            self.logger.debug(
                "Generated batch embeddings",
                count=len(embeddings),
                model=self.model,
            )

            return embeddings

        except Exception as e:
            self.logger.error("Batch embedding generation failed", error=str(e))
            return [[0.0] * self.dimension] * len(texts)

    async def embed_code(
        self,
        code: str,
        language: str = "python",
    ) -> List[float]:
        """
        Generate embeddings for code with language context.

        Args:
            code: Code to embed
            language: Programming language

        Returns:
            Embedding vector
        """
        # Add language context for better embeddings
        text = f"```{language}\n{code}\n```"
        return await self.embed(text)

    def get_dimension(self) -> int:
        """Get embedding dimension."""
        return self.dimension


# Global embeddings service
_embeddings_service: EmbeddingsService = None


def get_embeddings_service() -> EmbeddingsService:
    """Get the global embeddings service."""
    global _embeddings_service
    if _embeddings_service is None:
        _embeddings_service = EmbeddingsService()
    return _embeddings_service
