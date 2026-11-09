"""One thread-safe admission ledger for bounded model and embedding work.

Entries contain sizes and usage, never prompts, source text or credentials.
Known usage and unknown attempted usage stay distinct. A local refusal costs zero.
"""
from __future__ import annotations

import threading
import time

from mira.llm import LLMError,request_token_reservation


class GenerationBudget:
    def __init__(self,max_tokens:int,max_seconds:float,*,clock=time.monotonic,on_change=None):
        if max_tokens<=0 or max_seconds<=0:raise ValueError('positive generation limits required')
        self.max_tokens=max_tokens;self.max_seconds=max_seconds;self.clock=clock;self.started=clock();self.deadline=self.started+max_seconds
        self.known=0;self.unknown=0;self.pending=0;self.calls=[];self.lock=threading.RLock();self.on_change=on_change

    def remaining_seconds(self):return max(0.,self.deadline-self.clock())

    def _protected(self,role):
        if role=='writer':return 0
        if role in ('planner','regulatory_scout','industry_scout','experimental_hybrid'):
            return min(60000,self.max_tokens//3)
        if role=='analyst':return min(40000,self.max_tokens//4)
        return min(20000,self.max_tokens//5)

    def protected_seconds(self,role):
        if role=='writer':return 0
        if role in ('planner','regulatory_scout','industry_scout','experimental_hybrid'):
            return min(360,self.max_seconds/3)
        return min(120,self.max_seconds/5)

    def _publish(self):
        if self.on_change is not None:self.on_change(self.snapshot())

    def snapshot(self):
        with self.lock:
            return {'max_tokens':self.max_tokens,'known_tokens':self.known,'unknown_reserved_tokens':self.unknown,
                    'pending_tokens':self.pending,'allowance_used':self.known+self.unknown+self.pending,
                    'elapsed_seconds':round(self.clock()-self.started,3),'calls':[dict(c) for c in self.calls]}

    def start(self,kind,role,reservation,*,input_bytes=0):
        with self.lock:
            if reservation<0:raise ValueError('negative generation reservation')
            if (self.remaining_seconds()<=self.protected_seconds(role)
                    or self.known+self.unknown+self.pending+reservation+self._protected(role)>self.max_tokens):
                raise LLMError('generation admission refused: downstream reserve or deadline',request_sent=False)
            item={'kind':kind,'role':role,'reservation_tokens':reservation,'input_bytes':input_bytes,
                  'status':'pending','request_sent':None,'known_tokens':0,'unknown_reserved_tokens':0,
                  'started_seconds':round(self.clock()-self.started,3)}
            self.calls.append(item);self.pending+=reservation;self._publish();return item

    def finish(self,item,*,known=None,error=None,model=None):
        with self.lock:
            if item['status']!='pending':raise ValueError('generation call already settled')
            reservation=item['reservation_tokens'];self.pending-=reservation
            if error is None:
                known=known or 0;unknown=0;sent=True;status='complete'
            else:
                sent=getattr(error,'request_sent',None)
                measured=getattr(error,'tokens',None)
                if measured is None:
                    measured=getattr(error,'tokens_in',0)+getattr(error,'tokens_out',0)
                known=measured or 0
                unknown=(getattr(error,'reserved_tokens',0) or (reservation if not known and sent is not False else 0))
                if sent is False:unknown=0
                status='not_sent' if sent is False else 'failed'
            self.known+=known;self.unknown+=unknown
            item.update(status=status,request_sent=sent,known_tokens=known,unknown_reserved_tokens=unknown,
                        elapsed_seconds=round(self.clock()-self.started-item['started_seconds'],3))
            if model is not None:item['model']=model
            if error is not None:item['error_code']=getattr(error,'code',type(error).__name__)
            self._publish()


class GenerationClient:
    """Bound ordinary calls too, using the configured provider/model unchanged."""
    def __init__(self,base,budget:GenerationBudget):self.base=base;self.budget=budget

    def structured(self,**kwargs):
        role=kwargs['role']
        return self.structured_bounded(timeout_seconds=90 if role=='verifier' else 120,
                                       max_output_tokens=4096 if role=='verifier' else 8192,**kwargs)

    def structured_bounded(self,*,timeout_seconds,max_output_tokens,**kwargs):
        if not callable(getattr(self.base,'structured_bounded',None)):
            raise LLMError('client does not support bounded generation',request_sent=False)
        remaining=self.budget.remaining_seconds()
        timeout=min(timeout_seconds,remaining-self.budget.protected_seconds(kwargs['role']))
        if timeout<=0:raise LLMError('generation deadline reached',request_sent=False)
        reservation=request_token_reservation(system=kwargs['system'],user=kwargs['user'],
                                              output_type=kwargs['output_type'],max_output_tokens=max_output_tokens)
        item=self.budget.start('model',kwargs['role'],reservation,
                               input_bytes=len((kwargs['system']+kwargs['user']).encode()))
        try:
            result=self.base.structured_bounded(timeout_seconds=timeout,max_output_tokens=max_output_tokens,**kwargs)
        except Exception as error:
            self.budget.finish(item,error=error);raise
        self.budget.finish(item,known=result.tokens_in+result.tokens_out,model=result.model);return result


class GenerationEmbedder:
    def __init__(self,base,budget):self.base=base;self.budget=budget
    def embed(self,texts,*,timeout_seconds):
        from mira.hybrid import EmbeddingError
        size=sum(len(t.encode()) for t in texts)
        reservation=size+1024
        try:item=self.budget.start('embedding','experimental_hybrid',reservation,input_bytes=size)
        except LLMError as error:
            raise EmbeddingError(str(error),tokens=0,request_sent=False) from error
        try:result=self.base.embed(texts,timeout_seconds=min(timeout_seconds,self.budget.remaining_seconds()-self.budget.protected_seconds('experimental_hybrid')))
        except Exception as error:
            if getattr(error,'tokens',None) is None and hasattr(error,'reserved_tokens'):
                error.reserved_tokens=reservation
            self.budget.finish(item,error=error);raise
        self.budget.finish(item,known=result.tokens);return result
