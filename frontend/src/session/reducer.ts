import type {
  CompleteResponse,
  CreateSessionResponse,
  NextStepResponse,
  RunStepResponse,
} from '../api/types'
import { initialSessionState, type SessionState } from './types'

export type Action =
  | { type: 'session/start' }
  | { type: 'session/success'; payload: CreateSessionResponse }
  | { type: 'session/error'; error: string }
  | { type: 'next/start' }
  | { type: 'next/success'; payload: NextStepResponse }
  | { type: 'next/error'; error: string }
  | { type: 'run/start' }
  | { type: 'run/success'; payload: RunStepResponse }
  | { type: 'run/error'; error: string }
  | { type: 'complete/start' }
  | { type: 'complete/success'; payload: CompleteResponse }
  | { type: 'complete/error'; error: string }
  | { type: 'reset' }

function nextEntryId(
  prefix: string,
  timeline: SessionState['timeline'],
): string {
  return `${prefix}-${timeline.length + 1}`
}

export function sessionReducer(
  state: SessionState,
  action: Action,
): SessionState {
  switch (action.type) {
    case 'session/start':
      return { ...initialSessionState, loading: true }

    case 'session/success':
      return {
        ...initialSessionState,
        sessionId: action.payload.session_id,
        task: action.payload.task,
        tools: action.payload.tools,
        skills: action.payload.skills,
        need: action.payload.need,
        loading: false,
      }

    case 'session/error':
      return { ...initialSessionState, loading: false, error: action.error }

    case 'next/start':
      return { ...state, loading: true, error: null }

    case 'next/success': {
      const res = action.payload
      if (res.kind === 'next_step') {
        return {
          ...state,
          loading: false,
          need: res.need,
          timeline: [
            ...state.timeline,
            {
              kind: 'overseer',
              id: nextEntryId('overseer', state.timeline),
              outcome: 'next_step',
              decision: res.decision,
              step: res.step,
            },
          ],
        }
      }
      return {
        ...state,
        loading: false,
        need: res.need,
        finalResult: res.result,
        timeline: [
          ...state.timeline,
          {
            kind: 'overseer',
            id: nextEntryId('overseer', state.timeline),
            outcome: 'final_result',
            result: res.result,
          },
        ],
      }
    }

    case 'next/error':
      return { ...state, loading: false, error: action.error }

    case 'run/start':
      return { ...state, loading: true, error: null }

    case 'run/success':
      return {
        ...state,
        loading: false,
        need: action.payload.need,
        timeline: [
          ...state.timeline,
          {
            kind: 'worker',
            id: nextEntryId('worker', state.timeline),
            result: action.payload.result,
            toolCalls: action.payload.tool_calls,
            stepCounter: action.payload.step_counter,
          },
        ],
      }

    case 'run/error':
      return { ...state, loading: false, error: action.error }

    case 'complete/start':
      return { ...state, loading: true, error: null }

    case 'complete/success':
      return {
        ...state,
        loading: false,
        need: action.payload.need,
        completedResult: action.payload.result,
      }

    case 'complete/error':
      return { ...state, loading: false, error: action.error }

    case 'reset':
      return initialSessionState

    default:
      return state
  }
}
