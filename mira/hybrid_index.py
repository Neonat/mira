"""Explicit bounded archive backfill. Preview is offline; no research/fetch work."""
import argparse
from dataclasses import replace
from datetime import date
import json
import os
import sys
from types import SimpleNamespace
from uuid import UUID


def main(argv=None,*,factory=None,connector=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',type=UUID,required=True)
    parser.add_argument('--actor',type=UUID,required=True)
    parser.add_argument('--jurisdiction',choices=['HK','SG','INT'],required=True)
    parser.add_argument('--as-of',type=date.fromisoformat,required=True)
    parser.add_argument('--max-tokens',type=int,default=20000)
    parser.add_argument('--max-seconds',type=float,default=60)
    parser.add_argument('--max-characters',type=int,default=60000)
    parser.add_argument('--max-batches',type=int,default=4)
    parser.add_argument('--batch-size',type=int,default=40)
    parser.add_argument('--execute',action='store_true',help='allow embedding API calls and private cache writes')
    args=parser.parse_args(argv)
    try:
        if not (0<args.max_tokens<=1_000_000 and 0<args.max_seconds<=300
                and 0<args.max_characters<=1_000_000 and 0<args.max_batches<=1000 and 0<args.batch_size<=2048):
            raise ValueError('invalid finite indexing bounds')
        planned={k:v for k,v in vars(args).items()}
        if not args.execute:
            print(json.dumps(planned,default=str))
            return 0
        from mira.config import load_env
        from mira.runner import hybrid_from_env
        from mira.db import connect,acting_as,require_role
        from mira.pg_store import PostgresStore
        load_env()
        retriever=(factory or hybrid_from_env)()
        if retriever is None:raise ValueError('hybrid retrieval disabled')
        retriever.limits=replace(retriever.limits,max_tokens=args.max_tokens,timeout_seconds=args.max_seconds,
                                 max_characters=args.max_characters,max_index_batches=args.max_batches,max_index_passages=args.batch_size)
        with (connector or connect)(os.environ['MIRA_WORKER_DATABASE_URL']) as conn:
            with acting_as(conn,args.actor):require_role(conn,args.workspace)
            ctx=SimpleNamespace(workspace_id=args.workspace,user_id=args.actor,
                brief=SimpleNamespace(jurisdictions=[args.jurisdiction],as_of_date=args.as_of))
            sources=PostgresStore(conn).list_sources(args.workspace)
            # The archive SQL independently excludes MAS before indexing/ranking.
            task=SimpleNamespace(source_ids=[s.id for s in sources],
                jurisdiction_code=args.jurisdiction,question='')
            result=retriever.index(conn,ctx,task,remaining_tokens=args.max_tokens,remaining_seconds=args.max_seconds)
        # Passage text, vectors and credentials never enter operator output.
        output={k:v for k,v in vars(result).items() if k not in ('passages','vectors')}
        output['status']='complete' if (result.coverage_known and not result.pending_passages
            and result.cache_error is None and result.fallback_reason is None) else 'partial'
        print(json.dumps(output,default=str))
        return 0
    except Exception as exc:
        print(f'Archive indexing refused ({type(exc).__name__}); check local configuration and bounds.',file=sys.stderr)
        return 2


if __name__=='__main__':
    raise SystemExit(main())
