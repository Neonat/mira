"""One thread-safe admission ledger for bounded model and embedding work.

Entries contain sizes and usage, never prompts, source text or credentials.
Known usage and unknown attempted usage stay distinct. A local refusal costs zero.
"""
from __future__ import annotations

import math
import threading
import time
from mira.contracts import ClaimDraft
from mira.spending import SpendingError

from mira.llm import LLMError,request_token_reservation


class GenerationBudget:
    def __init__(self,max_tokens:int,max_seconds:float,*,clock=time.monotonic,on_change=None,
                 spending=None,models=None,initial_usage=None):
        if max_tokens<=0 or max_seconds<=0:raise ValueError('positive generation limits required')
        self.max_tokens=max_tokens;self.max_seconds=max_seconds;self.clock=clock;self.started=clock();self.deadline=self.started+max_seconds
        self.known=0;self.unknown=0;self.pending=0;self.calls=[];self.lock=threading.RLock();self.on_change=on_change
        self.spending=spending;self.models=dict(models or {});self.journal_failed=False;self.pricing_mismatch=False
        if initial_usage is not None:
            def counter(value):
                if isinstance(value,bool) or not isinstance(value,int) or value<0:
                    raise ValueError('Invalid restored usage counter')
                return value
            def seconds(value):
                if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<0:
                    raise ValueError('Invalid restored elapsed time')
                return value
            self.known=counter(initial_usage.get('known_tokens',0))
            pending=counter(initial_usage.get('pending_tokens',0))
            self.unknown=counter(initial_usage.get('unknown_reserved_tokens',0))+pending
            elapsed=seconds(initial_usage.get('elapsed_seconds',0))
            self.started-=elapsed;self.deadline-=elapsed
            self.pricing_mismatch=initial_usage.get('pricing_mismatch',False) is not False
            self.journal_failed=initial_usage.get('journal_available',True) is not True
            self.calls=[dict(c) for c in initial_usage.get('calls',[])]
            pending_calls=0
            for call in self.calls:
                for key in ('reservation_tokens','input_bytes','known_tokens','unknown_reserved_tokens','tokens_in','tokens_out'):
                    if key in call:counter(call[key])
                for key in ('started_seconds','elapsed_seconds'):
                    if key in call:seconds(call[key])
                if call.get('status')=='pending':
                    reserved=counter(call.get('reservation_tokens',0));pending_calls+=reserved
                    call.update(status='failed',request_sent=None,usage_known=False,unknown_reserved_tokens=reserved)
            if pending_calls>pending:raise ValueError('Restored pending calls exceed pending tokens')

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
        return min(120,self.max_seconds/10)

    def _publish(self):
        if self.on_change is not None:
            try:self.on_change(self.snapshot())
            except Exception:self.journal_failed=True

    def snapshot(self):
        with self.lock:
            value={'max_tokens':self.max_tokens,'known_tokens':self.known,'unknown_reserved_tokens':self.unknown,
                    'pending_tokens':self.pending,'allowance_used':self.known+self.unknown+self.pending,
                    'elapsed_seconds':round(self.clock()-self.started,3),'calls':[dict(c) for c in self.calls]}
            if self.spending is not None:value['spending']=self.spending.snapshot()
            if self.journal_failed:value['journal_available']=False
            if self.pricing_mismatch:value['pricing_mismatch']=True
            return value

    def start(self,kind,role,reservation,*,input_bytes=0):
        with self.lock:
            if reservation<0:raise ValueError('negative generation reservation')
            if self.journal_failed or self.pricing_mismatch:
                raise LLMError('Usage journal or pricing unavailable; no further request sent',request_sent=False)
            if (self.remaining_seconds()<=self.protected_seconds(role)
                    or self.known+self.unknown+self.pending+reservation+self._protected(role)>self.max_tokens):
                raise LLMError('generation admission refused: downstream reserve or deadline',request_sent=False)
            item={'kind':kind,'role':role,'reservation_tokens':reservation,'input_bytes':input_bytes,
                  'status':'pending','request_sent':None,'known_tokens':0,'unknown_reserved_tokens':0,
                  'started_seconds':round(self.clock()-self.started,3)}
            self.calls.append(item);self.pending+=reservation;self._publish()
            if self.journal_failed:
                self.pending-=reservation
                item.update(status='not_sent',request_sent=False,usage_known=True)
                raise LLMError('Usage journal unavailable; no provider request sent',request_sent=False)
            return item

    def finish(self,item,*,known=None,error=None,model=None,usage=None):
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
            if item['kind']=='model':
                if error is not None and hasattr(error,'tokens_in'):
                    usage=(error.tokens_in,error.tokens_out)
                if usage is not None:item.update(tokens_in=usage[0],tokens_out=usage[1])
            item['usage_known']=error is None or bool(known) or sent is False
            if error is not None:item['error_code']=getattr(error,'code',type(error).__name__)
            self._publish()


