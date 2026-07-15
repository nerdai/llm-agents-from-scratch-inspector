import { Button } from '@/components/ui/button'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/components/ui/sheet'
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
 * `GET /api/templates` -- the framework's default prompt templates.
 * Not session-scoped, so its trigger lives in the app header and works
 * even before a session exists (see `useTemplates`).
 */
function TemplatesDrawer() {
  const { data, isLoading, isError, error } = useTemplates()

  return (
    <Sheet>
      <SheetTrigger render={<Button type="button" variant="outline" />}>
        Templates
      </SheetTrigger>
      <SheetContent side="right" className="w-full sm:max-w-xl">
        <SheetHeader>
          <SheetTitle>Prompt templates</SheetTitle>
          <SheetDescription>
            The framework&apos;s default prompt templates, shared across every
            session&apos;s agent.
          </SheetDescription>
        </SheetHeader>
        <div className="flex flex-col gap-4 overflow-y-auto px-4 pb-4">
          {isLoading && (
            <p className="text-sm text-muted-foreground">Loading templates…</p>
          )}
          {isError && (
            <p className="text-sm text-destructive">
              Failed to load templates
              {error instanceof Error ? `: ${error.message}` : '.'}
            </p>
          )}
          {data &&
            TEMPLATE_KEYS.map((key) => (
              <div key={key} className="flex flex-col gap-1.5">
                <span className="font-mono text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                  {TEMPLATE_LABELS[key]}
                </span>
                <HighlightedBlock code={data[key]} />
              </div>
            ))}
        </div>
      </SheetContent>
    </Sheet>
  )
}

export default TemplatesDrawer
