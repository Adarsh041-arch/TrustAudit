# Multi-Model Document Audit Agent Plan

## Overview
This project is an AI agent system that can reason over hundreds of documents, validate arithmetic, cross-check consistency, and produce auditable findings. The design should combine deterministic validation, metadata-based routing, and multi-model reasoning with full provenance tracking.

## Phase 1: Scope and use cases
Define the initial document families and checks.

### Goals
- Select 3 to 5 document types to support first.
- Define the exact checks for each type.
- Decide what counts as a finding.
- Define when human review is required.
- Set success metrics.

### Deliverables
- Use-case list.
- Check catalog.
- Risk tiers by document type.
- Human-review criteria.
- Success metrics.

## Phase 2: Governance and controls
Set up ownership, permissions, and auditability before building the reasoning layer.

### Goals
- Define agent responsibilities.
- Define permissions and escalation paths.
- Establish audit logging and traceability.
- Separate deterministic actions from model-assisted actions.

### Deliverables
- Agent inventory.
- Role and ownership map.
- Permission matrix.
- Audit log specification.
- Escalation policy.

## Phase 3: Ingestion architecture
Build the ingestion layer that accepts documents and normalizes them for downstream processing.

### Architecture
- Document intake service.
- Parsing/OCR service.
- Normalizer.
- Provenance recorder.
- Document registry.

### Suggested states
- RECEIVED
- QUARANTINED
- PARSED
- NORMALIZED
- FAILED_PARSE
- READY_FOR_CHUNKING

### Suggested schema
```json
{
  "document_id": "DOC-001",
  "source_uri": "s3://bucket/file.pdf",
  "file_hash": "sha256...",
  "doc_type": "invoice",
  "tenant_id": "tenant-a",
  "version": "v3",
  "ingestion_run_id": "run-20260725-001",
  "status": "NORMALIZED",
  "parser_version": "ocr-v2.1",
  "page_count": 18,
  "created_at": "2026-07-25T09:30:00Z"
}
```

### Deliverables
- Ingestion service.
- OCR/text extraction.
- Structural parsing.
- Chunking strategy.
- Metadata schema.

## Phase 4: Chunking and metadata
Create retrieval-ready chunks with rich metadata and provenance.

### Goals
- Use structure-aware chunking.
- Keep tables, headings, and lists intact where possible.
- Add chunk-level metadata automatically.
- Preserve source spans and evidence links.

### Chunk schema
```json
{
  "chunk_id": "DOC-001-CH-004",
  "document_id": "DOC-001",
  "chunk_index": 4,
  "page_start": 5,
  "page_end": 6,
  "section_path": ["Policy", "Revenue", "Recognition"],
  "chunk_type": "table",
  "text": "...",
  "summary": "Revenue recognition policy for subscription contracts.",
  "keywords": ["revenue", "subscription", "recognition"],
  "entities": ["IFRS 15", "contract asset"],
  "source_spans": [
    {"page": 5, "start": 120, "end": 540}
  ],
  "confidence": 0.94
}
```

### Chunk states
- CHUNKED
- METADATA_EXTRACTED
- METADATA_VALIDATED
- INDEXED
- REJECTED

### Deliverables
- Metadata extractor.
- Schema validator.
- Provenance store.
- Confidence scoring.
- Controlled vocabulary map.

## Phase 5: Routing and filtering
Route documents to the relevant checks instead of sending everything through every agent.

### Goals
- Classify each document or chunk by metadata.
- Apply only relevant validation checks.
- Minimize unnecessary cost and latency.
- Escalate uncertain cases.

### Routing states
- ROUTE_PENDING
- ROUTE_MATCHED
- ROUTE_PARTIAL
- ROUTE_ESCALATED
- ROUTE_SKIPPED

### Example routing rules
- invoice -> arithmetic + duplicate + approval.
- contract -> version + clause consistency + obligation extraction.
- policy -> compliance + version + contradiction.
- financial_report -> arithmetic + roll-forward + tie-out.
- low-risk memo -> indexing only.

### Routing schema
```json
{
  "chunk_id": "DOC-001-CH-004",
  "document_type": "invoice",
  "risk_level": "high",
  "applicable_checks": ["arithmetic", "duplicate", "approval"],
  "routing_reason": "invoice with amount fields and approval metadata",
  "status": "ROUTE_MATCHED"
}
```

