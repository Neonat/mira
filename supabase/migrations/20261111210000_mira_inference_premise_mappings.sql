-- Preserve verified passage references from new inference checks without
-- changing earlier checks or their frozen evidence inputs.
alter table public.claim_checks
  add column premise_mappings jsonb,
  add constraint claim_checks_premise_mappings_shape check (
    premise_mappings is null or (
      method = 'inference_check'
      and input_snapshot is not null
      and jsonb_typeof(premise_mappings) = 'array'
      and premise_mappings <> '[]'::jsonb
    )
  );

comment on column public.claim_checks.premise_mappings is
  'Exact verifier-selected quotations keyed by dependency finding and passage within the frozen input. NULL means no validated mapping was recorded.';