class GenerationClient:
    """Bound ordinary calls too, using the configured provider/model unchanged."""
    def __init__(self,base,budget:GenerationBudget):self.base=base;self.budget=budget

    def structured(self,**kwargs):
        role = kwargs["role"]
        output_limit = 16384 if role == "writer" else 8192
        recoverable = role == "verifier" or (role == "analyst" and kwargs["output_type"] is ClaimDraft)
        try:
            return self.structured_bounded(timeout_seconds=120, max_output_tokens=output_limit, **kwargs)
        except LLMError as error:
            remaining = self.budget.remaining_seconds() - self.budget.protected_seconds(role)
            if (not recoverable or error.code not in {"request_timeout", "provider_unavailable"}
                    or error.tokens_in or error.tokens_out or remaining < 30):
                raise
            # Admit a fresh reservation. Usage from the first request remains
            # charged or reserved, even when the second request succeeds.
            return self.structured_bounded(timeout_seconds=150, max_output_tokens=output_limit, **kwargs)

    def structured_bounded(self,*,timeout_seconds,max_output_tokens,**kwargs):
        if not callable(getattr(self.base,'structured_bounded',None)):
            raise LLMError('client does not support bounded generation',request_sent=False)
        remaining=self.budget.remaining_seconds()
        timeout=min(timeout_seconds,remaining-self.budget.protected_seconds(kwargs['role']))
        if timeout<=0:raise LLMError('generation deadline reached',request_sent=False)
        reservation=request_token_reservation(system=kwargs['system'],user=kwargs['user'],
                                              output_type=kwargs['output_type'],max_output_tokens=max_output_tokens)
        ticket=None
        try:
            if self.budget.spending is not None:
                provider,sep,model=self.budget.models[kwargs['role']].partition(':')
                if not sep:raise SpendingError('Model price unavailable')
                ticket=self.budget.spending.reserve_model(kwargs['role'],provider,model,reservation-max_output_tokens,max_output_tokens)
            item=self.budget.start('model',kwargs['role'],reservation,
                                   input_bytes=len((kwargs['system']+kwargs['user']).encode()))
        except Exception as error:
            if ticket is not None:self.budget.spending.settle(ticket,request_sent=False)
            if isinstance(error,LLMError):raise
            raise LLMError('API cost allowance or validated price unavailable; request not sent',request_sent=False) from None
        try:
            timeout=min(timeout_seconds,self.budget.remaining_seconds()-self.budget.protected_seconds(kwargs['role']))
            if timeout<=0:raise LLMError('generation deadline reached',request_sent=False)
            result=self.base.structured_bounded(timeout_seconds=timeout,max_output_tokens=max_output_tokens,**kwargs)
        except Exception as error:
            if ticket is not None:_settle(self.budget,ticket,error=error)
            self.budget.finish(item,error=error);raise
        cost_ok=True
        if ticket is not None:
            aliases={'gpt-5.4-2026-03-05':'gpt-5.4','gpt-5.4-mini-2026-03-17':'gpt-5.4-mini'}
            if aliases.get(result.model,result.model)!=model:
                self.budget.spending.settle(ticket,request_sent=True);self.budget.pricing_mismatch=True
                self.budget.finish(item,known=result.tokens_in+result.tokens_out,model=result.model,
                                   usage=(result.tokens_in,result.tokens_out))
                raise LLMError('Provider returned an unpriced model; further requests stopped',
                    result.tokens_in,result.tokens_out,request_sent=True)
            cost_ok=_settle(self.budget,ticket,result=result)
        self.budget.finish(item,known=result.tokens_in+result.tokens_out,model=result.model,
                           usage=(result.tokens_in,result.tokens_out))
        if not cost_ok:
            raise LLMError('Provider usage exceeded its reserved cost; further requests stopped',
                result.tokens_in,result.tokens_out,request_sent=True)
        return result


