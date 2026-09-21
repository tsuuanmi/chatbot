# Migration Rules

The previous `chatbot` repository is a reference implementation only. This repository has one canonical architecture and does not preserve legacy compatibility unless a current requirement explicitly needs it.

## Rules

1. Do not bulk-copy the previous repository.

2. Migrate only behavior that is required by the current product.

3. Prefer a small rewrite over importing obsolete infrastructure.

4. Every migrated domain or safety rule requires regression coverage.

5. CPU execution must remain functional regardless of GPU availability.

6. Application behavior must remain identical between CPU and GPU paths.

7. Host-specific integration belongs in installation/host tooling, not application logic.

8. Do not disable SELinux to make a future RHEL deployment work.

9. Versioned runtime directories are disposable. Persistent deployment data belongs under `~/.local/share/chatbot/` or the PostgreSQL Docker volume, not inside the release directory.

10. Runtime ZIPs must never contain private secrets or persistent database data.

11. Model packages have an independent lifecycle from application runtime releases.

12. Public API design is canonical and production-oriented; do not add legacy adapters solely to preserve obsolete endpoint behavior.
