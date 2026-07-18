import { useTheme } from 'next-themes'
import { Moon, Sun } from 'lucide-react'
import { Button } from '@/components/ui/button'

/**
 * Light/dark toggle -- next-themes' `ThemeProvider` (main.tsx) owns
 * persistence (localStorage) and the initial system-preference read;
 * this just flips between the two resolved states rather than
 * cycling through a third "system" option, since the icon itself is
 * the only indicator of which one is active.
 */
function ModeToggle() {
  const { resolvedTheme, setTheme } = useTheme()
  const isDark = resolvedTheme === 'dark'

  return (
    <Button
      variant="ghost"
      size="icon-sm"
      aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      onClick={() => setTheme(isDark ? 'light' : 'dark')}
    >
      {isDark ? <Sun /> : <Moon />}
    </Button>
  )
}

export default ModeToggle
