import { useEffect, useState, type ReactNode } from 'react'
import { NavLink } from 'react-router-dom'

import type { Role } from '../api/types'
import { useAuth } from '../lib/auth'

interface NavItem {
  to: string
  label: string
  glyph: string
  roles?: Role[]
}

const NAV: { section: string; items: NavItem[] }[] = [
  {
    section: 'Overview',
    items: [
      { to: '/', label: 'Dashboard', glyph: '◎' },
      { to: '/workflow', label: 'Process map', glyph: '⇄' },
    ],
  },
  {
    section: 'Production',
    items: [
      { to: '/orders', label: 'Work orders', glyph: '▤' },
      { to: '/terminal', label: 'Shop floor', glyph: '⌗' },
      { to: '/calendar', label: 'Calendar', glyph: '▦' },
      { to: '/optimize', label: 'Optimisation', glyph: '◈' },
    ],
  },
  {
    section: 'Materials',
    items: [{ to: '/inventory', label: 'Inventory', glyph: '▦' }],
  },
  {
    section: 'Quality',
    items: [{ to: '/quality', label: 'Inspections & NCRs', glyph: '✓' }],
  },
  {
    section: 'Equipment',
    items: [{ to: '/equipment', label: 'Machines & OEE', glyph: '⚙' }],
  },
  {
    section: 'Configuration',
    items: [
      { to: '/master-data', label: 'Master data', glyph: '☰' },
      { to: '/accounts', label: 'Accounts', glyph: '⚇' },
    ],
  },
]

const THEME_KEY = 'ipms.theme'
type Theme = 'system' | 'light' | 'dark'

function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(() => (localStorage.getItem(THEME_KEY) as Theme) || 'system')

  useEffect(() => {
    if (theme === 'system') document.documentElement.removeAttribute('data-theme')
    else document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem(THEME_KEY, theme)
  }, [theme])

  const cycle = () => setTheme((current) => (current === 'system' ? 'light' : current === 'light' ? 'dark' : 'system'))
  return [theme, cycle]
}

export function Layout({
  title,
  subtitle,
  actions,
  children,
}: {
  title: string
  subtitle?: ReactNode
  actions?: ReactNode
  children: ReactNode
}) {
  const { user, signOut, can } = useAuth()
  const [theme, cycleTheme] = useTheme()
  const themeGlyph = theme === 'dark' ? '☾' : theme === 'light' ? '☀' : '◐'

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="mark">IPMS</div>
          <div className="plant">Sample Assembly Factory</div>
        </div>
        <nav className="nav">
          {NAV.map((group) => {
            const visible = group.items.filter((item) => !item.roles || can(...item.roles))
            if (!visible.length) return null
            return (
              <div key={group.section}>
                <div className="nav-section">{group.section}</div>
                {visible.map((item) => (
                  <NavLink key={item.to} to={item.to} end={item.to === '/'}>
                    <span className="glyph" aria-hidden="true">
                      {item.glyph}
                    </span>
                    {item.label}
                  </NavLink>
                ))}
              </div>
            )
          })}
        </nav>
        <div className="sidebar-foot">
          <div className="who">
            <div className="name">{user?.full_name}</div>
            <div className="role">{user?.role}</div>
          </div>
          <button className="ghost sm" onClick={signOut} title="Sign out">
            ⏻
          </button>
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <div>
            <h1>{title}</h1>
            {subtitle && <div className="sub">{subtitle}</div>}
          </div>
          <div className="topbar-actions">
            {actions}
            <button className="ghost sm" onClick={cycleTheme} title={`Theme: ${theme}`} aria-label="Change theme">
              {themeGlyph}
            </button>
          </div>
        </header>
        <main className="content">{children}</main>
      </div>
    </div>
  )
}
