"""Project-wide constants."""

# Embedding vector dimension. Must match the embedding model in use
# (nomic-embed-text = 768). Changing it requires a database migration, since
# it defines the size of the `chunks.embedding` pgvector column.
EMBEDDING_DIMENSIONS = 768
