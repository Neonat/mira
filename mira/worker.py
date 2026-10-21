"""One bounded extraction attempt; invoked by the local batch runner."""
import json
import sys
from mira.pipeline import process_item


def main():
    try:
        request = json.load(sys.stdin)
        bundle = process_item(request['item'], request['directory'])
        print(json.dumps({'bundle': bundle}))
        return 0
    except Exception as error:
        print(json.dumps({'error': str(error)[:500]}))
        return 1


if __name__ == '__main__':
    sys.exit(main())