class GenerationEmbedder:
    def __init__(self,base,budget):self.base=base;self.budget=budget
    def embed(self,texts,*,timeout_seconds):
        from mira.hybrid import EmbeddingError
        size=sum(len(t.encode()) for t in texts)
        reservation=size+1024
        ticket=None
        try:
            if self.budget.spending is not None:
                ticket=self.budget.spending.reserve_embedding('openai',self.base.identity.model,reservation)
            item=self.budget.start('embedding','experimental_hybrid',reservation,input_bytes=size)
        except Exception as error:
            if ticket is not None:self.budget.spending.settle(ticket,request_sent=False)
            raise EmbeddingError(str(error),tokens=0,request_sent=False) from error
        try:
            timeout=min(timeout_seconds,self.budget.remaining_seconds()-self.budget.protected_seconds('experimental_hybrid'))
            if timeout<=0:raise EmbeddingError('generation deadline reached',tokens=0,request_sent=False)
            result=self.base.embed(texts,timeout_seconds=timeout)
        except Exception as error:
            if getattr(error,'tokens',None) is None and hasattr(error,'reserved_tokens'):
                error.reserved_tokens=reservation
            if ticket is not None:_settle(self.budget,ticket,error=error)
            self.budget.finish(item,error=error);raise
        cost_ok=_settle(self.budget,ticket,result=result) if ticket is not None else True
        self.budget.finish(item,known=result.tokens)
        if not cost_ok:raise EmbeddingError('Provider usage exceeded its reserved cost',tokens=result.tokens,request_sent=True)
        return result


def _settle(budget,ticket,*,error=None,result=None):
    try:
        if error is not None:
            tin=getattr(error,'tokens_in',None);tout=getattr(error,'tokens_out',None)
            if ticket.kind=='embedding':tin=getattr(error,'tokens',None);tout=0 if tin else None
            if not (tin or tout):tin=tout=None
            budget.spending.settle(ticket,tokens_in=tin,tokens_out=tout,request_sent=getattr(error,'request_sent',None))
        elif ticket.kind=='embedding':
            budget.spending.settle(ticket,tokens_in=result.tokens or None,tokens_out=0 if result.tokens else None)
        else:
            budget.spending.settle(ticket,tokens_in=result.tokens_in if result.tokens_in or result.tokens_out else None,
                tokens_out=result.tokens_out if result.tokens_in or result.tokens_out else None)
    except SpendingError:
        budget.pricing_mismatch=True
        return False
    return True


class GenerationSearch:
    """URL-only Exa discovery shares the research run's cost/time admission."""
    def __init__(self,base,budget):self.base=base;self.budget=budget
    def for_domains(self,domains,as_of):
        return GenerationSearch(self.base.for_domains(domains,as_of),self.budget)
    def __call__(self,query,limit,timeout):
        ticket=None
        try:
            if self.budget.spending is not None:ticket=self.budget.spending.reserve_search(limit)
            remaining=self.budget.remaining_seconds()-self.budget.protected_seconds('regulatory_scout')
            if remaining<=0:raise LLMError('Discovery deadline reached',request_sent=False)
            item=self.budget.start('search','regulatory_scout',0,input_bytes=len(query.encode()))
        except Exception:
            if ticket is not None:self.budget.spending.settle(ticket,request_sent=False)
            raise LLMError('Discovery cost allowance, price or deadline unavailable',request_sent=False) from None
        try:
            remaining=self.budget.remaining_seconds()-self.budget.protected_seconds('regulatory_scout')
            if remaining<=0:raise LLMError('Discovery deadline reached',request_sent=False)
            results=self.base(query,limit,min(timeout,remaining))
        except Exception as error:
            if ticket is not None:self.budget.spending.settle(ticket,request_sent=getattr(error,'request_sent',True))
            self.budget.finish(item,error=error);raise
        if ticket is not None:self.budget.spending.settle(ticket,tokens_in=0,tokens_out=0)
        self.budget.finish(item,known=0);return results
