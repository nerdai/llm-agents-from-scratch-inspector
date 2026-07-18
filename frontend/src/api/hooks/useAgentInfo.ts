import { useQuery } from '@tanstack/react-query'
import { fetchAgentInfo } from '../client'
import { queryKeys } from '../queryKeys'

/**
 * `GET /api/agent-info` -- the discovered agent's static properties
 * (model, tools, default_task). Not session-scoped: unlike skills,
 * these are fixed by the discovered `LLMAgentBuilder` itself, so
 * they're readable before any session exists (see
 * `routes/session.py`'s `get_discovered_agent_info`).
 */
export function useAgentInfo() {
  return useQuery({
    queryKey: queryKeys.agentInfo,
    queryFn: fetchAgentInfo,
  })
}
