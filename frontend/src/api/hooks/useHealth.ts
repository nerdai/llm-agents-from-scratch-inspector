import { useQuery } from '@tanstack/react-query'
import { fetchHealth } from '../client'
import { queryKeys } from '../queryKeys'

/** `GET /api/health` -- backend liveness. */
export function useHealth() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: fetchHealth,
  })
}