### Deliverables
- Metadata classifier.
- Routing rules.
- Check assignment logic.
- Relevance thresholds.
- Fallback routing for uncertain cases.

## Phase 6: Validation engine
Implement deterministic validation logic in code.

### Goals
- Use explicit validators for arithmetic and consistency.
- Keep rules versioned.
- Produce structured exception outputs.
- Avoid relying on the LLM for math.

### Validator states
- PENDING
- PASS
- FAIL
- WARN
- NEEDS_REVIEW
- NOT_APPLICABLE

### Validation result schema
```json
{
  "check_id": "CHK-ARITH-001",
  "chunk_id": "DOC-001-CH-004",
  "check_type": "subtotal_tieout",
  "expected": 125000,
  "actual": 124800,
  "delta": -200,
  "tolerance": 0,
  "severity": "high",
  "status": "FAIL",
  "evidence": [
    {"doc_id": "DOC-001", "page": 6, "span": },
    {"doc_id": "DOC-002", "page": 2, "span": }
  ]
}
```

### Validation categories
- Arithmetic.
- Roll-forward.
- Tie-out.
- Duplicate detection.
- Sequence check.
- Threshold check.
- Reasonableness check.
- Cross-document consistency.

### Deliverables
- Arithmetic validator.
- Cross-document tie-out engine.
- Duplicate detector.
- Rule engine.
- Exception classifier.

## Phase 7: Agent state machine
Use a stateful orchestrator with specialist workers.

### Top-level states
- INTAKE
- EXTRACT
- CHUNK
- ENRICH
- ROUTE
- VALIDATE
- COMPARE
- ADJUDICATE
- REPORT
- HUMAN_REVIEW
- ARCHIVE
- FAILED

### State transitions
- INTAKE -> EXTRACT
- EXTRACT -> CHUNK
- CHUNK -> ENRICH
- ENRICH -> ROUTE
- ROUTE -> VALIDATE
- VALIDATE -> COMPARE
- COMPARE -> ADJUDICATE
- ADJUDICATE -> REPORT
- ADJUDICATE -> HUMAN_REVIEW when confidence is low or conflicts exist
- FAILED from any stage

### State object
```json
{
  "run_id": "run-001",
  "document_id": "DOC-001",
  "chunk_id": "DOC-001-CH-004",
  "current_state": "VALIDATE",
  "next_state": "COMPARE",
  "artifacts": {
    "parsed_text_ref": "...",
    "metadata_ref": "...",
    "validation_ref": "..."
  },
  "flags": {
    "low_confidence": false,
    "conflict_detected": true
  }
}
```

## Phase 8: Evidence and provenance graph
Build a traceable evidence graph from final conclusions back to source files.

### Graph nodes
- document
- chunk
- entity
- rule
- check
- exception
- decision
- reviewer

### Graph edges
- document -> chunk
- chunk -> entity
- chunk -> check
- check -> exception
- exception -> decision
- decision -> reviewer

### Deliverables
- Evidence graph.
- Immutable logs.
- Explanation format.
- Decision history.
- Reviewer-facing report template.

## Phase 9: Agent composition
Keep the agent set coarse-grained.

### Suggested agents
- Parser agent.
- Metadata agent.
- Routing agent.
- Validation agent.
- Consistency agent.
- Adjudicator agent.

### Design rule
Merge checks that share the same evidence and output format. Separate checks only when they need different tools or governance.

## Phase 10: Practical implementation choice
Use a layered architecture.

### Recommended components
- Workflow engine for states.
- Rule engine for deterministic checks.
- Vector database for retrieval.
- Graph database for provenance.
- LLMs for extraction, classification, and explanations.
- Human review UI for exceptions.

## Build order
1. Scope and governance.
2. Ingestion and metadata.
3. Routing and deterministic checks.
4. Multi-model reasoning.
5. Audit trail and human review.
6. Testing and pilot.
7. Scale-up.

## Next steps
- Convert this plan into a Mermaid architecture diagram.
- Convert the schemas into JSON Schema files.
- Turn the phases into a 90-day execution roadmap.