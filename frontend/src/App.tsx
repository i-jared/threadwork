import { BrowserRouter as Router, Routes, Route, Link, useLocation } from 'react-router-dom'
import SuccessPage from './pages/Success'
import { useEffect } from 'react'
import HomePage from './pages/Home'
import BillingPage from './pages/Billing'

// Component to log route changes
function RouteLogger() {
  const location = useLocation()
  
  useEffect(() => {
    console.log('Route changed:', location.pathname)
  }, [location])
  
  return null
}

function App() {
  console.log('App component rendering')

  useEffect(() => {
    console.log('App component mounted')
    return () => {
      console.log('App component unmounting')
    }
  }, [])

  return (
    <Router>
      <RouteLogger />
      <div className="min-h-screen bg-gray-50">
        <nav className="bg-white shadow-sm">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="flex justify-between h-16">
              <div className="flex">
                <Link to="/" className="flex items-center px-2 py-2 text-gray-900">
                  Home
                </Link>
                <Link to="/success" className="flex items-center px-2 py-2 text-gray-900">
                  Success Page
                </Link>
                <Link to="/billing" className="flex items-center px-2 py-2 text-gray-900">
                  Credits & Billing
                </Link>
              </div>
            </div>
          </div>
        </nav>

        <main>
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/success" element={<SuccessPage />} />
            <Route path="/billing" element={<BillingPage />} />
          </Routes>
        </main>
      </div>
    </Router>
  )
}

export default App
