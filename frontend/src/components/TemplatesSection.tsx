import { useState } from 'react'
import { ChevronDown } from 'lucide-react'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { cn } from '@/lib/utils'
import { useTemplates } from '../api/hooks'
import type { TemplatesOut } from '../api/types'
import HighlightedBlock from './HighlightedBlock'

const TEMPLATE_LABELS: Record<keyof TemplatesOut, string> = {
  system_message: 'system_message',
  get_next_step: 'get_next_step',
  step_rollout_chat_message: 'step_rollout_chat_message',
  step_rollout_content_instruction: 'step_rollout_content_instruction',
  step_rollout_content_tool_call_request:
    'step_rollout_content_tool_call_request',
  run_step_system_message_without_rollout:
    'run_step_system_message_without_rollout',
  run_step_system_message: 'run_step_system_message',
  run_step_user_message: 'run_step_user_message',
  skills_catalog: 'skills_catalog',
  memories: 'memories',
  approval_rejection_feedback: 'approval_rejection_feedback',
}

const TEMPLATE_KEYS = Object.keys(TEMPLATE_LABELS) as (keyof TemplatesOut)[]

/**
 * `GET /api/templates` -- scoped to the discovered agent same as
 * Tools/Model/Skills (`LLMAgentBuilder.with_templates(...)` exists in
 * the framework), grouped under `ConfigRail`'s "LLM Agent" heading
 * alongside them. Rendered regardless of whether a session exists
 * yet because the backend endpoint doesn't take a session id -- it
 * always returns the framework's hardcoded default rather than the
 * discovered builder's actual templates (issue #82) -- not because
 * templates themselves are somehow agent-independent. A vertical
 * accordion, same as the earlier `TemplatesDrawer` overlay's contents
 * but living in the rail instead of a separate top-level feature.
 * Collapsed by default, same as `RolloutPanel`, since the full set of
 * templates is a lot of text for a 320px-wide rail.
 */
function TemplatesSection() {
  const [open, setOpen] = useState(false)
  const { data, isLoading, isError, error } = useTemplates()

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger className="group/templates flex w-full items-center gap-1.5 text-left">
        <span className="text-[10.5px] font-semibold tracking-wide text-muted-foreground uppercase">
          Templates
        </span>
        <ChevronDown
          className={cn(
            'size-3 flex-none text-muted-foreground transition-transform',
            open && 'rotate-180',
          )}
        />
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="flex flex-col gap-3 pt-2">
          {isLoading && (
            <p className="text-xs text-muted-foreground">Loading templates…</p>
          )}
          {isError && (
            <p className="text-xs text-destructive">
              Failed to load templates
              {error instanceof Error ? `: ${error.message}` : '.'}
            </p>
          )}
          {data &&
            TEMPLATE_KEYS.map((key) => (
              <div key={key} className="flex flex-col gap-1">
                <span className="font-mono text-[10px] font-semibold tracking-wide text-muted-foreground uppercase">
                  {TEMPLATE_LABELS[key]}
                </span>
                <HighlightedBlock code={data[key]} />
              </div>
            ))}
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}

export default TemplatesSection
