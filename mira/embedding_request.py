"""One isolated embedding request with a hard process deadline."""
import json
import subprocess
import sys


class RequestTimeout(Exception):
    pass


def bounded_request(payload, *, timeout_seconds, command=None):
    if timeout_seconds <= 0:
        raise RequestTimeout('no time remaining')
    if command is None:
        command = [sys.executable, '-c', 'from mira.embedding_request import child; child()']
    try:
        result = subprocess.run(command, input=json.dumps(payload).encode(), capture_output=True,
                                timeout=timeout_seconds, check=True)
        value = json.loads(result.stdout)
        if not isinstance(value, dict):
            raise ValueError('invalid child response')
        return value
    except subprocess.TimeoutExpired:
        # subprocess.run kills and waits for its child before raising.
        raise RequestTimeout('embedding request timed out') from None
    except (subprocess.SubprocessError, ValueError, OSError):
        raise RuntimeError('embedding request failed') from None


def child():
    """Construct a fresh SDK client; credentials and text only arrive on stdin."""
    payload = json.load(sys.stdin)
    tokens = None
    try:
        from openai import OpenAI
        options = {'api_key': payload['api_key'], 'base_url': payload['base_url'],
                   'timeout': payload['timeout_seconds'], 'max_retries': 0}
        if payload.get('organization'):
            options['organization'] = payload['organization']
        if payload.get('project'):
            options['project'] = payload['project']
        client = OpenAI(**options)
        response = client.embeddings.create(model=payload['model'], input=payload['texts'],
                                            dimensions=payload['dimensions'])
        tokens = response.usage.total_tokens
        if not isinstance(tokens, int) or isinstance(tokens, bool) or tokens < 0:
            tokens = None
            raise ValueError('missing usage')
        data = [{'index': item.index, 'values': item.embedding} for item in response.data]
        output = {'tokens': tokens, 'data': data}
    except Exception:
        output = {'error': True, 'tokens': tokens}
    try:
        encoded = json.dumps(output, allow_nan=False)
    except (TypeError, ValueError):
        encoded = json.dumps({'error': True, 'tokens': tokens})
    sys.stdout.write(encoded)
