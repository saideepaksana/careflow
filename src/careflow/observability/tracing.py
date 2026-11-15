from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor, SpanExporter
from opentelemetry.trace import Span, Status, StatusCode

from careflow.config import SERVICE_NAME
from careflow.observability.budget import RequestBudget, request_budget

TRACES_PATH = "/v1/traces"
RESOURCE = Resource.create(
    {"service.name": SERVICE_NAME, "openinference.project.name": SERVICE_NAME}
)
tracer = trace.get_tracer(SERVICE_NAME)


def provider() -> TracerProvider:
    current = trace.get_tracer_provider()
    if isinstance(current, TracerProvider):
        return current
    installed = TracerProvider(resource=RESOURCE)
    trace.set_tracer_provider(installed)
    return installed


def setup_tracing(endpoint: str = "", exporter: SpanExporter | None = None) -> None:
    """Install the tracer provider once; each call may add an exporter."""
    installed = provider()
    if exporter is not None:
        installed.add_span_processor(SimpleSpanProcessor(exporter))
    if endpoint:
        otlp = OTLPSpanExporter(endpoint=endpoint.rstrip("/") + TRACES_PATH)
        installed.add_span_processor(BatchSpanProcessor(otlp))


@contextmanager
def span(
    name: str, ignore: tuple[type[BaseException], ...] = (), **attributes: object
) -> Iterator[Span]:
    """A span that records only the error type, never exception text."""
    with tracer.start_as_current_span(
        name, attributes=attributes, record_exception=False, set_status_on_exception=False
    ) as current:
        try:
            yield current
        except ignore:
            raise
        except BaseException as error:  # re-raised; only the type is recorded
            current.set_attribute("error.type", type(error).__name__)
            current.set_status(Status(StatusCode.ERROR))
            raise


def current_trace_id() -> str | None:
    context = trace.get_current_span().get_span_context()
    return format(context.trace_id, "032x") if context.is_valid else None


@contextmanager
def traced_request(
    name: str, ignore: tuple[type[BaseException], ...] = (), **attributes: object
) -> Iterator[tuple[Span, RequestBudget]]:
    """One span plus one budget for a request; nested requests join the outer budget."""
    with span(name, ignore, **attributes) as current, request_budget() as budget:
        yield current, budget
