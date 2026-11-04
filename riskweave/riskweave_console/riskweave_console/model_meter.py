"""Metadata-only SDK call accounting; no prompts, responses or keys are stored."""
from contextlib import contextmanager
import json
import time
from types import SimpleNamespace


def field(value, name, default=None):
    return value.get(name, default) if isinstance(value, dict) else getattr(value, name, default)


def token_usage(response, provider):
    usage = field(response, 'usage_metadata' if provider == 'gemini' else 'usage')
    if provider == 'ollama':
        return {'input_tokens': field(response, 'prompt_eval_count'),
                'output_tokens': field(response, 'eval_count'), 'total_tokens': None}
    if usage is None:
        return {'input_tokens': None, 'output_tokens': None, 'total_tokens': None}
    return {
        'input_tokens': field(usage, 'input_tokens', field(usage, 'prompt_tokens', field(usage, 'prompt_token_count'))),
        'output_tokens': field(usage, 'output_tokens', field(usage, 'completion_tokens', field(usage, 'candidates_token_count'))),
        'total_tokens': field(usage, 'total_tokens', field(usage, 'total_token_count')),
    }


class ModelMeter:
    def __init__(self, path):
        self.path = path
        self.calls = 0

    @contextmanager
    def call(self, provider, model, messages):
        self.calls += 1
        call = SimpleNamespace(response=None, sdk_invoked=False)
        started = time.perf_counter()
        error_type = None
        try:
            yield call
        except Exception as exc:
            error_type = type(exc).__name__
            raise
        finally:
            response = call.response
            try:
                request_bytes = len(json.dumps(messages, ensure_ascii=False).encode('utf-8'))
            except (TypeError, ValueError):
                request_bytes = None
            record = {
                'kind': 'provider_invocation', 'provider': provider, 'requested_model': model,
                'returned_model': field(response, 'model', field(response, 'model_version')),
                'duration_seconds': time.perf_counter() - started,
                'provider_invocations': 1, 'sdk_calls': int(call.sdk_invoked), 'sdk_network_attempts': None,
                'request_payload_utf8_bytes': request_bytes,
                'response_received': response is not None,
                'payload_boundary': 'Serialized message content only; excludes protocol and SDK overhead',
                'error_type': error_type, 'monetary_cost': None,
                **token_usage(response, provider),
            }
            # A measurement failure must not hide a provider exception or prevent
            # processing a successful robot plan. The caller can inspect last_error.
            try:
                with open(self.path, 'a', encoding='utf-8') as stream:
                    stream.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + '\n')
                self.last_error = None
            except (OSError, ValueError, TypeError) as exc:
                self.last_error = type(exc).__name__
