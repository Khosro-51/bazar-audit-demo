from dataclasses import dataclass, field
from enum import Enum


class Severity(Enum):
    LOW    = "LOW"
    MEDIUM = "MEDIUM"
    HIGH   = "HIGH"


class Confidence(Enum):
    LOW    = "LOW"
    MEDIUM = "MEDIUM"
    HIGH   = "HIGH"


@dataclass
class Insight:
    insight_id: str
    severity: Severity
    confidence: Confidence
    sample_size: int
    metric_snapshot: dict
    message: str
    recommended_action: str
    title_fa: str
    body_fa: str

    def to_dict(self):
        return {
            "insight_id":         self.insight_id,
            "severity":           self.severity.value,
            "confidence":         self.confidence.value,
            "sample_size":        self.sample_size,
            "metric_snapshot":    self.metric_snapshot,
            "message":            self.message,
            "recommended_action": self.recommended_action,
            "title_fa":           self.title_fa,
            "body_fa":            self.body_fa,
        }


@dataclass
class AuditReport:
    trader_id: str
    total_trades: int
    sample_size_ok: bool
    r_mode: str
    core_metrics: dict = field(default_factory=dict)
    insights: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    def to_dict(self):
        return {
            "trader_id":      self.trader_id,
            "total_trades":   self.total_trades,
            "sample_size_ok": self.sample_size_ok,
            "r_mode":         self.r_mode,
            "core_metrics":   self.core_metrics,
            "insights":       [i.to_dict() for i in self.insights],
            "warnings":       self.warnings,
        }
