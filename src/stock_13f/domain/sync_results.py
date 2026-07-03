"""Result dataclasses for backend sync services."""

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class SyncResult:
    job_name: str
    status: str
    started_at: datetime
    finished_at: datetime
    rows_written: int = 0
    checkpoints_updated: int = 0
    warnings: list[str] = field(default_factory=list)
    error_summary: str = ""
    details: dict[str, object] = field(default_factory=dict)

    @classmethod
    def success(
        cls,
        job_name: str,
        started_at: datetime,
        rows_written: int = 0,
        checkpoints_updated: int = 0,
        warnings: list[str] | None = None,
        details: dict[str, object] | None = None,
    ) -> "SyncResult":
        return cls(
            job_name=job_name,
            status="success",
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            rows_written=rows_written,
            checkpoints_updated=checkpoints_updated,
            warnings=warnings or [],
            details=details or {},
        )

    @classmethod
    def failed(
        cls,
        job_name: str,
        started_at: datetime,
        error_summary: str,
        warnings: list[str] | None = None,
        details: dict[str, object] | None = None,
    ) -> "SyncResult":
        return cls(
            job_name=job_name,
            status="failed",
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            warnings=warnings or [],
            error_summary=error_summary,
            details=details or {},
        )
