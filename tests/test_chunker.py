from __future__ import annotations

from audit_v2.extraction.chunker import TextChunk, chunk_text


class TestChunker:
    def test_chunk_empty_text(self):
        assert chunk_text("", "doc1") == []

    def test_chunk_short_text(self):
        chunks = chunk_text("Short text.", "doc1")
        assert len(chunks) == 0

    def test_chunk_single_paragraph(self):
        text = (
            "This is a sufficiently long paragraph that should be returned as a "
            "single chunk because it is longer than twenty characters."
        )
        chunks = chunk_text(text, "doc1")
        assert len(chunks) == 1
        assert chunks[0].text == text

    def test_chunk_multiple_paragraphs(self):
        text = (
            "Paragraph one has enough text to be a chunk."
            "\n\nParagraph two also qualifies for chunking."
        )
        chunks = chunk_text(text, "doc1")
        assert len(chunks) == 2

    def test_chunk_tracks_source_and_page(self):
        chunks = chunk_text(
            "This is a sufficiently long paragraph for testing purposes.", "doc_001", page=3,
        )
        assert chunks[0].source == "doc_001"
        assert chunks[0].page == 3
        assert chunks[0].chunk_id.startswith("chk_doc_001_3_")

    def test_chunk_long_paragraph_split_by_sentences(self):
        text = "First sentence here. " * 30
        chunks = chunk_text(text, "doc1")
        assert len(chunks) > 1
        for c in chunks:
            assert len(c.text) <= 520

    def test_text_chunk_dataclass(self):
        chunk = TextChunk(
            chunk_id="chk_1", source="doc1", page=2,
            bbox=[1.0, 2.0, 3.0, 4.0], text="test",
        )
        assert chunk.chunk_id == "chk_1"
        assert chunk.page == 2
        assert chunk.embedding is None


class TestEmbedding:
    def test_stub_embedding_returns_384_dims(self):
        from audit_v2.gateway.embedding import StubEmbeddingGateway
        gw = StubEmbeddingGateway()
        emb = gw.generate("test")
        assert len(emb) == 384
        assert all(v == 0.0 for v in emb)


class TestVectorStore:
    def test_memory_vector_store_insert_and_search(self):
        from audit_v2.persistence.vector_store import MemoryVectorStore
        store = MemoryVectorStore()
        chunk = TextChunk(chunk_id="chk_1", source="doc1", page=1, bbox=None, text="test")
        store.insert(chunk)
        results = store.search([0.0] * 384, "tenant1")
        assert len(results) == 1

    def test_vector_store_delete_by_source(self):
        from audit_v2.persistence.vector_store import MemoryVectorStore
        store = MemoryVectorStore()
        store.insert(TextChunk(chunk_id="chk_1", source="doc1", page=1, bbox=None, text="test"))
        store.insert(TextChunk(chunk_id="chk_2", source="doc1", page=2, bbox=None, text="more"))
        store.insert(TextChunk(chunk_id="chk_3", source="doc2", page=1, bbox=None, text="other"))
        store.delete_by_source("doc1")
        results = store.search([0.0] * 384, "tenant1")
        assert len(results) == 1
        assert results[0].source == "doc2"