import { Navigate, Route, Routes } from 'react-router-dom'

import { useAuth } from './lib/auth'
import { Accounts } from './pages/Accounts'
import { CalendarPage } from './pages/CalendarPage'
import { Dashboard } from './pages/Dashboard'
import { Equipment } from './pages/Equipment'
import { Inventory } from './pages/Inventory'
import { Login } from './pages/Login'
import { MasterData } from './pages/MasterData'
import { Optimize } from './pages/Optimize'
import { OrderDetail } from './pages/OrderDetail'
import { Orders } from './pages/Orders'
import { Quality } from './pages/Quality'
import { Terminal } from './pages/Terminal'
import { Workflow } from './pages/Workflow'

export function App() {
  const { user, loading } = useAuth()

  if (loading) {
    return (
      <div className="login-page">
        <div className="muted">Starting IPMS...</div>
      </div>
    )
  }

  if (!user) {
    return (
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    )
  }

  return (
    <Routes>
      <Route path="/" element={<Dashboard />} />
      <Route path="/workflow" element={<Workflow />} />
      <Route path="/optimize" element={<Optimize />} />
      <Route path="/calendar" element={<CalendarPage />} />
      <Route path="/accounts" element={<Accounts />} />
      <Route path="/orders" element={<Orders />} />
      <Route path="/orders/:orderId" element={<OrderDetail />} />
      <Route path="/terminal" element={<Terminal />} />
      <Route path="/inventory" element={<Inventory />} />
      <Route path="/quality" element={<Quality />} />
      <Route path="/equipment" element={<Equipment />} />
      <Route path="/master-data" element={<MasterData />} />
      <Route path="/login" element={<Navigate to="/" replace />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
