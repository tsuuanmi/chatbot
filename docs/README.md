# Chatbot BCA Documentation

## System and operation

- [`architecture.md`](architecture.md): deployment boundaries, answer cascade, data flow, and security model.
- [`api.md`](api.md): HTTP, authentication, response, error, and SSE contracts.
- [`offline.md`](offline.md): preparation, transfer, installation, LAN clients, operations, backup, and troubleshooting.
- [`source-layout.md`](source-layout.md): implemented Python package ownership and documentation mirror rule.

## Source manuals

[`src/`](src/) mirrors every Python file under the repository's `src/` directory.
`src/x.py` maps to `docs/src/x.md`, including `__init__.py` to `__init__.md`.
The isolated test suite rejects missing and orphaned source manuals.

## Review and content governance

- [`review/CONTENT_APPROVAL_WORKFLOW.md`](review/CONTENT_APPROVAL_WORKFLOW.md): approval and indexing procedure.
- [`review/SOURCE_MANIFEST_EXAMPLE.json`](review/SOURCE_MANIFEST_EXAMPLE.json): reviewed PDF source-manifest example.
- [`review/DOMAIN_BEHAVIOR_REVIEW.md`](review/DOMAIN_BEHAVIOR_REVIEW.md): domain-decision review record.
- [`review/KNOWLEDGE_RAG_REVIEW.md`](review/KNOWLEDGE_RAG_REVIEW.md): evidence and retrieval review record.
- [`review/PERFORMANCE_REVIEW.md`](review/PERFORMANCE_REVIEW.md): performance review record.
