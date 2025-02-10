import { useEffect, useState } from 'react'
import { supabase } from '../lib/supabase'
import { Link } from 'react-router-dom'

interface CreditInfo {
  credit_amount: number
  updated_at: string
}

export default function BillingPage() {
  const [credits, setCredits] = useState<CreditInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  console.log('BillingPage: Component rendering')

  useEffect(() => {
    async function fetchCredits() {
      console.log('BillingPage: Fetching credits')
      try {
        const { data, error } = await supabase
          .from('credits')
          .select('credit_amount, updated_at')
          .single()

        if (error) throw error
        console.log('BillingPage: Credits fetched:', data)
        setCredits(data)
      } catch (e) {
        const message = e instanceof Error ? e.message : 'Failed to fetch credits'
        console.error('BillingPage: Error:', message)
        setError(message)
      } finally {
        setLoading(false)
      }
    }

    fetchCredits()
  }, [])

  if (loading) return <div className="p-4">Loading credit information...</div>
  if (error) return <div className="p-4 text-red-500">Error: {error}</div>

  return (
    <div className="container mx-auto p-4 max-w-2xl">
      <h1 className="text-3xl font-bold mb-8">Credits & Billing</h1>
      
      <div className="bg-white p-6 rounded-lg shadow-sm mb-8">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-semibold">Current Balance</h2>
          <span className="text-2xl font-bold">{credits?.credit_amount || 0} credits</span>
        </div>
        <p className="text-sm text-gray-500">
          Last updated: {credits?.updated_at ? new Date(credits.updated_at).toLocaleDateString() : 'Never'}
        </p>
      </div>

      <div className="bg-white p-6 rounded-lg shadow-sm">
        <h2 className="text-xl font-semibold mb-4">Get More Credits</h2>
        <Link 
          to="#" 
          className="inline-block bg-blue-500 text-white px-6 py-3 rounded-lg hover:bg-blue-600 transition-colors"
        >
          Purchase Credits
        </Link>
      </div>
    </div>
  )
} 