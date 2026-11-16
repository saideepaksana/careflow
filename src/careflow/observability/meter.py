from collections.abc import Sequence

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

CHAT_PREFIX = "chat "


class UsageMeter(SpanExporter):
    """Collects model-call spans so an evaluation can meter usage per step."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        for item in spans:
            if item.name.startswith(CHAT_PREFIX):
                self.calls.append(chat_usage(item))
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        self.calls.clear()

    def take(self) -> list[dict]:
        taken, self.calls = self.calls, []
        return taken


def chat_usage(item: ReadableSpan) -> dict:
    attributes = item.attributes or {}
    return {
        "model": attributes.get("gen_ai.request.model", ""),
        "input_tokens": attributes.get("gen_ai.usage.input_tokens", 0),
        "output_tokens": attributes.get("gen_ai.usage.output_tokens", 0),
        "cost_usd": attributes.get("careflow.cost_usd", 0.0),
    }
